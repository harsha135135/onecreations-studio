"""Content-derived cache keys with an explicit dependency graph (v1 §29).

A cached depth sequence rendered from an old camera is a correctness bug. Each artifact's key is the sha256 of its
declared inputs; upstream artifacts contribute their own keys, so a change propagates exactly to its dependants.

Base inputs are content hashes (or any canonicalizable value) of: scene, camera, choreography, timewarp, lighting,
event, references, backend_profile, prompt, seed, and the export/render/generation/composite settings.
"""

from __future__ import annotations

from typing import Any, Mapping

from onecreations.hashing import content_hash

ARTIFACT_INPUTS: dict[str, tuple[str, ...]] = {
    "control_render": ("scene", "camera", "choreography", "timewarp", "control_export_settings"),
    "vfx_cache": ("scene", "choreography", "timewarp", "events"),
    "audio_placement": ("events", "timewarp", "audio_assets"),
    "beauty_render": ("scene", "camera", "choreography", "timewarp", "lighting", "vfx_cache", "render_settings"),
    "generation": ("control_render", "references", "backend_profile", "prompt", "seed", "generation_settings"),
    "composite": ("beauty_render", "generation", "masks", "composite_recipe"),
}

KEY_VERSION = 1


def _order() -> list[str]:
    done: list[str] = []
    pending = dict(ARTIFACT_INPUTS)
    while pending:
        ready = [a for a, deps in pending.items() if all(d not in ARTIFACT_INPUTS or d in done for d in deps)]
        if not ready:
            raise ValueError("cycle in ARTIFACT_INPUTS")
        for a in sorted(ready):
            done.append(a)
            pending.pop(a)
    return done


BASE_INPUTS = tuple(sorted({d for deps in ARTIFACT_INPUTS.values() for d in deps} - set(ARTIFACT_INPUTS)))


def artifact_key(artifact: str, inputs: Mapping[str, Any]) -> str:
    """Key for one artifact; `inputs` must contain exactly its declared inputs."""
    declared = ARTIFACT_INPUTS[artifact]
    missing = [d for d in declared if d not in inputs]
    extra = [k for k in inputs if k not in declared]
    if missing or extra:
        raise KeyError(f"{artifact}: missing {missing}, unexpected {extra}")
    return content_hash({"artifact": artifact, "key_version": KEY_VERSION, "inputs": {d: inputs[d] for d in declared}})


def compute_keys(base: Mapping[str, Any]) -> dict[str, str]:
    """All artifact keys from base inputs (see BASE_INPUTS)."""
    missing = [b for b in BASE_INPUTS if b not in base]
    if missing:
        raise KeyError(f"missing base inputs: {missing}")
    values: dict[str, Any] = dict(base)
    keys: dict[str, str] = {}
    for artifact in _order():
        keys[artifact] = artifact_key(artifact, {d: values[d] for d in ARTIFACT_INPUTS[artifact]})
        values[artifact] = keys[artifact]
    return keys


def invalidated_by(changed_input: str) -> list[str]:
    """Artifacts whose keys change when `changed_input` changes (transitively)."""
    hit: set[str] = set()
    frontier = {changed_input}
    while frontier:
        nxt = {a for a, deps in ARTIFACT_INPUTS.items() if frontier & set(deps)} - hit
        hit |= nxt
        frontier = nxt
    return sorted(hit)
