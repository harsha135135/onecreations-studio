from fractions import Fraction

import numpy as np
import pytest

from onecreations import cachekeys, hashing

BASE = {
    "scene": "scene-v1", "camera": "cam-v1", "choreography": "chor-v1", "timewarp": "tw-v1", "lighting": "light-v1",
    "events": ["parry_001@v1"], "audio_assets": "foley-v1", "references": ["ref-a"], "backend_profile": "be-v1",
    "prompt": "storm over the temple", "seed": 731, "control_export_settings": {"depth": "planar", "res": [640, 384]},
    "render_settings": {"engine": "CYCLES"}, "generation_settings": {"steps": 8}, "masks": "masks-v1",
    "composite_recipe": "comp-v1",
}


def test_camera_change_invalidates_exactly_its_dependants():
    a = cachekeys.compute_keys(BASE)
    b = cachekeys.compute_keys(dict(BASE, camera="cam-v2"))
    changed = sorted(k for k in a if a[k] != b[k])
    assert changed == ["beauty_render", "composite", "control_render", "generation"]
    assert changed == cachekeys.invalidated_by("camera")
    assert a["audio_placement"] == b["audio_placement"] and a["vfx_cache"] == b["vfx_cache"]


def test_event_change_reaches_vfx_audio_beauty_and_composite_but_not_controls():
    a = cachekeys.compute_keys(BASE)
    b = cachekeys.compute_keys(dict(BASE, events=["parry_001@v2"]))
    changed = sorted(k for k in a if a[k] != b[k])
    assert changed == ["audio_placement", "beauty_render", "composite", "vfx_cache"]


def test_keys_need_exact_inputs():
    with pytest.raises(KeyError):
        cachekeys.compute_keys({k: v for k, v in BASE.items() if k != "seed"})
    with pytest.raises(KeyError):
        cachekeys.artifact_key("audio_placement", {"events": 1, "timewarp": 2, "audio_assets": 3, "camera": 4})


def test_canonical_json_ignores_order_and_float_noise():
    a = {"b": 1, "a": [0.1 + 0.2, Fraction(9, 10), (1, 2)], "c": -0.0}
    b = {"c": 0.0, "a": [0.3, Fraction(9, 10), [1, 2]], "b": 1}
    assert hashing.canonical_json(a) == hashing.canonical_json(b)
    assert hashing.content_hash(a) == hashing.content_hash(b)
    assert hashing.content_hash({"x": 0.3}) != hashing.content_hash({"x": 0.3001})
    with pytest.raises(ValueError):
        hashing.canonical_json({"x": float("nan")})


def test_array_digest_is_content_based(tmp_path):
    arr = {"t": np.arange(5, dtype=np.float64), "m": np.eye(4)}
    d1 = hashing.array_digest(arr)
    np.savez_compressed(tmp_path / "a.npz", **arr)
    with np.load(tmp_path / "a.npz") as z:
        assert hashing.array_digest({k: z[k] for k in z.files}) == d1
    assert hashing.array_digest({"t": arr["t"].astype(np.float32), "m": arr["m"]}) != d1
    assert hashing.array_digest({"t": arr["t"].reshape(5, 1), "m": arr["m"]}) != d1
