"""Final finishing pass for a composited shot (showcase on): a restrained, reproducible grade.

    finish_grade.py --input hybrid.mp4 --out-dir DIR [--params '{"contrast": 1.05}'] [--name final]

1. Optional camera-response shake in POST (output frames -> integer pixel offsets, edge-clamped). It never touches the
   authored camera, the control or the generation; it is listed in the sidecar.
2. One ffmpeg filter chain built from PARAMS: eq (contrast / brightness / saturation / gamma), colorbalance (cool
   shadows, warm highlights), vignette, unsharp (luma only), temporal grain with a fixed seed.
Outputs: DIR/<name>_master.mp4 (lossless rgb), DIR/<name>.mp4 (H.264 crf 12, yuv420p, for viewing) and
DIR/<name>.json (params, the exact filter chain, input/output SHA-256).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import control_diagnostic as cd  # noqa: E402

DEFAULT = {"contrast": 1.05, "brightness": 0.0, "saturation": 1.0, "gamma": 1.0, "shadows_cool": 0.03,
           "highlights_warm": 0.03, "vignette_angle": 0.45, "sharpen": 0.35, "grain": 3, "grain_seed": 1000,
           "shake": []}                  # shake: [[output_frame, dx_px, dy_px], ...]


def filter_chain(p: dict) -> str:
    parts = [f"eq=contrast={p['contrast']}:brightness={p['brightness']}:saturation={p['saturation']}:gamma={p['gamma']}"]
    if p["shadows_cool"] or p["highlights_warm"]:
        c, w = p["shadows_cool"], p["highlights_warm"]
        parts.append(f"colorbalance=rs={-c}:bs={c}:rh={w}:bh={-w}")
    if p["vignette_angle"]:
        parts.append(f"vignette=angle={p['vignette_angle']}")
    if p["sharpen"]:
        parts.append(f"unsharp=lx=5:ly=5:la={p['sharpen']}:cx=3:cy=3:ca=0")
    if p["grain"]:
        parts.append(f"format=yuv444p,noise=c0s={p['grain']}:c0f=t:all_seed={p['grain_seed']}")   # luma grain
    return ",".join(parts)


def shake(frames: np.ndarray, offsets: list) -> np.ndarray:
    """Shift listed frames by integer (dx, dy) pixels, clamping at the edges (no black borders)."""
    out = frames.copy()
    n, h, w, _ = frames.shape
    for f, dx, dy in offsets:
        if not 0 <= f < n:
            continue
        ys = np.clip(np.arange(h) - int(dy), 0, h - 1)
        xs = np.clip(np.arange(w) - int(dx), 0, w - 1)
        out[f] = frames[f][ys][:, xs]
    return out


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(inp: Path, out_dir: Path, params: dict | None = None, name: str = "final", fps: str = "24") -> dict:
    p = dict(DEFAULT, **(params or {}))
    frames = shake(cd.decode_rgb(inp), p["shake"])
    n, h, w, _ = frames.shape
    out_dir.mkdir(parents=True, exist_ok=True)
    chain = filter_chain(p)
    master, view = out_dir / f"{name}_master.mp4", out_dir / f"{name}.mp4"
    ff = shutil.which("ffmpeg")
    src = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", fps, "-i", "-"]
    raw = np.ascontiguousarray(frames).tobytes()
    subprocess.run([ff, "-v", "error", "-y", *src, "-vf", chain, "-c:v", "libx264rgb", "-qp", "0", "-pix_fmt", "rgb24",
                    str(master)], input=raw, check=True)
    subprocess.run([ff, "-v", "error", "-y", "-i", str(master), "-c:v", "libx264", "-crf", "12", "-preset", "slow",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(view)], check=True)
    meta = {"input": str(inp), "input_sha256": _sha(inp), "frames": n, "size": [w, h], "params": p,
            "filter_chain": chain, "master": master.name, "master_sha256": _sha(master), "view": view.name,
            "view_sha256": _sha(view), "note": "post-only finish; the shake (if any) does not alter the authored camera"}
    (out_dir / f"{name}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--params", default=None, help="JSON overrides of DEFAULT")
    ap.add_argument("--name", default="final")
    a = ap.parse_args(argv)
    meta = run(a.input, a.out_dir, json.loads(a.params) if a.params else None, a.name)
    print(json.dumps({k: meta[k] for k in ("frames", "size", "filter_chain", "view")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
