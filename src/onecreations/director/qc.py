"""QC as data: the checks a compiled shot must pass, per stage, and the evaluator for the deterministic preflight.

D1 implements the PREFLIGHT checks (control inputs, before any generation). Post-generation and final checks are
declared with `implemented: false` so future automatic QC can plug in without changing the contract.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from onecreations.contracts.director import QCCheck


def checks_for(profile: str, ctx: dict) -> list[QCCheck]:
    if profile != "showcase_class_preflight_v1":
        raise ValueError(f"unknown QC profile {profile!r}")
    pre = [
        ("events_resolved", "events", {"required": ctx["required_events"]}, "D1 event graph"),
        ("timeline_matches_engine", "timeline", {}, "D1: compiler and Blender builder compute the same timeline"),
        ("weapon_bone_projection", "joints", {"rig": ctx["rig"], "bone": "mace", "object": ctx["weapon_track"],
                                              "max_px": 4.5}, "M2-B joint cross-check; Showcase 2.1 px"),
        ("stationary_root", "joints", {"rig": ctx["rig"], "bones": ["root", "pelvis", "thigh.L", "thigh.R",
                                                                     "shin.L", "shin.R"], "max_m": 0.001},
         "M2-B: root and legs never keyed"),
        ("camera_contract", "camera", {"max_position_err_m": 0.001, "max_angle_err_deg": 0.05},
         "M2-C camera contract"),
        ("camera_clearance", "clearance", {"min_m": 1.0}, "M2-C clearance rule"),
        ("actors_in_frame", "framing", {"objects": ctx["actors"], "min_px": 400}, "M2/M3 gate: subjects in frame"),
        ("weapon_visible", "framing", {"objects": [ctx["weapon_track"]], "min_px": 200}, "M2-B gate"),
        ("depth_valid", "passes", {"max_isolated_background_px": 200}, "M3-A / Showcase pass cleanliness"),
        ("first_frame_aligned", "first_frame", {"resolution": ctx["resolution"]},
         "first frame rendered from the same scene, camera and frame as the passes (exact by construction)"),
    ]
    post = [
        ("weapon_attachment", "post_generation", {"max_grip_px": 12}, "M3-A hybrid criterion"),
        ("contact_timing", "post_generation", {"event": "CONTACT", "tol_frames": 2}, "M2-B timing check"),
        ("appearance_persistence", "post_generation", {}, "M3-A appearance axis (visual today)"),
        ("protected_layer_integrity", "post_generation", {"no_double_image": True}, "M3-A / Showcase review"),
    ]
    final = [("deliverable_format", "final", {"resolution": ctx["resolution"], "fps": ctx["fps"]}, "delivery")]
    out = [QCCheck(id=i, stage="preflight", kind=k, params=p, implemented=True, provenance=s) for i, k, p, s in pre]
    out += [QCCheck(id=i, stage="post_generation", kind=k, params=p, implemented=False, provenance=s)
            for i, k, p, s in post]
    out += [QCCheck(id=i, stage="final", kind=k, params=p, implemented=False, provenance=s) for i, k, p, s in final]
    return out


def evaluate_preflight(compiled, out_dir: Path, built_spec: dict) -> dict:
    """Run the implemented preflight checks on a built scene (export bundle, controls, first frame)."""
    from onecreations.blender_bundle import load_bundle
    from onecreations.director import camera as cam
    from onecreations.geometry.intrinsics import project

    b = load_bundle(out_dir / "export")
    idx, depth = b.passes()["object_index"], b.passes()["depth_m"]
    om = b.manifest.passes.object_index_map
    results = {}
    for chk in compiled.qc:
        if chk.stage != "preflight":
            continue
        p = chk.params
        r: dict = {}
        if chk.id == "events_resolved":
            names = {e.name.split(".")[1] for e in compiled.events}
            r = {"passed": set(p["required"]) <= names, "events": {e.name: e.frame for e in compiled.events}}
        elif chk.id == "timeline_matches_engine":
            from onecreations.contracts.action import ActionTimeline

            r = {"passed": ActionTimeline.model_validate(built_spec["choreography"]["action_timeline"])
                 == compiled.action_timeline}
        elif chk.kind == "joints" and chk.id == "weapon_bone_projection":
            arm = next(a for a in b.manifest.armatures if a.oc_id == p["rig"])
            tails = b.joints()[f"{p['rig']}.tails"][:, list(arm.bones).index(p["bone"])]
            cam_arr = b.camera_arrays()
            errs = []
            for f in range(len(tails)):
                ys, xs = np.nonzero(idx[f] == om[p["object"]])
                uv, _ = project(tails[f][None], cam_arr["c2w"][f], b.K())
                errs.append(math.dist((xs.mean() + 0.5, ys.mean() + 0.5), (uv[0, 0], uv[0, 1])))
            r = {"passed": max(errs) <= p["max_px"], "max_px": round(max(errs), 2)}
        elif chk.id == "stationary_root":
            arm = next(a for a in b.manifest.armatures if a.oc_id == p["rig"])
            heads = b.joints()[f"{p['rig']}.heads"]
            move = max(float(np.abs(heads[:, list(arm.bones).index(n)] - heads[0, list(arm.bones).index(n)]).max())
                       for n in p["bones"])
            r = {"passed": move <= p["max_m"], "max_move_m": move}
        elif chk.id == "camera_contract":
            want = cam.samples(compiled.camera_move, compiled.frames, compiled.fps)
            got = b.camera_arrays()
            pos = float(np.abs(got["position"] - want.position).max())
            dots = np.abs(np.sum(got["quaternion_wxyz"] * want.quaternion, axis=1)).clip(0, 1)
            ang = float(np.degrees(2 * np.arccos(dots)).max())
            r = {"passed": pos <= p["max_position_err_m"] and ang <= p["max_angle_err_deg"],
                 "max_position_err_m": pos, "max_angle_err_deg": round(ang, 6)}
        elif chk.id == "camera_clearance":
            d = built_spec["camera_clearance"]["min_distance_m"]
            r = {"passed": d >= p["min_m"], "min_distance_m": d}
        elif chk.kind == "framing":
            h, w = idx.shape[1:]
            worst = {}
            ok = True
            for name in p["objects"]:
                counts = [(int((f == om[name]).sum())) for f in idx]
                edge = [bool(((f == om[name])[[0, -1], :].any() or (f == om[name])[:, [0, -1]].any())) for f in idx]
                worst[name] = {"min_px": min(counts), "touches_border_frames": int(sum(edge))}
                ok &= min(counts) >= p["min_px"] and not any(edge)
            r = {"passed": ok, "objects": worst, "frame": [w, h]}
        elif chk.id == "depth_valid":
            bg = idx == 0
            inner = bg[:, 1:-1, 1:-1]
            iso = int((inner & ~bg[:, :-2, 1:-1] & ~bg[:, 2:, 1:-1] & ~bg[:, 1:-1, :-2] & ~bg[:, 1:-1, 2:]).sum())
            finite = bool(np.isfinite(depth[idx > 0]).all())
            r = {"passed": iso <= p["max_isolated_background_px"] and finite, "isolated_background_px": iso,
                 "finite_depth_on_objects": finite}
        elif chk.id == "first_frame_aligned":
            ff = out_dir / "first_frame.png"
            r = {"passed": ff.is_file() and [b.manifest.camera.intrinsics.resolution_x,
                                             b.manifest.camera.intrinsics.resolution_y] == list(p["resolution"]),
                 "method": "same .blend, camera and frame as the passes"}
        results[chk.id] = r
    return {"passed": all(v["passed"] for v in results.values()), "checks": results,
            "not_run": [c.id for c in compiled.qc if c.stage != "preflight"]}
