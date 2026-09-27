"""GPU 渲染器的已验证默认配置（32 位版本）。

修改后重启渲染进程生效。相机内参/分辨率在 camera.py 中设置，
全局线程池容量在 thread_pool_config.py 中设置。
"""
from pathlib import Path

# 设备选择；auto 优先 CUDA，不可用时回退 CPU。
DEVICE = "auto"

# ---------- 缓冲格式：需与渲染器及 SPC 深度解码一致 ----------
# 深度与面编号分开存入两个 int32 缓冲，保留原来的 24 位深度精度。
ID_BITS = 24
MAX_FACES = 1 << ID_BITS
DEPTH_SCALE = float((1 << 24) - 1)
INT32_MAX = (1 << 31) - 1
EMPTY_KEY = INT32_MAX  # 空像素哨兵，严格大于所有有效深度与面编号。

# ---------- 几何精度 ----------
# 几何/数值容差；近面取绝对下限与模型包围盒对角线相对值的较大者。
NEAR_MIN = 1e-6
NEAR_SCALE = 1e-5
ROTATION_TOLERANCE = 1e-4
VECTOR_EPSILON = 1e-12
AREA_EPSILON = 1e-12
DEPTH_SPAN_MIN = 1e-9
FRUSTUM_EPS_MULTIPLIER = 16

# ---------- 图像外观 ----------
# 默认着色：单个平行光 + 环境光，三通道输出实际为相同灰度。
AMBIENT = 0.15
BACKGROUND = 0
GRAY = False
CULL_BACKFACES = True

# ---------- 显存预算与缓存 ----------
# 候选像素分批预算；不是严格显存上限，单个三角形包围盒不拆分。
CPU_MAX_ENTRIES = 1 << 20
GPU_MAX_ENTRIES = 1 << 22
MIN_ENTRIES = 1024
BYTES_PER_ENTRY_BUDGET = 1024
# 仅缓存最近一组相机的 z-buffer；改光照不重新光栅化。
CACHE_VISIBILITY = True

# ---------- 队列演示的在途任务窗口 ----------
# 队列故意不设容量，避免无人消费 output 时占住共享池线程。
# 大批任务由调用者限制在途数；main 用下面的窗口控制图片内存占用。
MAX_IN_FLIGHT = 8

# ---------- main() 环轨测试 ----------
# 演示路径与轨道：以原点为中心，平面法向为顶点 PCA 长轴。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_DUMP = PROJECT_ROOT / "test/dump/67p_read.dump"
DEMO_OUTPUT = PROJECT_ROOT / "test/imgs"
ORBIT_VIEWS = 360
ORBIT_STEP_DEG = 1.0
LIGHT_ANGLE_DEG = 45.0
# 使用最小半视场角的 85% 确定距离，保证以原点为中心的包围球完整入镜。
ORBIT_FILL = 0.85
PNG_COMPRESS_LEVEL = 1
# 每完成多少张图片输出一次进度；必须大于 0。
PROGRESS_INTERVAL = 30
