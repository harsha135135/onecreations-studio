"""Action presets -> semantic events and ActionTimeline phases (pure Python; mirrors the engine's choreography).

An action preset (registry kind `action`) defines named events (START, APEX, CONTACT, ...) as output frames, some of
which move with a parameter (CONTACT = APEX + strike_frames), and phases spanning event pairs. Everything downstream
(effects, grade jolt, compositor triggers, QC) refers to `action_id.EVENT`, never to a frame number, so changing the
strike timing moves every dependent effect. The Blender builder computes the same timeline independently; the
Blender test checks they agree.
"""

from __future__ import annotations

from fractions import Fraction

from onecreations.contracts.registry import AssetEntry
from onecreations.timebase import format_time


def action_params(entry: AssetEntry, params: dict) -> dict:
    """Preset defaults overridden by `params` (unknown parameters are rejected by validation, not here)."""
    out = {k: p.default for k, p in entry.params.items()}
    out.update(params)
    return out


def param_errors(entry: AssetEntry, params: dict) -> list[str]:
    errs = [f"unknown parameter {k!r} for {entry.id}" for k in params if k not in entry.params]
    for k, v in params.items():
        if k in entry.params:
            msg = entry.params[k].check(k, v)
            if msg:
                errs.append(msg)
    return errs


def resolve_events(entry: AssetEntry, params: dict) -> dict[str, int]:
    """Event name -> output frame for one action instance."""
    p = action_params(entry, params)
    out = {}
    for name, ev in entry.data["events"].items():
        frame = int(ev["frame"])
        if "plus_param" in ev:
            frame += int(p[ev["plus_param"]])
        out[name] = frame
    return out


def frame_time(frame: int, fps: int) -> Fraction:
    return Fraction(frame, fps)


def phases(entry: AssetEntry, params: dict, role: str) -> list[dict]:
    """ActionTimeline phases of one action instance (times are exact output-frame times; source == output here)."""
    ev = resolve_events(entry, params)
    fps = int(entry.data["fps"])
    return [{"id": ph["id"], "kind": ph["kind"], "actor": role, "start": format_time(frame_time(ev[ph["start"]], fps)),
             "end": format_time(frame_time(ev[ph["end"]], fps))} for ph in entry.data["phases"]]


def timeline_version(entry: AssetEntry, params: dict) -> str:
    tv = entry.data.get("timeline_version", {"default": "1.0.0"})
    p = action_params(entry, params)
    defaults = {k: s.default for k, s in entry.params.items()}
    return tv["default"] if all(p[k] == defaults[k] for k in defaults) else tv["other"].format(**p)


def event_phase_edge(entry: AssetEntry, event: str) -> tuple[str, str] | None:
    """The (phase, edge) of this action whose boundary is `event` (start edges first): how compositor triggers,
    which address timeline phase edges, express a semantic event."""
    for edge in ("start", "end"):
        for ph in entry.data["phases"]:
            if ph[edge] == event:
                return ph["id"], edge
    return None
