"""Contracts accept the v1 document's own examples, existing repo records, and reject malformed input."""
import json
import sys
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from onecreations.contracts import (ActionTimeline, AdmissionRecord, CameraMotion, CharacterAsset, CompositeManifest,
                                    ExperimentRecord, Shot, TimeWarpModel, VFXEvent)
from onecreations.contracts.schema_export import stale_schemas

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "diagnostic"

V1_CAMERA = """
camera_motion:
  id: temple_dive_to_parry_v1
  units: meters
  coordinate_system: blender_z_up
  pose_convention: camera_to_world
  rotation_format: quaternion_wxyz
  trajectory: camera_samples.npz
  intrinsics: lens_and_sensor.json
  source_time_curve: timewarp.json
  target_bindings: [fighter_A.chest, blade_contact]
  constraints:
    minimum_clearance_m: 0.15
    preserve_roll: true
    max_angular_acceleration: artist_defined
  provenance: {source: authored, confidence: verified_in_scene}
"""

V1_EVENT = """
event:
  id: parry_001
  type: SwordCollision
  source_time_seconds: 0.90
  attachment: contact_solver.parry_001
  participants: [fighter_A.sword, fighter_B.sword]
  seed: 731
  effects:
    sparks: {preset: steel_parry, duration_seconds: 0.18}
    flash: {preset: blue_energy, light_scene: true}
    camera_impulse: {preset: short_impact, space: camera_local}
    audio: {asset: foley/parry_07, offset_seconds: 0.0}
  cache_key_inputs: [scene_version, choreography_version, timewarp_version]
"""

V1_SHOT = """
shot:
  id: temple_parry_004
  schema_version: 1
  scene_state_in: temple_after_charge_v3
  duration_seconds: 6
  output_fps: {num: 24, den: 1}
  assets: [hero_v4, asura_v3, temple_v2, sword_pair_v2]
  choreography: parry_counter_v5
  camera: temple_dive_to_parry_v1
  timewarp: impact_hold_v2
  lighting: storm_blue_v1
  references: [approved_start, approved_contact, approved_end]
  generation:
    backend_profile: ltx25_union_depth_admitted
    allowed_regions: [distant_environment, atmosphere]
    protected_regions: [heroes, hands, weapons, foreground_architecture]
  events: [parry_001, wall_impact_002]
  continuity_out: temple_broken_pillar_v4
  acceptance: action_benchmark_v1
"""


def test_v1_document_examples_validate():
    cam = CameraMotion.model_validate(yaml.safe_load(V1_CAMERA)["camera_motion"])
    assert cam.constraints.max_angular_acceleration == "artist_defined"
    ev = VFXEvent.model_validate(yaml.safe_load(V1_EVENT)["event"])
    assert str(ev.source_time_seconds) == "9/10"
    assert ev.effects["flash"].model_extra == {"light_scene": True}
    shot = Shot.model_validate(yaml.safe_load(V1_SHOT)["shot"])
    assert shot.duration_seconds == 6


def test_times_serialize_exactly():
    ev = VFXEvent.model_validate(yaml.safe_load(V1_EVENT)["event"])
    dumped = ev.model_dump(mode="json")
    assert dumped["source_time_seconds"] == "9/10"
    assert dumped["effects"]["sparks"]["duration_seconds"] == "9/50"
    assert VFXEvent.model_validate(dumped) == ev


@pytest.mark.parametrize("cls,path", [
    (CharacterAsset, "assets/hero_v4.character.json"),
    (CameraMotion, "camera/temple_dive_to_parry_v1.json"),
    (ActionTimeline, "action/parry_counter_v5.json"),
    (TimeWarpModel, "time/impact_hold_v2.json"),
    (Shot, "shots/temple_parry_004.json"),
])
def test_example_project_files_validate(cls, path):
    cls.model_validate(json.loads((EX / path).read_text()))


def test_experiment_cards_validate():
    cards = sorted((ROOT / "training").rglob("experiment-card*.yaml"))
    assert len(cards) == 3
    for card in cards:
        ExperimentRecord.model_validate(yaml.safe_load(card.read_text()))


def test_monitor_output_validates_as_admission_record(tmp_path):
    from tools.admission import monitor
    monitor.main(["--label", "contract", "--interval", "0.1", "--out-dir", str(tmp_path), "--meta", "frames=49",
                  "--", sys.executable, "-c", "pass"])
    rec = json.loads((tmp_path / "records.jsonl").read_text().splitlines()[0])
    AdmissionRecord.model_validate(rec)
    rec["outcome"] = "pass: rung 1 at 512x320x49"
    AdmissionRecord.model_validate(rec)
    rec["outcome"] = "great"
    with pytest.raises(ValidationError):
        AdmissionRecord.model_validate(rec)


def test_rejections():
    good = json.loads((EX / "action/parry_counter_v5.json").read_text())
    bad = dict(good, phases=good["phases"] + [{"id": "x", "kind": "strike", "actor": "fighter_C", "start": 0, "end": 1}])
    with pytest.raises(ValidationError, match="unknown actor role"):
        ActionTimeline.model_validate(bad)
    with pytest.raises(ValidationError, match="ends after"):
        ActionTimeline.model_validate(dict(good, duration="1/2"))
    with pytest.raises(ValidationError, match="Extra inputs"):
        Shot.model_validate(dict(yaml.safe_load(V1_SHOT)["shot"], prompt="make it epic"))
    with pytest.raises(ValidationError):
        VFXEvent.model_validate(dict(yaml.safe_load(V1_EVENT)["event"], source_time_seconds="-1/24"))
    hero = json.loads((EX / "assets/hero_v4.character.json").read_text())
    hero["weapon_sockets"][0]["bone"] = "DEF-missing"
    with pytest.raises(ValidationError, match="bone_map"):
        CharacterAsset.model_validate(hero)
    with pytest.raises(ValidationError, match="4x4"):
        hero["weapon_sockets"][0]["bone"] = "DEF-hand.R"
        hero["weapon_sockets"][0]["transform"] = [[1, 0, 0]]
        CharacterAsset.model_validate(hero)


def test_composite_manifest_m3a_record_and_rejections():
    spec = json.loads((ROOT / "admission_records/2026-10-03_ltx25-m3a-action_shot_spec.json").read_text())
    m = CompositeManifest.model_validate(spec["layers"])
    mace, dust = m.layers
    assert mace.protection.track_object == "m3a_mace_head" and mace.render.motion_blur_shutter == 0.5
    assert dust.trigger.timeline == "m3a_mace_slam_v1" and dust.trigger.phase == "impact" and dust.duration_frames == 14
    raw = spec["layers"]
    with pytest.raises(ValidationError, match="protection rule"):
        CompositeManifest.model_validate(dict(raw, layers=[dict(raw["layers"][0], protection=None)]))
    with pytest.raises(ValidationError, match="trigger and a duration"):
        CompositeManifest.model_validate(dict(raw, layers=[dict(raw["layers"][1], duration_frames=None)]))
    with pytest.raises(ValidationError, match="nothing to render"):
        CompositeManifest.model_validate(dict(raw, layers=[dict(raw["layers"][1], collections=[])]))
    with pytest.raises(ValidationError, match="duplicate layer ids"):
        CompositeManifest.model_validate(dict(raw, layers=[raw["layers"][0], raw["layers"][0]]))


def test_composite_manifest_showcase_fields():
    base = {"schema_version": 1, "id": "sc", "shot": "showcase", "layers": [
        {"id": "mace", "kind": "protected_geometry", "objects": ["head"], "ghost_suppression": True,
         "ghost_mode": "under_layer", "ghost_colors": ["ember"],
         "protection": {"track_object": "head", "include_frames": [0, 1, 2]}},
        {"id": "flash", "kind": "effect", "collections": ["fx_flash"], "blend": "add",
         "render": {"light_only": ["fx_flash_light"], "motion_blur_shutter": None},
         "trigger": {"timeline": "t", "phase": "impact"}, "duration_frames": 5}]}
    m = CompositeManifest.model_validate(base)
    assert m.layers[0].ghost_mode == "under_layer" and m.layers[0].protection.include_frames == [0, 1, 2]
    assert m.layers[1].render.light_only == ["fx_flash_light"] and m.layers[1].blend == "add"
    over = dict(base["layers"][1], blend="over")
    with pytest.raises(ValidationError, match="blend 'add'"):
        CompositeManifest.model_validate(dict(base, layers=[base["layers"][0], over]))
    with pytest.raises(ValidationError, match="composited 'over'"):
        CompositeManifest.model_validate(dict(base, layers=[dict(base["layers"][0], blend="add")]))
    assert CompositeManifest.model_validate(dict(base, layers=[{"id": "x", "kind": "protected_geometry", "objects": ["a"],
                                                                 "protection": {"track_object": "a"}}])
                                            ).layers[0].ghost_mode == "outside_core"     # M3-A v1 default


def test_composite_manifest_m3b_hybrid_v2_mode():
    spec = json.loads((ROOT / "admission_records/2026-10-03_ltx25-m3a-action_shot_spec.json").read_text())
    raw = spec["layers"]
    v2 = dict(raw["layers"][0], ghost_mode="fill_under_layer", ghost_colors=["ember"])
    m = CompositeManifest.model_validate(dict(raw, id="m3b_layers_v2", shot="m3b_action", layers=[v2, raw["layers"][1]]))
    assert m.layers[0].ghost_mode == "fill_under_layer" and m.layers[0].protection == \
        CompositeManifest.model_validate(raw).layers[0].protection          # protection rule unchanged from M3-A
    with pytest.raises(ValidationError):
        CompositeManifest.model_validate(dict(raw, layers=[dict(v2, ghost_mode="everything")]))


def test_committed_schemas_are_current():
    assert stale_schemas() == [], "run: uv run onecreations schemas export"
