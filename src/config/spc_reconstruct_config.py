"""SPCModel 的默认参数；修改后重新启动 Python 进程。

容量和批大小可以按机器内存调整。数组维度、坐标约定和磁盘数据类型属于
数据格式，留在 spc_reconstruct.py 中，不作为可调超参数。
"""
from pathlib import Path

# 以源码位置定位项目根目录，不受启动程序时的工作目录影响。
# 每个 SPCModel 自动创建 MODEL_ROOT/<UUID>/，其下 images/ 存放照片。
MODEL_ROOT = Path(__file__).resolve().parents[2] / 'spc_models'

# LRU 持有的照片像素和掩码预算，单位字节；0 表示全部使用只读内存映射。
# 不包含外部引用、操作系统页面缓存、相机表、地形和观测索引。
IMAGE_CACHE_BYTES = 256 * 1024 * 1024
# Windows 上文件短暂占用时，原子替换图片清单的重试次数和初始间隔。
MANIFEST_REPLACE_RETRIES = 4
MANIFEST_REPLACE_DELAY = 0.025

# OBJ 每批最多写出的顶点/三角面行数，至少为 2。
OBJ_CHUNK_SIZE = 65536
# Maplet -> 闭合曲面：Screened Poisson 最大八叉树深度及工作线程数。
OBJ_FUSION_DEPTH = 8
OBJ_FUSION_THREADS = 4
# 用半个典型节点间距的体素合并重叠点；法向分组避免混合相反表面层。
OBJ_FUSION_VOXEL_RATIO = 0.5
OBJ_FUSION_POINT_WEIGHT = 4.0
# 高程转三维坐标时每批的采样点预算；每批至少处理一个完整 Maplet。
BODY_POINTS_CHUNK_SIZE = 262144

# 未提供初值时使用的网格间距（米）和反照率；地形仍默认无效。
DEFAULT_SPACING = 1.0
DEFAULT_ALBEDO = 1.0

# OBJ -> Maplet：面积采样选中心，法向投影采样局部连通表面。
OBJ_MAPLET_SIDE = 17  # 奇数，保证块中心是一个高程节点
OBJ_TARGET_MAPLETS = 128  # 未指定 spacing 时用于估计初始间距，并非强制块数
OBJ_MAX_MAPLETS = 512
OBJ_SEED_SAMPLES = 16384
OBJ_MAPLET_OVERLAP = 0.25  # 选中心时预留的线性重叠比例
OBJ_MIN_NORMAL_COSINE = 0.25  # 排除背面和相对参考平面过陡的三角面
OBJ_HEIGHT_EXTENT_RATIO = 1.0  # 法向搜索半深度 / Maplet 半宽
OBJ_QUERY_BATCH = 32768  # 每批空间查询的三角面数，限制候选列表及几何临时内存
OBJ_QUERY_PAIR_BUDGET = 1_048_576  # 大面覆盖所有查询点时，一批最多展开的候选配对数
OBJ_OVERLAP_HEIGHT_TOLERANCE = 0.25  # 判断两个离散高程面相符的间距倍数

# ---------- 固定相机参数下的局部 SPC ----------
# Lunar-Lambert 混合系数：0 为纯 Lambert，1 为 Lommel-Seeliger。
# 这是待标定的反射模型参数，需与输入照片的辐射模型一致。
LUNAR_LAMBERT_WEIGHT = 0.5
# 合成数据若已知反照率，可以固定它，只估计两个坡度分量。
FIT_ALBEDO = True
# 当前 gpu_render 只计算局部 Lambert 明暗，没有投影阴影；该测试关闭太阳射线检测。
# 真实图像默认仍检查投影阴影，相机遮挡检测不受此开关影响。
CAST_SHADOWS = True
# 线性 RGB 转灰度；输入已经是灰度时不使用。
RGB_LUMINANCE_WEIGHTS = (0.2126, 0.7152, 0.0722)
UPDATE_OUTER_ITERATIONS = 3
PHOTOMETRIC_ITERATIONS = 8
MAX_IMAGES_PER_MAPLET = 12
MIN_PHOTOMETRIC_IMAGES = 3
MIN_UPDATE_POINTS = 9
MIN_OBSERVATION_COVERAGE = 0.1
# cos(最大入射/出射角)，避免掠射面造成不稳定解。
MIN_ILLUMINATION_COSINE = 0.1
GEOMETRY_DUPLICATE_COSINE = 0.99996
MAX_IMAGE_GSD_RATIO = 4.0
PHOTOMETRIC_NOISE = 0.02  # 归一化线性灰度中的噪声尺度
HUBER_SIGMA = 2.0
PHOTOMETRIC_DAMPING = 1e-3
MIN_INFORMATION_RATIO = 1e-4
CONFIDENCE_INFORMATION_RATIO = 0.03
CONFIDENCE_IMAGE_COUNT = 5.0
PRIOR_ANCHOR_CONFIDENCE = 0.25
MAX_SLOPE = 5.0
MAX_SLOPE_STEP = 0.3
MAX_LOG_ALBEDO_STEP = 0.3
LINE_SEARCH_STEPS = 5
# 在实际重投影/积分后检查下降；单次候选最多移动一个网格间距。
MAX_HEIGHT_STEP_SPACING = 1.0
HEIGHT_COST_MIN_IMPROVEMENT = 1e-6
NUMERICAL_EPSILON = 1e-6

# 立体匹配：沿 Maplet 法向移动整块，在多视图中搜索纹理相关峰。
STEREO_SEARCH_SPACING = 2.0
STEREO_SEARCH_SAMPLES = 17  # 奇数，包含零偏移
STEREO_MIN_POINTS = 16
STEREO_MIN_ANGLE_DEG = 2.0
STEREO_MIN_TEXTURE = 0.01
STEREO_MIN_CORRELATION = 0.6
STEREO_MIN_PEAK_CURVATURE = 1e-4

# 已知反照率时，通过跨图光度一致性同时估计点高程和法向。
# 法向可在格点内变化，避免粗网格差分强行拟合未解析的微地形明暗。
DEPTH_SEARCH_SPACING = 0.5
DEPTH_SEARCH_SAMPLES = 17
MIN_DEPTH_IMAGES = 4
DEPTH_PRIOR_SPACING = 0.1  # 持久初始高程先验的标准差，以当前网格间距为单位
DEPTH_MIN_IMPROVEMENT = 0.05  # 以光度噪声方差为单位
DEPTH_MIN_CURVATURE = 0.01

# 坡度积分：弱先验避免无观测区域漂移，中心/重叠点提供高度基准。
INTEGRATION_PRIOR_WEIGHT = 1e-4
# 无可靠坡度的节点保留当前几何，不能充当自由变量来帮助其他节点拟合。
INTEGRATION_UNOBSERVED_WEIGHT = 1.0
MIN_SLOPE_QUALITY = 0.05
INTEGRATION_ANCHOR_WEIGHT = 10.0
INTEGRATION_OVERLAP_WEIGHT = 1.0
INTEGRATION_ITERATIONS = 150
INTEGRATION_TOLERANCE = 1e-5

# 图像支持更细地形时，将一个活动块四等分；子块保持行列数并拟合局部参考法向。
# 平坦区域间距减半，倾斜区域根据新切平面上的覆盖范围调整实际间距。
# 覆盖率按父块有效节点计算，允许局部观测触发拆分。每次 update 最多拆一层。
SPLIT_PIXELS_PER_SAMPLE = 2.0  # 拆分后的点间距至少对应这么多像素
SPLIT_MIN_COVERAGE = 0.25
SPLIT_MIN_POINTS = 4
MAX_SPLIT_DEPTH = 6
MAX_SPLITS_PER_UPDATE = 16
SPLIT_REPROJECT_ITERATIONS = 16  # 新法向射线与父高程面的求交迭代上限
SPLIT_REPROJECT_TOLERANCE = 1e-4  # 相对父块间距的求交/坐标匹配容差
MAX_MAPLETS = 16384  # 含保留编号的非活动父块
MAX_TOTAL_SAMPLES = 2_000_000

# 当前地形的 BVH 光线检测：同时排除相机遮挡和投影阴影。
RAY_LEAF_TRIANGLES = 32
RAY_BATCH_SIZE = 256
RAY_OFFSET_SPACING = 1e-4
