"""Render a composite layer of an authored scene (contract: onecreations.contracts.composite.CompositeManifest).

    blender -b scene.blend --factory-startup --python render_layers.py -- --spec shot_spec.json --layer mace_protect \
        --out-dir DIR [--frames 1-49] [--device OPTIX]

The layer's objects (oc_ids) and collections render normally; every other mesh is a HOLDOUT (it still occludes the
layer and casts shadows/bounce light on it, but renders as transparent), so occlusion by the actor or environment is
exact. Volume-only helpers (the haze box) are hidden, since a volume would fill the alpha. Transparent film, fixed
seed, OIDN, optional Blender motion blur (shutter in frames, centred on the frame). Writes DIR/f_####.png (RGBA,
straight alpha, Blender frame numbers) and DIR/layer_render.json.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import oc_blender_common as common  # noqa: E402
import render_reference  # noqa: E402


def setup_layer(scene, layer: dict) -> dict:
    keep = set(layer.get("objects", []))
    view_layer = bpy.context.view_layer
    enabled = []
    for name in layer.get("collections", []):
        view_layer.layer_collection.children[name].exclude = False
        enabled += [o.name for o in bpy.data.collections[name].all_objects]
    holdouts, hidden = [], []
    for o in scene.objects:
        if o.type != "MESH":
            continue
        if common.is_volume_only(o):
            o.hide_render = True
            hidden.append(o.name)
            continue
        oc_id = str(o["oc_id"]) if "oc_id" in o.keys() else None
        if (oc_id in keep) or (o.name in enabled):
            o.is_holdout = False
        elif layer.get("render", {}).get("holdout_others", True):
            o.is_holdout = True
            holdouts.append(o.name)
    return {"visible": sorted(keep) + sorted(enabled), "holdout": sorted(holdouts), "hidden": sorted(hidden)}


def render(spec_path: str, layer_id: str, out_dir: str, frames: str | None, device: str) -> dict:
    spec = common.read_json(spec_path)
    layer = next(ly for ly in spec["layers"]["layers"] if ly["id"] == layer_id)
    scene = bpy.context.scene
    devices = render_reference.use_gpu(device)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    r = layer.get("render", {})
    scene.cycles.samples = int(r.get("samples", 64))
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "denoising_use_gpu"):
        scene.cycles.denoising_use_gpu = False
    scene.render.film_transparent = True
    shutter = r.get("motion_blur_shutter")
    scene.render.use_motion_blur = bool(shutter)
    if shutter:
        scene.render.motion_blur_shutter = float(shutter)
        scene.render.motion_blur_position = "CENTER"
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    vis = setup_layer(scene, layer)
    first, last = scene.frame_start, scene.frame_end
    if frames:
        a, b = (int(v) for v in frames.split("-"))
        scene.frame_start, scene.frame_end = a, b
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "f_*.png")):
        os.remove(old)
    scene.render.filepath = os.path.join(out_dir, "f_")
    t0 = time.perf_counter()
    bpy.ops.render.render(animation=True)
    seconds = time.perf_counter() - t0
    written = sorted(glob.glob(os.path.join(out_dir, "f_*.png")))
    meta = {"layer": layer_id, "kind": layer["kind"], "source_file": os.path.basename(bpy.data.filepath),
            "blender": common.blender_version(), "devices_used": devices, "samples": scene.cycles.samples,
            "seed": 0, "denoiser": "OPENIMAGEDENOISE (CPU)", "film_transparent": True,
            "motion_blur_shutter": shutter, "motion_blur_position": "CENTER" if shutter else None,
            "view_transform": scene.view_settings.view_transform, "look": scene.view_settings.look,
            "exposure": float(scene.view_settings.exposure), "frames": [scene.frame_start, scene.frame_end],
            "scene_frames": [first, last], "files": len(written), "render_seconds": round(seconds, 1), **vis}
    common.write_json(os.path.join(out_dir, "layer_render.json"), meta)
    print(f"[oc] layer {layer_id}: {len(written)} frames in {seconds:.1f} s -> {out_dir}")
    return meta


def main() -> None:
    p = argparse.ArgumentParser(prog="render_layers")
    p.add_argument("--spec", required=True)
    p.add_argument("--layer", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--frames", default=None, help="Blender frame range a-b (default: the scene range)")
    p.add_argument("--device", default="OPTIX", choices=["OPTIX", "CUDA"])
    a = p.parse_args(common.script_args())
    render(a.spec, a.layer, a.out_dir, a.frames, a.device)


if __name__ == "__main__":
    main()
