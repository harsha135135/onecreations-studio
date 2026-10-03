"""M3-B characters (2026-10-03): finished, continuous characters for the UNCHANGED M3-A shot.

bpy + stdlib + numpy only; everything is procedural and deterministic (no sculpt files, assets or downloads).
M3-A's demon and ascetic were joined primitives (ball joints, capsule limbs, a toy proportion; M3-A section 15).
Here both are rebuilt from the oc_characters toolkit (metaball anatomy fused into one smooth mesh per body region,
swept horns / tusks / straps / locks, armour shells, folded cloth panels, smooth rest-space skinning), ON THE SAME
M2-B / M3-A RIG, KEYS AND PLACEMENT and inside the M3-A silhouettes, so the depth control, joints, ActionTimeline and
camera stay those of M3-A (the silhouette gate in silhouette_compare.py measures it against the M3-A export).

What is deliberately NOT changed: the mace (build_temple_action_scene.build_finished_mace: same geometry, materials
and passes, so the protected layer and its calibration stay comparable), object ids and pass indices (m3a_asura 1,
m3a_defender 2, m3a_mace_head 8, m3a_mace_shaft 9), the colour families the trackers rely on (crimson demon skin and
cloth, ash-blue ascetic, gold only on the mace head; no bronze, saffron or red on anything else) and the M3-A look
(environment, lights, haze, AgX).

- demon: the showcase anatomy (oc_characters torso, head and arms from build_showcase_scene) with M3-A-aligned legs
  (thighs/shins on the rig's x = +-0.25 bones), a layered crimson cloth skirt reproducing the M3-A skirt silhouette
  (flaring to r ~ 0.58 at knee height) under leather tassets and a belt, iron gorget, harness straps with an iron
  medallion, layered spiked pauldrons, leather bracers, iron greaves; horns shortened to the M3-A horn envelope.
- ascetic: the M3-A pose rebuilt as anatomy: straight stance at x = +-0.13, a wrapped dhoti over the legs to
  mid-shin, bare chest with an off-white shawl and a dark bead mala, ~7 heads tall (M3-A's head was oversized), a
  bearded face, matted jata bun with locks, both hands ON the trident shaft (M3-A's hands floated beside it); the
  trident keeps the M3-A diagonal (28 deg, in front at y = -0.5).
"""

from __future__ import annotations

import math
import random

import bpy
import numpy as np
from mathutils import Vector

import build_showcase_scene as sc
import build_temple_action_scene as action
import build_temple_shot_scene as temple
import build_temple_strike_scene as strike
import oc_characters as ch
import oc_lookdev as lk

SKINNING: dict = {}                     # weight sanity per skinned body, written to the spec by build_m3b_scene
_MATERIALS: dict = {}                   # built once per scene (shared by both characters)

# M3-A-aligned legs: hips over the rig's thigh bones (x = +-0.25), straight stance, feet toward -Y (the camera).
LEG = {s: {"hip": (s * 0.22, 0.02, 1.06), "knee": (s * 0.26, -0.05, 0.57), "ankle": (s * 0.27, 0.0, 0.12)}
       for s in (1, -1)}

# The M3-A ascetic's trident: a 2.3 m shaft centred at (0, -0.5, 1.15), tilted 28 deg about Y (prongs up at +X).
TRIDENT_TILT = math.radians(28.0)
TRIDENT_CENTRE, TRIDENT_LEN = Vector((0.0, -0.5, 1.15)), 2.3
TRIDENT_DIR = Vector((math.sin(TRIDENT_TILT), 0.0, math.cos(TRIDENT_TILT)))


def materials(lmat: dict) -> dict:
    """Character materials in the M3-A colours (validated tracking families), with the sculpt-oriented shaders
    (cavity AO, worn edges, gradient horn). The mace keeps lmat["gold"] / ["iron"] / ["leather"] unchanged."""
    if _MATERIALS.get("lmat") is lmat:
        return _MATERIALS["m"]
    _MATERIALS.update(lmat=lmat, m={
        "skin": lk.creature_skin("m3b_asura_skin", base=(0.55, 0.05, 0.035), dark=(0.30, 0.02, 0.015),
                                 cavity=(0.10, 0.012, 0.01)),
        "cloth": lk.cloth("m3b_asura_cloth", (0.26, 0.025, 0.02), weave=110.0, sheen=0.3, folds=6.0),
        "iron": lk.worn_metal("m3b_iron", (0.20, 0.185, 0.175), wear=(0.50, 0.48, 0.45)),
        "leather": lk.cloth("m3b_leather", (0.12, 0.06, 0.03), weave=40.0, sheen=0.1),
        "horn": lk.gradient_bone("m3b_horn", root=(0.12, 0.09, 0.07), tip=(0.80, 0.74, 0.60)),
        "tusk": lk.gradient_bone("m3b_tusk", root=(0.62, 0.55, 0.42), tip=(0.90, 0.86, 0.74)),
        "eye": lmat["eye"],
        "hair": lmat["hair"],
        "ash_skin": lk.creature_skin("m3b_ascetic_skin", base=(0.26, 0.40, 0.56), dark=(0.16, 0.25, 0.36),
                                     cavity=(0.10, 0.12, 0.16), sss_radius=(0.4, 0.5, 1.0), sss=0.2),
        "white_cloth": lmat["white_cloth"],
        "shawl": lk.cloth("m3b_shawl", (0.66, 0.62, 0.55), weave=90.0, sheen=0.3, folds=5.0),
        "beads": lmat["beads"],
        "trident": lk.worn_metal("m3b_trident_iron", (0.22, 0.21, 0.20), wear=(0.55, 0.53, 0.50), rough=(0.25, 0.45)),
    })
    return _MATERIALS["m"]


# --- the demon -------------------------------------------------------------------------------------------------

def leg_elements() -> list[dict]:
    e, b = ch.ell, ch.ball
    out = []
    for s, j in LEG.items():
        hip, knee, ankle = Vector(j["hip"]), Vector(j["knee"]), Vector(j["ankle"])
        out += ch.limb(hip, knee, 0.16, 0.11)
        out += [e(tuple(hip.lerp(knee, 0.45) + Vector((0, -0.06, 0))), (0.19, 0.10, 0.10), axis=knee - hip),  # quad
                b(tuple(knee + Vector((0, -0.05, 0))), 0.075)]                                              # knee
        out += ch.limb(knee, ankle, 0.10, 0.062)
        out += [e(tuple(knee.lerp(ankle, 0.35) + Vector((0, 0.05, 0))), (0.09, 0.095, 0.15)),             # calf
                e((ankle.x, -0.12, 0.06), (0.085, 0.17, 0.055)),                                          # foot
                b((ankle.x, 0.04, 0.07), 0.065)]                                                          # heel
        for dx in (-0.04, 0.0, 0.04):
            out.append(b((ankle.x + s * dx, -0.29, 0.04), 0.032))                                         # toes
    return out


def head_details(m) -> list:
    """Horns (inside the M3-A horn envelope), tusks, ears, eyes, topknot and mane locks; rigid to the chest."""
    out = []
    for s in (1, -1):
        out.append(ch.tube(f"m3b_horn{s}", [(s * 0.12, -0.03, 2.60), (s * 0.28, 0.0, 2.72), (s * 0.38, -0.03, 2.89),
                                            (s * 0.38, -0.10, 3.04)], [0.072, 0.058, 0.036, 0.0], m["horn"], ring=18))
        out.append(ch.tube(f"m3b_tusk{s}", [(s * 0.085, -0.17, 2.30), (s * 0.10, -0.235, 2.37), (s * 0.13, -0.25, 2.44)],
                           [0.022, 0.015, 0.0], m["tusk"], ring=12))
        out.append(ch.tube(f"m3b_ear{s}", [(s * 0.17, 0.02, 2.46), (s * 0.23, 0.05, 2.50), (s * 0.28, 0.08, 2.56)],
                           [0.045, 0.03, 0.0], m["skin"], ring=12, flat=0.45))
        out.append(ch.metaball_mesh(f"m3b_eye{s}", [ch.ell((s * 0.07, -0.185, 2.48), (0.026, 0.012, 0.016))], m["eye"],
                                    resolution=0.004, smooth_iters=0))
    out.append(ch.metaball_mesh("m3b_topknot", [ch.ell((0, 0.08, 2.70), (0.09, 0.09, 0.09)),
                                                ch.ell((0, 0.09, 2.78), (0.06, 0.06, 0.06))], m["hair"], resolution=0.01))
    out.append(ch.tube("m3b_knotring", [(0, 0.06, 2.72), (0, 0.11, 2.74)], [0.07, 0.07], m["iron"], ring=16))
    rng = random.Random(5)
    for k in range(7):                                           # mane locks down the upper back
        a = -0.5 + k / 6.0
        x0, x1 = a * 0.26, a * 0.42
        out.append(ch.tube(f"m3b_lock{k}", [(x0 * 0.8, 0.12, 2.62), (x0, 0.21, 2.45),
                                            (x1, 0.25 + rng.uniform(0, 0.03), 2.22),
                                            (x1 * 1.1, 0.24 + rng.uniform(0, 0.04), 2.02 - rng.uniform(0, 0.08))],
                           [0.045, 0.04, 0.03, 0.0], m["hair"], ring=10))
    return out


def chest_harness(m, torso) -> list:
    """Iron gorget, crossing leather straps fitted to the torso surface, an iron medallion and boss."""
    out = [ch.tube("m3b_gorget", sc.ring_path(torso, 2.22, 0.03, n=20), [0.05] * 21, m["iron"], ring=12, flat=0.55)]
    for s in (1, -1):                                            # shoulder -> opposite hip
        pts = [sc.hit_front(torso, s * x, z, 0.022) for x, z in ((0.34, 2.10), (0.21, 1.93), (0.0, 1.74),
                                                                 (-0.19, 1.54), (-0.29, 1.38))]
        pts = [sc.hit_down(torso, s * 0.37, 0.02, 0.02)] + pts
        out.append(ch.tube(f"m3b_strap{s}", pts, [0.05] * len(pts), m["leather"], ring=10, flat=0.3,
                           up=(0.0, -1.0, 0.0)))
    mc = sc.hit_front(torso, 0.0, 1.74, 0.03)
    out.append(ch.tube("m3b_medallion", [(0, mc[1] + 0.02, 1.74), (0, mc[1] - 0.03, 1.74)], [0.085, 0.075],
                       m["iron"], ring=24))
    out.append(ch.metaball_mesh("m3b_boss", [ch.ell((0, mc[1] - 0.04, 1.74), (0.04, 0.025, 0.04))], m["iron"],
                                resolution=0.006, smooth_iters=1))
    return out


def skirt_and_belt(m, torso) -> list:
    """Layered crimson cloth skirt (the M3-A skirt silhouette: from the waist to knee height, flaring to r ~ 0.58),
    leather tassets over the front and sides, a leather belt and an iron buckle plate; rigid to the pelvis."""
    out = [ch.tube("m3b_belt", sc.ring_path(torso, 1.33, 0.025, n=24), [0.06] * 25, m["leather"], ring=12, flat=0.4)]
    n = 10
    for k in range(n):                                           # overlapping radial panels, alternating layers
        ang = 2 * math.pi * (k + 0.5) / n - math.pi / 2           # k = 0 .. faces -Y first
        d = Vector((math.cos(ang), math.sin(ang), 0.0))
        lift = 0.012 if k % 2 else 0.0
        top = sc.hit_radial(torso, ang, 1.31, 0.015 + lift)
        bottom = (d.x * (0.57 + lift), d.y * (0.57 + lift), 0.56 + (0.03 if k % 2 else 0.0))
        out.append(ch.cloth_panel(f"m3b_skirt{k}", top, bottom, 0.23, 0.42, m["cloth"], folds=2, depth=0.02,
                                  facing=tuple(d), thickness=0.012))
    for k, ang in enumerate((-0.95, -0.55, -0.15, 0.25, 0.65)):  # leather tassets, front and sides (angle from -Y)
        a = ang - math.pi / 2
        d = Vector((math.cos(a), math.sin(a), 0.0))
        top = sc.hit_radial(torso, a, 1.27, 0.05)
        out.append(ch.cloth_panel(f"m3b_tasset{k}", top, (top[0] + d.x * 0.12, top[1] + d.y * 0.12, 0.90),
                                  0.15, 0.18, m["leather"], folds=1, depth=0.006, facing=tuple(d), thickness=0.02))
    bf = sc.hit_front(torso, 0.0, 1.33, 0.07)
    out.append(lk.rounded_box((0.20, 0.05, 0.16), bf, m["iron"], bevel=0.02, subdiv=1))
    return out


def leg_armour(m) -> list:
    out = []
    for s, j in LEG.items():
        knee, ankle = Vector(j["knee"]), Vector(j["ankle"])
        shin = [knee.lerp(ankle, t) + Vector((0, -0.025, 0)) for t in (0.10, 0.5, 0.88)]
        out.append(ch.tube(f"m3b_greave{s}", [tuple(p) for p in shin], [0.112, 0.098, 0.082], m["iron"], ring=16))
        out.append(ch.tube(f"m3b_anklet{s}", [(ankle.x, -0.01, 0.15), (ankle.x, -0.01, 0.10)], [0.082, 0.082],
                           m["leather"], ring=16))
    return out


def arm_armour(m, side: str, s: int) -> tuple[list, list]:
    """Layered spiked pauldron + iron arm band (upper arm) and a leather bracer with an iron band (forearm)."""
    x = s * 0.68
    upper = [ch.shell(f"m3b_pauldron{side}{k}", (x + s * dx, 0.0, z), semi, m["iron"], cut=-0.25, thickness=0.03,
                      rot_deg=(0, s * tilt, 0))
             for k, (dx, z, semi, tilt) in enumerate(((0.0, 2.11, (0.26, 0.25, 0.17), 18),
                                                      (0.06, 2.01, (0.24, 0.235, 0.14), 34),
                                                      (0.11, 1.92, (0.21, 0.22, 0.12), 50)))]
    for k, dy in enumerate((-0.11, 0.0, 0.11)):                  # spikes along the top plate
        base = Vector((x + s * 0.03, dy, 2.24))
        tip = base + Vector((s * 0.12, dy * 0.4, 0.17))
        upper.append(ch.tube(f"m3b_spike{side}{k}", [tuple(base), tuple(base.lerp(tip, 0.5)), tuple(tip)],
                             [0.045, 0.026, 0.0], m["iron"], ring=10))
    upper.append(ch.tube(f"m3b_armband{side}", [(x, 0, 1.78), (x, 0, 1.72)], [0.135, 0.135], m["iron"], ring=20))
    fore = [ch.tube(f"m3b_bracer{side}", [(x, -0.01, 1.42), (x, -0.01, 1.28), (x, 0.0, 1.16)],
                    [0.118, 0.105, 0.088], m["leather"], ring=18),
            ch.tube(f"m3b_bracerband{side}", [(x, -0.01, 1.35), (x, -0.01, 1.32)], [0.122, 0.122], m["iron"], ring=18)]
    return upper, fore


def build_asura(lmat: dict, rig):
    """The finished demon (m3a_asura, pass 1) on the unchanged M3-A rig, plus the unchanged M3-A mace."""
    m = materials(lmat)
    torso = ch.metaball_mesh("m3b_asura_torso", sc.torso_core_elements() + sc.head_elements() + leg_elements(),
                             m["skin"], resolution=0.016)
    zc = ch.vertex_coords(torso)[:, 2]
    ch.assign_weights(torso, ch.chain_weights(zc, [(1.42, 1.72, "pelvis", "chest")]))   # legs: pelvis (stationary)
    parts = [torso]
    for s, side in ((1, "L"), (-1, "R")):
        arm = ch.metaball_mesh(f"m3b_asura_arm{side}", sc.arm_elements(s), m["skin"], resolution=0.014)
        z = ch.vertex_coords(arm)[:, 2]
        stops = ([(1.06, 1.12, "mace", f"forearm.{side}")] if side == strike.WEAPON_SIDE else []) + \
                [(1.50, 1.62, f"forearm.{side}", f"upper_arm.{side}")]
        ch.assign_weights(arm, ch.chain_weights(z, stops))       # the weapon fist follows the mace bone (grip wraps)
        parts.append(arm)
    chest = head_details(m) + chest_harness(m, torso)
    hips = skirt_and_belt(m, torso) + leg_armour(m)
    for o in chest:
        ch.rigid(o, "chest")
    for o in hips:
        ch.rigid(o, "pelvis")
    parts += chest + hips
    for s, side in ((1, "L"), (-1, "R")):
        upper, fore = arm_armour(m, side, s)
        for o in upper:
            ch.rigid(o, f"upper_arm.{side}")
        for o in fore:
            ch.rigid(o, f"forearm.{side}")
        parts += upper + fore
    body = temple.join(parts, "m3a_asura")
    temple.set_origin(body, (0.0, 0.0, 0.0))
    SKINNING["m3a_asura"] = ch.weight_stats(body)
    ch.bind(body, rig)
    temple.tag(body, "m3a_asura", 1)
    shaft, head = action.build_finished_mace(lmat, rig)
    return body, shaft, head


# --- the ascetic (static) --------------------------------------------------------------------------------------

def trident_point(t: float) -> Vector:
    """A point on the M3-A trident shaft, t in [-0.5, 0.5] of its length from the centre (+ = prongs)."""
    return TRIDENT_CENTRE + TRIDENT_DIR * (t * TRIDENT_LEN)


def build_defender(lmat: dict):
    """The finished ascetic (~2.2 m) in the M3-A pose; built facing -Y like M3-A (the scene turns it to face -X)."""
    m = materials(lmat)
    e, b = ch.ell, ch.ball
    legs = {s: {"hip": (s * 0.12, 0.0, 0.95), "knee": (s * 0.13, -0.03, 0.52), "ankle": (s * 0.13, 0.0, 0.10)}
            for s in (1, -1)}
    core = [e((0, 0, 1.00), (0.21, 0.15, 0.13)), e((0, 0, 1.17), (0.19, 0.13, 0.12)),          # pelvis, waist
            e((0, -0.04, 1.30), (0.18, 0.12, 0.13)), e((0, 0.0, 1.47), (0.27, 0.16, 0.19)),   # abdomen, ribcage
            e((0, 0.06, 1.50), (0.23, 0.08, 0.18)),                                             # back
            e((0, 0.0, 1.74), (0.065, 0.065, 0.07)),                                            # neck
            e((0, 0.01, 1.96), (0.115, 0.13, 0.135)),                                           # cranium
            e((0, -0.05, 1.88), (0.09, 0.085, 0.065)),                                          # jaw
            e((0, -0.125, 1.93), (0.022, 0.03, 0.035)),                                         # nose
            e((0, -0.10, 1.99), (0.095, 0.03, 0.025))]                                          # brow
    for s in (1, -1):
        core += [b((s * 0.042, -0.11, 1.955), 0.022, negative=True),                           # eye sockets
                 e((s * 0.06, -0.09, 1.91), (0.04, 0.035, 0.03)),                               # cheeks
                 e((s * 0.11, -0.11, 1.55), (0.12, 0.065, 0.085)),                              # pectorals
                 e((s * 0.25, 0.0, 1.62), (0.10, 0.10, 0.09)),                                  # shoulders
                 e((s * 0.12, 0.04, 1.69), (0.11, 0.08, 0.05), rot_deg=(0, s * 18, 0)),         # trapezius
                 e((s * 0.125, 0.0, 1.97), (0.02, 0.035, 0.045))]                               # ears
    fit = ch.metaball_mesh("m3b_def_fit", core, m["ash_skin"], resolution=0.012)      # torso-only fitting surface
    els = list(core)
    hands = {1: trident_point(0.30), -1: trident_point(0.08)}    # both hands on the shaft (within arm reach)
    for s in (1, -1):
        j = legs[s]
        els += ch.limb(j["hip"], j["knee"], 0.11, 0.08) + ch.limb(j["knee"], j["ankle"], 0.07, 0.048)
        els += [e((j["ankle"][0], j["ankle"][1] - 0.08, 0.04), (0.055, 0.12, 0.04))]                 # feet
        shoulder = Vector((s * 0.25, -0.02, 1.62))
        elbow = sc.two_bone(shoulder, hands[s], 0.34, 0.33, (s * 0.8, 0.3, -0.6))
        els += ch.limb(shoulder, elbow, 0.072, 0.056) + ch.limb(elbow, hands[s], 0.056, 0.04)
        els += [b(tuple(hands[s] + Vector((0, 0.03, 0))), 0.048)]                                      # fists
    body = ch.metaball_mesh("m3b_def_body", els, m["ash_skin"], resolution=0.012)

    cloth = []
    dhoti = [e((0, 0, 1.0), (0.235, 0.19, 0.16))]                # wrapped dhoti over the legs to mid-shin
    for s in (1, -1):
        knee, ank = Vector(legs[s]["knee"]), Vector(legs[s]["ankle"])
        dhoti += ch.limb(legs[s]["hip"], knee, 0.15, 0.13) + ch.limb(knee, knee.lerp(ank, 0.45), 0.13, 0.115)
    cloth.append(ch.metaball_mesh("m3b_dhoti", dhoti, m["white_cloth"], resolution=0.012))
    cloth.append(ch.cloth_panel("m3b_pleats", (0, -0.17, 1.08), (0.0, -0.25, 0.36), 0.24, 0.32, m["white_cloth"],
                                folds=5, depth=0.016))
    cloth.append(ch.tube("m3b_waistcord", sc.ring_path(cloth[0], 1.10, 0.02, n=20), [0.025] * 21, m["beads"],
                         ring=8))
    sh = [sc.hit_front(fit, x, z, 0.02) for x, z in ((0.18, 1.62), (0.08, 1.50), (-0.06, 1.36), (-0.16, 1.22))]
    cloth.append(ch.tube("m3b_shawl", [(0.22, 0.05, 1.71)] + sh + [(-0.22, 0.02, 1.14)], [0.085] * 6, m["shawl"],
                         ring=10, flat=0.25, up=(0.0, -1.0, 0.0)))
    beads = [sc.hit_front(fit, 0.11 * math.cos(a), 1.70 - 0.16 * math.sin(a), 0.012) for a in np.linspace(0.15, 2.99, 9)]
    cloth.append(ch.tube("m3b_mala", [(0.10, 0.02, 1.72)] + beads + [(-0.10, 0.02, 1.72)], [0.016] * 11,
                         m["beads"], ring=8))
    for s in (1, -1):
        cloth.append(ch.metaball_mesh(f"m3b_def_eye{s}", [e((s * 0.042, -0.105, 1.955), (0.014, 0.006, 0.008))],
                                      m["hair"], resolution=0.003, smooth_iters=0))
    hair = [ch.metaball_mesh("m3b_jata", [e((0, 0.03, 2.13), (0.10, 0.10, 0.07)), e((0, 0.04, 2.21), (0.075, 0.075, 0.06)),
                                          e((0, 0.04, 2.28), (0.05, 0.05, 0.05)), e((0, 0.05, 2.05), (0.125, 0.11, 0.05))],
                             m["hair"], resolution=0.008),
            ch.metaball_mesh("m3b_beard", [e((0, -0.09, 1.84), (0.075, 0.05, 0.07)), e((0, -0.10, 1.78), (0.05, 0.04, 0.05))],
                             m["hair"], resolution=0.006)]
    rng = random.Random(9)
    for k in range(9):                                           # matted locks down the back
        a = -0.5 + k / 8.0
        hair.append(ch.tube(f"m3b_dlock{k}", [(a * 0.20, 0.07, 2.02), (a * 0.26, 0.15, 1.86),
                                              (a * 0.30 + rng.uniform(-0.02, 0.02), 0.17, 1.66),
                                              (a * 0.32, 0.15 + rng.uniform(0, 0.04), 1.48 + rng.uniform(0, 0.06))],
                            [0.03, 0.026, 0.018, 0.0], m["hair"], ring=8))
    butt, top = trident_point(-0.5), trident_point(0.5) - TRIDENT_DIR * 0.30
    side_v = TRIDENT_DIR.cross(Vector((0, 1, 0))).normalized()
    tri = [ch.tube("m3b_tri_shaft", [tuple(butt), tuple(top)], [0.024, 0.024], m["trident"], ring=12),
           ch.tube("m3b_tri_collar", [tuple(top - TRIDENT_DIR * 0.04), tuple(top + TRIDENT_DIR * 0.02)], [0.04, 0.04],
                   m["trident"], ring=12),
           ch.tube("m3b_tri_bar", [tuple(top - side_v * 0.16), tuple(top + side_v * 0.16)], [0.018, 0.018],
                   m["trident"], ring=8),
           ch.tube("m3b_tri_mid", [tuple(top), tuple(top + TRIDENT_DIR * 0.30)], [0.022, 0.0], m["trident"], ring=10)]
    for s in (1, -1):
        p0 = top + side_v * s * 0.16
        tri.append(ch.tube(f"m3b_tri_side{s}", [tuple(p0), tuple(p0 + side_v * s * 0.05 + TRIDENT_DIR * 0.13),
                                                  tuple(p0 + side_v * s * 0.01 + TRIDENT_DIR * 0.30)],
                           [0.018, 0.012, 0.0], m["trident"], ring=10))
    bpy.data.objects.remove(fit, do_unlink=True)
    obj = temple.join([body] + cloth + hair + tri, "m3a_defender")
    temple.set_origin(obj, (0.0, 0.0, 0.0))
    return obj
