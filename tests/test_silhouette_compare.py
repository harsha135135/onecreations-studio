import json

import numpy as np

from tools.admission import silhouette_compare as sc

LIMITS = {"min_iou": 0.8, "max_centroid_px": 3.0, "area_ratio": [0.85, 1.2]}


def _stack(boxes, n=3, shape=(40, 60), pidx=1):
    idx = np.zeros((n, *shape), np.uint8)
    for f in range(n):
        for (y0, y1, x0, x1) in boxes[f]:
            idx[f, y0:y1, x0:x1] = pidx
    return idx


def test_identical_masks_pass_with_iou_one():
    ref = _stack([[(10, 30, 10, 30)]] * 3)
    st = sc.compare_object(ref, ref.copy(), 1, 1)
    assert st["iou"] == [1.0] * 3 and st["centroid_shift_px"] == [0.0] * 3 and st["area_ratio"] == [1.0] * 3
    ev = sc.evaluate_object(st, LIMITS)
    assert ev["passed"] and ev["min_iou"] == 1.0


def test_pass_index_remap_shift_and_growth_are_measured():
    ref = _stack([[(10, 30, 10, 30)]] * 3, pidx=1)
    cand = _stack([[(10, 30, 10, 30)], [(10, 30, 12, 32)], [(10, 30, 10, 34)]], pidx=7)   # remapped pass index
    st = sc.compare_object(ref, cand, 1, 7)
    assert st["iou"][0] == 1.0
    assert st["iou"][1] == round(18 * 20 / (22 * 20), 4) and st["centroid_shift_px"][1] == 2.0
    assert st["area_ratio"][2] == 1.2 and st["centroid_shift_px"][2] == 2.0
    ev = sc.evaluate_object(st, LIMITS)
    assert ev["passed"] and ev["worst_iou_frame"] == 1 and ev["min_iou"] == 0.8182   # 18/22 < 20/24
    ev = sc.evaluate_object(st, dict(LIMITS, min_iou=0.9))
    assert not ev["passed"] and not ev["checks"]["iou"] and ev["checks"]["centroid"]


def test_visibility_mismatch_fails():
    ref = _stack([[(10, 30, 10, 30)], [(10, 30, 10, 30)], []])
    cand = _stack([[(10, 30, 10, 30)], [], []])
    st = sc.compare_object(ref, cand, 1, 1)
    assert st["iou"] == [1.0, 0.0, None]
    ev = sc.evaluate_object(st, LIMITS)
    assert ev["visibility_mismatch_frames"] == [1] and not ev["passed"]


def test_array_diffs_and_gate_loading(tmp_path):
    a = {"rig.heads": np.zeros((2, 3, 3)), "rig.tails": np.ones((2, 3, 3)), "old": np.zeros(1)}
    b = {"rig.heads": np.full((2, 3, 3), 1e-7), "rig.tails": np.ones((2, 4, 3))}
    d = sc.max_array_diff(a, b)
    assert abs(d["max_abs"]["rig.heads"] - 1e-7) < 1e-12 and d["shape_mismatch"] == ["rig.tails"]
    assert d["only_reference"] == ["old"] and d["only_candidate"] == []
    gate = {"objects": {"x": LIMITS}, "max_joint_diff_m": 1e-6, "max_camera_diff": 1e-6}
    (tmp_path / "p.json").write_text(json.dumps({"experiment": "e", "silhouette_gate": gate}), encoding="utf-8")
    (tmp_path / "s.json").write_text(json.dumps({"shot": "s", "m3b": {"silhouette_gate": gate}}), encoding="utf-8")
    assert sc.load_gate(tmp_path / "p.json") == gate == sc.load_gate(tmp_path / "s.json")
