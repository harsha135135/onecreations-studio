"""Automatic post-generation and final QC for the Showcase shot class (D2).

Measurable checks only, never an aesthetic score. Colour trackers are not used: under the warm high-contrast grade
stone and gold share hues (Showcase v1). Every check compares the video with the authored Blender reference through
normalised cross-correlation (NCC) of grey patches located by the object-index pass, which is invariant to the
generated video's brightness and contrast:

  video_valid         decodable, expected frame count and size, no blank or abruptly corrupt frames
  subject_framing     the attacker's reference patch is found within `max_offset_px` of its authored place
  contact_timing      the weapon head reaches its CONTACT position within `tol_frames` of strike.CONTACT
  apex_presence       the weapon head is near its APEX position at strike.APEX
  weapon_integrity    per-frame NCC of the weapon head in the strike interval; a low value = raw weapon failure
  camera_progression  the background (environment-only pixels) stays registered to the authored camera move
  output_integrity    no holes (exact-black regions the reference does not have)
  defender_framing    D3: the reacting defender's reference patch, as subject_framing, plus the contact frame
  trident_integrity   D3: masked NCC of the raw video on the authored (thin) defender weapon; low = raw weapon failure

D3(b) ownership-aligned profile (showcase_class_contact_v2; contact shots whose weapons are protected):
  parry_contact_timing_v2  the generated attacker's hand follows the authored grip around CONTACT (spatial, temporal
                           lag, whole-window trajectory); measured on the actor's own pixels, never on the weapon
  defender_reaction_timing the same measurement on the defender's rear grip over the raise and the bind
  raw_mace_contact         D3(a)'s contact_timing evaluator, recorded as a DIAGNOSTIC (the raw mace is replaced)
  final: mace_attached / trident_attached (no severe hand-weapon separation in the delivered video) and
         final_weapon_contact (the delivered protected layers touch on the bind frames)
A check whose on_fail is `diagnostic` is recorded and never decides the run. An evaluator that raises on a
measurement is recorded as a failed check with the error, not a crashed executor (D3(a)); a declared check without an
evaluator still raises (a configuration error).

What a failing check means is declared as data (QCCheck.params["on_fail"]): `repair` (a deterministic policy owns
it), `regenerate` (technical; at most the pre-registered retry), or `fail` (no automatic remedy).
"""

from __future__ import annotations

import numpy as np

from onecreations.director import media


def _event(compiled, name: str) -> int:
    return next(e.frame for e in compiled.events if e.name == name)


def _down(img: np.ndarray, k: int = 2) -> np.ndarray:
    h, w = img.shape[0] // k * k, img.shape[1] // k * k
    return img[:h, :w].reshape(h // k, k, w // k, k).mean(axis=(1, 3))


def check_video_valid(video: np.ndarray, frames: int, size: tuple[int, int], p: dict) -> dict:
    n, h, w, _ = video.shape
    g = video.reshape(n, -1).astype(np.float32)
    std = g.std(axis=1)
    diffs = np.abs(np.diff(g, axis=0)).mean(axis=1) if n > 1 else np.zeros(0)
    med = float(np.median(diffs)) if len(diffs) else 0.0
    spikes = [int(i + 1) for i, d in enumerate(diffs) if d > max(p.get("spike_abs", 25.0), p.get("spike_rel", 6.0) * med)]
    blank = [int(i) for i, s in enumerate(std) if s < p.get("min_std", 3.0)]
    ok = n == frames and (w, h) == tuple(size) and not blank and not spikes
    return {"passed": ok, "frames": n, "size": [w, h], "blank_frames": blank, "abrupt_frames": spikes,
            "median_frame_diff": round(med, 2)}


def check_subject_framing(ref, video, idx, pass_index, p: dict) -> dict:
    rows = {}
    ok = True
    for f in p["frames"]:
        box = media.bbox(idx[f] == pass_index, pad=6)
        if box is None:
            rows[str(f)] = None
            ok = False
            continue
        x0, y0, x1, y1 = box
        tmpl = _down(media.gray(ref[f])[y0:y1, x0:x1])
        v, dx, dy = media.match(tmpl, _down(media.gray(video[f])), x0 // 2, y0 // 2, p["max_offset_px"] // 2)
        off = float(np.hypot(dx * 2, dy * 2))
        rows[str(f)] = {"ncc": round(v, 3), "offset_px": round(off, 1)}
        ok &= v >= p["min_ncc"] and off <= p["max_offset_px"]
    return {"passed": bool(ok), "frames": rows}


def box_blur(g: np.ndarray, k: int = 5) -> np.ndarray:
    """k x k box blur (edge-padded): makes the weapon match robust to the generated video's softness."""
    r = k // 2
    p = np.pad(g, r, mode="edge")
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


class Greys:
    """Blurred grey frames, computed once per video."""

    def __init__(self, video: np.ndarray):
        self.video = video
        self._cache: dict[int, np.ndarray] = {}

    def __len__(self) -> int:
        return len(self.video)

    def __getitem__(self, f: int) -> np.ndarray:
        if f not in self._cache:
            self._cache[f] = box_blur(media.gray(self.video[f]))
        return self._cache[f]


def _head_ncc(ref, video, idx, pass_index, f_ref, f_vid, radius):
    """Where the reference weapon head of frame f_ref is found in frame f_vid (blurred greys), and how well."""
    box = media.bbox(idx[f_ref] == pass_index, pad=6)
    if box is None:
        return None
    x0, y0, x1, y1 = box
    v, dx, dy = media.match(ref[f_ref][y0:y1, x0:x1], video[f_vid], x0, y0, radius)
    return {"ncc": round(v, 3), "offset_px": round(float(np.hypot(dx, dy)), 1)}


def check_contact_timing(compiled, ref, video, idx, pass_index, p: dict) -> dict:
    c = _event(compiled, "strike.CONTACT")
    window = range(max(0, c - p["search_frames"]), min(len(video), c + p["search_frames"] + 1))
    scores = {f: _head_ncc(ref, video, idx, pass_index, c, f, p["radius_px"]) for f in window}
    best = max((s["ncc"] for s in scores.values() if s), default=0.0)
    # D3 fix: no frame reaching the contact position is a failed check, not an evaluator crash (d3_run1)
    onset = min((f for f, s in scores.items() if s and s["ncc"] >= p["onset_frac"] * best
                 and s["offset_px"] <= p["max_offset_px"]), default=None)
    ok = onset is not None and abs(onset - c) <= p["tol_frames"] and best >= p["min_ncc"]
    return {"passed": bool(ok), "contact_frame": c, "observed_onset": None if onset is None else int(onset),
            "offset_frames": None if onset is None else int(onset - c), "best_ncc": best,
            "per_frame_ncc": {str(f): s["ncc"] if s else None for f, s in scores.items()},
            "per_frame_offset_px": {str(f): s["offset_px"] if s else None for f, s in scores.items()}}


def check_apex_presence(compiled, ref, video, idx, pass_index, p: dict) -> dict:
    a = _event(compiled, "strike.APEX")
    s = _head_ncc(ref, video, idx, pass_index, a, a, p["radius_px"])
    ok = s is not None and s["ncc"] >= p["min_ncc"] and s["offset_px"] <= p["max_offset_px"]
    return {"passed": bool(ok), "apex_frame": a, **(s or {})}


def check_weapon_integrity(compiled, ref, video, idx, pass_index, p: dict) -> dict:
    a, c = _event(compiled, "strike.APEX"), _event(compiled, "strike.CONTACT")
    per = {}
    for f in range(a, c + 1):
        per[str(f)] = _head_ncc(ref, video, idx, pass_index, f, f, p["radius_px"])
    failed = [int(f) for f, v in per.items() if v is None or v["ncc"] < p["min_ncc"] or
              v["offset_px"] > p["max_offset_px"]]
    return {"passed": not failed, "failed_frames": failed, "per_frame_ncc": per,
            "meaning": "raw generated weapon unreliable in these frames" if failed else "raw weapon held"}


def check_thin_weapon(compiled, ref, video, idx, pass_index, p: dict) -> dict:
    """A long thin weapon (D3 trident): its bounding box is mostly background, so compare only the authored weapon
    pixels (dilated) between the reference and the raw video, at zero offset (the camera holds to ~4 px)."""
    start = _event(compiled, p["from_event"])
    per = {}
    for f in range(start, len(video)):
        m = idx[f] == pass_index
        if m.sum() < 30:
            per[str(f)] = None
            continue
        m = _dilate(m, p["dilate_px"])
        per[str(f)] = round(media.ncc(ref[f][m], video[f][m]), 3)
    failed = [int(f) for f, v in per.items() if v is not None and v < p["min_ncc"]]
    return {"passed": not failed, "failed_frames": failed, "per_frame_ncc": per,
            "meaning": "raw generated weapon unreliable in these frames" if failed else "raw weapon held"}


def grip_track(bundle, rig: str, bone: str) -> np.ndarray:
    """Projected authored grip (the weapon bone's head = the holding hand) per output frame, in pixel-index coords."""
    from onecreations.geometry.intrinsics import project

    arm = next(a for a in bundle.manifest.armatures if a.oc_id == rig)
    heads = bundle.joints()[f"{rig}.heads"][:, list(arm.bones).index(bone)]
    cam = bundle.camera_arrays()
    out = np.zeros((len(heads), 2))
    for f in range(len(heads)):
        uv, _ = project(heads[f][None], cam["c2w"][f], bundle.K())
        out[f] = uv[0] - 0.5
    return out


def masked_match(ref_g: np.ndarray, vid_g: np.ndarray, mask: np.ndarray, x0: int, y0: int,
                 radius: int) -> tuple[float, int, int]:
    """Best masked NCC of the reference box ref_g[mask] (top-left x0, y0) within +-radius px in vid_g:
    (ncc, dx, dy). Vectorised over all offsets; off-image offsets are skipped."""
    h, w = mask.shape
    H, W = vid_g.shape
    pad = np.pad(vid_g, radius, mode="edge")
    region = pad[y0:y0 + h + 2 * radius, x0:x0 + w + 2 * radius]
    if region.shape != (h + 2 * radius, w + 2 * radius):
        return 0.0, 0, 0
    win = np.lib.stride_tricks.sliding_window_view(region, (h, w))[..., mask]       # (2r+1, 2r+1, K)
    a = ref_g[mask].astype(np.float64)
    a = a - a.mean()
    b = win - win.mean(axis=-1, keepdims=True)
    den = np.sqrt((a * a).sum() * (b * b).sum(axis=-1))
    score = np.where(den > 1e-6, (b @ a) / np.maximum(den, 1e-6), 0.0)
    yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    inside = (x0 + xx >= 0) & (y0 + yy >= 0) & (x0 + xx + w <= W) & (y0 + yy + h <= H)
    score = np.where(inside, score, -1.0)
    i = int(np.argmax(score))
    dy, dx = np.unravel_index(i, score.shape)
    return float(score.flat[i]), int(dx) - radius, int(dy) - radius


def check_grip_follow(compiled, ref, video, idx, bundle, p: dict) -> dict:
    """Does the generated actor's hand follow the authored grip? The reference patch is the owner's own pixels (the
    weapon passes excluded) in a box around the projected authored grip; it is searched in the video.

    spatial:    median per-frame offset (lag 0) over the window <= max_median_offset_px
    trajectory: every frame of the settled sub-window (from `settled_event` + `settled_offset`: the contact / the
                arrived block) within max_offset_px, so it is not close on one frame only; median NCC >= min_ncc.
                The fast approach frames before it are excluded from this per-frame bound because LTX smears fast
                limbs (M2-B; on D2's admitted raw the arm patch moves 12-29 px there while the hold holds 4-5.5 px)
    temporal:   the lag that best matches the reference sequence over the whole window (incl. the approach, where
                the timing information is) is within tol_frames
    """
    a, b = (_event(compiled, e) + o for e, o in ((p["from_event"], p["from_offset"]), (p["to_event"], p["to_offset"])))
    frames = [f for f in range(max(0, a), min(len(video), b + 1))]
    grip = grip_track(bundle, p["rig"], p["bone"])
    owner = [bundle.manifest.passes.object_index_map[o] for o in p["owner_objects"]]
    excl = [bundle.manifest.passes.object_index_map[o] for o in p["exclude_objects"]
            if o in bundle.manifest.passes.object_index_map]
    hb, r = p["half_box_px"], p["radius_px"]

    def patch(f):
        gx, gy = int(round(grip[f][0])), int(round(grip[f][1]))
        x0, y0 = gx - hb, gy - hb
        Hh, Ww = idx.shape[1:]
        if x0 < 0 or y0 < 0 or x0 + 2 * hb + 1 > Ww or y0 + 2 * hb + 1 > Hh:
            return None
        sl = (slice(y0, y0 + 2 * hb + 1), slice(x0, x0 + 2 * hb + 1))
        m = np.isin(idx[f][sl], owner) & ~np.isin(idx[f][sl], excl)
        return (x0, y0, sl, m) if m.sum() >= p["min_mask_px"] else None

    patches = {f: patch(f) for f in frames}
    rows, lag_scores = {}, {}
    for lag in range(-p["search_frames"], p["search_frames"] + 1):
        scores = []
        for f in frames:
            pt = patches[f]
            if pt is None or not 0 <= f + lag < len(video):
                continue
            x0, y0, sl, m = pt
            v, dx, dy = masked_match(ref[f][sl], video[f + lag], m, x0, y0, r)
            scores.append(v)
            if lag == 0:
                rows[str(f)] = {"ncc": round(v, 3), "offset_px": round(float(np.hypot(dx, dy)), 1),
                                "grip_px": [round(float(grip[f][0]), 1), round(float(grip[f][1]), 1)]}
        lag_scores[lag] = round(float(np.mean(scores)), 4) if scores else None
    measured = [v for v in rows.values()]
    if len(measured) < max(2, int(np.ceil(p["min_frames_frac"] * len(frames)))):
        return {"passed": False, "reason": "too few measurable frames", "window": [a, b], "frames": rows}
    offs = [v["offset_px"] for v in measured]
    nccs = [v["ncc"] for v in measured]
    s0 = _event(compiled, p["settled_event"]) + p["settled_offset"] if "settled_event" in p else a
    settled = [v["offset_px"] for f, v in rows.items() if int(f) >= s0]
    if not settled:
        return {"passed": False, "reason": "no measurable settled frame", "window": [a, b], "frames": rows}
    valid = {k: v for k, v in lag_scores.items() if v is not None}
    best_lag = max(valid, key=lambda k: (valid[k], -abs(k)))
    spatial = float(np.median(offs)) <= p["max_median_offset_px"]
    trajectory = max(settled) <= p["max_offset_px"] and float(np.median(nccs)) >= p["min_ncc"]
    temporal = abs(best_lag) <= p["tol_frames"]
    return {"passed": bool(spatial and trajectory and temporal), "window": [a, b],
            "spatial": {"passed": bool(spatial), "median_offset_px": round(float(np.median(offs)), 2)},
            "trajectory": {"passed": bool(trajectory), "settled_from": s0, "max_settled_offset_px": max(settled),
                           "max_window_offset_px": max(offs), "median_ncc": round(float(np.median(nccs)), 3)},
            "temporal": {"passed": bool(temporal), "best_lag_frames": int(best_lag), "lag_mean_ncc": lag_scores},
            "frames": rows}


def check_layer_contact(compiled, layer_alpha_by_id: dict, p: dict) -> dict:
    """The delivered protected layers touch on the bind frames: min 2-D distance between the opaque pixels of the two
    weapon layers <= max_gap_px (the 3-D contact itself is verified before generation)."""
    a, b = _event(compiled, p["event"]), _event(compiled, p["event"]) + p["bind_frames"]
    rows, ok = {}, True
    for f in range(a, b + 1):
        la, lb = (layer_alpha_by_id.get(lid, {}).get(f) for lid in p["layers"])
        if la is None or lb is None:
            rows[str(f)] = None
            ok = False
            continue
        ma, mb = la >= p["alpha_min"], lb >= p["alpha_min"]
        if not ma.any() or not mb.any():
            rows[str(f)] = None
            ok = False
            continue
        gap = 0
        while gap <= p["max_gap_px"] and not (_dilate(ma, gap) & mb).any():
            gap += 1
        rows[str(f)] = gap if gap <= p["max_gap_px"] else f"> {p['max_gap_px']}"
        ok &= gap <= p["max_gap_px"]
    return {"passed": bool(ok), "frames": rows}


def _safe(fn, *args) -> dict:
    """An ordinary measurement must end PASS or FAIL: an evaluator error becomes a failed, recorded check (D3(a))."""
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - recorded, never swallowed silently
        import traceback

        return {"passed": False, "evaluator_error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=4)}


def check_camera_progression(ref, video, idx, env_indices, p: dict) -> dict:
    rows = {}
    ok = True
    for f in p["frames"]:
        env = np.isin(idx[f], env_indices)
        ys, xs = np.nonzero(env)
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        m = p["margin_px"]
        y0, y1, x0, x1 = y0 + m, y1 - m, x0 + m, x1 - m
        tmpl = _down(media.gray(ref[f])[y0:y1, x0:x1], 4)
        v, dx, dy = media.match(tmpl, _down(media.gray(video[f]), 4), x0 // 4, y0 // 4, p["max_offset_px"] // 4)
        off = float(np.hypot(dx * 4, dy * 4))
        rows[str(f)] = {"ncc": round(v, 3), "offset_px": round(off, 1)}
        ok &= v >= p["min_ncc"] and off <= p["max_offset_px"]
    return {"passed": bool(ok), "frames": rows, "note": "background registered to the authored move (image space)"}


def check_output_integrity(ref, video, p: dict) -> dict:
    holes = []
    for f in range(len(video)):
        black = (video[f] <= 1).all(axis=-1) & ~(ref[min(f, len(ref) - 1)] <= 8).all(axis=-1)
        if black.mean() > p["max_hole_frac"]:
            holes.append(f)
    return {"passed": not holes, "hole_frames": holes}


def post_generation(compiled, ref, raw, idx, om, bundle=None) -> dict:
    """Run the post-generation checks declared in the CompiledShot QC contract on the raw generated video."""
    checks = {q.id: q for q in compiled.qc if q.stage == "post_generation" and q.implemented}
    strike_role = next(ph.actor for ph in compiled.action_timeline.phases if ph.kind == "strike")
    actor = om[compiled.action_timeline.actors[strike_role]]
    weapon = next((o for o in compiled.semantic_objects if o.kind == "weapon" and o.mask_separable), None)
    head = om[weapon.oc_ids[0]] if weapon else None
    env = sorted({i for o in compiled.semantic_objects if o.kind == "environment_part" for i in o.pass_indices})
    out = {}
    gref, graw = Greys(ref), Greys(raw)
    for cid, q in checks.items():
        p = q.params
        if cid == "video_valid":
            r = _safe(check_video_valid, raw, compiled.frames, compiled.resolution, p)
        elif cid == "subject_framing":
            r = _safe(check_subject_framing, ref, raw, idx, actor, p)
        elif cid in ("contact_timing", "raw_mace_contact"):
            r = _safe(check_contact_timing, compiled, gref, graw, idx, head, p)
        elif cid == "apex_presence":
            r = _safe(check_apex_presence, compiled, gref, graw, idx, head, p)
        elif cid == "weapon_integrity":
            r = _safe(check_weapon_integrity, compiled, gref, graw, idx, head, p)
        elif cid == "camera_progression":
            r = _safe(check_camera_progression, ref, raw, idx, env, p)
        elif cid == "output_integrity":
            r = _safe(check_output_integrity, ref, raw, p)
        elif cid == "defender_framing":
            r = _safe(check_subject_framing, ref, raw, idx, om[p["object"]], p)
        elif cid == "trident_integrity":
            r = _safe(check_thin_weapon, compiled, gref, graw, idx, om[p["object"]], p)
        elif cid in ("parry_contact_timing_v2", "defender_reaction_timing"):
            r = _safe(check_grip_follow, compiled, gref, graw, idx, bundle, p)
        else:
            raise ValueError(f"post-generation check {cid!r} is declared implemented but has no evaluator")
        r["on_fail"] = p["on_fail"]
        if "object" in p:                              # the engine object the check measured (repair evidence target)
            r["object"] = p["object"]
        elif cid in ("contact_timing", "raw_mace_contact", "apex_presence", "weapon_integrity") and weapon:
            r["object"] = weapon.oc_ids[0]
        out[cid] = r
    return out


def decide(compiled, results: dict) -> dict:
    """Turn check results + declared on_fail actions + object policies into the run decision (data, not code)."""
    weapons = [o for o in compiled.semantic_objects if o.policy.geometry == "protected" and o.kind == "weapon"]
    protected = [o.id for o in weapons]
    repairs = [{"object": o, "action": "protected_layer", "reason": "policy (geometry=protected), not QC"}
               for o in protected]
    owner = {oc: o.id for o in weapons for oc in o.oc_ids}
    regenerate, fail, diagnostics = [], [], []
    for cid, r in results.items():
        if r["passed"]:
            continue
        action = r["on_fail"]
        if action == "diagnostic":                     # D3(b): recorded evidence about a replaced component
            diagnostics.append(cid)
            continue
        if action.startswith("repair"):
            target = owner.get(r.get("object")) if r.get("object") else None
            if not protected or (r.get("object") and target is None):
                fail.append(f"{cid}: needs repair but no protection policy covers it")
            else:
                for rep in repairs:                    # a check that names its object is evidence for that object only
                    if target is None or rep["object"] == target:
                        rep.setdefault("qc_evidence", []).append(cid)
        elif action == "regenerate":
            regenerate.append(cid)
        else:
            fail.append(cid)
    status = "fail" if fail else ("regenerate" if regenerate else "proceed")
    out = {"status": status, "repairs": repairs, "regenerate_for": regenerate, "fail_for": fail}
    if diagnostics:
        out["diagnostic_failures"] = diagnostics
    return out


def final(compiled, ref, raw, repaired, composite, final_video, idx, om, layer_alpha: dict, fx_alpha: dict,
          bundle=None, layer_alpha_by_id: dict | None = None) -> dict:
    """Deterministic integrity checks of the delivered video and of the compositing steps."""
    checks = {q.id: q.params for q in compiled.qc if q.stage == "final" and q.implemented}
    out = {}
    known = {"final_valid", "protected_weapon_present", "effects_begin_at_contact", "bounded_repair", "no_holes",
             "mace_attached", "trident_attached", "final_weapon_contact"}
    unknown = set(checks) - known
    if unknown:
        raise ValueError(f"final checks {sorted(unknown)} are declared implemented but have no evaluator")
    for cid in ("mace_attached", "trident_attached"):
        if cid in checks:
            out[cid] = _safe(check_grip_follow, compiled, Greys(ref), Greys(final_video), idx, bundle, checks[cid])
    if "final_weapon_contact" in checks:
        out["final_weapon_contact"] = _safe(check_layer_contact, compiled, layer_alpha_by_id or {},
                                            checks["final_weapon_contact"])
    p = checks.get("final_valid")
    if p is not None:
        out["final_valid"] = check_video_valid(final_video, compiled.frames, compiled.resolution, p)
    p = checks.get("protected_weapon_present")
    if p is not None:
        per, ok = {}, True
        for f, alpha in sorted(layer_alpha.items()):
            m = alpha > 200
            if m.sum() < 50:
                continue
            a, b = media.gray(repaired[f])[m], media.gray(final_video[f])[m]
            v = media.ncc(a, b)
            per[str(f)] = round(v, 3)
            ok &= v >= p["min_ncc"]
        out["protected_weapon_present"] = {"passed": bool(ok and per), "frames_checked": len(per),
                                           "min_ncc": min(per.values()) if per else None}
    p = checks.get("effects_begin_at_contact")
    if p is not None:
        c = _event(compiled, "strike.CONTACT")
        diff = np.abs(composite.astype(np.int16) - repaired.astype(np.int16)).max(axis=-1)
        before = int(diff[:c].max()) if c > 0 else 0
        at = int(diff[c].max())
        first = next((f for f in range(len(diff)) if diff[f].max() > p["min_change"]), None)
        out["effects_begin_at_contact"] = {"passed": before <= p["max_change_before"] and at > p["min_change"] and
                                           first == c, "contact_frame": c, "first_changed_frame": first,
                                           "max_change_before_contact": before}
    p = checks.get("bounded_repair")
    if p is not None:
        worst = 0.0
        for f in range(len(raw)):
            changed = np.abs(repaired[f].astype(np.int16) - raw[f].astype(np.int16)).max(axis=-1) > 2
            allowed = np.zeros(changed.shape, bool)
            for ids in p["allowed_pass_indices"]:
                allowed |= np.isin(idx[f], ids)
            if f in layer_alpha:
                allowed |= layer_alpha[f] > 0
            allowed = _dilate(allowed, p["band_px"])
            worst = max(worst, float((changed & ~allowed).mean()))
        out["bounded_repair"] = {"passed": worst <= p["max_outside_frac"], "max_changed_outside_frac": round(worst, 6)}
    p = checks.get("no_holes")
    if p is not None:
        out["no_holes"] = check_output_integrity(ref, final_video, p)
    return out


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for axis in (0, 1):
        acc = out.copy()
        for s in range(1, r + 1):
            acc |= np.roll(out, s, axis=axis) | np.roll(out, -s, axis=axis)
        out = acc
    return out
