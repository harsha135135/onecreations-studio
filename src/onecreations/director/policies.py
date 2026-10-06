"""Processing-policy selection: deterministic engineering rules, not ML, each with its provenance.

A ProcessingPolicy decides separately how an object's APPEARANCE and its GEOMETRY are treated (generative vs
deterministic / protected), that timing is always authored, and whether a future masked edit may target it.

Rules (heuristics from this project's own runs, not universal truths about LTX):
  P1 weapon: a weapon whose class a protection rule covers, used by an action whose estimated peak screen speed
     reaches the rule's trigger, gets protected geometry (Blender owns it) with generative-looking grade. Source:
     M2-B smear in the fastest frames at >= ~0.7 head widths/frame (a local observation at 512x320), unchanged at
     768x448, M3-A / Showcase repairs. The speed estimate scales the preset's measured peak by the default
     strike duration over the requested one.
  P2 character: generative appearance and geometry (shape is held by the depth control); editable iff its mask is
     separable (own object index).
  P3 integrated prop (e.g. the trident inside the defender mesh): follows its owner; never separately editable.
  P4 environment part: generative (trusted); editable iff separable.
  P5 effect: deterministic appearance and timing (rendered layers keyed from semantic events).
  An explicit ShotSpec.protection entry overrides P1 (rule id, or "none").
"""

from __future__ import annotations

from onecreations.contracts.director import ProcessingPolicy, ShotSpec
from onecreations.director.registry import Registry


def estimated_peak_speed(action_entry, params: dict) -> float | None:
    measured = action_entry.data.get("peak_weapon_speed_head_widths_per_frame")
    if not measured:
        return None
    peak = max(measured.values())
    if "strike_frames" in action_entry.params:
        default = action_entry.params["strike_frames"].default
        peak *= default / params.get("strike_frames", default)
    return round(peak, 3)


def weapon_rule(spec: ShotSpec, reg: Registry, prop) -> tuple[str | None, str]:
    """(rule id or None, provenance) for one weapon prop, applying P1 and explicit overrides."""
    explicit = next((p for p in spec.protection if p.object == prop.id), None)
    if explicit is not None:
        return (None if explicit.rule == "none" else explicit.rule), "ShotSpec.protection (explicit)"
    w = reg.get(prop.asset, "weapon")
    if w.data["mount"]["type"] == "integrated":
        return None, "P3: integrated prop follows its owner"
    actions = [a for a in spec.actions if a.actor == prop.owner]
    for rule in reg.of_kind("protection_rule"):
        if w.data["weapon_class"] not in rule.data["applies_to_weapon_class"]:
            continue
        for a in actions:
            if not reg.has(a.preset, "action"):
                continue
            speed = estimated_peak_speed(reg.get(a.preset), a.params)
            trig = rule.data.get("trigger", {}).get("min_peak_speed_head_widths_per_frame", 0.0)
            if speed is not None and speed >= trig:
                return rule.id, (f"P1: {w.data['weapon_class']} weapon, {a.preset} estimated peak {speed} head "
                                 f"widths/frame >= {trig} (local observation, M2-B/768/M3-A/Showcase)")
    return None, "P1 not triggered: generative output trusted"


def policy_for(kind: str, separable: bool, rule: str | None = None, provenance: str = "") -> ProcessingPolicy:
    if kind == "weapon" and rule:
        return ProcessingPolicy(appearance="generative", geometry="protected", editable=separable, rule=rule,
                                provenance=provenance)
    if kind == "effect":
        return ProcessingPolicy(appearance="deterministic", geometry="protected", editable=False,
                                provenance="P5: deterministic effect layer keyed from a semantic event")
    label = {"character": "P2", "weapon": "P3", "environment_part": "P4"}[kind]
    return ProcessingPolicy(appearance="generative", geometry="generative", editable=separable,
                            provenance=provenance or f"{label}: generative, held by the depth control")


def preview_rule(reg: Registry, weapon_id: str, action_id: str, params: dict) -> str | None:
    """P1 for a planned (weapon, action) pair, before a ShotSpec exists (the director's preview)."""
    w = reg.get(weapon_id, "weapon")
    speed = estimated_peak_speed(reg.get(action_id, "action"), params)
    for rule in reg.of_kind("protection_rule"):
        trig = rule.data.get("trigger", {}).get("min_peak_speed_head_widths_per_frame", 0.0)
        if w.data["weapon_class"] in rule.data["applies_to_weapon_class"] and speed is not None and speed >= trig:
            return rule.id
    return None
