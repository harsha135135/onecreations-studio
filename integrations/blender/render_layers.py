"""Render a composite layer of an authored scene (contract: onecreations.contracts.composite.CompositeManifest).

    blender -b scene.blend --factory-startup --python render_layers.py -- --spec shot_spec.json --layer mace_protect \
        --out-dir DIR [--frames 1-49] [--device OPTIX]

The layer's objects (oc_ids) and collections render normally; every other mesh is a HOLDOUT (it still occludes the
layer and casts shadows/bounce light on it, but renders as transparent), so occlusion by the actor or environment is
exact. Volume-only helpers (the haze box) are hidden, since a volume would fill the alpha. Transparent film, fixed
seed, OIDN, optional Blender motion blur (shutter in frames, centred on the frame). Writes DIR/f_####.png (RGBA,
straight alpha, Blender frame numbers) and DIR/layer_render.json.
Volume objects that belong to the layer (e.g. dust volumes in an effect collection) are kept.
render.light_only (showcase on): a LIGHT pass instead - only the listed lights (in the layer's collections) on, all
other lights hidden, world strength 0, every material's emission 0, opaque film, all meshes and the haze visible, no
holdouts. Composited additively (blend 'add'), e.g. an impact flash lighting the floor, actors and haze.
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


def setup_light_pass(scene, layer: dict) -> dict:
    view_layer = bpy.context.view_layer
    for name in layer.get("collections", []):
        view_layer.layer_collection.children[name].exclude = False
    keep = set(layer["render"]["light_only"])
    off = []
    for o in scene.objects:
        if o.type == "LIGHT" and o.name not in keep:
            o.hide_render = True
            off.append(o.name)
    if scene.world and scene.world.use_nodes:
        for n in scene.world.node_tree.nodes:
            if n.type == "BACKGROUND":
                n.inputs["Strength"].default_value = 0.0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for n in mat.node_tree.nodes:
            if n.type == "EMISSION":
                n.inputs["Strength"].default_value = 0.0
            elif n.type == "BSDF_PRINCIPLED":
                n.inputs["Emission Strength"].default_value = 0.0
    return {"lights_on": sorted(keep), "lights_off": sorted(off), "world": "strength 0", "emission": "0"}


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
        in_layer = (("oc_id" in o.keys() and str(o["oc_id"]) in keep) or o.name in enabled)
        if common.is_volume_only(o) and not in_layer:
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
    light_pass = bool(r.get("light_only"))
    scene.render.film_transparent = not light_pass
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
    vis = setup_light_pass(scene, layer) if light_pass else setup_layer(scene, layer)
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
            "seed": 0, "denoiser": "OPENIMAGEDENOISE (CPU)", "film_transparent": not light_pass,
            "light_pass": light_pass,
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
