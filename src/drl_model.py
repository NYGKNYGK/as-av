"""面向 SPC 的纯观测预测网络，依赖 numpy、torch。

输入：零相位三角面、惯性系候选相机位置、候选自转相位、固定平行光方向、
相机内参及可选时刻。模型联合选择相机位置和自转相位，不单独回归连续角度。
forward 输出每个候选和 STOP 的 logits，可由后续训练代码直接使用。
predict 反复调用网络，记录已选候选，直到 STOP 或数量上限，返回变长观测集合。
不包含环境、奖励、优化器、训练循环或 SPC 重建调用。没有预训练权重。

小天体绕通过 spin_center 的 z 轴旋转，+x 为零相位，右手定则，角度 [0,2π)。
零相位时本体系与惯性系重合，spin_center 默认为 OBJ 原点，不是局部块中心。
太阳方向是惯性系固定的表面指向光源方向。相机位置与朝向也在惯性系中；
本体系的等效外参和太阳方向根据自转计算，不能将变化的本体系外参当作相机移动。
输出 rotation_angles 和两套外参。渲染原始未旋转 OBJ 时使用 body_* 字段，
不要再旋转 OBJ，否则会重复施加自转。渲染器 light_dir 与指向太阳方向相反。
相位不是完整时间：未提供 times 时可等待后续周期到达选中相位，不能据此
确定等待时长/圈数；提供 times 时由调用方保证时刻与自转周期一致。
movement_weight 是推理时平移距离的评分惩罚，不是强化学习奖励；不保证全局最优。
valid_mask 由外部提供可行性判断；本网络不做遮挡、视场、光照质量或碰撞检查。
SPC 建模效果需要后续训练和重建验证，随机初始化输出仅用于接口验证。

示例::
    from src.drl_model import DRLModel, block_triangles, rotation_candidates
    # triangles = block_triangles(mesh, block_id)
    # model = DRLModel().to('cuda')
    # positions, angles = rotation_candidates([[10., 0., 0.]], num_phases=36)
    # fixed_sun = [1., 1., 0.5]  # 惯性系固定平行光方向
    # output = model(triangles, positions, fixed_sun, rotation_angles=angles,
    #                K=K, resolution=(width,height))
    # output.logits: (M+1,)，最后一项是 STOP；output.probabilities 为动作概率
    # plan = model.predict(triangles, positions, fixed_sun, K=K,
    #                      resolution=(width,height), max_views=12,
    #                      rotation_angles=angles, current_position=[10.,0.,0.],
    #                      max_camera_step=0)  # 固定相机位置，等待小天体自转
    # phases = plan.rotation_angles  # 每次观测的小天体自转弧度
    # for R, t, sun in zip(plan.body_rotations, plan.body_translations, plan.body_sun_directions):
    #     image = renderer.render(R, t, light_dir=-sun)
    # model.save('models/predictor.pt')
    # model = DRLModel.load('models/predictor.pt')

直接运行 python src/drl_model.py 执行 main 中的前向/推理自检，不训练。
自转预测结构需要 v3 权重，与旧版预测模型不兼容。
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import NamedTuple
import math

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


def _positive_int(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < 1:
        raise ValueError(f'{name} 必须是正整数')
    return int(value)


def block_triangles(mesh, block_id: int) -> np.ndarray:
    """提取 obj_reader.SpatialMesh 指定叶块的全部三角面。"""
    if isinstance(block_id, bool) or not isinstance(block_id, Integral) or block_id < 0:
        raise ValueError('block_id 必须是非负整数')
    for i, leaf in enumerate(mesh.spacial_mesh_tree.iter_leaves()):
        if i == block_id:
            return mesh.origin_mesh.vertices[leaf.faces].copy()
    raise ValueError('block_id 越界')


def rotation_candidates(positions, num_phases=36):
    """展开惯性系相机位置与均匀自转相位的笛卡尔积，不执行运动规划。

    positions: (C,3)，即使只给一个固定相机位置也能得到不同相位的观测。
    返回 expanded_positions (C*num_phases,3)、angles (C*num_phases,)。
    角度从 +x 起按右手定则绕 z 轴旋转，采用 [0,2π)，不重复 2π。
    """
    positions = np.asarray(positions, dtype=np.float64)
    if positions.ndim != 2 or positions.shape[1] != 3 or not len(positions) or not np.isfinite(positions).all():
        raise ValueError('positions 必须为非空有限的 (C,3) 数组')
    count = _positive_int(num_phases, 'num_phases')
    phases = np.arange(count, dtype=np.float64) * (2 * math.pi / count)
    return np.repeat(positions, count, axis=0), np.tile(phases, len(positions))


def _rotation_z(angles):
    c, s = angles.cos(), angles.sin()
    zero, one = torch.zeros_like(c), torch.ones_like(c)
    return torch.stack((c, -s, zero, s, c, zero, zero, zero, one), dim=-1).reshape(-1, 3, 3)


def _look_at(positions, targets):
    forward = F.normalize(targets - positions, dim=-1)
    up = torch.zeros_like(forward)
    up[:, 2] = 1
    up[forward[:, 2].abs() > .95] = up.new_tensor([0, 1, 0])
    right = F.normalize(torch.linalg.cross(forward, up), dim=-1)
    down = torch.linalg.cross(forward, right)
    rotation = torch.stack((right, down, forward), dim=1)
    return rotation, -torch.einsum('mij,mj->mi', rotation, positions)


class PredictionOutput(NamedTuple):
    """单场景 M 个候选加一个 STOP；logits 保留梯度供未来训练使用。"""
    logits: torch.Tensor
    action_mask: torch.Tensor

    @property
    def probabilities(self):
        return self.logits.softmax(dim=-1)


@dataclass(frozen=True)
class ObservationPlan:
    """按选择顺序返回新观测，允许空结果。

    positions/targets/rotations/translations/sun_directions 均在惯性系。
    rotation_angles 为小天体绕 z 轴的自转相位 (N,)，[0,2π) 弧度。
    body_* 是用于原始未旋转 OBJ/SPC 的等效本体系外参与太阳方向；
    外参均满足 X_camera=R@X+t。spin_center 为惯性系中固定的轴上点。
    """
    indices: np.ndarray
    positions: np.ndarray
    targets: np.ndarray
    rotations: np.ndarray
    translations: np.ndarray
    sun_directions: np.ndarray
    rotation_angles: np.ndarray
    body_rotations: np.ndarray
    body_translations: np.ndarray
    body_sun_directions: np.ndarray
    spin_center: np.ndarray
    times: np.ndarray | None
    stop_reason: str


class DRLModel(nn.Module):
    """共享几何/候选 MLP + 集合池化 + 观测评分头与 STOP 头。

    保留 DRLModel 类名方便后续接入训练；本类只有预测能力，没有 Critic。
    不同面数和候选数共用权重。forward 一次处理一个场景，不要求面排序。
    候选特征为本体系位置3/朝向3/太阳方向3、惯性系位置3、
    自转 sin/cos 2、时间1、已选标记1、惯性系移动距离1，共17维。
    上下文包含面/候选 max+mean 池化、已选候选 mean、相机及数量信息。
    """

    def __init__(self, hidden_dim=128):
        super().__init__()
        self.hidden_dim = _positive_int(hidden_dim, 'hidden_dim')
        h = self.hidden_dim
        self.face_encoder = nn.Sequential(nn.Linear(10, h), nn.ReLU(), nn.Linear(h, h), nn.ReLU())
        self.candidate_encoder = nn.Sequential(nn.Linear(17, h), nn.ReLU(), nn.Linear(h, h), nn.ReLU())
        self.context = nn.Sequential(nn.Linear(5*h + 8, h), nn.ReLU())
        self.view_head = nn.Sequential(nn.Linear(2*h, h), nn.ReLU(), nn.Linear(h, 1))
        self.stop_head = nn.Linear(h, 1)

    def _prepare(self, triangles, positions, sun_directions, *, K, resolution,
                 targets=None, times=None, selected_mask=None, valid_mask=None, max_views=None,
                 rotation_angles=None, spin_center=(0., 0., 0.), current_position=None,
                 movement_weight=1., max_camera_step=None):
        parameter = next(self.parameters())

        def array(value, name, shape):
            value = torch.as_tensor(value, dtype=parameter.dtype, device=parameter.device)
            if value.ndim != len(shape) or any(s is not None and s != n for s, n in zip(shape, value.shape)):
                raise ValueError(f'{name} 形状必须为 {shape}')
            if not bool(torch.isfinite(value).all()):
                raise ValueError(f'{name} 必须全部有限')
            return value

        def unit(value, name):
            length = torch.linalg.vector_norm(value, dim=-1, keepdim=True)
            if bool((length <= 1e-12).any()):
                raise ValueError(f'{name} 不能为零向量')
            return value / length

        tri = array(triangles, 'triangles', (None, 3, 3))
        if not len(tri):
            raise ValueError('三角面不能为空')
        lo, hi = tri.amin((0, 1)), tri.amax((0, 1))
        center = lo / 2 + hi / 2
        radius = torch.linalg.vector_norm(hi / 2 - lo / 2)
        if not bool(torch.isfinite(radius)) or radius <= 0:
            raise ValueError('包围盒必须具有有限的非零尺寸')
        tri = (tri - center) / radius
        cross = torch.linalg.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        area2 = torch.linalg.vector_norm(cross, dim=-1, keepdim=True)
        if not bool((area2 > 1e-8).any()):
            raise ValueError('不能全部为退化三角面')
        lengths = torch.linalg.vector_norm(tri - tri.roll(1, dims=1), dim=-1).sort(dim=-1).values
        geometry = torch.cat((tri.mean(1), F.normalize(cross, dim=-1, eps=1e-8), area2 / 2, lengths), dim=-1)
        positions = array(positions, 'positions', (None, 3))
        m = len(positions)
        if not m:
            raise ValueError('候选观测不能为空')
        # 固定惯性系平行光。允许同方向的兼容 (M,3) 输入，但不能逐帧改变方向。
        light = torch.as_tensor(sun_directions, dtype=parameter.dtype, device=parameter.device)
        if light.shape == (3,):
            light = light.expand(m, -1)
        suns = unit(array(light, 'sun_directions', (m, 3)), 'sun_directions')
        if not torch.allclose(suns, suns[:1].expand_as(suns), atol=1e-6, rtol=1e-6):
            raise ValueError('平行光在惯性系中的方向必须固定，请传 (3,) 向量')
        # 相位保留 float64，避免将接近 2π 的输出舍入为区间外值。
        angles = (torch.zeros(m, dtype=torch.float64, device=parameter.device) if rotation_angles is None else
                  torch.as_tensor(rotation_angles, dtype=torch.float64, device=parameter.device))
        if (angles.shape != (m,) or not bool(torch.isfinite(angles).all())
                or bool(((angles < 0) | (angles > 2 * math.pi)).any())):
            raise ValueError('rotation_angles 必须为 (M,) 且位于 [0,2π]，2π 归一化为 0')
        angles = angles.remainder(2 * math.pi)
        spin = _rotation_z(angles.to(parameter.dtype))
        origin = array(spin_center, 'spin_center', (3,))
        # X_inertial = origin + S @ (X_body - origin)，零相位两系重合。
        offset = origin - torch.einsum('mij,j->mi', spin, origin)
        default_targets = torch.einsum('mij,j->mi', spin, center) + offset
        targets = default_targets if targets is None else array(targets, 'targets', (m, 3))
        direction = unit(targets - positions, '相机朝向')
        inertial_R, inertial_t = _look_at(positions, targets)
        body_R = inertial_R @ spin
        body_t = torch.einsum('mij,mj->mi', inertial_R, offset) + inertial_t
        body_positions = origin + torch.einsum('mji,mj->mi', spin, positions - origin)
        body_direction = torch.einsum('mji,mj->mi', spin, direction)
        body_suns = torch.einsum('mji,mj->mi', spin, suns)
        if not math.isfinite(movement_weight) or movement_weight < 0:
            raise ValueError('movement_weight 必须为有限非负数')
        if max_camera_step is not None and (not math.isfinite(max_camera_step) or max_camera_step < 0):
            raise ValueError('max_camera_step 必须为有限非负数或 None')
        travel = positions.new_zeros(m)
        if current_position is not None:
            current = array(current_position, 'current_position', (3,))
            travel = torch.linalg.vector_norm(positions - current, dim=-1) / radius
        elif max_camera_step is not None:
            raise ValueError('设置 max_camera_step 时必须提供 current_position')
        budget = m if max_views is None else _positive_int(max_views, 'max_views')
        if budget > m:
            raise ValueError('max_views 不能超过候选数量')

        def mask(value, name, default):
            if value is None:
                return torch.full((m,), default, dtype=torch.bool, device=parameter.device)
            result = torch.as_tensor(value, device=parameter.device)
            if result.dtype != torch.bool or result.shape != (m,):
                raise ValueError(f'{name} 必须是 (M,) bool')
            return result.clone()

        selected = mask(selected_mask, 'selected_mask', False)
        allowed = mask(valid_mask, 'valid_mask', True) & ~selected
        if max_camera_step is not None:
            allowed &= travel <= max_camera_step / radius
        if int(selected.sum()) > budget:
            raise ValueError('已选数量不能超过 max_views')
        if int(selected.sum()) == budget:
            allowed[:] = False
        time_values = None if times is None else array(times, 'times', (m,))
        normalized_times = positions.new_zeros(m)
        if time_values is not None:
            # 大绝对时间建议调用方先减去统一时间原点，以避免 float32 精度损失。
            normalized_times = (time_values - time_values.min()) / (time_values.max() - time_values.min()).clamp_min(1e-12)
            if bool(selected.any()):
                allowed &= time_values >= time_values[selected].max()
        K = array(K, 'K', (3, 3))
        if (bool((K.diag()[:2] <= 0).any()) or
                not torch.allclose(K[2], K.new_tensor([0, 0, 1])) or
                not torch.isclose(K[1, 0], K.new_tensor(0.))):
            raise ValueError('K 必须为标准针孔内参')
        if len(resolution) != 2:
            raise ValueError('resolution 必须为 (width,height)')
        width, height = [_positive_int(v, 'resolution') for v in resolution]
        # 相机归一化内参与已选比例/预算共同作为网络输入，不计算物理奖励。
        camera = torch.stack((K[0, 0] / width, K[1, 1] / height, K[0, 2] / width,
                              K[1, 2] / height, selected.sum().to(K.dtype) / m, K.new_tensor(budget / m),
                              K.new_tensor(movement_weight), K.new_tensor(-1.) if max_camera_step is None else max_camera_step / radius))
        phase_features = torch.stack((angles.sin(), angles.cos()), dim=-1).to(parameter.dtype)
        candidates = torch.cat(((body_positions - center) / radius, body_direction, body_suns,
                                (positions - origin) / radius, phase_features,
                                normalized_times[:, None], selected.to(positions.dtype)[:, None], travel[:, None]), dim=-1)
        return (geometry, candidates, camera, selected, allowed, positions, targets, suns, time_values,
                angles, inertial_R, inertial_t, body_R, body_t, body_suns, travel, origin)

    def _forward_prepared(self, prepared):
        geometry, candidates, camera, selected, allowed = prepared[:5]
        faces, views = self.face_encoder(geometry), self.candidate_encoder(candidates)
        chosen = (views * selected[:, None]).sum(0) / selected.sum().clamp_min(1)
        pooled = torch.cat((faces.amax(0), faces.mean(0), views.amax(0), views.mean(0), chosen, camera))
        context = self.context(pooled)
        scores = self.view_head(torch.cat((views, context.expand(len(views), -1)), dim=-1)).flatten()
        # 推理阶段的显式移动偏好，不是强化学习奖励；不承诺全局最短路径。
        scores = scores - camera[-2] * prepared[15]
        logits = torch.cat((scores, self.stop_head(context)))
        mask = torch.cat((allowed, allowed.new_ones(1)))
        return PredictionOutput(logits.masked_fill(~mask, -torch.inf), mask)

    def forward(self, triangles, positions, sun_directions, *, K, resolution,
                targets=None, times=None, selected_mask=None, valid_mask=None, max_views=None,
                rotation_angles=None, spin_center=(0., 0., 0.), current_position=None,
                movement_weight=1., max_camera_step=None):
        """输出 (M+1,) 动作评分；最后一项 STOP 始终允许。

        selected_mask 标记已有观测；valid_mask 标记外部判断可用的候选。
        times 非空时禁止选择早于已有观测的时刻。max_views 是总观测数量上限，
        包含 selected_mask 中已有观测，不是强制输出数量。
        输出概率是相互竞争的动作概率，不是 SPC 重建成功概率。
        positions/targets/current_position 位于惯性系；triangles 是零相位 OBJ。
        rotation_angles 指定各候选的 z 轴自转相位；省略表示全部零相位。
        默认 targets 跟踪旋转后的块中心。sun_directions 为固定惯性系 (3,) 光向量。
        movement_weight 对归一化平移距离施加 logit 惩罚；max_camera_step 是
        相机单步平移上限（原始长度单位），0 表示固定相机位置，需 current_position。
        """
        return self._forward_prepared(self._prepare(
            triangles, positions, sun_directions, K=K, resolution=resolution, targets=targets,
            times=times, selected_mask=selected_mask, valid_mask=valid_mask, max_views=max_views,
            rotation_angles=rotation_angles, spin_center=spin_center, current_position=current_position,
            movement_weight=movement_weight, max_camera_step=max_camera_step))

    @torch.no_grad()
    def predict(self, triangles, positions, sun_directions, *, K, resolution,
                targets=None, times=None, selected_mask=None, valid_mask=None, max_views=None,
                rotation_angles=None, spin_center=(0., 0., 0.), current_position=None,
                movement_weight=1., max_camera_step=None):
        """纯自回归推理：最大评分动作 -> 更新已选标记 -> 再预测，无环境交互。

        返回新选候选的外参、rotation_angles、惯性系及本体系太阳方向和可选时刻。
        惯性系相机平移与小天体自转分开处理，STOP 可以立即产生空输出。
        调用方输入不会被修改。无随机采样，不进行优化或梯度更新。
        """
        options = dict(K=K, resolution=resolution, targets=targets, times=times,
                       valid_mask=valid_mask, max_views=max_views, rotation_angles=rotation_angles,
                       spin_center=spin_center, current_position=current_position,
                       movement_weight=movement_weight, max_camera_step=max_camera_step)
        prepared = self._prepare(triangles, positions, sun_directions, selected_mask=selected_mask, **options)
        selected = prepared[3].clone()
        budget = len(selected) if max_views is None else max_views
        ids, reason = [], 'budget'
        was_training = self.training
        self.eval()
        try:
            while int(selected.sum()) < budget:
                if not bool(prepared[4].any()):
                    reason = 'exhausted'
                    break
                action = int(self._forward_prepared(prepared).logits.argmax())
                if action == len(selected):
                    reason = 'stop'
                    break
                ids.append(action)
                selected[action] = True
                options['current_position'] = prepared[5][action]
                prepared = self._prepare(triangles, positions, sun_directions, selected_mask=selected, **options)
        finally:
            self.train(was_training)
        index = torch.tensor(ids, dtype=torch.long, device=prepared[5].device)
        p, target, sun = [value[index] for value in prepared[5:8]]
        time_result = None if prepared[8] is None else prepared[8][index].cpu().numpy()
        return ObservationPlan(np.asarray(ids, dtype=np.int64), p.cpu().numpy(), target.cpu().numpy(),
                               prepared[10][index].cpu().numpy(), prepared[11][index].cpu().numpy(), sun.cpu().numpy(),
                               prepared[9][index].cpu().numpy(), prepared[12][index].cpu().numpy(),
                               prepared[13][index].cpu().numpy(), prepared[14][index].cpu().numpy(),
                               prepared[16].cpu().numpy(),
                               time_result, reason)

    def save(self, path):
        """保存结构与权重；也支持二进制文件流。"""
        torch.save({'version': 3, 'hidden_dim': self.hidden_dim, 'state_dict': self.state_dict()}, path)

    @classmethod
    def load(cls, path, device='cpu'):
        checkpoint = torch.load(path, map_location=device, weights_only=True)
        if checkpoint.get('version') != 3:
            raise ValueError('需要包含自转相位的 v3 权重，旧版结构不兼容')
        model = cls(checkpoint['hidden_dim']).to(device)
        model.load_state_dict(checkpoint['state_dict'])
        return model


def main():
    """前向、推理与保存加载验证；不训练，不在 test 中创建代码。"""
    import io
    import unittest

    class PredictionChecks(unittest.TestCase):
        def setUp(self):
            torch.manual_seed(7)
            self.model = DRLModel(16)
            self.tri = np.array([[[-.5, -.5, 0], [.5, -.5, 0], [.5, .5, 0]],
                                 [[-.5, -.5, 0], [.5, .5, 0], [-.5, .5, 0]]], dtype=np.float32)
            self.positions = np.array([[1., 0, 2], [0, 1., 2], [-1., 0, 2], [0, -1., 2]], dtype=np.float32)
            self.sun = np.array([1., 0, 1], dtype=np.float32)
            self.options = dict(K=np.array([[100., 0, 64], [0, 100., 64], [0, 0, 1]]), resolution=(128, 128))

        def test_forward_and_gradient(self):
            output = self.model(self.tri, self.positions, self.sun, **self.options)
            self.assertEqual(output.logits.shape, (5,))
            torch.testing.assert_close(output.probabilities.sum(), torch.tensor(1.))
            output.logits.square().mean().backward()
            for parameter in self.model.parameters():
                self.assertIsNotNone(parameter.grad)
                self.assertTrue(bool(torch.isfinite(parameter.grad).all()))

        def test_order_and_variable_inputs(self):
            output = self.model(self.tri, self.positions, self.sun, **self.options)
            other = self.model(self.tri[::-1].copy(), self.positions, self.sun, **self.options)
            torch.testing.assert_close(output.logits, other.logits)
            perm = [2, 0, 3, 1]
            permuted = self.model(self.tri, self.positions[perm], self.sun, **self.options)
            torch.testing.assert_close(output.logits[perm], permuted.logits[:-1])
            torch.testing.assert_close(output.logits[-1], permuted.logits[-1])
            self.assertEqual(self.model(self.tri[:1], self.positions[:2], self.sun, **self.options).logits.shape, (3,))

        def test_masks_and_time(self):
            output = self.model(self.tri, self.positions, self.sun, times=[0, 3, 2, 1],
                                selected_mask=[False, False, True, False], **self.options)
            self.assertEqual(output.action_mask.tolist(), [False, True, False, False, True])
            exhausted = self.model(self.tri, self.positions, self.sun, valid_mask=[False]*4, **self.options)
            self.assertEqual(exhausted.probabilities.tolist(), [0., 0., 0., 0., 1.])

        def test_variable_prediction_and_pose(self):
            with torch.no_grad():
                for parameter in self.model.parameters():
                    parameter.zero_()
                self.model.stop_head.bias.fill_(10)
            empty = self.model.predict(self.tri, self.positions, self.sun, **self.options)
            self.assertEqual(empty.positions.shape, (0, 3))
            self.assertEqual(empty.rotations.shape, (0, 3, 3))
            self.assertEqual(empty.rotation_angles.shape, (0,))
            self.assertEqual(empty.body_rotations.shape, (0, 3, 3))
            self.assertEqual(empty.stop_reason, 'stop')
            with torch.no_grad():
                self.model.stop_head.bias.fill_(-10)
            selected = np.array([True, False, False, False])
            plan = self.model.predict(self.tri, self.positions, self.sun, max_views=3,
                                      selected_mask=selected, times=[0, 1, 2, 3], **self.options)
            self.assertEqual(plan.indices.tolist(), [1, 2])
            self.assertEqual(selected.tolist(), [True, False, False, False])
            self.assertEqual(plan.stop_reason, 'budget')
            np.testing.assert_allclose(np.einsum('mij,mj->mi', plan.rotations, plan.positions) + plan.translations, 0, atol=1e-6)
            np.testing.assert_allclose(plan.rotations @ plan.rotations.transpose(0, 2, 1), np.tile(np.eye(3), (2, 1, 1)), atol=1e-6)

        def test_fixed_camera_and_rotating_body(self):
            positions, angles = rotation_candidates([[4., 0., 2.]], num_phases=4)
            with torch.no_grad():
                for parameter in self.model.parameters():
                    parameter.zero_()
                self.model.stop_head.bias.fill_(-10)
            plan = self.model.predict(self.tri, positions, self.sun, rotation_angles=angles,
                                      current_position=positions[0], max_camera_step=0, **self.options)
            self.assertEqual(len(plan.indices), 4)
            np.testing.assert_allclose(plan.rotation_angles, angles)
            self.assertTrue(((plan.rotation_angles >= 0) & (plan.rotation_angles < 2*math.pi)).all())
            np.testing.assert_array_equal(plan.positions, np.tile(positions[0], (4, 1)))
            np.testing.assert_allclose(plan.rotations, np.tile(plan.rotations[:1], (4, 1, 1)), atol=1e-6)
            np.testing.assert_allclose(plan.sun_directions, np.tile(plan.sun_directions[:1], (4, 1)), atol=1e-6)
            np.testing.assert_allclose(plan.body_sun_directions[1], [0, -2**-.5, 2**-.5], atol=1e-6)
            self.assertFalse(np.allclose(plan.body_rotations[0], plan.body_rotations[1]))

        def test_frame_composition_about_nonzero_center(self):
            origin = np.array([2., -3., 1.])
            positions, angles = rotation_candidates([origin + [4, 1, 2]], num_phases=4)
            with torch.no_grad():
                for parameter in self.model.parameters():
                    parameter.zero_()
                self.model.stop_head.bias.fill_(-10)
            plan = self.model.predict(self.tri + origin, positions, self.sun, rotation_angles=angles,
                                      spin_center=origin, **self.options)
            for i, angle in enumerate(plan.rotation_angles):
                c, s = np.cos(angle), np.sin(angle)
                spin = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
                point = origin + [.3, -.2, .1]
                world_point = origin + spin @ (point - origin)
                a = plan.rotations[i] @ world_point + plan.translations[i]
                b = plan.body_rotations[i] @ point + plan.body_translations[i]
                np.testing.assert_allclose(a, b, atol=2e-6)
                np.testing.assert_allclose(plan.body_sun_directions[i], spin.T @ plan.sun_directions[i], atol=1e-6)

        def test_phase_wrap_and_move_preference(self):
            same_position = np.tile(self.positions[0], (2, 1))
            output = self.model(self.tri, same_position, self.sun,
                                rotation_angles=[0., 2*math.pi], **self.options)
            torch.testing.assert_close(output.logits[0], output.logits[1])
            with torch.no_grad():
                for parameter in self.model.parameters():
                    parameter.zero_()
                self.model.stop_head.bias.fill_(-100)
            positions = np.array([[10., 0., 2.], [1., 0., 2.], [1., 0., 2.]])
            plan = self.model.predict(self.tri, positions, self.sun, rotation_angles=[0, 0, math.pi],
                                      current_position=[1., 0., 2.], max_views=2, **self.options)
            self.assertEqual(plan.indices.tolist(), [1, 2])
            masked = self.model(self.tri, positions, self.sun, rotation_angles=[0, 0, math.pi],
                                current_position=[1., 0., 2.], max_camera_step=0, **self.options)
            self.assertEqual(masked.action_mask.tolist(), [False, True, True, True])

        def test_checkpoint(self):
            stream = io.BytesIO()
            self.model.save(stream)
            stream.seek(0)
            restored = DRLModel.load(stream)
            a = self.model(self.tri, self.positions, self.sun, **self.options)
            b = restored(self.tri, self.positions, self.sun, **self.options)
            torch.testing.assert_close(a.logits, b.logits)

        def test_invalid(self):
            for options in (dict(max_views=0), dict(valid_mask=[1]*4),
                            dict(selected_mask=[True]*4, max_views=2), dict(times=[0, 1, np.nan, 3]),
                            dict(rotation_angles=[0, 0, 0, 7]), dict(rotation_angles=[0, 0, 0, -1]),
                            dict(movement_weight=-1), dict(max_camera_step=0)):
                with self.assertRaises(ValueError):
                    self.model(self.tri, self.positions, self.sun, **self.options, **options)
            with self.assertRaises(ValueError):
                self.model(self.tri, self.positions, np.zeros_like(self.sun), **self.options)
            with self.assertRaisesRegex(ValueError, '固定'):
                self.model(self.tri, self.positions, [[1,0,1], [0,1,1], [1,0,1], [1,0,1]], **self.options)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PredictionChecks)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == '__main__':
    main()
