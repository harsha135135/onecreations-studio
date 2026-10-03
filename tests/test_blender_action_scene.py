"""Headless-Blender test of the M3-A action scene: the finished look keeps the control contracts. The rig and weapon
export, CameraMotion / ActionTimeline / CompositeManifest validate, the volume-only haze box is kept out of the
geometric passes (recorded in the manifest, no speckle), and the authored protected interval comes from the exported
ground truth. Skipped when Blender is not installed."""

import json
from fractions import Fraction

import pytest

from onecreations import blender_bridge as bb
from onecreations.blender_bundle import load_bundle
from onecreations.contracts import ActionTimeline, CameraMotion, CompositeManifest
from tools.admission import control_diagnostic as cd
from tools.admission import hybrid_composite as hc

pytestmark = pytest.mark.blender

if bb.find_blender() is None:
    pytest.skip("Blender not installed", allow_module_level=True)


@pytest.fixture(scope="module")
def m3a(tmp_path_factory):
    root = tmp_path_factory.mktemp("m3a")
    blend, spec = root / "m3a_action.blend", root / "shot_spec.json"
    bb.run_script("build_temple_action_scene.py", ["--out", blend, "--spec", spec])
    bb.run_script("oc_export.py", ["--out", root / "export", "--passes", "--shot-id", "m3a_action"], blend=blend)
    return {"root": root, "spec": json.loads(spec.read_text(encoding="utf-8")), "bundle": load_bundle(root / "export")}


def test_contracts_validate(m3a):
    root, spec = m3a["root"], m3a["spec"]
    CameraMotion.model_validate(json.loads((root / "camera_motion.json").read_text(encoding="utf-8")))
    tl = ActionTimeline.model_validate(spec["choreography"]["action_timeline"])
    assert tl.id == "m3a_mace_slam_v1" and set(tl.actors) == {"asura", "defender"}
    assert [p.id for p in tl.phases] == ["guard", "windup", "strike", "impact", "recovery", "defender_hold"]
    assert cd.timeline_frames(spec["choreography"]["action_timeline"], Fraction(24), "windup", "strike") == \
        {"apex": 23, "contact": 29}
    layers = CompositeManifest.model_validate(spec["layers"])
    assert [ly.id for ly in layers.layers] == ["mace_protect", "impact_dust"]
    assert hc.trigger_frame(spec["choreography"]["action_timeline"], "impact", "start", Fraction(24)) == \
        spec["choreography"]["impact_output_frame"] == 29


def test_rig_weapon_and_tracking_colours(m3a):
    m, spec = m3a["bundle"].manifest, m3a["spec"]
    (arm,) = m.armatures
    assert arm.oc_id == "m3a_asura_rig" and {"root", "mace", "hand.L"} <= set(arm.bones)
    objects = {o.oc_id: o.pass_index for o in m.objects}
    assert objects["m3a_asura"] == 1 and objects["m3a_defender"] == 2
    assert objects["m3a_mace_head"] == 8 and objects["m3a_mace_shaft"] == 9
    assert {objects[k] for k in ("m3a_lm_near", "m3a_lm_mid", "m3a_lm_far")} == {10, 11, 12}
    colours = {k: v["color"] for k, v in spec["tracking"]["subjects"].items()}
    assert colours["m3a_asura"] == "crimson" and colours["m3a_mace_head"] == "gold_deep"
    assert colours["m3a_lm_far"] == "teal"
    assert spec["tracking"]["parallax"]["layers"] == ["m3a_lm_near", "m3a_lm_far"]


def test_haze_box_is_kept_out_of_the_passes(m3a):
    b = m3a["bundle"]
    assert b.manifest.passes.excluded_volume_objects == ["lk_haze"]
    assert "lk_haze" not in b.manifest.passes.object_index_map
    idx = b.passes()["object_index"]
    background = idx == 0
    inner = background[:, 1:-1, 1:-1]
    isolated = inner & ~background[:, :-2, 1:-1] & ~background[:, 2:, 1:-1] & ~background[:, 1:-1, :-2] \
        & ~background[:, 1:-1, 2:]
    assert int(isolated.sum()) == 0                      # a volume in the passes would scatter index-0 speckle


def test_protected_interval_from_ground_truth(m3a):
    b, spec = m3a["bundle"], m3a["spec"]
    rule = CompositeManifest.model_validate(spec["layers"]).layers[0].protection
    idx = b.passes()["object_index"]
    stats = [cd.mask_stats(f == b.manifest.passes.object_index_map[rule.track_object]) for f in idx]
    assert all(stats)                                     # the mace head is visible in every frame
    cents, widths = [(s["cx"], s["cy"]) for s in stats], [s["w_px"] for s in stats]
    assert hc.authored_fast_frames(cents, widths, rule.authored_speed_widths, rule.dilate_frames) == \
        list(range(23, 30))
