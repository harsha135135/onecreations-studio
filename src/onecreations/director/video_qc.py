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
    best = max(s["ncc"] for s in scores.values() if s)
    onset = min(f for f, s in scores.items() if s and s["ncc"] >= p["onset_frac"] * best
                and s["offset_px"] <= p["max_offset_px"])
    ok = abs(onset - c) <= p["tol_frames"] and best >= p["min_ncc"]
    return {"passed": bool(ok), "contact_frame": c, "observed_onset": int(onset), "offset_frames": int(onset - c),
            "best_ncc": best, "per_frame_ncc": {str(f): s["ncc"] if s else None for f, s in scores.items()}}


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


def post_generation(compiled, ref, raw, idx, om) -> dict:
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
            r = check_video_valid(raw, compiled.frames, compiled.resolution, p)
        elif cid == "subject_framing":
            r = check_subject_framing(ref, raw, idx, actor, p)
        elif cid == "contact_timing":
            r = check_contact_timing(compiled, gref, graw, idx, head, p)
        elif cid == "apex_presence":
            r = check_apex_presence(compiled, gref, graw, idx, head, p)
        elif cid == "weapon_integrity":
            r = check_weapon_integrity(compiled, gref, graw, idx, head, p)
        elif cid == "camera_progression":
            r = check_camera_progression(ref, raw, idx, env, p)
        elif cid == "output_integrity":
            r = check_output_integrity(ref, raw, p)
        else:
            continue
        r["on_fail"] = p["on_fail"]
        out[cid] = r
    return out


def decide(compiled, results: dict) -> dict:
    """Turn check results + declared on_fail actions + object policies into the run decision (data, not code)."""
    protected = [o.id for o in compiled.semantic_objects if o.policy.geometry == "protected" and o.kind == "weapon"]
    repairs = [{"object": o, "action": "protected_layer", "reason": "policy (geometry=protected), not QC"}
               for o in protected]
    regenerate, fail = [], []
    for cid, r in results.items():
        if r["passed"]:
            continue
        action = r["on_fail"]
        if action.startswith("repair"):
            if not protected:
                fail.append(f"{cid}: needs repair but no protection policy covers it")
            else:
                for rep in repairs:
                    rep.setdefault("qc_evidence", []).append(cid)
        elif action == "regenerate":
            regenerate.append(cid)
        else:
            fail.append(cid)
    status = "fail" if fail else ("regenerate" if regenerate else "proceed")
    return {"status": status, "repairs": repairs, "regenerate_for": regenerate, "fail_for": fail}


def final(compiled, ref, raw, repaired, composite, final_video, idx, om, layer_alpha: dict, fx_alpha: dict) -> dict:
    """Deterministic integrity checks of the delivered video and of the compositing steps."""
    checks = {q.id: q.params for q in compiled.qc if q.stage == "final" and q.implemented}
    out = {}
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
