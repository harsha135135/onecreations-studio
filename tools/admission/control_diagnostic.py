"""R2D control diagnostic: does a depth control carry the authored motion, and does a generated video follow it?

    # before any model run: ground truth + what the control itself contains
    control_diagnostic.py inspect <bundle> --control depth_control.mp4 --reference reference_preview.mp4 --out-dir DIR
    # after a run: compare the generated video with ground truth and the control
    control_diagnostic.py compare <bundle> --control depth_control.mp4 --reference reference_preview.mp4 \
        --generated out.mp4 --out-dir DIR

Deliberately simple evidence, no learned metric:
- ground truth per frame from the export bundle's object-index pass (centroid, bbox, area, median depth);
- the control's mean intensity inside each object's ground-truth mask (near = bright, so an approaching object brightens);
- colour-blob tracking (red box, blue ball) in the reference render and in the generated video;
- pre-registered rules (fixed before the R2D run) for "box followed" and "ball followed", and a PASS/PARTIAL/FAIL.
Writes <out-dir>/<mode>.json and a contact sheet PNG (rows: reference, control[, generated]) at 0/25/50/75/100 %.
Needs ffmpeg on PATH. Units: output pixels; "cells" are Union-guide latent cells (32 px x reference downscale 2).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

CHECKPOINTS = (0.0, 0.25, 0.5, 0.75, 1.0)
GUIDE_CELL_PX = 64                       # VAE 32 px x Union LoRA reference_downscale_factor 2
TRACKED = {"r2d_box": "red", "r2d_ball": "blue"}
BOX_MONOTONE_TOL_PX = 16.0               # pre-registered (plan 2026-10-02): allowed backwards jitter between checkpoints
BOX_MIN_TRAVEL_FRAC = 0.5                # generated travel >= 50 % of ground-truth travel
BALL_MIN_AREA_RATIO = 2.0                # generated end/start area >= 2x
BALL_MONOTONE_TOL = 0.15                 # area may dip <= 15 % between checkpoints


def checkpoint_frames(n_frames: int) -> list[int]:
    return [int(round(c * (n_frames - 1))) for c in CHECKPOINTS]


def mask_stats(mask: np.ndarray) -> dict | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    h, w = mask.shape
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    return {"cx": float(xs.mean()), "cy": float(ys.mean()), "bbox": [x0, y0, x1, y1],
            "w_px": x1 - x0 + 1, "h_px": y1 - y0 + 1, "w_cells": round((x1 - x0 + 1) / GUIDE_CELL_PX, 2),
            "area_px": int(len(xs)), "area_pct": round(100.0 * len(xs) / (h * w), 2)}


def color_mask(rgb: np.ndarray, color: str) -> np.ndarray:
    """Plain RGB-dominance masks for the flat red box / blue ball (uint8 HxWx3)."""
    c = rgb.astype(np.float32)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    if color == "red":
        return (r > 90) & (r > 1.6 * g) & (r > 1.6 * b)
    if color == "blue":
        return (b > 80) & (b > 1.4 * r) & (b > 1.15 * g)
    raise ValueError(f"unknown colour {color!r}")


def _ffmpeg_frames(path: Path, pix_fmt: str, channels: int) -> np.ndarray:
    exe = shutil.which("ffmpeg")
    probe = shutil.which("ffprobe")
    if not exe or not probe:
        raise FileNotFoundError("ffmpeg/ffprobe not on PATH")
    wh = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                         "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout.strip()
    w, h = (int(v) for v in wh.split(",")[:2])
    raw = subprocess.run([exe, "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", pix_fmt, "-"],
                         capture_output=True, check=True).stdout
    shape = (-1, h, w, channels) if channels > 1 else (-1, h, w)
    return np.frombuffer(raw, np.uint8).reshape(shape)


def decode_gray(path: Path) -> np.ndarray:
    return _ffmpeg_frames(path, "gray", 1)


def decode_rgb(path: Path) -> np.ndarray:
    return _ffmpeg_frames(path, "rgb24", 3)


def track_colors(frames_rgb: np.ndarray) -> dict[str, list[dict | None]]:
    return {oc: [mask_stats(color_mask(f, col)) for f in frames_rgb] for oc, col in TRACKED.items()}


def ground_truth(bundle) -> dict[str, list[dict | None]]:
    p = bundle.passes()
    idx, depth = p["object_index"], p["depth_m"]
    index_of = bundle.manifest.passes.object_index_map
    out = {}
    for oc in TRACKED:
        rows = []
        for f in range(idx.shape[0]):
            m = idx[f] == index_of[oc]
            s = mask_stats(m)
            if s is not None:
                s["median_depth_m"] = round(float(np.median(depth[f][m])), 3)
            rows.append(s)
        out[oc] = rows
    return out


def control_inside(control: np.ndarray, bundle) -> dict[str, list[float | None]]:
    idx = bundle.passes()["object_index"]
    index_of = bundle.manifest.passes.object_index_map
    n = min(len(control), len(idx))
    return {oc: [round(float(control[f][idx[f] == index_of[oc]].mean()) / 255.0, 4)
                 if (idx[f] == index_of[oc]).any() else None for f in range(n)] for oc in TRACKED}


def _series(track: list[dict | None], key: str, frames: list[int]) -> list[float | None]:
    return [(track[f] or {}).get(key) if f < len(track) else None for f in frames]


def classify(gen: dict[str, list[dict | None]], gt: dict[str, list[dict | None]], n_frames: int) -> dict:
    """Pre-registered rules (plan approved 2026-10-02, before the R2D run)."""
    cps = checkpoint_frames(n_frames)
    res = {"checkpoints": cps}
    bx, gx = _series(gen["r2d_box"], "cx", cps), _series(gt["r2d_box"], "cx", cps)
    box = {"generated_cx": bx, "gt_cx": gx}
    if any(v is None for v in bx):
        box.update(followed=None, reason="box not detected at every checkpoint (colour metric unavailable)")
    else:
        monotone = all(b2 >= b1 - BOX_MONOTONE_TOL_PX for b1, b2 in zip(bx, bx[1:]))
        travel, gt_travel = bx[-1] - bx[0], gx[-1] - gx[0]
        frac = travel / gt_travel if gt_travel else 0.0
        errs = [abs(b - g) for b, g in zip(bx, gx)]
        box.update(monotone=monotone, travel_px=round(travel, 1), gt_travel_px=round(gt_travel, 1),
                   travel_frac=round(frac, 3), abs_err_px=[round(e, 1) for e in errs],
                   within_one_cell=[e <= GUIDE_CELL_PX for e in errs],
                   followed=bool(monotone and frac >= BOX_MIN_TRAVEL_FRAC),
                   direction_correct=bool(travel > 0))
    res["box"] = box
    ba, ga = _series(gen["r2d_ball"], "area_px", cps), _series(gt["r2d_ball"], "area_px", cps)
    ball = {"generated_area_px": ba, "gt_area_px": ga}
    if any(v is None for v in ba):
        ball.update(followed=None, reason="ball not detected at every checkpoint (colour metric unavailable)")
    else:
        ratio, gt_ratio = ba[-1] / ba[0], ga[-1] / ga[0]
        nondecreasing = all(a2 >= (1.0 - BALL_MONOTONE_TOL) * a1 for a1, a2 in zip(ba, ba[1:]))
        ball.update(area_ratio=round(ratio, 2), gt_area_ratio=round(gt_ratio, 2), nondecreasing=nondecreasing,
                    followed=bool(ratio >= BALL_MIN_AREA_RATIO and nondecreasing),
                    direction_correct=bool(ratio > 1.0))
    res["ball"] = ball
    followed = [box.get("followed"), ball.get("followed")]
    if None in followed:
        res["metric_class"] = None
    elif all(followed):
        res["metric_class"] = "PASS"
    elif any(followed) or box.get("direction_correct") or ball.get("direction_correct"):
        res["metric_class"] = "PARTIAL"
    else:
        res["metric_class"] = "FAIL"
    res["note"] = "metric_class is evidence only; the final class also requires visual inspection to agree (plan)"
    return res


def contact_sheet(rows: list[np.ndarray], frames: list[int], out_png: Path, scale: float = 0.5) -> None:
    """rows: list of (F,H,W,3) uint8 videos; picks `frames` from each, tiles horizontally, stacks rows."""
    strips = []
    for video in rows:
        tiles = [video[min(f, len(video) - 1)] for f in frames]
        strips.append(np.concatenate(tiles, axis=1))
    sheet = np.ascontiguousarray(np.concatenate(strips, axis=0))
    h, w = sheet.shape[:2]
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FileNotFoundError("ffmpeg not on PATH")
    out_png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([exe, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-",
                    "-vf", f"scale=iw*{scale}:-1", "-frames:v", "1", str(out_png)], input=sheet.tobytes(), check=True)


def _gray_to_rgb(gray: np.ndarray) -> np.ndarray:
    return np.repeat(gray[..., None], 3, axis=-1)


def run(mode: str, bundle_dir: Path, control: Path, reference: Path, out_dir: Path, generated: Path | None) -> dict:
    from onecreations.blender_bundle import load_bundle

    bundle = load_bundle(bundle_dir)
    gt = ground_truth(bundle)
    ctrl = decode_gray(control)
    ref = decode_rgb(reference)
    n = len(gt["r2d_box"])
    cps = checkpoint_frames(n)
    report = {"mode": mode, "bundle": str(bundle_dir), "bundle_content_sha256": bundle.manifest.content_sha256,
              "frames": n, "checkpoints": cps, "guide_cell_px": GUIDE_CELL_PX,
              "ground_truth": {oc: [gt[oc][f] for f in cps] for oc in TRACKED},
              "control_mean_inside_gt_mask": {oc: [v[f] for f in cps] for oc, v in control_inside(ctrl, bundle).items()},
              "reference_tracking": classify(track_colors(ref), gt, n)}
    box0, box1 = gt["r2d_box"][0], gt["r2d_box"][-1]
    ball0, ball1 = gt["r2d_ball"][0], gt["r2d_ball"][-1]
    ci = report["control_mean_inside_gt_mask"]
    report["gate"] = {
        "box_travel_cells": round((box1["cx"] - box0["cx"]) / GUIDE_CELL_PX, 2),
        "ball_area_ratio": round(ball1["area_px"] / ball0["area_px"], 2),
        "ball_control_brightening": bool(all(b > a for a, b in zip(ci["r2d_ball"], ci["r2d_ball"][1:]))),
    }
    report["gate"]["passed"] = bool(report["gate"]["box_travel_cells"] >= 4 and report["gate"]["ball_area_ratio"] >= 4
                                    and report["gate"]["ball_control_brightening"])
    rows = [ref, _gray_to_rgb(ctrl)]
    if generated is not None:
        gen = decode_rgb(generated)
        report["generated"] = str(generated)
        report["generated_frames"] = int(len(gen))
        tracked = track_colors(gen)
        report["generated_full_series"] = {oc: [(s or {}).get("cx" if oc == "r2d_box" else "area_px") for s in tr]
                                           for oc, tr in tracked.items()}
        report["comparison"] = classify(tracked, gt, n)
        rows.append(gen)
    out_dir.mkdir(parents=True, exist_ok=True)
    contact_sheet(rows, cps, out_dir / f"{mode}_contact_sheet.png")
    (out_dir / f"{mode}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["inspect", "compare"])
    p.add_argument("bundle", type=Path)
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--generated", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, required=True)
    a = p.parse_args(argv)
    if a.mode == "compare" and a.generated is None:
        p.error("compare needs --generated")
    rep = run(a.mode, a.bundle, a.control, a.reference, a.out_dir, a.generated)
    print(json.dumps({"gate": rep["gate"], "reference_metric": rep["reference_tracking"]["metric_class"],
                      "comparison": (rep.get("comparison") or {}).get("metric_class")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
