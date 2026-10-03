"""Control diagnostic: does a depth control carry the authored motion, and does a generated video follow it?

    # before any model run: ground truth + what the control itself contains (+ the pre-LTX gate)
    control_diagnostic.py inspect <bundle> --control depth_control.mp4 --reference reference_preview.mp4 \
        --out-dir DIR [--spec shot_spec.json]
    # after a run: compare the generated video with ground truth and the control
    control_diagnostic.py compare <bundle> --control ... --reference ... --generated out.mp4 --out-dir DIR [--spec ...]

The tracking spec (the "tracking" section of a scene's spec JSON, written before any run) names the subjects
(oc_id -> colour rule, role, checks with thresholds), the ground objects, the static structures and the gate.
Without --spec the R2D rules apply unchanged (red box: lateral; blue ball: approach).

Deliberately simple evidence, no learned metric:
- ground truth per frame from the export bundle's object-index pass (centroid, bbox, area, coverage in guide cells,
  median depth) and occlusion (nearer non-ground objects inside the subject's bbox);
- the control's mean intensity inside each subject mask, and its contrast against a ring around the subject;
- colour-blob tracking in the Blender reference (validates the tracker) and in the generated video;
- pre-registered checks -> PASS/PARTIAL/FAIL metric class (the final class also needs visual agreement):
  `lateral` and `approach` (M2-A), `position` (a stationary-root body: displacement from frame 0 and relative area
  follow GT) and `timing` (a weapon's apex and contact frames, excursion and swing direction vs GT; M2-B);
- with a "joints" section (M2-B): the weapon bone's projected tail vs its object-index centroid, stationary bones,
  and agreement of the exported motion's events with the ActionTimeline phase boundaries;
- static-structure drift (mean |frame_t - frame_0| over static structures away from subjects) — REPORT-ONLY:
  lighting, texture, shadow or generative appearance changes must not fail coherence on their own.
Writes <out-dir>/<mode>.json and a contact sheet PNG (rows: reference, control[, generated]) at 0/25/50/75/100 %,
plus an event contact sheet (GT apex - 2 ... contact + 2) when a subject has a `timing` check.
Needs ffmpeg on PATH. Units: output pixels; "cells" are Union-guide latent cells (32 px x reference downscale 2).
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

CHECKPOINTS = (0.0, 0.25, 0.5, 0.75, 1.0)
GUIDE_CELL_PX = 64                       # VAE 32 px x Union LoRA reference_downscale_factor 2
CELL_AREA = GUIDE_CELL_PX * GUIDE_CELL_PX
RING_PX = 12                             # control-contrast ring width around a subject
OCCLUSION_FRAC = 0.005                   # nearer-object pixels inside the bbox above this fraction = occluded
DRIFT_MARGIN_PX = 8                      # keep static-drift pixels this far away from any subject bbox

# R2D (2026-10-02) rules, pre-registered before that run; the default when no spec is given.
R2D_TRACKING = {
    "subjects": {
        "r2d_box": {"color": "red", "role": "primary",
                    "checks": {"lateral": {"monotone_tol_px": 16.0, "min_travel_frac": 0.5}}},
        "r2d_ball": {"color": "blue", "role": "primary",
                     "checks": {"approach": {"min_ratio": 2.0, "monotone_tol": 0.15}}},
    },
    "ground": [], "static_structures": [], "gate": {"legacy_r2d": True},
}


def load_tracking(spec_path: Path | None) -> dict:
    if spec_path is None:
        return copy.deepcopy(R2D_TRACKING)
    return tracking_from_spec(json.loads(Path(spec_path).read_text(encoding="utf-8")), spec_path)


def tracking_from_spec(spec: dict, spec_path=None) -> dict:
    tracking = spec.get("tracking")
    if not tracking or not tracking.get("subjects"):
        raise ValueError(f"{spec_path}: no tracking.subjects section")
    tracking.setdefault("ground", [])
    tracking.setdefault("static_structures", [])
    tracking.setdefault("gate", {})
    return tracking


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
            "h_cells": round((y1 - y0 + 1) / GUIDE_CELL_PX, 2), "area_px": int(len(xs)),
            "area_cells": round(len(xs) / CELL_AREA, 2), "area_pct": round(100.0 * len(xs) / (h * w), 2)}


def color_mask(rgb: np.ndarray, color: str) -> np.ndarray:
    """Plain RGB-dominance masks for flat red / blue / gold subjects (uint8 HxWx3). `gold` needs strong R and G
    over B (b < 0.55 g), which keeps warm sunlit stone (b ~ 0.75 g) out."""
    c = rgb.astype(np.float32)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    if color == "red":
        return (r > 90) & (r > 1.6 * g) & (r > 1.6 * b)
    if color == "blue":
        return (b > 80) & (b > 1.4 * r) & (b > 1.15 * g)
    if color == "gold":
        return (r > 100) & (g > 60) & (r >= g) & (g > 0.45 * r) & (b < 0.55 * g)
    raise ValueError(f"unknown colour {color!r}")


def dilate(mask: np.ndarray, r: int) -> np.ndarray:
    """Square binary dilation by r pixels (separable, numpy only)."""
    out = mask.copy()
    for axis in (0, 1):
        acc = out.copy()
        for s in range(1, r + 1):
            acc |= np.roll(out, s, axis=axis) & _valid(out.shape, s, axis)
            acc |= np.roll(out, -s, axis=axis) & _valid(out.shape, -s, axis)
        out = acc
    return out


def _valid(shape, shift: int, axis: int) -> np.ndarray:
    v = np.ones(shape, bool)
    idx = [slice(None)] * 2
    idx[axis] = slice(0, shift) if shift > 0 else slice(shape[axis] + shift, shape[axis])
    v[tuple(idx)] = False
    return v


def occlusion_fraction(idx: np.ndarray, depth: np.ndarray, subject: int, ignore: set[int]) -> float:
    """Fraction of the subject's bbox covered by other (non-ignored) objects nearer than the subject."""
    m = idx == subject
    s = mask_stats(m)
    if s is None:
        return 0.0
    x0, y0, x1, y1 = s["bbox"]
    sub_near = float(depth[m].min())
    box_idx, box_depth = idx[y0:y1 + 1, x0:x1 + 1], depth[y0:y1 + 1, x0:x1 + 1]
    other = (box_idx != subject) & (box_idx != 0) & ~np.isin(box_idx, list(ignore)) & (box_depth < sub_near - 0.05)
    return float(other.sum()) / box_idx.size


def control_contrast(control: np.ndarray, mask: np.ndarray, ring_px: int = RING_PX) -> float | None:
    if not mask.any():
        return None
    ring = dilate(mask, ring_px) & ~mask
    if not ring.any():
        return None
    return round(float(control[mask].mean() - control[ring].mean()) / 255.0, 4)


def static_drift(frames: np.ndarray, static_mask: np.ndarray, frame_ids: list[int]) -> list[float | None]:
    """Mean |frame_t - frame_0| / 255 over static_mask (REPORT-ONLY coherence evidence)."""
    if not static_mask.any():
        return [None for _ in frame_ids]
    f0 = frames[0].astype(np.float32)
    return [round(float(np.abs(frames[min(f, len(frames) - 1)].astype(np.float32) - f0)[static_mask].mean()) / 255.0, 4)
            for f in frame_ids]


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


def track_colors(frames_rgb: np.ndarray, subjects: dict) -> dict[str, list[dict | None]]:
    return {oc: [mask_stats(color_mask(f, cfg["color"])) for f in frames_rgb] for oc, cfg in subjects.items()}


def ground_truth(bundle, subjects: dict) -> dict[str, list[dict | None]]:
    p = bundle.passes()
    idx, depth = p["object_index"], p["depth_m"]
    index_of = bundle.manifest.passes.object_index_map
    out = {}
    for oc in subjects:
        rows = []
        for f in range(idx.shape[0]):
            m = idx[f] == index_of[oc]
            s = mask_stats(m)
            if s is not None:
                s["median_depth_m"] = round(float(np.median(depth[f][m])), 3)
            rows.append(s)
        out[oc] = rows
    return out


def _series(track: list[dict | None], key: str, frames: list[int]) -> list[float | None]:
    return [(track[f] or {}).get(key) if f < len(track) else None for f in frames]


def check_lateral(gen: list, gt: list, cps: list[int], params: dict) -> dict:
    gx, tx = _series(gen, "cx", cps), _series(gt, "cx", cps)
    out = {"generated_cx": gx, "gt_cx": tx}
    if any(v is None for v in gx) or any(v is None for v in tx):
        return dict(out, followed=None, reason="not detected at every checkpoint (colour metric unavailable)")
    tol = float(params.get("monotone_tol_px", 16.0))
    sign = 1.0 if tx[-1] >= tx[0] else -1.0           # authored direction from ground truth
    monotone = all(sign * (b - a) >= -tol for a, b in zip(gx, gx[1:]))
    travel, gt_travel = gx[-1] - gx[0], tx[-1] - tx[0]
    frac = travel / gt_travel if gt_travel else 0.0
    errs = [abs(a - b) for a, b in zip(gx, tx)]
    return dict(out, monotone=monotone, travel_px=round(travel, 1), gt_travel_px=round(gt_travel, 1),
                travel_frac=round(frac, 3), abs_err_px=[round(e, 1) for e in errs],
                abs_err_cells=[round(e / GUIDE_CELL_PX, 2) for e in errs],
                within_one_cell=[e <= GUIDE_CELL_PX for e in errs],
                direction_correct=bool(sign * travel > 0),
                followed=bool(monotone and frac >= float(params.get("min_travel_frac", 0.5))))


def check_approach(gen: list, gt: list, cps: list[int], params: dict) -> dict:
    ga, ta = _series(gen, "area_px", cps), _series(gt, "area_px", cps)
    out = {"generated_area_px": ga, "gt_area_px": ta}
    if any(v is None for v in ga) or any(v is None for v in ta):
        return dict(out, followed=None, reason="not detected at every checkpoint (colour metric unavailable)")
    ratio, gt_ratio = ga[-1] / ga[0], ta[-1] / ta[0]
    tol = float(params.get("monotone_tol", 0.15))
    nondecreasing = all(b >= (1.0 - tol) * a for a, b in zip(ga, ga[1:]))
    if "min_ratio" in params:
        threshold = float(params["min_ratio"])
    else:
        threshold = 1.0 + float(params.get("min_gain_frac", 0.5)) * (gt_ratio - 1.0)
    return dict(out, area_ratio=round(ratio, 3), gt_area_ratio=round(gt_ratio, 3), threshold=round(threshold, 3),
                nondecreasing=nondecreasing, direction_correct=bool((ratio - 1.0) * (gt_ratio - 1.0) > 0),
                followed=bool(ratio >= threshold and nondecreasing))


def check_position(gen: list, gt: list, cps: list[int], params: dict) -> dict:
    """Stationary-root body: displacement from frame 0 and area relative to frame 0 follow GT at every checkpoint.

    Relative to frame 0, so a constant colour-tracker offset (non-red parts in the GT mask) cancels. Catches invented
    translation and a body that breaks up or vanishes."""
    g, t = ([track[f] if f < len(track) else None for f in cps] for track in (gen, gt))
    out = {"generated_cx": [(r or {}).get("cx") for r in g], "generated_cy": [(r or {}).get("cy") for r in g],
           "gt_cx": [(r or {}).get("cx") for r in t], "gt_cy": [(r or {}).get("cy") for r in t]}
    if any(r is None for r in g) or any(r is None for r in t):
        return dict(out, followed=None, reason="not detected at every checkpoint (colour metric unavailable)")
    tol, area_tol = float(params.get("tol_px", 32.0)), float(params.get("area_tol", 0.25))
    disp = [max(abs((a["cx"] - g[0]["cx"]) - (b["cx"] - t[0]["cx"])),
                abs((a["cy"] - g[0]["cy"]) - (b["cy"] - t[0]["cy"]))) for a, b in zip(g, t)]
    area = [abs((a["area_px"] / g[0]["area_px"]) / (b["area_px"] / t[0]["area_px"]) - 1.0) for a, b in zip(g, t)]
    ok = all(d <= tol for d in disp)
    return dict(out, displacement_err_px=[round(d, 1) for d in disp], relative_area_err=[round(a, 3) for a in area],
                abs_err_px=[round(math.hypot(a["cx"] - b["cx"], a["cy"] - b["cy"]), 1) for a, b in zip(g, t)],
                tol_px=tol, area_tol=area_tol, direction_correct=ok,
                followed=bool(ok and all(a <= area_tol for a in area)))


def strike_events(track: list[dict | None], stop_px: float = 4.0) -> dict | None:
    """Events of a downward strike in a per-frame track. apex = highest on screen (min cy). contact = the first frame
    after the fastest frame-to-frame move following the apex from which the subject moves <= stop_px to the next
    frame (it stops). 2D speed, not vertical speed, so a final sideways settle is not taken for the stop."""
    pts = [(s["cx"], s["cy"]) if s else None for s in track]
    det = [i for i, q in enumerate(pts) if q is not None]
    if len(det) < 3:
        return None
    apex = min(det, key=lambda i: (pts[i][1], i))
    speed = {i: math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
             for i in range(apex, len(pts) - 1) if pts[i] is not None and pts[i + 1] is not None}
    ev = {"apex": apex, "contact": None, "peak_speed_frame": None, "peak_speed_px": None, "excursion_px": None,
          "dx_px": None}
    if not speed:
        return ev
    peak = max(speed, key=lambda i: (speed[i], -i))
    contact = next((i for i in sorted(speed) if i > peak and speed[i] <= stop_px), None)
    ev.update(peak_speed_frame=peak, peak_speed_px=round(speed[peak], 1), contact=contact)
    if contact is not None:
        ev.update(excursion_px=round(pts[contact][1] - pts[apex][1], 1), dx_px=round(pts[contact][0] - pts[apex][0], 1))
    return ev


def check_timing(gen: list, gt: list, cps: list[int], params: dict) -> dict:
    """A weapon's strike: apex and contact frames within tol_frames of GT, a downswing (apex before contact) with
    excursion >= min_excursion_frac of GT, the swing's x direction when GT moves >= min_dx_px sideways, and the
    subject detected in >= min_detect_frac of the frames. Uses every frame, not only the checkpoints."""
    stop = float(params.get("stop_px", 4.0))
    ev_g, ev_t = strike_events(gen, stop), strike_events(gt, stop)
    detected = sum(s is not None for s in gen) / max(len(gen), 1)
    out = {"generated_events": ev_g, "gt_events": ev_t, "detected_frac": round(detected, 3)}
    if ev_t is None or ev_t["contact"] is None:
        return dict(out, followed=None, reason="no strike events in ground truth")
    if detected < float(params.get("min_detect_frac", 0.9)) or ev_g is None:
        return dict(out, followed=None, reason="detected in too few frames (colour metric unavailable)")
    if ev_g["contact"] is None:
        return dict(out, followed=False, direction_correct=False, reason="no stop after the fastest move")
    tol = int(params.get("tol_frames", 2))
    d_apex, d_contact = ev_g["apex"] - ev_t["apex"], ev_g["contact"] - ev_t["contact"]
    exc_frac = ev_g["excursion_px"] / ev_t["excursion_px"] if ev_t["excursion_px"] else 0.0
    dx_applicable = abs(ev_t["dx_px"]) >= float(params.get("min_dx_px", 32.0))
    dx_ok = (not dx_applicable) or (ev_g["dx_px"] * ev_t["dx_px"] > 0)
    downswing = ev_g["excursion_px"] > 0 and ev_g["apex"] < ev_g["contact"]
    return dict(out, apex_offset_frames=d_apex, contact_offset_frames=d_contact, excursion_frac=round(exc_frac, 3),
                dx_check_applicable=dx_applicable, dx_ok=dx_ok, tol_frames=tol,
                direction_correct=bool(downswing and dx_ok),
                followed=bool(abs(d_apex) <= tol and abs(d_contact) <= tol and downswing and dx_ok
                              and exc_frac >= float(params.get("min_excursion_frac", 0.5))))


CHECKS = {"lateral": check_lateral, "approach": check_approach, "position": check_position, "timing": check_timing}


def classify(gen: dict, gt: dict, n_frames: int, tracking: dict) -> dict:
    """Apply each subject's pre-registered checks; metric class from the primary subjects."""
    cps = checkpoint_frames(n_frames)
    res = {"checkpoints": cps, "subjects": {}}
    followed, directions = [], []
    for oc, cfg in tracking["subjects"].items():
        sub = {"role": cfg.get("role", "primary"), "checks": {}}
        for name, params in cfg.get("checks", {}).items():
            if name == "report_only":
                sub["checks"][name] = {"area_px": _series(gen[oc], "area_px", cps),
                                       "cx": _series(gen[oc], "cx", cps), "gt_area_px": _series(gt[oc], "area_px", cps)}
                continue
            r = CHECKS[name](gen[oc], gt[oc], cps, params)
            sub["checks"][name] = r
            if sub["role"] == "primary":
                followed.append(r.get("followed"))
                directions.append(r.get("direction_correct", False))
        res["subjects"][oc] = sub
    if not followed or None in followed:
        res["metric_class"] = None
    elif all(followed):
        res["metric_class"] = "PASS"
    elif any(followed) or any(directions):
        res["metric_class"] = "PARTIAL"
    else:
        res["metric_class"] = "FAIL"
    res["note"] = "metric_class is evidence only; the final class also requires visual agreement"
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


def _legacy_r2d_gate(gt: dict, inside: dict) -> dict:
    box0, box1 = gt["r2d_box"][0], gt["r2d_box"][-1]
    ball0, ball1 = gt["r2d_ball"][0], gt["r2d_ball"][-1]
    gate = {"box_travel_cells": round((box1["cx"] - box0["cx"]) / GUIDE_CELL_PX, 2),
            "ball_area_ratio": round(ball1["area_px"] / ball0["area_px"], 2),
            "ball_control_brightening": bool(all(b > a for a, b in zip(inside["r2d_ball"], inside["r2d_ball"][1:])))}
    gate["passed"] = bool(gate["box_travel_cells"] >= 4 and gate["ball_area_ratio"] >= 4
                          and gate["ball_control_brightening"])
    return gate


def in_frame(row: dict | None, width: int, height: int) -> bool:
    """True when the subject's bbox does not touch the image border (it is not cut by the frame)."""
    if row is None:
        return False
    x0, y0, x1, y1 = row["bbox"]
    return x0 > 0 and y0 > 0 and x1 < width - 1 and y1 < height - 1


def joint_checks(heads: np.ndarray, tails: np.ndarray, bones: list[str], c2w: np.ndarray, k: np.ndarray,
                 weapon_track: list[dict | None], cfg: dict) -> dict:
    """First real-scene use of joints.npz: the weapon bone's tail projected with the shared camera model vs the weapon
    object's object-index centroid (pixel centres at +0.5), stationary bones, and the weapon's 3D height events."""
    from onecreations.geometry.intrinsics import project

    w = bones.index(cfg["weapon_bone"])
    errs = []
    for f in range(tails.shape[0]):
        s = weapon_track[f] if f < len(weapon_track) else None
        if s is None:
            errs.append(None)
            continue
        uv, _ = project(tails[f, w][None], c2w[f], k)
        errs.append(round(math.hypot(uv[0, 0] - (s["cx"] + 0.5), uv[0, 1] - (s["cy"] + 0.5)), 3))
    valid = [e for e in errs if e is not None]
    moves = {b: round(float(np.abs(heads[:, bones.index(b)] - heads[0, bones.index(b)]).max()), 6)
             for b in cfg.get("stationary_bones", [])}
    z = tails[:, w, 2]
    apex = int(np.argmax(z))
    low = float(z[apex:].min())
    contact = next(int(i) for i in range(apex, len(z)) if z[i] <= low + 1e-3)
    proj_ok = bool(valid) and len(valid) == len(errs) and max(valid) <= float(cfg.get("max_projection_err_px", 3.0))
    stat_ok = all(m <= float(cfg.get("max_stationary_m", 1e-3)) for m in moves.values())
    return {"projection_err_px": {"max": max(valid) if valid else None,
                                  "median": round(float(np.median(valid)), 3) if valid else None, "per_frame": errs},
            "stationary_max_move_m": moves,
            "weapon_height_events_3d": {"apex": apex, "contact": contact, "apex_height_m": round(float(z[apex]), 4),
                                        "contact_height_m": round(float(z[contact]), 4)},
            "projection_ok": proj_ok, "stationary_ok": stat_ok, "passed": bool(proj_ok and stat_ok)}


def timeline_frames(timeline: dict, fps: Fraction, apex_after: str, contact_after: str) -> dict:
    """Output-frame indices of the ActionTimeline boundaries that should be the apex and the contact (identity time
    map: output frame = source time x fps, source time 0 = the scene's first frame)."""
    from onecreations.timebase import parse_time

    phases = {ph["id"]: ph for ph in timeline["phases"]}
    out = {}
    for key, pid in (("apex", apex_after), ("contact", contact_after)):
        f = parse_time(phases[pid]["end"]) * fps
        if f.denominator != 1:
            raise ValueError(f"phase {pid} ends between frames ({f})")
        out[key] = int(f)
    return out


def timeline_agreement(expected: dict, observed: dict[str, dict | None], tol: int) -> dict:
    res = {"expected": expected, "tol_frames": tol, "observed": {}}
    ok = True
    for label, ev in observed.items():
        if ev is None or ev.get("contact") is None:
            res["observed"][label] = None
            ok = False
            continue
        d = {k: ev[k] - expected[k] for k in ("apex", "contact")}
        res["observed"][label] = {"apex": ev["apex"], "contact": ev["contact"], "offset_frames": d}
        ok = ok and all(abs(v) <= tol for v in d.values())
    res["passed"] = bool(ok)
    return res


def run(mode: str, bundle_dir: Path, control: Path, reference: Path, out_dir: Path, generated: Path | None,
        spec: Path | None = None) -> dict:
    from onecreations.blender_bundle import load_bundle

    spec_doc = json.loads(Path(spec).read_text(encoding="utf-8")) if spec else None
    tracking = tracking_from_spec(spec_doc, spec) if spec_doc else load_tracking(None)
    subjects = tracking["subjects"]
    bundle = load_bundle(bundle_dir)
    passes = bundle.passes()
    idx, depth = passes["object_index"], passes["depth_m"]
    index_of = bundle.manifest.passes.object_index_map
    gt = ground_truth(bundle, subjects)
    ctrl = decode_gray(control)
    ref = decode_rgb(reference)
    n = idx.shape[0]
    cps = checkpoint_frames(n)
    height, width = idx.shape[1:]
    ground_ids = {index_of[g] for g in tracking["ground"] if g in index_of}
    ignore = {oc: ground_ids | {index_of[o] for o in cfg.get("ignore_occluders", []) if o in index_of}
              for oc, cfg in subjects.items()}
    timed = [oc for oc, cfg in subjects.items() if "timing" in cfg.get("checks", {})]
    gt_events = {oc: strike_events(gt[oc], float(subjects[oc]["checks"]["timing"].get("stop_px", 4.0))) for oc in timed}

    inside = {oc: [round(float(ctrl[f][idx[f] == index_of[oc]].mean()) / 255.0, 4)
                   if (idx[f] == index_of[oc]).any() else None for f in cps] for oc in subjects}
    report = {"mode": mode, "bundle": str(bundle_dir), "bundle_content_sha256": bundle.manifest.content_sha256,
              "spec": str(spec) if spec else None, "frames": n, "checkpoints": cps, "guide_cell_px": GUIDE_CELL_PX,
              "ground_truth": {oc: [gt[oc][f] for f in cps] for oc in subjects},
              "control_mean_inside_gt_mask": inside,
              "control_contrast_vs_ring": {oc: [control_contrast(ctrl[f], idx[f] == index_of[oc]) for f in cps]
                                           for oc in subjects},
              "occluded_frames": {oc: [f for f in range(n) if occlusion_fraction(
                  idx[f], depth[f], index_of[oc], ignore[oc]) > OCCLUSION_FRAC] for oc in subjects},
              "reference_tracking": classify(track_colors(ref, subjects), gt, n, tracking)}
    if timed:
        report["gt_events"] = gt_events
        report["control_contrast_series_report_only"] = {
            oc: [control_contrast(ctrl[f], idx[f] == index_of[oc]) for f in range(n)] for oc in timed}

    gate_cfg = tracking["gate"]
    if gate_cfg.get("legacy_r2d"):
        report["gate"] = _legacy_r2d_gate(gt, inside)
    else:
        checks = {}
        for oc, cfg in subjects.items():
            if cfg.get("role", "primary") != "primary":
                continue
            g = {**gate_cfg, **cfg.get("gate", {})}          # per-subject overrides of the global thresholds
            rows = [gt[oc][f] for f in cps]
            cov = all(r is not None and r["h_cells"] >= g.get("min_height_cells", 0)
                      and r["area_cells"] >= g.get("min_area_cells", 0)
                      and r["w_cells"] >= g.get("min_width_cells", 0) for r in rows)
            travel_cells = round((rows[-1]["cx"] - rows[0]["cx"]) / GUIDE_CELL_PX, 2) if rows[0] and rows[-1] else None
            if g.get("contrast_frames") == "events":
                ev = gt_events.get(oc)
                contrast_frames = [ev["apex"], ev["contact"]] if ev and ev["contact"] is not None else []
                contrast = [control_contrast(ctrl[f], idx[f] == index_of[oc]) for f in contrast_frames]
            else:
                contrast_frames, contrast = cps, report["control_contrast_vs_ring"][oc]
            c = {
                "coverage_ok": cov, "travel_cells": travel_cells,
                "travel_ok": travel_cells is not None and ("lateral" not in cfg.get("checks", {})
                                                          or abs(travel_cells) >= g.get("min_travel_cells", 0)),
                "contrast_frames": contrast_frames,
                "min_control_contrast": min((v for v in contrast if v is not None), default=None),
                "contrast_ok": bool(contrast) and all(v is not None and v >= g.get("min_control_contrast", 0)
                                                      for v in contrast),
                "not_occluded": not report["occluded_frames"][oc],
                "depth_trend_m": [r["median_depth_m"] if r else None for r in rows],
            }
            required = ["coverage_ok", "travel_ok", "contrast_ok", "not_occluded"]
            if g.get("require_visible_all_frames"):
                c["visible_all_frames"] = all(r is not None for r in gt[oc])
                required.append("visible_all_frames")
            if g.get("require_in_frame"):
                c["in_frame"] = all(in_frame(r, width, height) for r in gt[oc] if r is not None)
                required.append("in_frame")
            if "min_excursion_cells" in g:
                ev = gt_events.get(oc)
                exc = ev["excursion_px"] / GUIDE_CELL_PX if ev and ev["excursion_px"] is not None else None
                c["excursion_cells"] = round(exc, 2) if exc is not None else None
                c["excursion_ok"] = exc is not None and exc >= g["min_excursion_cells"]
                required.append("excursion_ok")
            c["ok"] = all(c[k] for k in required)
            checks[oc] = c
        tracker_ok = report["reference_tracking"]["metric_class"] == "PASS"
        gate = {"subjects": checks, "reference_tracker_reproduces_gt": tracker_ok}
        passed = bool(tracker_ok and checks and all(c["ok"] for c in checks.values()))
        if "joints" in tracking:
            jc = tracking["joints"]
            arm = next(a for a in bundle.manifest.armatures if a.oc_id == jc["rig"])
            joints, cam = bundle.joints(), bundle.camera_arrays()
            report["joints"] = joint_checks(joints[f"{jc['rig']}.heads"], joints[f"{jc['rig']}.tails"], list(arm.bones),
                                            cam["c2w"], bundle.K(), gt[jc["weapon_object"]], jc)
            gate["joints_ok"] = report["joints"]["passed"]
            passed = passed and gate["joints_ok"]
        if "timeline" in tracking and spec_doc:
            tc = tracking["timeline"]
            rate = bundle.manifest.shot.output_fps
            expected = timeline_frames(spec_doc["choreography"]["action_timeline"], Fraction(rate.num, rate.den),
                                       tc["apex_after_phase"], tc["contact_after_phase"])
            observed = {"screen_gt": gt_events.get(tracking.get("joints", {}).get("weapon_object", timed[0] if timed
                                                                                    else ""))}
            if "joints" in report:
                observed["joints_3d"] = report["joints"]["weapon_height_events_3d"]
            report["timeline_agreement"] = timeline_agreement(expected, observed, int(tc.get("tol_frames", 1)))
            gate["timeline_ok"] = report["timeline_agreement"]["passed"]
            passed = passed and gate["timeline_ok"]
        gate["passed"] = passed
        report["gate"] = gate

    # report-only coherence evidence: static structures away from every subject's bbox (all frames)
    static_ids = [index_of[s] for s in tracking["static_structures"] if s in index_of]
    static_mask = np.isin(idx[0], static_ids) if static_ids else np.zeros(idx.shape[1:], bool)
    if static_ids:
        near_subject = np.zeros(idx.shape[1:], bool)
        for oc in subjects:
            for row in gt[oc]:
                if row:
                    x0, y0, x1, y1 = row["bbox"]
                    near_subject[max(0, y0 - DRIFT_MARGIN_PX):y1 + DRIFT_MARGIN_PX + 1,
                                 max(0, x0 - DRIFT_MARGIN_PX):x1 + DRIFT_MARGIN_PX + 1] = True
        static_mask &= ~near_subject
    report["static_structure_drift_report_only"] = {"pixels": int(static_mask.sum()),
                                                    "reference": static_drift(ref, static_mask, cps)}

    rows = [ref, _gray_to_rgb(ctrl)]
    if generated is not None:
        gen = decode_rgb(generated)
        report["generated"] = str(generated)
        report["generated_frames"] = int(len(gen))
        tracked = track_colors(gen, subjects)
        report["generated_full_series"] = {oc: {"cx": [(s or {}).get("cx") for s in tr],
                                                "cy": [(s or {}).get("cy") for s in tr],
                                                "area_px": [(s or {}).get("area_px") for s in tr]}
                                           for oc, tr in tracked.items()}
        report["generated_area_vs_gt"] = {oc: [round(a / g, 3) if a and g else None for a, g in zip(
            _series(tracked[oc], "area_px", cps), _series(gt[oc], "area_px", cps))] for oc in subjects}
        report["static_structure_drift_report_only"]["generated"] = static_drift(gen, static_mask, cps)
        report["comparison"] = classify(tracked, gt, n, tracking)
        rows.append(gen)
    out_dir.mkdir(parents=True, exist_ok=True)
    contact_sheet(rows, cps, out_dir / f"{mode}_contact_sheet.png")
    ev = gt_events.get(timed[0]) if timed else None
    if ev and ev["contact"] is not None:
        report["event_contact_sheet_frames"] = list(range(max(0, ev["apex"] - 2), min(n - 1, ev["contact"] + 2) + 1))
        contact_sheet(rows, report["event_contact_sheet_frames"], out_dir / f"{mode}_event_contact_sheet.png")
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
    p.add_argument("--spec", type=Path, default=None, help="scene spec JSON with a 'tracking' section (default: R2D)")
    a = p.parse_args(argv)
    if a.mode == "compare" and a.generated is None:
        p.error("compare needs --generated")
    rep = run(a.mode, a.bundle, a.control, a.reference, a.out_dir, a.generated, a.spec)
    print(json.dumps({"gate": rep["gate"], "reference_metric": rep["reference_tracking"]["metric_class"],
                      "comparison": (rep.get("comparison") or {}).get("metric_class")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
