"""Headless-Blender test of the M2-B strike scene: the rig exports through joints.npz, the root never moves, and the
exported weapon motion matches the authored ActionTimeline. Skipped when Blender is not installed."""

import json
from fractions import Fraction

import numpy as np
import pytest

from onecreations import blender_bridge as bb
from onecreations.blender_bundle import load_bundle
from onecreations.contracts import ActionTimeline
from tools.admission import control_diagnostic as cd

pytestmark = pytest.mark.blender

if bb.find_blender() is None:
    pytest.skip("Blender not installed", allow_module_level=True)


@pytest.fixture(scope="module")
def strike(tmp_path_factory):
    root = tmp_path_factory.mktemp("m2b")
    blend, spec = root / "m2b_strike.blend", root / "shot_spec.json"
    bb.run_script("build_temple_strike_scene.py", ["--out", blend, "--spec", spec])
    bb.run_script("oc_export.py", ["--out", root / "export", "--shot-id", "m2b_strike"], blend=blend)
    return {"root": root, "spec": json.loads(spec.read_text(encoding="utf-8")), "bundle": load_bundle(root / "export")}


def test_timeline_validates_and_is_written_next_to_the_spec(strike):
    tl = strike["spec"]["choreography"]["action_timeline"]
    model = ActionTimeline.model_validate(tl)
    assert [p.id for p in model.phases] == ["guard", "windup", "strike", "impact", "recovery"]
    assert json.loads((strike["root"] / "action_timeline.json").read_text(encoding="utf-8")) == tl
    assert cd.timeline_frames(tl, Fraction(24), "windup", "strike") == {"apex": 23, "contact": 29}


def test_rig_and_weapon_objects_are_exported(strike):
    m = strike["bundle"].manifest
    (arm,) = m.armatures
    assert arm.oc_id == "m2b_asura_rig" and {"root", "mace", "upper_arm.L", "forearm.L", "hand.L"} <= set(arm.bones)
    objects = {o.oc_id: o for o in m.objects}
    assert objects["m2b_asura"].pass_index == 1 and objects["m2b_mace_head"].pass_index == 8
    assert objects["m2b_mace_shaft"].pass_index == 9 and "m2a_shiva" in objects
    assert strike["spec"]["tracking"]["subjects"]["m2b_mace_head"]["color"] == "gold"


def test_root_is_stationary_and_weapon_events_match_the_timeline(strike):
    b = strike["bundle"]
    bones = list(b.manifest.armatures[0].bones)
    j = b.joints()
    heads, tails = j["m2b_asura_rig.heads"], j["m2b_asura_rig.tails"]
    for name in ["root", "pelvis", "thigh.L", "thigh.R", "shin.L", "shin.R"]:
        assert np.abs(heads[:, bones.index(name)] - heads[0, bones.index(name)]).max() < 1e-6
    z = tails[:, bones.index("mace"), 2]
    apex = int(np.argmax(z))
    assert apex == 23 and z[apex] < 3.1                       # the apex stays inside the frame's top edge
    assert int(np.argmax(z[apex:] <= z[apex:].min() + 1e-3)) + apex == 29
    assert z[29] == pytest.approx(0.34, abs=1e-3)             # head radius: resting on the floor
    assert np.abs(z[29:35] - z[29]).max() < 1e-3              # impact hold
