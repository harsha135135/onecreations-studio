import json

import numpy as np
import pytest

from tools.admission import control_diagnostic as cd

H, W, N = 160, 256, 9
R2D = cd.load_tracking(None)


def scene(box_x: list[int], ball_r: list[int]) -> np.ndarray:
    """Synthetic flat-colour frames: red box moving in x, blue disc with radius ball_r."""
    frames = np.full((len(box_x), H, W, 3), 190, np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    for i, (bx, br) in enumerate(zip(box_x, ball_r)):
        frames[i, 100:150, bx:bx + 60] = (205, 20, 20)
        if br > 0:
            frames[i][(yy - 40) ** 2 + (xx - 128) ** 2 <= br ** 2] = (20, 40, 215)
    return frames


def track(frames, tracking=R2D):
    return cd.track_colors(frames, tracking["subjects"])


def test_color_masks_and_stats():
    f = scene([10], [12])[0]
    red = cd.mask_stats(cd.color_mask(f, "red"))
    blue = cd.mask_stats(cd.color_mask(f, "blue"))
    assert red["bbox"] == [10, 100, 69, 149] and red["area_px"] == 60 * 50
    assert red["h_cells"] == round(50 / 64, 2) and red["area_cells"] == round(3000 / 4096, 2)
    assert abs(blue["cx"] - 128) < 0.5 and abs(blue["cy"] - 40) < 0.5
    assert cd.mask_stats(np.zeros((4, 4), bool)) is None
    assert cd.checkpoint_frames(49) == [0, 12, 24, 36, 48]


def test_default_tracking_reproduces_r2d_rules():
    gt = track(scene([10 + 20 * i for i in range(N)], [8 + 3 * i for i in range(N)]))
    same = cd.classify(gt, gt, N, R2D)
    assert same["metric_class"] == "PASS"
    assert same["subjects"]["r2d_box"]["checks"]["lateral"]["travel_frac"] == 1.0
    assert same["subjects"]["r2d_ball"]["checks"]["approach"]["threshold"] == 2.0
    static_box = track(scene([10] * N, [8 + 3 * i for i in range(N)]))
    assert cd.classify(static_box, gt, N, R2D)["metric_class"] == "PARTIAL"
    reversed_all = track(scene([170 - 20 * i for i in range(N)], [32 - 3 * i for i in range(N)]))
    r = cd.classify(reversed_all, gt, N, R2D)
    assert r["metric_class"] == "FAIL"
    assert r["subjects"]["r2d_box"]["checks"]["lateral"]["direction_correct"] is False
    no_ball = track(scene([10 + 20 * i for i in range(N)], [0] * N))
    assert cd.classify(no_ball, gt, N, R2D)["metric_class"] is None


def test_spec_driven_checks_gt_relative_gain_and_report_only(tmp_path):
    spec = {"tracking": {"subjects": {
        "r2d_box": {"color": "red", "role": "primary", "checks": {"lateral": {"monotone_tol_px": 16, "min_travel_frac": 0.5},
                                                                  "approach": {"min_gain_frac": 0.5}}},
        "r2d_ball": {"color": "blue", "role": "secondary", "checks": {"report_only": {}}}}}}
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    tracking = cd.load_tracking(path)
    assert tracking["ground"] == [] and tracking["gate"] == {}

    def grow(box_x, h):
        frames = np.full((len(box_x), H, W, 3), 190, np.uint8)
        for i, (bx, hh) in enumerate(zip(box_x, h)):
            frames[i, 150 - hh:150, bx:bx + 40] = (205, 20, 20)
        return frames

    xs = [10 + 20 * i for i in range(N)]
    gt = track(grow(xs, [40 + 2 * i for i in range(N)]), tracking)       # area ratio 56/40 = 1.4
    weak = track(grow(xs, [40 + 1 * i for i in range(N)]), tracking)     # 1.2 >= 1 + 0.5 * 0.4
    shrink = track(grow(xs, [40 - 1 * i for i in range(N)]), tracking)
    res = cd.classify(weak, gt, N, tracking)
    appr = res["subjects"]["r2d_box"]["checks"]["approach"]
    assert appr["threshold"] == pytest.approx(1.2) and appr["followed"] is True and res["metric_class"] == "PASS"
    assert "report_only" in res["subjects"]["r2d_ball"]["checks"]   # secondary never drives the class
    bad = cd.classify(shrink, gt, N, tracking)
    assert bad["subjects"]["r2d_box"]["checks"]["approach"]["direction_correct"] is False
    assert bad["metric_class"] == "PARTIAL"                          # lateral still followed
    with pytest.raises(ValueError):
        (tmp_path / "empty.json").write_text("{}")
        cd.load_tracking(tmp_path / "empty.json")


def test_occlusion_contrast_dilate_and_drift():
    idx = np.zeros((40, 40), np.int32)
    depth = np.full((40, 40), 20.0)
    idx[10:30, 10:20], depth[10:30, 10:20] = 1, 6.0           # subject at 6 m
    idx[30:40, :], depth[30:40, :] = 7, 4.0                    # ground in front (ignored)
    assert cd.occlusion_fraction(idx, depth, 1, {7}) == 0.0
    idx[12:16, 10:20], depth[12:16, 10:20] = 3, 3.0           # a nearer pillar crossing the subject
    assert cd.occlusion_fraction(idx, depth, 1, {7}) > 0.15
    m = np.zeros((9, 9), bool)
    m[4, 4] = True
    assert cd.dilate(m, 2).sum() == 25 and cd.dilate(m, 2)[2:7, 2:7].all()
    ctrl = np.zeros((40, 40), np.uint8)
    ctrl[10:30, 10:20] = 200
    subj = np.zeros((40, 40), bool)
    subj[10:30, 10:20] = True
    assert cd.control_contrast(ctrl, subj) == pytest.approx(200 / 255, abs=1e-3)
    frames = np.zeros((3, 4, 4, 3), np.uint8)
    frames[2] += 51
    sm = np.ones((4, 4), bool)
    assert cd.static_drift(frames, sm, [0, 2]) == [0.0, 0.2]
    assert cd.static_drift(frames, np.zeros((4, 4), bool), [0]) == [None]
