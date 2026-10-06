"""Camera presets -> an authored move and its samples (pure Python; same math as the engine's camera builder).

orbit_push_v1: look-at orbit around a target plus a push-in, fixed lens, no roll. A variant (low / high) and explicit
overrides adjust the defaults; the result must stay inside the preset's admitted envelope (M2-C / M3-A / Showcase).
"""

from __future__ import annotations

import math

import numpy as np

from onecreations.camera.trajectory import CameraTrajectory
from onecreations.contracts.registry import AssetEntry
from onecreations.geometry import conventions

MOVE_KEYS = ("azimuth_deg", "radius_m", "height_m", "lens_mm", "ease_linear_mix", "yaw_offset_deg", "sensor_mm",
             "sensor_fit", "clip_start", "clip_end")


def ease(s: float, mix: float) -> float:
    return mix * s + (1.0 - mix) * (0.5 - 0.5 * math.cos(math.pi * s))


def yaw_about_world_z(c2w: np.ndarray, angle_rad: float) -> np.ndarray:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    out = c2w.copy()
    out[:3, :3] = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]) @ c2w[:3, :3]
    return out


def build_move(entry: AssetEntry, variant: str | None, target, overrides: dict) -> dict:
    """The engine's CAMERA_MOVE dict: target first, then the preset defaults, variant and overrides."""
    move = dict(entry.data["defaults"])
    if variant:
        move.update(entry.data["variants"][variant])
    move.update({k: v for k, v in overrides.items() if k in MOVE_KEYS})
    return {"target": [round(float(v), 6) for v in target], **{k: move[k] for k in MOVE_KEYS}}


def envelope_errors(entry: AssetEntry, move: dict) -> list[str]:
    env = entry.data["envelope"]
    a0, a1 = move["azimuth_deg"]
    r0, r1 = move["radius_m"]
    errs = []
    if abs(a1 - a0) > env["max_orbit_deg"] + 1e-9:
        errs.append(f"orbit {abs(a1 - a0)} deg exceeds the admitted {env['max_orbit_deg']} deg")
    if r0 - r1 > env["max_push_in_m"] + 1e-9:
        errs.append(f"push-in {r0 - r1:.2f} m exceeds the admitted {env['max_push_in_m']} m")
    if r1 > r0:
        errs.append("pull-out (radius increasing) is not in the admitted family")
    if min(r0, r1) < env["min_radius_m"]:
        errs.append(f"radius below {env['min_radius_m']} m")
    lo, hi = env["height_m"]
    if not all(lo <= h <= hi for h in move["height_m"]):
        errs.append(f"height {move['height_m']} outside [{lo}, {hi}] m")
    lo, hi = env["lens_mm"]
    if not lo <= move["lens_mm"] <= hi:
        errs.append(f"lens {move['lens_mm']} mm outside [{lo}, {hi}] mm")
    lo, hi = env["ease_linear_mix"]
    if not lo <= move["ease_linear_mix"] <= hi:
        errs.append(f"ease mix {move['ease_linear_mix']} outside [{lo}, {hi}]")
    return errs


def samples(move: dict, frames: int, fps: int) -> CameraTrajectory:
    """One camera_to_world sample per output frame (t = k / fps), exactly as the engine samples it."""
    target = np.asarray(move["target"], dtype=np.float64)
    (a0, a1), (r0, r1), (h0, h1) = move["azimuth_deg"], move["radius_m"], move["height_m"]
    c2w = []
    for k in range(frames):
        e = ease(k / (frames - 1), move["ease_linear_mix"])
        az, r, h = math.radians(a0 + (a1 - a0) * e), r0 + (r1 - r0) * e, h0 + (h1 - h0) * e
        eye = np.array([target[0] + r * math.sin(az), target[1] - r * math.cos(az), h])
        c2w.append(yaw_about_world_z(conventions.look_at(eye, target), math.radians(move["yaw_offset_deg"])))
    return CameraTrajectory.from_c2w([k / fps for k in range(frames)], np.stack(c2w),
                                     lens_mm=np.full(frames, move["lens_mm"]), interpolation="catmull_rom",
                                     meta={"provenance": {"source": "authored"}, "move": "orbit+push-in, look-at"})
