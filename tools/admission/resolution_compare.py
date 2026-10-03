"""Same-shot resolution comparison of a fast-moving weapon (M2-B 512x320 vs 768x448).

    resolution_compare.py --run 512x320=G:/onecreations/renders/m2b_strike[,generated.mp4] \
        --run 768x448=G:/onecreations/renders/m2b_strike_768[,generated.mp4] --out comparison.json

Each run directory is a scene's render folder (export/, reference_preview.mp4, shot_spec.json). Per run it reports:
- the Union-guide grid the pinned LTXVideo graph builds at that output size (`guide_grid`, derived from
  EmptyLTXVLatentVideo (size // 32) and LTXAddVideoICLoRAGuide (resize to latent x 32 / latent_downscale_factor,
  VAE-encode, dilate by the factor), i.e. output px per guide cell);
- the weapon head's ground-truth size, area and motion per frame, in output pixels AND guide cells (raw px/frame is
  not comparable across resolutions on its own), the weapon silhouette (head + shaft) and the projected extent of the
  weapon-arm chain from joints.npz;
- with a generated video: per-frame retention = generated / reference area of the same colour tracker
  (control_diagnostic.color_mask), summarised over the pre-registered fast and worst frame ranges.
Evidence only: the classification rules live in the experiment's pre-registration record, not here.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))   # sibling tool, whether run as a script or imported

import control_diagnostic as cd  # noqa: E402

VAE_SPATIAL, LATENT_DOWNSCALE = 32, 2       # LTX video VAE (8, 32, 32); Union LoRA reference_downscale_factor 2


def guide_grid(width: int, height: int, vae_spatial: int = VAE_SPATIAL, downscale: int = LATENT_DOWNSCALE) -> dict:
    """The Union guide's spatial grid at an output size, as the pinned graph builds it."""
    if width % vae_spatial or height % vae_spatial:
        raise ValueError(f"{width}x{height} is not a multiple of {vae_spatial}")
    lw, lh = width // vae_spatial, height // vae_spatial
    if lw % downscale or lh % downscale:
        raise ValueError(f"latent {lw}x{lh} is not divisible by latent_downscale_factor {downscale}")
    gw, gh = lw * vae_spatial // downscale, lh * vae_spatial // downscale
    return {"output_px": [width, height], "latent": [lw, lh], "guide_resize_px": [gw, gh],
            "guide_cells": [gw // vae_spatial, gh // vae_spatial], "output_px_per_guide_cell": vae_spatial * downscale}


def motion(track: list[dict | None], cell_px: int) -> dict:
    """Per-frame centroid displacement of a GT track in px and cells, its peak and total path length."""
    pts = [(s["cx"], s["cy"]) if s else None for s in track]
    speed = [round(math.hypot(b[0] - a[0], b[1] - a[1]), 2) if a and b else None for a, b in zip(pts, pts[1:])]
    valid = [v for v in speed if v is not None]
    peak = max(valid) if valid else None
    return {"speed_px": speed, "speed_cells": [round(v / cell_px, 3) if v is not None else None for v in speed],
            "peak_px_per_frame": peak, "peak_cells_per_frame": round(peak / cell_px, 3) if peak else None,
            "peak_frame": speed.index(peak) if peak else None, "path_px": round(sum(valid), 1),
            "path_cells": round(sum(valid) / cell_px, 2)}


def retention_summary(ratios: list[float | None], fast: range, worst: range, severe: float) -> dict:
    """Generated/reference tracked-area ratios summarised over the fast and worst frame ranges and elsewhere."""
    def pick(frames):
        return [ratios[f] for f in frames if f < len(ratios) and ratios[f] is not None]
    fr, wr = pick(fast), pick(worst)
    slow = pick([f for f in range(len(ratios)) if f not in fast])
    return {"fast_frames": [fast.start, fast.stop - 1], "worst_frames": [worst.start, worst.stop - 1],
            "fast_retention": {f: ratios[f] for f in fast if f < len(ratios)},
            "fast_worst": min(fr) if fr else None, "fast_worst_frame": (list(fast)[fr.index(min(fr))] if fr else None),
            "fast_median": round(float(np.median(fr)), 3) if fr else None,
            "worst_region_median": round(float(np.median(wr)), 3) if wr else None,
            "severe_threshold": severe, "severe_frames": [f for f in fast if f < len(ratios)
                                                          and ratios[f] is not None and ratios[f] < severe],
            "outside_fast_median": round(float(np.median(slow)), 3) if slow else None}


def analyse_run(label: str, render_dir: Path, generated: Path | None, weapon: str, shaft: str, rig: str,
                chain: list[str], color: str, fast: range, worst: range, severe: float) -> dict:
    from onecreations.blender_bundle import load_bundle
    from onecreations.geometry.intrinsics import project

    bundle = load_bundle(render_dir / "export")
    passes = bundle.passes()
    idx = passes["object_index"]
    index_of = bundle.manifest.passes.object_index_map
    n, height, width = idx.shape
    grid = guide_grid(width, height)
    cell = grid["output_px_per_guide_cell"]
    head = [cd.mask_stats(idx[f] == index_of[weapon]) for f in range(n)]
    silhouette = [cd.mask_stats(np.isin(idx[f], [index_of[weapon], index_of[shaft]])) for f in range(n)]

    arm = next(a for a in bundle.manifest.armatures if a.oc_id == rig)
    bones = list(arm.bones)
    joints, cam = bundle.joints(), bundle.camera_arrays()
    heads, tails = joints[f"{rig}.heads"], joints[f"{rig}.tails"]
    chain_rows = []
    for f in range(n):
        pts = np.vstack([heads[f, bones.index(chain[0])][None]] + [tails[f, bones.index(b)][None] for b in chain])
        uv, _ = project(pts, cam["c2w"][f], bundle.K())
        seg = float(np.linalg.norm(np.diff(uv, axis=0), axis=1).sum())
        x0, y0 = uv.min(axis=0)
        x1, y1 = uv.max(axis=0)
        chain_rows.append({"polyline_px": round(seg, 1), "polyline_cells": round(seg / cell, 2),
                           "bbox_w_cells": round(float(x1 - x0) / cell, 2), "bbox_h_cells": round(float(y1 - y0) / cell, 2)})

    def series(rows, key):
        return [r[key] if r else None for r in rows]

    ev = cd.strike_events(head)
    out = {"label": label, "render_dir": str(render_dir), "bundle_content_sha256": bundle.manifest.content_sha256,
           "frames": n, "guide_grid": grid,
           "weapon_head_gt": {"w_px": series(head, "w_px"), "h_px": series(head, "h_px"),
                              "area_px": series(head, "area_px"), "w_cells": series(head, "w_cells"),
                              "h_cells": series(head, "h_cells"), "area_cells": series(head, "area_cells"),
                              "w_px_range": [min(series(head, "w_px")), max(series(head, "w_px"))],
                              "w_cells_range": [min(series(head, "w_cells")), max(series(head, "w_cells"))],
                              "area_cells_range": [min(series(head, "area_cells")), max(series(head, "area_cells"))]},
           "weapon_silhouette_gt": {"area_px": series(silhouette, "area_px"),
                                    "area_cells_range": [min(series(silhouette, "area_cells")),
                                                         max(series(silhouette, "area_cells"))]},
           "weapon_arm_chain_projected": {"bones": chain, "per_frame": chain_rows,
                                          "polyline_cells_range": [min(r["polyline_cells"] for r in chain_rows),
                                                                   max(r["polyline_cells"] for r in chain_rows)]},
           "weapon_head_motion_gt": motion(head, cell),
           "weapon_head_events_gt": ev,
           "excursion_cells": round(ev["excursion_px"] / cell, 2) if ev and ev["excursion_px"] is not None else None}

    if generated is not None:
        ref = cd.decode_rgb(render_dir / "reference_preview.mp4")
        gen = cd.decode_rgb(generated)
        ref_area = [int(cd.color_mask(f, color).sum()) for f in ref]
        gen_area = [int(cd.color_mask(f, color).sum()) for f in gen]
        ratios = [round(g / r, 3) if r else None for g, r in zip(gen_area, ref_area)]
        out["generated"] = str(generated)
        out["retention"] = {"metric": f"generated / reference area of the '{color}' colour mask (same tracker)",
                            "reference_area_px": ref_area, "generated_area_px": gen_area, "ratio": ratios,
                            **retention_summary(ratios, fast, worst, severe)}
    return out


def _range(text: str) -> range:
    a, b = (int(v) for v in text.split("-"))
    return range(a, b + 1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", action="append", required=True, help="LABEL=RENDER_DIR[,GENERATED.mp4]")
    p.add_argument("--weapon", default="m2b_mace_head")
    p.add_argument("--shaft", default="m2b_mace_shaft")
    p.add_argument("--rig", default="m2b_asura_rig")
    p.add_argument("--chain", default="upper_arm.L,forearm.L,hand.L,mace")
    p.add_argument("--color", default="gold")
    p.add_argument("--fast", default="24-28", help="output frames of the fast strike region (inclusive)")
    p.add_argument("--worst", default="25-27", help="output frames of the baseline's worst region (inclusive)")
    p.add_argument("--severe", type=float, default=0.25, help="retention below this counts as severely degraded")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    runs = []
    for spec in a.run:
        label, rest = spec.split("=", 1)
        parts = rest.split(",")
        runs.append(analyse_run(label, Path(parts[0]), Path(parts[1]) if len(parts) > 1 else None, a.weapon, a.shaft,
                                a.rig, a.chain.split(","), a.color, _range(a.fast), _range(a.worst), a.severe))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"runs": runs}, indent=1), encoding="utf-8")
    for r in runs:
        m, h = r["weapon_head_motion_gt"], r["weapon_head_gt"]
        line = (f"{r['label']}: guide {r['guide_grid']['guide_cells']} cells x {r['guide_grid']['output_px_per_guide_cell']} px; "
                f"head {h['w_px_range']} px = {h['w_cells_range']} cells; peak {m['peak_px_per_frame']} px/f = "
                f"{m['peak_cells_per_frame']} cells/f; path {m['path_px']} px = {m['path_cells']} cells")
        if "retention" in r:
            rt = r["retention"]
            line += (f"; retention fast worst {rt['fast_worst']} (f{rt['fast_worst_frame']}), fast median "
                     f"{rt['fast_median']}, severe {rt['severe_frames']}, outside-fast median {rt['outside_fast_median']}")
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
