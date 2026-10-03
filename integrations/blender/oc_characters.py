"""Continuous character geometry (showcase on): organic bodies that deform on the existing rigs instead of rigidly
skinned primitives.

bpy + stdlib + numpy only. Everything is procedural and deterministic (no sculpt files, no downloads).
- Anatomy: metaball ellipsoids (sizes given as VISIBLE semi-axes in metres) fused into one smooth field, converted
  to a mesh and lightly smoothed, so torso, neck, head and limbs read as one continuous body.
- Tubes: bmesh sweeps along a Catmull-Rom path with per-point radius (horns, tusks, straps, hair locks, prongs),
  with a UV map whose V runs 0 -> 1 along the path (used for root-to-tip material gradients).
- Shells and panels: armour plates (sphere caps with thickness) and cloth panels with folds.
- Skinning: weights from a rest-space function of vertex position (smoothstep blends between bones), so joints
  bend smoothly; the rig and its animation are untouched.
"""

from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

VISIBLE_RADIUS = 0.575       # visible / influence radius of one metaball element (stiffness 2, threshold 0.6); measured


# --- metaball anatomy ----------------------------------------------------------------------------------------

def ell(co, semi, rot_deg=(0.0, 0.0, 0.0), negative=False, axis=None, stiffness=2.0) -> dict:
    """An ellipsoid element with VISIBLE semi-axes `semi` (a, b, c) in metres (an isolated element renders at this
    size; neighbours blend and swell slightly). Orientation: `axis` (the local X axis points along this vector) or
    XYZ Euler degrees."""
    semi = tuple(float(s) for s in semi)
    big = max(semi)
    if axis is not None:
        q = Vector((1.0, 0.0, 0.0)).rotation_difference(Vector(axis).normalized())
    else:
        q = Euler([math.radians(a) for a in rot_deg], "XYZ").to_quaternion()
    return {"co": tuple(float(c) for c in co), "radius": big / VISIBLE_RADIUS, "size": tuple(s / big for s in semi),
            "rot": tuple(q), "negative": bool(negative), "stiffness": float(stiffness)}


def ball(co, r, negative=False) -> dict:
    return ell(co, (r, r, r), negative=negative)


def limb(a, b, r_a, r_b, flat=1.0, overlap=1.6) -> list[dict]:
    """A tapered limb from a to b: ellipsoids elongated along the segment (smooth taper, no beads)."""
    a, b = Vector(a), Vector(b)
    d = b - a
    length = d.length
    n = max(1, math.ceil(length * overlap / (0.9 * (r_a + r_b))))
    out = []
    for i in range(n):
        t = (i + 0.5) / n
        r = r_a + (r_b - r_a) * t
        half = 0.5 * length / n * overlap + 0.35 * r
        out.append(ell(a + d * t, (half, r, r * flat), axis=d))
    return out


def metaball_mesh(name: str, elements: list[dict], mat, resolution: float = 0.016, smooth_iters: int = 4,
                  smooth_factor: float = 0.5):
    """Fuse `elements` into one metaball field and convert it to a smooth-shaded mesh object named `name`."""
    mb = bpy.data.metaballs.new(name)
    mb.resolution = mb.render_resolution = resolution
    mb.threshold = 0.6
    for e in elements:
        el = mb.elements.new(type="ELLIPSOID")
        el.co, el.radius, el.stiffness = e["co"], e["radius"], e["stiffness"]
        el.size_x, el.size_y, el.size_z = e["size"]
        el.rotation = Quaternion(e["rot"])
        el.use_negative = e["negative"]
    family = "".join(ch for ch in name if ch.isalnum())          # metaball families are keyed by the base name
    ob = bpy.data.objects.new(family, mb)
    bpy.context.scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.convert(target="MESH")
    me = bpy.context.active_object
    me.name = name
    if smooth_iters:
        mod = me.modifiers.new("smooth", "SMOOTH")
        mod.factor, mod.iterations = smooth_factor, smooth_iters
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in me.data.polygons:
        p.use_smooth = True
    me.data.materials.clear()
    me.data.materials.append(mat)
    return me


# --- swept tubes -----------------------------------------------------------------------------------------------

def _catmull(points: list[Vector], samples: int) -> list[Vector]:
    pts = [points[0] + (points[0] - points[1])] + list(points) + [points[-1] + (points[-1] - points[-2])]
    out = []
    segs = len(points) - 1
    for k in range(samples + 1):
        u = k / samples * segs
        i = min(int(u), segs - 1)
        t = u - i
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    return out


def tube(name: str, points, radii, mat, ring: int = 16, samples: int = 24, flat: float = 1.0, up=(0.0, 0.0, 1.0)):
    """A tube swept along a smooth path through `points`, radius interpolated from `radii` (one per point; 0 gives
    a point). `flat` < 1 flattens the cross-section (straps). UV: U around, V along the path (0 root -> 1 tip)."""
    pts = [Vector(p) for p in points]
    path = _catmull(pts, samples) if len(pts) > 2 else [pts[0].lerp(pts[1], k / samples) for k in range(samples + 1)]
    rs = np.interp(np.linspace(0, 1, len(path)), np.linspace(0, 1, len(radii)), radii)
    bm = bmesh.new()
    rings = []
    normal = Vector(up)
    for k, p in enumerate(path):
        tan = (path[min(k + 1, len(path) - 1)] - path[max(k - 1, 0)]).normalized()
        normal = (normal - tan * normal.dot(tan))
        if normal.length < 1e-6:
            normal = tan.orthogonal()
        normal.normalize()
        binorm = tan.cross(normal)
        r = float(rs[k])
        if r <= 1e-5:
            rings.append([bm.verts.new(p)])
            continue
        rings.append([bm.verts.new(p + (normal * math.cos(2 * math.pi * j / ring) * flat
                                        + binorm * math.sin(2 * math.pi * j / ring)) * r) for j in range(ring)])
    uv_faces = []
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for j in range(ring):
            if len(a) == 1 and len(b) == 1:
                continue
            if len(a) == 1:
                f = bm.faces.new((a[0], b[(j + 1) % ring], b[j]))
            elif len(b) == 1:
                f = bm.faces.new((a[j], a[(j + 1) % ring], b[0]))
            else:
                f = bm.faces.new((a[j], a[(j + 1) % ring], b[(j + 1) % ring], b[j]))
            uv_faces.append((f, k, j))
    for end in (rings[0], rings[-1]):
        if len(end) > 2:
            bm.faces.new(end if end is rings[-1] else list(reversed(end)))
    uv = bm.loops.layers.uv.new("UVMap")
    nk = len(rings) - 1
    for f, k, j in uv_faces:
        for loop in f.loops:
            vk = k if loop.vert in rings[k] else k + 1
            loop[uv].uv = (j / ring, vk / nk)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    return ob


# --- shells and panels ---------------------------------------------------------------------------------------

def _finish(ob, mat, thickness=0.0, subdiv=0):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    if thickness:
        m = ob.modifiers.new("solid", "SOLIDIFY")
        m.thickness, m.offset = thickness, -1.0
        bpy.ops.object.modifier_apply(modifier=m.name)
    if subdiv:
        m = ob.modifiers.new("subd", "SUBSURF")
        m.levels = m.render_levels = subdiv
        bpy.ops.object.modifier_apply(modifier=m.name)
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    return ob


def shell(name, center, semi, mat, cut=0.0, thickness=0.03, rot_deg=(0.0, 0.0, 0.0), segments=32):
    """An armour plate: the part of an ellipsoid (semi-axes) above local z = cut * c, with thickness, rotated."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=segments, ring_count=segments // 2)
    ob = bpy.context.active_object
    ob.name = name
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < cut - 1e-6], context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.transform(Matrix.Diagonal((*semi, 1.0)))
    ob.data.transform(Euler([math.radians(a) for a in rot_deg], "XYZ").to_matrix().to_4x4())
    ob.data.transform(Matrix.Translation(center))
    return _finish(ob, mat, thickness)


def cloth_panel(name, top, bottom, width_top, width_bottom, mat, folds=5, depth=0.025, sag=0.0, thickness=0.012,
                facing=(0.0, -1.0, 0.0), rows=24, cols=20):
    """A hanging cloth panel from `top` to `bottom` (centres), flaring from width_top to width_bottom, with `folds`
    vertical folds of amplitude `depth` displaced along `facing`, and a forward `sag` belly."""
    top, bottom, facing = Vector(top), Vector(bottom), Vector(facing).normalized()
    down = bottom - top
    side = down.normalized().cross(facing).normalized()
    bm = bmesh.new()
    grid = []
    for i in range(rows + 1):
        t = i / rows
        w = width_top + (width_bottom - width_top) * t
        row = []
        for j in range(cols + 1):
            s = j / cols - 0.5
            fold = math.sin(s * folds * 2 * math.pi) * depth * (0.4 + 0.6 * t)
            belly = sag * math.sin(math.pi * t) * (1 - 4 * s * s)
            row.append(bm.verts.new(top + down * t + side * (s * w) + facing * (fold + belly)))
        grid.append(row)
    for i in range(rows):
        for j in range(cols):
            bm.faces.new((grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return _finish(ob, mat, thickness, subdiv=1)


# --- skinning ----------------------------------------------------------------------------------------------------

def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def chain_weights(param: np.ndarray, stops: list[tuple[float, float, str, str]]) -> dict[str, np.ndarray]:
    """Weights along a chain from a per-vertex parameter. stops: (lo, hi, bone_below, bone_above) with increasing
    parameter; between lo and hi the weight blends smoothly from bone_below to bone_above."""
    out: dict[str, np.ndarray] = {}
    remaining = np.ones_like(param)
    for lo, hi, below, above in stops:
        up = smoothstep(param, lo, hi)
        out[below] = out.get(below, 0.0) + remaining * (1.0 - up)
        remaining = remaining * up
        last = above
    out[last] = out.get(last, 0.0) + remaining
    return out


def assign_weights(ob, weights: dict[str, np.ndarray], mask: np.ndarray | None = None) -> None:
    """Write per-vertex weights into vertex groups (only vertices in `mask`, default all)."""
    n = len(ob.data.vertices)
    sel = np.ones(n, bool) if mask is None else mask
    for bone, w in weights.items():
        w = np.broadcast_to(np.asarray(w, np.float64), (n,))
        vg = ob.vertex_groups.get(bone) or ob.vertex_groups.new(name=bone)
        for i in np.nonzero(sel & (w > 1e-4))[0]:
            vg.add([int(i)], float(w[i]), "REPLACE")


def vertex_coords(ob) -> np.ndarray:
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def weight_stats(ob) -> dict:
    """Skinning sanity: vertex count, unweighted vertices, max |sum of weights - 1|, groups used."""
    names = {g.index: g.name for g in ob.vertex_groups}
    sums = np.zeros(len(ob.data.vertices))
    used = set()
    for v in ob.data.vertices:
        for g in v.groups:
            sums[v.index] += g.weight
            if g.weight > 1e-4:
                used.add(names[g.group])
    return {"vertices": int(len(sums)), "unweighted": int((sums < 1e-6).sum()),
            "max_sum_error": round(float(np.abs(sums - 1.0).max()), 6), "groups": sorted(used)}


def rigid(ob, bone: str):
    assign_weights(ob, {bone: np.ones(len(ob.data.vertices))})
    return ob


def bind(ob, rig):
    """Armature modifier + parenting while the rig is still at the origin (rest space = object space)."""
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    ob.parent = rig
    return ob
