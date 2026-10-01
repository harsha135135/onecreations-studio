import copy

import pytest

from onecreations.shotpkg import event_schedule, has_errors, load_project, validate_shot

EX = "examples/diagnostic"


@pytest.fixture(scope="module")
def project():
    ctx, shots, issues = load_project(EX)
    assert issues == []
    return ctx, shots["temple_parry_004"]


def codes(issues, severity="error"):
    return {i.code for i in issues if i.severity == severity}


def mutate(shot, **changes):
    data = shot.model_dump()
    for k, v in changes.items():
        if "." in k:
            a, b = k.split(".")
            data[a][b] = v
        else:
            data[k] = v
    return type(shot).model_validate(data)


def test_good_shot_has_only_expected_warnings(project):
    ctx, shot = project
    issues = validate_shot(shot, ctx)
    assert not has_errors(issues)
    assert codes(issues, "warning") == {"SHOT_BACKEND_FRAMES", "SHOT_BACKEND_NOT_ADMITTED"}


def test_event_schedule_keeps_subframe_timing(project):
    ctx, shot = project
    sched = {e["event"]: e for e in event_schedule(shot, ctx)}
    assert sched["parry_001"]["output_time"] == "9/4" and sched["parry_001"]["frame_position"] == "54"
    # 2.0 s source after the hold lands between frames: exactly 909/7 = 129.857...
    assert sched["wall_impact_002"]["frame_position"] == "909/7"
    assert sched["wall_impact_002"]["nearest_frame"] == 130


@pytest.mark.parametrize("changes,code", [
    ({"assets": ["hero_v4", "temple_v2", "sword_pair_v2", "ghost_v1"]}, "SHOT_UNKNOWN_ASSET"),
    ({"assets": ["hero_v4", "temple_v2", "sword_pair_v2"]}, "SHOT_ACTOR_ASSET_MISSING"),
    ({"scene_state_in": "nowhere"}, "SHOT_UNKNOWN_SCENE_STATE"),
    ({"camera": "missing_cam"}, "SHOT_UNKNOWN_CAMERA"),
    ({"choreography": "missing"}, "SHOT_UNKNOWN_CHOREOGRAPHY"),
    ({"timewarp": "missing"}, "SHOT_UNKNOWN_TIMEWARP"),
    ({"events": ["parry_001", "nope"]}, "SHOT_UNKNOWN_EVENT"),
    ({"duration_seconds": "61/24", "timewarp": None}, None),  # whole frames, identity map: fine
    ({"duration_seconds": "6.01"}, "SHOT_FRAME_COUNT_NOT_INTEGER"),
    ({"duration_seconds": 7}, "SHOT_TIMEWARP_DOMAIN"),
    ({"timewarp": None, "duration_seconds": 3}, "SHOT_CHOREO_COVERAGE"),
    ({"timewarp": None, "duration_seconds": "5/2", "source_start": 0}, "SHOT_CAMERA_COVERAGE"),
    ({"events": ["wall_impact_002"]}, "SHOT_CONTACT_EVENT_MISSING"),
    ({"timewarp": None, "duration_seconds": "1/2", "events": ["parry_001"]}, "SHOT_EVENT_OUTSIDE"),
    ({"generation.allowed_regions": ["atmosphere", "heroes"]}, "SHOT_REGION_CONFLICT"),
    ({"generation.allowed_regions": ["sky_box"]}, "SHOT_UNKNOWN_REGION"),
    ({"generation.controls": ["depth", "pose"]}, "SHOT_BACKEND_UNSUPPORTED_CONTROL"),
    ({"generation.reference_count": 3}, "SHOT_TOO_MANY_REFERENCES"),
    ({"generation.width": 650}, "SHOT_BACKEND_DIMENSIONS"),
    ({"generation.backend_profile": "nope"}, "SHOT_UNKNOWN_BACKEND"),
])
def test_each_issue_code(project, changes, code):
    ctx, shot = project
    issues = validate_shot(mutate(shot, **changes), ctx)
    if code is None:
        assert "SHOT_FRAME_COUNT_NOT_INTEGER" not in codes(issues)
    else:
        assert code in codes(issues), [i.code for i in issues]


def test_contact_event_mismatch(project):
    ctx, shot = project
    ctx2 = copy.deepcopy(ctx)
    ctx2.events["parry_001"] = ctx2.events["parry_001"].model_copy(update={"source_time_seconds": 1})
    assert "SHOT_CONTACT_EVENT_MISMATCH" in codes(validate_shot(shot, ctx2))


def test_missing_camera_samples_reported(tmp_path):
    import shutil
    dst = tmp_path / "p"
    shutil.copytree(EX, dst)
    (dst / "camera" / "temple_dive_to_parry_v1.csv").unlink()
    ctx, shots, issues = load_project(dst)
    assert [i.code for i in issues] == ["LOAD_CAMERA_SAMPLES"]
    assert "SHOT_CAMERA_UNLOADED" in codes(validate_shot(shots["temple_parry_004"], ctx), "warning")
