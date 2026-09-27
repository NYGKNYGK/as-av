"""SpatialMesh 队列式 GPU 渲染：专用线程监听，固定网格缓存，GPU 光栅化。

外参 X_camera = R @ X_world + t；相机 +x 向右、+y 向下、+z 向前。
内参与分辨率每次从 config.camera_config 读取，仅支持零畸变。
初始化后请勿修改网格和树；修改后应重新创建渲染器。
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from queue import Queue
from threading import Lock, RLock, Thread
from time import perf_counter
from contextlib import nullcontext
import numpy as np
import torch

if not __package__:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import camera_config as camera
from src.config import gpu_render_config as config
from src.config.gpu_render_config import (
    MAX_FACES as _MAX_FACES, DEPTH_SCALE as _DEPTH_SCALE, EMPTY_KEY as _EMPTY_KEY,
)
from src.obj_reader import SpatialMesh, _validate


@dataclass(frozen=True)
class RenderRequest:
    """入队时复制数组。R/t 为世界到相机外参，light_dir 是世界系光传播方向。"""
    R: np.ndarray
    t: np.ndarray
    light_dir: np.ndarray
    request_id: object = None


@dataclass(frozen=True)
class RenderResult:
    """每项请求恰有一项结果；失败时 image=None，error 保存异常，队列继续工作。"""
    image: np.ndarray | None
    R: np.ndarray
    t: np.ndarray
    light_dir: np.ndarray
    request_id: object
    render_seconds: float
    error: Exception | None = None


class _InputLine(Queue):
    """只允许通过 put 入队；消费由所属渲染器完成。"""
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def put(self, item, block=True, timeout=None):
        if not isinstance(item, RenderRequest):
            raise TypeError("input_line.put 需要 RenderRequest(R, t, light_dir, request_id)")
        item = RenderRequest(*(np.array(a, dtype=np.float32, copy=True)
                               for a in (item.R, item.t, item.light_dir)), item.request_id)
        with self.owner._queue_lock:
            if self.owner._closed:
                raise RuntimeError("渲染队列已关闭")
            super().put(item, block, timeout)


def _resolve_device(device: str = config.DEVICE) -> torch.device:
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    selected = torch.device(device)
    if selected.type not in ("cpu", "cuda"):
        raise ValueError("device 必须是 auto、cpu 或 cuda[:编号]")
    if selected.type == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("未检测到可用 CUDA 设备")
        index = selected.index if selected.index is not None else torch.cuda.current_device()
        torch.cuda.get_device_properties(index)
        selected = torch.device("cuda", index)
    return selected


class GPURenderer:
    """复用原始网格张量，树的 face_ids 直接索引原始面，不生成第二套排序网格。"""

    def __init__(self, mesh: SpatialMesh, device: str = config.DEVICE):
        if not isinstance(mesh, SpatialMesh):
            raise TypeError("mesh 必须是 obj_reader.SpatialMesh")
        origin = mesh.origin_mesh
        _validate(origin)
        if not np.isfinite(origin.face_centers).all() or not np.isfinite(origin.face_normals).all():
            raise ValueError("面中心和法向必须有限")
        if len(origin.faces) >= _MAX_FACES:
            raise ValueError(f"面数必须小于 {_MAX_FACES}")
        self.device = _resolve_device(device)
        self.vertices = torch.as_tensor(origin.vertices, dtype=torch.float32, device=self.device)
        self.faces = torch.as_tensor(origin.faces, dtype=torch.int32, device=self.device)
        self.face_normals = torch.as_tensor(origin.face_normals, device=self.device)
        self.face_centers = torch.as_tensor(origin.face_centers, device=self.device)
        bounds = mesh.spacial_mesh_tree.bounds
        self.znear = max(config.NEAR_MIN, float(np.linalg.norm(bounds[1] - bounds[0])) * config.NEAR_SCALE)
        # 固定模型只遍历树一次。缓存叶块数组，逐帧使用向量化 AABB 测试。
        leaves = list(mesh.spacial_mesh_tree.iter_leaves())
        blocks = np.stack([leaf.bounds for leaf in leaves])
        self._block_centers = blocks.mean(axis=1)
        self._block_extents = (blocks[:, 1] - blocks[:, 0]) / 2
        self._block_sizes = torch.tensor([len(leaf.face_ids) for leaf in leaves], dtype=torch.int32, device=self.device)
        self._ordered_ids = torch.as_tensor(np.concatenate([leaf.face_ids for leaf in leaves]), dtype=torch.int32, device=self.device)
        self._all_ids = torch.arange(len(origin.faces), dtype=torch.int32, device=self.device)
        self._plane_offsets = (self.face_centers * self.face_normals).sum(dim=1)
        self._visibility_key = None
        self._zbuf = None
        self._render_lock = Lock()
        self._queue_lock = RLock()
        self._worker = None
        self._closed = False
        self.input_line = _InputLine(self)
        self.output_line = Queue()
        # 初始化与工作线程可能使用不同 CUDA stream；明确完成上传再交给队列。
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)
        self._stream = torch.cuda.Stream(device=self.device) if self.device.type == "cuda" else None

    def start(self):
        """启动后台监听并立即返回；空队列阻塞等待，重复调用不会创建额外线程。

        通过 submit(...) 或 input_line.put(RenderRequest(...)) 提交请求，
        从 output_line.get() 获取 RenderResult；使用完毕后调用 close()。
        """
        with self._queue_lock:
            if self._closed:
                raise RuntimeError("渲染队列已关闭")
            if self._worker is None:
                worker = Thread(target=self._listen, name="GPURenderer", daemon=True)
                worker.start()
                self._worker = worker

    def submit(self, R, t, light_dir, request_id=None):
        """提交请求；调用 start() 后开始消费，结果通过 output_line.get 获取。"""
        self.input_line.put(RenderRequest(R, t, light_dir, request_id))

    def _listen(self):
        while True:
            request = self.input_line.get()
            try:
                if request is None:
                    return
                started = perf_counter()
                image, error = None, None
                try:
                    image = self.render(request.R, request.t, request.light_dir)
                except Exception as exc:
                    error = exc
                self.output_line.put(RenderResult(image, request.R, request.t, request.light_dir,
                                                 request.request_id, perf_counter() - started, error))
            finally:
                self.input_line.task_done()

    def close(self):
        """拒绝新请求，等待已接收任务完成；已生成的 output_line 仍可读取。"""
        with self._queue_lock:
            if not self._closed:
                # 尚未 start 时也处理已接收的请求，避免 join 永久等待。
                if self._worker is None and not self.input_line.empty():
                    self.start()
                self._closed = True
                if self._worker is not None:
                    # 绕过公开入口的类型检查；哨兵排在所有已接收请求之后。
                    Queue.put(self.input_line, None)
            worker = self._worker
        if worker is not None:
            worker.join()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def _visible_faces(self, R, t, K, width, height):
        """对预缓存叶块批量粗筛；整模入镜时直接复用所有面编号。"""
        planes = np.stack((K[0], width * K[2] - K[0],
                           K[1], height * K[2] - K[1], K[2]))
        offsets = planes @ t
        planes = planes @ R
        absolute = np.abs(planes)

        radius = self._block_extents @ absolute.T
        support = self._block_centers @ planes.T + offsets + radius
        tolerance = np.finfo(np.float32).eps * config.FRUSTUM_EPS_MULTIPLIER * (
            np.abs(self._block_centers) @ absolute.T + np.abs(offsets) + radius + 1)
        visible = (support >= -tolerance).all(axis=1)
        if visible.all():
            return self._all_ids
        if not visible.any():
            return self._all_ids[:0]
        mask = torch.as_tensor(visible, device=self.device)
        return self._ordered_ids[torch.repeat_interleave(mask, self._block_sizes)]

    def render(self, R, t, light_dir, **kwargs):
        """同步接口；与队列共用缓存和互斥锁，避免同时改写深度缓冲。"""
        with self._render_lock:
            with torch.cuda.stream(self._stream) if self._stream is not None else nullcontext():
                return self._render(R, t, light_dir, **kwargs)

    @torch.no_grad()
    def _render(self, R, t, light_dir, *, ambient: float = config.AMBIENT,
                background: int = config.BACKGROUND, gray: bool = config.GRAY,
                cull_backfaces: bool = config.CULL_BACKFACES, max_entries: int | None = None) -> np.ndarray:
        """返回 uint8 (H,W,3)，gray=True 时为 (H,W)。

        R: 世界到相机的 (3,3) 旋转矩阵；t: (3,) 或 (3,1) 平移。
        相机世界位置为 -R.T @ t；light_dir 为世界系光线传播方向。
        跨近面的三角形整体丢弃；max_entries 为近似候选像素预算，单面不拆分。
        """
        R = np.asarray(R, dtype=np.float32)
        t = np.asarray(t, dtype=np.float32).reshape(-1)
        light = np.asarray(light_dir, dtype=np.float32).reshape(-1)
        if R.shape != (3, 3) or not np.isfinite(R).all():
            raise ValueError("R 必须是有限的 (3,3) 旋转矩阵")
        if not np.allclose(R @ R.T, np.eye(3, dtype=np.float32), atol=config.ROTATION_TOLERANCE) or not np.isclose(np.linalg.det(R), 1, atol=config.ROTATION_TOLERANCE):
            raise ValueError("R 必须正交且 det(R)=1")
        if t.shape != (3,) or not np.isfinite(t).all():
            raise ValueError("t 必须是有限的三维平移")
        if light.shape != (3,) or not np.isfinite(light).all() or np.linalg.norm(light) < config.VECTOR_EPSILON:
            raise ValueError("light_dir 必须是有限的非零三维方向")
        light = -light / np.linalg.norm(light)
        K = np.asarray(camera.K, dtype=np.float32)
        if (K.shape != (3, 3) or not np.isfinite(K).all()
                or not np.array_equal(K[2], [0, 0, 1]) or K[1, 0] != 0
                or K[0, 0] <= 0 or K[1, 1] <= 0):
            raise ValueError("camera.K 必须是正焦距的上三角针孔内参")
        if np.any(np.asarray(camera.DIST_COEFFS) != 0):
            raise ValueError("仅支持无畸变图像；camera.DIST_COEFFS 必须全零")
        resolution = camera.RESOLUTION
        if len(resolution) != 2 or any(isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, np.integer)) or x < 1 for x in resolution):
            raise ValueError("camera.RESOLUTION 必须为正整数 (宽,高)")
        width, height = map(int, resolution)
        if width * height >= config.INT32_MAX:
            raise ValueError("resolution exceeds int32 pixel indexing range")
        if not np.isfinite(ambient) or not 0 <= ambient <= 1:
            raise ValueError("ambient 必须在 [0,1] 内")
        if not isinstance(background, (int, np.integer)) or not 0 <= background <= 255:
            raise ValueError("background 必须是 [0,255] 内的整数")
        dev = self.device
        if max_entries is None:
            max_entries = (max(config.MIN_ENTRIES, min(config.GPU_MAX_ENTRIES, torch.cuda.mem_get_info(dev)[0] // config.BYTES_PER_ENTRY_BUDGET))
                           if dev.type == "cuda" else config.CPU_MAX_ENTRIES)
        if isinstance(max_entries, bool) or not isinstance(max_entries, (int, np.integer)) or not 1 <= max_entries < config.INT32_MAX:
            raise ValueError("max_entries 必须是正整数")
        key = (R.tobytes(), t.tobytes(), K.tobytes(), width, height, bool(cull_backfaces))
        if config.CACHE_VISIBILITY and key == self._visibility_key:
            return self._shade(self._zbuf, light, ambient, background, height, width, gray)
        self._visibility_key = None
        candidate_ids = self._visible_faces(R, t, K, width, height)
        if not candidate_ids.numel():
            return self._empty_image(height, width, background, gray)
        R_t = torch.as_tensor(R, device=dev)
        t_t = torch.as_tensor(t, device=dev)
        # 面平面常数已缓存：在收集三角形之前剔除背面，减少索引/投影临时数组。
        if cull_backfaces:
            eye = -R_t.T @ t_t
            facing = self.face_normals[candidate_ids] @ eye > self._plane_offsets[candidate_ids]
            candidate_ids = candidate_ids[facing]
        if not candidate_ids.numel():
            return self._empty_image(height, width, background, gray)
        cam = self.vertices @ R_t.T + t_t
        tri = cam[self.faces[candidate_ids]]
        keep = (tri[..., 2] > self.znear).all(dim=1)
        face_ids = candidate_ids[keep]
        if not face_ids.numel():
            return self._empty_image(height, width, background, gray)
        tri = tri[keep]
        z = tri[..., 2]
        projected = tri @ torch.as_tensor(K, device=dev).T
        u, v = projected[..., 0] / z, projected[..., 1] / z

        # 仅展开中心落入投影包围盒的像素，避免微小三角形多扩出两圈候选像素。
        x0 = torch.clamp(torch.ceil(u.amin(dim=1) - 0.5), 0, width - 1).to(torch.int32)
        x1 = torch.clamp(torch.floor(u.amax(dim=1) - 0.5), 0, width - 1).to(torch.int32)
        y0 = torch.clamp(torch.ceil(v.amin(dim=1) - 0.5), 0, height - 1).to(torch.int32)
        y1 = torch.clamp(torch.floor(v.amax(dim=1) - 0.5), 0, height - 1).to(torch.int32)
        bw, bh = x1 - x0 + 1, y1 - y0 + 1

        area = (u[:, 1] - u[:, 0]) * (v[:, 2] - v[:, 0]) - (u[:, 2] - u[:, 0]) * (v[:, 1] - v[:, 0])
        visible = (area.abs() > config.AREA_EPSILON) & (bw > 0) & (bh > 0)
        # 完全落在视口外的三角形：包围盒被钳制后仍需剔除
        visible &= (u.amax(dim=1) >= 0) & (u.amin(dim=1) < width)
        visible &= (v.amax(dim=1) >= 0) & (v.amin(dim=1) < height)
        if not bool(visible.any()):
            return self._empty_image(height, width, background, gray)

        idx = visible
        face_ids, z, u, v = face_ids[idx], z[idx], u[idx], v[idx]
        x0, y0, bw, bh, area = x0[idx], y0[idx], bw[idx], bh[idx], area[idx]

        zfar = float(z.amax())
        znear_f = float(z.amin())
        depth_span = max(zfar - znear_f, config.DEPTH_SPAN_MIN)

        if self._zbuf is None or self._zbuf[0].numel() != height * width:
            self._zbuf = tuple(torch.empty((height * width,), dtype=torch.int32, device=dev) for _ in range(2))
        zbuf = tuple(buffer.fill_(_EMPTY_KEY) for buffer in self._zbuf)
        counts = bw * bh
        starts = self._chunk_bounds(counts, max_entries)

        inv_z = 1.0 / z
        for lo, hi in starts:
            self._rasterize_chunk(
                zbuf, face_ids[lo:hi], u[lo:hi], v[lo:hi], inv_z[lo:hi], area[lo:hi],
                x0[lo:hi], y0[lo:hi], bw[lo:hi], counts[lo:hi],
                width, height, znear_f, depth_span,
            )
        self._visibility_key = key
        return self._shade(zbuf, light, ambient, background, height, width, gray)

    @staticmethod
    def _chunk_bounds(counts: torch.Tensor, max_entries: int):
        """按累计像素数把三角形切块，限制单次展开的显存占用。"""
        # 常见帧先验证累计上界，避免逐面将计数复制到 Python；绝不让 int32 累加溢出。
        if not counts.numel():
            return []
        if counts.numel() * int(counts.max()) < config.INT32_MAX:
            total = int(counts.sum(dtype=torch.int32))
            if total <= max_entries:
                return [(0, counts.numel())]
            cumulative = torch.cumsum(counts, dim=0, dtype=torch.int32)
            edges = torch.arange(max_entries, total, max_entries, dtype=torch.int32, device=counts.device)
            cuts = torch.searchsorted(cumulative, edges, out_int32=True).unique().tolist()
            points = [0] + [cut for cut in cuts if cut > 0] + [counts.numel()]
            return list(zip(points[:-1], points[1:]))
        # 极端整帧候选数使用 Python 整数累计，仍不分配 64 位张量。
        bounds, start, size = [], 0, 0
        values = counts.tolist()
        for i, count in enumerate(values):
            if not 0 <= count < config.INT32_MAX:
                raise ValueError("单面候选像素数超出 int32 范围")
            if size and size + count > max_entries:
                bounds.append((start, i))
                start, size = i, 0
            size += count
        if start < len(values):
            bounds.append((start, len(values)))
        return bounds

    @staticmethod
    def _rasterize_chunk(zbuf, face_ids, u, v, inv_z, area, x0, y0, bw, counts,
                         width, height, znear, depth_span):
        depthbuf, facebuf = zbuf
        dev = depthbuf.device
        n = int(counts.sum(dtype=torch.int32))
        tri_of = torch.repeat_interleave(torch.arange(counts.numel(), dtype=torch.int32, device=dev), counts, output_size=n)
        offset = torch.arange(n, dtype=torch.int32, device=dev) - (torch.cumsum(counts, dim=0, dtype=torch.int32) - counts)[tri_of]
        w_of = bw[tri_of]
        px = x0[tri_of] + offset % w_of
        py = y0[tri_of] + offset // w_of
        fx, fy_ = px.to(torch.float32) + 0.5, py.to(torch.float32) + 0.5

        u0, u1, u2 = u[tri_of, 0], u[tri_of, 1], u[tri_of, 2]
        v0, v1, v2 = v[tri_of, 0], v[tri_of, 1], v[tri_of, 2]
        w0 = (u1 - fx) * (v2 - fy_) - (u2 - fx) * (v1 - fy_)
        w1 = (u2 - fx) * (v0 - fy_) - (u0 - fx) * (v2 - fy_)
        w2 = (u0 - fx) * (v1 - fy_) - (u1 - fx) * (v0 - fy_)

        a = area[tri_of]
        sign = torch.sign(a)
        inside = (w0 * sign >= 0) & (w1 * sign >= 0) & (w2 * sign >= 0)
        if not bool(inside.any()):
            return

        tri_of, px, py = tri_of[inside], px[inside], py[inside]
        lam0, lam1, lam2 = (w0[inside] / a[inside], w1[inside] / a[inside], w2[inside] / a[inside])

        # 1/z 在屏幕空间线性插值，得到透视正确的深度
        iz = lam0 * inv_z[tri_of, 0] + lam1 * inv_z[tri_of, 1] + lam2 * inv_z[tri_of, 2]
        valid = iz > 0
        if not bool(valid.any()):
            return
        tri_of, px, py, iz = tri_of[valid], px[valid], py[valid], iz[valid]
        depth = 1.0 / iz

        zq = torch.clamp((depth - znear) / depth_span, 0.0, 1.0).to(torch.float32) * _DEPTH_SCALE
        zq = zq.to(torch.int32)
        pixels = py * width + px
        previous = depthbuf.clone()
        depthbuf.scatter_reduce_(0, pixels, zq, reduce="amin", include_self=True)
        # 更近的深度出现时清空旧面编号；同深度则保留较小面编号。
        facebuf.masked_fill_(depthbuf < previous, _EMPTY_KEY)
        winners = zq == depthbuf[pixels]
        facebuf.scatter_reduce_(0, pixels[winners], face_ids[tri_of[winners]],
                                reduce="amin", include_self=True)


    def _shade(self, zbuf, light, ambient, background, height, width, gray):
        _, facebuf = zbuf
        hit = facebuf != _EMPTY_KEY
        face_ids = torch.where(hit, facebuf, 0)
        # 像素数远少于模型面数时，仅计算命中像素对应的法向，避免对数百万面着色。
        to_light = torch.as_tensor(light, dtype=torch.float32, device=self.device)
        lambert = (self.face_normals[face_ids] @ to_light).clamp(0, 1)
        shade = (ambient + (1 - ambient) * lambert) * 255
        pixels = torch.where(hit, shade, float(background))
        image = pixels.to(torch.uint8).reshape(height, width).cpu().numpy()
        return image if gray else np.repeat(image[..., None], 3, axis=2)

    @staticmethod
    def _empty_image(height, width, background, gray):
        shape = (height, width) if gray else (height, width, 3)
        return np.full(shape, background, dtype=np.uint8)


def main():
    """python -m src.gpu_render --device cuda：从 dump 队列渲染 360 帧并保存/计时。"""
    import argparse
    import json
    import pickle
    def orbit_requests(mesh: SpatialMesh):
        """PCA 顶点长轴为轨道法向；轨道中心/相机注视点均为世界原点。"""
        vertices = mesh.origin_mesh.vertices
        points = vertices - vertices.mean(axis=0)
        _, axes = np.linalg.eigh(points.T @ points / len(points))
        axis = axes[:, -1].astype(np.float32)
        # 固定特征向量符号，使不同运行的轨道起点尽量一致。
        if axis[np.argmax(np.abs(axis))] < 0:
            axis = -axis
        reference = np.eye(3, dtype=np.float32)[np.argmin(np.abs(axis))]
        e1 = np.cross(axis, reference)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(axis, e1)
        K = np.asarray(camera.K, dtype=np.float32)
        width, height = camera.RESOLUTION
        planes = np.stack((K[0], width * K[2] - K[0], K[1], height * K[2] - K[1]))
        # 即便 fx != fy、主点偏移或 K 带 skew，也按最近侧平面的角度包住模型。
        if (planes[:, 2] <= 0).any():
            raise ValueError("环轨测试要求主点严格位于画面内部")
        half_angle = np.arcsin(planes[:, 2] / np.linalg.norm(planes, axis=1)).min()
        radius = float(np.linalg.norm(vertices, axis=1).max())
        distance = radius / np.sin(half_angle * config.ORBIT_FILL)
        light_angle = np.deg2rad(config.LIGHT_ANGLE_DEG)
        requests = []
        for i in range(config.ORBIT_VIEWS):
            angle = np.deg2rad(i * config.ORBIT_STEP_DEG)
            eye = (distance * (np.cos(angle) * e1 + np.sin(angle) * e2)).astype(np.float32)
            forward = -eye / np.linalg.norm(eye)
            right = np.cross(forward, axis)
            right /= np.linalg.norm(right)
            R = np.stack((right, np.cross(forward, right), forward))
            light = (np.cos(light_angle) * forward + np.sin(light_angle) * right).astype(np.float32)
            requests.append(RenderRequest(R, -R @ eye, light, i))
        return requests, axis, float(distance)


    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--device", default=config.DEVICE)
    parser.add_argument("--dump", type=Path, default=config.DEMO_DUMP)
    parser.add_argument("--output", type=Path, default=config.DEMO_OUTPUT)
    args = parser.parse_args()

    from PIL import Image
    started = perf_counter()
    with args.dump.open("rb") as stream:
        mesh = pickle.load(stream)
    if not isinstance(mesh, SpatialMesh):
        raise TypeError("dump 必须包含 src.obj_reader.SpatialMesh")
    load_seconds = perf_counter() - started
    stamp = perf_counter()
    requests, axis, radius = orbit_requests(mesh)
    orbit_seconds = perf_counter() - stamp
    stamp = perf_counter()
    renderer = GPURenderer(mesh, device=args.device)
    initialization_seconds = perf_counter() - stamp
    args.output.mkdir(parents=True, exist_ok=True)
    records = []

    def save(result):
        stamp = perf_counter()
        name = f"67p_orbit_{result.request_id:03d}.png"
        Image.fromarray(result.image).save(args.output / name, compress_level=config.PNG_COMPRESS_LEVEL)
        R, t = result.R, result.t
        eye = -R.T @ t
        angle = np.degrees(np.arccos(np.clip(np.dot(R[2], result.light_dir) /
                                           np.linalg.norm(result.light_dir), -1, 1)))
        return dict(index=result.request_id, file=name, R=R.tolist(), t=t.tolist(), eye=eye.tolist(),
                    light_dir=result.light_dir.tolist(), light_angle_deg=float(angle),
                    render_seconds=result.render_seconds, save_seconds=perf_counter() - stamp)

    # 预热单列计时，不混入 360 帧队列吞吐；清可见性键防止首帧命中预热缓存。
    stamp = perf_counter()
    renderer.render(requests[0].R, requests[0].t, requests[0].light_dir)
    warmup_seconds = perf_counter() - stamp
    renderer._visibility_key = None
    stamp = perf_counter()
    try:
        renderer.start()
        sent = 0
        while sent < min(config.MAX_IN_FLIGHT, len(requests)):
            renderer.input_line.put(requests[sent])
            sent += 1
        for completed in range(len(requests)):
            result = renderer.output_line.get()
            try:
                if result.error is not None:
                    raise RuntimeError(f"渲染帧 {result.request_id} 失败") from result.error
                records.append(save(result))
            finally:
                renderer.output_line.task_done()
            if sent < len(requests):
                renderer.input_line.put(requests[sent])
                sent += 1
            if (completed + 1) % config.PROGRESS_INTERVAL == 0:
                print(f"{completed + 1}/{len(requests)} rendered, {perf_counter() - stamp:.2f}s", flush=True)
    finally:
        renderer.close()
    pipeline_seconds = perf_counter() - stamp
    times = np.array([record["render_seconds"] for record in records])
    report = dict(dump=str(args.dump.resolve()), resolution=list(camera.RESOLUTION), K=camera.K.tolist(),
                  device=str(renderer.device), gpu=torch.cuda.get_device_name(renderer.device)
                  if renderer.device.type == "cuda" else None,
                  vertices=len(mesh.origin_mesh.vertices), faces=len(mesh.origin_mesh.faces),
                  frames=len(records),
                  orbit_axis=axis.tolist(), orbit_radius=radius, orbit_center=[0, 0, 0], target=[0, 0, 0],
                  orbit_step_deg=config.ORBIT_STEP_DEG, light_angle_deg=config.LIGHT_ANGLE_DEG,
                  load_seconds=load_seconds, orbit_setup_seconds=orbit_seconds,
                  initialization_seconds=initialization_seconds, warmup_seconds=warmup_seconds,
                  pipeline_seconds=pipeline_seconds, total_seconds=perf_counter() - started,
                  frames_per_second=len(records) / pipeline_seconds,
                  render_mean_seconds=float(times.mean()), render_p95_seconds=float(np.percentile(times, 95)),
                  render_sum_seconds=float(times.sum()), save_sum_seconds=sum(r["save_seconds"] for r in records),
                  timing_note="Render includes CPU work and GPU-to-CPU copy; pipeline includes sequential PNG saves. "
                  "Warmup and initialization excluded from pipeline. Save durations overlap rendering.",
                  frames_data=records)
    (args.output / "67p_orbit_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "frames_data"}, indent=2))


if __name__ == "__main__":
    main()
