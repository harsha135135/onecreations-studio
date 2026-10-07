"""QC as data: the checks a compiled shot must pass, per stage, and the evaluator for the deterministic preflight.

D1 implemented the PREFLIGHT checks (control inputs, before any generation); D2 implements the POST_GENERATION
checks (A-F: video validity, subject control, action timing, weapon integrity, camera, output integrity; evaluated in
video_qc.py) and the FINAL checks. Each post-generation check declares its failure action as data (`on_fail`:
repair / regenerate / fail); measurable checks only, never an aesthetic score.
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
    cp = [0, 12, 24, 36, 48]
    post = [
        ("video_valid", "video", {"min_std": 3.0, "spike_abs": 25.0, "spike_rel": 6.0, "on_fail": "regenerate"},
         "technical validity (decode, count, size, blank or corrupt frames)"),
        ("subject_framing", "framing", {"frames": cp, "max_offset_px": 32, "min_ncc": 0.5, "on_fail": "fail"},
         "M2 position check (about half a 64-px guide cell)"),
        ("contact_timing", "timing", {"search_frames": 4, "radius_px": 24, "onset_frac": 0.9, "tol_frames": 2,
                                      "max_offset_px": 6, "min_ncc": 0.45, "on_fail": "fail"},
         "M2-B timing tolerance (2 frames); thresholds calibrated on Showcase v1 run 1 before D2"),
        ("apex_presence", "timing", {"radius_px": 24, "min_ncc": 0.4, "max_offset_px": 10, "on_fail": "fail"},
         "M2-B apex; calibrated on Showcase v1 run 1"),
        ("weapon_integrity", "weapon", {"radius_px": 24, "min_ncc": 0.4, "max_offset_px": 10, "on_fail": "repair"},
         "raw fast-weapon failure detector (M2-B / M3-A / Showcase); repaired by the protection policy"),
        ("camera_progression", "camera", {"frames": cp, "margin_px": 8, "max_offset_px": 24, "min_ncc": 0.5,
                                          "on_fail": "fail"}, "M2-C (generated move ~0.9x the authored one)"),
        ("output_integrity", "video", {"max_hole_frac": 0.005, "on_fail": "regenerate"}, "no black holes"),
    ]
    final = [
        ("final_valid", "video", {"min_std": 3.0, "spike_abs": 40.0, "spike_rel": 8.0}, "delivery validity"),
        ("protected_weapon_present", "weapon", {"min_ncc": 0.7}, "the repaired weapon survives effects and grade"),
        ("effects_begin_at_contact", "events", {"min_change": 8, "max_change_before": 2},
         "effects keyed from strike.CONTACT"),
        ("bounded_repair", "composite", {"allowed_pass_indices": [ctx["weapon_pass_indices"]], "band_px": 10,
                                         "max_outside_frac": 0.001}, "repair stays near the weapon"),
        ("no_holes", "video", {"max_hole_frac": 0.005}, "no black holes after compositing"),
    ]
    if "parry" in ctx:                                            # D3: a weapon-on-weapon contact (the parry pair)
        pr = ctx["parry"]
        pre[2] = (pre[2][0], pre[2][1], dict(pre[2][2], min_visible_frac=0.9),
                  pre[2][3] + "; D3: frames where the weapon is < 90 % visible (ray-cast) are excluded and reported")
        pre += [
            ("defender_stationary_root", "joints", {"rig": pr["defender_rig"], "bones": ["root", "pelvis", "thigh.L",
                                                                                      "thigh.R", "shin.L", "shin.R"],
                                                    "max_m": 0.001}, "D3: the defender's root and legs are never keyed"),
            ("defender_weapon_axis", "joints", {"rig": pr["defender_rig"], "bone": pr["weapon_bone"],
                                                "object": pr["weapon"], "max_median_px": 3.0},
             "D3: the trident bone lies on the rendered trident (median pixel distance to the projected bone line)"),
            ("contact_geometry", "contact", {"max_abs_gap_m": 0.01, "before_frames": 4, "min_gap_before_m": 0.30,
                                             "min_gap_m": -0.005, "min_body_clearance_m": 0.10},
             "D3: the mace head touches the shaft on CONTACT (solved by construction), was clear of it 4 frames "
             "before, and no weapon passes through a weapon or a body (vertex distances, ~1 cm resolution)"),
            ("contact_visible", "contact", {"objects": [ctx["weapon_track"], pr["weapon"]], "radius_px": 16,
                                            "min_border_px": 64}, "D3: both weapons visible at the projected contact"),
            ("defender_weapon_visible", "framing", {"objects": [pr["weapon"]], "min_px": 150}, "D3: trident in frame"),
        ]
        post += [
            ("defender_framing", "framing", {"object": pr["defender"], "frames": sorted(set(cp + [pr["contact_frame"]])),
                                             "max_offset_px": 32, "min_ncc": 0.5, "on_fail": "fail"},
             "D3: the reacting defender follows the authored pose (the subject_framing rule, plus the contact frame)"),
            ("trident_integrity", "weapon", {"object": pr["weapon"], "from_event": pr["defender_start_event"],
                                             "dilate_px": 2, "min_ncc": 0.4, "on_fail": "repair"},
             "D3: thin raw weapon detector (masked NCC on the authored trident); evidence for the P6 repair"),
        ]
    out = [QCCheck(id=i, stage="preflight", kind=k, params=p, implemented=True, provenance=s) for i, k, p, s in pre]
    out += [QCCheck(id=i, stage="post_generation", kind=k, params=p, implemented=True, provenance=s)
            for i, k, p, s in post]
    out += [QCCheck(id=i, stage="final", kind=k, params=p, implemented=True, provenance=s) for i, k, p, s in final]
    return out


def evaluate_preflight(compiled, export_dir: Path, first_frame: Path, built_spec: dict) -> dict:
    """Run the implemented preflight checks on a built scene (export bundle, controls, first frame)."""
    from onecreations.blender_bundle import load_bundle
    from onecreations.director import camera as cam
    from onecreations.geometry.intrinsics import project

    b = load_bundle(export_dir)
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
            # D3: frames where another object hides part of the weapon move its visible centroid; with
            # min_visible_frac they are excluded (and reported) using the engine's per-frame visibility
            vis = (built_spec.get("tracking", {}).get("visibility") or {}).get(p["object"])
            skip = {f for f, v in enumerate(vis or []) if "min_visible_frac" in p and v < p["min_visible_frac"]}
            errs = {}
            for f in range(len(tails)):
                ys, xs = np.nonzero(idx[f] == om[p["object"]])
                uv, _ = project(tails[f][None], cam_arr["c2w"][f], b.K())
                errs[f] = math.dist((xs.mean() + 0.5, ys.mean() + 0.5), (uv[0, 0], uv[0, 1]))
            used = [e for f, e in errs.items() if f not in skip]
            r = {"passed": max(used) <= p["max_px"], "max_px": round(max(used), 2)}
            if "min_visible_frac" in p:
                r["occluded_frames_excluded"] = {str(f): {"visible_frac": vis[f], "px": round(errs[f], 2)}
                                                 for f in sorted(skip)}
        elif chk.id == "defender_weapon_axis":
            arm = next(a for a in b.manifest.armatures if a.oc_id == p["rig"])
            bi = list(arm.bones).index(p["bone"])
            heads, tails = b.joints()[f"{p['rig']}.heads"][:, bi], b.joints()[f"{p['rig']}.tails"][:, bi]
            cam_arr = b.camera_arrays()
            meds = []
            for f in range(len(heads)):
                ys, xs = np.nonzero(idx[f] == om[p["object"]])
                uv, _ = project(np.stack([heads[f], tails[f]]), cam_arr["c2w"][f], b.K())
                a, d = uv[0], uv[1] - uv[0]
                d = d / max(float(np.hypot(*d)), 1e-9)
                rel = np.stack([xs + 0.5 - a[0], ys + 0.5 - a[1]], axis=1)
                meds.append(float(np.median(np.abs(rel[:, 0] * d[1] - rel[:, 1] * d[0]))))
            r = {"passed": max(meds) <= p["max_median_px"], "max_median_px": round(max(meds), 2)}
        elif chk.id == "contact_geometry":
            c = built_spec["choreography"]["contact"]
            s, f0 = c["series"], c["frame_output"]
            gap = s["head_to_shaft_m"]
            body = min(min(s["trident_to_attacker_m"]), min(s["head_to_defender_m"]))
            r = {"passed": abs(gap[f0]) <= p["max_abs_gap_m"] and gap[f0 - p["before_frames"]] >= p["min_gap_before_m"]
                 and min(gap) >= p["min_gap_m"] and body >= p["min_body_clearance_m"],
                 "gap_at_contact_m": gap[f0], "gap_before_m": gap[f0 - p["before_frames"]], "min_gap_m": min(gap),
                 "min_body_clearance_m": body, "contact_frame": f0, "contact_u_m": s["shaft_u_m"][f0]}
        elif chk.id == "contact_visible":
            c = built_spec["choreography"]["contact"]
            f0 = c["frame_output"]
            uv, _ = project(np.array([c["contact_point_world"]], float), b.camera_arrays()["c2w"][f0], b.K())
            u, v = float(uv[0, 0]), float(uv[0, 1])
            h, w = idx.shape[1:]
            yy, xx = np.mgrid[0:h, 0:w]
            near = (xx + 0.5 - u) ** 2 + (yy + 0.5 - v) ** 2 <= p["radius_px"] ** 2
            seen = {o: int((near & (idx[f0] == om[o])).sum()) for o in p["objects"]}
            border = min(u, v, w - u, h - v)
            r = {"passed": all(n > 0 for n in seen.values()) and border >= p["min_border_px"],
                 "contact_px": [round(u, 1), round(v, 1)], "pixels_near_contact": seen, "border_px": round(border, 1)}
        elif chk.id in ("stationary_root", "defender_stationary_root"):
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
            ff = Path(first_frame)
            r = {"passed": ff.is_file() and [b.manifest.camera.intrinsics.resolution_x,
                                             b.manifest.camera.intrinsics.resolution_y] == list(p["resolution"]),
                 "method": "same .blend, camera and frame as the passes"}
        else:
            raise ValueError(f"preflight check {chk.id!r} is declared implemented but has no evaluator")
        results[chk.id] = r
    return {"passed": all(v["passed"] for v in results.values()), "checks": results,
            "not_run": [c.id for c in compiled.qc if c.stage != "preflight"]}
