"""Headless-Blender test of the SHOWCASE v1 scene: the continuous characters are fully skinned on the unchanged M2-B
rig, the strike timing and camera contract survive the export, the defender is static and the layer manifest with the
new fields validates. Skipped when Blender is not installed."""

import json
from fractions import Fraction

import numpy as np
import pytest

from onecreations import blender_bridge as bb
from onecreations.blender_bundle import load_bundle
from onecreations.contracts import ActionTimeline, CameraMotion, CompositeManifest
from tools.admission import control_diagnostic as cd

pytestmark = pytest.mark.blender

if bb.find_blender() is None:
    pytest.skip("Blender not installed", allow_module_level=True)


@pytest.fixture(scope="module")
def sc(tmp_path_factory):
    root = tmp_path_factory.mktemp("showcase")
    blend, spec = root / "showcase.blend", root / "shot_spec.json"
    bb.run_script("build_showcase_scene.py", ["--out", blend, "--spec", spec], timeout=1800)
    bb.run_script("oc_export.py", ["--out", root / "export", "--shot-id", "showcase_v1"], blend=blend)
    return {"root": root, "spec": json.loads(spec.read_text(encoding="utf-8")), "bundle": load_bundle(root / "export")}


def test_continuous_body_is_fully_skinned(sc):
    st = sc["spec"]["characters"]["skinning"]["sc_asura"]
    assert st["vertices"] > 20000 and st["unweighted"] == 0 and st["max_sum_error"] < 1e-3
    assert {"pelvis", "chest", "upper_arm.L", "forearm.L", "upper_arm.R", "forearm.R", "mace"} <= set(st["groups"])


def test_contracts_rig_and_objects(sc):
    spec, m = sc["spec"], sc["bundle"].manifest
    CameraMotion.model_validate(json.loads((sc["root"] / "camera_motion.json").read_text(encoding="utf-8")))
    ActionTimeline.model_validate(spec["choreography"]["action_timeline"])
    layers = CompositeManifest.model_validate(spec["layers"])
    assert layers.layers[0].ghost_mode == "under_layer" and layers.layers[0].protection.include_frames == list(range(49))
    assert layers.layers[2].render.light_only == ["fx_flash_light"] and layers.layers[2].blend == "add"
    (arm,) = m.armatures
    assert arm.oc_id == "sc_asura_rig"
    passes = {o.oc_id: o.pass_index for o in m.objects}
    assert (passes["sc_asura"], passes["sc_defender"], passes["sc_mace_head"], passes["sc_mace_shaft"]) == (1, 2, 8, 9)
    assert m.camera.intrinsics.resolution_x == 768 and m.camera.intrinsics.resolution_y == 448


def test_strike_timing_static_defender_and_camera(sc):
    b, spec = sc["bundle"], sc["spec"]
    bones = list(b.manifest.armatures[0].bones)
    j = b.joints()
    heads, tails = j["sc_asura_rig.heads"], j["sc_asura_rig.tails"]
    for name in ["root", "pelvis", "thigh.L", "shin.R"]:
        assert np.abs(heads[:, bones.index(name)] - heads[0, bones.index(name)]).max() < 1e-6
    z = tails[:, bones.index("mace"), 2]
    apex = int(np.argmax(z))
    assert apex == 23 and int(np.argmax(z[apex:] <= z[apex:].min() + 1e-3)) + apex == 29
    assert cd.timeline_frames(spec["choreography"]["action_timeline"], Fraction(24), "windup", "strike") == \
        {"apex": 23, "contact": 29}
    obj = b.objects()["sc_defender"]
    assert np.abs(obj - obj[0]).max() < 1e-9
    with np.load(sc["root"] / "camera_motion.npz", allow_pickle=False) as zf:
        authored = {k: zf[k] for k in zf.files if k != "meta_json"}
    res = cd.camera_contract(b.camera_arrays(), authored, Fraction(24), {})
    assert res["passed"] and res["lens_fixed"] and res["max_position_err_m"] < 1e-5
