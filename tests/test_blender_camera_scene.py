"""Headless-Blender test of the M2-C camera scene: the authored CameraMotion validates, survives the Session A import
(oc_import_camera) and export (oc_export) round trip, the actor is static, the camera keeps its clearance, and the
landmark banners exist as separate objects. Skipped when Blender is not installed."""

import json
from fractions import Fraction

import numpy as np
import pytest

from onecreations import blender_bridge as bb
from onecreations.blender_bundle import load_bundle
from onecreations.camera.retarget import clearance_report, proxies_from_dicts
from onecreations.camera.trajectory import CameraTrajectory
from onecreations.contracts import CameraMotion
from onecreations.hashing import file_sha256
from tools.admission import control_diagnostic as cd

pytestmark = pytest.mark.blender

if bb.find_blender() is None:
    pytest.skip("Blender not installed", allow_module_level=True)


@pytest.fixture(scope="module")
def m2c(tmp_path_factory):
    root = tmp_path_factory.mktemp("m2c")
    blend, spec = root / "m2c_camera.blend", root / "shot_spec.json"
    bb.run_script("build_temple_camera_scene.py", ["--out", blend, "--spec", spec])
    bb.run_script("oc_export.py", ["--out", root / "export", "--shot-id", "m2c_camera"], blend=blend)
    return {"root": root, "spec": json.loads(spec.read_text(encoding="utf-8")), "bundle": load_bundle(root / "export")}


def test_camera_motion_contract_and_round_trip(m2c):
    root = m2c["root"]
    motion = CameraMotion.model_validate(json.loads((root / "camera_motion.json").read_text(encoding="utf-8")))
    assert motion.trajectory == "camera_motion.npz" and motion.trajectory_sha256 == file_sha256(root / "camera_motion.npz")
    assert motion.intrinsics.lens_mm == 35.0 and motion.constraints.minimum_clearance_m == 1.0
    with np.load(root / "camera_motion.npz", allow_pickle=False) as z:
        authored = {k: z[k] for k in z.files if k != "meta_json"}
    res = cd.camera_contract(m2c["bundle"].camera_arrays(), authored, Fraction(24), {})
    assert res["passed"] and res["samples"] == 49 and res["lens_fixed"]
    assert res["max_position_err_m"] < 1e-5 and res["max_angle_err_deg"] < 1e-3


def test_actor_static_banners_and_clearance(m2c):
    b, spec = m2c["bundle"], m2c["spec"]
    objects = b.objects()
    assert np.abs(objects["m2c_asura"] - objects["m2c_asura"][0]).max() < 1e-9      # no subject motion at all
    by_id = {o.oc_id: o for o in b.manifest.objects}
    assert {by_id[k].pass_index for k in ("m2c_lm_near", "m2c_lm_mid", "m2c_lm_far")} == {10, 11, 12}
    cam = b.camera_arrays()
    assert np.linalg.norm(cam["position"][-1] - cam["position"][0]) > 3.0              # the camera really moves
    assert spec["camera_clearance"]["ok"] and spec["camera_clearance"]["min_distance_m"] >= 1.0
    traj = CameraTrajectory.load_npz(m2c["root"] / "camera_motion.npz")
    assert clearance_report(traj, proxies_from_dicts(spec["clearance_proxies"]), 1.0)["ok"]
    tracking = spec["tracking"]
    assert tracking["parallax"]["layers"] == ["m2c_lm_near", "m2c_lm_mid", "m2c_lm_far"]
