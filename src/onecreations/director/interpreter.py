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
BLOCK_WORDS = ["block", "blocks", "blocking", "parry", "parries"]


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

    # characters by role
    chars, names = {}, {}
    for entry, alias, _pos in reg.match_aliases(text, "character"):
        for role in entry.data["roles"]:
            if role not in chars:
                chars[role] = entry.id
                proper = entry.data.get("proper_names", {})
                names[role] = proper.get(alias, entry.data["semantic_name"])
                dec.append(Decision(slot=role, choice=entry.id, source="prompt", evidence=alias))
    for role in ("attacker", "defender"):
        if role not in chars and "character" not in unsup_cats:
            entry = next(e for e in reg.of_kind("character") if role in e.data["roles"])
            chars[role], names[role] = entry.id, entry.data["semantic_name"]
            dec.append(Decision(slot=role, choice=entry.id, source="default",
                                note=f"the current engine always stages a {role}"))
            warnings.append(f"no {role} named: using {entry.id}")

    # weapons
    weapons = {}
    for entry, alias, _pos in reg.match_aliases(text, "weapon"):
        if entry.data["mount"]["type"] == "rig_bone":
            weapons["attacker"] = entry.id
            dec.append(Decision(slot="attacker.weapon", choice=entry.id, source="prompt", evidence=alias))
        else:
            dec.append(Decision(slot="defender.weapon", choice=entry.id, source="prompt", evidence=alias,
                                note="integrated into the defender asset"))
    if "attacker" in chars and "attacker" not in weapons and "weapon" not in unsup_cats:
        weapons["attacker"] = "heavy_mace_v1"
        dec.append(Decision(slot="attacker.weapon", choice="heavy_mace_v1", source="default",
                            note="the only weapon the attacker can wield"))

    # actions
    actions, params = {}, {}
    rigged = [e for e in reg.of_kind("action") if e.data["actor_motion"] == "rigged"]
    hit = [(e, a) for e in rigged for a in e.aliases if _has(text, a)]
    if "attacker" in chars and "action" not in unsup_cats:
        e = hit[0][0] if hit else rigged[0]
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
        actions["defender"] = "defender_guard_v1"
        guard = reg.get("defender_guard_v1")
        g = next((a for a in guard.aliases if _has(text, a)), None)
        dec.append(Decision(slot="defender.action", choice="defender_guard_v1", source="prompt" if g else "default",
                            evidence=g))
        if any(_has(text, w) for w in BLOCK_WORDS):
            warnings.append("a block/parry with weapon contact is not supported: the defender holds a static guard "
                            "and the mace lands beside him")

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
    if "attacker" in weapons and "attacker" in actions:
        rule = pol.preview_rule(reg, weapons["attacker"], actions["attacker"], params.get("attacker", {}))
        if rule:
            sem = reg.get(weapons["attacker"]).aliases[0].upper()
            protection[sem] = rule
            dec.append(Decision(slot="protection", choice=f"{sem} -> {rule}", source="rule", evidence="P1"))

    supported = not unsupported and env is not None and {"attacker", "defender"} <= set(chars) and \
        "attacker" in actions and look is not None
    return DirectorPlan(request=request, interpreter=INTERPRETER, supported=supported, environment=env,
                        characters=chars, semantic_names=names, weapons=weapons, actions=actions,
                        action_params=params, camera=cam_entry.id, camera_variant=variant, look=look, vfx=vfx,
                        predicted_protection=protection, decisions=dec, warnings=warnings, unsupported=unsupported)
