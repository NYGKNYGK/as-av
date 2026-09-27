# 0. pip install numpy scipy  (可选: trimesh，用于解析少见的 OBJ 写法)
# GPU（可选，CUDA 13）：pip install "cupy-cuda13x[ctk]>=14,<15"
"""两个三角网格（例如 SfM 重建结果与原始模型）的形状相似度。

单目 SfM 的重建与真实模型相差一个相似变换（旋转、平移、尺度），所以先配准再比较：
质心 / 尺度归一化 -> 主轴（PCA）给出 24 个候选旋转 -> 带尺度的截尾 ICP 精配准。
相似度用三维重建评测常用的 F-score（Knapitsch et al., Tanks and Temples, 2017）：
在两个表面上均匀采样，距离对方表面小于阈值 tau 的点所占比例分别为精度 / 完整度，
取二者的调和平均。取值 [0, 1]，1 表示两个表面在 tau 精度下完全重合。

OBJ 按字节并行解析；表面积分块计算，避免大网格的临时数组挤占内存。
device="auto" 在 CuPy / CUDA 可用时用 GPU KD-tree 做精确最近邻搜索，否则使用 CPU。
GPU 首次调用需要初始化 CUDA 和编译内核，批量比较时可摊薄这部分开销。
"""
from __future__ import annotations

import os
import warnings
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from itertools import permutations, product
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

if __package__:
    from .obj_reader import SpatialMesh, load_obj as load_spatial_obj
else:
    from obj_reader import SpatialMesh, load_obj as load_spatial_obj

# ---------------- OBJ 快速解析 ----------------

def _columns(buf: np.ndarray, starts: np.ndarray, width: int) -> np.ndarray:
    """取每个词元起点后的 width 个字节，返回 (width, n)：第 j 行是所有词元的第 j 个字符。"""
    idx = np.arange(width)[:, None] + starts[None, :]
    np.minimum(idx, len(buf) - 1, out=idx)
    return buf[idx]


def _parse_floats(buf: np.ndarray, starts: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """批量转换词元为 float32；避免长尾数累加和指数表的单精度溢出。"""
    width = int(lengths.max())
    tokens = _columns(buf, starts, width).T.copy()
    tokens[np.arange(width)[None, :] >= lengths[:, None]] = 32
    return tokens.view(f'S{width}').ravel().astype(np.float32)


def _parse_first_ints(buf: np.ndarray, starts: np.ndarray, width: int):
    """解析 'a'、'a/b'、'a//c'、'a/b/c' 中的 a，返回 (数值, 是否为负)。"""
    cols = _columns(buf, starts, width)
    val = np.zeros(len(starts), np.int64)
    run = np.ones(len(starts), bool)
    for j, c in enumerate(cols):
        d = c - np.uint8(48)
        run &= (d < 10) | ((j == 0) & (c == 45))
        val = np.where(run & (d < 10), val * 10 + d, val)
    return val, cols[0] == 45


class _Unsupported(Exception):
    """快速路径不支持的写法，交给 trimesh。"""


def _parse_chunk(buf: np.ndarray):
    """解析由完整行组成的一段字节，返回 (顶点 (n, 3), 三角面 (m, 3)，1 起始索引)。"""
    sep = buf <= 32                                           # 空格 / 制表符 / 换行 / 回车
    start = ~sep
    start[1:] &= sep[:-1]
    end = ~sep
    end[:-1] &= sep[1:]
    ts, te = np.flatnonzero(start), np.flatnonzero(end) + 1  # 每个词元的 [起点, 终点)
    empty = np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), np.int64)
    if len(ts) == 0:
        return empty

    line_starts = np.r_[0, np.flatnonzero(buf[:-1] == 10) + 1]
    first_tok = np.searchsorted(ts, line_starts)              # 每行第一个词元（关键字）
    n_tok = np.diff(np.r_[first_tok, len(ts)])
    kw = np.minimum(first_tok, len(ts) - 1)
    single = (n_tok > 0) & (te[kw] - ts[kw] == 1)
    is_v = single & (buf[ts[kw]] == 118)                      # 'v'（不含 vn / vt）
    is_f = single & (buf[ts[kw]] == 102)                      # 'f'

    v_first, v_count = first_tok[is_v], n_tok[is_v] - 1
    if len(v_first) and v_count.min() < 3:
        raise _Unsupported("顶点坐标少于 3 个")
    vt = (v_first[:, None] + np.arange(1, 4)).ravel()
    verts = _parse_floats(buf, ts[vt], te[vt] - ts[vt]).reshape(-1, 3) if len(vt) else empty[0]

    f_first, k = first_tok[is_f], n_tok[is_f] - 1
    if len(f_first) == 0:
        return verts, empty[1]
    if k.min() < 3:
        raise _Unsupported("面的顶点数少于 3")
    # 取出各面全部顶点引用，多边形按扇形 (0, i, i+1) 三角化
    triangles = bool((k == 3).all())
    if triangles:
        tok = (f_first[:, None] + np.arange(1, 4)).ravel()
    else:
        offsets = np.cumsum(k) - k
        tok = np.repeat(f_first + 1, k) + (np.arange(int(k.sum())) - np.repeat(offsets, k))
    width = int(min((te[tok] - ts[tok]).max(), 12))
    refs, neg = _parse_first_ints(buf, ts[tok], width)
    if neg.any():
        raise _Unsupported("负（相对）索引")
    if triangles:
        return verts, refs.reshape(-1, 3)
    n_tri = k - 2
    line = np.repeat(np.arange(len(k)), n_tri)
    j = np.arange(int(n_tri.sum())) - np.repeat(np.cumsum(n_tri) - n_tri, n_tri)
    base = offsets[line]
    faces = np.stack([refs[base], refs[base + 1 + j], refs[base + 2 + j]], axis=1)
    return verts, faces


def load_obj(path, workers: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """读取 OBJ 的顶点 (N, 3) float32 与三角面 (M, 3) int64（0 起始）。

    保留此旧版元组接口供已有调用及解析基准使用；双模型请使用
    obj_reader.load_obj。相似度计算的路径输入已统一使用新读取器。
    文件按行边界切块后多线程解析（numpy 运算期间释放 GIL）；遇到负索引等快速路径
    不支持的写法时退回 trimesh。
    """
    data = Path(path).read_bytes()
    buf = np.frombuffer(data, np.uint8)
    available = getattr(os, "process_cpu_count", os.cpu_count)() or 1
    workers = min(available, 16 if workers is None else max(1, workers))
    n_chunks = max(1, min(workers * 4, len(buf) >> 20))
    cuts = [0]
    for k in range(1, n_chunks):
        p = data.find(b"\n", k * len(buf) // n_chunks)
        if p < 0:
            break
        if p + 1 > cuts[-1]:
            cuts.append(p + 1)
    cuts.append(len(buf))
    chunks = [buf[a:b] for a, b in zip(cuts[:-1], cuts[1:]) if b > a]
    if not chunks:
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.int64)
    try:
        if len(chunks) == 1:
            parts = [_parse_chunk(chunks[0])]
        else:
            with ThreadPoolExecutor(workers) as pool:
                parts = list(pool.map(_parse_chunk, chunks))
    except _Unsupported:
        import trimesh

        mesh = trimesh.load(path, force="mesh", process=False)
        return np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.int64)

    verts = np.concatenate([p[0] for p in parts])
    faces = np.concatenate([p[1] for p in parts]) - 1
    if len(faces) and (faces.min() < 0 or faces.max() >= len(verts)):
        raise ValueError(f"{path}: 面索引越界")
    return verts, faces


# ---------------- 表面采样 ----------------

def sample_surface(vertices: np.ndarray, faces: np.ndarray, n: int, seed: int = 0) -> np.ndarray:
    """按面积在网格表面均匀采样 n 个点。"""
    vertices = np.asarray(vertices, dtype=np.float32)
    if n <= 0:
        raise ValueError("采样点数必须大于 0")
    if len(faces) == 0:
        raise ValueError("网格没有三角面")
    # 只保留一份全长 CDF；临时顶点/叉积数组限制在 CPU 缓存友好的大小。
    cdf = np.empty(len(faces), dtype=np.float32)
    block = 16_384
    for start in range(0, len(faces), block):
        f = faces[start:start + block]
        a, b, c = (vertices[f[:, i]] for i in range(3))
        cdf[start:start + block] = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    np.cumsum(cdf, out=cdf)
    if not np.isfinite(cdf[-1]) or cdf[-1] <= 0:
        raise ValueError("网格表面积必须为有限正数")
    rng = np.random.default_rng(seed)
    tri = np.minimum(np.searchsorted(cdf, rng.random(n, dtype=np.float32) * cdf[-1], side="right"), len(faces) - 1)
    u, v = rng.random((2, n), dtype=np.float32)
    flip = u + v > 1.0
    u[flip], v[flip] = 1.0 - u[flip], 1.0 - v[flip]
    a, b, c = (vertices[faces[tri, i]] for i in range(3))
    return a + u[:, None] * (b - a) + v[:, None] * (c - a)


@lru_cache(maxsize=8)
def _cached_samples(path: str, mtime_ns: int, size: int, n: int, seed: int) -> np.ndarray:
    # 键里带上修改时间和大小：文件被覆盖后不会拿到旧结果
    mesh = load_spatial_obj(path).origin_mesh
    samples = sample_surface(np.asarray(mesh.vertices, np.float32), mesh.faces, n, seed)
    samples.setflags(write=False)
    return samples


def _samples(mesh, n: int, seed: int) -> np.ndarray:
    """支持 OBJ、SpatialMesh、TriangleMesh、trimesh 或 (V, F)；SpatialMesh 取原始模型。"""
    if isinstance(mesh, (str, Path)):
        st = os.stat(mesh)
        return _cached_samples(str(Path(mesh).resolve()), st.st_mtime_ns, st.st_size, n, seed)
    if isinstance(mesh, SpatialMesh):
        mesh = mesh.origin_mesh
    if hasattr(mesh, "vertices") and hasattr(mesh, "faces"):
        vertices, faces = mesh.vertices, mesh.faces
    else:
        vertices, faces = mesh
    return sample_surface(np.asarray(vertices, np.float32), np.asarray(faces, np.int64), n, seed)


# ---------------- CUDA 最近邻搜索（按需加载 CuPy） ----------------


_CUDA_SOURCE = r'''
extern "C" __global__
void nearest(const float* points, const int* original, const int* nodes,
             const float* bounds, const float* queries, const int nq,
             const int nr, const float upper, float* distances, long long* indices) {
    int qi = blockDim.x * blockIdx.x + threadIdx.x;
    if (qi >= nq) return;
    float q[3] = {queries[3*qi], queries[3*qi+1], queries[3*qi+2]};
    float best = upper * upper;
    int found = nr;
    int pending[64];
    float lower[64];
    int top = 0;
    pending[top] = 0;
    lower[top++] = 0.0f;
    while (top) {
        --top;
        int node = pending[top];
        if (lower[top] > best) continue;
        int left = nodes[4*node];
        if (left < 0) {
            int start = nodes[4*node+2], end = nodes[4*node+3];
            for (int p = start; p < end; ++p) {
                float dx = q[0] - points[3*p];
                float dy = q[1] - points[3*p+1];
                float dz = q[2] - points[3*p+2];
                float d = dx*dx + dy*dy + dz*dz;
                if (d < best) {
                    best = d;
                    found = original[p];
                }
            }
        } else {
            int right = nodes[4*node+1];
            float dl = 0.0f, dr = 0.0f;
            for (int axis = 0; axis < 3; ++axis) {
                float a = fmaxf(0.0f, fmaxf(bounds[6*left+axis] - q[axis],
                                         q[axis] - bounds[6*left+axis+3]));
                float b = fmaxf(0.0f, fmaxf(bounds[6*right+axis] - q[axis],
                                         q[axis] - bounds[6*right+axis+3]));
                dl += a*a;
                dr += b*b;
            }
            // Push farther first so the next visit tightens the search radius.
            if (dl > dr) {
                int tmp = left; left = right; right = tmp;
                float tmpd = dl; dl = dr; dr = tmpd;
            }
            if (dr <= best) { pending[top] = right; lower[top++] = dr; }
            if (dl <= best) { pending[top] = left; lower[top++] = dl; }
        }
    }
    distances[qi] = found == nr ? __int_as_float(0x7f800000) : sqrtf(best);
    indices[qi] = found;
}
'''


@lru_cache(maxsize=1)
def _cuda_kernel():
    import cupy as cp

    # Keep a fixed rounding order for float32 comparisons near the threshold.
    kernel = cp.RawKernel(_CUDA_SOURCE, 'nearest', options=('--fmad=false',))
    try:
        kernel.compile()
    except cp.cuda.compiler.CompileException as exc:
        raise RuntimeError('Failed to compile the CUDA nearest-neighbor kernel') from exc
    return kernel


class CudaKDTree:
    def __init__(self, tree):
        import cupy as cp

        self.n = tree.n
        if tree.n >= np.iinfo(np.int32).max:
            raise ValueError('CUDA KD-tree requires fewer than 2**31 points')
        ordered = np.ascontiguousarray(tree.data[tree.indices], dtype=np.float32)
        # Breadth-first numbering lets each level's bounds be reduced in bulk.
        queue = [tree.tree]
        records = []
        levels = []
        first = 0
        while first < len(queue):
            last = len(queue)
            internal = []
            for i in range(first, last):
                node = queue[i]
                if node.split_dim < 0:
                    records.append((-1, -1, node.start_idx, node.end_idx))
                else:
                    child = len(queue)
                    queue.extend((node.lesser, node.greater))
                    records.append((child, child + 1, node.start_idx, node.end_idx))
                    internal.append(i)
            levels.append(np.asarray(internal, dtype=np.intp))
            first = last
        if len(levels) >= 64:
            raise RuntimeError('CUDA KD-tree traversal stack limit exceeded')
        nodes = np.asarray(records, dtype=np.int32)
        bounds = np.empty((len(nodes), 6), dtype=np.float32)
        leaves = np.flatnonzero(nodes[:, 0] < 0)
        leaves = leaves[np.argsort(nodes[leaves, 2])]
        starts = nodes[leaves, 2]
        bounds[leaves, :3] = np.minimum.reduceat(ordered, starts, axis=0)
        bounds[leaves, 3:] = np.maximum.reduceat(ordered, starts, axis=0)
        for parents in reversed(levels):
            left, right = nodes[parents, 0], nodes[parents, 1]
            bounds[parents, :3] = np.minimum(bounds[left, :3], bounds[right, :3])
            bounds[parents, 3:] = np.maximum(bounds[left, 3:], bounds[right, 3:])
        self.points = cp.asarray(ordered)
        self.original = cp.asarray(tree.indices, dtype=cp.int32)
        self.nodes = cp.asarray(nodes)
        self.bounds = cp.asarray(bounds)

    def query(self, queries, distance_upper_bound=np.inf):
        import cupy as cp

        queries = cp.ascontiguousarray(queries, dtype=cp.float32)
        n = len(queries)
        distances = cp.empty(n, dtype=cp.float32)
        indices = cp.empty(n, dtype=cp.int64)
        if n:
            _cuda_kernel()(((n + 127) // 128,), (128,),
                      (self.points, self.original, self.nodes, self.bounds, queries,
                       np.int32(n), np.int32(self.n), np.float32(distance_upper_bound),
                       distances, indices))
        return distances, indices


# ---------------- 配准 ----------------


def _cuda_modules():
    """惰性加载可选 GPU 依赖，CPU 路径无需安装 CuPy。"""
    import cupy as cp

    if cp.cuda.runtime.getDeviceCount() == 0:
        raise RuntimeError("没有可用的 CUDA GPU")
    return cp, CudaKDTree


def _check_device(device: str) -> None:
    if device not in ("auto", "cpu", "cuda"):
        raise ValueError("device 必须是 'auto'、'cpu' 或 'cuda'")


def _query_workers(n: int) -> int:
    # cKDTree 每次 query 都新建线程；小批查询不值得启动全部逻辑核心。
    available = getattr(os, "process_cpu_count", os.cpu_count)() or 1
    return min(available, 8 if n < 16_384 else 32, max(1, n // 256))


class _NearestNeighbors:
    """统一 CPU / GPU 查询；保持 float32 和 eps=0，不构造 N×M 距离矩阵。"""

    def __init__(self, points: np.ndarray, device: str):
        self.requested_device = device
        self.cp = None
        self.cpu_tree = cKDTree(np.asarray(points, dtype=np.float32))
        if device != "cpu":
            try:
                cp, CudaKDTree = _cuda_modules()
                self.tree = CudaKDTree(self.cpu_tree)
                self.cp = cp
                return
            except (ImportError, OSError, RuntimeError, MemoryError) as exc:
                if device == "cuda":
                    raise RuntimeError(
                        "CUDA 后端不可用；请安装与 CUDA 匹配的 CuPy >= 14 "
                        "（CUDA 13: pip install 'cupy-cuda13x[ctk]>=14,<15'），"
                        "或使用 device='cpu'。"
                    ) from exc
                if not isinstance(exc, ImportError):
                    warnings.warn(f"CUDA 初始化失败，改用 CPU：{exc}", RuntimeWarning, stacklevel=2)
        self.tree = self.cpu_tree

    def query(self, points, distance_upper_bound=np.inf):
        if self.cp is not None:
            cp = self.cp
            try:
                d, idx = self.tree.query(cp.asarray(points), distance_upper_bound=distance_upper_bound)
                return cp.asnumpy(d), cp.asnumpy(idx)
            except (OSError, RuntimeError, MemoryError) as exc:
                if self.requested_device == "cuda":
                    raise
                warnings.warn(f"CUDA 查询失败，改用 CPU：{exc}", RuntimeWarning, stacklevel=2)
                self.cp = None
                self.tree = self.cpu_tree
        d, idx = self.tree.query(np.asarray(points, dtype=np.float32),
                                 workers=_query_workers(len(points)),
                                 distance_upper_bound=distance_upper_bound)
        return d.astype(np.float32), idx


def _umeyama(src: np.ndarray, dst: np.ndarray):
    """最小二乘相似变换 dst ≈ s * R @ src + t（Umeyama 1991）。"""
    mu_s, mu_d = src.mean(axis=0), dst.mean(axis=0)
    xs, xd = src - mu_s, dst - mu_d
    U, D, Vt = np.linalg.svd(xd.T @ xs / len(src))
    S = np.ones(3, dtype=np.float32)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[2] = -1.0
    R = (U * S) @ Vt
    s = float((D * S).sum() / ((xs ** 2).sum() / len(src)))
    return s, R, mu_d - s * R @ mu_s


def _icp(src, tree, ref, s, R, t, iters: int, trim: float = 0.9, tol: float = 1e-6):
    """带尺度的截尾 ICP：每轮只用距离最近的 trim 比例点对，抵抗离群点和局部缺失。"""
    err = np.inf
    for _ in range(iters):
        d, idx = tree.query(s * src @ R.T + t)
        keep = d <= np.quantile(d, trim)
        s, R, t = _umeyama(src[keep], ref[idx[keep]])
        new_err = float(np.sqrt(np.mean(d[keep] ** 2)))
        if abs(err - new_err) <= tol * max(new_err, 1e-12):
            err = new_err
            break
        err = new_err
    return s, R, t, err


def _proper_rotations() -> list[np.ndarray]:
    """立方体的 24 个旋转（行列式为 +1 的带符号置换矩阵）。"""
    out = []
    for perm in permutations(range(3)):
        for signs in product((1.0, -1.0), repeat=3):
            G = np.zeros((3, 3), dtype=np.float32)
            G[range(3), perm] = signs
            if np.linalg.det(G) > 0:
                out.append(G)
    return out


def align(src: np.ndarray, ref: np.ndarray, n_fit: int = 8000, seed: int = 0,
          *, device: str = "auto"):
    """估计把 src 点云对齐到 ref 的相似变换，返回 (s, R, t)。

    PCA 主轴只确定到符号和顺序，所以把立方体的 24 个旋转都当作初值：先用最近邻
    距离粗筛，再对前几名做短程 ICP，最后对胜出者做完整 ICP。
    device 与 mesh_similarity 的同名参数一致，只改变最近邻计算后端。
    """
    rng = np.random.default_rng(seed)
    _check_device(device)
    src, ref = np.asarray(src, dtype=np.float32), np.asarray(ref, dtype=np.float32)
    if n_fit < 3 or min(len(src), len(ref)) < 3:
        raise ValueError("配准至少需要 3 个点，且 n_fit >= 3")
    fit_src = src[rng.choice(len(src), min(n_fit, len(src)), replace=False)]
    fit_ref = ref[rng.choice(len(ref), min(4 * n_fit, len(ref)), replace=False)]
    tree = _NearestNeighbors(fit_ref, device)

    c_src, c_ref = fit_src.mean(axis=0), fit_ref.mean(axis=0)
    r_src = np.sqrt(((fit_src - c_src) ** 2).sum(axis=1).mean())
    r_ref = np.sqrt(((fit_ref - c_ref) ** 2).sum(axis=1).mean())
    if not (r_src > 0 and r_ref > 0 and np.isfinite(r_src) and np.isfinite(r_ref)):
        raise ValueError("配准点云的尺度必须为有限正数")
    xs, xr = fit_src - c_src, fit_ref - c_ref
    E_src = np.linalg.eigh(xs.T @ xs / (len(xs) - 1))[1]
    E_ref = np.linalg.eigh(xr.T @ xr / (len(xr) - 1))[1]
    if np.linalg.det(E_src) * np.linalg.det(E_ref) < 0:
        E_src[:, 0] *= -1.0

    s0 = r_ref / r_src
    probe = fit_src[:1000]
    starts = []
    probes = []
    for G in _proper_rotations():
        R = E_ref @ G @ E_src.T
        t = c_ref - s0 * R @ c_src
        probes.append(s0 * probe @ R.T + t)
        starts.append((R, t))
    # 合并 24 组查询，减少线程创建 / GPU 启动与传输次数，候选和距离保持不变。
    d, _ = tree.query(np.concatenate(probes))
    errors = d.reshape(len(starts), len(probe)).mean(axis=1)
    starts = [(float(error), R, t) for error, (R, t) in zip(errors, starts)]
    starts.sort(key=lambda x: x[0])

    best = min(
        (_icp(fit_src[:2000], tree, fit_ref, s0, R, t, iters=15) for _, R, t in starts[:4]),
        key=lambda x: x[3],
    )
    s, R, t, _ = _icp(fit_src, tree, fit_ref, *best[:3], iters=60)
    return s, R, t


# ---------------- 相似度 ----------------

def mesh_similarity(
    reconstructed,
    reference,
    threshold: float = 0.01,
    n_points: int = 100_000,
    align_meshes: bool = True,
    seed: int = 0,
    return_details: bool = False,
    *,
    device: str = "auto",
):
    """重建模型与参考模型的形状相似度（F-score，取值 [0, 1]，越大越相似）。

    参数:
        reconstructed / reference: OBJ 路径、SpatialMesh、TriangleMesh、trimesh.Trimesh
            或 (顶点, 面) 元组；SpatialMesh 默认采用 original，确保采样顺序一致。
        threshold: 距离阈值 tau，取参考模型包围盒对角线长度的比例（默认 1%）
        n_points: 每个表面的采样点数，决定指标的统计精度
        align_meshes: 是否先做相似变换配准（SfM 重建在任意坐标系和尺度下，需要配准；
            两者已在同一坐标系时可关掉）
        return_details: 为 True 时额外返回精度、完整度、倒角距离与配准变换
        device: 'auto' 优先使用 CuPy CUDA，缺失时回退 CPU；'cpu' 强制 CPU；
            'cuda' 强制 GPU，不可用时报错。首次 GPU 调用有初始化 / 编译开销。

    返回:
        F-score；return_details=True 时返回 (F-score, 详情字典)。
    """
    _check_device(device)
    if n_points <= 0:
        raise ValueError("n_points 必须大于 0")
    if not np.isfinite(threshold) or threshold < 0:
        raise ValueError("threshold 必须是有限非负数")
    rec = np.asarray(_samples(reconstructed, n_points, seed))
    ref = np.asarray(_samples(reference, n_points, seed + 1))

    s, R, t = 1.0, np.eye(3, dtype=np.float32), np.zeros(3, dtype=np.float32)
    if align_meshes:
        s, R, t = align(rec, ref, seed=seed, device=device)
        rec = s * rec @ R.T + t

    diag = float(np.linalg.norm(ref.max(axis=0) - ref.min(axis=0)))
    if not np.isfinite(diag) or diag <= 0:
        raise ValueError("参考点云包围盒对角线必须为有限正数")
    tau = threshold * diag
    # 只返回 F-score 时，超过 tau 的精确距离没有用；详情模式仍查询完整距离。
    bound = np.inf if return_details else tau
    d_rec, _ = _NearestNeighbors(ref, device).query(rec, distance_upper_bound=bound)
    d_ref, _ = _NearestNeighbors(rec, device).query(ref, distance_upper_bound=bound)
    precision = float(np.mean(d_rec < tau))
    recall = float(np.mean(d_ref < tau))
    fscore = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
    if not return_details:
        return fscore
    return fscore, {
        "precision": precision,
        "recall": recall,
        "tau": tau,
        "chamfer": float((d_rec.mean() + d_ref.mean()) / 2 / diag),   # 以对角线长度归一化
        "scale": s,
        "rotation": R,
        "translation": t,
    }


if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(description="计算两个 OBJ 网格的形状相似度（F-score）")
    parser.add_argument("reconstructed", type=Path, help="重建得到的 OBJ")
    parser.add_argument("reference", type=Path, help="参考（原始）OBJ")
    parser.add_argument("--threshold", type=float, default=0.01, help="距离阈值，占参考包围盒对角线的比例")
    parser.add_argument("--points", type=int, default=100_000, help="每个表面的采样点数")
    parser.add_argument("--no-align", action="store_true", help="两个模型已在同一坐标系时跳过配准")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto",
                        help="最近邻计算设备（默认 auto，优先 CUDA）")
    args = parser.parse_args()

    t0 = time.perf_counter()
    score, info = mesh_similarity(args.reconstructed, args.reference, threshold=args.threshold,
                                  n_points=args.points, align_meshes=not args.no_align,
                                  return_details=True, device=args.device)
    print(f"F-score {score:.4f} (tau = {args.threshold:.1%} 对角线) | 精度 {info['precision']:.4f} "
          f"完整度 {info['recall']:.4f} | 倒角距离 {info['chamfer']:.5f} | 尺度 {info['scale']:.4f} "
          f"| 耗时 {time.perf_counter() - t0:.2f}s")
