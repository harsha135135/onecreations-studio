"""Silhouette / alignment gate between two export bundles of the same shot (M3-B on): did a first-frame appearance
change (new character geometry) keep the control of the reference shot?

    silhouette_compare.py --reference G:/onecreations/renders/m3a_action/export \
        --candidate G:/onecreations/renders/m3b_action/export --gate PREREG.json --out silhouette_gate.json

Per gated object (by oc_id, through each bundle's own object-index map) and per frame: IoU of the two object-index
masks, centroid shift (px) and area ratio (candidate / reference); then the frame-wise minimum / maximum against the
pre-registered limits. Also: the exported joints (every rig, heads and tails) and the camera (camera-to-world and
K) must be unchanged, i.e. the rig, keys and camera move are the reference's. The gate reads the "silhouette_gate"
section of a pre-registration JSON (or a shot spec's "m3b" section):
  {"objects": {oc_id: {"min_iou": .., "max_centroid_px": .., "area_ratio": [lo, hi]}}, "max_joint_diff_m": ..,
   "max_camera_diff": ..}
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import control_diagnostic as cd  # noqa: E402


def mask_iou(a: np.ndarray, b: np.ndarray) -> float | None:
    union = int((a | b).sum())
    return None if union == 0 else round(int((a & b).sum()) / union, 4)


def compare_object(ref_idx: np.ndarray, cand_idx: np.ndarray, ref_pass: int, cand_pass: int) -> dict:
    """Per-frame IoU, centroid shift (px) and area ratio of one object's masks in two (N, H, W) index stacks."""
    n = min(len(ref_idx), len(cand_idx))
    iou, shift, ratio, vis_r, vis_c = [], [], [], [], []
    for f in range(n):
        a, b = ref_idx[f] == ref_pass, cand_idx[f] == cand_pass
        iou.append(mask_iou(a, b))
        sa, sb = cd.mask_stats(a), cd.mask_stats(b)
        shift.append(round(math.dist((sa["cx"], sa["cy"]), (sb["cx"], sb["cy"])), 2) if sa and sb else None)
        ratio.append(round(int(b.sum()) / int(a.sum()), 4) if a.any() else None)
        vis_r.append(sa is not None)
        vis_c.append(sb is not None)
    return {"frames": n, "iou": iou, "centroid_shift_px": shift, "area_ratio": ratio, "visible_reference": vis_r,
            "visible_candidate": vis_c}


def evaluate_object(stats: dict, limits: dict) -> dict:
    """Frame-wise worst values against the limits. A frame where the object is visible in one bundle only fails."""
    iou = stats["iou"]
    present = [v for v in iou if v is not None]
    vis_mismatch = [f for f, (r, c) in enumerate(zip(stats["visible_reference"], stats["visible_candidate"])) if r != c]
    shifts = [v for v in stats["centroid_shift_px"] if v is not None]
    ratios = [v for v in stats["area_ratio"] if v is not None]
    lo, hi = limits.get("area_ratio", [0.0, math.inf])
    out = {"min_iou": min(present) if present else None,
           "worst_iou_frame": int(np.nanargmin([np.nan if v is None else v for v in iou])) if present else None,
           "max_centroid_shift_px": max(shifts) if shifts else None,
           "area_ratio_range": [min(ratios), max(ratios)] if ratios else None,
           "visibility_mismatch_frames": vis_mismatch, "limits": limits}
    checks = {"iou": out["min_iou"] is not None and out["min_iou"] >= limits["min_iou"],
              "centroid": out["max_centroid_shift_px"] is not None
              and out["max_centroid_shift_px"] <= limits["max_centroid_px"],
              "area": bool(ratios) and lo <= min(ratios) and max(ratios) <= hi,
              "visibility": not vis_mismatch}
    out.update(checks=checks, passed=all(checks.values()))
    return out


def max_array_diff(a: dict, b: dict) -> dict:
    """Max |difference| per shared key of two dicts of arrays; keys present in one only are listed."""
    shared = sorted(set(a) & set(b))
    return {"max_abs": {k: float(np.abs(np.asarray(a[k], np.float64) - np.asarray(b[k], np.float64)).max())
                        for k in shared if np.shape(a[k]) == np.shape(b[k])},
            "shape_mismatch": [k for k in shared if np.shape(a[k]) != np.shape(b[k])],
            "only_reference": sorted(set(a) - set(b)), "only_candidate": sorted(set(b) - set(a))}


def run(reference: Path, candidate: Path, gate: dict) -> dict:
    from onecreations.blender_bundle import load_bundle

    ref, cand = load_bundle(reference), load_bundle(candidate)
    ref_idx, cand_idx = ref.passes()["object_index"], cand.passes()["object_index"]
    rmap, cmap = ref.manifest.passes.object_index_map, cand.manifest.passes.object_index_map
    report = {"reference": str(reference), "candidate": str(candidate), "objects": {}}
    for oc_id, limits in gate["objects"].items():
        if oc_id not in rmap or oc_id not in cmap:
            report["objects"][oc_id] = {"passed": False, "error": "object missing from a bundle's object-index map"}
            continue
        stats = compare_object(ref_idx, cand_idx, rmap[oc_id], cmap[oc_id])
        report["objects"][oc_id] = dict(evaluate_object(stats, limits), per_frame=stats)
    joints = max_array_diff(ref.joints(), cand.joints())
    rc, cc = ref.camera_arrays(), cand.camera_arrays()
    camera = max_array_diff({"c2w": rc["c2w"]}, {"c2w": cc["c2w"]})
    camera["max_abs"]["K"] = float(np.abs(ref.K() - cand.K()).max())
    jmax = max(joints["max_abs"].values(), default=math.inf)
    report["joints"] = dict(joints, passed=bool(joints["max_abs"]) and not joints["shape_mismatch"]
                            and not joints["only_reference"] and not joints["only_candidate"]
                            and jmax <= gate["max_joint_diff_m"])
    report["camera"] = dict(camera, passed=max(camera["max_abs"].values()) <= gate["max_camera_diff"])
    report["passed"] = all(o["passed"] for o in report["objects"].values()) and report["joints"]["passed"] \
        and report["camera"]["passed"]
    return report


def load_gate(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for section in (data, data.get("m3b", {}), data.get("preregistration", {})):
        if "silhouette_gate" in section:
            return section["silhouette_gate"]
    raise KeyError(f"{path}: no silhouette_gate section")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reference", type=Path, required=True, help="reference export bundle dir (M3-A)")
    p.add_argument("--candidate", type=Path, required=True, help="candidate export bundle dir (M3-B)")
    p.add_argument("--gate", type=Path, required=True, help="pre-registration JSON or shot spec with the gate")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    rep = run(a.reference, a.candidate, load_gate(a.gate))
    a.out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    summary = {k: {kk: v.get(kk) for kk in ("passed", "min_iou", "max_centroid_shift_px", "area_ratio_range")}
               for k, v in rep["objects"].items()}
    print(json.dumps({"passed": rep["passed"], "objects": summary, "joints": rep["joints"]["passed"],
                      "camera": rep["camera"]["passed"]}, indent=1))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
