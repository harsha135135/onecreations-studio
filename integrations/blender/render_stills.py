"""Render selected frames of a scene as PNG stills (look development / review; not a reference render).

    blender -b scene.blend --factory-startup --python render_stills.py -- --out-dir DIR --frames 1,24,30 \
        [--samples 64] [--device OPTIX] [--percent 100] [--motion-blur 0.5]

Cycles on the GPU, fixed seed, OIDN (CPU). Writes DIR/still_####.png (Blender frame numbers) and DIR/stills.json
(settings + seconds per frame). Reference renders for the pipeline still come from render_reference.py.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import oc_blender_common as common  # noqa: E402
import render_reference  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(prog="render_stills")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--frames", required=True, help="comma-separated Blender frames")
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--device", default="OPTIX", choices=["OPTIX", "CUDA"])
    p.add_argument("--percent", type=int, default=100)
    p.add_argument("--motion-blur", type=float, default=None)
    a = p.parse_args(common.script_args())
    scene = bpy.context.scene
    devices = render_reference.use_gpu(a.device)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = a.samples
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.seed = 0
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "denoising_use_gpu"):
        scene.cycles.denoising_use_gpu = False
    scene.render.use_motion_blur = bool(a.motion_blur)
    if a.motion_blur:
        scene.render.motion_blur_shutter = a.motion_blur
        scene.render.motion_blur_position = "CENTER"
    scene.render.resolution_percentage = a.percent
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    os.makedirs(a.out_dir, exist_ok=True)
    times = {}
    for f in (int(v) for v in a.frames.split(",")):
        scene.frame_set(f)
        scene.render.filepath = os.path.join(os.path.abspath(a.out_dir), f"still_{f:04d}.png")
        t0 = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        times[str(f)] = round(time.perf_counter() - t0, 1)
        print(f"[oc] still {f}: {times[str(f)]} s")
    common.write_json(os.path.join(a.out_dir, "stills.json"),
                      {"source_file": os.path.basename(bpy.data.filepath), "devices_used": devices,
                       "samples": a.samples, "percent": a.percent, "motion_blur": a.motion_blur, "seconds": times,
                       "view_transform": scene.view_settings.view_transform, "look": scene.view_settings.look})


if __name__ == "__main__":
    main()
