"""读取原始 OBJ，再构建多线程二叉包围盒树。

read_obj(path) -> TriangleMesh；parse_mesh_to_tree(origin_mesh) -> SpatialMeshTree；
load_obj(path) -> SpatialMesh(origin_mesh, spacial_mesh_tree)。
几何为 float32，索引为 int32。按重心最长轴中位数二分，不裁切三角形，
所以子盒可以重叠，父盒完整包含子盒。修改原始几何后需重新建树。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import numpy as np

if __package__:
    from . import thread_pool
    from .config import obj_reader_config as config
else:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from src import thread_pool
    from src.config import obj_reader_config as config


@dataclass(slots=True)
class TriangleMesh:
    """原始顺序：(V,3) 顶点和 (F,3) 面、重心、法向。"""
    vertices: np.ndarray
    faces: np.ndarray
    face_centers: np.ndarray
    face_normals: np.ndarray


@dataclass(slots=True)
class SpatialMeshTree:
    """树节点。内部节点仅保存包围盒、子节点和划分平面。

    叶子 faces 为 int32 (N,3)，引用 origin_mesh.vertices；face_ids 为
    int32 (N,)，引用原始三角面编号。bounds 为 float32 (2,3)。
    空网格返回空叶子和全零包围盒，不表示存在几何。
    """
    bounds: np.ndarray
    left: SpatialMeshTree | None = None
    right: SpatialMeshTree | None = None
    faces: np.ndarray | None = None
    face_ids: np.ndarray | None = None
    split_axis: np.int32 = np.int32(-1)
    split_position: np.float32 = np.float32(0)

    @property
    def is_leaf(self) -> bool:
        return self.left is None and self.right is None

    def iter_leaves(self) -> Iterator[SpatialMeshTree]:
        stack = [self]
        while stack:
            node = stack.pop()
            if node.is_leaf:
                yield node
            else:
                stack.extend((node.right, node.left))


@dataclass(slots=True)
class SpatialMesh:
    """只保存原始模型和空间树，不再维护第二套扁平模型。"""
    origin_mesh: TriangleMesh
    spacial_mesh_tree: SpatialMeshTree


def _positive(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(f"{name} 必须是正整数")
    return int(value)


def _validate(mesh: TriangleMesh) -> None:
    vertices, faces = mesh.vertices, mesh.faces
    if vertices.dtype != np.float32 or vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError("vertices 必须为 float32 (V,3)")
    if faces.dtype != np.int32 or faces.ndim != 2 or faces.shape[1] != 3:
        raise ValueError("faces 必须为 int32 (F,3)")
    if max(len(vertices), len(faces)) > np.iinfo(np.int32).max:
        raise ValueError("网格规模超过 int32 范围")
    if not np.isfinite(vertices).all():
        raise ValueError("顶点必须有限")
    if faces.size and (faces.min() < 0 or faces.max() >= len(vertices)):
        raise ValueError("顶点索引越界")
    for array in (mesh.face_centers, mesh.face_normals):
        if array.dtype != np.float32 or array.shape != faces.shape:
            raise ValueError("重心和法向必须为 float32 (F,3)")


def read_obj(path: str | Path) -> TriangleMesh:
    """由 rapidobj 读取并三角化；预计算重心和法向，不重排面、不保存材质。"""
    from rapidobj import parse_obj

    path = Path(path)
    with path.open("rb"):
        pass
    result = parse_obj(str(path.resolve()))
    if not result.ok:
        raise ValueError(f"{path}: {result.error_message}")
    vertices = np.array(result.vertices, dtype=np.float32, copy=True, order="C")
    faces = np.array(result.faces, dtype=np.int32, copy=True, order="C")
    del result
    centers = np.empty(faces.shape, dtype=np.float32)
    normals = np.empty_like(centers)
    mesh = TriangleMesh(vertices, faces, centers, normals)
    _validate(mesh)
    batch = _positive(config.FACE_BATCH_SIZE, "FACE_BATCH_SIZE")
    parallel = len(faces) >= _positive(config.MIN_PARALLEL_FACES, "MIN_PARALLEL_FACES")

    def geometry(start):
        end = min(start + batch, len(faces))
        points = vertices[faces[start:end]]
        centers[start:end] = (points / np.float32(3)).sum(axis=1)
        edges = points[:, 1:] - points[:, :1]
        scale = np.abs(edges).max(axis=(1, 2), keepdims=True)
        np.divide(edges, scale, out=edges, where=scale != 0)
        cross = np.cross(edges[:, 0], edges[:, 1])
        lengths = np.linalg.norm(cross, axis=1, keepdims=True)
        normals[start:end] = np.divide(cross, lengths, out=np.zeros_like(cross), where=lengths != 0)

    thread_pool.run_tasks(geometry, range(0, len(faces), batch), parallel=parallel)
    if not np.isfinite(centers).all() or not np.isfinite(normals).all():
        raise ValueError("几何计算超出 float32 有限范围")
    return mesh


def parse_mesh_to_tree(origin_mesh: TriangleMesh) -> SpatialMeshTree:
    """按重心二分构建包围盒树；独立子树使用共享线程池并行处理。"""
    _validate(origin_mesh)
    if not np.isfinite(origin_mesh.face_centers).all() or not np.isfinite(origin_mesh.face_normals).all():
        raise ValueError("重心和法向必须有限")
    limit = _positive(config.MAX_FACES_PER_BLOCK, "MAX_FACES_PER_BLOCK")
    parallel_min = _positive(config.MIN_PARALLEL_FACES, "MIN_PARALLEL_FACES")
    partition_min = _positive(config.MIN_PARTITION_TASK_FACES, "MIN_PARTITION_TASK_FACES")
    count = len(origin_mesh.faces)
    order = np.arange(count, dtype=np.int32)
    root = SpatialMeshTree(np.zeros((2, 3), dtype=np.float32))
    parallel = count >= parallel_min and not thread_pool.in_worker_thread() and thread_pool.MAX_WORKERS > 1

    def split(task):
        node, start, end = task
        ids = order[start:end]
        points = origin_mesh.face_centers[ids]
        axis = int(np.argmax(points.max(axis=0) / np.float32(2) - points.min(axis=0) / np.float32(2)))
        mid = (end - start) // 2
        permutation = np.argpartition(points[:, axis], mid).astype(np.int32)
        order[start:end] = ids[permutation]
        node.split_axis = np.int32(axis)
        node.split_position = np.float32(points[permutation[mid], axis])
        node.left = SpatialMeshTree(np.empty((2, 3), dtype=np.float32))
        node.right = SpatialMeshTree(np.empty((2, 3), dtype=np.float32))
        return (node.left, start, start + mid), (node.right, start + mid, end)

    def merge(node):
        node.bounds[0] = np.minimum(node.left.bounds[0], node.right.bounds[0])
        node.bounds[1] = np.maximum(node.left.bounds[1], node.right.bounds[1])

    def build(task):
        node, start, end = task
        if end - start <= limit:
            node.face_ids = order[start:end].copy()
            node.faces = origin_mesh.faces[node.face_ids]
            if end > start:
                points = origin_mesh.vertices[node.faces]
                node.bounds[0] = points.min(axis=(0, 1))
                node.bounds[1] = points.max(axis=(0, 1))
            return
        left, right = split(task)
        build(left)
        build(right)
        merge(node)

    frontier = [(root, 0, count)]
    parents = []
    while parallel and len(frontier) < thread_pool.MAX_WORKERS:
        eligible = [task for task in frontier if task[2] - task[1] > max(limit, partition_min)]
        if not eligible:
            break
        results = thread_pool.run_tasks(split, eligible)
        children = {id(task[0]): pair for task, pair in zip(eligible, results)}
        parents.extend(task[0] for task in eligible)
        frontier = [child for task in frontier for child in children.get(id(task[0]), (task,))]
    thread_pool.run_tasks(build, frontier, parallel=parallel)
    for node in reversed(parents):
        merge(node)
    return root


def load_obj(path: str | Path) -> SpatialMesh:
    """读取路径，返回包含原始网格和空间树的最终模型。"""
    origin_mesh = read_obj(path)
    return SpatialMesh(origin_mesh, parse_mesh_to_tree(origin_mesh))


def main() -> None:
    """测试新结构、统计时间，并替换 test/dump 中对应模型的 dump。"""
    import argparse
    import json
    import pickle
    from importlib import import_module
    from time import perf_counter

    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("obj", nargs="?", type=Path, default=root / "models/67p.obj")
    args = parser.parse_args()
    reader = import_module("src.obj_reader")
    started = perf_counter()
    origin = reader.read_obj(args.obj)
    read_seconds = perf_counter() - started
    started = perf_counter()
    tree = reader.parse_mesh_to_tree(origin)
    tree_seconds = perf_counter() - started
    mesh = reader.SpatialMesh(origin, tree)

    def validate(model):
        original = model.origin_mesh
        reader._validate(original)
        seen = np.zeros(len(original.faces), dtype=np.int32)
        stack = [model.spacial_mesh_tree]
        nodes = leaves = largest = 0
        while stack:
            node = stack.pop()
            nodes += 1
            assert node.bounds.dtype == np.float32 and np.isfinite(node.bounds).all()
            if node.is_leaf:
                leaves += 1
                largest = max(largest, len(node.faces))
                assert node.faces.dtype == node.face_ids.dtype == np.int32
                assert len(node.faces) <= config.MAX_FACES_PER_BLOCK
                np.testing.assert_array_equal(node.faces, original.faces[node.face_ids])
                np.add.at(seen, node.face_ids, 1)
                if len(node.faces):
                    points = original.vertices[node.faces]
                    np.testing.assert_array_equal(node.bounds[0], points.min(axis=(0, 1)))
                    np.testing.assert_array_equal(node.bounds[1], points.max(axis=(0, 1)))
            else:
                assert node.faces is None and node.face_ids is None
                assert node.left is not None and node.right is not None
                for child in (node.left, node.right):
                    assert (node.bounds[0] <= child.bounds[0]).all()
                    assert (node.bounds[1] >= child.bounds[1]).all()
                    stack.append(child)
        assert (seen == 1).all()
        return nodes, leaves, largest

    nodes, leaves, largest = validate(mesh)
    output = root / "test/dump"
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"{args.obj.stem}_read.dump"
    temporary = target.with_suffix(".dump.tmp")
    try:
        started = perf_counter()
        with temporary.open("wb") as stream:
            pickle.dump(mesh, stream, protocol=5)
        dump_seconds = perf_counter() - started
        with temporary.open("rb") as stream:
            restored = pickle.load(stream)
        assert validate(restored) == (nodes, leaves, largest)
        for name in ("vertices", "faces", "face_centers", "face_normals"):
            np.testing.assert_array_equal(getattr(origin, name), getattr(restored.origin_mesh, name))
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    report = dict(model=str(args.obj.resolve()), vertices=len(origin.vertices), faces=len(origin.faces),
                  nodes=nodes, leaves=leaves, largest_leaf=largest, read_seconds=read_seconds,
                  tree_seconds=tree_seconds, total_seconds=read_seconds + tree_seconds,
                  dump_seconds=dump_seconds, dump_bytes=target.stat().st_size,
                  float_dtype="float32", index_dtype="int32", validation="passed",
                  timing_note="Single run; OS cache not flushed; validation and dump excluded from total.")
    target.with_name(f"{args.obj.stem}_read_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"已替换 {target}")


if __name__ == "__main__":
    main()
