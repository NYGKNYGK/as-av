"""SPC 连续数组模型：地形、相机、Maplet 观测关联及磁盘照片。

地形采用 SoA（每个属性一条连续数组）；不同尺寸的 Maplet 按 C 顺序打包。
照片默认存盘，每个实例独占 spc_models/<UUID>/，路径见 model_dir。
images/ 中每张照片保存 float32 灰度和 bool 掩码；LRU 缓存或 memmap 按需读取。

    model = SPCModel(maplet_shapes=[(101, 101)], spacing=[0.1])
    model.maplet_view(0, 'height')[:] = heights
    model.maplet_view(0, 'valid')[:] = True
    result = model.update(photo, K=K, R=R, t=t, sun_direction=sun)
    confidence = model.confidence[model.active_sample_mask]
    model.to_obj(model.model_dir / 'model.obj')

输入契约：调用方保证尺寸、索引、字段名、有限值和相机参数正确；输入时只做数组布局转换，
不重复校验元数据，不检查旋转矩阵正交性或协方差半正定性。Maplet 至少为 2×2，
存储的照片为非空二维灰度图，输入 Maplet→照片 CSR 每行按影像编号递增且唯一。
保留数值求解所需的有效性筛选、容量/步长下限和闭合网格的输出检查。
坐标为小天体固连坐标系、米、弧度；相机轴为右/下/前，像素中心为整数。

数值缓冲可原地更新；结构数组只读，照片和观测通过追加接口扩展。
照片视图只读，修改使用 set_image。update 可能拆分 Maplet 并重建缓冲，旧视图需要重新获取；
dataclasses.replace 同样会创建新的实例目录，照片需由调用方重新导入。
磁盘清单只保存照片尺寸和文件名，相机、地形、观测仍在内存，并非完整模型检查点。
缓存预算只计 LRU 持有的像素/掩码，不含外部引用、操作系统页面缓存和合并临时数组。
超出预算的照片返回 memmap，调用方应分块处理；照片覆盖时保留旧文件，保护已有视图。
实例目录不会随对象销毁而删除，供后续读取照片或放置导出的模型等信息。
update 实现固定相机参数的局部 SPC：中心高度立体匹配、坡度/反照率光度拟合、带锚点积分。
已知反照率且采用 Lambert 模型时，改用高程搜索与局部单位法向联合拟合，保留持久初始先验。
要求已有大致正确且 valid=True 的初始地形和已去畸变、线性辐射定标的二维灰度照片；
太阳方向为表面指向太阳的本体系单位向量。缺失光照的照片仅存储，不参与光度求解。
这不是任务级 SPC 全套软件：不优化相机姿态/轨道、不自动创建初始全局形状、不估计反射函数。
遮挡和投影阴影依据当前 Maplet 三角网格，未覆盖的地形不能作为遮挡物。
confidence 是由支持数、光照条件、拟合残差和锚点质量组成的工程评分，不是标定概率。
方法参考：https://doi.org/10.1186/s40623-023-01814-7 ，SPC method 部分。
模型仅支持单写入者；同一照片应只调用一次 update，避免重复存储。

射线遮挡默认在可用时使用 CuPy/CUDA 并行计算，小任务及无 CUDA 环境使用 NumPy。
环境变量 SPC_RAY_BACKEND=cpu 可强制 CPU，cuda 可强制检查 GPU 后端；默认 auto。
GPU 首次使用包含内核编译开销。照片、Maplet 和求解接口仍使用 NumPy float32。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import OrderedDict
from functools import lru_cache
import json
import os
import warnings
from operator import index as integer_index
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep
from uuid import uuid4

import numpy as np
from scipy.sparse import csr_array
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

if __package__:
    from .config import spc_reconstruct_config as config
    from .obj_reader import TriangleMesh
else:
    from config import spc_reconstruct_config as config
    from obj_reader import TriangleMesh


def _array(value, shape, dtype, *, fill=0, copy=False):
    """统一 dtype、形状和可写 C 连续布局，由 NumPy 完成尺寸转换。

    None 创建默认缓冲；标量广播到已知尺寸。copy=True 用于结构数组，
    避免将模型的只读标记施加到调用方的输入数组上。
    """
    if value is None:
        return np.full(shape, fill, dtype=dtype)
    raw = np.asarray(value, dtype=dtype)
    if raw.ndim == 0:
        raw = np.broadcast_to(raw, shape)
    else:
        raw = raw.reshape(shape)
    if copy:
        return np.array(raw, dtype=dtype, order='C', copy=True)
    return np.require(raw, requirements=['C', 'W'])


def _layout(value):
    """计算各二维块的起止偏移；块 k 对应 offsets[k]:offsets[k+1]。"""
    if value is None:
        shapes = np.empty((0, 2), dtype=np.int32)
    else:
        shapes = np.array(value, dtype=np.int32, order='C', copy=True).reshape(-1, 2)
    counts = shapes.astype(np.int64).prod(axis=1)
    offsets = np.empty(len(shapes) + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(counts, out=offsets[1:])
    return shapes, offsets


def _nonnegative_int(value, name, minimum=0):
    """通过整数索引协议转换，只保留容量/步长下限。"""
    value = integer_index(value)
    if value < minimum:
        raise ValueError(f'{name} 必须是至少为 {minimum} 的整数')
    return value


def _write_image_manifest(directory, shapes, files):
    """先写临时清单再原子替换，使读者只能看到完整版本。"""
    temporary = None
    try:
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                prefix='.manifest.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(dict(format='spc-images-v1', shapes=shapes.tolist(), files=files), stream,
                      ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        for attempt in range(config.MANIFEST_REPLACE_RETRIES + 1):
            try:
                temporary.replace(directory / 'manifest.json')
                break
            except PermissionError as error:
                if getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == config.MANIFEST_REPLACE_RETRIES:
                    raise
                # 保留旧清单的原子性；持续拒绝访问仍报错，不吞掉存储故障。
                sleep(config.MANIFEST_REPLACE_DELAY * 2**attempt)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_image_file(directory, image_id, image, mask):
    """一份不可变文件：小端 float32 亮度平面，随后为 bool 掩码平面。"""
    name = f'image_{image_id:08d}_{uuid4().hex}.bin'
    path = directory / name
    try:
        with path.open('xb') as stream:
            np.asarray(image, dtype='<f4', order='C').tofile(stream)
            mask.tofile(stream)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return name


def _unit(vectors):
    """最后一维归一化，所有几何计算保持 float32。"""
    return vectors / np.maximum(np.linalg.norm(vectors, axis=-1, keepdims=True), config.NUMERICAL_EPSILON)


def _bilinear(values, u, v, mask=None):
    """双线性采样；越界或参与插值的像素无效时返回 False。"""
    ny, nx = values.shape
    inside = np.isfinite(u) & np.isfinite(v) & (u >= 0) & (v >= 0) & (u <= nx - 1) & (v <= ny - 1)
    x = np.clip(np.nan_to_num(u), 0, nx - 1)
    y = np.clip(np.nan_to_num(v), 0, ny - 1)
    x0, y0 = x.astype(np.int64), y.astype(np.int64)
    x1, y1 = np.minimum(x0 + 1, nx - 1), np.minimum(y0 + 1, ny - 1)
    dx, dy = x - x0.astype(np.float32), y - y0.astype(np.float32)
    result = np.zeros(u.shape, dtype=np.float32)
    for row, col, weight in ((y0, x0, (1-dx)*(1-dy)), (y0, x1, dx*(1-dy)),
                             (y1, x0, (1-dx)*dy), (y1, x1, dx*dy)):
        samples = values[row, col]
        usable = np.isfinite(samples)
        if mask is not None:
            usable &= mask[row, col]
        inside &= usable | (weight == 0)
        result += np.where(usable, samples, 0) * weight
    return result, inside


def _reflectance(p, q, sun, view, *, derivatives=True):
    """Lunar-Lambert 反射率及对两方向坡度的解析导数，未包含反照率。

    n=(-p,-q,1)/sqrt(1+p²+q²)，F=(1-L)*cos(i)+2L*cos(i)/(cos(i)+cos(e))。
    混合系数固定；本实现不拟合相位函数。阴影和背面由调用方的观测掩码剔除。
    derivatives=False 跳过两方向导数的数组计算，返回的 fp/fq 为 None。
    """
    length = np.sqrt(1 + p*p + q*q)
    normal = np.stack((-p, -q, np.ones_like(p)), axis=-1) / length[..., None]
    ci = np.sum(normal * sun, axis=-1)
    ce = np.sum(normal * view, axis=-1)
    denominator = np.maximum(ci + ce, config.NUMERICAL_EPSILON)
    mix = config.LUNAR_LAMBERT_WEIGHT
    reflectance = (1 - mix) * ci + 2 * mix * ci / denominator
    if not derivatives:
        return reflectance, None, None, ci, ce
    d_ci = (1 - mix) + 2 * mix * ce / (denominator * denominator)
    d_ce = -2 * mix * ci / (denominator * denominator)
    dp = -normal * (p / (length * length))[..., None]
    dq = -normal * (q / (length * length))[..., None]
    dp[..., 0] -= 1 / length
    dq[..., 1] -= 1 / length
    fp = d_ci * np.sum(dp * sun, axis=-1) + d_ce * np.sum(dp * view, axis=-1)
    fq = d_ci * np.sum(dq * sun, axis=-1) + d_ce * np.sum(dq * view, axis=-1)
    return reflectance, fp, fq, ci, ce


def _closed_mesh_topology(vertices, faces):
    """验证实际输出是无退化面、绕序一致且边/顶点均为二流形的闭合网格。"""
    if not len(vertices) or not len(faces) or not np.isfinite(vertices).all():
        raise ValueError('曲面重建产生空网格或非有限坐标')
    if faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError('重建面索引越界')
    if len(np.unique(faces)) != len(vertices):
        raise ValueError('重建包含未引用顶点')
    triangles = vertices[faces].astype(np.float64)
    cross = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    if np.any(np.linalg.norm(cross, axis=1) == 0):
        raise ValueError('重建含退化三角面；请调整 depth 或输入 Maplet 分辨率')
    if len(np.unique(np.sort(faces, axis=1), axis=0)) != len(faces):
        raise ValueError('重建含重复三角面')
    edges = faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2)
    unique, inverse, counts = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True, return_counts=True)
    boundary = int(np.count_nonzero(counts == 1))
    nonmanifold = int(np.count_nonzero(counts > 2))
    if boundary or nonmanifold:
        raise ValueError(f'闭合融合失败：{boundary} 条开放边，{nonmanifold} 条非流形边；目标 OBJ 未覆盖')
    sign = np.where(edges[:, 0] < edges[:, 1], 1, -1)
    if np.any(np.bincount(inverse, weights=sign) != 0):
        raise ValueError('重建面绕序不一致')
    # 每个顶点的 incident faces 必须只有一个连通扇；仅检查边数会漏掉蝴蝶结顶点。
    corner_a = np.arange(faces.size)
    corner_b = corner_a//3*3+(corner_a % 3+1) % 3
    low = np.where(sign > 0, corner_a, corner_b)
    high = np.where(sign > 0, corner_b, corner_a)
    order = np.argsort(inverse)
    pairs = np.concatenate((low[order].reshape(-1, 2), high[order].reshape(-1, 2)))
    graph = csr_array((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(faces.size, faces.size))
    fans = connected_components(graph, directed=False, return_labels=False)
    if fans != len(vertices):
        raise ValueError('重建含非流形顶点或未引用顶点')
    graph = csr_array((np.ones(len(unique)), (unique[:, 0], unique[:, 1])), shape=(len(vertices), len(vertices)))
    components = int(connected_components(graph, directed=False, return_labels=False))
    return dict(components=components, boundary_edges=boundary, nonmanifold_edges=nonmanifold,
                nonmanifold_vertices=0, watertight=True, winding_consistent=True)


class _RayTree(tuple):
    """保持原有四元组接口；CUDA 数据随树失效，不缓存可变的模型数组。"""

    def __new__(cls, lower, upper, left, right):
        tree = super().__new__(cls, (lower, upper, left, right))
        tree.triangle_count = len(left) if right is None else left.triangle_count + right.triangle_count
        tree.device_data = None
        return tree

    def __getnewargs__(self):
        return tuple(self)

    def __getstate__(self):
        # 复制/序列化只保留 CPU 几何；设备缓存可重建，不能绑定到另一进程的 CUDA 上下文。
        return None


_ray_cuda_failed_devices = set()


@lru_cache(maxsize=1)
def _ray_cuda_backend():
    """可选 CuPy 后端，首次使用才加载；不要求 CPU 用户安装 CUDA。"""
    try:
        import cupy as cp
    except (ImportError, OSError):
        return None
    try:
        if not cp.cuda.runtime.getDeviceCount():
            return None
    except cp.cuda.runtime.CUDARuntimeError:
        return None
    # 禁止融合乘加和近似倒数，保留 NumPy float32 的运算顺序及交点容差。
    kernel = cp.RawKernel(r'''
    extern "C" __global__ void clear_rays(
        const float* boxes, const int* nodes, const float* triangles,
        const float* origins, const float* directions, const float* distances,
        unsigned char* visible, int count, int node_count, float eps, float tiny) {
        int ray = blockDim.x * blockIdx.x + threadIdx.x;
        if (ray >= count) return;
        const float* o = origins + 3*ray;
        const float* d = directions + 3*ray;
        float inv[3]; bool parallel[3];
        for (int axis=0; axis<3; ++axis) {
            parallel[axis] = fabsf(d[axis]) < tiny;
            inv[axis] = parallel[axis] ? 0.f : 1.f/d[axis];
        }
        visible[ray] = 1;
        int node = 0;
        while (node < node_count) {
            const float* box = boxes + 6*node;
            const int* info = nodes + 3*node;
            float enter = -__int_as_float(0x7f800000), leave = __int_as_float(0x7f800000);
            bool outside = false;
            for (int axis=0; axis<3; ++axis) {
                if (parallel[axis]) {
                    outside |= o[axis] < box[axis] || o[axis] > box[axis+3];
                } else {
                    float a = (box[axis]-o[axis])*inv[axis];
                    float b = (box[axis+3]-o[axis])*inv[axis];
                    enter = fmaxf(enter, fminf(a,b));
                    leave = fminf(leave, fmaxf(a,b));
                }
            }
            if (outside || leave < fmaxf(enter,eps) || enter >= distances[ray]) {
                node = info[2]; continue;
            }
            for (int t=info[0]; t<info[0]+info[1]; ++t) {
                const float* a = triangles + 11*t;
                const float* e = a+3; const float* f = a+6;
                float cx=d[1]*f[2]-d[2]*f[1], cy=d[2]*f[0]-d[0]*f[2], cz=d[0]*f[1]-d[1]*f[0];
                float det=(e[0]*cx+e[1]*cy)+e[2]*cz;
                if (fabsf(det) <= (tiny*a[9])*a[10]) continue;
                float inverse=1.f/det;
                float x=o[0]-a[0], y=o[1]-a[1], z=o[2]-a[2];
                float u=((x*cx+y*cy)+z*cz)*inverse;
                float qx=y*e[2]-z*e[1], qy=z*e[0]-x*e[2], qz=x*e[1]-y*e[0];
                float v=((d[0]*qx+d[1]*qy)+d[2]*qz)*inverse;
                float distance=((f[0]*qx+f[1]*qy)+f[2]*qz)*inverse;
                if (u>=0.f && v>=0.f && u+v<=1.f && distance>eps && distance<distances[ray]-eps) {
                    visible[ray]=0; return;
                }
            }
            ++node;
        }
    }
    ''', 'clear_rays', options=('--fmad=false', '--prec-div=true', '--prec-sqrt=true'))
    return cp, kernel


def _clear_rays_cuda(tree, origins, directions, distances, epsilon, backend):
    """每条射线由一个 GPU 线程遍历 BVH；跳转索引避免固定大小的线程栈。"""
    cp, kernel = backend
    device = cp.cuda.runtime.getDevice()
    saved = tree.device_data
    if saved is None or saved[0] != device:
        boxes, nodes, leaves = [], [], []
        count = 0

        def pack(node):
            nonlocal count
            lower, upper, left, right = node
            index = len(nodes)
            boxes.append((lower, upper))
            nodes.append([0, 0, 0])
            if right is None:
                leaves.append(left)
                nodes[index][:2] = count, len(left)
                count += len(left)
            else:
                pack(left)
                pack(right)
            nodes[index][2] = len(nodes)

        pack(tree)
        triangles = np.concatenate(leaves)
        a = triangles[:, 0]
        e, f = triangles[:, 1]-a, triangles[:, 2]-a
        triangles = np.column_stack((a, e, f, np.linalg.norm(e, axis=1), np.linalg.norm(f, axis=1)))
        saved = (device, cp.asarray(np.asarray(boxes, dtype=np.float32)),
                 cp.asarray(np.asarray(nodes, dtype=np.int32)),
                 cp.asarray(triangles.astype(np.float32, copy=False)))
        tree.device_data = saved
    _, boxes, nodes, triangles = saved
    count = len(origins)
    visible = cp.empty(count, dtype=cp.uint8)
    arrays = tuple(cp.asarray(np.ascontiguousarray(a)) for a in (origins, directions, distances))
    kernel(((count+127)//128,), (128,), (boxes, nodes, triangles, *arrays, visible,
           np.int32(count), np.int32(len(nodes)), np.float32(epsilon), np.float32(config.NUMERICAL_EPSILON)))
    return cp.asnumpy(visible).view(np.bool_)


def _triangle_tree(triangles):
    """临时 BVH；每个叶子只保存少量三角形，用于本次求解的射线遮挡判断。"""
    if not len(triangles):
        return None
    lower = triangles.min(axis=(0, 1))
    upper = triangles.max(axis=(0, 1))
    if len(triangles) <= config.RAY_LEAF_TRIANGLES:
        return _RayTree(lower, upper, triangles, None)
    centers = triangles.mean(axis=1)
    axis = int(np.argmax(upper - lower))
    split = len(triangles) // 2
    order = np.argpartition(centers[:, axis], split)
    return _RayTree(lower, upper, _triangle_tree(triangles[order[:split]]), _triangle_tree(triangles[order[split:]]))


def _terrain_forest(trees):
    """组合可复用的 Maplet BVH；叶节点仍使用相同的精确三角形射线检测。"""
    if not trees:
        return None
    if len(trees) == 1:
        return trees[0]
    lower = np.stack([tree[0] for tree in trees])
    upper = np.stack([tree[1] for tree in trees])
    centers = (lower + upper) * np.float32(0.5)
    axis = int(np.argmax(np.ptp(centers, axis=0)))
    split = len(trees) // 2
    order = np.argpartition(centers[:, axis], split)
    return _RayTree(lower.min(axis=0), upper.max(axis=0),
            _terrain_forest([trees[i] for i in order[:split]]),
            _terrain_forest([trees[i] for i in order[split:]]))


def _clear_rays(tree, origins, directions, distances, epsilon):
    """有限线段/太阳射线遮挡；SPC_RAY_BACKEND=auto/cpu/cuda 控制可选 GPU。

    默认只对至少 32 条 float32 射线和 256 个三角面启用 GPU；小任务仍走 NumPy。
    auto 在 CUDA 不可用时回退，cuda 在后端缺失或执行失败时报错，便于部署诊断。
    """
    count = len(origins)
    visible = np.ones(count, dtype=np.bool_)
    if tree is None or count == 0:
        return visible
    mode = os.environ.get('SPC_RAY_BACKEND', 'auto').lower()
    if mode not in ('auto', 'cpu', 'cuda'):
        raise ValueError('SPC_RAY_BACKEND 必须是 auto、cpu 或 cuda')
    if (mode != 'cpu' and isinstance(tree, _RayTree) and tree[0].dtype == np.float32
            and all(a.dtype == np.float32 for a in (origins, directions, distances))
            and (mode == 'cuda' or (count >= 32 and tree.triangle_count >= 256))):
        backend = _ray_cuda_backend()
        if backend is not None:
            device = backend[0].cuda.runtime.getDevice()
            try:
                if mode == 'cuda' or device not in _ray_cuda_failed_devices:
                    return _clear_rays_cuda(tree, origins, directions, distances, epsilon, backend)
            except (RuntimeError, MemoryError, OSError, backend[0].cuda.compiler.CompileException) as error:
                if mode == 'cuda':
                    raise
                _ray_cuda_failed_devices.add(device)
                tree.device_data = None
                warnings.warn(f'CUDA 射线检测失败，使用 CPU：{error}', RuntimeWarning, stacklevel=2)
        elif mode == 'cuda':
            raise RuntimeError('SPC_RAY_BACKEND=cuda 需要可用的 CuPy/CUDA')
    parallel_all = np.abs(directions) < config.NUMERICAL_EPSILON
    inverse_all = np.divide(1, directions, out=np.zeros_like(directions), where=~parallel_all)
    stack = [(tree, np.arange(count))]
    while stack:
        node, ids = stack.pop()
        ids = ids[visible[ids]]
        if not len(ids):
            continue
        lower, upper, left, right = node
        origin = origins[ids]
        parallel, inverse = parallel_all[ids], inverse_all[ids]
        t0, t1 = (lower - origin) * inverse, (upper - origin) * inverse
        enter = np.where(parallel, -np.inf, np.minimum(t0, t1)).max(axis=1)
        leave = np.where(parallel, np.inf, np.maximum(t0, t1)).min(axis=1)
        outside = (parallel & ((origin < lower) | (origin > upper))).any(axis=1)
        hit = ~outside & (leave >= np.maximum(enter, epsilon)) & (enter < distances[ids])
        ids = ids[hit]
        if not len(ids):
            continue
        if right is not None:
            stack.extend(((left, ids), (right, ids)))
            continue
        triangles = left
        a, e1, e2 = triangles[:, 0], triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
        determinant_floor = config.NUMERICAL_EPSILON * np.linalg.norm(e1, axis=1) * np.linalg.norm(e2, axis=1)
        for start in range(0, len(ids), config.RAY_BATCH_SIZE):
            batch = ids[start:start + config.RAY_BATCH_SIZE]
            direction = directions[batch, None]
            cross = np.cross(direction, e2)
            det = np.sum(e1 * cross, axis=-1)
            inverse = np.divide(1, det, out=np.zeros_like(det), where=np.abs(det) > determinant_floor)
            offset = origins[batch, None] - a
            u = np.sum(offset * cross, axis=-1) * inverse
            other = np.cross(offset, e1)
            v = np.sum(direction * other, axis=-1) * inverse
            distance = np.sum(e2 * other, axis=-1) * inverse
            blocked = ((np.abs(det) > determinant_floor) & (u >= 0) & (v >= 0) &
                       (u + v <= 1) & (distance > epsilon) &
                       (distance < distances[batch, None] - epsilon))
            visible[batch] &= ~blocked.any(axis=1)
    return visible


@dataclass(slots=True)
class _ObjSurfaceIndex:
    """仅在导入期间使用：原始面编号、焊接顶点编号与 SciPy 重心空间索引。"""
    triangles: np.ndarray
    normals: np.ndarray
    vertex_ids: np.ndarray
    centers: cKDTree
    max_radius: np.float32


def _obj_patch_faces(index, origin, basis, half, depth, seed_face):
    """原生空间查询和稀疏图连通分析，返回局部柱体内与种子面连通的原始面编号。"""
    radius = np.sqrt(2*half*half+depth*depth)+index.max_radius
    radius = np.nextafter(np.float32(radius), np.float32(np.inf))
    ids = np.asarray(index.centers.query_ball_point(origin, radius, return_sorted=True), dtype=np.int32)
    local = (index.triangles[ids]-origin) @ basis
    limits = np.array([half, half, depth], dtype=np.float32)
    selected = (local.min(axis=1) <= limits).all(axis=1) & (local.max(axis=1) >= -limits).all(axis=1)
    selected &= index.normals[ids] @ basis[:, 2] >= config.OBJ_MIN_NORMAL_COSINE
    ids = ids[selected]
    seeds = np.flatnonzero(ids == seed_face)
    if not len(seeds):
        return np.empty(0, dtype=np.int32)
    # 面与顶点组成二部图。不显式生成所有两两相邻面，避免高阶顶点产生平方数量的边。
    vertices, inverse = np.unique(index.vertex_ids[ids], return_inverse=True)
    count = len(ids)
    rows = np.repeat(np.arange(count, dtype=np.int32), 3)
    cols = inverse.ravel().astype(np.int32)+count
    graph = csr_array((np.ones(len(rows), dtype=np.uint8), (rows, cols)),
                      shape=(count+len(vertices), count+len(vertices)))
    _, labels = connected_components(graph, directed=False)
    return ids[labels[:count] == labels[seeds[0]]]


def _obj_project_heights(triangles, xy, depth):
    """用二维空间索引筛选可能相交的点面组合，再批量求交；不展开 点数×面数 矩阵。"""
    height = np.zeros(len(xy), dtype=np.float32)
    best = np.full(len(xy), np.inf, dtype=np.float32)
    if not len(xy):
        return height, np.zeros(0, dtype=np.bool_)
    if len(xy) > config.OBJ_QUERY_PAIR_BUDGET:
        valid = np.empty(len(xy), dtype=np.bool_)
        for start in range(0, len(xy), config.OBJ_QUERY_PAIR_BUDGET):
            stop = start+config.OBJ_QUERY_PAIR_BUDGET
            height[start:stop], valid[start:stop] = _obj_project_heights(triangles, xy[start:stop], depth)
        return height, valid
    point_tree = cKDTree(xy)
    epsilon = config.NUMERICAL_EPSILON
    # 大面或重复面可能包围所有查询点；即使最坏情况也限制一批候选配对的数量。
    batch_size = min(config.OBJ_QUERY_BATCH, max(1, config.OBJ_QUERY_PAIR_BUDGET//len(xy)))
    for start in range(0, len(triangles), batch_size):
        batch = triangles[start:start+batch_size]
        centers = batch[..., :2].mean(axis=1)
        radii = np.linalg.norm(batch[..., :2]-centers[:, None], axis=-1).max(axis=1)
        # 包围圆略扩展，包含 float32 舍入及重心坐标的边界容差。
        radii += epsilon*(4*radii+np.max(np.abs(batch[..., :2]), axis=(1, 2)))
        hits = point_tree.query_ball_point(centers, radii, return_sorted=False)
        sizes = np.fromiter(map(len, hits), dtype=np.int64, count=len(hits))
        if not sizes.any():
            continue
        face_ids = np.repeat(np.arange(len(batch)), sizes)
        point_ids = np.concatenate([hit for hit in hits if hit]).astype(np.int64, copy=False)
        a = batch[face_ids, 0]
        b, c = batch[face_ids, 1]-a, batch[face_ids, 2]-a
        determinant = b[:, 0]*c[:, 1]-b[:, 1]*c[:, 0]
        inverse = np.divide(1, determinant, out=np.zeros_like(determinant), where=determinant != 0)
        delta = xy[point_ids]-a[:, :2]
        u = (delta[:, 0]*c[:, 1]-delta[:, 1]*c[:, 0])*inverse
        v = (b[:, 0]*delta[:, 1]-b[:, 1]*delta[:, 0])*inverse
        z = a[:, 2]+u*b[:, 2]+v*c[:, 2]
        hit = (determinant != 0) & (u >= -epsilon) & (v >= -epsilon) & (u+v <= 1+epsilon) & (np.abs(z) <= depth)
        distance = np.where(hit, np.abs(z), np.inf)
        local_best = np.full(len(xy), np.inf, dtype=np.float32)
        np.minimum.at(local_best, point_ids, distance)
        eligible = np.isfinite(distance) & (distance == local_best[point_ids])
        winners = np.full(len(xy), len(point_ids), dtype=np.int64)
        # 相同距离时取排在前面的三角面，与顺序求交的 tie-break 保持一致。
        np.minimum.at(winners, point_ids[eligible], np.flatnonzero(eligible))
        closer = local_best < best
        height[closer] = z[winners[closer]]
        best[closer] = local_best[closer]
    return height, np.isfinite(best)


def _fit_slopes(samples, height, albedo, spacing):
    """逐点鲁棒 Gauss-Newton，解 p、q 及可选的 log(albedo)。

    只累积小型正规方程；已知反照率时为 2×2，否则为 3×3。
    信息矩阵特征值用于判断观测可辨识性，不是输入数据合法性校验。
    """
    q, p = np.gradient(height, spacing)
    rho = np.maximum(albedo.copy(), config.NUMERICAL_EPSILON)
    shape = height.shape
    variables = 3 if config.FIT_ALBEDO else 2
    def equations(p, q, rho):
        """累积各照片的鲁棒正规方程、代价、有效观测数和线搜索权重。"""
        matrix = np.zeros(shape + (variables, variables), dtype=np.float32)
        rhs = np.zeros(shape + (variables,), dtype=np.float32)
        cost = np.zeros(shape, dtype=np.float32)
        counts = np.zeros(shape, dtype=np.int32)
        weights = []
        for observed, mask, view, sun in samples:
            f, fp, fq, ci, ce = _reflectance(p, q, sun, view)
            valid = mask & (ci > config.MIN_ILLUMINATION_COSINE) & (ce > config.MIN_ILLUMINATION_COSINE)
            residual = observed - rho*f
            weight = valid.astype(np.float32) * np.minimum(
                1, config.HUBER_SIGMA * config.PHOTOMETRIC_NOISE / np.maximum(np.abs(residual), config.NUMERICAL_EPSILON))
            jacobian = rho[..., None] * np.stack((fp, fq, f) if config.FIT_ALBEDO else (fp, fq), axis=-1)
            matrix += weight[..., None, None] * jacobian[..., :, None] * jacobian[..., None, :]
            rhs += weight[..., None] * jacobian * residual[..., None]
            cost += weight * residual * residual
            counts += valid
            weights.append(weight)
        return matrix, rhs, cost, counts, weights

    for _ in range(config.PHOTOMETRIC_ITERATIONS):
        matrix, rhs, cost, counts, weights = equations(p, q, rho)
        spectrum = np.linalg.eigvalsh(matrix)
        ratio = spectrum[..., 0] / np.maximum(spectrum[..., -1], config.NUMERICAL_EPSILON)
        active = (counts >= config.MIN_PHOTOMETRIC_IMAGES) & (ratio > config.MIN_INFORMATION_RATIO)
        if not active.any():
            break
        damping = config.PHOTOMETRIC_DAMPING * np.maximum(np.trace(matrix, axis1=-2, axis2=-1), config.NUMERICAL_EPSILON)
        system = matrix + damping[..., None, None] * np.eye(variables, dtype=np.float32)
        delta = np.linalg.solve(system, rhs[..., None])[..., 0]
        delta[..., :2] = np.clip(delta[..., :2], -config.MAX_SLOPE_STEP, config.MAX_SLOPE_STEP)
        if config.FIT_ALBEDO:
            delta[..., 2] = np.clip(delta[..., 2], -config.MAX_LOG_ALBEDO_STEP, config.MAX_LOG_ALBEDO_STEP)
        pending = active.copy()
        for level in range(config.LINE_SEARCH_STEPS):
            scale = 0.5 ** level
            candidate_p = np.clip(p + scale*delta[..., 0], -config.MAX_SLOPE, config.MAX_SLOPE)
            candidate_q = np.clip(q + scale*delta[..., 1], -config.MAX_SLOPE, config.MAX_SLOPE)
            candidate_rho = rho * np.exp(scale*delta[..., 2]) if config.FIT_ALBEDO else rho
            candidate_cost = np.zeros(shape, dtype=np.float32)
            for sample, weight in zip(samples, weights):
                observed, _, view, sun = sample
                f, _, _, ci, ce = _reflectance(candidate_p, candidate_q, sun, view, derivatives=False)
                candidate_cost += weight * (observed - candidate_rho*f)**2
                candidate_cost = np.where((weight > 0) & ((ci <= 0) | (ce <= 0)), np.inf, candidate_cost)
            accept = pending & (candidate_cost <= cost)
            p[accept], q[accept], rho[accept] = candidate_p[accept], candidate_q[accept], candidate_rho[accept]
            pending &= ~accept
            if not pending.any():
                break
    matrix, _, cost, counts, _ = equations(p, q, rho)
    spectrum = np.linalg.eigvalsh(matrix)
    ratio = np.maximum(spectrum[..., 0], 0) / np.maximum(spectrum[..., -1], config.NUMERICAL_EPSILON)
    active = (counts >= config.MIN_PHOTOMETRIC_IMAGES) & (ratio > config.MIN_INFORMATION_RATIO)
    rms = np.sqrt(cost / np.maximum(counts, 1).astype(np.float32))
    quality = (np.minimum(counts / np.float32(config.CONFIDENCE_IMAGE_COUNT), 1) *
               np.minimum(ratio / config.CONFIDENCE_INFORMATION_RATIO, 1) *
               np.exp(-(rms / config.PHOTOMETRIC_NOISE)**2))
    return p, q, rho, quality.astype(np.float32), active, counts, rms


def _integrate_slopes(prior, p, q, weights, spacing, anchor_weight, anchor_height):
    """加权坡度积分，解稀疏 Poisson 正规方程；矩阵不显式组装。

    差分严格使用亮度计算的 np.gradient 模板，避免积分后法向与拟合值不一致。
    Jacobi 预条件共轭梯度仅使用 float32 网格数组。
    """
    ids = np.arange(prior.size).reshape(prior.shape)
    left = np.concatenate((ids[:, :1], ids[:, :-2], ids[:, -2:-1]), axis=1).ravel()
    right = np.concatenate((ids[:, 1:2], ids[:, 2:], ids[:, -1:]), axis=1).ravel()
    top = np.concatenate((ids[:1], ids[:-2], ids[-2:-1]), axis=0).ravel()
    bottom = np.concatenate((ids[1:2], ids[2:], ids[-1:]), axis=0).ravel()
    cx = np.full(prior.shape, 0.5, dtype=np.float32)
    cy = cx.copy()
    cx[:, [0, -1]] = 1
    cy[[0, -1], :] = 1
    a, b = np.concatenate((left, top)), np.concatenate((right, bottom))
    coefficient = np.concatenate((cx.ravel(), cy.ravel()))
    weight = np.tile(weights.ravel(), 2)
    target = np.concatenate((p.ravel(), q.ravel()))*spacing

    def transpose(value):
        """差分算子的转置：将坡度残差累加回相邻高程节点。"""
        result = np.zeros(prior.size, dtype=np.float32)
        np.add.at(result, a, -coefficient*value)
        np.add.at(result, b, coefficient*value)
        return result.reshape(prior.shape)

    diagonal = anchor_weight.copy()
    np.add.at(diagonal.ravel(), a, weight*coefficient**2)
    np.add.at(diagonal.ravel(), b, weight*coefficient**2)
    rhs = anchor_weight*anchor_height + transpose(weight*target)

    def multiply(value):
        """计算正规方程矩阵与向量的乘积，不分配完整矩阵。"""
        flat = value.ravel()
        return anchor_weight*value + transpose(weight*coefficient*(flat[b]-flat[a]))

    height = prior.copy()
    residual = rhs - multiply(height)
    direction = residual / diagonal
    product = np.sum(residual * direction)
    tolerance = config.INTEGRATION_TOLERANCE * max(np.linalg.norm(rhs), config.NUMERICAL_EPSILON)
    for _ in range(config.INTEGRATION_ITERATIONS):
        if np.linalg.norm(residual) <= tolerance:
            break
        applied = multiply(direction)
        denominator = np.sum(direction * applied)
        if denominator <= 0:
            break
        alpha = product / denominator
        height += alpha * direction
        residual -= alpha * applied
        preconditioned = residual / diagonal
        new_product = np.sum(residual * preconditioned)
        direction = preconditioned + (new_product / max(product, np.float32(1e-30))) * direction
        product = new_product
    return height


@dataclass(slots=True)
class SPCModel:
    """连续数组 SPC 模型，所有实体编号均为从零开始的整数行号。

    M=Maplet 数，S=总地形采样点数，I=影像数，P=总像素数，E=重叠边数，
    Q=重叠点对数。几何参数与密集采样统一为 float32；实体编号为
    int32；全局采样索引/偏移为 int64；掩码为 bool，不存 dtype=object 数组。

    origins[M,3] 对应网格中心，bases[M,3,3] 的列为 e_u/e_v/n。
    spacing[M] 为参考平面上相邻点间距(m)，parent_ids[M] 为父块或 -1。
    maplet_active[M] 标记参与求解/导出的叶块；拆分后父块归档，编号永不复用。
    split_levels[M] 为拆分层数，根块为 0；子块行列数不变，参考法向按局部坡面重估。
    spacing 按旋转后覆盖范围计算；平坦区域减半，倾斜区域按切平面尺寸调整。
    height/albedo/valid[S] 共用 maplet_offsets；初始 valid=False。
    confidence[S] 始终分配，初值为 0，update 更新为 [0,1] 工程评分。
    height_sigma/overlap_sigma 为可选米制误差，NaN 表示未估计；不由评分换算为方差。

    images/image_valid[P] 仅用于构造时导入已有打包像素，写盘后立即置为 None。
    不提供像素时只创建元数据和空清单项，不分配 P 大小的内存。
    model_dir 为实例目录，image_store 为其 images/ 子目录；image_view 按需读盘。
    X_camera=R@X_body+t；sun_directions[I,3] 为表面指向太阳的单位向量，
    整行 NaN 表示未知。distortion[I,14] 按 OpenCV 顺序补零，counts 为
    0/4/5/8/12/14；0 表示已去畸变。timestamps_utc 为 datetime64[ns] UTC。

    pose_covariance 是 [位置(m), 小角度(rad)] 的 (N,6,6) 数组，可缺省；
    影像的位置指本体系相机中心，旋转为相机系左扰动；
    Maplet 的位置指 origin，旋转为 basis 的本体系左扰动。整项 NaN 表示未知。

    maplet_image_offsets[M+1]/maplet_image_ids[L] 是到观测的 CSR。
    overlap_pairs[E,2] 保存无向边，overlap_offsets[E+1] 划分点对；
    overlap_sample_ids[Q,2] 是 height 缓冲中的全局扁平索引，分别属于边两端。
    overlap_weights[Q] 为相对权重；邻接 CSR 在构造时生成。

    vertices[V,3]/faces[F,3] 为可选派生网格，mesh_maplet_ids 记录来源；
    地形改变后需重新生成。optimization_state 是可选的低频检查点元数据，
    不参与逐点计算，布局由求解器定义。数值数组可能与输入共享内存。
    """
    # 地形：所有逐点属性使用相同的 maplet_offsets 定位。
    maplet_shapes: np.ndarray | None = None
    origins: np.ndarray | None = None
    bases: np.ndarray | None = None
    spacing: np.ndarray | None = None
    parent_ids: np.ndarray | None = None
    maplet_active: np.ndarray | None = None
    split_levels: np.ndarray | None = None
    height: np.ndarray | None = None
    height_prior: np.ndarray | None = None  # 已知反照率深度求解的持久先验；首次更新前捕获
    albedo: np.ndarray | None = None
    valid: np.ndarray | None = None
    height_sigma: np.ndarray | None = None
    overlap_sigma: np.ndarray | None = None
    confidence: np.ndarray | None = None
    observation_count: np.ndarray | None = None
    maplet_pose_covariance: np.ndarray | None = None

    # 相机表常驻内存；images/image_valid 只是构造时的可选导入缓冲。
    image_shapes: np.ndarray | None = None
    images: np.ndarray | None = None
    image_valid: np.ndarray | None = None
    K: np.ndarray | None = None
    R: np.ndarray | None = None
    t: np.ndarray | None = None
    sun_directions: np.ndarray | None = None
    distortion: np.ndarray | None = None
    distortion_counts: np.ndarray | None = None
    timestamps_utc: np.ndarray | None = None
    image_pose_covariance: np.ndarray | None = None
    model_dir: Path = field(init=False)
    image_store: Path = field(init=False)
    image_cache_bytes: int = field(default_factory=lambda: config.IMAGE_CACHE_BYTES)

    # Maplet 级照片关联和重叠约束；不保存逐高程点到照片的反向索引。
    maplet_image_offsets: np.ndarray | None = None
    maplet_image_ids: np.ndarray | None = None
    overlap_pairs: np.ndarray | None = None
    overlap_offsets: np.ndarray | None = None
    overlap_sample_ids: np.ndarray | None = None
    overlap_weights: np.ndarray | None = None

    vertices: np.ndarray | None = None
    faces: np.ndarray | None = None
    mesh_maplet_ids: np.ndarray | None = None
    frame: str = 'body_fixed'
    units: str = 'm'
    optimization_state: dict[str, object] | None = None

    maplet_offsets: np.ndarray = field(init=False, repr=False)
    image_offsets: np.ndarray = field(init=False, repr=False)
    neighbor_offsets: np.ndarray = field(init=False, repr=False)
    neighbor_ids: np.ndarray = field(init=False, repr=False)
    _shape_runs: np.ndarray = field(init=False, repr=False)
    _image_files: list[str | None] = field(init=False, default_factory=list, repr=False)
    _image_cache: OrderedDict = field(init=False, default_factory=OrderedDict, repr=False)
    _image_cache_used: int = field(init=False, default=0, repr=False)
    _terrain_cache: dict = field(init=False, default_factory=dict, repr=False)

    def __post_init__(self):
        """建立连续缓冲、只读结构索引和邻接 CSR，并初始化实例的磁盘照片仓库。"""
        self.image_cache_bytes = _nonnegative_int(self.image_cache_bytes, 'image_cache_bytes')
        # 只构造地形缓冲和相机表；照片像素不会分配为一个巨大的默认数组。
        self.maplet_shapes, self.maplet_offsets = _layout(self.maplet_shapes)
        self.image_shapes, self.image_offsets = _layout(self.image_shapes)
        maplet_count = len(self.maplet_shapes)
        image_count = len(self.image_shapes)
        sample_count = int(self.maplet_offsets[-1])
        for name, shape, dtype, fill in (
            ('origins', (maplet_count, 3), np.float32, 0),
            ('spacing', (maplet_count,), np.float32, config.DEFAULT_SPACING),
            ('parent_ids', (maplet_count,), np.int32, -1),
            ('maplet_active', (maplet_count,), np.bool_, True),
            ('split_levels', (maplet_count,), np.int32, 0),
            ('height', (sample_count,), np.float32, 0),
            ('albedo', (sample_count,), np.float32, config.DEFAULT_ALBEDO),
            ('valid', (sample_count,), np.bool_, False),
            ('confidence', (sample_count,), np.float32, 0),
            ('observation_count', (sample_count,), np.int32, 0),
            ('t', (image_count, 3), np.float32, 0),
            ('sun_directions', (image_count, 3), np.float32, np.nan),
            ('distortion_counts', (image_count,), np.uint8, 0),
        ):
            setattr(self, name, _array(getattr(self, name), shape, dtype, fill=fill,
                                      copy=name in ('parent_ids', 'maplet_active', 'split_levels')))
        for name, count in (('bases', maplet_count), ('K', image_count), ('R', image_count)):
            value = getattr(self, name)
            if value is None:
                value = np.broadcast_to(np.eye(3, dtype=np.float32), (count, 3, 3))
            setattr(self, name, _array(value, (count, 3, 3), np.float32))
        for name, shape, dtype in (
            ('height_sigma', (sample_count,), np.float32),
            ('overlap_sigma', (sample_count,), np.float32),
            ('height_prior', (sample_count,), np.float32),
            ('maplet_pose_covariance', (maplet_count, 6, 6), np.float32),
            ('image_pose_covariance', (image_count, 6, 6), np.float32),
            ('distortion', (image_count, 14), np.float32),
            ('timestamps_utc', (image_count,), 'datetime64[ns]'),
        ):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, _array(value, shape, dtype))
        for name, width, dtype in (
            ('maplet_image_ids', None, np.int32), ('overlap_pairs', 2, np.int32),
            ('overlap_sample_ids', 2, np.int64), ('vertices', 3, np.float32),
            ('faces', 3, np.int32), ('mesh_maplet_ids', None, np.int32),
        ):
            value = getattr(self, name)
            rows = 0 if value is None else len(value)
            shape = (rows,) if width is None else (rows, width)
            setattr(self, name, _array(value, shape, dtype, copy=name != 'vertices'))
        overlap_count = len(self.overlap_pairs)
        pair_count = len(self.overlap_sample_ids)
        self.maplet_image_offsets = _array(self.maplet_image_offsets, (maplet_count + 1,), np.int64, copy=True)
        self.overlap_offsets = _array(self.overlap_offsets, (overlap_count + 1,), np.int64, copy=True)
        self.overlap_weights = _array(self.overlap_weights, (pair_count,), np.float32, fill=1)
        sources = np.concatenate((self.overlap_pairs[:, 0], self.overlap_pairs[:, 1]))
        targets = np.concatenate((self.overlap_pairs[:, 1], self.overlap_pairs[:, 0]))
        self.neighbor_ids = np.ascontiguousarray(targets[np.argsort(sources, kind='stable')])
        self.neighbor_offsets = np.empty(maplet_count + 1, dtype=np.int64)
        self.neighbor_offsets[0] = 0
        np.cumsum(np.bincount(sources, minlength=maplet_count), out=self.neighbor_offsets[1:])
        # 连续的同尺寸块作为一批，坐标转换可 reshape 后直接广播，免去逐点查表。
        boundaries = np.flatnonzero(np.any(self.maplet_shapes[1:] != self.maplet_shapes[:-1], axis=1)) + 1
        self._shape_runs = (np.concatenate(([0], boundaries, [maplet_count])).astype(np.int64)
                            if maplet_count else np.zeros(1, dtype=np.int64))
        for name in ('maplet_shapes', 'maplet_offsets', 'image_shapes', 'image_offsets',
                    'parent_ids', 'maplet_active', 'split_levels', 'maplet_image_offsets', 'maplet_image_ids', 'overlap_pairs',
                     'overlap_offsets', 'overlap_sample_ids', 'faces', 'mesh_maplet_ids',
                     'neighbor_offsets', 'neighbor_ids', '_shape_runs'):
            getattr(self, name).flags.writeable = False
        self._initialize_image_store()

    def _initialize_image_store(self):
        """创建实例独占目录；已有打包像素逐张导入，成功后释放输入引用。

        images/manifest.json 保存图像编号、尺寸及当前文件名。实例目录可用于
        存放调用方导出的 OBJ 或其他信息，但此处不自动保存模型其余状态。
        """
        self.model_dir = Path(config.MODEL_ROOT) / uuid4().hex
        self.model_dir.mkdir(parents=True, exist_ok=False)
        self.image_store = self.model_dir / 'images'
        self.image_store.mkdir()
        files = [None] * len(self.image_shapes)
        try:
            if self.images is not None:
                # 标量初值通过零步长视图广播；默认掩码逐张分配，避免额外的 P 大小缓冲。
                total = int(self.image_offsets[-1])
                pixels = np.broadcast_to(np.asarray(self.images, dtype=np.float32).reshape(-1), (total,))
                masks = None
                if self.image_valid is not None:
                    masks = np.broadcast_to(np.asarray(self.image_valid, dtype=np.bool_).reshape(-1), (total,))
                for k, shape in enumerate(self.image_shapes):
                    start, end = self.image_offsets[k:k + 2]
                    image = pixels[start:end].reshape(tuple(shape))
                    # 与原有构造输入约定一致：未提供有效掩码时默认均无效。
                    mask = np.zeros(tuple(shape), dtype=np.bool_) if masks is None else masks[start:end].reshape(tuple(shape))
                    files[k] = _write_image_file(self.image_store, k, image, mask)
            _write_image_manifest(self.image_store, self.image_shapes, files)
        except BaseException:
            # 仅清理本次创建的文件和空目录，不递归删除目录或修改其他实例。
            for name in files:
                if name is not None:
                    (self.image_store / name).unlink(missing_ok=True)
            self.image_store.rmdir()
            self.model_dir.rmdir()
            raise
        self._image_files = files
        self.images = self.image_valid = None

    def maplet_view(self, maplet_id, field_name='height'):
        """返回已分配逐点字段的二维共享视图，例如 height、valid、albedo、confidence。"""
        values = getattr(self, field_name)
        start, end = self.maplet_offsets[maplet_id:maplet_id + 2]
        return values[start:end].reshape(tuple(self.maplet_shapes[maplet_id]))

    def image_view(self, image_id, *, mask=False):
        """二维影像或掩码；磁盘模式按需加载，返回只读视图。"""
        return self._disk_image(image_id)[1 if mask else 0]

    def observation_ids(self, maplet_id):
        """O(1) 返回参与该 Maplet 更新的历史照片编号，只读 CSR 切片。"""
        start, end = self.maplet_image_offsets[maplet_id:maplet_id + 2]
        return self.maplet_image_ids[start:end]

    def _associate_image(self, maplet_ids, image_id):
        """按行尾追加照片关联，线性搬移原 CSR，不再展开全部行号并重新排序。"""
        if not len(maplet_ids):
            return
        added = np.bincount(np.asarray(maplet_ids, dtype=np.int32), minlength=len(self.maplet_shapes))
        shifts = np.r_[0, np.cumsum(added, dtype=np.int64)]
        offsets = self.maplet_image_offsets+shifts
        ids = np.full(int(offsets[-1]), image_id, dtype=np.int32)
        # 每个旧节点的行号不变，仅整体向后移动前面各行新增条目的数量。
        destinations = np.arange(len(self.maplet_image_ids), dtype=np.int64)
        destinations += np.repeat(shifts[:-1], np.diff(self.maplet_image_offsets))
        ids[destinations] = self.maplet_image_ids
        offsets.flags.writeable = ids.flags.writeable = False
        self.maplet_image_offsets, self.maplet_image_ids = offsets, ids

    @property
    def image_cache_used_bytes(self):
        """LRU 当前持有的像素和掩码字节数，不含外部视图及操作系统页面缓存。"""
        return self._image_cache_used

    def clear_image_cache(self):
        """释放模型对缓存数组的引用；调用方持有的视图仍有效。"""
        self._image_cache.clear()
        self._image_cache_used = 0

    def set_image_cache_limit(self, cache_bytes):
        """调整像素缓存预算，并立即淘汰超过新预算的最久未用条目。"""
        self.image_cache_bytes = _nonnegative_int(cache_bytes, 'cache_bytes')
        self._trim_image_cache()

    def _trim_image_cache(self, incoming=0):
        """加载前腾出 incoming 字节；OrderedDict 首项是最久未访问的照片。"""
        while self._image_cache and self._image_cache_used + incoming > self.image_cache_bytes:
            _, (image, mask) = self._image_cache.popitem(last=False)
            self._image_cache_used -= image.nbytes + mask.nbytes

    def _disk_image(self, k):
        """缓存命中直接复用；小图完整读入，大图映射；短文件由读取/reshape 报错。"""
        if k in self._image_cache:
            self._image_cache.move_to_end(k)
            return self._image_cache[k]
        name = self._image_files[k]
        if name is None:
            raise ValueError(f'影像 {k} 尚未写入磁盘，请先调用 set_image')
        path = self.image_store / name
        shape = tuple(self.image_shapes[k])
        count = int(self.image_offsets[k + 1] - self.image_offsets[k])
        pixel_bytes = count * np.dtype('<f4').itemsize
        size = pixel_bytes + count * np.dtype(np.bool_).itemsize
        if size > self.image_cache_bytes:
            # 不把整张大图装入 LRU；实际触及的文件页面由操作系统管理。
            return (np.memmap(path, dtype='<f4', mode='r', shape=shape),
                    np.memmap(path, dtype=np.bool_, mode='r', offset=pixel_bytes, shape=shape))
        self._trim_image_cache(size)
        with path.open('rb') as stream:
            image = np.fromfile(stream, dtype='<f4', count=count).reshape(shape)
            mask = np.fromfile(stream, dtype=np.bool_, count=count).reshape(shape)
        image.flags.writeable = mask.flags.writeable = False
        self._image_cache[k] = image, mask
        self._image_cache_used += size
        return image, mask

    def _image_input(self, image, mask, shape=None):
        """统一二维灰度和掩码布局；替换照片时沿用原有尺寸。"""
        raw = np.asarray(image, dtype=np.float32)
        ny, nx = raw.shape
        shape = (ny, nx) if shape is None else tuple(shape)
        pixels = _array(raw, shape, np.float32)
        valid = _array(mask, shape, np.bool_, fill=True)
        return pixels, valid

    def set_image(self, image_id, image, *, mask=None):
        """写入/替换一张照片；磁盘文件和清单完成后才切换，磁盘视图不可原地修改。"""
        k = image_id
        pixels, valid = self._image_input(image, mask, self.image_shapes[k])
        # 新版本先写完，再切换清单。旧文件保留，已返回的 memmap 仍指向原版本。
        files = self._image_files.copy()
        name = _write_image_file(self.image_store, k, pixels, valid)
        files[k] = name
        try:
            _write_image_manifest(self.image_store, self.image_shapes, files)
        except BaseException:
            (self.image_store / name).unlink(missing_ok=True)
            raise
        self._image_files = files
        cached = self._image_cache.pop(k, None)
        if cached is not None:
            self._image_cache_used -= sum(a.nbytes for a in cached)

    def append_image(self, image, *, K, R, t, mask=None, sun_direction=None,
                     distortion=None, timestamp_utc=None, pose_covariance=None):
        """追加照片及相机元数据，返回稳定的新编号；使用实例自带的磁盘仓库。

        只追加一张照片的像素文件，不重读旧像素；内存中的小型相机表会扩展。
        仅保存照片，不更新地形；需要重建时调用 update。仓库不会持久化这些相机参数。
        """
        pixels, valid = self._image_input(image, mask)
        distortion_row = None
        distortion_count = 0
        if distortion is not None:
            coefficients = np.asarray(distortion, dtype=np.float32)
            distortion_count = coefficients.size
            distortion_row = np.zeros((1, 14), dtype=np.float32)
            distortion_row[0, :distortion_count] = coefficients

        # 直接构造新增的一行相机数据，不创建临时 SPCModel 或扫描历史相机表。
        new_rows = {
            'K': np.asarray(K, dtype=np.float32).reshape(1, 3, 3),
            'R': np.asarray(R, dtype=np.float32).reshape(1, 3, 3),
            't': np.asarray(t, dtype=np.float32).reshape(1, 3),
            'sun_directions': (np.full((1, 3), np.nan, dtype=np.float32) if sun_direction is None else
                               np.asarray(sun_direction, dtype=np.float32).reshape(1, 3)),
            'distortion_counts': np.array([distortion_count], dtype=np.uint8),
            'distortion': distortion_row,
            'timestamps_utc': None if timestamp_utc is None else np.array([timestamp_utc], dtype='datetime64[ns]'),
            'image_pose_covariance': (None if pose_covariance is None else
                                      np.asarray(pose_covariance, dtype=np.float32).reshape(1, 6, 6)),
        }
        k = len(self.image_shapes)
        shapes = np.concatenate((self.image_shapes, np.asarray(pixels.shape, dtype=np.int32)[None]))
        offsets = np.append(self.image_offsets, self.image_offsets[-1] + pixels.size)
        metadata = {}
        # 可选属性首次出现时补齐历史空值；后续缺省行也使用相同哨兵。
        for field_name, new in new_rows.items():
            old = getattr(self, field_name)
            if old is None and new is None:
                metadata[field_name] = None
                continue
            if field_name == 'distortion':
                fill = 0
            elif field_name == 'timestamps_utc':
                fill = np.datetime64('NaT', 'ns')
            else:
                fill = np.nan
            if old is None:
                old = np.full((k,) + new.shape[1:], fill, dtype=new.dtype)
            if new is None:
                new = np.full((1,) + old.shape[1:], fill, dtype=old.dtype)
            metadata[field_name] = np.concatenate((old, new))
        shapes.flags.writeable = offsets.flags.writeable = False
        # 相机表暂存在局部变量中，只有照片及清单写入成功后才更新实例状态。
        name = _write_image_file(self.image_store, k, pixels, valid)
        files = self._image_files + [name]
        try:
            _write_image_manifest(self.image_store, shapes, files)
        except BaseException:
            (self.image_store / name).unlink(missing_ok=True)
            raise
        self.image_shapes, self.image_offsets, self._image_files = shapes, offsets, files
        for field_name, value in metadata.items():
            setattr(self, field_name, value)
        return k


    def _surface_points(self, maplet_id, height):
        """将指定高程试解投到本体系，不改写模型，供匹配和迭代使用。"""
        ny, nx = height.shape
        u = (np.arange(nx, dtype=np.float32) - (nx - 1)*0.5) * self.spacing[maplet_id]
        v = (np.arange(ny, dtype=np.float32) - (ny - 1)*0.5) * self.spacing[maplet_id]
        basis = self.bases[maplet_id]
        return (self.origins[maplet_id] + u[None, :, None]*basis[:, 0] +
                v[:, None, None]*basis[:, 1] + height[..., None]*basis[:, 2])

    def _terrain_tree(self, maplet_id=None, height=None):
        """复用未改变块的 BVH；逐块比较几何快照，支持公开数组的原地修改。"""
        pieces = []
        overlaps = set() if maplet_id is None else set(self.neighbors(maplet_id).tolist())
        target = None if maplet_id is None else np.concatenate((
            self.origins[maplet_id], self.bases[maplet_id].ravel(),
            self.maplet_shapes[maplet_id], [self.spacing[maplet_id]]))
        for k, shape in enumerate(self.maplet_shapes):
            if not self.maplet_active[k]:
                self._terrain_cache.pop(k, None)
                continue
            h = height if k == maplet_id else self.maplet_view(k)
            valid = self.maplet_view(k, 'valid').ravel()
            geometry = np.concatenate((self.origins[k], self.bases[k].ravel(), shape, [self.spacing[k]]))
            cached = self._terrain_cache.get(k)
            if (cached is not None and np.array_equal(cached[0], h)
                    and np.array_equal(cached[1], valid) and np.array_equal(cached[2], geometry)):
                triangles, base_tree, cropped = cached[3:]
            else:
                triangles = self._maplet_triangles(k, h)
                base_tree = _triangle_tree(triangles)
                cropped = {}
                self._terrain_cache[k] = (h.copy(), valid.copy(), geometry, triangles, base_tree, cropped)
            tree = base_tree
            if k in overlaps and len(triangles):
                saved = cropped.get(maplet_id)
                if saved is None or not np.array_equal(saved[0], target):
                    # 重叠块中完全落在试解块覆盖内的面不作为另一层遮挡物。
                    local = (triangles-self.origins[maplet_id]) @ self.bases[maplet_id]
                    half = (self.maplet_shapes[maplet_id, ::-1]-1).astype(np.float32)*self.spacing[maplet_id]*0.5
                    inside = (np.abs(local[..., :2]) <= half+config.NUMERICAL_EPSILON).all(axis=(1, 2))
                    saved = (target.copy(), _triangle_tree(triangles[~inside]))
                    cropped[maplet_id] = saved
                tree = saved[1]
            if tree is not None:
                pieces.append(tree)
        return _terrain_forest(pieces)

    def _maplet_triangles(self, k, height):
        """当前块的三角化规则与 OBJ 导出一致。"""
        points = self._surface_points(k, height).reshape(-1, 3)
        ny, nx = map(int, self.maplet_shapes[k])
        cells = np.arange((ny-1)*(nx-1))
        a = (cells // (nx-1))*nx + cells % (nx-1)
        b, c, d = a+1, a+nx, a+nx+1
        valid = self.maplet_view(k, 'valid').ravel()
        other = ~(valid[a] & valid[d])
        first = np.column_stack((a, b, np.where(other, c, d)))
        second = np.column_stack((np.where(other, b, a), d, c))
        faces = np.concatenate((first, second))
        return points[faces[valid[faces].all(axis=1)]]

    def _image_gsd(self, maplet_id, image_id):
        """由中心处的透视投影 Jacobian 估计较差方向的米/像素，含距离与斜视影响。"""
        k = maplet_id
        h = self.maplet_view(k)
        center_index = (h.shape[0]//2, h.shape[1]//2)
        valid = self.maplet_view(k, 'valid')
        center_height = h[center_index] if valid[center_index] else h[valid].mean()
        center = self.origins[k] + center_height*self.bases[k, :, 2]
        camera = self.R[image_id] @ center + self.t[image_id]
        if camera[2] <= config.NUMERICAL_EPSILON:
            return np.float32(np.inf)
        projected = self.K[image_id] @ camera
        axes = self.K[image_id] @ self.R[image_id] @ self.bases[k, :, :2]
        jacobian = (axes[:2]*projected[2] - projected[:2, None]*axes[2]) / projected[2]**2
        scale = np.linalg.svd(jacobian, compute_uv=False)[-1]
        return np.float32(1 / max(scale, config.NUMERICAL_EPSILON))

    def _image_gsds(self, k, image_ids):
        """批量计算同一块在历史照片中的 GSD，避免逐照片重复求中心和调用 SVD。"""
        h = self.maplet_view(k)
        middle = (h.shape[0]//2, h.shape[1]//2)
        valid = self.maplet_view(k, 'valid')
        center_height = h[middle] if valid[middle] else h[valid].mean()
        center = self.origins[k]+center_height*self.bases[k, :, 2]
        R, K = self.R[image_ids], self.K[image_ids]
        camera = R @ center+self.t[image_ids]
        in_front = camera[:, 2] > config.NUMERICAL_EPSILON
        projected = (K @ camera[..., None])[..., 0]
        axes = K @ R @ self.bases[k, :, :2]
        depth = np.where(in_front, projected[:, 2], 1)
        jacobian = (axes[:, :2]*depth[:, None, None]-projected[:, :2, None]*axes[:, 2, None, :])/depth[:, None, None]**2
        scale = np.linalg.svd(jacobian, compute_uv=False)[:, -1]
        return np.where(in_front, 1/np.maximum(scale, config.NUMERICAL_EPSILON), np.inf).astype(np.float32)

    def _sampling_geometry(self, k, height):
        """同一候选高程的点位、法向和差分掩码只算一次；不跨求解缓存可变数组。"""
        points = self._surface_points(k, height)
        valid = self.maplet_view(k, 'valid')
        q, p = np.gradient(np.where(valid, height, 0), self.spacing[k])
        normal = np.stack((-p, -q, np.ones_like(p)), axis=-1) / np.sqrt(1+p*p+q*q)[..., None]
        padded = np.pad(valid, 1, mode='edge')
        usable = valid & padded[1:-1, :-2] & padded[1:-1, 2:] & padded[:-2, 1:-1] & padded[2:, 1:-1]
        return points, normal, usable

    def _sample_views(self, k, height, image_ids, tree=None):
        geometry = self._sampling_geometry(k, height)
        return [self._sample_maplet(k, height, i, tree, geometry=geometry) for i in image_ids]

    def _sample_maplet(self, maplet_id, height, image_id, tree=None, *, geometry=None):
        """投影、双线性取样，并用面朝向、相机射线和太阳射线筛选观测。"""
        k = maplet_id
        points, normal, terrain_valid = self._sampling_geometry(k, height) if geometry is None else geometry
        camera = points @ self.R[image_id].T + self.t[image_id]
        projected = camera @ self.K[image_id].T
        depth = projected[..., 2]
        denominator = np.where(depth > config.NUMERICAL_EPSILON, depth, 1)
        image, mask = self._disk_image(image_id)
        observed, usable = _bilinear(image, projected[..., 0]/denominator, projected[..., 1]/denominator, mask)
        usable &= terrain_valid & (depth > config.NUMERICAL_EPSILON) & (observed > 0)
        center = -self.R[image_id].T @ self.t[image_id]
        world_view = _unit(center - points)
        view = np.nan_to_num(world_view @ self.bases[k])
        sun = self.sun_directions[image_id] @ self.bases[k]
        # 可见性仅需两个余弦，不必计算反射率及其分母。
        ci = np.sum(normal * np.nan_to_num(sun), axis=-1)
        ce = np.sum(normal * view, axis=-1)
        usable &= ce > config.MIN_ILLUMINATION_COSINE
        known_sun = np.isfinite(sun).all()
        if known_sun:
            usable &= ci > config.MIN_ILLUMINATION_COSINE
        if tree is not None:
            indices = np.flatnonzero(usable)
            origin = points.reshape(-1, 3)[indices]
            directions = world_view.reshape(-1, 3)[indices]
            distances = np.linalg.norm(center - origin, axis=1)
            epsilon = np.float32(self.spacing[k] * config.RAY_OFFSET_SPACING)
            clear = _clear_rays(tree, origin, directions, distances, epsilon)
            if known_sun and config.CAST_SHADOWS:
                light = np.broadcast_to(self.sun_directions[image_id], origin.shape)
                clear &= _clear_rays(tree, origin, light, np.full(len(origin), np.inf, dtype=np.float32), epsilon)
            usable.ravel()[indices] &= clear
        return observed, usable, view, sun

    def _select_views(self, maplet_id):
        """从合格历史照片中优先选取视角/光照分散的组合，避免最近数帧几乎重合。"""
        candidates, geometries = [], []
        k = maplet_id
        for image_id in self.observation_ids(k)[::-1]:
            if self._image_files[image_id] is None or self.distortion_counts[image_id]:
                continue
            sun = self.sun_directions[image_id]
            if not np.isfinite(sun).all() or self._image_gsd(k, image_id) > config.MAX_IMAGE_GSD_RATIO*self.spacing[k]:
                continue
            center = -self.R[image_id].T @ self.t[image_id]
            view = _unit(center - self.origins[k])
            candidates.append(int(image_id))
            geometries.append(np.concatenate((view, sun)))
        if not candidates:
            return []
        geometry = np.asarray(geometries, dtype=np.float32)
        selected = [0]  # 保留最新观测，然后贪心选择离已选组合最远的几何。
        distance = np.full(len(candidates), np.inf, dtype=np.float32)
        while len(selected) < min(len(candidates), config.MAX_IMAGES_PER_MAPLET):
            delta = geometry-geometry[selected[-1]]
            distance = np.minimum(distance, np.sum(delta*delta, axis=1))
            distance[selected] = -1
            index = int(np.argmax(distance))
            if distance[index] <= 2*(1-config.GEOMETRY_DUPLICATE_COSINE):
                break
            selected.append(index)
        return [candidates[index] for index in selected]

    @staticmethod
    def _intersect_height_grid(height, valid, spacing, starts, direction):
        """沿给定方向与双线性高程面求交；坐标、射线参数均使用块局部物理单位。

        Newton 迭代使用双线性面的解析导数。最终只接受域内、有效且正面相交的点；
        不向父块外或孔洞内外推。返回射线参数、父网格列/行坐标和有效掩码。
        """
        ny, nx = height.shape
        distance = np.zeros(starts.shape[:-1], dtype=np.float32)
        tolerance = np.float32(config.SPLIT_REPROJECT_TOLERANCE*spacing)
        values = height[valid]
        if not values.size:
            return distance, distance.copy(), distance.copy(), np.zeros_like(distance, dtype=np.bool_)
        # 求交只可能发生在父块有效高程的包围盒内。限制 Newton 的射线区间，
        # 防止近切线在网格外反复外推，生成溢出的无效高度并污染邻接几何。
        half = np.array([(nx-1)*spacing/2, (ny-1)*spacing/2], dtype=np.float32)
        lower = np.r_[-half, values.min()]-tolerance
        upper = np.r_[half, values.max()]+tolerance
        parallel = np.abs(direction) <= config.NUMERICAL_EPSILON
        inverse = np.divide(1, direction, out=np.zeros_like(direction), where=~parallel)
        first, last = (lower-starts)*inverse, (upper-starts)*inverse
        enter = np.where(parallel, -np.inf, np.minimum(first, last)).max(axis=-1)
        leave = np.where(parallel, np.inf, np.maximum(first, last)).min(axis=-1)
        possible = (leave >= enter) & ~(parallel & ((starts < lower) | (starts > upper))).any(axis=-1)
        distance = np.where(possible, np.clip(distance, enter, leave), 0)
        for _ in range(config.SPLIT_REPROJECT_ITERATIONS):
            points = starts+distance[..., None]*direction
            u = points[..., 0]/spacing+np.float32((nx-1)/2)
            v = points[..., 1]/spacing+np.float32((ny-1)/2)
            x = np.clip(u, 0, nx-1)
            y = np.clip(v, 0, ny-1)
            ix = np.minimum(x.astype(np.int32), nx-2)
            iy = np.minimum(y.astype(np.int32), ny-2)
            dx, dy = x-ix.astype(np.float32), y-iy.astype(np.float32)
            a, b = height[iy, ix], height[iy, ix+1]
            c, d = height[iy+1, ix], height[iy+1, ix+1]
            # 无效节点不能污染整批射线；最终 mask 仍按实际插值权重检查孔洞。
            a, b, c, d = (np.nan_to_num(value) for value in (a, b, c, d))
            surface = (1-dy)*((1-dx)*a+dx*b)+dy*((1-dx)*c+dx*d)
            slope_u = ((1-dy)*(b-a)+dy*(d-c))/spacing
            slope_v = ((1-dx)*(c-a)+dx*(d-b))/spacing
            derivative = direction[2]-slope_u*direction[0]-slope_v*direction[1]
            step = np.divide(surface-points[..., 2], derivative, out=np.zeros_like(distance),
                             where=possible & (np.abs(derivative) > config.NUMERICAL_EPSILON))
            candidate = np.where(possible, np.clip(distance+step, enter, leave), 0)
            movement = np.max(np.abs(candidate-distance), initial=0)
            distance = candidate
            if movement <= tolerance:
                break
        points = starts+distance[..., None]*direction
        u = points[..., 0]/spacing+np.float32((nx-1)/2)
        v = points[..., 1]/spacing+np.float32((ny-1)/2)
        margin = config.SPLIT_REPROJECT_TOLERANCE
        inside = (u >= -margin) & (u <= nx-1+margin) & (v >= -margin) & (v <= ny-1+margin)
        u, v = np.clip(u, 0, nx-1), np.clip(v, 0, ny-1)
        surface, supported = _bilinear(height, u, v, valid)
        supported &= possible & inside & (np.abs(surface-points[..., 2]) <= tolerance)
        supported &= derivative > config.NUMERICAL_EPSILON
        return np.where(supported, distance, 0), u, v, supported

    def _split_child_grid(self, k, qy, qx):
        """拟合子区域坡面，建立右手正交基，并将父地形重投影到新规则网格。

        覆盖尺寸取旧子区域在新切平面上的包围盒，因此旋转后的实际间距不一定
        恰为父块的一半。子块可轻微重叠，父块之外和孔洞中的射线仍标记无效。
        """
        ny, nx = map(int, self.maplet_shapes[k])
        spacing = self.spacing[k]
        u, v = np.meshgrid(qx*np.float32((nx-1)/2)+np.arange(nx, dtype=np.float32)/2,
                           qy*np.float32((ny-1)/2)+np.arange(ny, dtype=np.float32)/2)
        height, supported = _bilinear(self.maplet_view(k), u, v, self.maplet_view(k, 'valid'))
        x, y = (u-np.float32((nx-1)/2))*spacing, (v-np.float32((ny-1)/2))*spacing
        center = np.array([x.mean(), y.mean(), 0], dtype=np.float32)
        rotation = np.eye(3, dtype=np.float32)
        if supported.sum() >= 3:
            design = np.column_stack((x[supported]-center[0], y[supported]-center[1],
                                      np.ones(int(supported.sum()), dtype=np.float32)))
            coefficients, _, rank, _ = np.linalg.lstsq(design, height[supported], rcond=None)
            if rank == 3:
                normal = _unit(np.array([-coefficients[0], -coefficients[1], 1], dtype=np.float32))
                tangent = _unit(np.array([1, 0, 0], dtype=np.float32)-normal[0]*normal)
                rotation = np.column_stack((tangent, np.cross(normal, tangent), normal))
                center[2] = coefficients[2]
        # 孔洞不参与拟合或包围盒统计；不足以定义坡面的区域保持父坐标轴。
        new_spacing = np.float32(spacing/2)
        if supported.any():
            cloud = np.stack((x, y, height), axis=-1)[supported]
            local = (cloud-center) @ rotation
            lower, upper = local[:, :2].min(axis=0), local[:, :2].max(axis=0)
            center += rotation[:, :2] @ ((lower+upper)/2)
            new_spacing = np.float32(max(new_spacing, (upper[0]-lower[0])/(nx-1),
                                        (upper[1]-lower[1])/(ny-1)))
        col, row = np.meshgrid((np.arange(nx, dtype=np.float32)-(nx-1)/2)*new_spacing,
                               (np.arange(ny, dtype=np.float32)-(ny-1)/2)*new_spacing)
        starts = center+col[..., None]*rotation[:, 0]+row[..., None]*rotation[:, 1]
        current, pu, pv, valid = self._intersect_height_grid(
            self.maplet_view(k), self.maplet_view(k, 'valid'), spacing, starts, rotation[:, 2])
        fields = dict(height=current, valid=valid)
        fields['albedo'] = _bilinear(self.maplet_view(k, 'albedo'), pu, pv, self.maplet_view(k, 'valid'))[0]
        if self.height_prior is not None:
            prior, _, _, prior_valid = self._intersect_height_grid(
                self.maplet_view(k, 'height_prior'), self.maplet_view(k, 'valid'), spacing, starts, rotation[:, 2])
            # 先验没有覆盖的射线冻结在当前形状，不将域外外推作为约束。
            fields['height_prior'] = np.where(prior_valid, prior, current)
        # 重参数化后的节点不等同于旧观测节点；置信度由后续照片重新建立。
        for name in ('confidence', 'observation_count', 'height_sigma', 'overlap_sigma'):
            source = getattr(self, name)
            if source is not None:
                fields[name] = np.full((ny, nx), np.nan if name.endswith('_sigma') else 0, dtype=source.dtype)
        return self.origins[k]+self.bases[k] @ center, self.bases[k] @ rotation, new_spacing, fields

    def _split_maplets(self, parent_ids):
        """把选中的活动叶块四等分，一次批量追加所有子块缓冲。

        子块保持父块行列数，重估局部参考法向并重新采样；父块归档，旧编号不移动。
        新节点的置信度/计数清零；可选误差置 NaN，照片候选视图由父块继承。
        仍然重合的节点保留显式对应，其余重叠区通过射线插值建立高程约束。
        """
        parents = [int(k) for k in dict.fromkeys(parent_ids) if self.maplet_active[k]]
        if not parents:
            return {}
        old_offsets = self.maplet_offsets
        old_count = len(self.maplet_shapes)
        children = {k: list(range(old_count+4*i, old_count+4*i+4)) for i, k in enumerate(parents)}
        owners = np.repeat(np.asarray(parents, dtype=np.int32), 4)
        quadrants = np.tile(np.array([[0, 0], [0, 1], [1, 0], [1, 1]], dtype=np.int32), (len(parents), 1))
        shapes, offsets = _layout(np.concatenate((self.maplet_shapes, self.maplet_shapes[owners])))
        fields = ('height', 'height_prior', 'albedo', 'valid', 'confidence',
                  'observation_count', 'height_sigma', 'overlap_sigma')
        buffers = {name: [getattr(self, name)] for name in fields if getattr(self, name) is not None}
        origins, bases, spacings = [], [], []
        for k, (qy, qx) in zip(owners, quadrants):
            origin, basis, step, fields = self._split_child_grid(k, qy, qx)
            origins.append(origin)
            bases.append(basis)
            spacings.append(step)
            for name, pieces in buffers.items():
                pieces.append(fields[name].ravel())
        origins = np.asarray(origins, dtype=np.float32)
        shift = origins-self.origins[owners]
        self.origins = np.concatenate((self.origins, origins))
        self.bases = np.concatenate((self.bases, np.asarray(bases, dtype=np.float32)))
        self.spacing = np.concatenate((self.spacing, np.asarray(spacings, dtype=np.float32)))
        self.parent_ids = np.concatenate((self.parent_ids, owners))
        self.split_levels = np.concatenate((self.split_levels, self.split_levels[owners]+1))
        active = np.concatenate((self.maplet_active, np.ones(len(owners), dtype=np.bool_)))
        active[parents] = False
        self.maplet_active = active
        if self.maplet_pose_covariance is not None:
            # 本体系平移/小转角协方差随子块中心的力臂变换。
            jacobian = np.broadcast_to(np.eye(6, dtype=np.float32), (len(owners), 6, 6)).copy()
            x, y, z = shift.T
            jacobian[:, 0, 4], jacobian[:, 0, 5] = z, -y
            jacobian[:, 1, 3], jacobian[:, 1, 5] = -z, x
            jacobian[:, 2, 3], jacobian[:, 2, 4] = y, -x
            covariance = jacobian @ self.maplet_pose_covariance[owners] @ jacobian.swapaxes(-1, -2)
            self.maplet_pose_covariance = np.concatenate((self.maplet_pose_covariance, covariance))
        image_rows = [self.observation_ids(k) for k in range(old_count)]
        image_rows.extend(self.observation_ids(k) for k in owners)
        self.maplet_image_ids = np.concatenate(image_rows)
        self.maplet_image_offsets = np.r_[0, np.cumsum([len(row) for row in image_rows], dtype=np.int64)]
        for name, pieces in buffers.items():
            setattr(self, name, np.concatenate(pieces))
        self.maplet_shapes, self.maplet_offsets = shapes, offsets
        self._split_overlaps(children, old_offsets)
        boundaries = np.flatnonzero(np.any(shapes[1:] != shapes[:-1], axis=1))+1
        self._shape_runs = np.r_[0, boundaries, len(shapes)].astype(np.int64)
        for name in ('maplet_shapes', 'maplet_offsets', 'parent_ids', 'maplet_active', 'split_levels',
                     'maplet_image_ids', 'maplet_image_offsets', '_shape_runs'):
            getattr(self, name).flags.writeable = False
        self._invalidate_mesh()
        return children

    def _split_overlaps(self, children, old_offsets):
        """重建邻接与仍重合的对应点 CSR；无法精确转接的点由几何重叠约束替代。"""
        edges = {}

        def add(a, b, samples=(), weights=()):
            """规范无向边方向并收集对应点，最后统一打包为 CSR。"""
            if a > b:
                a, b = b, a
                samples = [(v, u) for u, v in samples]
            row = edges.setdefault((int(a), int(b)), ([], []))
            row[0].extend(samples)
            row[1].extend(weights)

        def locate(k, points):
            """只保留实际重合的节点；旋转后的近邻不能冒充同一个地形点。"""
            ny, nx = self.maplet_shapes[k]
            local = (points-self.origins[k]) @ self.bases[k]
            uv = local[..., :2]/self.spacing[k]+np.array([(nx-1)/2, (ny-1)/2], dtype=np.float32)
            col, row = np.rint(uv[..., 0]).astype(np.int64), np.rint(uv[..., 1]).astype(np.int64)
            inside = (col >= 0) & (col < nx) & (row >= 0) & (row < ny)
            indices = np.clip(row, 0, ny-1)*nx+np.clip(col, 0, nx-1)
            target = self._surface_points(k, self.maplet_view(k)).reshape(-1, 3)[indices]
            matched = inside & self.maplet_view(k, 'valid').ravel()[indices]
            matched &= np.linalg.norm(target-points, axis=-1) <= self.spacing[k]*config.SPLIT_REPROJECT_TOLERANCE
            return indices+self.maplet_offsets[k], matched

        def endpoints(k, sample):
            """将旧对应点映射到子块中仍与其实际重合的节点；未拆分端保持编号。"""
            if k not in children:
                return [(k, int(sample))]
            point = self._surface_points(k, self.maplet_view(k)).reshape(-1, 3)[int(sample-old_offsets[k])]
            result = []
            if np.isfinite(point).all():
                for child in children[k]:
                    index, matched = locate(child, point[None])
                    if matched[0]:
                        result.append((child, int(index[0])))
            return result

        def intersects(a, b):
            """用双向投影包围盒剔除已声明相邻、但拆分后不再相交的子区域。"""
            # 原有邻接已声明是同一表面；投影包围盒仅用于剔除不相交的子区域。
            for first, second in ((a, b), (b, a)):
                valid = self.maplet_view(second, 'valid')
                if not valid.any():
                    return False
                points = self._surface_points(second, self.maplet_view(second))[valid]
                uv = (points-self.origins[first]) @ self.bases[first, :, :2]
                half = (self.maplet_shapes[first, ::-1]-1)*self.spacing[first]/2
                tolerance = self.spacing[first]*config.NUMERICAL_EPSILON
                if np.any(uv.min(axis=0) > half+tolerance) or np.any(uv.max(axis=0) < -half-tolerance):
                    return False
            return True

        for edge, (a, b) in enumerate(self.overlap_pairs):
            for ca in children.get(int(a), [int(a)]):
                for cb in children.get(int(b), [int(b)]):
                    if (a not in children and b not in children) or intersects(ca, cb):
                        add(ca, cb)
            start, end = self.overlap_offsets[edge:edge+2]
            for (sa, sb), weight in zip(self.overlap_sample_ids[start:end], self.overlap_weights[start:end]):
                left, right = endpoints(int(a), sa), endpoints(int(b), sb)
                if not left or not right:
                    continue
                divided = np.float32(weight/(len(left)*len(right)))
                for ca, ia in left:
                    for cb, ib in right:
                        add(ca, cb, [(ia, ib)], [divided])

        for ids in children.values():
            for a in range(4):
                k = ids[a]
                points = self._surface_points(k, self.maplet_view(k)).reshape(-1, 3)
                source = np.flatnonzero(self.maplet_view(k, 'valid'))
                for b in range(a+1, 4):
                    target, matched = locate(ids[b], points[source])
                    pairs = np.column_stack((source[matched]+self.maplet_offsets[k], target[matched]))
                    # 非对齐网格保留块邻接，通过 _height_anchors 的射线插值约束重叠区。
                    add(k, ids[b], pairs.tolist(), np.ones(len(pairs), dtype=np.float32))
        ordered = sorted(edges)
        self.overlap_pairs = np.asarray(ordered, dtype=np.int32).reshape(-1, 2)
        self.overlap_offsets = np.r_[0, np.cumsum([len(edges[key][0]) for key in ordered], dtype=np.int64)]
        self.overlap_sample_ids = np.asarray([pair for key in ordered for pair in edges[key][0]], dtype=np.int64).reshape(-1, 2)
        self.overlap_weights = np.asarray([weight for key in ordered for weight in edges[key][1]], dtype=np.float32)
        sources = np.concatenate((self.overlap_pairs[:, 0], self.overlap_pairs[:, 1]))
        targets = np.concatenate((self.overlap_pairs[:, 1], self.overlap_pairs[:, 0]))
        self.neighbor_ids = targets[np.argsort(sources, kind='stable')]
        self.neighbor_offsets = np.r_[0, np.cumsum(np.bincount(sources, minlength=len(self.maplet_shapes)), dtype=np.int64)]
        for name in ('overlap_pairs', 'overlap_offsets', 'overlap_sample_ids', 'neighbor_ids', 'neighbor_offsets'):
            getattr(self, name).flags.writeable = False

    def _invalidate_mesh(self):
        """高程或网格布局改变后，丢弃已经过期的派生全局网格。"""
        self.vertices = np.empty((0, 3), dtype=np.float32)
        self.faces = np.empty((0, 3), dtype=np.int32)
        self.mesh_maplet_ids = np.empty(0, dtype=np.int32)
        self.faces.flags.writeable = self.mesh_maplet_ids.flags.writeable = False

    def _stereo_anchor(self, maplet_id, height, image_ids, samples):
        """多视角纹理匹配估计整块法向高度偏移；无纹理/无基线/边界峰不接受。"""
        if len(image_ids) < 2:
            return np.float32(0), np.float32(0)
        k = maplet_id
        if not config.FIT_ALBEDO and np.std(self.maplet_view(k, 'albedo')[self.maplet_view(k, 'valid')]) < config.STEREO_MIN_TEXTURE:
            # 已知均匀反照率没有可匹配纹理；形状误差产生的明暗不能充当纹理。
            return np.float32(0), np.float32(0)
        reference_view = _unit(-self.R[image_ids[0]].T @ self.t[image_ids[0]] - self.origins[k])
        pairs = []
        for index, image_id in enumerate(image_ids[1:], 1):
            view = _unit(-self.R[image_id].T @ self.t[image_id] - self.origins[k])
            if np.dot(view, reference_view) < np.cos(np.deg2rad(config.STEREO_MIN_ANGLE_DEG)):
                pairs.append(index)
        if not pairs:
            return np.float32(0), np.float32(0)
        q, p = np.gradient(height, self.spacing[k])
        offsets = np.linspace(-config.STEREO_SEARCH_SPACING*self.spacing[k],
                              config.STEREO_SEARCH_SPACING*self.spacing[k],
                              config.STEREO_SEARCH_SAMPLES, dtype=np.float32)
        scores = np.full(len(offsets), -np.inf, dtype=np.float32)
        for index, offset in enumerate(offsets):
            projected = self._sample_views(k, height + offset, image_ids)
            corrected = []
            for sample, original in zip(projected, samples):
                values, mask, view, sun = sample
                f = _reflectance(p, q, sun, view, derivatives=False)[0]
                mask &= original[1] & (f > config.NUMERICAL_EPSILON)
                corrected.append((values / np.maximum(f, config.NUMERICAL_EPSILON), mask))
            correlations = []
            for other in pairs:
                a, mask_a = corrected[0]
                b, mask_b = corrected[other]
                valid = mask_a & mask_b
                if np.count_nonzero(valid) < config.STEREO_MIN_POINTS:
                    continue
                av, bv = a[valid], b[valid]
                av, bv = av-av.mean(), bv-bv.mean()
                if min(av.std(), bv.std()) < config.STEREO_MIN_TEXTURE:
                    continue
                correlations.append(np.sum(av*bv) / np.sqrt(np.sum(av*av)*np.sum(bv*bv)))
            if correlations:
                scores[index] = np.mean(correlations)
        best = int(np.argmax(scores))
        if best == 0 or best == len(scores)-1 or scores[best] < config.STEREO_MIN_CORRELATION:
            return np.float32(0), np.float32(0)
        left, peak, right = scores[best-1:best+2]
        curvature = 2*peak-left-right
        if not np.isfinite(curvature) or curvature < config.STEREO_MIN_PEAK_CURVATURE:
            return np.float32(0), np.float32(0)
        subpixel = np.clip(0.5*(right-left)/curvature, -1, 1)
        offset = offsets[best] + subpixel*(offsets[1]-offsets[0])
        quality = np.clip((peak-config.STEREO_MIN_CORRELATION)/(1-config.STEREO_MIN_CORRELATION), 0, 1)
        return np.float32(offset), np.float32(quality)

    def _fit_photometric_heights(self, maplet_id, height, albedo, image_ids, samples):
        """已知反照率的局部光度立体：搜索高程，将每个候选的单位法向作为隐变量。

        粗网格的差分法向并不等于像素处微地形法向。直接逼迫两者一致会扭曲
        已准确的粗形状。本方法只接受多视角支持、具有内部尖锐极小值的深度；
        无纹理平面/退化观测保持先验。原始 OBJ 不参与此求解。
        """
        k = maplet_id
        masks = np.stack([sample[1] for sample in samples])
        suns = np.stack([sample[3] for sample in samples])
        counts = masks.sum(axis=0)
        matrix = np.einsum('ihw,ij,ik->hwjk', masks.astype(np.float32), suns, suns)
        eigenvalues, vectors = np.linalg.eigh(matrix)
        informative = eigenvalues > config.MIN_INFORMATION_RATIO*np.maximum(eigenvalues[..., -1:], config.NUMERICAL_EPSILON)
        rank = informative.sum(axis=-1)
        inverse = np.divide(1, eigenvalues, out=np.zeros_like(eigenvalues), where=informative)
        pseudo = (vectors*inverse[..., None, :]) @ vectors.swapaxes(-1, -2)
        null = vectors[..., 0]
        q, p = np.gradient(height, self.spacing[k])
        prior_normal = _unit(np.stack((-p, -q, np.ones_like(p)), axis=-1))
        sign = np.where(np.sum(prior_normal*null, axis=-1) >= 0, 1, -1).astype(np.float32)
        noise_squared = np.float32(config.PHOTOMETRIC_NOISE**2)

        def fit(observations):
            """消去候选高程处的单位法向，计算可观测节点的跨视图光度误差。"""
            values = np.stack([sample[0] for sample in observations])
            usable = np.stack([sample[1] for sample in observations])
            intensity = values/np.maximum(albedo, config.NUMERICAL_EPSILON)
            rhs = np.einsum('ihw,ij->hwj', masks*intensity, suns)
            normal = np.einsum('hwjk,hwk->hwj', pseudo, rhs)
            missing = np.sqrt(np.maximum(1-np.sum(normal*normal, axis=-1), 0))*sign
            normal += np.where((rank == 2)[..., None], missing[..., None]*null, 0)
            normal = _unit(normal)
            prediction = albedo*np.einsum('hwj,ij->ihw', normal, suns)
            error = np.sum(np.where(masks, (values-prediction)**2, 0), axis=0)/np.maximum(counts, 1).astype(np.float32)
            supported = (counts >= config.MIN_DEPTH_IMAGES) & (rank >= 2) & ~np.any(masks & ~usable, axis=0)
            # 没有足够分散的光照时不能把伪逆给出的法向当作有效测量。
            supported &= eigenvalues[..., -2] > config.CONFIDENCE_INFORMATION_RATIO*np.maximum(eigenvalues[..., -1], config.NUMERICAL_EPSILON)
            return np.where(supported, error, np.inf).astype(np.float32)

        before = fit(samples)
        prior = self.maplet_view(k, 'height_prior')
        sigma = np.float32(self.spacing[k]*config.DEPTH_PRIOR_SPACING)
        prior_cost = noise_squared*((height-prior)/sigma)**2
        extent = np.float32(self.spacing[k]*config.DEPTH_SEARCH_SPACING)
        offsets = np.linspace(-extent, extent, config.DEPTH_SEARCH_SAMPLES, dtype=np.float32)
        costs = []
        for offset in offsets:
            observations = samples if offset == 0 else self._sample_views(k, height+offset, image_ids)
            costs.append(fit(observations)+noise_squared*((height+offset-prior)/sigma)**2)
        costs = np.stack(costs)
        best = np.argmin(costs, axis=0)
        interior = (best > 0) & (best < len(offsets)-1)
        safe = np.clip(best, 1, len(offsets)-2)
        rows, cols = np.indices(height.shape)
        left, center, right = costs[safe-1, rows, cols], costs[safe, rows, cols], costs[safe+1, rows, cols]
        finite = np.isfinite(left) & np.isfinite(center) & np.isfinite(right) & np.isfinite(before)
        # 无支持的点不参与差值运算，避免 inf-inf 污染置信度。
        left, center, right = (np.where(finite, value, 0) for value in (left, center, right))
        curvature = left+right-2*center
        active = (interior & finite & (curvature > noise_squared*config.DEPTH_MIN_CURVATURE) &
                  (center < noise_squared) & (before+prior_cost-center > noise_squared*config.DEPTH_MIN_IMPROVEMENT))
        subpixel = np.clip(np.divide(0.5*(left-right), curvature, out=np.zeros_like(curvature),
                                    where=curvature > 0), -1, 1)
        delta = offsets[safe]+subpixel*(offsets[1]-offsets[0])
        proposed = height+np.where(active, delta, 0)
        tree = self._terrain_tree(k, proposed)
        observations = self._sample_views(k, proposed, image_ids, tree)
        after = fit(observations)
        active &= (after < before-noise_squared*config.DEPTH_MIN_IMPROVEMENT)
        active &= after+noise_squared*((proposed-prior)/sigma)**2 < before+prior_cost
        quality = np.where(active, np.minimum(curvature/noise_squared, 1)*np.exp(-after/noise_squared), 0)
        return np.where(active, proposed, height).astype(np.float32), active, quality.astype(np.float32), before, after, counts

    def _accept_height_update(self, maplet_id, height, albedo, proposed_height, proposed_albedo, image_ids, samples):
        """实际重投影后的线搜索；同一观测集比较代价，不能靠丢掉难拟合像素获益。"""
        k = maplet_id
        masks = [sample[1] for sample in samples]
        count = sum(int(mask.sum()) for mask in masks)
        if count == 0:
            return height, albedo, False, 0.0, 0.0
        threshold = config.HUBER_SIGMA*config.PHOTOMETRIC_NOISE

        def cost(h, rho, observations):
            """在固定原观测掩码上计算 Huber 代价；丢失原观测时返回无穷大。"""
            q, p = np.gradient(h, self.spacing[k])
            value = 0.0
            for (observed, usable, view, sun), mask in zip(observations, masks):
                if np.any(mask & ~usable):
                    return np.inf
                residual = np.abs(observed-rho*_reflectance(p, q, sun, view, derivatives=False)[0])[mask]
                value += float(np.sum(np.where(residual <= threshold, residual**2,
                                               2*threshold*residual-threshold**2)))
            return value/count

        before = cost(height, albedo, samples)
        delta = proposed_height-height
        limit = self.spacing[k]*config.MAX_HEIGHT_STEP_SPACING
        scale = min(1.0, float(limit/max(np.max(np.abs(delta)), config.NUMERICAL_EPSILON)))
        for _ in range(config.LINE_SEARCH_STEPS):
            candidate = height+np.float32(scale)*delta
            rho = albedo+np.float32(scale)*(proposed_albedo-albedo)
            tree = self._terrain_tree(k, candidate)
            projected = self._sample_views(k, candidate, image_ids, tree)
            after = cost(candidate, rho, projected)
            if after < before*(1-config.HEIGHT_COST_MIN_IMPROVEMENT):
                return candidate, rho, True, before, after
            scale *= 0.5
        return height, albedo, False, before, before

    def _height_anchors(self, maplet_id, prior):
        """初始形状给弱约束，中心立体高度和已知重叠对应点给强约束。"""
        k = maplet_id
        weight = np.full(prior.shape, config.INTEGRATION_PRIOR_WEIGHT, dtype=np.float32)
        target_sum = weight * prior
        center = (prior.shape[0]//2, prior.shape[1]//2)
        if not self.maplet_view(k, 'valid')[center]:
            rows, cols = np.nonzero(self.maplet_view(k, 'valid'))
            nearest = np.argmin((rows-center[0])**2 + (cols-center[1])**2)
            center = (rows[nearest], cols[nearest])
        weight[center] += config.INTEGRATION_ANCHOR_WEIGHT
        target_sum[center] += config.INTEGRATION_ANCHOR_WEIGHT * prior[center]
        for edge_id in np.flatnonzero(np.any(self.overlap_pairs == k, axis=1)):
            side = int(self.overlap_pairs[edge_id, 1] == k)
            other = self.overlap_pairs[edge_id, 1-side]
            start, end = self.overlap_offsets[edge_id:edge_id+2]
            pairs = self.overlap_sample_ids[start:end]
            supported = self.valid[pairs].all(axis=1)
            pairs = pairs[supported]
            indices = pairs[:, side] - self.maplet_offsets[k]
            other_indices = pairs[:, 1-side] - self.maplet_offsets[other]
            points = self.body_points(int(other)).reshape(-1, 3)[other_indices]
            heights = (points-self.origins[k]) @ self.bases[k, :, 2]
            strength = self.overlap_weights[start:end][supported] * config.INTEGRATION_OVERLAP_WEIGHT
            np.add.at(weight.ravel(), indices, strength)
            np.add.at(target_sum.ravel(), indices, strength*heights)
            if self.split_levels[k] or self.split_levels[other] or not len(pairs):
                # 旋转重采样后两块节点通常不重合。沿本块法向与邻块高程面求交，
                # 在同一条物理射线上施加约束，不能把最近节点的高度直接当成目标。
                starts = self._surface_points(k, np.zeros_like(prior))
                starts = (starts-self.origins[other]) @ self.bases[other]
                direction = self.bases[k, :, 2] @ self.bases[other]
                target, _, _, overlap = self._intersect_height_grid(
                    self.maplet_view(other), self.maplet_view(other, 'valid'),
                    self.spacing[other], starts, direction)
                overlap &= self.maplet_view(k, 'valid')
                overlap.ravel()[indices] = False  # 已有显式对应点的约束不重复累计。
                strength = np.float32(config.INTEGRATION_OVERLAP_WEIGHT)
                weight[overlap] += strength
                target_sum[overlap] += strength*target[overlap]
        return weight, target_sum / weight

    def update(self, image, *, K, R, t, sun_direction=None, mask=None, split=True, defer=False,
               intensity_scale=None, intensity_offset=0.0, timestamp_utc=None):
        """保存一张新观测，并以传统 SPC 的局部流程更新可见 Maplet。

        K/R/t 沿用 X_camera=R@X_body+t，照片必须已去畸变，可输入灰度或线性 RGB。
        RGB 按配置亮度系数转为灰度。sun_direction 为本体系
        表面指向太阳的方向；未知时只保存照片和块级关联。整数灰度默认除以其类型最大值，
        浮点灰度默认已线性归一化；显式定标公式为 (image-intensity_offset)/intensity_scale。
        无法从相机参数推导太阳方向，也不自动去 gamma 或扣除环境光。

        每块：筛选历史视图 → 立体相关搜索中心高度 → 光度最小二乘求坡度/反照率 →
        带中心及重叠点约束的坡度积分。相机参数固定，不含全局 bundle adjustment。
        FIT_ALBEDO=False 且 LUNAR_LAMBERT_WEIGHT=0 时，用跨视角光度一致性搜索逐点高程；
        单位法向独立于粗网格差分，height_prior 保留首次更新前形状以约束累计漂移。
        单张照片或退化光照不足以同时解两个坡度及反照率，此时仅保留已有形状或可靠立体偏移。

        split=True 时按投影 GSD 将活动 Maplet 四等分，子块行列数不变。
        子块参考法向拟合局部坡面，高程沿新法向重投影；间距按新切平面的覆盖尺寸计算。
        每次调用最多拆一层；父块归档，不再参与求解、遮挡计算和 OBJ 导出。
        重采样节点初始置信度为零，只有足够的新旧观测支持求解后才获得非零评分。
        拆分会更换逐点数组；先前获取的 maplet_view/body_points 等视图需重新获取。

        返回 image_id、split_maplets（父块）、split_children（父子编号映射）、
        updated_maplets 及每块的状态/拟合指标。
        照片在求解前写盘；即使没有可更新区域，它也保留在实例目录供后续使用。

        defer=True 只保存照片并建立候选关联，忽略 split；全部导入后调用 refine()。
        这适合已知全部相机的离线数据集，避免每加入一帧重复求解同一块。
        """
        raw = np.asarray(image)
        scale = intensity_scale
        if scale is None:
            scale = np.iinfo(raw.dtype).max if raw.dtype.kind in 'ui' else 1
        if scale <= 0:
            raise ValueError('intensity_scale 必须大于零')
        pixels = (raw.astype(np.float32) - np.float32(intensity_offset)) / np.float32(scale)
        if pixels.ndim == 3:
            pixels = pixels @ np.asarray(config.RGB_LUMINANCE_WEIGHTS, dtype=np.float32)
        sun = None if sun_direction is None else _unit(np.asarray(sun_direction, dtype=np.float32))
        if not config.FIT_ALBEDO and self.height_prior is None:
            self.height_prior = self.height.copy()
        image_id = self.append_image(pixels, K=K, R=R, t=t, mask=mask,
                                     sun_direction=sun, timestamp_utc=timestamp_utc)
        report = dict(image_id=image_id, split_maplets=[], split_children={}, updated_maplets=[], maplets=[])
        tree = None  # 仅无重叠邻块的区域需要这一份公共遮挡树。
        visible = []
        candidates = []
        total = len(self.height)
        for k in np.flatnonzero(self.maplet_active):
            k = int(k)
            if not self.maplet_view(k, 'valid').any():
                continue
            # 射线只能减少可用点；先排除背面、出视场和无光照的块。
            _, possible, _, _ = self._sample_maplet(k, self.maplet_view(k), image_id)
            possible_count = np.count_nonzero(possible)
            if possible_count < min(config.MIN_UPDATE_POINTS, config.SPLIT_MIN_POINTS):
                continue
            if defer:
                if (possible_count >= config.MIN_UPDATE_POINTS
                        and possible_count/possible.size >= config.MIN_OBSERVATION_COVERAGE):
                    visible.append(k)
                continue
            if len(self.neighbors(k)):
                visible_tree = self._terrain_tree(k, self.maplet_view(k))
            else:
                if tree is None:
                    tree = self._terrain_tree()
                visible_tree = tree
            _, usable, _, _ = self._sample_maplet(k, self.maplet_view(k), image_id, visible_tree)
            del visible_tree
            count = int(np.count_nonzero(usable))
            if count >= config.MIN_UPDATE_POINTS and count/usable.size >= config.MIN_OBSERVATION_COVERAGE:
                visible.append(k)
            # 拆分可以由局部观测触发，不依赖父块能否达到完整高程求解的覆盖门槛。
            if (split and sun is not None and count >= config.SPLIT_MIN_POINTS
                    and count/np.count_nonzero(self.maplet_view(k, 'valid')) >= config.SPLIT_MIN_COVERAGE
                    and self.split_levels[k] < config.MAX_SPLIT_DEPTH
                    and len(candidates) < config.MAX_SPLITS_PER_UPDATE
                    and len(self.maplet_shapes)+4*(len(candidates)+1) <= config.MAX_MAPLETS):
                extra = 4*int(np.prod(self.maplet_shapes[k]))
                if (total+extra <= config.MAX_TOTAL_SAMPLES
                        and self.spacing[k]/self._image_gsd(k, image_id) >= 2*config.SPLIT_PIXELS_PER_SAMPLE):
                    candidates.append(k)
                    total += extra
        del tree
        self._associate_image(sorted(set(visible).union(candidates)), image_id)
        if defer:
            report['status'] = 'deferred'
            report['candidate_maplets'] = visible
            return report
        children = self._split_maplets(candidates)
        report['split_maplets'] = candidates
        report['split_children'] = children
        visible = [k for k in visible if self.maplet_active[k]]
        for ids in children.values():
            for k in ids:
                if not self.maplet_view(k, 'valid').any():
                    continue
                child_tree = self._terrain_tree(k, self.maplet_view(k))
                _, usable, _, _ = self._sample_maplet(k, self.maplet_view(k), image_id, child_tree)
                usable_count = np.count_nonzero(usable)
                if (usable_count >= config.MIN_UPDATE_POINTS
                        and usable_count/usable.size >= config.MIN_OBSERVATION_COVERAGE):
                    visible.append(k)
        return self._refine_maplets(visible, report, has_illumination=sun is not None)

    def _split_from_observations(self, report, progress=None):
        """按已存储照片的 GSD 和实际可见覆盖率逐层细分，不重复导入或逐帧求解。

        每层批量建立子块并继承父块观测；新子块继续检查是否还需要细分。
        批量流程受总块数、总节点数及最大层数约束，单帧拆分数量限制仅用于 update。
        """
        pending = np.flatnonzero(self.maplet_active).tolist()
        while pending:
            candidates = []
            total_samples = len(self.height)
            for position, k in enumerate(pending):
                if progress is not None:
                    progress('split', position, len(pending))
                valid = self.maplet_view(k, 'valid')
                if not valid.any() or self.split_levels[k] >= config.MAX_SPLIT_DEPTH:
                    continue
                extra = 4*int(np.prod(self.maplet_shapes[k]))
                if (len(self.maplet_shapes)+4*(len(candidates)+1) > config.MAX_MAPLETS
                        or total_samples+extra > config.MAX_TOTAL_SAMPLES):
                    report['split_budget_exhausted'] = True
                    continue
                # 使用所有已关联照片的 GSD；视角多样性筛选不应丢掉最清晰的一帧。
                image_ids = [int(i) for i in self.observation_ids(k)
                             if self._image_files[i] is not None and not self.distortion_counts[i]
                             and np.isfinite(self.sun_directions[i]).all()]
                if not image_ids:
                    continue
                gsds = self._image_gsds(k, image_ids)
                ranked = sorted(zip(gsds, image_ids))
                height = self.maplet_view(k)
                tree = None
                for gsd, image_id in ranked:
                    if self.spacing[k]/gsd < 2*config.SPLIT_PIXELS_PER_SAMPLE:
                        break
                    _, possible, _, _ = self._sample_maplet(k, height, image_id)
                    count = np.count_nonzero(possible)
                    if count < config.SPLIT_MIN_POINTS or count/valid.sum() < config.SPLIT_MIN_COVERAGE:
                        continue
                    if tree is None:
                        tree = self._terrain_tree(k, height)
                    _, usable, _, _ = self._sample_maplet(k, height, image_id, tree)
                    count = np.count_nonzero(usable)
                    if count >= config.SPLIT_MIN_POINTS and count/valid.sum() >= config.SPLIT_MIN_COVERAGE:
                        candidates.append(k)
                        total_samples += extra
                        break
            if progress is not None:
                progress('split', len(pending), len(pending))
            if not candidates:
                break
            children = self._split_maplets(candidates)
            report['split_maplets'].extend(candidates)
            report['split_children'].update(children)
            pending = [child for group in children.values() for child in group]

    def refine(self, *, split=False, progress=None):
        """用已关联历史照片更新所有活动块，不重复写入照片。

        可先 update(..., defer=True) 导入一批照片，再统一求解；候选关联仅作
        宽松投影筛选，求解仍用当前地形的精确相机遮挡及配置的太阳遮挡检查。
        每块实际求解视图数仍受 MAX_IMAGES_PER_MAPLET 限制。
        split=True 时先按观测分辨率细分，再统一求解活动叶块；默认保持原布局。
        progress 可接收 (phase, completed, total)，用于批量任务的进度显示。
        """
        report = dict(image_id=None, split_maplets=[], split_children={}, updated_maplets=[], maplets=[])
        if split:
            self._split_from_observations(report, progress)
        visible = [int(k) for k in np.flatnonzero(self.maplet_active)
                   if self.maplet_view(k, 'valid').any() and len(self.observation_ids(k))]
        return self._refine_maplets(visible, report, progress=progress)

    def _refine_maplets(self, visible, report, *, has_illumination=True, progress=None):
        """在线和批量更新共用同一局部 SPC 求解过程。"""
        for position, k in enumerate(visible):
            if progress is not None:
                progress('refine', position, len(visible))
            ids = self._select_views(k)
            result = dict(maplet_id=k, image_ids=ids, status='insufficient_observations',
                          stereo_quality=0.0, solved_points=0)
            report['maplets'].append(result)
            if not has_illumination:
                result['status'] = 'missing_illumination'
                continue
            if len(ids) < 2:
                continue
            valid = self.maplet_view(k, 'valid')
            height = np.where(valid, self.maplet_view(k), 0)
            albedo = np.where(valid, self.maplet_view(k, 'albedo'), config.DEFAULT_ALBEDO)
            tree = self._terrain_tree(k, height)
            samples = self._sample_views(k, height, ids, tree)
            if not config.FIT_ALBEDO and config.LUNAR_LAMBERT_WEIGHT == 0:
                candidate, supported, quality, before, after, counts = self._fit_photometric_heights(k, height, albedo, ids, samples)
                if supported.any():
                    self.maplet_view(k)[supported] = candidate[supported]
                    self.maplet_view(k, 'confidence')[supported] = quality[supported]
                    self.maplet_view(k, 'observation_count')[:] = counts
                    for name in ('height_sigma', 'overlap_sigma'):
                        if getattr(self, name) is not None:
                            self.maplet_view(k, name)[supported] = np.nan
                    result.update(status='photometric_depth', solved_points=int(supported.sum()),
                                  photometric_rms=float(np.sqrt(after[supported]).mean()),
                                  accepted_costs=[dict(before=float(before[supported].mean()),
                                                       after=float(after[supported].mean()), accepted=True)])
                    report['updated_maplets'].append(k)
                else:
                    result['status'] = 'unconstrained_photometric_depth'
                continue
            offset, stereo_quality = self._stereo_anchor(k, height, ids, samples)
            if stereo_quality > 0:
                shifted, _, accepted, _, _ = self._accept_height_update(k, height, albedo, height+offset, albedo, ids, samples)
                if accepted:
                    offset = np.float32(np.mean((shifted-height)[valid]))
                    height = shifted
                else:
                    offset, stereo_quality = np.float32(0), np.float32(0)
            prior = height.copy()
            result['stereo_quality'] = float(stereo_quality)
            result['stereo_height_offset'] = float(offset)
            changed = bool(stereo_quality > 0)
            confidence = self.maplet_view(k, 'confidence').copy()
            counts = np.zeros(height.shape, dtype=np.int32)
            active = np.zeros(height.shape, dtype=np.bool_)
            solved = np.zeros(height.shape, dtype=np.bool_)
            for _ in range(config.UPDATE_OUTER_ITERATIONS):
                tree = self._terrain_tree(k, height)
                samples = self._sample_views(k, height, ids, tree)
                p, q, rho, quality, active, counts, _ = _fit_slopes(samples, height, albedo, self.spacing[k])
                active &= self.maplet_view(k, 'valid') & (quality >= config.MIN_SLOPE_QUALITY)
                if np.count_nonzero(active) < config.MIN_UPDATE_POINTS:
                    break
                anchor_weight, anchor_height = self._height_anchors(k, prior)
                unsupported = ~active
                anchor_height[unsupported] = height[unsupported]
                anchor_weight[unsupported] = np.maximum(anchor_weight[unsupported], config.INTEGRATION_UNOBSERVED_WEIGHT)
                new_height = _integrate_slopes(height, p, q, quality*active, self.spacing[k], anchor_weight, anchor_height)
                # 完整积分结果作为候选；只写 active 会破坏相邻差分和积分约束。
                new_height[~valid] = height[~valid]
                rho[~active] = albedo[~active]
                height, albedo, accepted, before_cost, after_cost = self._accept_height_update(
                    k, height, albedo, new_height, rho, ids, samples)
                result.setdefault('accepted_costs', []).append(dict(before=before_cost, after=after_cost, accepted=accepted))
                if not accepted:
                    break
                solved |= active
                confidence[active] = quality[active]*max(stereo_quality, config.PRIOR_ANCHOR_CONFIDENCE)
                changed = True
            # 用积分后的实际形状重新评估残差，不把坡度拟合的理想残差当作高度质量。
            active = solved
            if active.any():
                tree = self._terrain_tree(k, height)
                final_samples = self._sample_views(k, height, ids, tree)
                q, p = np.gradient(height, self.spacing[k])
                squared = np.zeros(height.shape, dtype=np.float32)
                final_count = np.zeros(height.shape, dtype=np.int32)
                for observed, usable, view, light in final_samples:
                    residual = observed - albedo*_reflectance(p, q, light, view, derivatives=False)[0]
                    squared += np.where(usable, residual*residual, 0)
                    final_count += usable
                actual_rms = np.sqrt(squared / np.maximum(final_count, 1).astype(np.float32))
                confidence[active] *= np.exp(-(actual_rms[active]/config.PHOTOMETRIC_NOISE)**2)
                confidence[final_count < config.MIN_PHOTOMETRIC_IMAGES] = 0
                result['photometric_rms'] = float(actual_rms[active].mean())
                result['status'] = 'photometric_and_stereo' if stereo_quality > 0 else 'photometric_with_prior_anchor'
                result['solved_points'] = int(np.count_nonzero(active))
            elif stereo_quality > 0:
                center = (height.shape[0]//2, height.shape[1]//2)
                confidence[center] = max(confidence[center], stereo_quality*config.PRIOR_ANCHOR_CONFIDENCE)
                result['status'] = 'stereo_only'
            else:
                result['status'] = 'degenerate_geometry_or_lighting'
            if changed:
                self.maplet_view(k)[valid] = height[valid]
                self.maplet_view(k, 'albedo')[valid] = albedo[valid]
                confidence[~valid] = 0
                self.maplet_view(k, 'confidence')[:] = np.clip(confidence, 0, 1)
                self.maplet_view(k, 'observation_count')[:] = counts
                if self.height_sigma is not None:
                    self.maplet_view(k, 'height_sigma')[:] = np.nan
                if self.overlap_sigma is not None:
                    self.maplet_view(k, 'overlap_sigma')[:] = np.nan
                report['updated_maplets'].append(k)
        if progress is not None:
            progress('refine', len(visible), len(visible))
        if report['updated_maplets']:
            self._invalidate_mesh()
            report['status'] = 'updated'
        elif report['split_maplets']:
            report['status'] = 'split_only'
        elif not visible:
            report['status'] = 'no_visible_initial_surface'
        else:
            report['status'] = 'stored_only'
        return report


    def neighbors(self, maplet_id):
        """O(1) 定位邻接 CSR 切片，返回只读整数编号视图。"""
        k = maplet_id
        start, end = self.neighbor_offsets[k:k + 2]
        return self.neighbor_ids[start:end]

    @property
    def active_sample_mask(self):
        """当前叶块中的有效节点；body_points() 的打包结果也包含归档父块。"""
        return self.valid & np.repeat(self.maplet_active, np.diff(self.maplet_offsets))

    @property
    def extents(self):
        """每块的 (u跨度,v跨度)，单位米，形状 (M,2)。"""
        return (self.maplet_shapes[:, ::-1].astype(np.float32) - 1) * self.spacing[:, None]

    @property
    def camera_centers(self):
        """批量返回本体系相机中心 (I,3)，单位米。"""
        return -np.einsum('nij,ni->nj', self.R, self.t)

    @classmethod
    def from_obj(cls, mesh: TriangleMesh, *, maplet_side=None, spacing=None, max_maplets=None,
                 overlap=None, albedo=config.DEFAULT_ALBEDO, keep_mesh=False,
                 frame='body_fixed', units='m', image_cache_bytes=None):
        """由 obj_reader.TriangleMesh 自动建立可直接 update/to_obj 的 SPCModel。

        保持输入坐标、尺度和面绕序；需要一致的面绕序，不自动修补孔洞或翻转面。
        mesh 可由 obj_reader.read_obj 读取，也可直接在内存中构造；此方法不读取文件。
        复用 vertices/faces、预计算的 face_centers/face_normals，调用方保证它们相互一致。
        反照率使用 albedo，初始置信度/观测计数为零，不修改输入网格及其数组。

        maplet_side 是奇数边长，spacing 是相邻高程节点的物理间距。未给 spacing 时，
        根据表面积和配置的目标块数估计；max_maplets 是上限，实际块数自动确定。
        overlap 控制中心选取时预留的线性重叠。以面积采样点覆盖率判断是否继续建块，
        不是逐三角面的严格覆盖保证；数量/内存上限可能留下未覆盖区域。统计保存在
        optimization_state['initialization']，包括是否因预算停止和采样覆盖率。

        每块沿参考法向采样包含种子面的局部连通表面；孔洞、背面及未命中位置 valid=False。
        高程先验复制初始高程；父编号为 -1，所有块活动，拆分层数为 0。
        照片及 Maplet→照片 CSR 初始为空；邻接按同一表面上的几何重叠建立，
        非对齐网格通过插值约束关联，不伪造逐点对应。默认不保留原始大网格；
        keep_mesh=True 时额外保存 vertices/faces，后续地形更新会使该网格失效。

        示例：mesh = read_obj('obj_models/67p.obj')
              model = SPCModel.from_obj(mesh, maplet_side=17)
        """
        side = config.OBJ_MAPLET_SIDE if maplet_side is None else maplet_side
        maximum = config.OBJ_MAX_MAPLETS if max_maplets is None else max_maplets
        overlap = config.OBJ_MAPLET_OVERLAP if overlap is None else overlap
        side = _nonnegative_int(side, 'maplet_side', 3)
        maximum = _nonnegative_int(maximum, 'max_maplets', 1)
        if side % 2 != 1 or not 0 <= overlap < 1:
            raise ValueError('maplet_side 必须为奇数，overlap 必须位于 [0,1)')
        if spacing is not None and (not np.isfinite(spacing) or spacing <= 0):
            raise ValueError('spacing 必须为有限正数')
        maximum = min(maximum, config.MAX_MAPLETS, config.MAX_TOTAL_SAMPLES//(side*side))
        if maximum == 0:
            raise ValueError('当前采样点预算不足以建立一个 Maplet')
        vertices = np.asarray(mesh.vertices, dtype=np.float32)
        faces = np.asarray(mesh.faces, dtype=np.int32)
        centers = np.asarray(mesh.face_centers, dtype=np.float32)
        normal = np.asarray(mesh.face_normals, dtype=np.float32)
        triangles = vertices[faces]
        lengths = np.linalg.norm(np.cross(triangles[:, 1]-triangles[:, 0],
                                          triangles[:, 2]-triangles[:, 0]), axis=1)
        usable = np.isfinite(lengths) & (lengths > 0)
        if not usable.any():
            raise ValueError('TriangleMesh 没有可用的非退化三角面')
        if not usable.all():
            faces, triangles, normal, lengths = faces[usable], triangles[usable], normal[usable], lengths[usable]
            centers = centers[usable]
        areas = lengths*np.float32(0.5)
        area = np.sum(areas, dtype=np.float32)
        if spacing is None:
            spacing = np.sqrt(area/min(config.OBJ_TARGET_MAPLETS, maximum))/((side-1)*(1-overlap))
        spacing = np.float32(spacing)
        half = np.float32((side-1)*spacing/2)
        depth = np.float32(half*config.OBJ_HEIGHT_EXTENT_RATIO)

        # 确定性的面积分层采样，避免随机种子导致同一 OBJ 多次导入得到不同划分。
        cumulative = np.cumsum(areas, dtype=np.float32)
        count = config.OBJ_SEED_SAMPLES
        fractions = (np.arange(count, dtype=np.float32)+np.float32(0.5))/count
        face_ids = np.searchsorted(cumulative, fractions*cumulative[-1]).clip(max=len(faces)-1)
        sequence = np.arange(count, dtype=np.float32)+np.float32(0.5)
        root = np.sqrt(np.mod(sequence*np.float32(0.61803398875), 1))
        second = np.mod(sequence*np.float32(0.41421356237), 1)
        barycentric = np.column_stack((1-root, root*(1-second), root*second))
        points = np.sum(triangles[face_ids]*barycentric[..., None], axis=1)
        extra = np.arange(len(faces)) if len(faces) <= count//2 else np.array([int(np.argmax(areas))])
        points = np.concatenate((centers[extra], points))
        face_ids = np.concatenate((extra, face_ids))
        seed_normals = normal[face_ids]
        # 全局焊接一次，后续每块只处理整数顶点编号，省去反复对三维坐标排序。
        welded = np.unique(vertices, axis=0, return_inverse=True)[1]
        vertex_ids = welded[faces].astype(np.int32)
        del welded
        max_radius = np.float32(0)
        for start in range(0, len(triangles), config.OBJ_QUERY_BATCH):
            delta = triangles[start:start+config.OBJ_QUERY_BATCH]-centers[start:start+config.OBJ_QUERY_BATCH, None]
            max_radius = max(max_radius, np.sqrt(np.max(np.sum(delta*delta, axis=-1))))
        # cKDTree 内部索引用 float64，模型几何及数值求解仍为 float32；索引在导入后释放。
        index = _ObjSurfaceIndex(triangles, normal, vertex_ids, cKDTree(centers), max_radius)
        axis = (np.arange(side, dtype=np.float32)-(side-1)/2)*spacing
        col, row = np.meshgrid(axis, axis)
        xy = np.column_stack((col.ravel(), row.ravel()))
        uncovered = np.ones(len(points), dtype=np.bool_)
        nearest = np.full(len(points), np.inf, dtype=np.float32)
        origins, bases, heights, masks, patch_faces = [], [], [], [], []
        seed = int(np.argmax(areas[face_ids[:len(extra)]]))
        while uncovered.any() and len(origins) < maximum:
            origin, n = points[seed], seed_normals[seed]
            reference = np.eye(3, dtype=np.float32)[int(np.argmin(np.abs(n)))]
            tangent = _unit(np.cross(reference, n))
            basis = np.column_stack((tangent, np.cross(n, tangent), n))
            patch_ids = _obj_patch_faces(index, origin, basis, half, depth, int(face_ids[seed]))
            patch = triangles[patch_ids]
            local = (points-origin) @ basis
            interior = uncovered & (np.abs(local[:, :2]) <= half*(1-overlap)).all(axis=1)
            interior &= (np.abs(local[:, 2]) <= depth) & (seed_normals @ n >= config.OBJ_MIN_NORMAL_COSINE)
            ids = np.flatnonzero(interior)
            query = np.concatenate((xy, local[ids, :2]))
            values, valid = _obj_project_heights((patch-origin) @ basis, query, depth)
            heights.append(values[:side*side])
            masks.append(valid[:side*side])
            origins.append(origin.copy())
            bases.append(basis)
            # 三角面身份仅在初始化期间用于区分相邻但不连通的表面层。
            patch_faces.append(patch_ids)
            matched = valid[side*side:] & (np.abs(values[side*side:]-local[ids, 2]) <= spacing*config.SPLIT_REPROJECT_TOLERANCE)
            uncovered[ids[matched]] = False
            uncovered[seed] = False
            nearest = np.minimum(nearest, np.sum((points-origin)**2, axis=1))
            if uncovered.any():
                seed = int(np.argmax(np.where(uncovered, nearest, -1)))
        del index, vertex_ids, triangles
        m = len(origins)
        origins, bases = np.asarray(origins, dtype=np.float32), np.asarray(bases, dtype=np.float32)
        heights, masks = np.asarray(heights, dtype=np.float32), np.asarray(masks, dtype=np.bool_)
        # 先用包围球筛选块对，再确认共有源三角面与实际高程重叠，防止跨薄层相连。
        coordinates = (origins[:, None]+col.ravel()[None, :, None]*bases[:, None, :, 0]
                       +row.ravel()[None, :, None]*bases[:, None, :, 1]
                       +heights[..., None]*bases[:, None, :, 2])
        radii = np.sqrt(2*half*half+np.max(np.where(masks, heights*heights, 0), axis=1))
        edges = []
        for a in range(m):
            distance = np.linalg.norm(origins[a+1:]-origins[a], axis=1)
            candidates = np.flatnonzero(distance <= radii[a]+radii[a+1:])+a+1
            for b in candidates:
                if np.dot(bases[a, :, 2], bases[b, :, 2]) < config.OBJ_MIN_NORMAL_COSINE:
                    continue
                if not np.intersect1d(patch_faces[a], patch_faces[b], assume_unique=True).size:
                    continue
                for first, other in ((a, int(b)), (int(b), a)):
                    local = (coordinates[first, masks[first]]-origins[other]) @ bases[other]
                    h, valid = _bilinear(heights[other].reshape(side, side),
                                        local[:, 0]/spacing+(side-1)/2, local[:, 1]/spacing+(side-1)/2,
                                        masks[other].reshape(side, side))
                    if np.any(valid & (np.abs(h-local[:, 2]) <= spacing*config.OBJ_OVERLAP_HEIGHT_TOLERANCE)):
                        edges.append((a, int(b)))
                        break
        state = dict(source='TriangleMesh', source_faces=len(faces), maplets=m, spacing=float(spacing),
                     candidate_points=len(points), covered_fraction=float(1-np.mean(uncovered)),
                     budget_exhausted=bool(uncovered.any()), units=units,
                     coverage_note='Area-sampled estimate, not an exact all-triangle coverage guarantee.')
        options = {} if image_cache_bytes is None else dict(image_cache_bytes=image_cache_bytes)
        return cls(maplet_shapes=np.full((m, 2), side, dtype=np.int32), origins=origins, bases=bases,
                   spacing=spacing, height=heights.ravel(), height_prior=heights.ravel().copy(),
                   valid=masks.ravel(), albedo=albedo,
                   overlap_pairs=np.asarray(edges, dtype=np.int32).reshape(-1, 2),
                   overlap_offsets=np.zeros(len(edges)+1, dtype=np.int64),
                   vertices=vertices if keep_mesh else None, faces=faces if keep_mesh else None,
                   mesh_maplet_ids=np.full(len(faces), -1, dtype=np.int32) if keep_mesh else None,
                   frame=frame, units=units, optimization_state={'initialization': state}, **options)

    def fuse_to_mesh(self, *, depth=None, keep_largest_component=False) -> TriangleMesh:
        """仅从活动 Maplet 当前点位和法向重建闭合曲面；不使用参考 OBJ、缓存网格或先验高程。

        重叠点按体素及法向分组后加权融合，再做 Screened Poisson 重建。
        法向应一致朝外；缺失区域由隐式曲面补全，不能保证等于真实形状。
        keep_largest_component=True 时只保留面数最多的连通曲面，适用于单天体。
        """
        try:
            import pymeshlab
        except ImportError as error:
            raise ImportError('闭合导出需要 pymeshlab；请安装 src/requirements/requirements.txt') from error
        depth = _nonnegative_int(config.OBJ_FUSION_DEPTH if depth is None else depth, 'depth', 4)
        if depth > 12:
            raise ValueError('depth 不得超过 12，避免八叉树内存失控')
        points, normals, quality, spacings = [], [], [], []
        for k in np.flatnonzero(self.maplet_active):
            valid = self.maplet_view(k, 'valid')
            h = self.maplet_view(k)
            padded = np.pad(valid, 1, mode='edge')
            usable = valid & padded[1:-1, :-2] & padded[1:-1, 2:] & padded[:-2, 1:-1] & padded[2:, 1:-1]
            usable &= np.isfinite(h)
            if not usable.any():
                continue
            q, p = np.gradient(np.where(valid, h, 0), self.spacing[k])
            world_normals = _unit(np.stack((-p, -q, np.ones_like(p)), axis=-1)) @ self.bases[k].T
            ny, nx = h.shape
            y, x = np.meshgrid(np.linspace(-1, 1, ny), np.linspace(-1, 1, nx), indexing='ij')
            taper = np.maximum(1-np.maximum(np.abs(x), np.abs(y)), 0.05)
            confidence = np.clip(np.nan_to_num(self.maplet_view(k, 'confidence')), 0, 1)
            points.append(self._surface_points(k, h)[usable])
            normals.append(world_normals[usable])
            quality.append((taper*(0.25+0.75*confidence))[usable])
            spacings.append(self.spacing[k])
        if not points:
            raise ValueError('没有可用于闭合重建的有效 Maplet 点和法向')
        points = np.concatenate(points).astype(np.float64)
        normals = np.concatenate(normals).astype(np.float64)
        quality = np.concatenate(quality).astype(np.float64)
        if not np.isfinite(points).all() or not np.isfinite(normals).all():
            raise ValueError('Maplet 几何包含非有限值')
        input_count = len(points)
        center = (points.min(axis=0)+points.max(axis=0))*0.5
        scale = np.ptp(points, axis=0).max()
        if len(points) < 32 or scale <= 0:
            raise ValueError('闭合重建至少需要 32 个分布在三维表面上的有效节点')
        points = (points-center)/scale
        singular = np.linalg.svd(points-points.mean(axis=0), compute_uv=False)
        if singular[-1] <= singular[0]*1e-4:
            raise ValueError('Maplet 点退化为平面/直线，无法可靠推断闭合体')
        voxel = float(np.median(spacings)*config.OBJ_FUSION_VOXEL_RATIO/scale)
        cells = np.floor((points-points.min(axis=0))/voxel).astype(np.int64)
        # 不合并同体素内相反朝向的薄层；保留实际法向供后续融合。
        directions = np.floor((np.clip(normals, -1, 1)+1)*2).astype(np.int64)
        _, inverse = np.unique(np.column_stack((cells, directions)), axis=0, return_inverse=True)
        weights = np.bincount(inverse, weights=quality)
        count = np.bincount(inverse)
        points = np.column_stack([np.bincount(inverse, weights=quality*points[:, axis])/weights for axis in range(3)])
        normals = np.column_stack([np.bincount(inverse, weights=quality*normals[:, axis])/weights for axis in range(3)])
        normals /= np.linalg.norm(normals, axis=1, keepdims=True)
        quality = weights/count
        quality /= np.median(quality)
        meshset = pymeshlab.MeshSet()
        meshset.add_mesh(pymeshlab.Mesh(vertex_matrix=points, v_normals_matrix=normals,
                                       v_scalar_array=quality), 'active_maplet_samples')
        meshset.generate_surface_reconstruction_screened_poisson(
            depth=depth, fulldepth=min(depth, 5), scale=1.2,
            pointweight=config.OBJ_FUSION_POINT_WEIGHT, confidence=True,
            preclean=False, threads=config.OBJ_FUSION_THREADS)
        # 按实际输出精度清理：float32 舍入可能让原本不同的顶点重合。
        # 若在舍入前清理，高分辨率网格仍会留下零面积面。
        result = meshset.current_mesh()
        vertices = np.asarray(result.vertex_matrix()*scale+center, dtype=np.float32)
        meshset.add_mesh(pymeshlab.Mesh(vertices, result.face_matrix()), 'output_precision_surface')
        meshset.meshing_remove_duplicate_vertices()
        meshset.meshing_remove_duplicate_faces()
        meshset.meshing_remove_null_faces()
        meshset.meshing_remove_unreferenced_vertices()
        result = meshset.current_mesh()
        vertices = np.asarray(result.vertex_matrix(), dtype=np.float32)
        faces = np.asarray(result.face_matrix(), dtype=np.int32)
        removed_components = removed_faces = 0
        if keep_largest_component:
            # 单天体实验可排除隐式重建产生的孤立小曲面；通用接口默认保留所有分量。
            edges = faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2)
            graph = csr_array((np.ones(len(edges)), (edges[:, 0], edges[:, 1])),
                              shape=(len(vertices), len(vertices)))
            components, labels = connected_components(graph, directed=False)
            if components > 1:
                face_labels = labels[faces[:, 0]]
                keep = face_labels == np.argmax(np.bincount(face_labels))
                removed_components, removed_faces = components-1, int((~keep).sum())
                used, inverse = np.unique(faces[keep], return_inverse=True)
                vertices, faces = vertices[used], inverse.reshape(-1, 3).astype(np.int32)
        topology = _closed_mesh_topology(vertices, faces)
        triangles = vertices[faces]
        cross = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
        if self.optimization_state is None:
            self.optimization_state = {}
        self.optimization_state['fusion'] = dict(
            method='oriented active Maplet samples, weighted voxel fusion, Screened Poisson',
            reference_mesh_used=False, height_prior_used=False, input_samples=input_count,
            fused_samples=len(points), voxel_size=voxel*float(scale), depth=depth,
            removed_components=removed_components, removed_faces=removed_faces,
            vertices=len(vertices), faces=len(faces), **topology,
            coverage_note='Missing surface coverage is completed by the implicit solver, not measured geometry.')
        return TriangleMesh(vertices, faces, triangles.mean(axis=1), _unit(cross))

    def to_obj(self, path: str | Path, *, source='auto', depth=None, keep_largest_component=False,
               chunk_size=config.OBJ_CHUNK_SIZE) -> Path:
        """导出 Wavefront OBJ 几何并返回路径；成功后替换目标文件。

        source='auto'：存在 Maplet 时融合当前高程为闭合曲面，否则使用 vertices/faces。
        source='maplets' 或 'fused'：只根据活动 Maplet 重建共享顶点的闭合曲面；
        不读取其他 OBJ，不使用 vertices/faces 或 height_prior。depth 控制重建深度。
        source='patches'：诊断模式，各 Maplet 独立三角化，不融合且不保证闭合。
        keep_largest_component 仅影响融合导出，默认保留全部连通分量。
        source='mesh'：直接导出已有全局网格，调用方须保证它与当前地形一致。

        patches 模式的网格单元四角均有效时沿左上到右下的对角线分为两个三角面；
        仅三角有效时生成一个三角面，更少则不连面。绕序朝向各块的参考法线。
        无效采样点被跳过并重新编号，有效孤立点保留为顶点；无有效顶点时报错。
        已拆分父块不导出。闭合融合需要 pymeshlab 和一致朝外的法向；未覆盖处由
        隐式曲面补全，不能保证补面等于真实形状。拓扑检查不通过时保留原目标文件。
        顶点使用 9 位有效数字，保证 float32 数值往返读取；只保存顶点和三角面，
        不保存反照率、置信度、相机或求解器状态。

        chunk_size 限制每批写入行数（至少 2）；融合计算另需全局点云/八叉树内存。
        在目标目录写临时文件，完成后原子替换，失败时保留已有目标文件。
        """
        if source not in ('auto', 'maplets', 'mesh', 'fused', 'patches'):
            raise ValueError("source 必须为 'auto'、'maplets'、'mesh'、'fused' 或 'patches'")
        chunk_size = _nonnegative_int(chunk_size, 'chunk_size', 2)
        if source == 'auto':
            source = 'maplets' if len(self.maplet_shapes) else 'mesh'
        if source == 'mesh' and not len(self.vertices):
            raise ValueError('没有可导出的全局网格顶点')
        fused = None
        if source in ('maplets', 'fused'):
            fused = self.fuse_to_mesh(depth=depth, keep_largest_component=keep_largest_component)

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                    dir=destination.parent, prefix=f'.{destination.name}.',
                                    suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(f'# SPCModel geometry; units: {self.units}\n# frame: {self.frame!r}\n# source: {source}\n')
                if source == 'mesh' or fused is not None:
                    vertices = self.vertices if fused is None else fused.vertices
                    faces = self.faces if fused is None else fused.faces
                    stream.write('o global_model\n')
                    for start in range(0, len(vertices), chunk_size):
                        np.savetxt(stream, vertices[start:start + chunk_size], fmt='v %.9g %.9g %.9g')
                    for start in range(0, len(faces), chunk_size):
                        # 先扩为 int64 再加 1，避免 int32 索引在 OBJ 编号时溢出。
                        np.savetxt(stream, faces[start:start + chunk_size].astype(np.int64) + 1, fmt='f %d %d %d')
                else:
                    stream.write('# Maplets are independent patches; overlaps are not fused.\n')
                    vertex_offset = 0
                    for k, (ny, nx) in enumerate(self.maplet_shapes):
                        if not self.maplet_active[k]:
                            continue
                        ny, nx = int(ny), int(nx)
                        valid = self.maplet_view(k, 'valid').ravel()
                        count = int(np.count_nonzero(valid))
                        if not count:
                            continue
                        points = self.body_points(k).reshape(-1, 3)
                        stream.write(f'o maplet_{k}\n')
                        # 每块一份索引映射；无效点不输出，后续块延续全局 OBJ 顶点编号。
                        indices = np.full(len(valid), -1, dtype=np.int64)
                        indices[valid] = np.arange(vertex_offset + 1, vertex_offset + count + 1, dtype=np.int64)
                        for start in range(0, len(points), chunk_size):
                            stop = start + chunk_size
                            np.savetxt(stream, points[start:stop][valid[start:stop]], fmt='v %.9g %.9g %.9g')
                        # 逐批处理单元，不为整个模型保存面数组；每个单元最多输出两面。
                        cells_per_batch = max(1, chunk_size // 2)
                        for start in range(0, (ny - 1) * (nx - 1), cells_per_batch):
                            cell = np.arange(start, min(start + cells_per_batch, (ny - 1) * (nx - 1)), dtype=np.int64)
                            a = (cell // (nx - 1)) * nx + cell % (nx - 1)
                            b, c, d = a + 1, a + nx, a + nx + 1
                            other = ~(valid[a] & valid[d])
                            triangles = np.empty((len(cell), 2, 3), dtype=np.int64)
                            triangles[:, 0, 0] = a
                            triangles[:, 0, 1] = b
                            triangles[:, 0, 2] = np.where(other, c, d)
                            triangles[:, 1, 0] = np.where(other, b, a)
                            triangles[:, 1, 1] = d
                            triangles[:, 1, 2] = c
                            triangles = triangles.reshape(-1, 3)
                            triangles = triangles[valid[triangles].all(axis=1)]
                            np.savetxt(stream, indices[triangles], fmt='f %d %d %d')
                        vertex_offset += count
                        del points, indices
                    if vertex_offset == 0:
                        raise ValueError('没有可导出的有效 Maplet 顶点')
            temporary.replace(destination)
            return destination
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def body_points(self, maplet_id=None, *, out=None, chunk_size=config.BODY_POINTS_CHUNK_SIZE):
        """高程转本体系；无效点为 NaN，可复用 out 避免重复分配输出。

        指定块返回 (Ny,Nx,3)，采用广播而不创建完整 meshgrid。
        不指定块返回打包顺序 (S,3)，包括归档父块，按同尺寸连续段分批广播。
        仅需要当前表面时，对返回值使用 active_sample_mask 筛选。
        chunk_size 是每批的采样点预算，每批至少包含一个完整 Maplet。
        out 须为可写 C 连续 float32 数组，不得与坐标输入共享内存。
        """
        chunk_size = _nonnegative_int(chunk_size, 'chunk_size', 1)
        k = maplet_id
        shape = (len(self.height), 3) if k is None else (*map(int, self.maplet_shapes[k]), 3)
        if out is None:
            out = np.empty(shape, dtype=np.float32)
        flat = out.reshape(-1, 3)
        output_start = 0 if k is None else int(self.maplet_offsets[k])
        runs = zip(self._shape_runs[:-1], self._shape_runs[1:]) if k is None else ((k, k + 1),)
        for run_start, run_end in runs:
            ny, nx = map(int, self.maplet_shapes[run_start])
            batch_size = max(1, int(chunk_size) // (ny * nx))
            u = np.arange(nx, dtype=np.float32) - (nx - 1) / 2
            v = np.arange(ny, dtype=np.float32) - (ny - 1) / 2
            for first in range(int(run_start), int(run_end), batch_size):
                last = min(first + batch_size, int(run_end))
                start, end = int(self.maplet_offsets[first]), int(self.maplet_offsets[last])
                block = flat[start - output_start:end - output_start].reshape(last - first, ny, nx, 3)
                height = self.height[start:end].reshape(last - first, ny, nx)
                valid = self.valid[start:end].reshape(last - first, ny, nx)
                basis = self.bases[first:last]
                spacing = self.spacing[first:last, None]
                np.multiply(height[..., None], basis[:, None, None, :, 2], out=block, where=valid[..., None])
                np.copyto(block, np.nan, where=~valid[..., None])
                block += (u[None, :, None] * (spacing * basis[:, :, 0])[:, None, :])[:, None, :, :]
                block += (v[None, :, None] * (spacing * basis[:, :, 1])[:, None, :])[:, :, None, :]
                block += self.origins[first:last, None, None, :]
        return out
