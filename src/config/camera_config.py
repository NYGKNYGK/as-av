"""OSIRIS-REx PolyCam 的针孔相机内参（详细测绘约 3.7 km 对焦档位）。

标定值来自 Golish 等人的 OCAMS 在轨标定论文表 7a：
https://ntrs.nasa.gov/citations/20210011481

该模块供 gpu_render 使用。渲染器仅支持零畸变，所以 K 对应已去畸变的
1024×1024 图像；原始 PolyCam 图像的畸变须在输入前按对焦档位校正。
"""

import math

import numpy as np


# PolyCam 有效成像区域与像素间距。
WIDTH = 1024
HEIGHT = 1024
RESOLUTION = (WIDTH, HEIGHT)
PIXEL_PITCH_MM = 0.0085

# 3.7 km 对焦档位（电机位置 16650）；其他档位应使用该图像对应的焦距。
FOCUS_DISTANCE_M = 3700.0
FOCUS_MOTOR_POSITION = 16650
FOCAL_LENGTH_MM = 628.21
FX = FOCAL_LENGTH_MM / PIXEL_PITCH_MM
FY = FX

# SPICE 仪器核中，1024×1024 有效图像的名义中心，按 0 起始像素坐标表示。
CX = (WIDTH - 1) / 2.0
CY = (HEIGHT - 1) / 2.0
FOV_DEG = math.degrees(2.0 * math.atan(HEIGHT * PIXEL_PITCH_MM / (2.0 * FOCAL_LENGTH_MM)))

# 同一对焦档位的实测径向畸变。rho 与 delta_rho 均以 mm 为单位：
# delta_rho = p1*rho + p2*rho**2 + p3*rho**3。
# 畸变中心不同于上述名义图像中心；这组系数不能直接填入 OpenCV 的 k1/k2/k3。
DISTORTION_CENTER_PX = (511.5, 502.0)
RADIAL_DISTORTION_COEFFS_MM = (0.0, 5.97e-5, 3.19e-5)

K = np.array([
    [FX, 0.0, CX],
    [0.0, FY, CY],
    [0.0, 0.0, 1.0],
], dtype=np.float32)

# OpenCV 顺序 (k1, k2, p1, p2, k3)。零值表示输入已去畸变，
# 并不表示 PolyCam 原始图像没有镜头畸变。
DIST_COEFFS = np.zeros(5, dtype=np.float32)
