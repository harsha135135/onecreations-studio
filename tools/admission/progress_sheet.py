"""Progress contact sheet: the same action-phase frames from several clips (any sizes), one labelled row per clip.

    progress_sheet.py --out sheet.png --frames 4,23,26,29,40 --frame-labels opening,apex,"fast swing",impact,recovery \
        --row "M2-B blockout (raw)=G:/.../ltx25_m2b_00001_.mp4" --row "SHOWCASE v1=G:/.../final.mp4" [--height 336]

Each clip is scaled to the tile height with Lanczos and centre-padded to the widest tile, so clips with different
aspect ratios line up without distortion. Labels are drawn with ffmpeg drawtext (Windows Arial, or the --font file).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import control_diagnostic as cd  # noqa: E402

LABEL_H = 34


def _scaled(video: Path, height: int, width: int, tmp: Path) -> np.ndarray:
    out = tmp / f"s_{abs(hash(str(video)))}.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-i", str(video), "-vf",
                    f"scale=-2:{height}:flags=lanczos,pad={width}:{height}:(ow-iw)/2:0", "-c:v", "libx264rgb", "-qp",
                    "0", "-pix_fmt", "rgb24", str(out)], check=True)
    return cd.decode_rgb(out)


def _probe_aspect(video: Path) -> float:
    w, h = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=width,height", "-of", "csv=p=0", str(video)], capture_output=True, text=True,
                          check=True).stdout.strip().split(",")[:2]
    return int(w) / int(h)


def _esc(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")


def build(rows: list[tuple[str, Path]], frames: list[int], frame_labels: list[str], out: Path, height: int = 336,
          font: str = "C\\:/Windows/Fonts/arialbd.ttf") -> Path:
    width = int(round(max(_probe_aspect(v) for _, v in rows) * height / 2)) * 2
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        strips = []
        for _, video in rows:
            v = _scaled(video, height, width, tmp)
            strips.append(np.concatenate([np.pad(v[min(f, len(v) - 1)], ((LABEL_H, 0), (0, 0), (0, 0)))
                                          for f in frames], axis=1))
        sheet = np.ascontiguousarray(np.concatenate(strips, axis=0))
        h, w = sheet.shape[:2]
        draws = []
        for r, (label, _) in enumerate(rows):
            y = r * (height + LABEL_H) + 8
            for c, fl in enumerate(frame_labels):
                text = f"{label}  |  {fl} (f{frames[c]})" if c == 0 else f"{fl} (f{frames[c]})"
                draws.append(f"drawtext=fontfile='{font}':text='{_esc(text)}':x={c * width + 10}:y={y}:fontsize=19:"
                             f"fontcolor=white")
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                        f"{w}x{h}", "-i", "-", "-vf", ",".join(draws), "-frames:v", "1", str(out)],
                       input=sheet.tobytes(), check=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--frame-labels", required=True)
    ap.add_argument("--row", action="append", required=True, help="LABEL=VIDEO")
    ap.add_argument("--height", type=int, default=336)
    ap.add_argument("--font", default="C\\:/Windows/Fonts/arialbd.ttf")
    a = ap.parse_args(argv)
    rows = [(r.split("=", 1)[0], Path(r.split("=", 1)[1])) for r in a.row]
    frames = [int(v) for v in a.frames.split(",")]
    labels = a.frame_labels.split(",")
    if len(labels) != len(frames):
        ap.error("one label per frame")
    print(build(rows, frames, labels, a.out, a.height, a.font))
    return 0


if __name__ == "__main__":
    sys.exit(main())
