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
