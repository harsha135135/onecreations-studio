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


def test_gold_mask_separates_gold_from_warm_stone():
    px = np.array([[(230, 180, 60), (120, 85, 25), (200, 170, 130), (110, 95, 75), (200, 20, 15), (215, 205, 170),
                    (190, 170, 150)]], np.uint8)
    assert cd.color_mask(px, "gold").tolist() == [[True, True, False, False, False, False, False]]


def head_track(cy: list[float], cx: list[float] | None = None) -> list[dict | None]:
    cx = cx or [100.0] * len(cy)
    return [None if y is None else {"cx": float(x), "cy": float(y), "area_px": 900} for x, y in zip(cx, cy)]


# guard (8 frames), rise to an apex at 12, eased fast drop to a stop at 18, hold, recovery that ends lower on screen
STRIKE = [120.0] * 8 + [110, 90, 70, 55, 50, 52, 70, 120, 190, 240, 250, 250, 250, 250, 251, 252, 251, 230, 180]


def test_strike_events_and_timing_check():
    ev = cd.strike_events(head_track(STRIKE))
    assert ev["apex"] == 12 and ev["contact"] == 18 and ev["peak_speed_frame"] == 15 and ev["excursion_px"] == 200
    late = STRIKE[:15] + [90, 120, 150, 190, 220, 240, 250, 250, 250, 250, 250, 250]   # stops at 21, 3 frames late
    params = {"tol_frames": 2, "stop_px": 4, "min_excursion_frac": 0.5, "min_detect_frac": 0.9, "min_dx_px": 32}
    gt = head_track(STRIKE)
    on_time = cd.check_timing(head_track(STRIKE), gt, [], params)
    assert on_time["followed"] is True and on_time["apex_offset_frames"] == 0 and not on_time["dx_check_applicable"]
    off = cd.check_timing(head_track(late), gt, [], params)
    assert off["contact_offset_frames"] == 3 and off["followed"] is False and off["direction_correct"] is True
    flat = cd.check_timing(head_track([120.0] * len(STRIKE)), gt, [], params)
    assert flat["followed"] is False and flat["direction_correct"] is False
    sparse = cd.check_timing(head_track([None] * 10 + STRIKE[10:]), gt, [], params)
    assert sparse["followed"] is None                                        # metric unavailable, not a failure
    sideways = head_track(STRIKE, [100.0] * 13 + [100, 90, 80, 60, 40, 30] + [30.0] * 8)
    gt_side = cd.check_timing(sideways, sideways, [], params)
    assert gt_side["dx_check_applicable"] and gt_side["followed"]
    assert cd.check_timing(head_track(STRIKE, [100.0] * 13 + [100, 110, 120, 140, 160, 170] + [170.0] * 8),
                           sideways, [], params)["dx_ok"] is False


def test_position_check_for_a_stationary_root():
    n = len(STRIKE)
    body = lambda dx, area: [{"cx": 200.0 + dx * i / (n - 1), "cy": 150.0, "area_px": int(20000 * (1 + area * i / (n - 1)))}
                             for i in range(n)]
    cps = cd.checkpoint_frames(n)
    gt = body(0, 0)
    offset = [dict(r, cx=r["cx"] + 9) for r in body(0, 0.05)]                # constant tracker offset cancels
    assert cd.check_position(offset, gt, cps, {"tol_px": 32, "area_tol": 0.25})["followed"] is True
    walks = cd.check_position(body(60, 0), gt, cps, {"tol_px": 32, "area_tol": 0.25})
    assert walks["followed"] is False and walks["displacement_err_px"][-1] == 60.0
    shrinks = cd.check_position(body(0, -0.4), gt, cps, {"tol_px": 32, "area_tol": 0.25})
    assert shrinks["followed"] is False and shrinks["direction_correct"] is True
    tracking = {"subjects": {"body": {"color": "red", "role": "primary", "checks": {"position": {}}},
                             "head": {"color": "gold", "role": "primary", "checks": {"timing": {}}}}}
    res = cd.classify({"body": body(60, 0), "head": head_track(STRIKE)},
                      {"body": gt, "head": head_track(STRIKE)}, len(STRIKE), tracking)
    assert res["metric_class"] == "PARTIAL"                                  # weapon followed, body translated


def test_self_occluders_are_ignored_and_frame_border():
    idx = np.zeros((40, 40), np.int32)
    depth = np.full((40, 40), 20.0)
    idx[5:35, 10:25], depth[5:35, 10:25] = 1, 6.0             # body
    idx[12:20, 18:28], depth[12:20, 18:28] = 8, 5.5           # its own weapon in front
    assert cd.occlusion_fraction(idx, depth, 1, set()) > 0.1
    assert cd.occlusion_fraction(idx, depth, 1, {8}) == 0.0
    assert cd.in_frame({"bbox": [1, 1, 38, 38]}, 40, 40) and not cd.in_frame({"bbox": [0, 5, 20, 20]}, 40, 40)
    assert not cd.in_frame(None, 40, 40)


def test_joint_checks_and_timeline_agreement():
    from fractions import Fraction
    from onecreations.geometry.intrinsics import project

    f_count, k = 30, np.array([[100.0, 0, 64], [0, 100.0, 48], [0, 0, 1]])
    cam = np.eye(4)
    cam[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]                        # Blender camera rotated 90 deg about X:
    c2w = np.repeat(cam[None], f_count, axis=0)                             # looks along world +Y, world Z is up
    t = np.arange(f_count)
    z_world = np.where(t < 10, 1.0 + 0.1 * t, np.maximum(2.0 - 0.4 * (t - 10), 0.2))   # apex 10, floor from 15
    tails = np.zeros((f_count, 2, 3))
    tails[:, 1] = np.stack([0.2 * np.ones(f_count), 5.0 * np.ones(f_count), z_world], axis=1)
    heads = np.zeros((f_count, 2, 3))
    uv = np.array([project(tails[i, 1][None], c2w[i], k)[0][0] for i in range(f_count)])
    track = [{"cx": u - 0.5 + 0.3, "cy": v - 0.5} for u, v in uv]
    cfg = {"weapon_bone": "mace", "stationary_bones": ["root"], "max_projection_err_px": 3.0, "max_stationary_m": 1e-3}
    res = cd.joint_checks(heads, tails, ["root", "mace"], c2w, k, track, cfg)
    assert res["passed"] and res["projection_err_px"]["max"] == pytest.approx(0.3, abs=1e-6)
    assert res["weapon_height_events_3d"]["apex"] == 10 and res["weapon_height_events_3d"]["contact"] == 15
    moved = heads.copy()
    moved[5:, 0, 0] = 0.01
    assert cd.joint_checks(moved, tails, ["root", "mace"], c2w, k, track, cfg)["stationary_ok"] is False
    timeline = {"phases": [{"id": "windup", "end": "23/24"}, {"id": "strike", "end": "29/24"}]}
    expected = cd.timeline_frames(timeline, Fraction(24), "windup", "strike")
    assert expected == {"apex": 23, "contact": 29}
    ok = cd.timeline_agreement(expected, {"a": {"apex": 23, "contact": 30}}, 1)
    bad = cd.timeline_agreement(expected, {"a": {"apex": 23, "contact": 31}, "b": None}, 1)
    assert ok["passed"] and not bad["passed"] and bad["observed"]["b"] is None


def test_m2c_landmark_colour_masks():
    # rendered M2-C values (reference): green, magenta, cyan banners; ash-blue ascetic, sunlit stone, sky, crimson, gold
    px = np.array([[(75, 202, 71), (230, 66, 177), (64, 193, 183), (153, 176, 190), (200, 170, 130), (190, 170, 150),
                    (225, 81, 68), (230, 180, 60)]], np.uint8)
    assert cd.color_mask(px, "green").tolist() == [[True] + [False] * 7]
    assert cd.color_mask(px, "magenta").tolist() == [[False, True] + [False] * 6]
    assert cd.color_mask(px, "cyan").tolist() == [[False, False, True] + [False] * 5]


def landmark(points):
    return [{"cx": float(x), "cy": float(y), "area_px": 900} for x, y in points]


def test_trajectory_check_direction_magnitude_stall_and_jump():
    n = 25
    cps = cd.checkpoint_frames(n)
    gt = landmark([(100 + 4 * i, 80 - 1 * i) for i in range(n)])               # moves +96, -24 px
    p = {"min_cos": 0.9, "mag_ratio": [0.6, 1.6], "cp_err_frac": 0.3, "cp_err_min_px": 16, "reversal_tol": 0.1,
         "jump_factor": 3.0, "jump_px": 12, "progress_tol": 0.25}
    short = cd.check_trajectory(landmark([(100 + 3.6 * i, 80 - 0.9 * i) for i in range(n)]), gt, cps, p)
    assert short["followed"] and short["magnitude_ratio"] == pytest.approx(0.9, abs=1e-3) and short["cos"] > 0.999
    backwards = cd.check_trajectory(landmark([(100 - 4 * i, 80 + i) for i in range(n)]), gt, cps, p)
    assert backwards["followed"] is False and backwards["direction_correct"] is False
    stall = cd.check_trajectory(landmark([(100 + 4 * min(i, 6), 80 - min(i, 6)) for i in range(n - 1)]
                                         + [(196, 56)]), gt, cps, p)      # stops at 25 %, then one jump to the end
    assert stall["followed"] is False and max(v for v in stall["progress_lag"] if v is not None) > 0.25
    assert stall["max_step_px"] > stall["jump_limit_px"]
    lost = cd.check_trajectory(landmark([(100 + 4 * i, 80 - i) for i in range(n)])[:10] + [None] * (n - 10), gt, cps, p)
    assert lost["followed"] is None                                          # metric unavailable, not a verdict


def test_parallax_check_orders_and_ratios():
    n = 25

    def lm(dx):
        return landmark([(50 + dx * i / (n - 1), 60) for i in range(n)])

    gt = {"near": lm(50), "mid": lm(80), "far": lm(115)}
    layers = ["near", "mid", "far"]
    same = cd.check_parallax({k: lm(0.9 * d) for k, d in (("near", 50), ("mid", 80), ("far", 115))}, gt, layers,
                             {"min_gt_separation": 1.25, "ratio_tol": 1.35})
    assert same["followed"] and same["order_agrees"] and same["normalised_generated"]["near"] == pytest.approx(0.435, abs=1e-3)
    swapped = cd.check_parallax({"near": lm(115), "mid": lm(80), "far": lm(50)}, gt, layers, {})
    assert swapped["order_agrees"] is False and swapped["followed"] is False
    flat = cd.check_parallax({"near": lm(80), "mid": lm(85), "far": lm(90)}, gt, layers, {"ratio_tol": 1.35})
    assert flat["order_agrees"] is True and flat["followed"] is False        # right order, parallax far too weak


def test_camera_contract_and_visibility_timeline():
    from fractions import Fraction

    t = np.arange(5) / 24
    authored = {"t": t, "position": np.zeros((5, 3)), "quaternion_wxyz": np.tile([1.0, 0, 0, 0], (5, 1)),
                "lens_mm": np.full(5, 35.0)}
    ok = cd.camera_contract(dict(authored), authored, Fraction(24), {"max_position_err_m": 1e-3, "max_angle_err_deg": 0.05})
    assert ok["passed"] and ok["lens_fixed"]
    moved = dict(authored, position=authored["position"] + [0, 0, 0.01])
    assert cd.camera_contract(moved, authored, Fraction(24), {})["passed"] is False
    zoom = dict(authored, lens_mm=np.linspace(35, 40, 5))
    assert cd.camera_contract(zoom, authored, Fraction(24), {})["lens_fixed"] is False
    tl = cd.visibility_timeline([70, 75, 80, 95, 100, 100], 0.9)
    assert tl["hidden_frames"] == [0, 1, 2] and tl["hidden_intervals"] == [[0, 2]]
    cmp = cd.compare_timelines(tl, cd.visibility_timeline([70, 80, 100, 100, 100, 100], 0.9))
    assert cmp == {"hidden_iou": round(2 / 3, 3), "first_hidden_offset": 0, "last_hidden_offset": -1}
    assert cd._occlusion_fracs({"subjects": ["a"], "visible_frac": 0.4}) == {"a": 0.4}
    assert cd._occlusion_fracs({"subjects": {"a": 0.9}}) == {"a": 0.9}
