import numpy as np
import pytest

from onecreations.camera import analysis, io_colmap, io_csv, normalize, retarget
from onecreations.camera.trajectory import CameraTrajectory
from onecreations.geometry import conventions, quat


def orbit(radius=4.0, height=1.5, seconds=4.0, n=97, revolutions=1.0):
    t = np.linspace(0, seconds, n)
    ang = 2 * np.pi * revolutions * t / seconds
    eyes = np.stack([radius * np.cos(ang), radius * np.sin(ang), np.full_like(ang, height)], axis=1)
    c2w = np.stack([conventions.look_at(e, [0, 0, height]) for e in eyes])
    return CameraTrajectory.from_c2w(t, c2w)


def dolly(seconds=2.0, n=5, speed=1.5):
    t = np.linspace(0, seconds, n)
    eyes = np.stack([np.zeros(n), -10 + speed * t, np.full(n, 1.6)], axis=1)
    c2w = np.stack([conventions.look_at(e, e + [0, 1, 0]) for e in eyes])
    return CameraTrajectory.from_c2w(t, c2w)


def test_interpolation_hits_samples_and_rejects_out_of_range():
    tr = orbit()
    pos, q = tr.evaluate(tr.t)
    assert np.allclose(pos, tr.position, atol=1e-12)
    assert all(quat.angle_between(a, b) < 1e-9 for a, b in zip(q, tr.quaternion))
    with pytest.raises(ValueError):
        tr.evaluate([tr.end + 0.1])
    with pytest.raises(ValueError):
        CameraTrajectory([0, 0], np.zeros((2, 3)), [[1, 0, 0, 0]] * 2)


def test_resample_is_deterministic():
    tr = orbit()
    a = tr.resample(rate=120)
    b = tr.resample(rate=120)
    assert np.array_equal(a.position, b.position) and np.array_equal(a.quaternion, b.quaternion)


def test_orbit_stats_match_analytic_values():
    r, secs = 4.0, 4.0
    st = analysis.trajectory_stats(orbit(radius=r, seconds=secs))
    omega = 2 * np.pi / secs
    assert st["path_length_m"] == pytest.approx(2 * np.pi * r, rel=1e-3)
    assert st["speed_mps"]["mean"] == pytest.approx(r * omega, rel=1e-3)
    assert st["angular_speed_dps_max"] == pytest.approx(360 / secs, rel=1e-3)
    assert abs(st["roll_deg"]["min"]) < 1e-6 and abs(st["roll_deg"]["max"]) < 1e-6
    # centripetal r*omega^2, including the end segments (quadratic end tangents)
    assert st["accel_mps2_max"] == pytest.approx(r * omega ** 2, rel=0.01)


def test_dolly_stats():
    st = analysis.trajectory_stats(dolly(speed=1.5))
    assert st["speed_mps"]["max"] == pytest.approx(1.5, rel=1e-9)
    assert st["path_length_m"] == pytest.approx(3.0, rel=1e-9)
    assert st["angular_speed_dps_max"] == pytest.approx(0, abs=1e-9)


def test_retarget_preserves_relative_motion():
    tr = orbit()
    src = retarget.Anchor((0, 0, 1.5), 0)
    dst = retarget.Anchor((10, 5, 0.5), 90)
    out = retarget.retarget(tr, src, dst, scale=0.5, time_scale=2.0)
    # distance to the anchor scales; camera still looks at the (moved) anchor
    d_src = np.linalg.norm(tr.position - np.array(src.position), axis=1)
    d_dst = np.linalg.norm(out.position - np.array(dst.position), axis=1)
    assert np.allclose(d_dst, 0.5 * d_src)
    fwd = conventions.camera_forward(out.c2w())
    to_anchor = np.array(dst.position) - out.position
    to_anchor /= np.linalg.norm(to_anchor, axis=1, keepdims=True)
    assert np.allclose(np.einsum("ij,ij->i", fwd, to_anchor), 1.0)
    assert out.duration == pytest.approx(2 * tr.duration)
    assert out.meta["provenance"]["source"] == "retargeted"
    assert [op["op"] for op in out.meta["operations"]] == ["retarget", "time_scale"]


def test_clearance_violation_detected():
    tr = dolly(speed=1.5)  # y from -10 to -7 at x=0, z=1.6
    pillar = retarget.AABB("pillar", (-0.2, -8.6, 0), (0.2, -8.4, 3))
    rep = retarget.clearance_report(tr, [pillar], minimum_clearance_m=0.15)
    assert not rep["ok"] and rep["violations"][0]["proxy"] == "pillar"
    assert rep["min_distance_m"] < 0  # passes through it
    far = retarget.Sphere("statue", (5, 0, 0), 1.0)
    assert retarget.clearance_report(tr, [far], 0.15)["ok"]


def test_normalize_align_up_and_scale():
    tr = orbit()
    tilt = normalize.rotation_between([0, 0, 1], [0, 1, 1])
    tilted = normalize.apply_similarity(tr, rotation=tilt)
    fixed = normalize.align_up(tilted, measured_up=tilt @ [0, 0, 1])
    assert np.allclose(fixed.position, tr.position, atol=1e-9)
    assert fixed.meta["provenance"]["up_axis"] == "aligned"
    s = normalize.scale_from_known_distance(2.0, 3.0)
    scaled = normalize.set_metric_scale(tr, s, "door width 0.9 m measured in frame 12")
    assert np.allclose(scaled.position, 1.5 * tr.position)
    assert scaled.meta["provenance"]["scale"] == "metric_estimated"
    with pytest.raises(ValueError):
        normalize.apply_similarity(tr, scale=-1)


def test_csv_roundtrip(tmp_path):
    tr = orbit(n=9)
    io_csv.write_csv(tr, tmp_path / "o.csv")
    back = io_csv.read_csv(tmp_path / "o.csv")
    assert np.array_equal(back.t, tr.t) and np.array_equal(back.position, tr.position)


def test_npz_roundtrip(tmp_path):
    tr = orbit(n=9)
    tr.meta["provenance"] = {"source": "authored"}
    tr.save_npz(tmp_path / "o.npz")
    back = CameraTrajectory.load_npz(tmp_path / "o.npz")
    assert np.array_equal(back.position, tr.position) and back.meta == tr.meta


def test_colmap_import_reproduces_blender_poses(tmp_path):
    tr = orbit(n=12)
    names = [f"frame_{i:04d}.jpg" for i in range(len(tr))]
    io_colmap.write_images_txt(tmp_path / "images.txt", tr.c2w(), names)
    imgs = io_colmap.parse_images_txt(tmp_path / "images.txt")
    back = io_colmap.images_to_trajectory(imgs, fps=24)
    assert np.allclose(back.c2w(), tr.c2w(), atol=1e-9)
    assert back.meta["provenance"]["scale"] == "unknown"
    assert np.allclose(np.diff(back.t), 1 / 24)
    (tmp_path / "cameras.txt").write_text("# c\n1 PINHOLE 640 360 500 501 320 180\n2 SIMPLE_PINHOLE 64 36 50 32 18\n")
    cams = io_colmap.parse_cameras_txt(tmp_path / "cameras.txt")
    assert cams[1]["K"][1][1] == 501 and cams[2]["K"][0][0] == 50
