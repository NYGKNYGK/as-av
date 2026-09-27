"""OBJ 读取与空间分块参数；修改默认值后重新启动 Python 进程。

parse_mesh_to_tree 使用 MAX_FACES_PER_BLOCK 作为叶节点的面数上限。
OBJ 调度阈值在本文件中；共享线程池容量位于 thread_pool_config.py。
rapidobj 的线程由库自行管理。
"""


# 包围盒内的三角面超过此数量时，继续二分；不是空间尺寸阈值。
MAX_FACES_PER_BLOCK = 1024

# 几何计算每批三角面数，不是线程池容量。
FACE_BATCH_SIZE = 65536

# 小模型直接在调用线程计算，不向共享池提交任务。
MIN_PARALLEL_FACES = 131072

# 只将足够大的子树分派给线程池，小子树在工作线程内继续划分。
MIN_PARTITION_TASK_FACES = 32768
