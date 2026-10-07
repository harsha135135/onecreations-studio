"""Headless-Blender D1 test: the compiled Showcase v1 ShotSpec builds the same scene as the hand-configured builder,
and a changed strike timing moves CONTACT identically in the compiler and in Blender. Skipped without Blender."""

import copy
import json
from pathlib import Path

import pytest

from onecreations import blender_bridge as bb
from onecreations.contracts import ActionTimeline, CompositeManifest, ShotSpec
from onecreations.director.compiler import compile_shot
from onecreations.director.registry import load_registry

pytestmark = pytest.mark.blender

if bb.find_blender() is None:
    pytest.skip("Blender not installed", allow_module_level=True)

SPEC = Path(__file__).resolve().parents[1] / "examples" / "director" / "showcase_v1.shotspec.json"


def _build(root: Path, compiled=None) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    args = ["--out", root / "s.blend", "--spec", root / "shot_spec.json"]
    if compiled is not None:
        (root / "scene_build.json").write_text(json.dumps(compiled.scene_build), encoding="utf-8")
        args += ["--config", root / "scene_build.json"]
    bb.run_script("build_showcase_scene.py", args, timeout=1800)
    return json.loads((root / "shot_spec.json").read_text(encoding="utf-8"))


def test_compiled_showcase_builds_the_hand_configured_scene(tmp_path):
    reg = load_registry()
    compiled = compile_shot(ShotSpec.model_validate(json.loads(SPEC.read_text())), reg)
    manual = _build(tmp_path / "manual")
    auto = _build(tmp_path / "compiled", compiled)
    # every built field identical; the layer manifest equal as a validated contract (the compiled one spells out
    # the defaults the hand-written dict leaves implicit)
    assert {k: v for k, v in auto.items() if k != "layers"} == {k: v for k, v in manual.items() if k != "layers"}
    assert CompositeManifest.model_validate(auto["layers"]) == CompositeManifest.model_validate(manual["layers"])
    assert ActionTimeline.model_validate(auto["choreography"]["action_timeline"]) == compiled.action_timeline


def test_contact_propagates_through_compiler_and_engine(tmp_path):
    reg = load_registry()
    d = json.loads(SPEC.read_text())
    d = copy.deepcopy(d)
    d["id"] = "d1_slow_strike"
    d["actions"][0]["params"] = {"strike_frames": 8}
    d["events"] = [e for e in d["events"] if e["preset"] in ("impact_dust_v1", "debris_v1")]
    compiled = compile_shot(ShotSpec.model_validate(d), reg)
    built = _build(tmp_path / "slow", compiled)
    contact = next(e.frame for e in compiled.events if e.name == "strike.CONTACT")
    assert contact == 31 == built["choreography"]["impact_output_frame"]
    assert built["choreography"]["sc_asura"]["events_blender_frame"] == {"apex": 24, "contact": 32}
    assert ActionTimeline.model_validate(built["choreography"]["action_timeline"]) == compiled.action_timeline
    assert CompositeManifest.model_validate(built["layers"]) == compiled.layers
    assert [ly.id for ly in compiled.layers.layers] == ["mace_protect", "impact_fx"] and built["shot"] == "d1_slow_strike"


def test_named_defender_role_builds_and_matches_the_engine(tmp_path):
    """A prompt that names the defender (role "shiva", not "defender") must build a timeline the contract accepts and
    the compiler agrees with (D3 Phase 0: the engine used to hard-code the role "defender")."""
    from onecreations.director.interpreter import interpret
    from onecreations.director.planner import plan_to_spec
    reg = load_registry()
    plan = interpret("Lord Shiva stands inside an ancient ruined temple at dusk. A massive horned Asura attacks him "
                     "with a mace. Use a low orbit and push-in.", reg)
    compiled = compile_shot(plan_to_spec(plan, reg, "d3_named_defender"), reg)
    assert compiled.action_timeline.actors == {"asura": "sc_asura", "shiva": "sc_defender"}
    built = _build(tmp_path / "named", compiled)
    assert ActionTimeline.model_validate(built["choreography"]["action_timeline"]) == compiled.action_timeline


PARRY = ("Create a cinematic shot of a horned Asura attacking an ascetic defender with a heavy mace in an ancient "
         "ruined temple at dusk. The defender parries the blow with a trident. Use a low orbit and push-in.")


@pytest.mark.parametrize("strike_frames", [6, 9])
def test_parry_builds_with_an_exact_contact(tmp_path, strike_frames):
    """D3: the compiled parry builds the same timeline, contact interval and layers as the compiler, and the solved
    contact holds at both strike speeds: the mace head touches the shaft on CONTACT, was clear 4 frames earlier, and
    nothing interpenetrates (vertex distances)."""
    from onecreations.director.interpreter import interpret
    from onecreations.director.planner import plan_to_spec
    reg = load_registry()
    d = plan_to_spec(interpret(PARRY, reg), reg, f"d3_parry_{strike_frames}").model_dump(mode="json")
    for a in d["actions"]:
        a["params"] = {"strike_frames": strike_frames}
    compiled = compile_shot(ShotSpec.model_validate(d), reg)
    built = _build(tmp_path / "parry", compiled)
    assert ActionTimeline.model_validate(built["choreography"]["action_timeline"]) == compiled.action_timeline
    assert CompositeManifest.model_validate(built["layers"]) == compiled.layers
    contact = built["choreography"]["contact"]
    f0 = contact["frame_output"]
    assert f0 == next(e.frame for e in compiled.events if e.name == "strike.CONTACT") == 23 + strike_frames
    gap = contact["series"]["head_to_shaft_m"]
    assert abs(gap[f0]) <= 0.01 and gap[f0 - 4] >= 0.3 and min(gap) >= -0.005
    assert min(contact["series"]["trident_to_attacker_m"]) >= 0.1 and min(contact["series"]["head_to_defender_m"]) >= 0.1
    skin = built["characters"]["skinning"]["sc_defender"]
    assert skin["unweighted"] == 0 and skin["max_sum_error"] < 1e-3
    assert len(built["tracking"]["visibility"]["sc_mace_head"]) == 49
    assert built["choreography"]["sc_defender"]["rig"] == "sc_defender_rig"


def test_rigged_defender_holds_the_v1_guard(tmp_path):
    """ascetic_defender_v2 with the static guard: one key, the same placement, the trident as its own object."""
    root = tmp_path / "v2guard"
    root.mkdir()
    (root / "cfg.json").write_text(json.dumps({"attacker_asset": "asura_v2", "defender_asset": "ascetic_defender_v2"}))
    bb.run_script("build_showcase_scene.py", ["--out", root / "s.blend", "--spec", root / "shot_spec.json",
                                              "--config", root / "cfg.json"], timeout=1800)
    built = json.loads((root / "shot_spec.json").read_text(encoding="utf-8"))
    d = built["choreography"]["sc_defender"]
    assert d["motion"] == "rigged, held guard" and d["events_blender_frame"] == {}
    assert [p["id"] for p in built["choreography"]["action_timeline"]["phases"]][-1] == "defender_hold"
    assert "contact" not in built["choreography"] and built["choreography"]["action_timeline"]["contacts"] == []
