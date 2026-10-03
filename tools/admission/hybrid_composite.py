"""Hybrid composite (M3-A on): a raw generated video + deterministic layers rendered from the authored scene.

    hybrid_composite.py --render-dir G:/onecreations/renders/m3a_action --generated raw.mp4 --out-dir DIR

The render dir holds the scene's export/ bundle, shot_spec.json (its "layers" section is a CompositeManifest),
reference_preview.mp4 (sharp), reference_motionblur.mp4 (matched shutter) and layers/<id>/f_####.png (RGBA, straight
alpha, Blender frame numbers) from render_layers.py. Method, fixed before any generation:
1. Weapon retention per frame = generated / reference area of the tracked weapon's colour rule, counted only inside
   a band around its authored silhouette (frames f-2..f+2, dilated), against the motion-blur reference (and the
   sharp one, report-only). Legitimate motion blur is in the reference, so it is not counted as loss.
2. Protected frames = frames where the authored speed (into or out of the frame) >= rule x the weapon's own width,
   dilated, UNION frames where the blur-matched retention < rule.
3. Grade: one per-channel gain mapping the Blender layer to the generated look, fitted on unprotected frames where
   the generated weapon is solid (retention >= 0.8), clipped to [0.6, 1.6].
4. In protected frames: generated weapon remnants inside the band but outside the protected layer are inpainted
   (diffusion from the surrounding pixels), then the graded layer is alpha-composited (occlusion is already in the
   layer's alpha: holdouts). Effect layers are composited from their ActionTimeline trigger frame.
   --ghost-under-layer (method v2, added after M3-A's v1 result, not pre-registered there): also inpaint generated
   weapon pixels UNDER the layer, so a semi-transparent motion-blurred layer does not show the generated weapon through.
   Since the showcase this is the manifest field ghost_mode: under_layer (the flag forces it on a v1 manifest);
   ghost_colors adds colour rules counted as remnants; protection.include_frames forces frames into the protected
   set; effect layers with blend: add (light passes) are added, not alpha-composited.
   ghost_mode: fill_under_layer (M3-B hybrid v2, pre-registered before the M3-B generation): under_layer plus every
   pixel the layer covers at all, whatever its colour, except generated actor pixels (see ghost_mask). Each protected
   frame also reports unexplained_weapon_px (weapon-coloured composite pixels outside the layer's footprint).
Outputs: hybrid.mp4 (lossless rgb), composite_report.json, A/B/C contact sheets (A = Blender reference + effects,
B = raw generated, C = hybrid).
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import control_diagnostic as cd  # noqa: E402

BAND_PX, GHOST_DILATE_PX = 14, 2
FILL_ALPHA_MIN = 2              # fill_under_layer: layer alpha > 2/255 counts as covered


def alpha_over(base: np.ndarray, layer_rgba: np.ndarray, gain=(1.0, 1.0, 1.0)) -> np.ndarray:
    """Straight-alpha 'over': out = gain * layer.rgb * a + base * (1 - a)."""
    a = layer_rgba[..., 3:4].astype(np.float32) / 255.0
    rgb = np.clip(layer_rgba[..., :3].astype(np.float32) * np.asarray(gain, np.float32), 0, 255)
    return np.clip(rgb * a + base.astype(np.float32) * (1.0 - a) + 0.5, 0, 255).astype(np.uint8)


def add_light(base: np.ndarray, layer_rgba: np.ndarray, gain: float = 1.0) -> np.ndarray:
    """Additive light pass: out = base + gain * layer.rgb (clipped)."""
    return np.clip(base.astype(np.float32) + gain * layer_rgba[..., :3].astype(np.float32) + 0.5, 0, 255).astype(np.uint8)


def apply_effect(base: np.ndarray, layer_rgba: np.ndarray, blend: str) -> np.ndarray:
    return add_light(base, layer_rgba) if blend == "add" else alpha_over(base, layer_rgba)


def fit_gain(pairs: list[tuple[np.ndarray, np.ndarray]], lo: float = 0.6, hi: float = 1.6) -> list[float]:
    """Median over frames of mean(generated) / mean(layer) per channel, from (generated_px, layer_px) samples."""
    ratios = [g.mean(axis=0) / np.maximum(lay.mean(axis=0), 1.0) for g, lay in pairs if len(g) >= 20]
    if not ratios:
        return [1.0, 1.0, 1.0]
    return [round(float(np.clip(v, lo, hi)), 4) for v in np.median(np.stack(ratios), axis=0)]


def inpaint(img: np.ndarray, mask: np.ndarray, iters: int = 80, exclude_sources: np.ndarray | None = None) -> np.ndarray:
    """Fill `mask` pixels by iterated 4-neighbour averaging seeded from the surrounding (unmasked) pixels.
    `exclude_sources` pixels are kept as they are but never seed the fill (e.g. actor pixels next to a weapon streak,
    so the background estimate under the streak does not bleed actor colour)."""
    if not mask.any():
        return img
    out = img.astype(np.float32).copy()
    known = ~mask if exclude_sources is None else ~mask & ~exclude_sources
    out[mask] = 0.0
    weight = known.astype(np.float32)
    for _ in range(iters):
        acc = np.zeros_like(out)
        cnt = np.zeros(mask.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc += np.roll(np.roll(out * weight[..., None], dy, 0), dx, 1)
            cnt += np.roll(np.roll(weight, dy, 0), dx, 1)
        fill = mask & (cnt > 0)
        out[fill] = acc[fill] / cnt[fill][:, None]
        weight = np.where(fill, 1.0, weight)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def weapon_remnants(rgb: np.ndarray, color: str, extra_colors=()) -> np.ndarray:
    """Pixels of the generated frame that look like the protected weapon (its tracking colour + ghost colours)."""
    m = cd.color_mask(rgb, color)
    for extra in extra_colors:
        m |= cd.color_mask(rgb, extra)
    return m


def ghost_mask(alpha: np.ndarray, remnant: np.ndarray, band: np.ndarray, mode: str,
               keep: np.ndarray | None = None) -> np.ndarray:
    """Generated pixels to inpaint before the layer goes over (alpha: the layer's straight alpha, uint8).
    outside_core (M3-A v1): weapon-coloured remnants in the band where the layer alpha < 77 (0.3).
    under_layer (M3-A post-hoc v2): weapon-coloured remnants anywhere in the band, under the layer too.
    fill_under_layer (M3-B v2, pre-registered): under_layer PLUS every pixel the layer covers at all (alpha > 2)
      whatever its colour; `keep` (generated actor pixels) is never inpainted: they legitimately show through a
      partial-alpha weapon in front of them, and an actor in front of the weapon is already a holdout (alpha 0).
      A semi-transparent blur streak can then only ever show a weapon-free estimate of the background through it,
      never the generated weapon, so a double image is impossible by construction."""
    if mode == "outside_core":
        ghost = cd.dilate(remnant & band & (alpha < 77), GHOST_DILATE_PX)
    elif mode in ("under_layer", "fill_under_layer"):
        ghost = cd.dilate(remnant & band, GHOST_DILATE_PX)
        if mode == "fill_under_layer":
            ghost |= alpha > FILL_ALPHA_MIN
            if keep is not None:
                ghost &= ~keep
    else:
        raise ValueError(f"unknown ghost mode {mode!r}")
    return ghost


def unexplained_weapon_px(composite: np.ndarray, alpha: np.ndarray, band: np.ndarray, color: str,
                          extra_colors=()) -> int:
    """Report-only double-image measure: weapon-coloured composite pixels in the band that the layer does not
    explain (outside its alpha > 10 footprint dilated by 2 px), i.e. visible generated-weapon remnants."""
    explained = cd.dilate(alpha > 10, GHOST_DILATE_PX)
    return int((weapon_remnants(composite, color, extra_colors) & band & ~explained).sum())


def authored_fast_frames(centroids: list, widths: list, speed_widths: float, dilate: int) -> list[int]:
    n = len(centroids)
    sp = [math.dist(centroids[f], centroids[f + 1]) if centroids[f] is not None and centroids[f + 1] is not None
          else 0.0 for f in range(n - 1)]
    fast = [f for f in range(n) if widths[f] and max(sp[f - 1] if f > 0 else 0.0, sp[f] if f < n - 1 else 0.0)
            >= speed_widths * widths[f]]
    return sorted({g for f in fast for g in range(f - dilate, f + dilate + 1) if 0 <= g < n})


def trigger_frame(timeline: dict, phase: str, edge: str, fps: Fraction) -> int:
    from onecreations.timebase import parse_time

    ph = next(p for p in timeline["phases"] if p["id"] == phase)
    f = parse_time(ph[edge]) * fps
    if f.denominator != 1:
        raise ValueError(f"{phase}.{edge} is not on a frame ({f})")
    return int(f)


def nearest_distance(point, mask: np.ndarray, radius: int = 40) -> float | None:
    if point is None:
        return None
    x, y = int(round(point[0])), int(round(point[1]))
    h, w = mask.shape
    y0, y1, x0, x1 = max(0, y - radius), min(h, y + radius + 1), max(0, x - radius), min(w, x + radius + 1)
    ys, xs = np.nonzero(mask[y0:y1, x0:x1])
    if len(xs) == 0:
        return None
    return round(float(np.min(np.hypot(xs + x0 - point[0], ys + y0 - point[1]))), 1)


def _png_rgba(path: Path) -> np.ndarray:
    raw = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgba",
                          "-"], capture_output=True, check=True).stdout
    probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-show_entries", "stream=width,height", "-of",
                            "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout.strip()
    w, h = (int(v) for v in probe.split(",")[:2])
    return np.frombuffer(raw, np.uint8).reshape(h, w, 4)


def _encode(frames: np.ndarray, out: Path, fps: str = "24") -> None:
    n, h, w, _ = frames.shape
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                    "-r", fps, "-i", "-", "-c:v", "libx264rgb", "-qp", "0", "-pix_fmt", "rgb24", str(out)],
                   input=np.ascontiguousarray(frames).tobytes(), check=True)


def run(render_dir: Path, generated: Path, out_dir: Path, ghost_under_layer: bool = False) -> dict:
    from onecreations.blender_bundle import load_bundle
    from onecreations.contracts import CompositeManifest
    from onecreations.geometry.intrinsics import project

    spec = json.loads((render_dir / "shot_spec.json").read_text(encoding="utf-8"))
    manifest = CompositeManifest.model_validate(spec["layers"])
    tracking = spec["tracking"]
    timeline = spec["choreography"]["action_timeline"]
    bundle = load_bundle(render_dir / "export")
    idx = bundle.passes()["object_index"]
    index_of = bundle.manifest.passes.object_index_map
    rate = bundle.manifest.shot.output_fps
    fps = Fraction(rate.num, rate.den)
    raw = cd.decode_rgb(generated)
    sharp = cd.decode_rgb(render_dir / "reference_preview.mp4")
    blur = cd.decode_rgb(render_dir / "reference_motionblur.mp4")
    n = min(len(raw), idx.shape[0])
    out = raw[:n].copy()
    report = {"generated": str(generated), "render_dir": str(render_dir), "frames": n,
              "method": "ghost mode forced to under_layer (--ghost-under-layer)" if ghost_under_layer else
              "manifest ghost_mode", "layers": {}}

    for layer in sorted(manifest.layers, key=lambda ly: ly.order):
        ldir = render_dir / "layers" / layer.id
        frames_rgba = {int(p.stem.split("_")[1]) - 1: p for p in sorted(ldir.glob("f_*.png"))}  # output index
        entry = {"kind": layer.kind, "layer_frames_available": sorted(frames_rgba)}
        if layer.kind == "protected_geometry":
            rule = layer.protection
            obj = rule.track_object
            color = tracking["subjects"][obj]["color"]
            gt_masks = [idx[f] == index_of[obj] for f in range(n)]
            stats = [cd.mask_stats(m) for m in gt_masks]
            cents = [(s["cx"], s["cy"]) if s else None for s in stats]
            widths = [s["w_px"] if s else 0 for s in stats]
            band = [cd.dilate(np.any(np.stack(gt_masks[max(0, f - 2):f + 3]), axis=0), BAND_PX) for f in range(n)]

            def area(video, f):
                return int((cd.color_mask(video[f], color) & band[f]).sum())

            ret_blur = [round(area(raw, f) / max(area(blur, f), 1), 3) for f in range(n)]
            ret_sharp = [round(area(raw, f) / max(area(sharp, f), 1), 3) for f in range(n)]
            authored = authored_fast_frames(cents, widths, rule.authored_speed_widths or 1e9, rule.dilate_frames)
            low = [f for f in range(n) if rule.raw_retention_below and ret_blur[f] < rule.raw_retention_below]
            protected = sorted(set(authored) | set(low) | {f for f in rule.include_frames if 0 <= f < n})
            unreliable = set(authored) | set(low)
            missing = [f for f in protected if f not in frames_rgba]
            if missing:
                raise FileNotFoundError(f"layer {layer.id}: no render for protected frames {missing}")
            layers_cache = {f: _png_rgba(frames_rgba[f]) for f in frames_rgba}
            gain = [1.0, 1.0, 1.0]
            if layer.grade == "per_channel_gain":
                pairs = []
                for f in range(n):
                    if f in unreliable or ret_blur[f] < 0.8 or f not in layers_cache:
                        continue
                    sel = (layers_cache[f][..., 3] >= 242) & cd.color_mask(raw[f], color) & band[f]
                    pairs.append((raw[f][sel].astype(np.float32), layers_cache[f][..., :3][sel].astype(np.float32)))
                gain = fit_gain(pairs)
            # grip point (projected mace-bone head) for the hand-attachment check
            jc = tracking.get("joints", {})
            grips = [None] * n
            if jc:
                arm = next(a for a in bundle.manifest.armatures if a.oc_id == jc["rig"])
                heads = bundle.joints()[f"{jc['rig']}.heads"]
                cam = bundle.camera_arrays()
                wi = list(arm.bones).index(jc["weapon_bone"])
                for f in range(n):
                    uv, _ = project(heads[f, wi][None], cam["c2w"][f], bundle.K())
                    grips[f] = (float(uv[0, 0]) - 0.5, float(uv[0, 1]) - 0.5)
            body = jc.get("body_object", "m3a_asura")
            body_color = tracking["subjects"].get(body, {}).get("color", "crimson")
            mode = "under_layer" if ghost_under_layer and layer.ghost_mode == "outside_core" else layer.ghost_mode
            per_frame = {}
            for f in protected:
                lay = layers_cache[f]
                base = out[f]
                ghost = np.zeros(base.shape[:2], bool)
                if layer.ghost_suppression:
                    remnant = weapon_remnants(base, color, layer.ghost_colors)
                    keep = cd.color_mask(raw[f], body_color)
                    ghost = ghost_mask(lay[..., 3], remnant, band[f], mode, keep)
                    base = inpaint(base, ghost, exclude_sources=keep if mode == "fill_under_layer" else None)
                out[f] = alpha_over(base, lay, gain)
                unexplained = unexplained_weapon_px(out[f], lay[..., 3], band[f], color, layer.ghost_colors)
                comp = cd.mask_stats(cd.color_mask(out[f], color) & band[f])
                refb = cd.mask_stats(cd.color_mask(blur[f], color) & band[f])
                err = (round(math.dist((comp["cx"], comp["cy"]), cents[f]), 1) if comp and cents[f] else None)
                err_b = (round(math.dist((comp["cx"], comp["cy"]), (refb["cx"], refb["cy"])), 1)
                         if comp and refb else None)
                per_frame[f] = {"retention_vs_blur": ret_blur[f], "retention_vs_sharp": ret_sharp[f],
                                "ghost_px_inpainted": int(ghost.sum()), "layer_alpha_px": int((lay[..., 3] > 10).sum()),
                                "unexplained_weapon_px_report_only": unexplained,
                                "composite_vs_blur_reference_centroid_px": err_b,
                                "composite_vs_sharp_gt_centroid_px_report_only": err,
                                "grip_to_generated_hand_px": nearest_distance(grips[f], cd.color_mask(raw[f], body_color))}
            entry.update(color=color, band_px=BAND_PX, retention_vs_blur=ret_blur, retention_vs_sharp=ret_sharp,
                         authored_fast_frames=authored, low_retention_frames=low, protected_frames=protected,
                         ghost_mode=mode,
                         ghost_colors=list(layer.ghost_colors), grade_gain=gain, per_frame=per_frame)
        else:
            start = trigger_frame(timeline, layer.trigger.phase, layer.trigger.edge, fps)
            frames = [f for f in range(start, start + layer.duration_frames) if f < n]
            missing = [f for f in frames if f not in frames_rgba]
            if missing:
                raise FileNotFoundError(f"layer {layer.id}: no render for frames {missing}")
            for f in frames:
                out[f] = apply_effect(out[f], _png_rgba(frames_rgba[f]), layer.blend)
            entry.update(trigger={"timeline": layer.trigger.timeline, "phase": layer.trigger.phase,
                                  "edge": layer.trigger.edge, "output_frame": start}, frames=frames, blend=layer.blend)
        report["layers"][layer.id] = entry

    out_dir.mkdir(parents=True, exist_ok=True)
    _encode(out, out_dir / "hybrid.mp4")
    # A: authored truth = sharp Blender reference + effect layers at their trigger frames
    truth = sharp[:n].copy()
    for lid, entry in report["layers"].items():
        if entry["kind"] == "effect":
            for f in entry["frames"]:
                truth[f] = apply_effect(truth[f], _png_rgba(render_dir / "layers" / lid / f"f_{f + 1:04d}.png"),
                                        entry.get("blend", "over"))
    _encode(truth, out_dir / "reference_with_effects.mp4")
    report["outputs"] = {"hybrid": "hybrid.mp4", "reference_with_effects": "reference_with_effects.mp4"}
    (out_dir / "composite_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return {"report": report, "truth": truth, "raw": raw[:n], "hybrid": out}


def abc_sheets(truth, raw, hybrid, out_dir: Path, key_frames: list[int], strip: list[int]) -> None:
    cd.contact_sheet([truth, raw, hybrid], key_frames, out_dir / "abc_key_frames.png", scale=0.5)
    cd.contact_sheet([truth, raw, hybrid], strip, out_dir / "abc_strike_strip.png", scale=0.5)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--render-dir", type=Path, required=True)
    p.add_argument("--generated", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--key-frames", default="4,14,23,25,26,28,29,32,40,48")
    p.add_argument("--strip", default="22-31")
    p.add_argument("--ghost-under-layer", action="store_true", help="method v2: inpaint generated weapon pixels under "
                                                                     "the layer too (default: v1)")
    a = p.parse_args(argv)
    res = run(a.render_dir, a.generated, a.out_dir, a.ghost_under_layer)
    s0, s1 = (int(v) for v in a.strip.split("-"))
    abc_sheets(res["truth"], res["raw"], res["hybrid"], a.out_dir, [int(v) for v in a.key_frames.split(",")],
               list(range(s0, s1 + 1)))
    rep = res["report"]
    for lid, e in rep["layers"].items():
        if e["kind"] == "protected_geometry":
            print(json.dumps({"layer": lid, "protected_frames": e["protected_frames"], "authored": e["authored_fast_frames"],
                              "low_retention": e["low_retention_frames"], "gain": e["grade_gain"]}))
        else:
            print(json.dumps({"layer": lid, "trigger": e["trigger"], "frames": e["frames"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
