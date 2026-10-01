"""Cross-reference validation of a shot package against its project (v1 §13, §28).

Schema validity is the contracts' job; this module checks that the pieces fit together: IDs resolve, the time map
covers the shot, the camera and choreography cover the warped source interval, events and required contacts line
up, regions don't conflict, and the chosen backend actually supports what the shot asks for.

Time domain: camera trajectories, choreographies and events are all in **source time** (choreography t = 0).
"""

from __future__ import annotations

from fractions import Fraction

from onecreations.contracts import Shot
from onecreations.shotpkg.issues import Issue
from onecreations.shotpkg.project import ShotContext
from onecreations.timebase import FrameRate, TimeWarp, format_time

TIME_TOL = 1e-9


def shot_timewarp(shot: Shot, ctx: ShotContext) -> TimeWarp | None:
    if shot.timewarp is None:
        return TimeWarp.identity(shot.duration_seconds, shot.source_start)
    tw = ctx.timewarps.get(shot.timewarp)
    return tw.to_timewarp() if tw else None


def validate_shot(shot: Shot, ctx: ShotContext) -> list[Issue]:
    issues: list[Issue] = []

    def err(code: str, msg: str, field: str | None = None) -> None:
        issues.append(Issue(code, "error", msg, field))

    def warn(code: str, msg: str, field: str | None = None) -> None:
        issues.append(Issue(code, "warning", msg, field))

    # ---- references resolve
    for a in shot.assets:
        if a not in ctx.assets:
            err("SHOT_UNKNOWN_ASSET", f"asset {a!r} is not in the project", "assets")
    if shot.scene_state_in not in ctx.scene_states:
        err("SHOT_UNKNOWN_SCENE_STATE", f"scene_state_in {shot.scene_state_in!r} is not a known scene state",
            "scene_state_in")
    if shot.lighting is not None and shot.lighting not in ctx.lighting:
        err("SHOT_UNKNOWN_LIGHTING", f"lighting {shot.lighting!r} is unknown", "lighting")
    for r in shot.references:
        if r not in ctx.references:
            err("SHOT_UNKNOWN_REFERENCE", f"reference {r!r} is unknown", "references")
    choreo = ctx.choreographies.get(shot.choreography)
    if choreo is None:
        err("SHOT_UNKNOWN_CHOREOGRAPHY", f"choreography {shot.choreography!r} is unknown", "choreography")
    if shot.camera not in ctx.camera_motions:
        err("SHOT_UNKNOWN_CAMERA", f"camera {shot.camera!r} is unknown", "camera")
    if shot.timewarp is not None and shot.timewarp not in ctx.timewarps:
        err("SHOT_UNKNOWN_TIMEWARP", f"timewarp {shot.timewarp!r} is unknown", "timewarp")
    for e in shot.events:
        if e not in ctx.events:
            err("SHOT_UNKNOWN_EVENT", f"event {e!r} is unknown", "events")

    # ---- frames and time map
    rate = FrameRate(shot.output_fps.num, shot.output_fps.den)
    n_frames = rate.frame_count(shot.duration_seconds)
    if n_frames.denominator != 1:
        err("SHOT_FRAME_COUNT_NOT_INTEGER",
            f"duration {format_time(shot.duration_seconds)} s × {rate.num}/{rate.den} fps = {format_time(n_frames)} "
            "frames; durations must be a whole number of output frames", "duration_seconds")
    if shot.timewarp is not None and shot.source_start != 0:
        warn("SHOT_SOURCE_START_IGNORED", "source_start is ignored when a timewarp is given (keys are absolute)",
             "source_start")
    tw = shot_timewarp(shot, ctx)
    src0 = src1 = None
    if tw is not None:
        if not tw.covers_output(0, shot.duration_seconds):
            err("SHOT_TIMEWARP_DOMAIN",
                f"timewarp covers output [{format_time(tw.output_start)}, {format_time(tw.output_end)}] s but the shot "
                f"needs [0, {format_time(shot.duration_seconds)}] s", "timewarp")
        else:
            src0, src1 = tw(0), tw(shot.duration_seconds)

    # ---- choreography coverage and actors
    if choreo is not None:
        for role, asset_id in choreo.actors.items():
            if asset_id not in shot.assets:
                err("SHOT_ACTOR_ASSET_MISSING", f"choreography role {role!r} uses asset {asset_id!r}, which the shot "
                    "does not list", "assets")
        if src1 is not None and src1 > choreo.duration:
            err("SHOT_CHOREO_COVERAGE", f"shot needs source time up to {format_time(src1)} s but choreography "
                f"{choreo.id} lasts {format_time(choreo.duration)} s", "choreography")

    # ---- camera coverage
    if shot.camera in ctx.camera_motions and src0 is not None:
        rng = ctx.camera_ranges.get(shot.camera)
        if rng is None:
            warn("SHOT_CAMERA_UNLOADED", f"camera {shot.camera!r} samples not loaded; coverage unchecked", "camera")
        elif rng[0] > float(src0) + TIME_TOL or rng[1] < float(src1) - TIME_TOL:
            err("SHOT_CAMERA_COVERAGE", f"camera samples cover [{rng[0]:g}, {rng[1]:g}] s but the shot needs source "
                f"[{float(src0):g}, {float(src1):g}] s", "camera")

    # ---- events and contacts
    if src0 is not None:
        for e in shot.events:
            ev = ctx.events.get(e)
            if ev is not None and not (src0 <= ev.source_time_seconds <= src1):
                err("SHOT_EVENT_OUTSIDE", f"event {e} at source {format_time(ev.source_time_seconds)} s is outside "
                    f"the shot's source interval [{format_time(src0)}, {format_time(src1)}]", "events")
        if choreo is not None:
            for c in choreo.contacts:
                if c.end < src0 or c.start > src1 or c.event is None:
                    continue
                if c.event not in shot.events:
                    (err if c.required else warn)(
                        "SHOT_CONTACT_EVENT_MISSING", f"contact {c.id} in this shot triggers event {c.event}, which the "
                        "shot does not include", "events")
                    continue
                ev = ctx.events.get(c.event)
                if ev is not None and not (c.start <= ev.source_time_seconds <= c.end):
                    err("SHOT_CONTACT_EVENT_MISMATCH", f"event {ev.id} at {format_time(ev.source_time_seconds)} s is not "
                        f"inside contact {c.id} [{format_time(c.start)}, {format_time(c.end)}] s", "events")

    # ---- generation request vs backend
    gen = shot.generation
    if gen is not None:
        overlap = sorted(set(gen.allowed_regions) & set(gen.protected_regions))
        if overlap:
            err("SHOT_REGION_CONFLICT", f"regions both allowed and protected: {overlap}", "generation")
        for r in gen.allowed_regions + gen.protected_regions:
            if r not in ctx.mask_layers:
                err("SHOT_UNKNOWN_REGION", f"region {r!r} is not a known mask layer", "generation")
        be = ctx.backends.get(gen.backend_profile)
        if be is None:
            err("SHOT_UNKNOWN_BACKEND", f"backend profile {gen.backend_profile!r} is unknown", "generation")
        else:
            unsupported = sorted(set(gen.controls) - set(be.control_modalities))
            if unsupported:
                err("SHOT_BACKEND_UNSUPPORTED_CONTROL", f"backend {be.id} does not accept {unsupported} "
                    f"(supports {sorted(be.control_modalities)})", "generation.controls")
            if gen.reference_count > be.max_reference_images:
                err("SHOT_TOO_MANY_REFERENCES", f"{gen.reference_count} references requested, backend {be.id} accepts "
                    f"{be.max_reference_images}", "generation.reference_count")
            for dim, mult, mx in (("width", be.width_multiple, be.max_width), ("height", be.height_multiple, be.max_height)):
                v = getattr(gen, dim)
                if v is None:
                    continue
                if v % mult:
                    err("SHOT_BACKEND_DIMENSIONS", f"{dim} {v} is not a multiple of {mult}", f"generation.{dim}")
                if mx is not None and v > mx:
                    err("SHOT_BACKEND_DIMENSIONS", f"{dim} {v} exceeds backend max {mx}", f"generation.{dim}")
            if n_frames.denominator == 1 and not be.frame_count.allows(int(n_frames)):
                warn("SHOT_BACKEND_FRAMES", f"{int(n_frames)} frames do not fit backend {be.id}'s frame rule in one "
                     "window; the shot must be generated in windows or retained from 3D", "generation")
            if be.admission.status not in ("A_admitted", "B_preview_only"):
                warn("SHOT_BACKEND_NOT_ADMITTED", f"backend {be.id} admission status is {be.admission.status}",
                     "generation.backend_profile")
    return issues


def event_schedule(shot: Shot, ctx: ShotContext) -> list[dict]:
    """Where each event lands in output time and frames — the timing VFX, audio and review all share."""
    tw = shot_timewarp(shot, ctx)
    rate = FrameRate(shot.output_fps.num, shot.output_fps.den)
    out = []
    for e in shot.events:
        ev = ctx.events.get(e)
        if ev is None or tw is None:
            continue
        try:
            t_out = tw.inverse(ev.source_time_seconds)
        except ValueError:
            continue
        pos = rate.frame_position(t_out)
        nearest = rate.nearest_frame(t_out)
        out.append({"event": e, "type": ev.type, "source_time": format_time(ev.source_time_seconds),
                    "output_time": format_time(t_out), "frame_position": format_time(pos),
                    "nearest_frame": nearest, "offset_from_nearest_frames": format_time(pos - Fraction(nearest))})
    return out
