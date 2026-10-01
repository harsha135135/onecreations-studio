import numpy as np
import pytest

from onecreations.geometry import conventions, intrinsics, quat
from onecreations.geometry.intrinsics import BlenderCameraParams

RNG = np.random.default_rng(7)


def random_quats(n):
    return quat.normalize(RNG.normal(size=(n, 4)))


def test_matrix_quat_roundtrip():
    for q in random_quats(200):
        q2 = quat.from_matrix(quat.to_matrix(q))
        assert quat.angle_between(q, q2) < 1e-9


def test_slerp_endpoints_and_midpoint():
    a = quat.from_axis_angle([0, 0, 1], 0.0)
    b = quat.from_axis_angle([0, 0, 1], np.radians(90))
    assert np.allclose(quat.slerp(a, b, 0), a)
    assert np.allclose(quat.slerp(a, b, 1), b)
    mid = quat.slerp(a, b, 0.5)
    assert quat.angle_between(mid, quat.from_axis_angle([0, 0, 1], np.radians(45))) < 1e-12
    # shortest path even when b is given in the opposite hemisphere
    assert quat.angle_between(quat.slerp(a, -b, 0.5), mid) < 1e-12


def test_make_continuous_removes_sign_flips():
    qs = np.array([quat.from_axis_angle([0, 0, 1], np.radians(a)) for a in range(0, 360, 10)])
    qs[5::2] *= -1
    c = quat.make_continuous(qs)
    assert np.all(np.einsum("ij,ij->i", c[1:], c[:-1]) > 0)


def test_blender_opencv_roundtrip_and_axes():
    c2w = conventions.look_at([0, -5, 1], [0, 0, 1])
    cv = conventions.blender_c2w_to_opencv(c2w)
    assert np.allclose(conventions.opencv_c2w_to_blender(cv), c2w)
    # Blender camera looks down -Z: forward should be +Y here; OpenCV forward is its +Z column
    assert np.allclose(conventions.camera_forward(c2w), [0, 1, 0])
    assert np.allclose(cv[:3, 2], [0, 1, 0])
    assert np.allclose(cv[:3, 1], [0, 0, -1])  # OpenCV +Y is down


def test_validate_rigid_catches_flipped_axis_and_scale():
    c2w = conventions.look_at([1, -4, 2], [0, 0, 0])
    conventions.validate_rigid(c2w)
    flipped = c2w @ np.diag([1, 1, -1, 1])
    with pytest.raises(conventions.ConventionError, match="det"):
        conventions.validate_rigid(flipped)
    scaled = c2w @ np.diag([2, 2, 2, 1])
    with pytest.raises(conventions.ConventionError, match="orthonormal"):
        conventions.validate_rigid(scaled)


def test_roll_angle_matches_look_at_roll():
    for deg in (-30, 0, 12.5, 80):
        m = conventions.look_at([3, -6, 2], [0, 0, 1], roll_rad=np.radians(deg))
        assert np.degrees(conventions.roll_angle(m)) == pytest.approx(deg, abs=1e-9)
    straight_down = conventions.look_at([0, 0, 5], [0, 0, 0], world_up=(0, 1, 0))
    assert np.isnan(conventions.roll_angle(straight_down))


def k_of(**kw):
    return intrinsics.intrinsic_matrix(BlenderCameraParams(**kw))


def test_intrinsics_horizontal_fit_hand_computed():
    k = k_of(lens_mm=50, sensor_width_mm=36, resolution_x=1920, resolution_y=1080)
    fx = 50 / 36 * 1920
    assert np.allclose(k, [[fx, 0, 960], [0, fx, 540], [0, 0, 1]])


def test_intrinsics_vertical_fit_shift_and_pixel_aspect():
    # portrait image with AUTO fit → vertical fit, but AUTO still uses sensor *width* as the fitted size
    k = k_of(lens_mm=35, sensor_width_mm=36, sensor_height_mm=24, resolution_x=1080, resolution_y=1920,
             shift_x=0.1, shift_y=-0.05)
    view_fac = 1920
    f = 35 / 36 * view_fac
    assert np.allclose(k, [[f, 0, 540 - 0.1 * view_fac], [0, f, 960 - 0.05 * view_fac], [0, 0, 1]])
    # explicit VERTICAL fit uses the sensor height
    kv = k_of(lens_mm=35, sensor_height_mm=24, sensor_fit="VERTICAL", resolution_x=1920, resolution_y=1080)
    assert kv[1, 1] == pytest.approx(35 / 24 * 1080)
    # non-square pixels: fy = fx / (pa_y / pa_x)
    ka = k_of(lens_mm=50, resolution_x=1440, resolution_y=1080, pixel_aspect_x=4 / 3, pixel_aspect_y=1)
    assert ka[1, 1] == pytest.approx(ka[0, 0] * (4 / 3))


def test_project_unproject_roundtrip_and_inverted_pose_is_caught():
    p = BlenderCameraParams(lens_mm=35, shift_x=0.05, shift_y=-0.03, resolution_x=640, resolution_y=360)
    k = intrinsics.intrinsic_matrix(p)
    c2w = conventions.look_at([2, -6, 1.5], [0, 0, 0.5], roll_rad=np.radians(7))
    pts = RNG.uniform(-1, 1, size=(50, 3)) + [0, 0, 0.5]
    uv, z = intrinsics.project(pts, c2w, k)
    assert np.all(z > 0)
    back = intrinsics.unproject(uv, z, c2w, k)
    assert np.allclose(back, pts, atol=1e-9)
    # a world->camera matrix passed where camera->world is expected projects the scene behind the camera
    w2c = conventions.invert_rigid(c2w)
    _, z_wrong = intrinsics.project(pts, w2c, k)
    assert not np.all(z_wrong > 0) or not np.allclose(intrinsics.project(pts, w2c, k)[0], uv, atol=1.0)


def test_target_projects_to_principal_point_and_planar_factor():
    p = BlenderCameraParams(lens_mm=50, resolution_x=200, resolution_y=100)
    k = intrinsics.intrinsic_matrix(p)
    c2w = conventions.look_at([0, -4, 0], [0, 0, 0])
    uv, z = intrinsics.project(np.array([[0.0, 0.0, 0.0]]), c2w, k)
    assert np.allclose(uv, [[100, 50]]) and z[0] == pytest.approx(4)
    f = intrinsics.euclidean_to_planar_factor(200, 100, k)
    assert f.max() <= 1 and f.max() > 0.9999 and f[0, 0] < f[50, 100]
