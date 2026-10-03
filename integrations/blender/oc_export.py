"""Export a shot from Blender into a OneCreations bundle (contract: onecreations.contracts.export.ExportManifest).

    blender -b scene.blend --factory-startup --python oc_export.py -- --out DIR [--camera NAME] [--shot-id ID]
        [--fps 24 | 24000/1001] [--duration SECONDS] [--source-start S] [--timewarp tw.json]
        [--passes [--samples 1] [--allow-subframe-passes] [--keep-exr]] [--probes]

Per output frame k: output time k/fps → source time via the TimeWarp → Blender frame
frame_start + source_time × scene_fps, evaluated with frame_set(int, subframe). Writes:
  camera_samples.npz  t (output s), t_source, blender_frame, position, quaternion_wxyz, c2w, lens_mm, shift_x, shift_y
  objects.npz         one (F,4,4) matrix_world stack per tagged object (key = oc_id)
  joints.npz          <oc_id>.heads / <oc_id>.tails (F,J,3) world-space bone heads/tails per tagged armature
  probes.npz          points (F,P,3) world, ndc (F,P,3) = Blender's world_to_camera_view (cross-check only)
  passes.npz          depth_m (F,H,W) planar meters (inf = background), object_index (F,H,W) uint16,
                      normal (F,H,W,3) world space — Cycles CPU, fixed seed, tiny pixel filter
  export_manifest.json  canonical JSON + content_sha256

Session A scope: Cryptomatte decoding, beauty renders, motion vectors, joint visibility and subframe pass rendering
are deferred (listed in the manifest's `deferred`).
"""

from __future__ import annotations

import argparse
import glob
import math
import os
import shutil
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402

import oc_blender_common as common  # noqa: E402
from onecreations import hashing  # noqa: E402
from onecreations.geometry import intrinsics as intr  # noqa: E402
from onecreations.geometry import quat  # noqa: E402
from onecreations.timebase import FrameRate, TimeWarp, format_time, parse_time  # noqa: E402

CONVENTIONS = {
    "units": "meters",
    "world": "blender_z_up_right_handed",
    "pose": "camera_to_world",
    "camera_axes": "blender: -Z forward, +Y up, +X right",
    "rotation": "quaternion_wxyz",
    "pixels": "top-left origin, +u right, +v down, pixel centres at +0.5",
    "image_rows": "top-down",
    "depth": "planar view-space depth in meters; inf = background",
    "time": "exact rational seconds; source time 0 = scene frame_start",
}
DEFERRED = ["cryptomatte_decoding", "beauty_render", "motion_vectors", "joint_visibility", "subframe_pass_rendering"]
PASS_SLOTS = (("depth", "Depth"), ("normal", "Normal"), ("index", "IndexOB"))
BACKGROUND_DEPTH = 1e9


def parse_args(argv):
    p = argparse.ArgumentParser(prog="oc_export")
    p.add_argument("--out", required=True)
    p.add_argument("--camera")
    p.add_argument("--shot-id", default="adhoc")
    p.add_argument("--fps")
    p.add_argument("--duration")
    p.add_argument("--source-start", default="0")
    p.add_argument("--timewarp")
    p.add_argument("--passes", action="store_true")
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--allow-subframe-passes", action="store_true")
    p.add_argument("--keep-exr", action="store_true")
    p.add_argument("--probes", action="store_true")
    return p.parse_args(argv)


def plan_frames(scene, args):
    fps_scene = common.scene_fps(scene)
    out_rate = FrameRate.from_value(args.fps) if args.fps else FrameRate(fps_scene.numerator, fps_scene.denominator)
    if args.timewarp:
        tw = TimeWarp.from_dict(common.read_json(args.timewarp))
        if tw.output_start != 0:
            raise ValueError("timewarp must start at output time 0")
        duration = parse_time(args.duration) if args.duration else tw.output_end
    else:
        duration = (parse_time(args.duration) if args.duration
                    else Fraction(scene.frame_end - scene.frame_start + 1) / fps_scene)
        tw = TimeWarp.identity(duration, parse_time(args.source_start))
    n = out_rate.frame_count(duration)
    if n.denominator != 1:
        raise ValueError(f"duration {format_time(duration)} s is not a whole number of output frames")
    frames = []
    for k in range(int(n)):
        t_out = out_rate.time_of_frame(k)
        t_src = tw(t_out)
        frames.append({"index": k, "output_time": t_out, "source_time": t_src,
                       "blender_frame": scene.frame_start + t_src * fps_scene})
    return fps_scene, out_rate, duration, tw, frames


def set_frame(scene, bf: Fraction) -> None:
    whole = math.floor(bf)
    scene.frame_set(int(whole), subframe=float(bf - whole))


def setup_passes(scene, exr_dir: str, samples: int):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = False
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False
    scene.cycles.filter_width = 0.01
    scene.render.use_motion_blur = False
    scene.render.use_compositing = True
    scene.render.use_sequencer = False
    scene.use_nodes = True
    vl = bpy.context.view_layer
    vl.use_pass_z = vl.use_pass_normal = vl.use_pass_object_index = True
    tree = scene.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    rl = tree.nodes.new("CompositorNodeRLayers")
    comp = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(rl.outputs["Image"], comp.inputs["Image"])
    fo = tree.nodes.new("CompositorNodeOutputFile")
    fo.base_path = exr_dir
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.format.exr_codec = "ZIP"
    fo.file_slots.clear()
    for slot_name, socket in PASS_SLOTS:
        fo.file_slots.new(slot_name)
        if socket not in rl.outputs:
            raise RuntimeError(f"render layer has no {socket!r} output; available: {list(rl.outputs.keys())}")
        tree.links.new(rl.outputs[socket], fo.inputs[slot_name])
    return fo


def read_exr(path: str) -> np.ndarray:
    img = bpy.data.images.load(path, check_existing=False)
    try:
        img.colorspace_settings.name = "Non-Color"
        n = len(img.pixels)
        w, h = img.size
        buf = np.empty(n, dtype=np.float32)
        img.pixels.foreach_get(buf)
        return buf.reshape(h, w, n // (w * h))[::-1].copy()  # Blender images are bottom-up
    finally:
        bpy.data.images.remove(img)


def render_passes(scene, fo, exr_dir: str, k: int) -> dict:
    for slot, (slot_name, _) in zip(fo.file_slots, PASS_SLOTS):
        slot.path = f"{slot_name}_k{k:05d}_"
    bpy.ops.render.render(write_still=False)
    out = {}
    for slot_name, _ in PASS_SLOTS:
        files = glob.glob(os.path.join(exr_dir, f"{slot_name}_k{k:05d}_*.exr"))
        if len(files) != 1:
            raise RuntimeError(f"expected one {slot_name} EXR for output frame {k}, found {files}")
        out[slot_name] = read_exr(files[0])
    return out


def measure_depth_convention(scene, depsgraph, c2w, k_mat, depth_raw, clip_end) -> dict:
    """Compare the rendered depth with ray-cast distances at a pixel grid to learn Blender's depth convention."""
    h, w = depth_raw.shape
    origin = Vector(c2w[:3, 3].tolist())
    err_planar, err_euclid = [], []
    for r in np.linspace(0.1 * h, 0.9 * h, 5).astype(int):
        for c in np.linspace(0.1 * w, 0.9 * w, 9).astype(int):
            ray_cv = intr.pixel_rays_cv(np.array([[c + 0.5, r + 0.5]]), k_mat)[0]
            cos = 1.0 / np.linalg.norm(ray_cv)
            d_world = c2w[:3, :3] @ np.array([ray_cv[0], -ray_cv[1], -ray_cv[2]])
            d_world /= np.linalg.norm(d_world)
            hit, loc, *_ = scene.ray_cast(depsgraph, origin, Vector(d_world.tolist()), distance=clip_end)
            d = float(depth_raw[r, c])
            if not hit or not np.isfinite(d) or d >= BACKGROUND_DEPTH:
                continue
            euclid = (loc - origin).length
            err_planar.append(abs(d - euclid * cos))
            err_euclid.append(abs(d - euclid))
    if not err_planar:
        return {"measured_convention": "unverified", "probes": 0, "median_error_planar_m": None,
                "median_error_euclidean_m": None}
    mp, me = float(np.median(err_planar)), float(np.median(err_euclid))
    conv = "unverified" if min(mp, me) > 0.01 else ("planar" if mp <= me else "euclidean")
    return {"measured_convention": conv, "probes": len(err_planar), "median_error_planar_m": mp,
            "median_error_euclidean_m": me}


def export(args) -> str:
    scene = bpy.context.scene
    cam = bpy.data.objects[args.camera] if args.camera else scene.camera
    if cam is None or cam.type != "CAMERA":
        raise ValueError("no camera: pass --camera NAME or set scene.camera")
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    fps_scene, out_rate, duration, tw, frames = plan_frames(scene, args)
    if args.passes and not args.allow_subframe_passes and any(f["blender_frame"].denominator != 1 for f in frames):
        raise ValueError("passes at subframe source times are unverified (deferred); export passes on whole frames "
                         "or pass --allow-subframe-passes")

    params = common.camera_params(cam, scene)
    k_mat = intr.intrinsic_matrix(params)
    width, height = params.width_px, params.height_px
    meshes = common.tagged_objects(scene, types={"MESH"})
    tagged = [o for o in common.tagged_objects(scene) if o != cam and o.type != "ARMATURE"]
    armatures = common.tagged_objects(scene, types={"ARMATURE"})

    exr_dir = os.path.join(out_dir, "_exr")
    fo = None
    excluded_volumes = []
    if args.passes:
        os.makedirs(exr_dir, exist_ok=True)
        fo = setup_passes(scene, exr_dir, args.samples)
        for o in scene.objects:                       # passes are geometric: volume-only helpers would scatter rays
            if common.is_volume_only(o) and not o.hide_render:
                o.hide_render = True
                excluded_volumes.append(o.name)

    cam_rows = {k: [] for k in ("c2w", "lens_mm", "shift_x", "shift_y")}
    obj_rows = {str(o["oc_id"]): [] for o in tagged}
    joint_rows = {str(a["oc_id"]): ([], []) for a in armatures}
    probe_points, probe_ndc, probe_labels = [], [], []
    pass_rows = {"depth_m": [], "object_index": [], "normal": []}
    depth_check = None
    factor = None

    for f in frames:
        set_frame(scene, f["blender_frame"])
        depsgraph = bpy.context.evaluated_depsgraph_get()
        cam_eval = cam.evaluated_get(depsgraph)
        c2w = common.rigid_matrix(cam_eval.matrix_world)
        cam_rows["c2w"].append(c2w)
        cam_rows["lens_mm"].append(float(cam_eval.data.lens))
        cam_rows["shift_x"].append(float(cam_eval.data.shift_x))
        cam_rows["shift_y"].append(float(cam_eval.data.shift_y))
        for o in tagged:
            obj_rows[str(o["oc_id"])].append(common.to_numpy(o.evaluated_get(depsgraph).matrix_world))
        for a in armatures:
            a_eval = a.evaluated_get(depsgraph)
            mw = a_eval.matrix_world
            heads, tails = joint_rows[str(a["oc_id"])]
            heads.append([list(mw @ pb.head) for pb in a_eval.pose.bones])
            tails.append([list(mw @ pb.tail) for pb in a_eval.pose.bones])
        if args.probes:
            pts, ndc, labels = [], [], []
            for o in meshes:
                mw = o.evaluated_get(depsgraph).matrix_world
                corners = [mw @ Vector(c) for c in o.bound_box] + [mw.translation.copy()]
                for i, p in enumerate(corners):
                    pts.append(list(p))
                    ndc.append(list(world_to_camera_view(scene, cam_eval, p)))
                    labels.append(f"{o['oc_id']}:{'origin' if i == 8 else f'corner{i}'}")
            probe_points.append(pts)
            probe_ndc.append(ndc)
            probe_labels = labels
        if fo is not None:
            raw = render_passes(scene, fo, exr_dir, f["index"])
            depth_raw = raw["depth"][..., 0].astype(np.float64)
            if depth_check is None:
                depth_check = measure_depth_convention(scene, depsgraph, c2w, k_mat, depth_raw, params.clip_end)
                if depth_check["measured_convention"] == "euclidean":
                    factor = intr.euclidean_to_planar_factor(width, height, k_mat)
            background = depth_raw >= BACKGROUND_DEPTH
            depth = depth_raw * factor if factor is not None else depth_raw
            depth[background] = np.inf
            pass_rows["depth_m"].append(depth.astype(np.float32))
            pass_rows["object_index"].append(np.rint(raw["index"][..., 0]).astype(np.uint16))
            pass_rows["normal"].append(raw["normal"][..., :3].astype(np.float32))

    c2w_all = np.stack(cam_rows["c2w"])
    quats = quat.make_continuous(np.stack([quat.from_matrix(m[:3, :3]) for m in c2w_all]))
    cam_arrays = {
        "t": np.array([float(f["output_time"]) for f in frames]),
        "t_source": np.array([float(f["source_time"]) for f in frames]),
        "blender_frame": np.array([float(f["blender_frame"]) for f in frames]),
        "position": c2w_all[:, :3, 3].copy(), "quaternion_wxyz": quats, "c2w": c2w_all,
        "lens_mm": np.array(cam_rows["lens_mm"]), "shift_x": np.array(cam_rows["shift_x"]),
        "shift_y": np.array(cam_rows["shift_y"]),
    }
    manifest = {
        "schema_version": 1,
        "exporter_version": common.EXPORTER_VERSION,
        "blender_version": common.blender_version(),
        "source_file": os.path.basename(bpy.data.filepath) or "(unsaved)",
        "conventions": CONVENTIONS,
        "scene": {"name": scene.name, "fps": {"num": fps_scene.numerator, "den": fps_scene.denominator},
                  "frame_start": scene.frame_start, "frame_end": scene.frame_end,
                  "length_unit": scene.unit_settings.length_unit, "unit_scale": float(scene.unit_settings.scale_length)},
        "shot": {"id": args.shot_id, "output_fps": out_rate.to_dict(), "frame_count": len(frames),
                 "duration": format_time(duration), "timewarp_keys": tw.to_dict()["keys"]},
        "frames": [{"index": f["index"], "output_time": format_time(f["output_time"]),
                    "source_time": format_time(f["source_time"]), "blender_frame": format_time(f["blender_frame"])}
                   for f in frames],
        "camera": {"object_name": cam.name, "intrinsics": {**params.to_dict(), "K": k_mat.tolist()},
                   "samples": common.save_arrays(os.path.join(out_dir, "camera_samples.npz"), cam_arrays),
                   "animated_lens": bool(np.ptp(cam_arrays["lens_mm"]) > 1e-9),
                   "animated_shift": bool(np.ptp(cam_arrays["shift_x"]) > 1e-9 or np.ptp(cam_arrays["shift_y"]) > 1e-9)},
        "objects": [{"oc_id": str(o["oc_id"]), "name": o.name, "type": o.type, "pass_index": int(o.pass_index),
                     "bound_box_local": [list(c) for c in o.bound_box]} for o in tagged],
        "objects_file": (common.save_arrays(os.path.join(out_dir, "objects.npz"),
                                            {k: np.stack(v) for k, v in obj_rows.items()}) if tagged else None),
        "armatures": [{"oc_id": str(a["oc_id"]), "name": a.name, "bones": [b.name for b in a.pose.bones]}
                      for a in armatures],
        "joints_file": (common.save_arrays(os.path.join(out_dir, "joints.npz"),
                                           {f"{k}.{part}": np.array(rows[i]) for k, rows in joint_rows.items()
                                            for i, part in enumerate(("heads", "tails"))}) if armatures else None),
        "probe_labels": probe_labels,
        "probes_file": (common.save_arrays(os.path.join(out_dir, "probes.npz"),
                                           {"points": np.array(probe_points), "ndc": np.array(probe_ndc)})
                        if args.probes else None),
        "passes": None,
        "deferred": DEFERRED,
    }
    if fo is not None:
        pass_arrays = {k: np.stack(v) for k, v in pass_rows.items()}
        manifest["passes"] = {
            "engine": "CYCLES", "samples": args.samples, "filter_width": 0.01, "width": width, "height": height,
            "file": common.save_arrays(os.path.join(out_dir, "passes.npz"), pass_arrays),
            "background_depth": "inf",
            "depth": {**depth_check, "stored_as": "raw" if depth_check["measured_convention"] == "unverified" else "planar"},
            "normal_space": "world",
            "object_index_map": {str(o["oc_id"]): int(o.pass_index) for o in meshes if o.pass_index},
        }
        if excluded_volumes:
            manifest["passes"]["excluded_volume_objects"] = sorted(excluded_volumes)
        if not args.keep_exr:
            shutil.rmtree(exr_dir, ignore_errors=True)
    manifest["content_sha256"] = hashing.content_hash(manifest)
    path = os.path.join(out_dir, "export_manifest.json")
    common.write_json(path, manifest)
    print(f"[oc] exported {len(frames)} frames → {path} (content {manifest['content_sha256'][:12]})")
    return path


if __name__ == "__main__":
    export(parse_args(common.script_args()))
