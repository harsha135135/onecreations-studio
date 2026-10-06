"""Generation prompt composition from registry fragments (appearance only).

The prompt describes how things LOOK: look, environment, characters, held props, a static stance. It never describes
choreography or camera motion - those come from the authored control (the M2/M3 rule). Fragments live in the registry
so a new asset brings its own description.
"""

from __future__ import annotations

from onecreations.contracts.director import ShotSpec
from onecreations.director.registry import Registry


def compose_prompt(spec: ShotSpec, reg: Registry) -> str:
    gp = reg.get(spec.generation.profile, "generation_profile")
    look = reg.get(spec.look.preset, "look").data["prompt"]
    env = reg.get(spec.environment.asset, "environment").data["prompt"]
    by_role = {c.role: c for c in spec.characters}

    def held(role):
        c = by_role[role]
        ids = [p.asset for p in spec.props if p.owner == c.id]
        ids += [i for i in reg.get(c.asset).data.get("integrated_props", []) if reg.has(i) and i not in ids]
        return " ".join(reg.get(i, "weapon").data["prompt"] for i in ids)

    def stance(role):
        c = by_role[role]
        for a in spec.actions:
            if a.actor == c.id and "prompt" in reg.get(a.preset).data:
                return reg.get(a.preset).data["prompt"]
        return ""

    text = gp.data["prompt_template"].format(
        look_open=look["open"], env_subject=env["subject"], look_time=look["time"], env_detail=env["detail"],
        look_light=look["light"], attacker=reg.get(by_role["attacker"].asset).data["prompt"],
        attacker_weapon=held("attacker"), defender=reg.get(by_role["defender"].asset).data["prompt"],
        defender_prop=held("defender"), defender_stance=stance("defender"), look_close=look["close"],
        style=(" " + spec.generation.style.strip()) if spec.generation.style else "")
    return " ".join(text.split())
