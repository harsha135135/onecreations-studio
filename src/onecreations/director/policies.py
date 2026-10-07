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
  P6 contact weapon (D3): a weapon that takes part in an authored weapon-on-weapon contact (an action's `contact`,
     e.g. the mace and the trident of a parry) gets protected geometry, so both weapons meet where they were authored.
     Checked after P1, so a fast mace keeps its P1 rule.
  An explicit ShotSpec.protection entry overrides P1 and P6 (rule id, or "none").
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


def contact_props(spec: ShotSpec, reg: Registry) -> set[str]:
    """Prop ids that take part in an authored contact: for each action with a `contact`, the weapon its actor holds
    and the weapon held by the actor of the partner action."""
    out = set()
    for a in spec.actions:
        if not reg.has(a.preset, "action") or "contact" not in reg.get(a.preset).data:
            continue
        partner = reg.get(a.preset).data["contact"]["partner_action"]
        actors = {a.actor} | {b.actor for b in spec.actions if b.preset == partner}
        out |= {p.id for p in spec.props if p.owner in actors and reg.has(p.asset, "weapon")
                and reg.get(p.asset).data["mount"]["type"] == "rig_bone"}
    return out


def weapon_rule(spec: ShotSpec, reg: Registry, prop) -> tuple[str | None, str]:
    """(rule id or None, provenance) for one weapon prop, applying P1, P6 and explicit overrides."""
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
            if "min_peak_speed_head_widths_per_frame" in rule.data.get("trigger", {}) and speed is not None                     and speed >= trig:
                return rule.id, (f"P1: {w.data['weapon_class']} weapon, {a.preset} estimated peak {speed} head "
                                 f"widths/frame >= {trig} (local observation, M2-B/768/M3-A/Showcase)")
    if prop.id in contact_props(spec, reg):
        for rule in reg.of_kind("protection_rule"):
            if rule.data.get("trigger", {}).get("in_contact") and                     w.data["weapon_class"] in rule.data["applies_to_weapon_class"]:
                return rule.id, f"P6: {prop.id} takes part in an authored weapon-on-weapon contact"
    return None, "P1/P6 not triggered: generative output trusted"


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


def preview_rule(reg: Registry, weapon_id: str, action_id: str, params: dict,
                 in_contact: bool = False) -> tuple[str | None, str | None]:
    """(rule, "P1" / "P6") for a planned (weapon, action) pair, before a ShotSpec exists (the director's preview)."""
    w = reg.get(weapon_id, "weapon")
    if w.data["mount"]["type"] == "integrated":
        return None, None
    speed = estimated_peak_speed(reg.get(action_id, "action"), params)
    for rule in reg.of_kind("protection_rule"):
        trig = rule.data.get("trigger", {})
        if w.data["weapon_class"] in rule.data["applies_to_weapon_class"] and speed is not None and                 "min_peak_speed_head_widths_per_frame" in trig and speed >= trig["min_peak_speed_head_widths_per_frame"]:
            return rule.id, "P1"
    for rule in reg.of_kind("protection_rule"):
        if in_contact and rule.data.get("trigger", {}).get("in_contact") and                 w.data["weapon_class"] in rule.data["applies_to_weapon_class"]:
            return rule.id, "P6"
    return None, None
