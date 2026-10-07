"""ShotSpec validation against the registry and the current engine, before any expensive execution.

Every problem is an Issue with a stable code, so an invalid spec fails here with a clear message instead of inside
Blender. Two families: registry/consistency rules (any engine) and ENGINE_* capability rules of the current
blender_showcase_v1 builder (one rigged attacker with the mace slam, one static defender, the temple, 49 frames; D3:
or the blocked strike against the rigged defender's parry).
"""

from __future__ import annotations

from onecreations.contracts.director import ShotSpec
from onecreations.director import actions as act
from onecreations.director import camera as cam
from onecreations.director.registry import Registry
from onecreations.shotpkg.issues import Issue

CONTACT_LAYER_COMPONENTS = {"dust", "debris", "sparks", "cracks", "flash"}


def _e(code, msg, field=None):
    return Issue(code, "error", msg, field)


def _w(code, msg, field=None):
    return Issue(code, "warning", msg, field)


def validate_spec(spec: ShotSpec, reg: Registry) -> list[Issue]:
    out: list[Issue] = []

    def need(asset_id, kind, field):
        if not reg.has(asset_id):
            out.append(_e("SPEC_UNKNOWN_ASSET", f"{field}: no registry entry {asset_id!r}", field))
            return None
        e = reg.get(asset_id)
        if e.kind != kind:
            out.append(_e("SPEC_WRONG_KIND", f"{field}: {asset_id!r} is a {e.kind}, expected a {kind}", field))
            return None
        return e

    env = need(spec.environment.asset, "environment", "environment.asset")
    chars = {c.id: (c, need(c.asset, "character", f"characters[{c.id}].asset")) for c in spec.characters}
    sem = set(chars) | {spec.environment.id} | {p.id for p in spec.props}
    if env:
        sem |= set(env.data["semantic_objects"])

    # props / weapons
    for p in spec.props:
        w = need(p.asset, "weapon", f"props[{p.id}].asset")
        if p.owner not in chars:
            out.append(_e("SPEC_UNKNOWN_SEMANTIC", f"props[{p.id}].owner {p.owner!r} is not a character", "props"))
            continue
        owner, oe = chars[p.owner]
        if not (w and oe):
            continue
        mount = w.data["mount"]
        if mount["type"] == "rig_bone":
            if p.mount != "weapon_hand" or oe.data.get("rig") != mount["rig"]:
                out.append(_e("SPEC_WEAPON_MOUNT", f"{p.asset} needs a {mount['rig']} rig with a {mount['bone']} bone; "
                                                   f"{oe.id} has rig {oe.data.get('rig')}", f"props[{p.id}]"))
            elif "weapon_hand" not in oe.data["anchors"]:
                out.append(_e("SPEC_ANCHOR", f"{oe.id} has no weapon_hand anchor", f"props[{p.id}]"))
            elif w.data["weapon_class"] not in oe.data.get("weapon_classes", []):
                out.append(_e("SPEC_WEAPON_CLASS", f"{oe.id} cannot wield a {w.data['weapon_class']} weapon",
                              f"props[{p.id}]"))
        elif mount["owner_asset"] != owner.asset:
            out.append(_e("SPEC_WEAPON_MOUNT", f"{p.asset} is integrated into {mount['owner_asset']}, not {owner.asset}",
                          f"props[{p.id}]"))

    # actions
    action_events: dict[str, dict[str, int]] = {}
    for a in spec.actions:
        field = f"actions[{a.id}]"
        ae = need(a.preset, "action", f"{field}.preset")
        if a.actor not in chars:
            out.append(_e("SPEC_UNKNOWN_SEMANTIC", f"{field}.actor {a.actor!r} is not a character", field))
            continue
        if a.target is not None and a.target not in sem:
            out.append(_e("SPEC_TARGET_MISSING", f"{field}.target {a.target!r} does not exist", field))
        _, ce = chars[a.actor]
        if not (ae and ce):
            continue
        if ae.data["actor_motion"] == "rigged" and ce.data.get("rig") != ae.data.get("requires_rig"):
            out.append(_e("SPEC_ACTION_RIG_MISMATCH", f"{a.preset} needs rig {ae.data.get('requires_rig')}; "
                                                      f"{ce.id} has {ce.data.get('rig')}", field))
            continue
        if ae.data["actor_motion"] == "static" and ce.data["motion"] != "static":
            out.append(_w("SPEC_ACTION_STATIC", f"{a.preset} is a held pose; {ce.id} is rigged", field))
        if ae.data["actor_motion"] == "rigged" and ce.data["motion"] == "static":
            out.append(_e("SPEC_ACTION_ACTOR_MOTION", f"{a.preset} needs a rigged actor; {ce.id} is static", field))
            continue
        need_cls = ae.data.get("requires_weapon_class")
        if need_cls:
            held = [p for p in spec.props if p.owner == a.actor and reg.has(p.asset, "weapon")
                    and reg.get(p.asset).data["weapon_class"] == need_cls]
            if not held:
                out.append(_e("SPEC_WEAPON_MISSING", f"{a.preset} needs {a.actor} to hold a {need_cls} weapon", field))
        for msg in act.param_errors(ae, a.params):
            out.append(_e("SPEC_PARAM", f"{field}: {msg}", field))
        if any(i.field == field and i.code == "SPEC_PARAM" for i in out):
            continue
        if spec.duration_frames < int(ae.data["frames"]) or spec.fps != int(ae.data["fps"]):
            out.append(_e("SPEC_DURATION", f"{a.preset} needs {ae.data['frames']} frames at {ae.data['fps']} fps; "
                                           f"the shot has {spec.duration_frames} at {spec.fps}", field))
        action_events[a.id] = act.resolve_events(ae, a.params)

    # authored contacts: a contact action needs its partner action on its target, with the same CONTACT frame
    for a in spec.actions:
        if a.id not in action_events:
            continue
        ae = reg.get(a.preset)
        field = f"actions[{a.id}]"
        partner_preset = ae.data.get("contact", {}).get("partner_action") or ae.data.get("partner_action")
        if not partner_preset:
            continue
        partners = [b for b in spec.actions if b.preset == partner_preset and b.actor != a.actor]
        if len(partners) != 1:
            out.append(_e("SPEC_CONTACT_PARTNER", f"{a.preset} needs exactly one {partner_preset} by another actor",
                          field))
            continue
        b = partners[0]
        if "contact" in ae.data and a.target is not None and a.target != b.actor:
            out.append(_e("SPEC_CONTACT_PARTNER", f"{a.id} targets {a.target}, but {partner_preset} is performed by "
                                                  f"{b.actor}", field))
        if b.id in action_events and action_events[a.id].get("CONTACT") != action_events[b.id].get("CONTACT"):
            out.append(_e("SPEC_SYNC_CONTACT", f"{a.id}.CONTACT (frame {action_events[a.id].get('CONTACT')}) != "
                                               f"{b.id}.CONTACT (frame {action_events[b.id].get('CONTACT')}): one "
                                               f"contact needs one frame", field))

    # events (effects)
    for ev in spec.events:
        field = f"events[{ev.id}]"
        ve = need(ev.preset, "vfx", f"{field}.preset")
        if ev.trigger.action not in action_events:
            out.append(_e("SPEC_EVENT_UNRESOLVABLE", f"{field}: trigger action {ev.trigger.action!r} does not exist "
                                                     f"or did not validate", field))
            continue
        if ev.trigger.event not in action_events[ev.trigger.action]:
            out.append(_e("SPEC_EVENT_UNRESOLVABLE", f"{field}: {ev.trigger.action} has no {ev.trigger.event} event "
                                                     f"(has {sorted(action_events[ev.trigger.action])})", field))
            continue
        frame = action_events[ev.trigger.action][ev.trigger.event] + ev.trigger.offset_frames
        if not 0 <= frame < spec.duration_frames:
            out.append(_e("SPEC_EVENT_OUTSIDE", f"{field} resolves to frame {frame}, outside the shot", field))
        if ve and ve.data["component"] in CONTACT_LAYER_COMPONENTS and (
                ev.trigger.event != "CONTACT" or ev.trigger.offset_frames != 0):
            out.append(_e("ENGINE_EFFECT_TRIGGER", f"{field}: this engine keys {ve.id} from the strike CONTACT only "
                                                   f"(no other event, no offset)", field))

    # camera
    ce = need(spec.camera.preset, "camera", "camera.preset")
    if spec.camera.target.anchor not in chars:
        out.append(_e("SPEC_CAMERA_TARGET", f"camera.target.anchor {spec.camera.target.anchor!r} is not a character",
                      "camera.target"))
    if ce:
        if spec.camera.variant and spec.camera.variant not in ce.data["variants"]:
            out.append(_e("SPEC_CAMERA_VARIANT", f"no camera variant {spec.camera.variant!r} "
                                                 f"(has {sorted(ce.data['variants'])})", "camera.variant"))
        else:
            unknown = set(spec.camera.params) - set(cam.MOVE_KEYS)
            if unknown:
                out.append(_e("SPEC_PARAM", f"camera.params: unknown {sorted(unknown)}", "camera.params"))
            move = cam.build_move(ce, spec.camera.variant, (0, 0, 0), spec.camera.params)
            for msg in cam.envelope_errors(ce, move):
                out.append(_e("SPEC_CAMERA_ENVELOPE", f"camera: {msg}", "camera"))

    need(spec.look.preset, "look", "look.preset")
    need(spec.grade.preset, "grade", "grade.preset")
    gp = need(spec.generation.profile, "generation_profile", "generation.profile")
    if gp:
        if list(spec.resolution) != list(gp.data["resolution"]):
            out.append(_e("SPEC_RESOLUTION_UNSUPPORTED", f"{gp.id} renders {gp.data['resolution']}, not "
                                                         f"{list(spec.resolution)}", "resolution"))
        if spec.duration_frames != int(gp.data["frames"]) or spec.fps != int(gp.data["fps"]):
            out.append(_e("SPEC_DURATION", f"{gp.id} generates {gp.data['frames']} frames at {gp.data['fps']} fps",
                          "duration_frames"))
    for pr in spec.protection:
        if pr.object not in sem:
            out.append(_e("SPEC_UNKNOWN_SEMANTIC", f"protection.object {pr.object!r} does not exist", "protection"))
        if pr.rule != "none":
            need(pr.rule, "protection_rule", "protection.rule")

    # placements
    if env:
        zone = env.data.get("actor_zone")
        for c, ce_ in chars.values():
            pos = c.placement.position if c.placement else (ce_.data["default_placement"]["position"] if ce_ else None)
            if zone and pos is not None and not (zone["min"][0] <= pos[0] <= zone["max"][0]
                                                 and zone["min"][1] <= pos[1] <= zone["max"][1]):
                out.append(_e("SPEC_PLACEMENT_ZONE", f"{c.id} at {list(pos)} is outside the staged actor zone",
                              f"characters[{c.id}]"))

    out += engine_issues(spec, reg)
    return out


ATTACKERS = ("asura_v2", "asura_showcase_v1")             # the builder's attacker variants (scene_build.attacker_asset)
DEFENDERS = ("ascetic_defender_v1", "ascetic_defender_v2")  # scene_build.defender_asset
# (defender asset, attacker action, defender action): what the builder can stage (build_showcase_scene.check_cast)
ENGINE_COMBOS = {("ascetic_defender_v1", "mace_slam_v1", "defender_guard_v1"),
                 ("ascetic_defender_v2", "mace_slam_v1", "defender_guard_v1"),
                 ("ascetic_defender_v2", "mace_strike_blocked_v1", "trident_parry_v1")}
ATTACK_PRESETS = ("mace_slam_v1", "mace_strike_blocked_v1")
DEFENCE_PRESETS = ("defender_guard_v1", "trident_parry_v1")


def engine_issues(spec: ShotSpec, reg: Registry) -> list[Issue]:
    """Capabilities of the current blender_showcase_v1 builder (honest limits, not general rules)."""
    out = []
    if spec.environment.asset != "temple_courtyard_v1":
        out.append(_e("ENGINE_ENVIRONMENT", "this engine builds temple_courtyard_v1 only", "environment"))
    roles = [(c.role, c.asset) for c in spec.characters]
    if len(roles) != 2 or sorted(r for r, _ in roles) != ["attacker", "defender"] or             dict(roles)["attacker"] not in ATTACKERS or dict(roles)["defender"] not in DEFENDERS:
        out.append(_e("ENGINE_CAST", f"this engine stages exactly one {' or '.join(ATTACKERS)} attacker and one "
                                     f"{' or '.join(DEFENDERS)} defender (got {roles})", "characters"))
        return out
    attackers = {c.id for c in spec.characters if c.role == "attacker"}
    defenders = {c.id for c in spec.characters if c.role == "defender"}
    att = [a for a in spec.actions if a.actor in attackers and a.preset in ATTACK_PRESETS]
    dfn = [a for a in spec.actions if a.actor in defenders and a.preset in DEFENCE_PRESETS]
    if len(att) != 1:
        out.append(_e("ENGINE_ACTION", f"this engine animates exactly one {' or '.join(ATTACK_PRESETS)} by the "
                                       f"attacker", "actions"))
    if len(dfn) != 1:
        out.append(_e("ENGINE_ACTION", f"this engine gives the defender exactly one {' or '.join(DEFENCE_PRESETS)}",
                      "actions"))
    if len(att) == 1 and len(dfn) == 1:
        combo = (dict(roles)["defender"], att[0].preset, dfn[0].preset)
        if combo not in ENGINE_COMBOS:
            out.append(_e("ENGINE_ACTION", f"this engine cannot stage {combo[0]} with {combo[1]} x {combo[2]}",
                          "actions"))
        if att[0].preset == "mace_strike_blocked_v1" and att[0].id != "strike":
            out.append(_e("ENGINE_ACTION", "this engine names the blocked strike's contact event strike.CONTACT: "
                                           "the attacker's action id must be 'strike'", "actions"))
    maces = [p for p in spec.props if p.asset == "heavy_mace_v1" and p.owner in attackers]
    if len(maces) != 1:
        out.append(_e("ENGINE_PROPS", "this engine mounts exactly one heavy_mace_v1 on the attacker", "props"))
    if dict(roles)["defender"] == "ascetic_defender_v2" and             len([p for p in spec.props if p.asset == "trident_v2" and p.owner in defenders]) != 1:
        out.append(_e("ENGINE_PROPS", "ascetic_defender_v2 holds exactly one trident_v2", "props"))
    return out
