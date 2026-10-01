"""Visualize a camera trajectory in Blender: path curve, sampled frustums, start/end markers, optional target
lines and velocity arrows. Viewport-oriented (open the saved .blend); preview rendering is deferred.

    blender -b [scene.blend] --factory-startup --python oc_visualize_trajectory.py -- --samples traj.npz|traj.csv
        [--time-key t] [--intrinsics intrinsics_or_manifest.json] [--frustums 8] [--frustum-depth 0.6]
        [--target X,Y,Z | --target-samples target.npz] [--velocity [--velocity-scale 0.25]]
        [--name NAME] --save out.blend [--summary out.json]

Everything goes into collection `OC_Traj_<name>`; re-running replaces it. Frustums use the same intrinsics math as
the main package (sensor fit, shift), and include an up-tick triangle so roll is visible.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import oc_blender_common as common  # noqa: E402
from oc_import_camera import load_samples  # noqa: E402
from onecreations.camera.trajectory import CameraTrajectory  # noqa: E402
from onecreations.geometry import intrinsics as intr  # noqa: E402
from onecreations.geometry.intrinsics import BlenderCameraParams  # noqa: E402

COLORS = {"path": (1.0, 0.75, 0.1, 1.0), "frustum": (0.2, 0.6, 1.0, 1.0), "start": (0.1, 0.9, 0.2, 1.0),
          "end": (0.95, 0.15, 0.15, 1.0), "target": (0.9, 0.3, 0.9, 1.0), "velocity": (0.1, 0.9, 0.9, 1.0)}


def material(name: str, rgba) -> bpy.types.Material:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    return mat


def fresh_collection(name: str) -> bpy.types.Collection:
    old = bpy.data.collections.get(name)
    if old is not None:
        for obj in list(old.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def add_object(coll, name: str, data, color_key: str):
    obj = bpy.data.objects.new(name, data)
    coll.objects.link(obj)
    obj.color = COLORS[color_key]
    if hasattr(data, "materials"):
        data.materials.append(material(f"OC_viz_{color_key}", COLORS[color_key]))
    return obj


def edge_mesh(name: str, verts, edges):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [tuple(e) for e in edges], [])
    me.update()
    return me


def sphere_mesh(name: str, radius: float):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=radius)
    bm.to_mesh(me)
    bm.free()
    return me


def frustum_geometry(c2w, k_mat, w, h, depth):
    """Apex + 4 image corners + up-tick (2 points) → verts, edges."""
    apex = c2w[:3, 3]
    corners = intr.frustum_corners_world(c2w, k_mat, w, h, depth)  # TL, TR, BR, BL
    top_mid = 0.5 * (corners[0] + corners[1])
    up = c2w[:3, 1]
    width = np.linalg.norm(corners[1] - corners[0])
    tick = top_mid + up * 0.25 * width
    verts = [apex, *corners, 0.85 * corners[0] + 0.15 * corners[1], 0.15 * corners[0] + 0.85 * corners[1], tick]
    edges = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (2, 3), (3, 4), (4, 1), (5, 7), (7, 6)]
    return verts, edges


def visualize(args) -> dict:
    s = load_samples(args.samples, args.time_key)
    traj = CameraTrajectory(s["t"], s["position"], s["quaternion_wxyz"], s.get("lens_mm"))
    if args.intrinsics:
        params = BlenderCameraParams.from_dict(common.load_intrinsics_dict(args.intrinsics))
    else:
        params = BlenderCameraParams(lens_mm=50.0, resolution_x=1920, resolution_y=1080)
    name = args.name or os.path.splitext(os.path.basename(args.samples))[0]
    coll = fresh_collection(f"OC_Traj_{name}")
    summary = {"collection": coll.name, "samples": len(traj), "objects": {}}

    curve = bpy.data.curves.new(f"OC_path_{name}", type="CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = args.path_width
    spline = curve.splines.new("POLY")
    spline.points.add(len(traj) - 1)
    for p, pos in zip(spline.points, traj.position):
        p.co = (float(pos[0]), float(pos[1]), float(pos[2]), 1.0)
    add_object(coll, f"OC_path_{name}", curve, "path")
    summary["path_points"] = len(spline.points)

    n = max(2, args.frustums)
    times = np.linspace(traj.start, traj.end, n)
    c2ws = traj.evaluate_c2w(times)
    lenses = traj.evaluate_lens(times)
    verts, edges = [], []
    for i, m in enumerate(c2ws):
        p = params if lenses is None else BlenderCameraParams.from_dict({**params.to_dict(), "lens_mm": float(lenses[i])})
        v, e = frustum_geometry(m, intr.intrinsic_matrix(p), p.width_px, p.height_px, args.frustum_depth)
        base = len(verts)
        verts.extend(v)
        edges.extend((a + base, b + base) for a, b in e)
    add_object(coll, f"OC_frustums_{name}", edge_mesh(f"OC_frustums_{name}", verts, edges), "frustum")
    summary["frustum_count"] = n
    summary["frustum_times"] = [round(float(t), 9) for t in times]
    summary["frustum_apexes"] = [[round(float(c), 9) for c in m[:3, 3]] for m in c2ws]

    for key, pos in (("start", traj.position[0]), ("end", traj.position[-1])):
        obj = add_object(coll, f"OC_{key}_{name}", sphere_mesh(f"OC_{key}_{name}", args.marker_radius), key)
        obj.location = [float(c) for c in pos]
        summary[key] = [round(float(c), 9) for c in pos]

    target_pts = None
    if args.target:
        target_pts = np.tile(np.array([float(v) for v in args.target.split(",")]), (n, 1))
    elif args.target_samples:
        tgt = load_samples(args.target_samples, args.time_key)
        target_pts = np.stack([np.interp(times, tgt["t"], tgt["position"][:, j]) for j in range(3)], axis=1)
    if target_pts is not None:
        tv = [*c2ws[:, :3, 3], *target_pts]
        te = [(i, i + n) for i in range(n)]
        add_object(coll, f"OC_target_lines_{name}", edge_mesh(f"OC_target_lines_{name}", tv, te), "target")
        empty = bpy.data.objects.new(f"OC_target_{name}", None)
        empty.empty_display_type = "SPHERE"
        empty.empty_display_size = args.marker_radius * 1.5
        empty.location = [float(c) for c in target_pts[-1]]
        coll.objects.link(empty)
        summary["target_lines"] = n

    if args.velocity:
        dt = 1e-3 * max(traj.duration, 1e-6)
        p0, _ = traj.evaluate(np.clip(times - dt, traj.start, traj.end))
        p1, _ = traj.evaluate(np.clip(times + dt, traj.start, traj.end))
        span = np.clip(times + dt, traj.start, traj.end) - np.clip(times - dt, traj.start, traj.end)
        vel = (p1 - p0) / span[:, None]
        vv, ve = [], []
        for pos, v in zip(c2ws[:, :3, 3], vel):
            tip = pos + v * args.velocity_scale
            base = len(vv)
            vv.extend([pos, tip])
            ve.append((base, base + 1))
            length = np.linalg.norm(tip - pos)
            if length > 1e-9:
                d = (tip - pos) / length
                side = np.cross(d, [0.0, 0.0, 1.0])
                side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-6 else np.array([1.0, 0.0, 0.0])
                for sgn in (1, -1):
                    vv.append(tip - 0.2 * length * d + sgn * 0.1 * length * side)
                    ve.append((base + 1, len(vv) - 1))
        add_object(coll, f"OC_velocity_{name}", edge_mesh(f"OC_velocity_{name}", vv, ve), "velocity")
        summary["velocity_vectors"] = n
        summary["max_speed_mps"] = round(float(np.linalg.norm(vel, axis=1).max()), 6)

    summary["objects"] = {o.name: o.type for o in coll.objects}
    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.save))
    if args.summary:
        common.write_json(args.summary, summary)
    print(f"[oc] trajectory visualized in collection {coll.name!r} ({len(coll.objects)} objects)")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(prog="oc_visualize_trajectory")
    p.add_argument("--samples", required=True)
    p.add_argument("--time-key", default="t")
    p.add_argument("--intrinsics")
    p.add_argument("--frustums", type=int, default=8)
    p.add_argument("--frustum-depth", type=float, default=0.6)
    p.add_argument("--path-width", type=float, default=0.01)
    p.add_argument("--marker-radius", type=float, default=0.08)
    p.add_argument("--target")
    p.add_argument("--target-samples")
    p.add_argument("--velocity", action="store_true")
    p.add_argument("--velocity-scale", type=float, default=0.25)
    p.add_argument("--name")
    p.add_argument("--save")
    p.add_argument("--summary")
    visualize(p.parse_args(common.script_args()))


if __name__ == "__main__":
    main()
