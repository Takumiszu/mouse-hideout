# -*- coding: utf-8 -*-
"""房子.3mf -> 鼠屋 v4
在源网格上改:
 1) 翻转 180° 成罩子
 2) 屋顶小孔填平 + 正中留 1 个洞
 3) 顶部加宽(半径 +13%)
 4) 整体缩放到 长宽 110mm / 高 55mm, 沿法线补厚壁厚到 ~1.1
 5) 两个门改成"半圆拱门"(直边 + 正圆拱顶), 不再用尖角缺口
"""
import os
import numpy as np
import trimesh
from shapely.geometry import Polygon

SRC = r'D:\房子.3mf'
TARGET_XY = 100.0
TARGET_Z = 55.0
TOP_K, TOP_P = 0.13, 1.6
ROOF_DISC_R, ROOF_Z0, ROOF_Z1 = 46.6, 72.5, 74.19
HOLE_R = 11.5
GROW = 0.20            # 法线补厚(每面)
DOOR_W = 44.0          # 拱门宽
DOOR_STRAIGHT = 16.0   # 直边高 -> 拱顶高 = 16 + 22 = 38
FRONT_AZ, LEFT_AZ = 270.0, 180.0


def cut(a, b):
    o = trimesh.boolean.difference([a, b], engine='manifold')
    return trimesh.util.concatenate(o) if isinstance(o, list) else o


def uni(a, b):
    o = trimesh.boolean.union([a, b], engine='manifold')
    return trimesh.util.concatenate(o) if isinstance(o, list) else o


def cyl(r, z0, z1, n=96):
    m = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=n)
    m.apply_translation([0, 0, (z0 + z1) / 2])
    m.fix_normals()
    return m


def extrude_xz(pts, y0, y1):
    m = trimesh.creation.extrude_polygon(Polygon(pts), y1 - y0)
    m.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, y0],
                                [0, 1, 0, 0], [0, 0, 0, 1]], float))
    m.fix_normals()
    if m.volume < 0:
        m.invert()
    return m


def extrude_yz(pts, x0, x1):
    m = trimesh.creation.extrude_polygon(Polygon(pts), x1 - x0)
    m.apply_transform(np.array([[0, 0, 1, x0], [1, 0, 0, 0],
                                [0, 1, 0, 0], [0, 0, 0, 1]], float))
    m.fix_normals()
    if m.volume < 0:
        m.invert()
    return m


def arch(center, width, straight, n=40):
    """半圆拱: 竖直边 + 正圆拱顶, 底部开口"""
    r = width / 2.0
    pts = [(center - r, -2.0), (center + r, -2.0), (center + r, straight)]
    for i in range(1, n):
        a = np.pi * i / n
        pts.append((center + r * np.cos(a), straight + r * np.sin(a)))
    pts.append((center - r, straight))
    return pts


m = trimesh.load(SRC).to_geometry()
m.fix_normals()
v = m.vertices.copy()
H = float(v[:, 2].max())

# 1) 翻转
h = trimesh.Trimesh(np.stack([v[:, 0], -v[:, 1], H - v[:, 2]], 1), m.faces.copy(), process=True)
h.fix_normals()
c = (h.bounds[0] + h.bounds[1]) / 2
h.apply_translation([-c[0], -c[1], -h.bounds[0][2]])
print('flip:', h.is_watertight, round(h.volume / 1000, 1))

# 2) 屋顶
h = uni(h, cyl(ROOF_DISC_R, ROOF_Z0, ROOF_Z1))
h = cut(h, cyl(HOLE_R, ROOF_Z0 - 4, ROOF_Z1 + 4))
h.merge_vertices(); h.fix_normals()

# 3) 顶部加宽
nv = h.vertices.copy()
s = 1.0 + TOP_K * (np.clip(nv[:, 2] / H, 0, 1) ** TOP_P)
nv[:, 0] *= s
nv[:, 1] *= s
h = trimesh.Trimesh(nv, h.faces.copy(), process=True)
h.fix_normals(); h.merge_vertices()
b = h.bounds[1] - h.bounds[0]
print('before scale bbox', np.round(b, 1))

# 4) 缩放到目标 + 法线补厚
sx, sy, sz = TARGET_XY / b[0], TARGET_XY / b[1], TARGET_Z / b[2]
h.vertices = h.vertices * np.array([sx, sy, sz])
h.fix_normals()
h.vertices = h.vertices + h.vertex_normals * GROW
h.fix_normals(); h.merge_vertices()
b = h.bounds[1] - h.bounds[0]
print('scaled bbox', np.round(b, 1), 'watertight', h.is_watertight)

# 5) 两个半圆拱门
h = cut(h, extrude_xz(arch(0.0, DOOR_W, DOOR_STRAIGHT), -300.0, 10.0))
h = cut(h, extrude_yz(arch(0.0, DOOR_W, DOOR_STRAIGHT), -300.0, 10.0))
h.merge_vertices(); h.fix_normals()
b = h.bounds[1] - h.bounds[0]
# 开完门后 X/Y 最大点被切掉, 再按 X/Y 归一到 110(只缩放 XY, 高度保持 55)
k = TARGET_XY / b[0]
h.vertices[:, 0] *= k
h.vertices[:, 1] *= k
h.fix_normals()
b = h.bounds[1] - h.bounds[0]
print('final bbox', np.round(b, 1), '| watertight', h.is_watertight,
      '| vol cm3', round(float(h.volume) / 1000, 1), '| faces', len(h.faces))
print('avg wall mm ~', round(2 * h.volume / h.area, 2))

# 打印姿态(翻回碗: 屋顶朝下)
pv = h.vertices.copy()
Hh = float(pv[:, 2].max())
pr = trimesh.Trimesh(np.stack([pv[:, 0], -pv[:, 1], Hh - pv[:, 2]], 1), h.faces.copy(), process=True)
pr.fix_normals(); pr.apply_translation([0, 0, -pr.bounds[0][2]])


def overhang(mm, tag):
    tri = mm.vertices[mm.faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    a = np.linalg.norm(n, axis=1) / 2
    n = n / (2 * a[:, None] + 1e-12)
    cen = tri.mean(axis=1)
    dn = (n[:, 2] < -np.cos(np.radians(45))) & (cen[:, 2] > 0.6)
    print(f'{tag}: overhang {a[dn].sum():6.0f} mm2 | bed {a[cen[:,2]<0.6].sum():6.0f} mm2')


overhang(h, 'house-pose')
overhang(pr, 'print-pose')

home = os.path.expanduser('~')
desk = next(p for p in [os.path.join(home, 'OneDrive', '桌面'), os.path.join(home, 'OneDrive', 'Desktop'),
                        os.path.join(home, 'Desktop')] if os.path.isdir(p))
out = os.path.join(desk, '3Doutput')
for f in ('obj', 'stl'):
    os.makedirs(os.path.join(out, f), exist_ok=True)
h.export(os.path.join(out, 'obj', 'fangzi-house-100-arch.obj'))
h.export(os.path.join(out, 'stl', 'fangzi-house-100-arch.stl'))
pr.export(os.path.join(out, 'obj', 'fangzi-house-100-arch-print.obj'))
pr.export(os.path.join(out, 'stl', 'fangzi-house-100-arch-print.stl'))
print('exported')
