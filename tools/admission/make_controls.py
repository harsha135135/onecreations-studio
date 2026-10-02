"""Turn a Blender export bundle's planar depth pass into a depth control video for video-model admission rungs.

    make_controls.py <bundle_dir> --out G:/onecreations/renders/diag_512x320x49/depth_control.mp4

Convention (proposed — compare with the target graph's own depth preprocessor before trusting results):
inverse planar depth, normalized per clip between its 1st and 99th percentiles, near = white, background (inf) = black,
8-bit gray encoded by ffmpeg as H.264 yuv420p, CRF 10, at the shot's output fps. A JSON sidecar next to the video
records the mapping and the bundle's content hash so the control is traceable to the exact export.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

CONVENTION = "inverse planar depth, per-clip p1-p99 normalization, near=white, background=black, 8-bit gray"


def depth_to_control(depth_m: np.ndarray, lo_pct: float = 1.0, hi_pct: float = 99.0) -> tuple[np.ndarray, dict]:
    """(F,H,W) planar depth in metres (inf = background) -> (F,H,W) uint8 control frames and the mapping used."""
    depth = np.asarray(depth_m, dtype=np.float64)
    finite = np.isfinite(depth) & (depth > 0)
    if not finite.any():
        raise ValueError("depth pass has no finite positive values")
    inv = np.zeros_like(depth)
    inv[finite] = 1.0 / depth[finite]
    lo, hi = np.percentile(inv[finite], [lo_pct, hi_pct])
    if hi <= lo:
        hi = lo + 1e-9
    norm = np.clip((inv - lo) / (hi - lo), 0.0, 1.0)
    norm[~finite] = 0.0
    frames = np.round(norm * 255.0).astype(np.uint8)
    meta = {"convention": CONVENTION, "inv_depth_lo": float(lo), "inv_depth_hi": float(hi),
            "near_m": float(1.0 / hi), "far_m": float(1.0 / lo) if lo > 0 else None,
            "background_fraction": float(1.0 - finite.mean())}
    return frames, meta


def encode_video(frames: np.ndarray, out: Path, fps: str) -> None:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FileNotFoundError("ffmpeg not on PATH")
    n, h, w = frames.shape
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
           "-s", f"{w}x{h}", "-r", fps, "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "10", str(out)]
    subprocess.run(cmd, input=np.ascontiguousarray(frames).tobytes(), check=True)


def main(argv: list[str] | None = None) -> int:
    from onecreations.blender_bundle import load_bundle

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("bundle", type=Path, help="export bundle directory (oc_export.py --passes)")
    p.add_argument("--out", type=Path, required=True, help="output .mp4")
    p.add_argument("--fps", default=None, help="override, e.g. 24 or 24000/1001 (default: the shot's output fps)")
    args = p.parse_args(argv)

    bundle = load_bundle(args.bundle)
    frames, meta = depth_to_control(bundle.passes()["depth_m"])
    rate = bundle.manifest.shot.output_fps
    fps = args.fps or f"{rate.num}/{rate.den}"
    encode_video(frames, args.out, fps)
    meta.update({"source_bundle": str(args.bundle), "source_content_sha256": bundle.manifest.content_sha256,
                 "frames": int(frames.shape[0]), "width": int(frames.shape[2]), "height": int(frames.shape[1]),
                 "fps": fps, "video": args.out.name})
    sidecar = args.out.with_suffix(".json")
    sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[make_controls] wrote {args.out} ({frames.shape[0]} frames {frames.shape[2]}x{frames.shape[1]}) + {sidecar.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
