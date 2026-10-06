"""Small video/image helpers for the director pipeline (ffmpeg on PATH; numpy only)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import numpy as np


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FileNotFoundError("ffmpeg not on PATH")
    return exe


def probe(path: Path) -> dict:
    out = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=width,height,nb_read_frames,r_frame_rate", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True).stdout.strip().split(",")
    w, h, rate, n = out[0], out[1], out[2], out[3]
    return {"width": int(w), "height": int(h), "fps": rate, "frames": int(n)}


def decode_rgb(path: Path) -> np.ndarray:
    info = probe(path)
    raw = subprocess.run([ffmpeg(), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, info["height"], info["width"], 3)


def encode_rgb(frames: np.ndarray, out: Path, fps: str = "24", lossless: bool = True) -> None:
    n, h, w, _ = frames.shape
    codec = ["-c:v", "libx264rgb", "-qp", "0", "-pix_fmt", "rgb24"] if lossless else \
        ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p"]
    subprocess.run([ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", fps,
                    "-i", "-", *codec, str(out)], input=np.ascontiguousarray(frames).tobytes(), check=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gray(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / d) if d > 1e-6 else 0.0


def match(template: np.ndarray, image: np.ndarray, x0: int, y0: int, radius: int) -> tuple[float, int, int]:
    """Best normalised cross-correlation of `template` (grey) placed with its top-left at (x0 + dx, y0 + dy),
    |dx|, |dy| <= radius, inside `image` (grey). Returns (ncc, dx, dy)."""
    th, tw = template.shape
    h, w = image.shape
    best = (-1.0, 0, 0)
    for dy in range(-radius, radius + 1):
        y = y0 + dy
        if y < 0 or y + th > h:
            continue
        for dx in range(-radius, radius + 1):
            x = x0 + dx
            if x < 0 or x + tw > w:
                continue
            v = ncc(template, image[y:y + th, x:x + tw])
            if v > best[0]:
                best = (v, dx, dy)
    return best


def bbox(mask: np.ndarray, pad: int = 0) -> tuple[int, int, int, int] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    h, w = mask.shape
    return (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad), min(w, int(xs.max()) + 1 + pad),
            min(h, int(ys.max()) + 1 + pad))
