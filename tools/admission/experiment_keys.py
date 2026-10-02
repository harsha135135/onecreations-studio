"""Cache keys (src/onecreations/cachekeys.py) for one controlled generation run, from its recorded inputs.

    experiment_keys.py --spec shot_spec.json --bundle <export dir> --control-sidecar depth_control.json \
        --workflow workflows/ltx25/m2a_temple_api.json --first-frame first_frame.png --seed 1000 \
        --models ltx25_22b_distilled,ltx_union_ic_lora --out admission_records/<label>_keys.json

Maps a run onto the existing artifact graph instead of a parallel scheme:
- control_render <- scene (spec "scene"), camera (export camera-samples digest), choreography (spec "choreography"),
  timewarp (identity unless the export used one), control_export_settings (export/pass settings + control convention)
- generation <- control_render, references (first-frame sha256), backend_profile (registry model sha256s),
  prompt (all CLIPTextEncode texts), seed, generation_settings (the workflow with prompts and seed blanked)
Changing the prompt re-keys only `generation`; changing the camera or choreography re-keys both.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

from onecreations.cachekeys import artifact_key
from onecreations.hashing import content_hash

PROMPT_NODE, SEED_NODE = "CLIPTextEncode", "RandomNoise"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def split_workflow(workflow: dict) -> tuple[list[str], dict]:
    """(prompt texts in node order, workflow with prompts/seed blanked) from an API-format graph."""
    blank = copy.deepcopy(workflow)
    prompts = []
    for node_id in sorted(blank, key=str):
        node = blank[node_id]
        node.pop("_meta", None)
        if node.get("class_type") == PROMPT_NODE:
            prompts.append(node["inputs"].get("text", ""))
            node["inputs"]["text"] = "<prompt>"
        elif node.get("class_type") == SEED_NODE:
            node["inputs"]["noise_seed"] = "<seed>"
    return prompts, blank


def keys_from_inputs(*, scene: dict, choreography: dict, camera_digest: str, timewarp, export_settings: dict,
                     control_meta: dict, workflow: dict, first_frame_sha256: str, model_hashes: dict, seed: int) -> dict:
    prompts, settings = split_workflow(workflow)
    control_settings = {"export": export_settings,
                        "control": {k: control_meta.get(k) for k in ("convention", "lo_pct", "hi_pct", "fps")}}
    inputs_control = {"scene": content_hash(scene), "camera": camera_digest, "choreography": content_hash(choreography),
                      "timewarp": timewarp, "control_export_settings": content_hash(control_settings)}
    control_key = artifact_key("control_render", inputs_control)
    inputs_gen = {"control_render": control_key, "references": {"first_frame": first_frame_sha256},
                  "backend_profile": content_hash(model_hashes), "prompt": prompts, "seed": int(seed),
                  "generation_settings": content_hash(settings)}
    return {"control_render": control_key, "generation": artifact_key("generation", inputs_gen),
            "inputs": {"control_render": inputs_control,
                       "generation": dict(inputs_gen, prompt=prompts)}, "provenance": "computed"}


def registry_hashes(registry: Path, model_ids: list[str]) -> dict:
    import yaml

    reg = yaml.safe_load(Path(registry).read_text(encoding="utf-8"))
    by_id = {m["id"]: m for m in reg["models"]}
    return {mid: sorted(f["sha256"] for f in by_id[mid].get("files", [])) for mid in model_ids}


def main(argv: list[str] | None = None) -> int:
    from onecreations.blender_bundle import load_bundle

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--control-sidecar", type=Path, required=True)
    p.add_argument("--workflow", type=Path, required=True)
    p.add_argument("--first-frame", type=Path, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--models", default="ltx25_22b_distilled,ltx_union_ic_lora")
    p.add_argument("--registry", type=Path, default=Path("model_registry/models.yaml"))
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)

    spec = json.loads(a.spec.read_text(encoding="utf-8"))
    bundle = load_bundle(a.bundle)
    raw = bundle.raw
    passes = raw.get("passes") or {}
    export_settings = {
        "exporter_version": raw.get("exporter_version"), "conventions": raw.get("conventions"),
        "probes": bool(raw.get("probes_file")),
        "passes": {k: passes.get(k) for k in ("engine", "samples", "filter_width", "width", "height",
                                              "background_depth", "normal_space")},
        "shot": {k: (raw.get("shot") or {}).get(k) for k in ("duration", "frame_count", "output_fps")},
    }
    timewarp = (raw.get("shot") or {}).get("timewarp_keys") or "identity"
    keys = keys_from_inputs(scene=spec.get("scene", {}), choreography=spec.get("choreography", {}),
                            camera_digest=bundle.manifest.camera.samples.digest, timewarp=timewarp,
                            export_settings=export_settings,
                            control_meta=json.loads(a.control_sidecar.read_text(encoding="utf-8")),
                            workflow=json.loads(a.workflow.read_text(encoding="utf-8")),
                            first_frame_sha256=_sha256(a.first_frame),
                            model_hashes=registry_hashes(a.registry, [m for m in a.models.split(",") if m]),
                            seed=a.seed)
    keys["sources"] = {"spec": str(a.spec), "bundle": str(a.bundle), "bundle_content_sha256": bundle.manifest.content_sha256,
                       "workflow": str(a.workflow), "workflow_sha256": _sha256(a.workflow),
                       "first_frame_sha256": keys["inputs"]["generation"]["references"]["first_frame"]}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(keys, indent=2), encoding="utf-8")
    print(json.dumps({"control_render": keys["control_render"], "generation": keys["generation"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
