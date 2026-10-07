"""Deterministic character-asset admission: compare a candidate character build against the current one.

Both builds must share the rig, the shot and the camera; only the character surfaces differ. Inputs are the oc_export
bundles (`--passes`, the candidate optionally `--material-index`) and the Cycles stills of each build at the admission
frames. All figures are measured from those files; the visual verdict (blob anatomy, clipping) is separate.

    uv run python tools/admission/character_admission.py --base <dir> --cand <dir> --frames 4,23,25,29,40 \
        --pass-index 1 --weapon-pass 9 --out admission.json

D3 (a rigged variant of a static asset whose weapon became its own object): `--cand-extra-pass 10` adds that pass to
the candidate's silhouette, so v1 (trident inside pass 2) and v2 (pass 2 + trident pass 10) compare like for like, and
the result carries the silhouette IoU per frame. The rig comparison covers the joint keys both bundles share.

<dir> holds `export/` (bundle) and `stills/still_%04d.png` (Blender frame = index + 1).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from onecreations.director import media


def _cross(o, a, b) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _hull_area(mask: np.ndarray) -> float:
    rows = np.nonzero(mask.any(1))[0]          # only each row's extreme pixels can be hull vertices
    pts = np.array([(x, y) for y in rows for x in (np.argmax(mask[y]), mask.shape[1] - 1 - np.argmax(mask[y][::-1]))],
                   float)
    if len(pts) < 3:
        return 0.0
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def half(ps):
        h = []
        for p in ps:
            while len(h) >= 2 and _cross(h[-2], h[-1], p) <= 0:
                h.pop()
            h.append(p)
        return h
    hull = np.array(half(pts)[:-1] + half(pts[::-1])[:-1])
    x, y = hull[:, 0], hull[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def _perimeter(mask: np.ndarray) -> int:
    m = mask.astype(np.int8)
    return int(np.abs(np.diff(m, axis=0)).sum() + np.abs(np.diff(m, axis=1)).sum())


def silhouette(mask: np.ndarray) -> dict:
    """area; solidity = area / convex-hull area (lower: limbs and horns read separately from the body);
    outline = perimeter / sqrt(area) (higher: a more articulated outline)."""
    area = int(mask.sum())
    return {"area_px": area, "solidity": round(area / max(_hull_area(mask), 1.0), 4),
            "outline": round(_perimeter(mask) / max(np.sqrt(area), 1.0), 3)}


def surface_definition(normal: np.ndarray, mask: np.ndarray, crease_deg: float = 12.0) -> dict:
    """Fraction of interior pixels whose normal turns > crease_deg to a neighbour (form definition; a fused,
    blobby surface has few such pixels) and the mean neighbour angle (deg). Proxy, from the normal pass."""
    n = normal / np.maximum(np.linalg.norm(normal, axis=-1, keepdims=True), 1e-6)
    inner = mask[1:-1, 1:-1] & mask[:-2, 1:-1] & mask[2:, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:]
    c = n[1:-1, 1:-1]
    ang = np.zeros(c.shape[:2])
    for nb in (n[:-2, 1:-1], n[2:, 1:-1], n[1:-1, :-2], n[1:-1, 2:]):
        ang = np.maximum(ang, np.degrees(np.arccos(np.clip((c * nb).sum(-1), -1, 1))))
    a = ang[inner]
    return {"crease_frac": round(float((a > crease_deg).mean()), 4) if a.size else 0.0,
            "mean_angle_deg": round(float(a.mean()), 3) if a.size else 0.0}


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def compare(base: Path, cand: Path, frames: list[int], pass_index: int, weapon_pass: int,
            cand_extra: tuple[int, ...] = ()) -> dict:
    from onecreations.blender_bundle import load_bundle

    bb, cb = load_bundle(base / "export"), load_bundle(cand / "export")
    bp, cp = bb.passes(), cb.passes()
    bj, cj = np.load(base / "export" / "joints.npz"), np.load(cand / "export" / "joints.npz")
    shared = sorted(set(bj.files) & set(cj.files))
    rig = {"keys_equal": sorted(bj.files) == sorted(cj.files), "shared_keys": shared,
           "candidate_only_keys": sorted(set(cj.files) - set(bj.files)),
           "max_joint_diff_m": max((float(np.abs(bj[k] - cj[k]).max()) for k in shared), default=None)}
    bids = sorted(int(v) for v in np.unique(bp["object_index"]))
    cids = sorted(int(v) for v in np.unique(cp["object_index"]))
    out = {"rig": rig, "pass_indices": {"base": bids, "candidate": cids, "equal": bids == cids}, "frames": {}}
    mat = cp.get("material_index") if hasattr(cp, "get") else None
    mat_map = json.loads((cand / "export" / "export_manifest.json").read_text(encoding="utf-8"))
    mat_map = (mat_map.get("passes") or {}).get("material_index_map", {})
    for f in frames:
        row = {}
        masks = {}
        for name, p, d in (("base", bp, base), ("candidate", cp, cand)):
            m = np.isin(p["object_index"][f], [pass_index] + list(cand_extra if name == "candidate" else ()))
            masks[name] = m
            w = p["object_index"][f] == weapon_pass
            # the weapon hand holds the shaft: character pixels within 2 px of the shaft
            grip = int((_dilate(w, 2) & m).sum())
            img = media.decode_rgb(d / "stills" / f"still_{f + 1:04d}.png")[0].astype(float)
            row[name] = {**silhouette(m), **surface_definition(p["normal"][f], m), "hand_on_shaft_px": grip,
                         "shading_std": round(float(img[m].mean(-1).std()), 2)}
        if cand_extra:
            inter, union = (masks["base"] & masks["candidate"]).sum(), (masks["base"] | masks["candidate"]).sum()
            row["silhouette_iou"] = round(float(inter / max(union, 1)), 4)
        if mat is not None:
            m = cp["object_index"][f] == pass_index
            groups = {}
            for g in sorted(set(mat_map.values())):
                groups[str(g)] = int((m & (mat[f] == g)).sum())
            row["candidate"]["material_groups_px"] = groups
            row["candidate"]["unassigned_px"] = int((m & ~np.isin(mat[f], list(set(mat_map.values())))).sum())
        out["frames"][str(f)] = row
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--cand", type=Path, required=True)
    ap.add_argument("--frames", default="4,23,25,29,40")
    ap.add_argument("--pass-index", type=int, default=1)
    ap.add_argument("--weapon-pass", type=int, default=9)
    ap.add_argument("--cand-extra-pass", type=int, action="append", default=[],
                    help="pass index added to the candidate's silhouette (e.g. its now separate weapon)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    res = compare(a.base, a.cand, [int(x) for x in a.frames.split(",")], a.pass_index, a.weapon_pass,
                  tuple(a.cand_extra_pass))
    a.out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
