"""keyword_v1: the smallest useful prompt interpreter (natural-language request -> DirectorPlan).

Deterministic word/phrase matching against the registry's aliases, plus an explicit lexicon of things the current
library cannot do, so unsupported requests are refused honestly instead of silently approximated. No model, no API.
The interface (`interpret(request, registry) -> DirectorPlan`) is what an LLM-based director would implement later;
everything downstream (plan -> ShotSpec -> validate -> compile) is unchanged by that swap.
"""

from __future__ import annotations

import re

from onecreations.contracts.director import Decision, DirectorPlan
from onecreations.director import policies as pol
from onecreations.director.registry import Registry

INTERPRETER = "keyword_v1"

# Words for things the library does not have (checked as whole words). Curated, not exhaustive.
UNSUPPORTED = {
    "character": ["dragon", "robot", "horse", "wolf", "tiger", "lion", "elephant", "soldier", "knight", "samurai",
                  "ninja", "zombie", "alien", "troll", "goblin", "army", "crowd", "monkey", "hanuman", "ravana",
                  "rama", "krishna", "ganesha", "durga", "kali", "vampire", "wizard", "witch"],
    "environment": ["tokyo", "city", "street", "forest", "jungle", "ocean", "sea", "beach", "desert", "mountain",
                    "mountains", "castle", "palace", "spaceship", "space", "cave", "river", "village", "battlefield",
                    "arena", "volcano", "bridge", "rooftop"],
    "weapon": ["sword", "axe", "spear", "bow", "arrow", "gun", "rifle", "pistol", "hammer", "shield", "dagger",
               "knife", "staff", "whip", "discus", "chakram"],
    "action": ["flying", "flies", "fly", "runs", "running", "jumps", "jumping", "leaps", "dances", "dancing", "kicks",
               "punches", "shoots", "explodes", "transforms", "grabs", "wrestles", "charges",
               "duel", "fight scene", "chases"],
    "camera": ["fpv", "drone", "whip pan", "crane", "handheld", "dolly zoom", "zoom", "aerial", "tracking shot",
               "barrel roll", "close-up", "close up", "overhead", "bird's-eye", "first person", "pan", "tilt"],
    "look": ["night", "midnight", "noon", "daytime", "morning", "rain", "raining", "snow", "snowing", "storm",
             "underwater", "neon"],
    "vfx": ["explosion", "lightning", "laser", "magic", "blood", "energy beam", "fireball", "portal"],
}
SLOW_WORDS = ["slow", "slowly", "deliberate", "deliberately", "heavy, slow"]


def _role_actions(reg: Registry, role: str) -> list:
    return [e for e in reg.of_kind("action") if role in e.data.get("roles", [])]


def _performer(reg: Registry, action, current: str) -> str | None:
    """The staged character if it can perform `action`, else the first registered variant with the same role that can
    (static actions suit anyone; rigged ones need the required rig)."""
    def can(cid):
        ce = reg.get(cid)
        return action.data["actor_motion"] == "static" or ce.data.get("rig") == action.data.get("requires_rig")
    if can(current):
        return current
    role = action.data["roles"][0]
    return next((c.id for c in reg.of_kind("character") if role in c.data["roles"] and can(c.id)), None)


def _holder(reg: Registry, weapon, chars: dict) -> str | None:
    """The role whose staged character can hold `weapon` (by rig mount, or as its integrated prop)."""
    mount = weapon.data["mount"]
    for role, cid in chars.items():
        ce = reg.get(cid)
        if mount["type"] == "rig_bone" and ce.data.get("rig") == mount["rig"] or \
                mount["type"] == "integrated" and mount["owner_asset"] == cid:
            return role
    return None


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9'\- ]+", " ", text.lower()).split())


def _has(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text) is not None


def interpret(request: str, reg: Registry) -> DirectorPlan:
    text = _norm(request)
    dec: list[Decision] = []
    warnings: list[str] = []
    unsupported = [f"{cat}: '{w}' is not in the library" for cat, words in UNSUPPORTED.items()
                   for w in words if _has(text, w)]
    unsup_cats = {u.split(":")[0] for u in unsupported}

    # environment
    env = None
    m = reg.match_aliases(text, "environment")
    if m:
        env = m[0][0].id
        dec.append(Decision(slot="environment", choice=env, source="prompt", evidence=m[0][1]))
    elif "environment" not in unsup_cats:
        env = reg.of_kind("environment")[0].id
        dec.append(Decision(slot="environment", choice=env, source="default", note="no setting named; the only one"))

    # characters by role (the first named entry per role; the defender may be swapped below for a variant that can
    # perform the requested action)
    chars, names, char_dec = {}, {}, {}
    for entry, alias, _pos in reg.match_aliases(text, "character"):
        for role in entry.data["roles"]:
            if role not in chars:
                chars[role] = entry.id
                proper = entry.data.get("proper_names", {})
                names[role] = proper.get(alias, entry.data["semantic_name"])
                char_dec[role] = len(dec)
                dec.append(Decision(slot=role, choice=entry.id, source="prompt", evidence=alias))
    for role in ("attacker", "defender"):
        if role not in chars and "character" not in unsup_cats:
            entry = next(e for e in reg.of_kind("character") if role in e.data["roles"])
            chars[role], names[role] = entry.id, entry.data["semantic_name"]
            char_dec[role] = len(dec)
            dec.append(Decision(slot=role, choice=entry.id, source="default",
                                note=f"the current engine always stages a {role}"))
            warnings.append(f"no {role} named: using {entry.id}")

    # actions (role-filtered; presets without aliases are only chosen as a partner)
    actions, params = {}, {}
    if "attacker" in chars and "action" not in unsup_cats:
        att = [e for e in _role_actions(reg, "attacker") if e.aliases]
        hit = [(e, a) for e in att for a in e.aliases if _has(text, a)]
        e = hit[0][0] if hit else att[0]
        actions["attacker"] = e.id
        dec.append(Decision(slot="attacker.action", choice=e.id, source="prompt" if hit else "default",
                            evidence=hit[0][1] if hit else None))
        if not hit:
            warnings.append(f"no supported attack named: using {e.id}")
        slow = next((w for w in SLOW_WORDS if _has(text, w)), None)
        if slow:
            params["attacker"] = {"strike_frames": 9}
            dec.append(Decision(slot="attacker.action.strike_frames", choice="9", source="prompt", evidence=slow,
                                note="the M2-B retry speed (x1.5 slower downswing)"))
    if "defender" in chars:
        d_acts = _role_actions(reg, "defender")
        hit = sorted([(e, a) for e in d_acts for a in e.aliases if _has(text, a)],
                     key=lambda h: "partner_action" not in h[0].data)          # a parry beats a plain guard
        e, alias = hit[0] if hit else (next(x for x in d_acts if x.data["actor_motion"] == "static"), None)
        performer = _performer(reg, e, chars["defender"])
        if "partner_action" in e.data and (performer is None or "attacker" not in actions):
            warnings.append(f"'{alias}' needs {e.id}, which no registered defender can perform here: the defender "
                            f"holds a static guard and the mace lands beside him")
            e, alias = next(x for x in d_acts if x.data["actor_motion"] == "static"), None
            performer = chars["defender"]
        actions["defender"] = e.id
        dec.append(Decision(slot="defender.action", choice=e.id, source="prompt" if alias else "default",
                            evidence=alias))
        if performer != chars["defender"]:
            old = dec[char_dec["defender"]]
            dec[char_dec["defender"]] = Decision(slot="defender", choice=performer, source=old.source,
                                                 evidence=old.evidence,
                                                 note=f"{e.id} needs a {e.data['requires_rig']} rig: {chars['defender']} "
                                                      f"cannot perform it, {performer} is its rigged variant")
            chars["defender"] = performer
        partner = e.data.get("partner_action")
        if partner:                                    # the attacker's strike becomes the one this action stops
            actions["attacker"] = partner
            dec.append(Decision(slot="attacker.action", choice=partner, source="rule",
                                note=f"the partner of {e.id}: the strike is stopped on the defender's weapon"))
            synced = {k: params["attacker"][k] for k in e.data.get("sync_params", []) if k in params.get("attacker", {})}
            if synced:
                params["defender"] = synced
                dec += [Decision(slot=f"defender.action.{k}", choice=str(v), source="rule",
                                 note="synchronised with the attacker (one shared CONTACT)") for k, v in synced.items()]

    # weapons: a named weapon goes to the staged character that can hold it; otherwise each role's default
    weapons = {}
    for entry, alias, _pos in reg.match_aliases(text, "weapon"):
        role = _holder(reg, entry, chars)
        if role is None:
            continue                                   # a variant for an asset not staged here (e.g. trident_v1)
        if entry.data["mount"]["type"] == "rig_bone":
            weapons[role] = entry.id
            dec.append(Decision(slot=f"{role}.weapon", choice=entry.id, source="prompt", evidence=alias))
        else:
            dec.append(Decision(slot=f"{role}.weapon", choice=entry.id, source="prompt", evidence=alias,
                                note=f"integrated into the {role} asset"))
    if "attacker" in chars and "attacker" not in weapons and "weapon" not in unsup_cats:
        weapons["attacker"] = "heavy_mace_v1"
        dec.append(Decision(slot="attacker.weapon", choice="heavy_mace_v1", source="default",
                            note="the only weapon the attacker can wield"))
    d_weapon = reg.get(chars["defender"]).data.get("default_weapon") if "defender" in chars else None
    if d_weapon and "defender" not in weapons:
        weapons["defender"] = d_weapon
        dec.append(Decision(slot="defender.weapon", choice=d_weapon, source="default",
                            note=f"{chars['defender']}'s own weapon"))

    # camera
    cam_entry = reg.of_kind("camera")[0]
    c_hit = next((a for a in cam_entry.aliases if _has(text, a)), None)
    variant = "low"
    v_hit = None
    for v, words in cam_entry.data["variant_aliases"].items():
        w = next((w for w in words if _has(text, w)), None)
        if w:
            variant, v_hit = v, w
            break
    dec.append(Decision(slot="camera", choice=cam_entry.id, source="prompt" if c_hit else "default", evidence=c_hit))
    dec.append(Decision(slot="camera.variant", choice=variant, source="prompt" if v_hit else "default", evidence=v_hit))

    # look
    look = None
    lm = reg.match_aliases(text, "look")
    if lm:
        look = lm[0][0].id
        dec.append(Decision(slot="look", choice=look, source="prompt", evidence=lm[0][1]))
    elif "look" not in unsup_cats:
        look = reg.of_kind("look")[0].id
        dec.append(Decision(slot="look", choice=look, source="default"))

    # effects
    vfx = [e.id for e, alias, _ in reg.match_aliases(text, "vfx")]
    if vfx:
        dec += [Decision(slot="vfx", choice=v, source="prompt") for v in vfx]
    elif "attacker" in actions:
        vfx = list(reg.get(actions["attacker"]).data.get("default_vfx", []))
        dec += [Decision(slot="vfx", choice=v, source="default", note="the action's default impact package")
                for v in vfx]

    protection = {}
    in_contact = any("contact" in reg.get(a).data for a in actions.values())
    for role in ("attacker", "defender"):
        if role in weapons and role in actions:
            rule, label = pol.preview_rule(reg, weapons[role], actions[role], params.get(role, {}), in_contact)
            if rule:
                sem = reg.get(weapons[role]).aliases[0].upper()
                protection[sem] = rule
                dec.append(Decision(slot="protection", choice=f"{sem} -> {rule}", source="rule", evidence=label))

    supported = not unsupported and env is not None and {"attacker", "defender"} <= set(chars) and \
        "attacker" in actions and look is not None
    return DirectorPlan(request=request, interpreter=INTERPRETER, supported=supported, environment=env,
                        characters=chars, semantic_names=names, weapons=weapons, actions=actions,
                        action_params=params, camera=cam_entry.id, camera_variant=variant, look=look, vfx=vfx,
                        predicted_protection=protection, decisions=dec, warnings=warnings, unsupported=unsupported)
