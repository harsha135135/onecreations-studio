"""Render a controlled shot's Blender beauty reference: first_frame.png (frame 1) and reference_preview.mp4 (all frames).

    blender -b scene.blend --factory-startup --python render_reference.py -- --out-dir DIR [--samples 64]
        [--device OPTIX] [--keep-frames] [--motion-blur 0.5 --name reference_motionblur]

Cycles on the GPU (OptiX by default), fixed seed, OpenImageDenoise on the CPU, no motion blur, and the view transform
the scene sets (Standard for the M2 scenes). first_frame.png is frame 1 of the same render (the LTX first-frame
conditioning image). The preview is encoded losslessly (libx264rgb -qp 0, rgb24), so the analysis decodes exactly what
Blender rendered. A sidecar render_reference.json records the settings, the Blender version, the GPU device(s) used and
the SHA-256 of both outputs. Needs ffmpeg on PATH. Replaces the ad-hoc reference renders used up to M2-A.
--motion-blur SHUTTER (frames, centred) renders a matched motion-blur reference instead: DIR/<name>.mp4 + <name>.json,
no first frame (M3-A: separates legitimate blur of fast motion from generative ghosting).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import oc_blender_common as common  # noqa: E402


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def use_gpu(device_type: str) -> list[str]:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = device_type
    prefs.get_devices()
    used = []
    for d in prefs.devices:
        d.use = d.type == device_type
        if d.use:
            used.append(f"{d.name} ({d.type})")
    if not used:
        raise RuntimeError(f"no {device_type} device available")
    return used


def render(out_dir: str, samples: int, device_type: str, keep_frames: bool, motion_blur: float | None = None,
           name: str = "reference_preview") -> dict:
    scene = bpy.context.scene
    devices = use_gpu(device_type)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "denoising_use_gpu"):
        scene.cycles.denoising_use_gpu = False
    scene.render.use_motion_blur = bool(motion_blur)
    if motion_blur:
        scene.render.motion_blur_shutter = float(motion_blur)
        scene.render.motion_blur_position = "CENTER"
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"

    out_dir = os.path.abspath(out_dir)
    frames_dir = os.path.join(out_dir, f"_{name}_frames")
    shutil.rmtree(frames_dir, ignore_errors=True)
    os.makedirs(frames_dir)
    scene.render.filepath = os.path.join(frames_dir, "f_")
    t0 = time.perf_counter()
    bpy.ops.render.render(animation=True)
    seconds = time.perf_counter() - t0
    frames = sorted(glob.glob(os.path.join(frames_dir, "f_*.png")))
    expected = scene.frame_end - scene.frame_start + 1
    if len(frames) != expected:
        raise RuntimeError(f"rendered {len(frames)} frames, expected {expected}")

    first = os.path.join(out_dir, "first_frame.png")
    if not motion_blur:
        shutil.copyfile(frames[0], first)
    preview = os.path.join(out_dir, f"{name}.mp4")
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FileNotFoundError("ffmpeg not on PATH")
    fps = common.scene_fps(scene)
    subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-framerate", f"{fps.numerator}/{fps.denominator}",
                    "-start_number", str(scene.frame_start), "-i", os.path.join(frames_dir, "f_%04d.png"),
                    "-c:v", "libx264rgb", "-qp", "0", "-pix_fmt", "rgb24", preview], check=True)
    if not keep_frames:
        shutil.rmtree(frames_dir, ignore_errors=True)

    meta = {"source_file": os.path.basename(bpy.data.filepath), "blender": common.blender_version(),
            "engine": "CYCLES", "device": device_type, "devices_used": devices, "samples": samples, "seed": 0,
            "adaptive_sampling": False, "denoiser": "OPENIMAGEDENOISE (CPU)",
            "motion_blur": {"shutter": float(motion_blur), "position": "CENTER"} if motion_blur else False,
            "view_transform": scene.view_settings.view_transform, "look": scene.view_settings.look,
            "exposure": float(scene.view_settings.exposure),
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "frames": [scene.frame_start, scene.frame_end], "fps": f"{fps.numerator}/{fps.denominator}",
            "render_seconds": round(seconds, 1),
            "reference_preview": {"file": f"{name}.mp4", "codec": "libx264rgb -qp 0 (lossless, rgb24)",
                                  "sha256": sha256(preview)}}
    if not motion_blur:
        meta["first_frame"] = {"file": "first_frame.png", "blender_frame": scene.frame_start, "sha256": sha256(first)}
    common.write_json(os.path.join(out_dir, "render_reference.json" if not motion_blur else f"{name}.json"), meta)
    print(f"[oc] reference rendered: {len(frames)} frames in {seconds:.1f} s on {devices} -> {out_dir}")
    return meta


def main() -> None:
    p = argparse.ArgumentParser(prog="render_reference")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--device", default="OPTIX", choices=["OPTIX", "CUDA"])
    p.add_argument("--keep-frames", action="store_true")
    p.add_argument("--motion-blur", type=float, default=None, help="shutter in frames (e.g. 0.5); default off")
    p.add_argument("--name", default=None, help="output basename (default reference_preview, or "
                                                 "reference_motionblur with --motion-blur)")
    a = p.parse_args(common.script_args())
    name = a.name or ("reference_motionblur" if a.motion_blur else "reference_preview")
    render(a.out_dir, a.samples, a.device, a.keep_frames, a.motion_blur, name)


if __name__ == "__main__":
    main()
