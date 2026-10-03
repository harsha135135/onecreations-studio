"""Build the M3-B shot: the M3-A shot with finished, continuous characters (first-frame appearance upgrade).

    blender -b --factory-startup --python build_m3b_scene.py -- --out m3b.blend --spec shot_spec.json

Everything but the two characters is the M3-A scene, built by build_temple_action_scene.build(variant=...): the
temple and its finished look, banners, rig m3a_asura_rig with the M2-B keys and root, ActionTimeline m3a_mace_slam_v1,
CameraMotion m3a_orbit_push_in_v1, the M3-A mace, the impact_dust effect, the object ids and pass indices. The
characters come from oc_m3b_characters (continuous anatomy, layered costume, inside the M3-A silhouettes).
--spec writes the M3-A spec with: shot m3b_action, the characters' skinning sanity, the composite manifest with the
pre-registered hybrid v2 ghost rule (fill_under_layer), and the M3-B pre-registration (silhouette gate, occlusion
case, classification) embedded verbatim with its SHA-256.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_temple_action_scene as action  # noqa: E402
import oc_blender_common as common  # noqa: E402
import oc_m3b_characters as m3b  # noqa: E402
from onecreations import hashing  # noqa: E402

SHOT = "m3b_action"
PREREG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "admission_records",
                      "2026-10-03_ltx25-m3b-character_preregistration.json")


def composite_manifest(spec_layers: dict) -> dict:
    """The M3-A manifest with the pre-registered hybrid v2 ghost rule on the protected mace layer."""
    out = json.loads(json.dumps(spec_layers))
    out.update(id="m3b_layers_v2", shot=SHOT)
    mace = next(ly for ly in out["layers"] if ly["id"] == "mace_protect")
    mace.update(ghost_suppression=True, ghost_mode="fill_under_layer", ghost_colors=["ember"])
    return out


def spec_hook(spec: dict) -> dict:
    prereg_path = os.path.normpath(PREREG)
    with open(prereg_path, encoding="utf-8") as fh:
        prereg = json.load(fh)
    spec.update(shot=SHOT, purpose=(
        "M3-B: the M3-A shot (same temple and look, rig, keys, ActionTimeline, camera move, mace, effect, ids and "
        "LTX configuration) with finished continuous characters for the first frame, and the pre-registered hybrid "
        "v2 ghost rule"))
    spec["scene"]["characters"] = {
        "builder": "oc_m3b_characters (continuous metaball anatomy, swept tubes, armour shells, cloth panels)",
        "skinning": m3b.SKINNING, "unchanged": ["m3a_mace_head", "m3a_mace_shaft", "rig", "keys", "placement"]}
    spec["layers"] = composite_manifest(spec["layers"])
    spec["tracking"]["notes"] += ("; M3-B: same tracking as M3-A (same ids, colour rules and tolerances); colour rules "
                                  "are re-validated on the M3-B finished reference before the run (pre-registration "
                                  "gate 9)")
    spec["classification"] = dict(prereg["classification"], hybrid_usable=prereg["hybrid_v2"]["usable"],
                                  retry=prereg["generation_budget_and_retry"])
    spec["m3b"] = {"preregistration": "admission_records/" + os.path.basename(prereg_path),
                   "preregistration_sha256": hashing.file_sha256(prereg_path),
                   "baseline_shot": "m3a_action", "silhouette_gate": prereg["silhouette_gate"],
                   "occlusion_case": prereg["occlusion_case"], "pre_generation_gates": prereg["pre_generation_gates"]}
    return spec


def main() -> None:
    p = argparse.ArgumentParser(prog="build_m3b_scene")
    p.add_argument("--out", required=True)
    p.add_argument("--spec", default=None)
    a = p.parse_args(common.script_args())
    action.build(a.out, a.spec, variant=SimpleNamespace(shot="M3-B", build_asura=m3b.build_asura,
                                                        build_defender=m3b.build_defender, spec_hook=spec_hook))


if __name__ == "__main__":
    main()
