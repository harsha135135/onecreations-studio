"""Headless-Blender test of the M3-B scene (the M3-A shot with continuous characters): the bodies are fully skinned
on the unchanged rig, joints and camera are bit-for-bit M3-A's, the actors stay visible in every frame, and the spec
carries the pre-registered hybrid v2 rule and gate. The silhouette LIMITS are a pre-generation gate (measured on the
desktop with silhouette_compare.py), not asserted here. Skipped when Blender is not installed."""

import json
from fractions import Fraction

import pytest

from onecreations import blender_bridge as bb
from onecreations.blender_bundle import load_bundle
from onecreations.contracts import ActionTimeline, CompositeManifest
from tools.admission import control_diagnostic as cd
from tools.admission import silhouette_compare as sc

pytestmark = pytest.mark.blender

if bb.find_blender() is None:
    pytest.skip("Blender not installed", allow_module_level=True)


def _build(root, script, shot):
    blend, spec = root / f"{shot}.blend", root / "shot_spec.json"
    bb.run_script(script, ["--out", blend, "--spec", spec], timeout=1800)
    bb.run_script("oc_export.py", ["--out", root / "export", "--passes", "--shot-id", shot], blend=blend)
    return {"root": root, "spec": json.loads(spec.read_text(encoding="utf-8")), "bundle": load_bundle(root / "export")}


@pytest.fixture(scope="module")
def shots(tmp_path_factory):
    return {"m3a": _build(tmp_path_factory.mktemp("m3a"), "build_temple_action_scene.py", "m3a_action"),
            "m3b": _build(tmp_path_factory.mktemp("m3b"), "build_m3b_scene.py", "m3b_action")}


def test_continuous_bodies_are_fully_skinned(shots):
    st = shots["m3b"]["spec"]["scene"]["characters"]["skinning"]["m3a_asura"]
    assert st["vertices"] > 20000 and st["unweighted"] == 0 and st["max_sum_error"] < 1e-3
    assert {"pelvis", "chest", "upper_arm.L", "forearm.L", "upper_arm.R", "forearm.R", "mace"} <= set(st["groups"])


def test_spec_keeps_m3a_control_and_registers_hybrid_v2(shots):
    a, b = shots["m3a"]["spec"], shots["m3b"]["spec"]
    assert b["shot"] == "m3b_action"
    assert b["choreography"]["action_timeline"] == a["choreography"]["action_timeline"]
    assert b["choreography"]["camera_move"] == a["choreography"]["camera_move"]
    assert b["tracking"]["subjects"] == a["tracking"]["subjects"] and b["tracking"]["joints"] == a["tracking"]["joints"]
    ActionTimeline.model_validate(b["choreography"]["action_timeline"])
    layers = CompositeManifest.model_validate(b["layers"])
    mace = layers.layers[0]
    assert mace.ghost_mode == "fill_under_layer" and mace.ghost_colors == ["ember"]
    assert mace.protection == CompositeManifest.model_validate(a["layers"]).layers[0].protection
    assert cd.timeline_frames(b["choreography"]["action_timeline"], Fraction(24), "windup", "strike") == \
        {"apex": 23, "contact": 29}
    assert b["m3b"]["silhouette_gate"]["objects"]["m3a_asura"]["min_iou"] > 0


def test_joints_camera_identical_and_actors_visible(shots):
    ref, cand = shots["m3a"]["bundle"], shots["m3b"]["bundle"]
    j = sc.max_array_diff(ref.joints(), cand.joints())
    assert j["max_abs"] and max(j["max_abs"].values()) <= 1e-6 and not j["shape_mismatch"]
    assert sc.max_array_diff({"c": ref.camera_arrays()["c2w"]}, {"c": cand.camera_arrays()["c2w"]})["max_abs"]["c"] \
        <= 1e-6
    rmap, cmap = ref.manifest.passes.object_index_map, cand.manifest.passes.object_index_map
    assert {k: rmap[k] for k in ("m3a_asura", "m3a_defender", "m3a_mace_head", "m3a_mace_shaft")} == \
        {k: cmap[k] for k in ("m3a_asura", "m3a_defender", "m3a_mace_head", "m3a_mace_shaft")}
    idx = cand.passes()["object_index"]
    for oc_id in ("m3a_asura", "m3a_defender", "m3a_mace_head"):
        assert all((f == cmap[oc_id]).any() for f in idx), oc_id
