"""Headless-Blender tests of the Blender → OneCreations contract (v1 §15 diagnostic scene).

They check the exported data against independent references: Blender's own world_to_camera_view, ray-cast depth,
known scene geometry (floor z = 0, wall y = 6), analytic keyframed motion, and a re-import round trip.
Skipped automatically when Blender is not installed (set ONECREATIONS_BLENDER to point at it).
"""

import json
import warnings

import numpy as np
import pytest

from onecreations import blender_bridge as bb
from onecreations.blender_bundle import BundleError, load_bundle
from onecreations.geometry import intrinsics as intr

pytestmark = pytest.mark.blender

EXE = bb.find_blender()
if EXE is None:
    pytest.skip("Blender not installed", allow_module_level=True)

CAM_START = np.array([0.0, -8.0, 1.5])
CAM_END = np.array([2.0, -7.0, 1.8])
HOLD_WARP = {"keys": [["0", "0"], ["1/2", "1/4"], ["1", "1/4"], ["3/2", "3/4"]]}


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    root = tmp_path_factory.mktemp("blender")
    version = bb.blender_version(EXE)
    if not bb.is_pinned(version):
        warnings.warn(f"Blender {version} is not the pinned {bb.PINNED_SERIES} LTS series")
    blend = root / "diag.blend"
    bb.run_script("build_diagnostic_scene.py", ["--out", blend])
    full = root / "full"
    bb.run_script("oc_export.py", ["--out", full, "--passes", "--probes", "--shot-id", "diag"], blend=blend)
    return {"root": root, "blend": blend, "full": full, "version": version}


def test_bundle_validates_and_records_versions(work):
    b = load_bundle(work["full"])
    m = b.manifest
    assert m.blender_version.startswith(work["version"].split()[0])
    assert m.shot.frame_count == 24 and len(m.frames) == 24
    assert m.frames[0].blender_frame == 1 and m.frames[-1].blender_frame == 24
    assert {o.oc_id for o in m.objects} >= {"diag_cube", "diag_asym", "diag_occluder", "diag_wall", "diag_floor"}
    assert m.passes is not None and m.passes.object_index_map["diag_floor"] == 5
    assert "cryptomatte_decoding" in m.deferred


def test_tampered_bundle_is_rejected(work, tmp_path):
    import shutil
    dst = tmp_path / "copy"
    shutil.copytree(work["full"], dst)
    raw = json.loads((dst / "export_manifest.json").read_text())
    raw["shot"]["id"] = "edited"
    (dst / "export_manifest.json").write_text(json.dumps(raw))
    with pytest.raises(BundleError, match="content hash"):
        load_bundle(dst)


def test_projection_matches_blender_world_to_camera_view(work):
    b = load_bundle(work["full"])
    cam, probes = b.camera_arrays(), b.probes()
    w, h = b.image_size()
    k = b.K()
    worst_xy = worst_z = 0.0
    for f in range(len(cam["c2w"])):
        uv, z = intr.project(probes["points"][f], cam["c2w"][f], k)
        ndc_ours = np.stack([uv[:, 0] / w, 1.0 - uv[:, 1] / h], axis=1)
        front = z > 0.2
        worst_xy = max(worst_xy, float(np.abs(ndc_ours[front] - probes["ndc"][f][front, :2]).max()))
        worst_z = max(worst_z, float(np.abs(z - probes["ndc"][f][:, 2]).max()))
    assert worst_xy < 2e-5, worst_xy  # normalized image coords; measured ~3e-6 (0.0005 px) on Blender 4.5 / macOS
    assert worst_z < 1e-4, worst_z


def test_depth_convention_measured_and_geometry_recovered(work):
    b = load_bundle(work["full"])
    d = b.manifest.passes.depth
    assert d.measured_convention in ("planar", "euclidean") and d.stored_as == "planar"
    chosen = d.median_error_planar_m if d.measured_convention == "planar" else d.median_error_euclidean_m
    assert chosen < 1e-3 and d.probes >= 10
    cam, p = b.camera_arrays(), b.passes()
    w, h = b.image_size()
    uv = intr.pixel_centers(w, h).reshape(-1, 2)
    for f in (0, 23):
        depth = p["depth_m"][f].reshape(-1).astype(np.float64)
        idx = p["object_index"][f].reshape(-1)
        world = intr.unproject(uv, np.where(np.isfinite(depth), depth, 0.0), cam["c2w"][f], b.K())
        floor = idx == 5
        wall = idx == 4
        assert floor.sum() > 500 and wall.sum() > 200
        assert np.abs(world[floor, 2]).max() < 1e-4          # floor plane z = 0 (measured ~3e-6 m)
        assert np.abs(world[wall, 1] - 6.0).max() < 1e-4     # wall plane y = 6 (measured ~6e-6 m)
    assert np.isinf(p["depth_m"]).sum() == 0 or np.all(p["object_index"][np.isinf(p["depth_m"])] == 0)


def test_cube_mask_matches_projected_box(work):
    b = load_bundle(work["full"])
    cam, objs, p = b.camera_arrays(), b.objects(), b.passes()
    cube = next(o for o in b.manifest.objects if o.oc_id == "diag_cube")
    corners = np.hstack([np.array(cube.bound_box_local), np.ones((8, 1))]) @ objs["diag_cube"][0].T
    uv, z = intr.project(corners[:, :3], cam["c2w"][0], b.K())
    assert np.all(z > 0)
    rows, cols = np.nonzero(p["object_index"][0] == 1)
    mask_box = np.array([cols.min(), rows.min(), cols.max() + 1, rows.max() + 1], dtype=float)
    proj_box = np.array([uv[:, 0].min(), uv[:, 1].min(), uv[:, 0].max(), uv[:, 1].max()])
    assert np.abs(mask_box - proj_box).max() <= 1.0, (mask_box, proj_box)
    # the occluder crosses the cube around frames 12-13: visible cube pixels must drop, then recover
    counts = (p["object_index"] == 1).reshape(24, -1).sum(axis=1)
    assert counts[12:14].min() < 0.6 * counts[0] and counts[16] > 0.9 * counts[0]


def test_joints_follow_the_rig(work):
    b = load_bundle(work["full"])
    j = b.joints()
    heads, tails = j["diag_rig.heads"], j["diag_rig.tails"]
    assert heads.shape == (24, 2, 3) and tails.shape == (24, 2, 3)
    assert np.allclose(heads[:, 0], [-2.5, 1.5, 0.0], atol=1e-6)        # upper bone root is fixed
    assert np.allclose(tails[0, 1], [-2.5, 1.5, 2.0], atol=1e-5)        # straight at frame 1
    assert np.linalg.norm(tails[-1, 1] - tails[0, 1]) > 0.5             # lower bone bent by frame 24


def test_timewarp_hold_and_subframe_sampling(work):
    tw_path = work["root"] / "hold.json"
    tw_path.write_text(json.dumps(HOLD_WARP))
    out = work["root"] / "warped"
    bb.run_script("oc_export.py", ["--out", out, "--timewarp", tw_path, "--shot-id", "warp"], blend=work["blend"])
    b = load_bundle(out)
    cam = b.camera_arrays()
    assert len(cam["t"]) == 36
    bf = np.array([float(f.blender_frame) for f in b.manifest.frames])
    assert any(abs(x - round(x)) == 0.5 for x in bf)  # half-frame source samples were evaluated
    expected = CAM_START + ((bf - 1.0) / 24.0)[:, None] * (CAM_END - CAM_START)
    assert np.allclose(cam["position"], expected, atol=2e-5)
    hold = cam["position"][12:25]  # output 0.5 s .. 1.0 s
    assert np.allclose(hold, hold[0], atol=1e-9)


def test_subframe_passes_are_refused(work):
    tw_path = work["root"] / "hold2.json"
    tw_path.write_text(json.dumps(HOLD_WARP))
    with pytest.raises(bb.BlenderError, match="subframe"):
        bb.run_script("oc_export.py", ["--out", work["root"] / "nope", "--timewarp", tw_path, "--passes"],
                      blend=work["blend"])


def test_camera_roundtrip_export_import_export(work):
    rt_blend = work["root"] / "rt.blend"
    bb.run_script("oc_import_camera.py", ["--samples", work["full"] / "camera_samples.npz", "--intrinsics",
                                          work["full"] / "export_manifest.json", "--camera-name", "OC_Camera_RT",
                                          "--save", rt_blend], blend=work["blend"])
    out = work["root"] / "rt_export"
    bb.run_script("oc_export.py", ["--out", out, "--camera", "OC_Camera_RT"], blend=rt_blend)
    a, b = load_bundle(work["full"]).camera_arrays(), load_bundle(out).camera_arrays()
    assert np.allclose(a["c2w"], b["c2w"], atol=1e-5)
    assert np.allclose(a["lens_mm"], b["lens_mm"])
    ia = load_bundle(work["full"]).manifest.camera.intrinsics
    ib = load_bundle(out).manifest.camera.intrinsics
    assert np.allclose(ia.K, ib.K)


def test_exports_have_identical_canonical_manifests(work):
    again = work["root"] / "again"
    bb.run_script("oc_export.py", ["--out", again, "--passes", "--probes", "--shot-id", "diag"], blend=work["blend"])
    first = load_bundle(work["full"]).manifest
    second = load_bundle(again).manifest
    assert first.camera.samples.digest == second.camera.samples.digest
    assert first.passes.file.digest == second.passes.file.digest
    assert first.content_sha256 == second.content_sha256


def test_visualizer_builds_expected_objects(work):
    from onecreations.camera.trajectory import CameraTrajectory
    summary_path = work["root"] / "viz.json"
    bb.run_script("oc_visualize_trajectory.py", [
        "--samples", work["full"] / "camera_samples.npz", "--intrinsics", work["full"] / "export_manifest.json",
        "--frustums", "6", "--target", "0,0,0.5", "--velocity", "--name", "diag",
        "--save", work["root"] / "viz.blend", "--summary", summary_path], blend=work["blend"])
    s = json.loads(summary_path.read_text())
    assert s["path_points"] == 24 and s["frustum_count"] == 6
    assert s["target_lines"] == 6 and s["velocity_vectors"] == 6
    types = sorted(s["objects"].values())
    assert types.count("CURVE") == 1 and types.count("EMPTY") == 1 and types.count("MESH") == 5
    traj = CameraTrajectory.load_npz(work["full"] / "camera_samples.npz")
    pos, _ = traj.evaluate(np.array(s["frustum_times"]))
    assert np.allclose(np.array(s["frustum_apexes"]), pos, atol=1e-6)
    assert np.allclose(s["start"], traj.position[0], atol=1e-6) and np.allclose(s["end"], traj.position[-1], atol=1e-6)
    assert (work["root"] / "viz.blend").is_file()
