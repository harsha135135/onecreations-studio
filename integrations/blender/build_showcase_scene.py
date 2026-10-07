"""Build SHOWCASE v1 (2026-10-03): the best controlled cinematic action shot the system can make today.

    blender -b --factory-startup --python build_showcase_scene.py -- --out showcase.blend --spec shot_spec.json

D1 (2026-10-06): --config scene_build.json (from the director's CompiledShot) overrides the module constants below
(placements, camera move, look, strike timing, effect components, layer manifest, ids). Without --config the build
is exactly SHOWCASE v1.

THIS IS A SHOWCASE OPTIMISATION SCENE, NOT AN ADMISSION EXPERIMENT: characters, look, lighting, framing, resolution and
effects all change together, chosen for final visual quality. Control is kept, not re-tested:
- the M2-B rig and its strike keys verbatim (original speed, the M3-A ActionTimeline phases), root fixed; the rig is
  turned 30 deg toward the defender (root yaw only; the strike stays a sideways arc in the image)
- an M2-C / M3-A-family camera move (look-at orbit + push-in, fixed lens), recomposed for 768x448 (aspect 1.714)
- depth, object index, joints, camera and the finished first frame all come from this one scene, so they align
Characters are continuous (oc_characters): metaball anatomy -> one smooth mesh per body region, swept horns / tusks /
straps / locks, armour shells and cloth panels, smooth rest-space weights (pelvis / chest / arm chains; the weapon
fist follows the mace bone so the grip always wraps the shaft). The defender is static (no rig).
- sc_asura (pass 1), sc_defender (2), sc_mace_head (8, aged gold: the only gold object), sc_mace_shaft (9)
- environment: the M2-A temple re-surfaced and upgraded (beams, capitals, shikhara finial, braziers with fire,
  lit sanctum doorway, dark cloth banners instead of diagnostic colour landmarks)
- fx_impact collection (dust volumes, debris, sparks, floor cracks) and fx_flash (impact light), both excluded from
  the main view layer and rendered only as composite layers (render_layers.py), triggered by the ActionTimeline.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import build_temple_camera_scene as camscene  # noqa: E402
import build_temple_shot_scene as temple  # noqa: E402
import build_temple_strike_scene as strike  # noqa: E402
import oc_blender_common as common  # noqa: E402
import oc_characters as ch  # noqa: E402
import oc_import_camera  # noqa: E402
import oc_lookdev as lk  # noqa: E402
from onecreations import hashing  # noqa: E402

FRAMES, FPS = temple.FRAMES, temple.FPS
RES = (768, 448)
ROOT_AT = list(strike.ROOT_AT)
ASURA_YAW_DEG = 30.0                                  # turned toward the defender (rig root yaw only)
DEFENDER_AT, DEFENDER_YAW_DEG, DEFENDER_SCALE = [0.70, -3.55, 0.0], -65.0, 1.08
CAMERA_MOVE = {"target": [-0.5, -3.9, 1.5], "azimuth_deg": [-14.0, 10.0], "radius_m": [7.6, 6.3],
               "height_m": [2.25, 1.95], "ease_linear_mix": 0.5, "yaw_offset_deg": 0.0, "lens_mm": 32.0,
               "sensor_mm": 36.0, "sensor_fit": "AUTO", "clip_start": 0.1, "clip_end": 300.0}
MIN_CLEARANCE_M = 1.0
STRIKE_FRAMES = strike.DEFAULT_STRIKE_FRAMES
SUN = {"elevation_deg": 22.0, "heading_deg": 150.3, "energy": 4.2, "color": (1.0, 0.55, 0.28)}
SKINNING: dict = {}                                   # filled by build_asura (weight sanity, written to the spec)
SHOT_ID, TIMELINE_ID = "showcase_v1", "sc_mace_slam_v1"
TIMELINE_ACTORS = {"asura": "sc_asura", "defender": "sc_defender"}
FX = {"components": ["dust", "debris", "sparks", "cracks"], "flash": True, "seed": 23, "dust_density": 1.6,
      "dust_decay_s": 0.6, "flash_energy_w": [2200.0, 1100.0, 420.0, 140.0, 40.0]}
FX_KINDS = {"dust": ("plume", "ring"), "debris": ("chip",), "sparks": ("spark",), "cracks": ("crack",)}
LAYERS = None                                         # compiled CompositeManifest (dict); None: layers_manifest()
ATTACKER_ASSET = "asura_showcase_v1"                  # D2: "asura_v2" builds the upgraded character
DEFENDER_ASSET = "ascetic_defender_v1"                # D3: "ascetic_defender_v2" is rigged, trident separate
ATTACKER_ACTION, DEFENDER_ACTION = "mace_slam_v1", "defender_guard_v1"   # D3: mace_strike_blocked_v1 x trident_parry_v1
CONTACT: dict = {}                                    # filled by the parry build: the solved weapon-on-weapon contact


def apply_config(cfg: dict) -> None:
    """Apply a compiled scene_build configuration (D1). Unknown keys are errors: the compiler and this builder must
    agree on the interface."""
    global RES, ROOT_AT, ASURA_YAW_DEG, DEFENDER_AT, DEFENDER_YAW_DEG, DEFENDER_SCALE, CAMERA_MOVE, SUN, STRIKE_FRAMES
    global SHOT_ID, TIMELINE_ID, TIMELINE_ACTORS, LAYERS, ATTACKER_ASSET, DEFENDER_ASSET, ATTACKER_ACTION
    global DEFENDER_ACTION
    known = {"engine", "shot_id", "timeline_id", "timeline_actors", "frames", "fps", "resolution", "root_at",
             "asura_yaw_deg", "defender_at", "defender_yaw_deg", "defender_scale", "camera_move", "sun", "look",
             "strike_frames", "fx", "layers", "attacker_asset", "material_index_pass", "defender_asset",
             "attacker_action", "defender_action"}
    unknown = set(cfg) - known
    if unknown:
        raise ValueError(f"scene_build: unknown keys {sorted(unknown)}")
    if cfg.get("frames", FRAMES) != FRAMES or cfg.get("fps", FPS) != FPS:
        raise ValueError(f"this engine builds {FRAMES} frames at {FPS} fps only")
    RES = tuple(cfg.get("resolution", RES))
    ROOT_AT = list(cfg.get("root_at", ROOT_AT))
    ASURA_YAW_DEG = cfg.get("asura_yaw_deg", ASURA_YAW_DEG)
    DEFENDER_AT = list(cfg.get("defender_at", DEFENDER_AT))
    DEFENDER_YAW_DEG = cfg.get("defender_yaw_deg", DEFENDER_YAW_DEG)
    DEFENDER_SCALE = cfg.get("defender_scale", DEFENDER_SCALE)
    CAMERA_MOVE = dict(cfg.get("camera_move", CAMERA_MOVE))
    SUN = dict(cfg.get("sun", SUN))
    LOOK.update(cfg.get("look", {}))
    STRIKE_FRAMES = int(cfg.get("strike_frames", STRIKE_FRAMES))
    FX.update(cfg.get("fx", {}))
    SHOT_ID = cfg.get("shot_id", SHOT_ID)
    TIMELINE_ID = cfg.get("timeline_id", TIMELINE_ID)
    TIMELINE_ACTORS = dict(cfg.get("timeline_actors", TIMELINE_ACTORS))
    LAYERS = cfg.get("layers")
    ATTACKER_ASSET = cfg.get("attacker_asset", ATTACKER_ASSET)
    if ATTACKER_ASSET not in ("asura_showcase_v1", "asura_v2"):
        raise ValueError(f"this engine builds asura_showcase_v1 or asura_v2, not {ATTACKER_ASSET}")
    DEFENDER_ASSET = cfg.get("defender_asset", DEFENDER_ASSET)
    ATTACKER_ACTION = cfg.get("attacker_action", ATTACKER_ACTION)
    DEFENDER_ACTION = cfg.get("defender_action", DEFENDER_ACTION)
    check_cast()


def check_cast() -> None:
    """The engine's supported combinations (the director's engine_issues mirror these)."""
    combos = {("ascetic_defender_v1", "mace_slam_v1", "defender_guard_v1"),
              ("ascetic_defender_v2", "mace_slam_v1", "defender_guard_v1"),
              ("ascetic_defender_v2", "mace_strike_blocked_v1", "trident_parry_v1")}
    if (DEFENDER_ASSET, ATTACKER_ACTION, DEFENDER_ACTION) not in combos:
        raise ValueError(f"this engine cannot build {DEFENDER_ASSET} with {ATTACKER_ACTION} x {DEFENDER_ACTION}")


def parry() -> bool:
    return DEFENDER_ACTION == "trident_parry_v1"
LOOK = {"sun": 3.2, "fill": 220.0, "firekey": 700.0, "coolrim": 1500.0, "fire": 420.0, "sanctum": 90.0,
        "world": 0.15, "haze": 0.005, "exposure": -0.7, "look": "AgX - High Contrast",
        "fire_emission": 1.8, "door_emission": 0.3, "fill_color": (0.40, 0.55, 1.0), "skin": (0.19, 0.022, 0.017), "skin_dark": (0.065, 0.008, 0.006)}


# --- palette ---------------------------------------------------------------------------------------------------

def materials() -> dict:
    return {
        "skin": lk.creature_skin("sc_asura_skin", base=LOOK["skin"], dark=LOOK["skin_dark"],
                                 cavity=(0.04, 0.006, 0.006)),
        "iron": lk.worn_metal("sc_iron", (0.075, 0.07, 0.068), wear=(0.42, 0.40, 0.38)),
        "bronze": lk.worn_metal("sc_bronze", (0.30, 0.17, 0.07), wear=(0.62, 0.45, 0.25), rough=(0.25, 0.45)),
        "gold": lk.worn_metal("sc_gold", (0.80, 0.55, 0.18), wear=(1.0, 0.85, 0.55), rough=(0.18, 0.35), grime=0.35),
        "leather": lk.cloth("sc_leather", (0.07, 0.035, 0.02), weave=35.0, sheen=0.12),
        "loincloth": lk.cloth("sc_loincloth", (0.10, 0.03, 0.025), sheen=0.3),
        "horn": lk.gradient_bone("sc_horn", root=(0.06, 0.045, 0.035), tip=(0.78, 0.70, 0.56)),
        "tusk": lk.gradient_bone("sc_tusk", root=(0.55, 0.48, 0.36), tip=(0.92, 0.88, 0.78)),
        "eye": lk.plain("sc_eye", (1.0, 0.6, 0.1), 0.3, emission=(1.0, 0.55, 0.08), strength=14.0),
        "hair": lk.plain("sc_hair", (0.015, 0.012, 0.01), 0.45),
        "ash_skin": lk.creature_skin("sc_ash_skin", base=(0.20, 0.28, 0.40), dark=(0.10, 0.15, 0.24),
                                     cavity=(0.10, 0.11, 0.13), sss_radius=(0.5, 0.6, 0.9), sss=0.2),
        "white_cloth": lk.cloth("sc_white", (0.56, 0.52, 0.45), sheen=0.25),
        "shawl": lk.cloth("sc_shawl", (0.40, 0.38, 0.35), sheen=0.3),
        "sash": lk.cloth("sc_sash", (0.36, 0.13, 0.035), sheen=0.3),
        "beads": lk.plain("sc_beads", (0.06, 0.035, 0.025), 0.5),
        "steel": lk.worn_metal("sc_steel", (0.50, 0.50, 0.52), wear=(0.8, 0.8, 0.82), rough=(0.18, 0.32), grime=0.55),
        "moon": lk.plain("sc_moon", (0.85, 0.85, 0.80), 0.3, emission=(0.8, 0.85, 1.0), strength=1.5),
        "stone": lk.stone("sc_stone", a=(0.40, 0.33, 0.26), b=(0.20, 0.16, 0.13), scale=3.0, dirt=0.4),
        "pillar": lk.stone("sc_pillar", a=(0.42, 0.35, 0.27), b=(0.22, 0.18, 0.14), fluting=9.0, dirt=0.4),
        "shrine": lk.stone("sc_shrine", a=(0.38, 0.31, 0.24), b=(0.18, 0.15, 0.12), scale=5.0, dirt=0.35),
        "floor": lk.flagstones("sc_floor"),
        "door": lk.plain("sc_door", (0.05, 0.02, 0.01), 0.9, emission=(1.0, 0.36, 0.10),
                         strength=LOOK["door_emission"]),
        "fire": lk.fire("sc_fire", color=(1.0, 0.22, 0.02), core=(1.0, 0.48, 0.10), strength=LOOK["fire_emission"],
                        scale=5.0, mask=(0.0, 0.32)),
        "coal": lk.plain("sc_coal", (0.03, 0.01, 0.005), 0.8, emission=(1.0, 0.2, 0.03), strength=3.0),
        "banner": lk.cloth("sc_banner", (0.16, 0.025, 0.02), weave=90.0, sheen=0.25, folds=4.0),
    }


MATERIAL_GROUPS = {"skin": 1, "iron": 2, "bronze": 2, "leather": 3, "loincloth": 3, "horn": 4, "tusk": 4, "eye": 4,
                   "hair": 4, "gold": 5}                 # 1 skin, 2 armour, 3 cloth/harness, 4 head details, 5 weapon


def tag_material_groups(m: dict) -> None:
    for key, index in MATERIAL_GROUPS.items():
        m[key].pass_index = index


# --- surface fitting helpers (rig rest space) --------------------------------------------------------------------

def hit_front(body, x, z, offset, y0=-2.0):
    ok, loc, nrm, _ = body.ray_cast(Vector((x, y0, z)), Vector((0.0, 1.0, 0.0)))
    if not ok:
        raise RuntimeError(f"surface fit missed at x={x}, z={z}")
    return tuple(loc + nrm * offset)


def hit_down(body, x, y, offset, z0=4.0):
    ok, loc, nrm, _ = body.ray_cast(Vector((x, y, z0)), Vector((0.0, 0.0, -1.0)))
    if not ok:
        raise RuntimeError(f"downward fit missed at x={x}, y={y}")
    return tuple(loc + nrm * offset)


def hit_radial(body, angle, z, offset, center=(0.0, 0.0), dist=2.0):
    d = Vector((math.cos(angle), math.sin(angle), 0.0))
    origin = Vector((center[0], center[1], z)) + d * dist
    ok, loc, nrm, _ = body.ray_cast(origin, -d)
    if not ok:
        raise RuntimeError(f"radial fit missed at angle={angle}, z={z}")
    return tuple(loc + nrm * offset)


def ring_path(body, z, offset, n=24, center=(0.0, 0.0)):
    pts = [hit_radial(body, 2 * math.pi * k / n, z, offset, center) for k in range(n)]
    return pts + [pts[0]]


def two_bone(s, g, l1, l2, pole):
    return strike.two_bone_ik(Vector(s), Vector(g), l1, l2, Vector(pole))


# --- the demon ---------------------------------------------------------------------------------------------------

def torso_elements() -> list[dict]:
    e = ch.ell
    out = [
        e((0, 0.02, 1.16), (0.30, 0.21, 0.17)),                       # pelvis
        e((0.14, 0.10, 1.07), (0.15, 0.13, 0.15)), e((-0.14, 0.10, 1.07), (0.15, 0.13, 0.15)),  # glutes
        e((0, 0.0, 1.40), (0.31, 0.21, 0.16)),                        # waist / obliques
        e((0, -0.06, 1.57), (0.28, 0.19, 0.20)),                      # abdomen
        e((0, 0.0, 1.86), (0.42, 0.27, 0.30)),                        # ribcage
        e((0, 0.15, 1.92), (0.32, 0.10, 0.30)),                       # back
        e((0, 0.01, 2.21), (0.13, 0.13, 0.12)),                       # neck
    ]
    for s in (1, -1):
        out += [e((s * 0.19, -0.155, 1.97), (0.21, 0.11, 0.14), rot_deg=(0, s * -12, 0)),   # pectorals
                e((s * 0.33, 0.04, 1.80), (0.13, 0.17, 0.26)),                              # lats
                e((s * 0.17, 0.06, 2.13), (0.17, 0.12, 0.09), rot_deg=(0, s * 20, 0)),      # trapezius
                e((s * 0.49, 0.0, 2.06), (0.16, 0.15, 0.13))]                               # shoulder mass
        for z in (1.71, 1.61, 1.51):
            out.append(e((s * 0.07, -0.215, z), (0.065, 0.035, 0.045)))                     # abdominals
    out += head_elements()
    out += leg_elements()
    return out


def head_elements() -> list[dict]:
    e, b = ch.ell, ch.ball
    out = [e((0, 0.03, 2.47), (0.19, 0.21, 0.22)),                    # cranium
           e((0, -0.15, 2.53), (0.17, 0.06, 0.05)),                   # heavy brow ridge
           e((0, -0.08, 2.32), (0.16, 0.14, 0.09)),                   # wide jaw
           e((0, -0.17, 2.29), (0.07, 0.05, 0.05)),                   # chin
           e((0, -0.215, 2.43), (0.04, 0.05, 0.055)),                 # nose
           e((0, -0.20, 2.335), (0.085, 0.04, 0.014), negative=True)]  # snarling mouth line
    for s in (1, -1):
        out += [e((s * 0.10, -0.14, 2.42), (0.07, 0.06, 0.05)),       # cheekbones
                e((s * 0.035, -0.225, 2.415), (0.022, 0.02, 0.018)),  # flared nostrils
                b((s * 0.07, -0.19, 2.48), 0.032, negative=True)]     # deep eye sockets
    return out


LEG = {s: {"hip": (s * 0.19, 0.02, 1.06), "knee": (s * 0.33, -0.10, 0.58), "ankle": (s * 0.40, -0.02, 0.12)}
       for s in (1, -1)}


def leg_elements() -> list[dict]:
    e, b = ch.ell, ch.ball
    out = []
    for s, j in LEG.items():
        out += ch.limb(j["hip"], j["knee"], 0.17, 0.115)
        out += [e((s * 0.27, -0.10, 0.84), (0.20, 0.10, 0.10), axis=Vector(j["knee"]) - Vector(j["hip"])),  # quad
                b((s * 0.33, -0.15, 0.58), 0.08)]                                                       # knee
        out += ch.limb(j["knee"], j["ankle"], 0.10, 0.065)
        out += [e((s * 0.36, 0.04, 0.40), (0.10, 0.10, 0.15)),                                          # calf
                e((s * 0.42, -0.12, 0.06), (0.09, 0.19, 0.06)),                                         # foot
                b((s * 0.40, 0.05, 0.07), 0.07)]                                                        # heel
        for dx in (-0.045, 0.0, 0.045):
            out.append(b((s * 0.42 + dx, -0.31, 0.04), 0.034))                                         # toes
    return out


def arm_elements(s: int) -> list[dict]:
    """One arm in the rig's REST pose (vertical at x = +-0.68): deltoid -> fist. s = +1 left (weapon), -1 right."""
    e, b = ch.ell, ch.ball
    x = s * 0.68
    out = [e((s * 0.64, 0.0, 2.02), (0.17, 0.16, 0.16))]                                  # deltoid
    out += ch.limb((x, 0, 2.0), (x, 0, 1.58), 0.12, 0.095)
    out += [e((x, -0.06, 1.80), (0.10, 0.10, 0.16)),                                     # biceps
            e((x + s * 0.01, 0.06, 1.83), (0.10, 0.10, 0.18)),                            # triceps
            b((x, 0.03, 1.56), 0.08)]                                                     # elbow
    out += ch.limb((x, 0, 1.55), (x, 0, 1.13), 0.10, 0.065)
    out += [e((x - s * 0.01, -0.02, 1.44), (0.10, 0.095, 0.12)),                          # forearm flexors
            b((x, 0, 1.11), 0.06)]                                                        # wrist
    if s == 1:                                     # weapon fist around the shaft (shaft along -Y through z = 0.98)
        out += [e((x, 0.0, 1.01), (0.075, 0.095, 0.075)), e((x, 0.0, 0.94), (0.06, 0.09, 0.035)),
                e((x - 0.06, -0.07, 0.99), (0.03, 0.05, 0.03))]
        out += [b((x + 0.045, y, 0.965), 0.034) for y in (-0.065, -0.022, 0.022, 0.065)]
    else:                                          # clenched off-hand
        out += [e((x, -0.02, 1.02), (0.07, 0.08, 0.075)), e((x - s * 0.05, -0.07, 1.0), (0.03, 0.05, 0.03))]
        out += [b((x + s * 0.01, -0.085, z), 0.032) for z in (0.97, 1.0, 1.03, 1.06)]
    return out


HEAD_PIVOT, HEAD_SCALE_V2 = Vector((0.0, 0.01, 2.21)), 1.12
K_V2, K_SHRINK = 2.7, 0.93          # firmer muscle fields (less blending); visible size compensated (measured ~+7%)


def _hs(p, k=HEAD_SCALE_V2):
    """v2 head scale about the neck base."""
    return tuple(HEAD_PIVOT + (Vector(p) - HEAD_PIVOT) * k)


def _firm(co, semi, **kw):
    return ch.ell(co, tuple(v * K_SHRINK for v in semi), stiffness=K_V2, **kw)


def torso_elements_v2() -> list[dict]:
    """v2: narrower waist, broader lats/back, firmer pectorals/abdominals/serratus/traps (defined, not fused)."""
    e = ch.ell
    out = [e((0, 0.02, 1.16), (0.29, 0.21, 0.17)),
           e((0.14, 0.10, 1.07), (0.15, 0.13, 0.15)), e((-0.14, 0.10, 1.07), (0.15, 0.13, 0.15)),
           e((0, 0.0, 1.40), (0.27, 0.20, 0.16)), e((0, -0.06, 1.57), (0.26, 0.18, 0.20)),
           e((0, 0.0, 1.87), (0.41, 0.26, 0.30)), e((0, 0.16, 1.93), (0.36, 0.10, 0.30)),
           e((0, 0.02, 2.20), (0.14, 0.14, 0.13))]
    for s in (1, -1):
        out += [_firm((s * 0.19, -0.17, 1.98), (0.21, 0.10, 0.13), rot_deg=(0, s * -14, 0)),
                _firm((s * 0.36, 0.05, 1.82), (0.13, 0.18, 0.28)),
                _firm((s * 0.18, 0.06, 2.14), (0.18, 0.12, 0.09), rot_deg=(0, s * 22, 0)),
                e((s * 0.49, 0.0, 2.06), (0.16, 0.15, 0.13))]
        for z in (1.72, 1.62, 1.52):
            out.append(_firm((s * 0.075, -0.215, z), (0.07, 0.035, 0.045)))
        for k, z in enumerate((1.80, 1.70, 1.60)):                       # serratus
            out.append(_firm((s * (0.30 - 0.02 * k), -0.12, z), (0.05, 0.04, 0.035), rot_deg=(0, s * 30, 0)))
    out += head_elements_v2()
    out += leg_elements_v2()
    return out


def head_elements_v2() -> list[dict]:
    e, b = ch.ell, ch.ball
    k = HEAD_SCALE_V2
    raw = [((0, 0.03, 2.47), (0.19, 0.21, 0.22), {}), ((0, -0.155, 2.535), (0.18, 0.065, 0.05), {}),
           ((0, -0.09, 2.31), (0.16, 0.15, 0.10), {}), ((0, -0.18, 2.27), (0.075, 0.055, 0.055), {}),
           ((0, -0.205, 2.47), (0.03, 0.03, 0.06), {}),                     # nose bridge
           ((0, -0.22, 2.42), (0.045, 0.05, 0.05), {}),
           ((0, -0.205, 2.33), (0.09, 0.04, 0.014), {"negative": True})]
    for s in (1, -1):
        raw += [((s * 0.105, -0.145, 2.41), (0.075, 0.06, 0.05), {}), ((s * 0.035, -0.23, 2.405), (0.022, 0.02, 0.018), {}),
                ((s * 0.12, -0.02, 2.62), (0.06, 0.06, 0.05), {})]           # horn bases fused into the skull
    out = [e(_hs(c), tuple(v * k for v in semi), **kw) for c, semi, kw in raw]
    for s in (1, -1):
        out.append(b(_hs((s * 0.07, -0.195, 2.48)), 0.034 * k, negative=True))
    return out


def leg_elements_v2() -> list[dict]:
    e, b = ch.ell, ch.ball
    out = []
    for s, j in LEG.items():
        out += ch.limb(j["hip"], j["knee"], 0.17, 0.11)
        out += [_firm((s * 0.28, -0.11, 0.86), (0.20, 0.10, 0.10), axis=Vector(j["knee"]) - Vector(j["hip"])),
                _firm((s * 0.20, -0.05, 0.80), (0.16, 0.07, 0.07), axis=Vector(j["knee"]) - Vector(j["hip"])),
                b((s * 0.33, -0.15, 0.58), 0.075)]
        out += ch.limb(j["knee"], j["ankle"], 0.095, 0.06)
        out += [_firm((s * 0.36, 0.05, 0.41), (0.10, 0.10, 0.16)), e((s * 0.42, -0.12, 0.06), (0.09, 0.19, 0.06)),
                b((s * 0.40, 0.05, 0.07), 0.07)]
        for dx in (-0.045, 0.0, 0.045):
            out.append(b((s * 0.42 + dx, -0.31, 0.04), 0.034))
    return out


def arm_elements_v2(s: int) -> list[dict]:
    """v2 arm (rest pose): firmer deltoid/biceps/triceps, elbow point, tapered forearm, slimmer wrist; palm only
    (the fingers are swept tubes, see finger_tubes)."""
    e, b = ch.ell, ch.ball
    x = s * 0.68
    out = [_firm((s * 0.65, 0.0, 2.02), (0.18, 0.17, 0.17))]
    out += ch.limb((x, 0, 2.0), (x, 0, 1.58), 0.115, 0.09)
    out += [_firm((x, -0.065, 1.80), (0.105, 0.10, 0.165)), _firm((x + s * 0.01, 0.065, 1.84), (0.10, 0.10, 0.19)),
            b((x, 0.05, 1.555), 0.07)]
    out += ch.limb((x, 0, 1.55), (x, 0, 1.13), 0.10, 0.058)
    out += [_firm((x - s * 0.01, -0.025, 1.45), (0.10, 0.09, 0.12)), b((x, 0, 1.11), 0.052),
            e((x - s * 0.015, 0.0, 1.035), (0.06, 0.085, 0.06))]        # palm / back of hand
    return out


def finger_tubes(s: int, m, prefix: str, grip: bool = True) -> list:
    """Four fingers wrapped around the grip axis (along Y through (x, *, 0.98)) and a thumb over them; without a grip
    the fingers close into a fist around a filled palm (no hole)."""
    x, gz, r = s * 0.68, (0.98 if grip else 1.0), (0.072 if grip else 0.04)
    out = [] if grip else [ch.metaball_mesh(f"{prefix}fist", [ch.ell((x, 0.0, gz), (0.05, 0.085, 0.05))], m["skin"],
                                            resolution=0.008, smooth_iters=2)]
    for k, y in enumerate((-0.066, -0.022, 0.022, 0.066)):
        pts = []
        for a in np.linspace(math.radians(95), math.radians(-150), 7):      # top -> outer side -> under the grip
            pts.append((x + s * r * math.cos(a), y, gz + r * math.sin(a)))
        out.append(ch.tube(f"{prefix}{k}", pts, [0.03, 0.029, 0.028, 0.027, 0.025, 0.022, 0.018], m["skin"], ring=10))
    thumb = [(x - s * 0.055, -0.05, gz + 0.055), (x - s * 0.035, -0.085, gz + 0.075), (x + s * 0.01, -0.085, gz + 0.07)]
    out.append(ch.tube(f"{prefix}t", thumb, [0.03, 0.027, 0.02], m["skin"], ring=10))
    return out


def build_asura(m, rig):
    if ATTACKER_ASSET == "asura_v2":
        return build_asura_v2(m, rig)
    rigid = ch.rigid
    torso = ch.metaball_mesh("sc_asura_torso", torso_elements(), m["skin"], resolution=0.016)
    zc = ch.vertex_coords(torso)[:, 2]
    ch.assign_weights(torso, ch.chain_weights(zc, [(1.42, 1.72, "pelvis", "chest")]))
    parts = [torso]
    for s, side in ((1, "L"), (-1, "R")):
        arm = ch.metaball_mesh(f"sc_asura_arm{side}", arm_elements(s), m["skin"], resolution=0.014)
        z = ch.vertex_coords(arm)[:, 2]
        stops = ([(1.06, 1.12, "mace", f"forearm.{side}")] if side == strike.WEAPON_SIDE else []) + \
                [(1.50, 1.62, f"forearm.{side}", f"upper_arm.{side}")]
        ch.assign_weights(arm, ch.chain_weights(z, stops))
        parts.append(arm)

    head = []                                                    # head details follow the chest rigidly
    for s in (1, -1):
        head.append(ch.tube(f"sc_horn{s}", [(s * 0.12, -0.03, 2.60), (s * 0.30, 0.0, 2.74), (s * 0.44, -0.04, 2.96),
                                            (s * 0.42, -0.12, 3.16), (s * 0.35, -0.20, 3.27)],
                            [0.075, 0.062, 0.042, 0.022, 0.0], m["horn"], ring=18))
        head.append(ch.tube(f"sc_tusk{s}", [(s * 0.085, -0.17, 2.30), (s * 0.10, -0.235, 2.37), (s * 0.13, -0.25, 2.44)],
                            [0.022, 0.015, 0.0], m["tusk"], ring=12))
        head.append(ch.tube(f"sc_ear{s}", [(s * 0.17, 0.02, 2.46), (s * 0.23, 0.05, 2.50), (s * 0.28, 0.08, 2.56)],
                            [0.045, 0.03, 0.0], m["skin"], ring=12, flat=0.45))
        eye = ch.metaball_mesh(f"sc_eye{s}", [ch.ell((s * 0.07, -0.185, 2.48), (0.026, 0.012, 0.016))], m["eye"],
                               resolution=0.004, smooth_iters=0)
        head.append(eye)
    knot = ch.metaball_mesh("sc_topknot", [ch.ell((0, 0.10, 2.70), (0.09, 0.09, 0.10)),
                                           ch.ell((0, 0.13, 2.80), (0.06, 0.06, 0.07))], m["hair"], resolution=0.01)
    head.append(knot)
    head.append(ch.tube("sc_knotring", [(0, 0.07, 2.73), (0, 0.13, 2.75)], [0.07, 0.07], m["bronze"], ring=16))
    rng = random.Random(5)
    for k in range(7):                                           # mane locks down the upper back
        a = -0.5 + k / 6.0
        x0, x1 = a * 0.26, a * 0.42
        head.append(ch.tube(f"sc_lock{k}", [(x0 * 0.8, 0.12, 2.62), (x0, 0.21, 2.45),
                                            (x1, 0.25 + rng.uniform(0, 0.03), 2.22),
                                            (x1 * 1.1, 0.24 + rng.uniform(0, 0.04), 2.02 - rng.uniform(0, 0.08))],
                            [0.045, 0.04, 0.03, 0.0], m["hair"], ring=10))
    # armour and harness fitted to the torso surface
    head.append(ch.tube("sc_gorget", ring_path(torso, 2.22, 0.03, n=20), [0.05] * 21, m["iron"], ring=12, flat=0.55))
    for s in (1, -1):                                            # crossing chest straps (shoulder -> opposite hip)
        pts = [hit_front(torso, s * x, z, 0.022) for x, z in ((0.34, 2.10), (0.21, 1.93), (0.0, 1.74),
                                                              (-0.19, 1.54), (-0.29, 1.38))]
        pts = [hit_down(torso, s * 0.37, 0.02, 0.02)] + pts
        head.append(ch.tube(f"sc_strap{s}", pts, [0.05] * len(pts), m["leather"], ring=10, flat=0.3,
                            up=(0.0, -1.0, 0.0)))
    mc = hit_front(torso, 0.0, 1.74, 0.03)
    head.append(ch.tube("sc_medallion", [(0, mc[1] + 0.02, 1.74), (0, mc[1] - 0.03, 1.74)], [0.085, 0.075],
                        m["bronze"], ring=24))
    head.append(ch.metaball_mesh("sc_boss", [ch.ell((0, mc[1] - 0.04, 1.74), (0.04, 0.025, 0.04))], m["bronze"],
                                 resolution=0.006, smooth_iters=1))
    for o in head:
        rigid(o, "chest")
    parts += head

    hips = [ch.tube("sc_belt", ring_path(torso, 1.33, 0.025, n=24), [0.06] * 25, m["leather"], ring=12, flat=0.4)]
    bf = hit_front(torso, 0.0, 1.33, 0.07)
    hips.append(lk.rounded_box((0.20, 0.05, 0.16), bf, m["bronze"], bevel=0.02, subdiv=1))
    hips.append(ch.cloth_panel("sc_loin_front", (0, bf[1] + 0.02, 1.27), (0, bf[1] - 0.06, 0.60), 0.36, 0.44,
                               m["loincloth"], folds=3, depth=0.02, sag=0.03))
    hips.append(ch.cloth_panel("sc_loin_back", (0, 0.27, 1.27), (0, 0.34, 0.58), 0.40, 0.46, m["loincloth"],
                               folds=3, depth=0.02, facing=(0, 1, 0)))
    for s in (1, -1):
        for k, ang in enumerate((-0.35, 0.05, 0.45)):            # leather tassets over the thighs
            ax, ay = math.cos(ang) * s, -math.sin(ang) - 0.2
            top = hit_radial(torso, math.atan2(ay, ax), 1.27, 0.03)
            face = (ax, ay, 0.0)
            hips.append(ch.cloth_panel(f"sc_tasset{s}{k}", top, (top[0] + ax * 0.08, top[1] + ay * 0.08, 0.86),
                                       0.15, 0.17, m["leather"], folds=1, depth=0.006, facing=face, thickness=0.02))
        j = LEG[s]
        shin = [Vector(j["knee"]).lerp(Vector(j["ankle"]), t) + Vector((0, -0.02, 0)) for t in (0.08, 0.5, 0.9)]
        hips.append(ch.tube(f"sc_greave{s}", [tuple(p) for p in shin], [0.115, 0.10, 0.085], m["iron"], ring=16))
        hips.append(ch.tube(f"sc_anklet{s}", [(s * 0.40, -0.02, 0.15), (s * 0.40, -0.02, 0.10)], [0.085, 0.085],
                            m["bronze"], ring=16))
    for o in hips:
        rigid(o, "pelvis")
    parts += hips

    for s, side in ((1, "L"), (-1, "R")):
        x = s * 0.68
        plates = [ch.shell(f"sc_pauldron{side}{k}", (x + s * dx, 0.0, z), semi, m["iron"], cut=-0.25, thickness=0.03,
                           rot_deg=(0, s * tilt, 0))
                  for k, (dx, z, semi, tilt) in enumerate(((0.0, 2.11, (0.26, 0.25, 0.17), 18),
                                                           (0.06, 2.01, (0.24, 0.235, 0.14), 34),
                                                           (0.11, 1.92, (0.21, 0.22, 0.12), 50)))]
        for k, dy in enumerate((-0.11, 0.0, 0.11)):              # spikes along the top plate
            base = Vector((x + s * 0.03, dy, 2.24))
            tip = base + Vector((s * 0.12, dy * 0.4, 0.20))
            plates.append(ch.tube(f"sc_spike{side}{k}", [tuple(base), tuple(base.lerp(tip, 0.5)), tuple(tip)],
                                  [0.045, 0.026, 0.0], m["iron"], ring=10))
        plates.append(ch.tube(f"sc_armband{side}", [(x, 0, 1.78), (x, 0, 1.72)], [0.135, 0.135], m["bronze"], ring=20))
        for o in plates:
            rigid(o, f"upper_arm.{side}")
        bracer = ch.tube(f"sc_bracer{side}", [(x, -0.01, 1.42), (x, -0.01, 1.28), (x, 0.0, 1.16)],
                         [0.118, 0.105, 0.088], m["leather"], ring=18)
        studs = ch.tube(f"sc_bracerband{side}", [(x, -0.01, 1.35), (x, -0.01, 1.32)], [0.122, 0.122], m["iron"],
                        ring=18)
        for o in (bracer, studs):
            rigid(o, f"forearm.{side}")
        parts += plates + [bracer, studs]

    body = temple.join(parts, "sc_asura")
    temple.set_origin(body, (0.0, 0.0, 0.0))
    SKINNING["sc_asura"] = ch.weight_stats(body)
    ch.bind(body, rig)
    temple.tag(body, "sc_asura", 1)

    gx, gz, ml = 0.68, 0.98, strike.MACE_LENGTH
    shaft = [ch.tube("sc_shaft", [(gx, 0.18, gz), (gx, -(ml - 0.12), gz)], [0.042, 0.042], m["iron"], ring=14),
             ch.tube("sc_grip", [(gx, 0.13, gz), (gx, -0.13, gz)], [0.05, 0.05], m["leather"], ring=14),
             ch.metaball_mesh("sc_pommel", [ch.ell((gx, 0.21, gz), (0.06, 0.05, 0.06))], m["bronze"], resolution=0.008)]
    for y in (-0.22, -(ml - 0.30)):
        shaft.append(ch.tube(f"sc_collar{y:.2f}", [(gx, y + 0.03, gz), (gx, y - 0.03, gz)], [0.06, 0.06], m["bronze"],
                             ring=14))
    shaft = temple.join([rigid(o, "mace") for o in shaft], "sc_mace_shaft")
    ch.bind(shaft, rig)
    temple.tag(shaft, "sc_mace_shaft", 9)
    hc = Vector((gx, -ml, gz))
    mh = [ch.metaball_mesh("sc_mace_core", [ch.ell(tuple(hc), (0.25, 0.27, 0.25))], m["gold"], resolution=0.012)]
    for k in range(8):                                           # flanges around the shaft axis
        a = 2 * math.pi * k / 8
        d = Vector((math.cos(a), 0.0, math.sin(a)))
        mh.append(ch.metaball_mesh(f"sc_flange{k}", [ch.ell(tuple(hc + d * 0.22), (0.12, 0.24, 0.035),
                                                               rot_deg=(0, -math.degrees(a), 0))],
                                     m["gold"], resolution=0.01, smooth_iters=2))
    golden = math.pi * (3 - math.sqrt(5))
    for k in range(12):
        yv = 1 - (k + 0.5) * 2 / 12
        rr = math.sqrt(1 - yv * yv)
        th = golden * k
        d = Vector((math.cos(th) * rr, -yv, math.sin(th) * rr))
        if d.y > 0.55:
            continue
        base = hc + d * 0.24
        mh.append(ch.tube(f"sc_mspike{k}", [tuple(base), tuple(base + d * 0.09), tuple(base + d * 0.17)],
                            [0.045, 0.024, 0.0], m["gold"], ring=10))
    mh.append(ch.tube("sc_mtip", [tuple(hc + Vector((0, -0.25, 0))), tuple(hc + Vector((0, -0.45, 0)))],
                        [0.05, 0.0], m["gold"], ring=12))
    mace_head = temple.join([rigid(o, "mace") for o in mh], "sc_mace_head")
    ch.bind(mace_head, rig)
    temple.tag(mace_head, "sc_mace_head", 8)
    return body, shaft, mace_head


def build_asura_v2(m, rig):
    """asura_v2 (D2): same rig, anchors, oc_ids and pass indices as asura_showcase_v1; upgraded surfaces."""
    rigid = ch.rigid
    torso = ch.metaball_mesh("sc_asura_torso", torso_elements_v2(), m["skin"], resolution=0.011, smooth_iters=8,
                             smooth_factor=0.6)
    zc = ch.vertex_coords(torso)[:, 2]
    ch.assign_weights(torso, ch.chain_weights(zc, [(1.42, 1.72, "pelvis", "chest")]))
    parts = [torso]
    for s, side in ((1, "L"), (-1, "R")):
        arm = ch.metaball_mesh(f"sc_asura_arm{side}", arm_elements_v2(s), m["skin"], resolution=0.010,
                               smooth_iters=8, smooth_factor=0.6)
        z = ch.vertex_coords(arm)[:, 2]
        weapon = side == strike.WEAPON_SIDE
        stops = ([(1.06, 1.12, "mace", f"forearm.{side}")] if weapon else []) + \
                [(1.50, 1.62, f"forearm.{side}", f"upper_arm.{side}")]
        ch.assign_weights(arm, ch.chain_weights(z, stops))
        fingers = finger_tubes(s, m, f"sc_finger{side}", grip=weapon)
        for f in fingers:
            rigid(f, "mace" if weapon else f"forearm.{side}")
        parts += [arm] + fingers

    k = HEAD_SCALE_V2
    head = []
    for s in (1, -1):
        horn = [(s * 0.12, -0.02, 2.62), (s * 0.31, 0.0, 2.76), (s * 0.46, -0.04, 2.99), (s * 0.44, -0.13, 3.19),
                (s * 0.36, -0.22, 3.30)]
        head.append(ch.tube(f"sc_horn{s}", [_hs(p) for p in horn], [0.085, 0.068, 0.045, 0.024, 0.0], m["horn"], ring=20))
        tusk = [(s * 0.085, -0.18, 2.29), (s * 0.10, -0.245, 2.36), (s * 0.135, -0.26, 2.44)]
        head.append(ch.tube(f"sc_tusk{s}", [_hs(p) for p in tusk], [0.024 * k, 0.016 * k, 0.0], m["tusk"], ring=12))
        ear = [(s * 0.17, 0.02, 2.46), (s * 0.23, 0.05, 2.50), (s * 0.28, 0.08, 2.56)]
        head.append(ch.tube(f"sc_ear{s}", [_hs(p) for p in ear], [0.045 * k, 0.03 * k, 0.0], m["skin"], ring=12, flat=0.45))
        head.append(ch.metaball_mesh(f"sc_eye{s}", [ch.ell(_hs((s * 0.07, -0.19, 2.48)), (0.028, 0.013, 0.017))],
                                     m["eye"], resolution=0.004, smooth_iters=0))
    head.append(ch.metaball_mesh("sc_topknot", [ch.ell(_hs((0, 0.10, 2.70)), (0.10, 0.10, 0.11)),
                                                ch.ell(_hs((0, 0.13, 2.81)), (0.065, 0.065, 0.075))], m["hair"],
                                 resolution=0.01))
    head.append(ch.tube("sc_knotring", [_hs((0, 0.07, 2.73)), _hs((0, 0.13, 2.75))], [0.078, 0.078], m["bronze"], ring=16))
    rng = random.Random(5)
    for kk in range(9):
        a = -0.5 + kk / 8.0
        x0, x1 = a * 0.30, a * 0.46
        head.append(ch.tube(f"sc_lock{kk}", [_hs((x0 * 0.8, 0.12, 2.62)), (x0, 0.23, 2.44),
                                             (x1, 0.27 + rng.uniform(0, 0.03), 2.20),
                                             (x1 * 1.1, 0.26 + rng.uniform(0, 0.04), 1.98 - rng.uniform(0, 0.08))],
                            [0.05, 0.044, 0.032, 0.0], m["hair"], ring=10))
    # integrated armour: breastplate, shoulder straps tying in the pauldrons, gorget, medallion
    head.append(ch.shell("sc_breastplate", (0.0, -0.02, 1.90), (0.45, 0.31, 0.33), m["iron"], cut=0.05,
                         thickness=0.035, rot_deg=(90, 0, 0)))
    head.append(ch.tube("sc_gorget", ring_path(torso, 2.22, 0.035, n=20), [0.055] * 21, m["iron"], ring=12, flat=0.55))
    for s in (1, -1):
        head.append(ch.tube(f"sc_shoulderstrap{s}", [(s * 0.27, -0.30, 2.12), (s * 0.40, -0.10, 2.27),
                                                     (s * 0.40, 0.12, 2.26), (s * 0.28, 0.28, 2.08)],
                            [0.05] * 4, m["leather"], ring=10, flat=0.35, up=(0.0, 0.0, 1.0)))
        head.append(ch.tube(f"sc_platerim{s}", [(s * 0.41, -0.10, 1.62), (s * 0.43, -0.20, 1.90), (s * 0.30, -0.30, 2.15)],
                            [0.022] * 3, m["bronze"], ring=8))
    head.append(ch.tube("sc_medallion", [(0, -0.31, 1.86), (0, -0.37, 1.86)], [0.095, 0.085], m["bronze"], ring=24))
    head.append(ch.metaball_mesh("sc_boss", [ch.ell((0, -0.38, 1.86), (0.045, 0.028, 0.045))], m["bronze"],
                                 resolution=0.006, smooth_iters=1))
    for o in head:
        rigid(o, "chest")
    parts += head

    hips = [ch.tube("sc_belt", ring_path(torso, 1.33, 0.03, n=24), [0.065] * 25, m["leather"], ring=12, flat=0.4)]
    bf = hit_front(torso, 0.0, 1.33, 0.075)
    hips.append(lk.rounded_box((0.22, 0.05, 0.17), bf, m["bronze"], bevel=0.02, subdiv=1))
    hips.append(ch.cloth_panel("sc_loin_front", (0, bf[1] + 0.02, 1.27), (0, bf[1] - 0.06, 0.58), 0.36, 0.46,
                               m["loincloth"], folds=4, depth=0.022, sag=0.03))
    hips.append(ch.cloth_panel("sc_loin_back", (0, 0.27, 1.27), (0, 0.34, 0.56), 0.40, 0.48, m["loincloth"],
                               folds=4, depth=0.022, facing=(0, 1, 0)))
    for s in (1, -1):
        for kk, ang in enumerate((-0.35, 0.05, 0.45)):
            ax, ay = math.cos(ang) * s, -math.sin(ang) - 0.2
            top = hit_radial(torso, math.atan2(ay, ax), 1.27, 0.03)
            hips.append(ch.cloth_panel(f"sc_tasset{s}{kk}", top, (top[0] + ax * 0.08, top[1] + ay * 0.08, 0.86),
                                       0.15, 0.17, m["iron"], folds=1, depth=0.006, facing=(ax, ay, 0.0), thickness=0.02))
        j = LEG[s]
        shin = [Vector(j["knee"]).lerp(Vector(j["ankle"]), t) + Vector((0, -0.02, 0)) for t in (0.08, 0.5, 0.9)]
        hips.append(ch.tube(f"sc_greave{s}", [tuple(p) for p in shin], [0.11, 0.095, 0.082], m["iron"], ring=16))
        hips.append(ch.shell(f"sc_kneeguard{s}", (j["knee"][0], j["knee"][1] - 0.06, j["knee"][2]), (0.10, 0.08, 0.10),
                             m["iron"], cut=0.0, thickness=0.02, rot_deg=(90, 0, 0)))
        hips.append(ch.tube(f"sc_anklet{s}", [(s * 0.40, -0.02, 0.15), (s * 0.40, -0.02, 0.10)], [0.085, 0.085],
                            m["bronze"], ring=16))
    for o in hips:
        rigid(o, "pelvis")
    parts += hips

    for s, side in ((1, "L"), (-1, "R")):
        x = s * 0.68
        plates = [ch.shell(f"sc_pauldron{side}{kk}", (x + s * dx, 0.0, z), semi, m["iron"], cut=-0.25, thickness=0.035,
                           rot_deg=(0, s * tilt, 0))
                  for kk, (dx, z, semi, tilt) in enumerate(((0.0, 2.12, (0.27, 0.26, 0.18), 18),
                                                            (0.06, 2.02, (0.25, 0.245, 0.15), 34),
                                                            (0.11, 1.93, (0.22, 0.23, 0.13), 50)))]
        plates.append(ch.tube(f"sc_pauldronrim{side}", [(x - s * 0.20, -0.20, 2.10), (x + s * 0.10, -0.24, 2.05),
                                                       (x + s * 0.22, -0.10, 1.95)], [0.02] * 3, m["bronze"], ring=8))
        for kk, dy in enumerate((-0.12, 0.0, 0.12)):
            base = Vector((x + s * 0.03, dy, 2.25))
            tip = base + Vector((s * 0.13, dy * 0.4, 0.22))
            plates.append(ch.tube(f"sc_spike{side}{kk}", [tuple(base), tuple(base.lerp(tip, 0.5)), tuple(tip)],
                                  [0.05, 0.028, 0.0], m["iron"], ring=10))
        plates.append(ch.tube(f"sc_armband{side}", [(x, 0, 1.78), (x, 0, 1.72)], [0.13, 0.13], m["bronze"], ring=20))
        for o in plates:
            rigid(o, f"upper_arm.{side}")
        bracer = ch.tube(f"sc_bracer{side}", [(x, -0.015, 1.42), (x, -0.012, 1.28), (x, 0.0, 1.15)],
                         [0.115, 0.10, 0.080], m["leather"], ring=18)
        studs = ch.tube(f"sc_bracerband{side}", [(x, -0.012, 1.35), (x, -0.012, 1.32)], [0.118, 0.118], m["iron"],
                        ring=18)
        for o in (bracer, studs):
            rigid(o, f"forearm.{side}")
        parts += plates + [bracer, studs]

    body = temple.join(parts, "sc_asura")
    temple.set_origin(body, (0.0, 0.0, 0.0))
    SKINNING["sc_asura"] = ch.weight_stats(body)
    ch.bind(body, rig)
    temple.tag(body, "sc_asura", 1)
    return (body,) + build_mace(m, rig)


def build_mace(m, rig):
    rigid = ch.rigid
    gx, gz, ml = 0.68, 0.98, strike.MACE_LENGTH
    shaft = [ch.tube("sc_shaft", [(gx, 0.18, gz), (gx, -(ml - 0.12), gz)], [0.042, 0.042], m["iron"], ring=14),
             ch.tube("sc_grip", [(gx, 0.13, gz), (gx, -0.13, gz)], [0.05, 0.05], m["leather"], ring=14),
             ch.metaball_mesh("sc_pommel", [ch.ell((gx, 0.21, gz), (0.06, 0.05, 0.06))], m["bronze"], resolution=0.008)]
    for y in (-0.22, -(ml - 0.30)):
        shaft.append(ch.tube(f"sc_collar{y:.2f}", [(gx, y + 0.03, gz), (gx, y - 0.03, gz)], [0.06, 0.06], m["bronze"],
                             ring=14))
    shaft = temple.join([rigid(o, "mace") for o in shaft], "sc_mace_shaft")
    ch.bind(shaft, rig)
    temple.tag(shaft, "sc_mace_shaft", 9)
    hc = Vector((gx, -ml, gz))
    mh = [ch.metaball_mesh("sc_mace_core", [ch.ell(tuple(hc), (0.25, 0.27, 0.25))], m["gold"], resolution=0.012)]
    for kk in range(8):
        a = 2 * math.pi * kk / 8
        d = Vector((math.cos(a), 0.0, math.sin(a)))
        mh.append(ch.metaball_mesh(f"sc_flange{kk}", [ch.ell(tuple(hc + d * 0.22), (0.12, 0.24, 0.035),
                                                                rot_deg=(0, -math.degrees(a), 0))],
                                   m["gold"], resolution=0.01, smooth_iters=2))
    golden = math.pi * (3 - math.sqrt(5))
    for kk in range(12):
        yv = 1 - (kk + 0.5) * 2 / 12
        rr = math.sqrt(1 - yv * yv)
        th = golden * kk
        d = Vector((math.cos(th) * rr, -yv, math.sin(th) * rr))
        if d.y > 0.55:
            continue
        base = hc + d * 0.24
        mh.append(ch.tube(f"sc_mspike{kk}", [tuple(base), tuple(base + d * 0.09), tuple(base + d * 0.17)],
                          [0.045, 0.024, 0.0], m["gold"], ring=10))
    mh.append(ch.tube("sc_mtip", [tuple(hc + Vector((0, -0.25, 0))), tuple(hc + Vector((0, -0.45, 0)))],
                      [0.05, 0.0], m["gold"], ring=12))
    mace_head = temple.join([rigid(o, "mace") for o in mh], "sc_mace_head")
    ch.bind(mace_head, rig)
    temple.tag(mace_head, "sc_mace_head", 8)
    return shaft, mace_head


# --- the defender (static) -------------------------------------------------------------------------------------

TRIDENT = {"butt": (0.15, 0.55, 0.45), "top": (-0.05, -0.85, 2.35)}      # forward guard, prongs at the attacker


def build_defender(m):
    """A static ascetic (~2.2 m) in a grounded guard, trident held diagonally across the body. Built facing -Y."""
    e, b = ch.ell, ch.ball
    butt, top = Vector(TRIDENT["butt"]), Vector(TRIDENT["top"])
    h_low, h_high = butt.lerp(top, 0.40), butt.lerp(top, 0.66)
    legs = {1: {"hip": (0.12, 0.0, 0.95), "knee": (0.17, -0.30, 0.52), "ankle": (0.19, -0.42, 0.10)},
            -1: {"hip": (-0.12, 0.0, 0.95), "knee": (-0.18, 0.22, 0.50), "ankle": (-0.22, 0.48, 0.10)}}
    core = [e((0, 0, 1.0), (0.20, 0.15, 0.13)), e((0, 0, 1.18), (0.18, 0.13, 0.12)),
           e((0, -0.04, 1.30), (0.17, 0.12, 0.13)), e((0, 0, 1.50), (0.27, 0.17, 0.20)),
           e((0, 0.07, 1.52), (0.22, 0.08, 0.18)),
           e((0, 0.0, 1.72), (0.07, 0.07, 0.07)), e((0, 0.01, 1.90), (0.11, 0.125, 0.13)),
           e((0, -0.05, 1.82), (0.085, 0.08, 0.06)), e((0, -0.125, 1.87), (0.022, 0.03, 0.035)),
           e((0, -0.095, 1.93), (0.09, 0.03, 0.025)), e((0, -0.115, 1.835), (0.03, 0.015, 0.012))]
    for s in (1, -1):
        core += [b((s * 0.042, -0.105, 1.913), 0.022, negative=True), e((s * 0.06, -0.085, 1.87), (0.04, 0.035, 0.03))]
        core += [e((s * 0.11, -0.11, 1.56), (0.12, 0.065, 0.085)), e((s * 0.24, 0.0, 1.62), (0.105, 0.10, 0.09)),
                 e((s * 0.12, 0.04, 1.69), (0.11, 0.08, 0.05), rot_deg=(0, s * 18, 0))]
    fit = ch.metaball_mesh("sc_def_fit", core, m["ash_skin"], resolution=0.012)     # torso-only surface for fitting
    els = list(core)
    for s in (1, -1):
        j = legs[s]
        els += ch.limb(j["hip"], j["knee"], 0.11, 0.08) + ch.limb(j["knee"], j["ankle"], 0.07, 0.048)
        els += [e((j["ankle"][0], j["ankle"][1] - 0.08, 0.04), (0.055, 0.12, 0.04))]
        shoulder = Vector((s * 0.24, 0.0, 1.62))
        hand = h_low if s == 1 else h_high
        elbow = two_bone(shoulder, hand, 0.32, 0.31, (s * 0.8, 0.3, -0.6))
        els += ch.limb(shoulder, elbow, 0.072, 0.056) + ch.limb(elbow, hand, 0.056, 0.04)
        els += [b(tuple(hand), 0.045)]
    body = ch.metaball_mesh("sc_def_body", els, m["ash_skin"], resolution=0.012)

    cloth = []
    dhoti = [e((0, 0, 1.0), (0.235, 0.19, 0.16))]
    for s in (1, -1):
        j = legs[s]
        knee, ank = Vector(j["knee"]), Vector(j["ankle"])
        dhoti += ch.limb(j["hip"], j["knee"], 0.145, 0.125) + ch.limb(knee, knee.lerp(ank, 0.32), 0.125, 0.115)
    cloth.append(ch.metaball_mesh("sc_dhoti", dhoti, m["white_cloth"], resolution=0.012))
    cloth.append(ch.cloth_panel("sc_pleats", (0, -0.17, 1.08), (0.0, -0.27, 0.40), 0.24, 0.34, m["white_cloth"],
                                folds=5, depth=0.016))
    for s in (1, -1):
        cloth.append(ch.metaball_mesh(f"sc_def_eye{s}", [e((s * 0.042, -0.10, 1.913), (0.014, 0.006, 0.008))],
                                      m["hair"], resolution=0.003, smooth_iters=0))
    cloth.append(ch.tube("sc_sash", ring_path(cloth[0], 1.12, 0.02, n=20), [0.04] * 21, m["sash"], ring=10, flat=0.5))
    sh = [hit_front(fit, x, z, 0.02) for x, z in ((0.18, 1.62), (0.08, 1.50), (-0.06, 1.36), (-0.16, 1.20))]
    cloth.append(ch.tube("sc_shawl", [(0.22, 0.05, 1.71)] + sh + [(-0.22, 0.02, 1.12)], [0.085] * 6, m["shawl"],
                         ring=10, flat=0.25, up=(0.0, -1.0, 0.0)))
    beads = [hit_front(fit, 0.11 * math.cos(a), 1.70 - 0.16 * math.sin(a), 0.012) for a in np.linspace(0.15, 2.99, 9)]
    cloth.append(ch.tube("sc_beads", [(0.10, 0.02, 1.72)] + beads + [(-0.10, 0.02, 1.72)], [0.016] * 11,
                         m["beads"], ring=8))
    hair = [ch.metaball_mesh("sc_jata", [e((0, 0.04, 2.03), (0.115, 0.11, 0.075)), e((0, 0.05, 2.09), (0.09, 0.085, 0.05)),
                                         e((0.03, 0.08, 2.0), (0.07, 0.08, 0.06)), e((0, 0.06, 1.96), (0.12, 0.10, 0.05))],
                             m["hair"], resolution=0.008)]
    rng = random.Random(9)
    for k in range(9):
        a = -0.5 + k / 8.0
        hair.append(ch.tube(f"sc_dlock{k}", [(a * 0.20, 0.07, 1.98), (a * 0.26, 0.15, 1.82),
                                             (a * 0.30 + rng.uniform(-0.02, 0.02), 0.17, 1.62),
                                             (a * 0.32, 0.15 + rng.uniform(0, 0.04), 1.44 + rng.uniform(0, 0.06))],
                            [0.03, 0.026, 0.018, 0.0], m["hair"], ring=8))
    d = (top - butt).normalized()
    tri = [ch.tube("sc_tri_shaft", [tuple(butt), tuple(top)], [0.022, 0.022], m["steel"], ring=12)]
    side_v = d.cross(Vector((0, 1, 0))).normalized()
    tri.append(ch.tube("sc_tri_bar", [tuple(top - side_v * 0.15), tuple(top + side_v * 0.15)], [0.016, 0.016],
                       m["steel"], ring=8))
    tri.append(ch.tube("sc_tri_mid", [tuple(top), tuple(top + d * 0.42)], [0.02, 0.0], m["steel"], ring=10))
    for s in (1, -1):
        p0 = top + side_v * s * 0.15
        tri.append(ch.tube(f"sc_tri_side{s}", [tuple(p0), tuple(p0 + side_v * s * 0.06 + d * 0.14),
                                                 tuple(p0 + side_v * s * 0.02 + d * 0.32)], [0.017, 0.012, 0.0],
                           m["steel"], ring=10))
    bpy.data.objects.remove(fit, do_unlink=True)
    obj = temple.join([body] + cloth + hair + tri, "sc_defender")
    temple.set_origin(obj, (0.0, 0.0, 0.0))
    obj.scale = (DEFENDER_SCALE,) * 3
    return obj


# --- the rigged defender (D3: ascetic_defender_v2 + trident_v2) ------------------------------------------------
# The v1 body, dress and hair rebuilt in a rest pose (arms hanging) on a 16-bone rig with the M2-B topology and the
# ascetic's proportions; the trident is its own object (sc_trident, pass 10) rigid to the `trident` bone, with a
# thicker shaft (0.035 m: v1's 0.022 m is ~4-5 px at 768x448). The 1.08 scale lives on the rig object. Hands stay on
# the shaft because the defender is keyed on every frame from interpolated targets (two-handed grip).

DEF_SHOULDER_X, DEF_SHOULDER_Z, DEF_UPPER, DEF_FORE, DEF_HAND = 0.24, 1.62, 0.32, 0.26, 0.05
TRIDENT_LEN = (Vector(TRIDENT["top"]) - Vector(TRIDENT["butt"])).length          # 2.369 m, as v1
TRIDENT_GRIP_U, TRIDENT_OFF_U = 0.40, 0.66                                         # v1 hand positions on the shaft
TRIDENT_GRIP_TO_TOP = (1.0 - TRIDENT_GRIP_U) * TRIDENT_LEN
TRIDENT_SHAFT_R = 0.035
DEF_LEGS = {1: {"hip": (0.12, 0.0, 0.95), "knee": (0.17, -0.30, 0.52), "ankle": (0.19, -0.42, 0.10)},
            -1: {"hip": (-0.12, 0.0, 0.95), "knee": (-0.18, 0.22, 0.50), "ankle": (-0.22, 0.48, 0.10)}}


def _def_bones() -> list:
    x, z = DEF_SHOULDER_X, DEF_SHOULDER_Z
    elbow_z, wrist_z = z - DEF_UPPER, z - DEF_UPPER - DEF_FORE
    grip_z = wrist_z - DEF_HAND
    out = [("root", (0, 0, 0), (0, 0, 0.4), None, False),
           ("pelvis", (0, 0, 0.95), (0, 0, 1.15), "root", False),
           ("spine", (0, 0, 1.15), (0, 0, 1.40), "pelvis", True),
           ("chest", (0, 0, 1.40), (0, 0, 1.80), "spine", True),
           ("head", (0, 0, 1.80), (0, 0, 2.08), "chest", True)]
    for s, side in ((1, "L"), (-1, "R")):
        out += [(f"upper_arm.{side}", (s * x, 0, z), (s * x, 0, elbow_z), "chest", False),
                (f"forearm.{side}", (s * x, 0, elbow_z), (s * x, 0, wrist_z), f"upper_arm.{side}", True),
                (f"hand.{side}", (s * x, 0, wrist_z), (s * x, 0, grip_z), f"forearm.{side}", True)]
        if side == "L":
            out.append(("trident", (x, 0, grip_z), (x, -TRIDENT_GRIP_TO_TOP, grip_z), "hand.L", True))
    for s, side in ((1, "L"), (-1, "R")):
        j = DEF_LEGS[s]
        out += [(f"thigh.{side}", j["hip"], j["knee"], "pelvis", False),
                (f"shin.{side}", j["knee"], j["ankle"], f"thigh.{side}", True)]
    return out


def _v1_guard() -> dict:
    butt, top = Vector(TRIDENT["butt"]), Vector(TRIDENT["top"])
    return {"chest": [0.0, 0.0], "grip": list(butt.lerp(top, TRIDENT_GRIP_U)), "weapon_dir": list(top - butt)}


# Defender poses (rig space, facing -Y). d_guard reproduces v1's baked guard exactly (same IK, same poles).
# d_block is a hanging guard: hands high, shaft slanting down toward the attacker (~30 deg), so the mace, coming down
# from the upper left, crosses it at ~70 deg in the image; d_push drives the shaft up-forward after the bind.
DEF_POSES = {
    "d_guard": _v1_guard(),
    "d_lift": {"chest": [-3.0, 10.0], "grip": [0.10, 0.10, 1.52], "weapon_dir": [-0.03, -0.25, 0.97]},
    "d_block": {"chest": [5.0, 20.0], "grip": [0.22, 0.12, 2.00], "weapon_dir": [-0.05, -0.85, -0.50]},
    "d_push": {"chest": [8.0, 22.0], "grip": [0.21, 0.04, 2.00], "weapon_dir": [-0.05, -0.85, -0.50]},
    "d_ready": {"chest": [4.0, 15.0], "grip": [0.20, 0.06, 1.92], "weapon_dir": [-0.05, -0.85, -0.30]},
}
DEF_PROFILE = strike.RigProfile(bones=_def_bones(), poses=DEF_POSES, poles={"L": [0.8, 0.3, -0.6], "R": [-0.8, 0.3, -0.6]},
                                upper_arm=DEF_UPPER, forearm=DEF_FORE, hand=DEF_HAND, weapon_bone="trident",
                                weapon_length=TRIDENT_GRIP_TO_TOP, weapon_side="L",
                                off_hand_on_weapon=(TRIDENT_OFF_U - TRIDENT_GRIP_U) * TRIDENT_LEN)
DEF_STATIONARY_BONES = ["root", "pelvis", "thigh.L", "thigh.R", "shin.L", "shin.R"]


def _defender_core() -> list[dict]:
    e, b = ch.ell, ch.ball
    core = [e((0, 0, 1.0), (0.20, 0.15, 0.13)), e((0, 0, 1.18), (0.18, 0.13, 0.12)),
            e((0, -0.04, 1.30), (0.17, 0.12, 0.13)), e((0, 0, 1.50), (0.27, 0.17, 0.20)),
            e((0, 0.07, 1.52), (0.22, 0.08, 0.18)),
            e((0, 0.0, 1.72), (0.07, 0.07, 0.07)), e((0, 0.01, 1.90), (0.11, 0.125, 0.13)),
            e((0, -0.05, 1.82), (0.085, 0.08, 0.06)), e((0, -0.125, 1.87), (0.022, 0.03, 0.035)),
            e((0, -0.095, 1.93), (0.09, 0.03, 0.025)), e((0, -0.115, 1.835), (0.03, 0.015, 0.012))]
    for s in (1, -1):
        core += [b((s * 0.042, -0.105, 1.913), 0.022, negative=True), e((s * 0.06, -0.085, 1.87), (0.04, 0.035, 0.03))]
        core += [e((s * 0.11, -0.11, 1.56), (0.12, 0.065, 0.085)), e((s * 0.24, 0.0, 1.62), (0.105, 0.10, 0.09)),
                 e((s * 0.12, 0.04, 1.69), (0.11, 0.08, 0.05), rot_deg=(0, s * 18, 0))]
    return core


def build_trident_v2(m, rig, grip: Vector):
    """sc_trident in rest space along the `trident` bone (-Y from the grip), rigid to it; v1 proportions, the shaft
    and prongs ~1.5x thicker."""
    rigid = ch.rigid
    d = Vector((0.0, -1.0, 0.0))
    butt = grip - d * (TRIDENT_GRIP_U * TRIDENT_LEN)
    top = grip + d * TRIDENT_GRIP_TO_TOP
    side_v = Vector((1.0, 0.0, 0.0))
    tri = [ch.tube("sc_tri2_shaft", [tuple(butt), tuple(top)], [TRIDENT_SHAFT_R, TRIDENT_SHAFT_R], m["steel"], ring=14),
           ch.tube("sc_tri2_bar", [tuple(top - side_v * 0.16), tuple(top + side_v * 0.16)], [0.024, 0.024],
                   m["steel"], ring=10),
           ch.tube("sc_tri2_mid", [tuple(top), tuple(top + d * 0.42)], [0.03, 0.0], m["steel"], ring=12),
           ch.tube("sc_tri2_butt", [tuple(butt), tuple(butt - d * 0.05)], [0.045, 0.0], m["steel"], ring=12)]
    for s in (1, -1):
        p0 = top + side_v * s * 0.16
        tri.append(ch.tube(f"sc_tri2_side{s}", [tuple(p0), tuple(p0 + side_v * s * 0.06 + d * 0.14),
                                                  tuple(p0 + side_v * s * 0.02 + d * 0.32)], [0.026, 0.018, 0.0],
                           m["steel"], ring=12))
    obj = temple.join([rigid(o, "trident") for o in tri], "sc_trident")
    temple.set_origin(obj, (0.0, 0.0, 0.0))
    ch.bind(obj, rig)
    temple.tag(obj, "sc_trident", 10)
    return obj


def build_defender_v2(m, rig):
    """ascetic_defender_v2: v1's body, dress and hair in a rest pose, skinned to `rig`; the trident separate."""
    e, b, rigid = ch.ell, ch.ball, ch.rigid
    core = _defender_core()
    fit = ch.metaball_mesh("sc_def_fit", core, m["ash_skin"], resolution=0.012)
    els = list(core)
    for s in (1, -1):
        j = DEF_LEGS[s]
        els += ch.limb(j["hip"], j["knee"], 0.11, 0.08) + ch.limb(j["knee"], j["ankle"], 0.07, 0.048)
        els += [e((j["ankle"][0], j["ankle"][1] - 0.08, 0.04), (0.055, 0.12, 0.04))]
    body = ch.metaball_mesh("sc_def_body", els, m["ash_skin"], resolution=0.012)
    ch.assign_weights(body, ch.chain_weights(ch.vertex_coords(body)[:, 2], [(1.22, 1.45, "pelvis", "chest")]))
    parts = [body]
    x, z = DEF_SHOULDER_X, DEF_SHOULDER_Z
    elbow_z, wrist_z = z - DEF_UPPER, z - DEF_UPPER - DEF_FORE
    grip_z = wrist_z - DEF_HAND
    for s, side in ((1, "L"), (-1, "R")):
        shoulder, elbow, hand = Vector((s * x, 0, z)), Vector((s * x, 0, elbow_z)), Vector((s * x, 0, grip_z))
        arm = ch.metaball_mesh(f"sc_def_arm{side}", ch.limb(shoulder, elbow, 0.072, 0.056) +
                               ch.limb(elbow, hand, 0.056, 0.04) + [b(tuple(hand), 0.045)], m["ash_skin"],
                               resolution=0.010)
        ch.assign_weights(arm, ch.chain_weights(ch.vertex_coords(arm)[:, 2],
                                                [(grip_z + 0.04, grip_z + 0.07, f"hand.{side}", f"forearm.{side}"),
                                                 (elbow_z - 0.03, elbow_z + 0.04, f"forearm.{side}",
                                                  f"upper_arm.{side}")]))
        parts.append(arm)
    grip = Vector((x, 0.0, grip_z))
    off = grip + Vector((0.0, -1.0, 0.0)) * DEF_PROFILE.off_hand_on_weapon
    for k, p in enumerate((grip, off)):                       # closed fists around the shaft, rigid to the trident
        parts.append(rigid(ch.metaball_mesh(f"sc_def_fist{k}", [e(tuple(p), (0.05, 0.06, 0.055))], m["ash_skin"],
                                            resolution=0.008), "trident"))

    dress = []
    dhoti = [e((0, 0, 1.0), (0.235, 0.19, 0.16))]
    for s in (1, -1):
        j = DEF_LEGS[s]
        knee, ank = Vector(j["knee"]), Vector(j["ankle"])
        dhoti += ch.limb(j["hip"], j["knee"], 0.145, 0.125) + ch.limb(knee, knee.lerp(ank, 0.32), 0.125, 0.115)
    dress.append(ch.metaball_mesh("sc_dhoti", dhoti, m["white_cloth"], resolution=0.012))
    dress.append(ch.cloth_panel("sc_pleats", (0, -0.17, 1.08), (0.0, -0.27, 0.40), 0.24, 0.34, m["white_cloth"],
                                folds=5, depth=0.016))
    dress.append(ch.tube("sc_sash", ring_path(dress[0], 1.12, 0.02, n=20), [0.04] * 21, m["sash"], ring=10, flat=0.5))
    for o in dress:
        rigid(o, "pelvis")
    sh = [hit_front(fit, xx, zz, 0.02) for xx, zz in ((0.18, 1.62), (0.08, 1.50), (-0.06, 1.36), (-0.16, 1.20))]
    shawl = ch.tube("sc_shawl", [(0.22, 0.05, 1.71)] + sh + [(-0.22, 0.02, 1.12)], [0.085] * 6, m["shawl"],
                    ring=10, flat=0.25, up=(0.0, -1.0, 0.0))
    ch.assign_weights(shawl, ch.chain_weights(ch.vertex_coords(shawl)[:, 2], [(1.22, 1.45, "pelvis", "chest")]))
    beads = [hit_front(fit, 0.11 * math.cos(a), 1.70 - 0.16 * math.sin(a), 0.012) for a in np.linspace(0.15, 2.99, 9)]
    upper = [ch.tube("sc_beads", [(0.10, 0.02, 1.72)] + beads + [(-0.10, 0.02, 1.72)], [0.016] * 11, m["beads"], ring=8)]
    for s in (1, -1):
        upper.append(ch.metaball_mesh(f"sc_def_eye{s}", [e((s * 0.042, -0.10, 1.913), (0.014, 0.006, 0.008))],
                                      m["hair"], resolution=0.003, smooth_iters=0))
    upper.append(ch.metaball_mesh("sc_jata", [e((0, 0.04, 2.03), (0.115, 0.11, 0.075)),
                                              e((0, 0.05, 2.09), (0.09, 0.085, 0.05)),
                                              e((0.03, 0.08, 2.0), (0.07, 0.08, 0.06)),
                                              e((0, 0.06, 1.96), (0.12, 0.10, 0.05))], m["hair"], resolution=0.008))
    rng = random.Random(9)
    for k in range(9):
        a = -0.5 + k / 8.0
        upper.append(ch.tube(f"sc_dlock{k}", [(a * 0.20, 0.07, 1.98), (a * 0.26, 0.15, 1.82),
                                              (a * 0.30 + rng.uniform(-0.02, 0.02), 0.17, 1.62),
                                              (a * 0.32, 0.15 + rng.uniform(0, 0.04), 1.44 + rng.uniform(0, 0.06))],
                             [0.03, 0.026, 0.018, 0.0], m["hair"], ring=8))
    for o in upper:
        rigid(o, "chest")
    bpy.data.objects.remove(fit, do_unlink=True)
    obj = temple.join(parts + dress + [shawl] + upper, "sc_defender")
    temple.set_origin(obj, (0.0, 0.0, 0.0))
    SKINNING["sc_defender"] = ch.weight_stats(obj)
    ch.bind(obj, rig)
    temple.tag(obj, "sc_defender", 2)
    return obj, build_trident_v2(m, rig, grip)


# --- the parry (D3: mace_strike_blocked_v1 x trident_parry_v1) ------------------------------------------------
# The defender's poses are authored; the attacker's contact pose is DERIVED from the defender's block so that the mace
# head touches the trident shaft on the CONTACT frame by construction (for any admitted placement): the head centre
# sits on the shaft's upward normal at PARRY_CONTACT_U along the shaft, pushed out until its nearest vertex is exactly
# one shaft radius from the axis. Both actors then hold the bind for one frame and part (rebound / push).

PARRY_RAISE_START = 9             # Blender frame: the defender leaves the guard as the wind-up begins (GUARD_END = 8)
PARRY_ARRIVE_BEFORE = 2           # the block is in place this many frames before contact (braced, not lucky)
PARRY_LIFT_AT = 17                # Blender frame: trident pulled up and back (clear of the wind-up), then brought over
PARRY_BIND = 3                    # frames the weapons stay in contact after CONTACT (a readable clash, like the slam's
                                  # floor hold; the head arrives at ~1.5 head widths/frame)
PARRY_REBOUND_AFTER = 5           # then both part over this many frames (rebound / push)
PARRY_CONTACT_U = 1.10            # contact point: metres along the shaft from the weapon grip (rig units)
PARRY_AIM_FROM = (0.88, -0.45, 2.45)  # attacker rig space: the mace points from here to the head (grip high, overhead blow)
PARRY_SHAFT_SEGMENT = (-TRIDENT_GRIP_U * TRIDENT_LEN, TRIDENT_GRIP_TO_TOP)    # along the shaft from the grip (rig units)


def parry_events(strike_frames: int) -> dict:
    """Blender frames of the parry pair (output frame = Blender frame - 1)."""
    contact = strike.APEX_FRAME + strike_frames
    strike.choreography_frames(strike_frames)                  # same validity range as the slam
    bind_end = contact + PARRY_BIND
    return {"apex": strike.APEX_FRAME, "contact": contact, "raise": PARRY_RAISE_START, "lift": PARRY_LIFT_AT,
            "arrive": contact - PARRY_ARRIVE_BEFORE, "bind_end": bind_end,
            "rebound": min(bind_end + PARRY_REBOUND_AFTER, FRAMES - 5), "hold_end": strike.HOLD_END}


def blocked_keys(strike_frames: int) -> dict:
    ev = parry_events(strike_frames)
    c = ev["contact"]
    return {1: ("guard", "BEZIER", "AUTO"), 8: ("guard", "BEZIER", "AUTO"), strike.APEX_FRAME: ("apex", "QUAD", "EASE_IN"),
            c: ("blocked", "CONSTANT", "AUTO"), ev["bind_end"]: ("blocked", "BEZIER", "AUTO"),
            ev["rebound"]: ("rebound", "BEZIER", "AUTO"), 49: ("rechamber", "BEZIER", "AUTO")}


def _blend_pose(a: dict, b: dict, t: float, ease: str = "smooth") -> dict:
    """Blend of two two-handed poses (smoothstep, or ease-out: a fast start), interpolating the point midway between
    the hands (not the grip) so neither hand swings out of reach while the shaft turns."""
    w = t * t * (3.0 - 2.0 * t) if ease == "smooth" else 1.0 - (1.0 - t) ** 2
    h = DEF_PROFILE.off_hand_on_weapon / 2.0
    da, db = Vector(a["weapon_dir"]).normalized(), Vector(b["weapon_dir"]).normalized()
    d = da.lerp(db, w).normalized()
    mid = (Vector(a["grip"]) + da * h).lerp(Vector(b["grip"]) + db * h, w)
    return {"chest": [a["chest"][i] * (1 - w) + b["chest"][i] * w for i in range(2)],
            "grip": list(mid - d * h), "weapon_dir": list(d)}


def defender_parry_poses(strike_frames: int) -> dict[int, dict]:
    """One interpolated target pose per Blender frame (keys on every frame keep both hands on the shaft)."""
    ev = parry_events(strike_frames)
    c = ev["contact"]
    segs = [(1, ev["raise"], "d_guard", "d_guard", "smooth"), (ev["raise"], ev["lift"], "d_guard", "d_lift", "smooth"),
            (ev["lift"], ev["arrive"], "d_lift", "d_block", "smooth"),
            (ev["arrive"], ev["bind_end"] + 1, "d_block", "d_block", "smooth"),  # pushes once the mace has left
            (ev["bind_end"] + 1, ev["rebound"], "d_block", "d_push", "smooth"),
            (ev["rebound"], FRAMES, "d_push", "d_ready", "smooth")]
    out = {}
    for a, b, pa, pb, ease in segs:
        for f in range(a, b + 1):
            out[f] = _blend_pose(DEF_POSES[pa], DEF_POSES[pb], (f - a) / (b - a) if b > a else 0.0, ease)
    return out


def key_defender(rig, poses: dict[int, dict]) -> dict:
    prof = strike.RigProfile(**{**DEF_PROFILE.__dict__, "poses": {f"df{f}": p for f, p in poses.items()}})
    keys = {f: (f"df{f}", "LINEAR", "AUTO") for f in poses}
    reached = strike.key_poses(rig, keys, prof)
    return {k: v for k, v in reached.items() if k in {f"df{f}" for f in (1, PARRY_RAISE_START, FRAMES)}} | {
        "per_frame_trident_tip": {str(f): reached[f"df{f}"]["trident_tip"] for f in sorted(poses)}}


def world_of(at, yaw_deg, scale=1.0) -> Matrix:
    return (Matrix.Translation(Vector(at)) @ Matrix.Rotation(math.radians(yaw_deg), 4, "Z") @
            Matrix.Diagonal((scale, scale, scale, 1.0)))


def shaft_world(def_rig, pose: dict) -> tuple[Vector, Vector, float]:
    """(grip, unit direction, world scale) of the trident shaft for a defender pose."""
    P = strike.solve_pose(def_rig, pose, DEF_PROFILE)["trident"]
    W = world_of(DEFENDER_AT, DEFENDER_YAW_DEG, DEFENDER_SCALE)
    return W @ P.translation, (W.to_3x3() @ P.to_3x3().col[1]).normalized(), DEFENDER_SCALE


def _seg_dist(points: np.ndarray, a: Vector, d: Vector, lo: float, hi: float) -> np.ndarray:
    rel = points - np.array(a)
    t = np.clip(rel @ np.array(d), lo, hi)
    return np.linalg.norm(rel - np.outer(t, np.array(d)), axis=1)


def _head_rest_vertices(head_obj) -> np.ndarray:
    """Mesh vertices in rig rest space (the object is parented to the rig with an identity parent inverse)."""
    co = ch.vertex_coords(head_obj)
    B = np.array(head_obj.matrix_basis)
    return (np.c_[co, np.ones(len(co))] @ B.T)[:, :3]


def solve_blocked_pose(asura_rig, head_obj, def_rig) -> tuple[dict, dict, dict, dict]:
    """The attacker's contact pose (mace head touching the shaft), rebound and re-chamber poses (attacker rig space)."""
    grip, sdir, k = shaft_world(def_rig, DEF_POSES["d_block"])
    pc = grip + sdir * (PARRY_CONTACT_U * k)
    up = Vector((0.0, 0.0, 1.0))
    n = (up - sdir * up.dot(sdir)).normalized()
    r_w = TRIDENT_SHAFT_R * k
    lo, hi = PARRY_SHAFT_SEGMENT[0] * k, PARRY_SHAFT_SEGMENT[1] * k
    Wa = world_of(ROOT_AT, ASURA_YAW_DEG)
    Wa_inv = Wa.inverted()
    rest_mace = asura_rig.data.bones["mace"].matrix_local
    verts = _head_rest_vertices(head_obj)
    vh = np.c_[verts, np.ones(len(verts))]
    centre = pc + n * (strike.MACE_HEAD_R + r_w)
    aim_from = Vector(PARRY_AIM_FROM)
    for _ in range(6):
        tip = Wa_inv @ centre
        mdir = (tip - aim_from).normalized()
        pose = {"chest": [10.0, -6.0], "mace_tip": list(tip), "mace_dir": list(mdir), "off_grip": [-0.70, 0.10, 1.40]}
        P = strike.solve_pose(asura_rig, pose)
        M = np.array(Wa @ P["mace"] @ rest_mace.inverted())
        world = (vh @ M.T)[:, :3]
        gap = float((_seg_dist(world, grip, sdir, lo, hi) - r_w).min())
        if abs(gap) < 2e-4:
            break
        centre = centre - n * gap
    grip_c = tip - mdir * strike.MACE_LENGTH
    rebound = {"chest": [2.0, -4.0], "grip": list(grip_c + Vector((-0.05, 0.10, 0.22))),
               "mace_dir": list((mdir + Vector((-0.05, 0.10, 0.65))).normalized()), "off_grip": [-0.62, -0.20, 1.20]}
    rechamber = {"chest": [3.0, 2.0], "grip": [0.80, 0.10, 1.75], "mace_dir": [0.30, 0.15, 0.94],
                 "off_grip": [-0.62, -0.20, 1.20]}
    info = {"shaft_grip_world": [round(v, 4) for v in grip], "shaft_dir_world": [round(v, 4) for v in sdir],
            "contact_u_m": PARRY_CONTACT_U, "normal_world": [round(v, 4) for v in n],
            "head_centre_world": [round(v, 4) for v in centre], "solve_gap_m": round(gap, 5),
            "contact_point_world": [round(v, 4) for v in pc + n * r_w]}
    return pose, rebound, rechamber, info


def _kd(points):
    from mathutils.kdtree import KDTree
    tree = KDTree(len(points))
    for j, p in enumerate(points):
        tree.insert(p, j)
    tree.balance()
    return tree


def contact_series(scene, asura_rig, head_obj, def_rig, defender_obj, trident_obj, attacker_obj) -> dict:
    """Per output frame: min distance (m) from the evaluated mace head to the trident shaft surface (< 0 =
    interpenetration), the nearest shaft parameter, mace head to the defender's body, and trident to the attacker's
    body (vertex-to-vertex, so ~1 cm resolution)."""
    out = {"head_to_shaft_m": [], "head_to_defender_m": [], "trident_to_attacker_m": [], "shaft_u_m": []}
    k = DEFENDER_SCALE
    lo, hi = PARRY_SHAFT_SEGMENT[0] * k, PARRY_SHAFT_SEGMENT[1] * k
    for f in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        pts = []
        for ob in (head_obj, defender_obj, trident_obj, attacker_obj):
            ev = ob.evaluated_get(dg)
            me = ev.to_mesh()
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            M = np.array(ob.matrix_world)
            pts.append((np.c_[co.reshape(-1, 3), np.ones(len(me.vertices))] @ M.T)[:, :3])
            ev.to_mesh_clear()
        pb = def_rig.pose.bones["trident"]
        Mt = def_rig.matrix_world @ pb.matrix
        g, d = Mt.translation, (Mt.to_3x3().col[1]).normalized()
        dist = _seg_dist(pts[0], g, d, lo, hi)
        i = int(dist.argmin())
        out["head_to_shaft_m"].append(round(float(dist[i] - TRIDENT_SHAFT_R * k), 4))
        out["shaft_u_m"].append(round(float((pts[0][i] - np.array(g)) @ np.array(d)) / k, 3))
        tree = _kd(pts[1])
        out["head_to_defender_m"].append(round(min(tree.find(Vector(p))[2] for p in pts[0][::4]), 4))
        tree = _kd(pts[2])
        out["trident_to_attacker_m"].append(round(min(tree.find(Vector(p))[2] for p in pts[3][::6]), 4))
    return out


def visible_fraction(scene, cam, obj, max_vertices: int = 800) -> list[float]:
    """Per output frame: the fraction of the object's (subsampled, evaluated) vertices whose camera ray first hits the
    object itself - < 1 where another object occludes it (back-facing vertices hit its own front, so count as seen)."""
    out = []
    for f in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        me = ev.to_mesh()
        step = max(1, len(me.vertices) // max_vertices)
        pts = [ev.matrix_world @ v.co for v in list(me.vertices)[::step]]
        ev.to_mesh_clear()
        eye = cam.matrix_world.translation
        seen = 0
        for p in pts:
            d = p - eye
            hit, _loc, _n, _i, hob, _m = scene.ray_cast(dg, eye, d.normalized(), distance=d.length + 0.05)
            seen += bool(hit and hob is not None and hob.original == obj)
        out.append(round(seen / max(len(pts), 1), 3))
    return out


def parry_timeline_parts(strike_frames: int, att_role: str, def_role: str) -> tuple[list, list]:
    """Defender phases and the contact interval, in the compiler's format (output-frame times)."""
    ev = parry_events(strike_frames)
    c = ev["contact"]
    phases = [{"id": "def_guard", "kind": "idle", "actor": def_role, "start": "0", "end": strike.src_time(ev["raise"])},
              {"id": "def_raise", "kind": "defense", "actor": def_role, "start": strike.src_time(ev["raise"]),
               "end": strike.src_time(c)},
              {"id": "def_block", "kind": "contact", "actor": def_role, "start": strike.src_time(c),
               "end": strike.src_time(ev["hold_end"])},
              {"id": "def_recovery", "kind": "recovery", "actor": def_role, "start": strike.src_time(ev["hold_end"]),
               "end": strike.src_time(FRAMES)}]
    contacts = [{"id": "mace_on_trident", "participants": [f"{att_role}.mace", f"{def_role}.trident"],
                 "start": strike.src_time(c), "end": strike.src_time(c), "contact_points": [f"{att_role}.mace.head"],
                 "required": True, "event": "strike.CONTACT"}]
    return phases, contacts


# --- environment upgrades --------------------------------------------------------------------------------------

def finish_environment(m, finial):
    shrine = bpy.data.objects["m2a_shrine"]                  # drop the old finial sphere (its faces carry `finial`)
    marker = {i for i, sl in enumerate(shrine.material_slots) if sl.material is finial}
    bm = bmesh.new()
    bm.from_mesh(shrine.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in marker], context="FACES")
    bm.to_mesh(shrine.data)
    bm.free()
    swaps = {"m2a_colonnade": m["pillar"], "m2a_walls": m["stone"], "m2a_rubble": m["stone"], "m2a_shrine": m["shrine"]}
    for name, new in swaps.items():
        o = bpy.data.objects[name]
        for i, slot in enumerate(o.material_slots):
            if slot.material and slot.material.name.startswith("m2a_shrine_dark"):
                o.material_slots[i].material = m["door"]
            else:
                o.material_slots[i].material = new
    bpy.data.objects["m2a_floor"].material_slots[0].material = m["floor"]


def upgrade_temple(m, scene):
    arch = []
    for side in (-1, 1):
        x = side * temple.PILLAR_X
        for y in temple.PILLAR_YS:
            arch += [lk.torus(0.36, 0.05, (x, y, 0.42), m["pillar"]), lk.torus(0.355, 0.045, (x, y, 3.88), m["pillar"]),
                     lk.torus(0.345, 0.03, (x, y, 3.75), m["pillar"])]
        arch.append(lk.rounded_box((0.95, 9.0, 0.48), (x, 1.75, 4.74), m["stone"], bevel=0.04, subdiv=0))
        arch.append(lk.rounded_box((1.12, 9.2, 0.16), (x, 1.75, 5.06), m["stone"], bevel=0.03, subdiv=0))
    px, py, pz = temple.PLATFORM["center"]
    top = pz + temple.PLATFORM["size"][2] / 2 + 2.6 + 1.8 + 1.5 + 1.2
    cy = py + 0.6
    arch.append(lk.tapered(0.85, 0.75, 0.30, (0.0, cy, top + 0.15), m["shrine"], verts=32, subdiv=0))
    ama = ch.metaball_mesh("sc_amalaka", [ch.ell((math.cos(a) * 0.55, cy + math.sin(a) * 0.55, top + 0.55),
                                                 (0.16, 0.16, 0.22)) for a in np.linspace(0, 2 * math.pi, 16, False)],
                           m["shrine"], resolution=0.03)
    arch.append(ama)
    arch.append(ch.tube("sc_kalasha", [(0, cy, top + 0.75), (0, cy, top + 0.95), (0, cy, top + 1.2), (0, cy, top + 1.5)],
                        [0.22, 0.26, 0.12, 0.0], m["bronze"], ring=20))
    for k in range(4):                                       # corner turrets on the first tier
        sx, sy = (1 if k % 2 else -1), (1 if k // 2 else -1)
        base = (sx * 2.2, cy + sy * 1.5, pz + temple.PLATFORM["size"][2] / 2 + 2.6)
        arch.append(ch.tube(f"sc_turret{k}", [base, (base[0], base[1], base[2] + 0.5), (base[0], base[1], base[2] + 1.1)],
                            [0.32, 0.26, 0.0], m["shrine"], ring=12))
    tag_all(arch, "sc_architecture", 13)

    braziers = []
    lights = []
    for k, (bx, by) in enumerate(((-2.6, 5.0), (2.6, 5.0), (-4.5, -2.3), (4.2, -2.3))):
        braziers += [lk.rounded_box((0.52, 0.52, 0.16), (bx, by, 0.08), m["stone"], bevel=0.03, subdiv=0),
                     lk.tapered(0.16, 0.12, 0.80, (bx, by, 0.56), m["stone"], verts=16, subdiv=0),
                     lk.rounded_box((0.34, 0.34, 0.08), (bx, by, 0.98), m["stone"], bevel=0.02, subdiv=0),
                     lk.torus(0.37, 0.035, (bx, by, 1.22), m["bronze"]),
                     ch.shell(f"sc_bowl{k}", (bx, by, 1.22), (0.38, 0.38, 0.26), m["bronze"], cut=0.0,
                              thickness=0.03, rot_deg=(180, 0, 0)),
                     lk.ball(0.26, (bx, by, 1.10), m["coal"], scale=(1.0, 1.0, 0.25))]
        flames = []
        rng = random.Random(30 + k)
        for f in range(3):
            fx, fy = bx + rng.uniform(-0.1, 0.1), by + rng.uniform(-0.1, 0.1)
            fl = lk.ball(0.2, (fx, fy, 1.42 + 0.06 * f), m["fire"], scale=(0.6 - 0.1 * f, 0.6 - 0.1 * f, 1.9 - 0.3 * f))
            fl.visible_shadow = False
            flames.append(fl)
        flame = temple.join(flames, f"sc_flame{k}")
        flame.visible_shadow = False
        flame["oc_exclude_from_passes"] = True                    # transparent flame: no meaningful depth
        lights.append(lk.point_light(scene, f"sc_fire_light{k}", (bx, by, 1.75), LOOK["fire"], (1.0, 0.45, 0.16),
                                     radius=0.25))
    tag_all(braziers, "sc_braziers", 14)

    banners = []
    for side in (-1, 1):
        x = side * (temple.PILLAR_X - 0.5)
        for y in (-0.75, 4.25):
            banners.append(ch.cloth_panel(f"sc_banner{side}{y}", (x, y, 4.45), (x, y, 1.95), 0.85, 0.80, m["banner"],
                                          folds=4, depth=0.03, facing=(-side, 0, 0)))
    tag_all(banners, "sc_banners", 15)
    rng = random.Random(41)
    stones = []
    while len(stones) < 46:
        x, y = rng.uniform(-6.4, 6.4), rng.uniform(-9.0, 6.0)
        if abs(x + 0.6) < 2.6 and -6.0 < y < -2.2:               # keep the action area clear
            continue
        if abs(abs(x) - temple.PILLAR_X) < 0.7 and -2.6 < y < 6.1:
            continue
        r = rng.uniform(0.04, 0.16)
        bpy.ops.mesh.primitive_ico_sphere_add(radius=1.0, subdivisions=1, location=(x, y, r * 0.3))
        st = bpy.context.active_object
        for v in st.data.vertices:                                  # angular rubble, not pebbles
            v.co *= rng.uniform(0.65, 1.2)
        st.scale = (r, r * rng.uniform(0.6, 1.0), r * rng.uniform(0.4, 0.7))
        st.rotation_euler = (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0, math.pi))
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        st.data.materials.append(m["stone"])
        stones.append(st)
    tag_all(stones, "sc_debris", 16)
    door_y = py + 0.6 - 1.8 - 0.05
    lights.append(lk.point_light(scene, "sc_sanctum", (0.0, door_y - 0.6, 2.2), LOOK["sanctum"], (1.0, 0.45, 0.15),
                                 radius=0.4))
    return lights


def tag_all(parts, oc_id, pass_index):
    o = temple.join(parts, oc_id)
    temple.tag(o, oc_id, pass_index)
    return o


def lighting(scene):
    lights = [lk.sun_light(scene, "sc_sun", SUN["elevation_deg"], SUN["heading_deg"], LOOK["sun"], SUN["color"])]
    lights.append(lk.area_light(scene, "sc_fill", (-1.0, -15.0, 5.5), (-0.5, -4.0, 1.4), LOOK["fill"],
                                tuple(LOOK["fill_color"]), 12.0))
    lights.append(lk.area_light(scene, "sc_firekey", (-5.2, -6.8, 2.4), (-1.6, -4.0, 1.9), LOOK["firekey"],
                                (1.0, 0.50, 0.22), 1.6))
    lights.append(lk.area_light(scene, "sc_coolrim", (-4.5, 3.0, 5.0), (-1.2, -4.0, 1.8), LOOK["coolrim"],
                                (0.6, 0.72, 1.0), 3.0))
    sd = (math.cos(math.radians(SUN["elevation_deg"])) * math.sin(math.radians(SUN["heading_deg"])),
          -math.cos(math.radians(SUN["elevation_deg"])) * math.cos(math.radians(SUN["heading_deg"])),
          math.sin(math.radians(SUN["elevation_deg"])))
    lk.dusk_world(scene, sun_dir=sd, strength=LOOK["world"])
    lk.haze_volume(scene, density=LOOK["haze"])
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = LOOK["look"]
    scene.view_settings.exposure = LOOK["exposure"]
    return lights


# --- deterministic impact effects ------------------------------------------------------------------------------

def contact_point() -> list[float]:
    """The 3D contact: on the floor for the slam (z = 0), on the trident shaft for the parry."""
    return list(CONTACT["contact_point_world"]) if CONTACT else impact_point()


def impact_point() -> list[float]:
    if CONTACT:                                          # parry: ground effects (only if requested) below the clash
        p = CONTACT["contact_point_world"]
        return [p[0], p[1], 0.0]
    tip = Vector(strike.POSES["contact"]["mace_tip"])
    p = Matrix.Rotation(math.radians(ASURA_YAW_DEG), 3, "Z") @ Vector((tip.x, tip.y, 0.0))
    return [round(ROOT_AT[0] + p.x, 4), round(ROOT_AT[1] + p.y, 4), 0.0]


def _dust_volume():
    mat = bpy.data.materials.new("fx_dust_volume")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (0.84, 0.74, 0.60, 1.0)          # light dust that catches the backlight
    vol.inputs["Anisotropy"].default_value = 0.5
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.5
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(nt.nodes.new("ShaderNodeTexCoord").outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.45, 0.7
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    sph = nt.nodes.new("ShaderNodeTexGradient")
    sph.gradient_type = "SPHERICAL"
    nt.links.new(nt.nodes.new("ShaderNodeTexCoord").outputs["Object"], sph.inputs["Vector"])
    shaped = nt.nodes.new("ShaderNodeMath")
    shaped.operation = "MULTIPLY"
    nt.links.new(ramp.outputs["Color"], shaped.inputs[0])
    nt.links.new(sph.outputs["Fac"], shaped.inputs[1])
    dens = nt.nodes.new("ShaderNodeMath")
    dens.operation = "MULTIPLY"
    nt.links.new(shaped.outputs["Value"], dens.inputs[0])
    dens.name = "fx_density"
    nt.links.new(dens.outputs["Value"], vol.inputs["Density"])
    glow = nt.nodes.new("ShaderNodeMath")                 # faint warm self-light ~ density (ambient + fire bounce)
    glow.operation = "MULTIPLY"
    nt.links.new(dens.outputs["Value"], glow.inputs[0])
    glow.inputs[1].default_value = 0.22
    vol.inputs["Emission Color"].default_value = (1.0, 0.78, 0.55, 1.0)
    nt.links.new(glow.outputs["Value"], vol.inputs["Emission Strength"])
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return mat, dens.inputs[1]


def _crack_material():
    mat = bpy.data.materials.new("fx_cracks")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    co = nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.feature = "DISTANCE_TO_EDGE"
    vor.inputs["Scale"].default_value = 5.0
    nt.links.new(co, vor.inputs["Vector"])
    crack = nt.nodes.new("ShaderNodeMath")
    crack.operation = "LESS_THAN"
    nt.links.new(vor.outputs["Distance"], crack.inputs[0])
    crack.inputs[1].default_value = 0.035
    grad = nt.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.9, 0.9, 0.9)
    nt.links.new(co, mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], grad.inputs["Vector"])
    reach = nt.nodes.new("ShaderNodeMath")
    reach.operation = "MULTIPLY"
    nt.links.new(crack.outputs["Value"], reach.inputs[0])
    nt.links.new(grad.outputs["Fac"], reach.inputs[1])
    crater = nt.nodes.new("ShaderNodeValToRGB")
    crater.color_ramp.elements[0].position, crater.color_ramp.elements[1].position = 0.55, 0.85
    nt.links.new(grad.outputs["Fac"], crater.inputs["Fac"])
    total = nt.nodes.new("ShaderNodeMath")
    total.operation = "MAXIMUM"
    nt.links.new(reach.outputs["Value"], total.inputs[0])
    sc = nt.nodes.new("ShaderNodeMath")
    sc.operation = "MULTIPLY"
    nt.links.new(crater.outputs["Color"], sc.inputs[0])
    sc.inputs[1].default_value = 0.55
    nt.links.new(sc.outputs["Value"], total.inputs[1])
    gate = nt.nodes.new("ShaderNodeMath")
    gate.operation = "MULTIPLY"
    nt.links.new(total.outputs["Value"], gate.inputs[0])
    dark = nt.nodes.new("ShaderNodeBsdfPrincipled")
    dark.inputs["Base Color"].default_value = (0.02, 0.016, 0.012, 1.0)
    dark.inputs["Roughness"].default_value = 0.95
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(gate.outputs["Value"], mix.inputs[0])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[1])
    nt.links.new(dark.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat, gate.inputs[1]


def build_impact_fx(scene, start_frame: int, m, seed: int | None = None):
    """Dust volumes (burst + ground ring), debris chunks, sparks and floor cracks, keyed per frame (CONSTANT) from
    `start_frame` (the ActionTimeline impact start). Collection fx_impact, excluded from the main view layer."""
    coll = bpy.data.collections.new("fx_impact")
    scene.collection.children.link(coll)
    dust_mat, dens = _dust_volume()
    crack_mat, crack_on = _crack_material()
    spark_mat = lk.plain("fx_spark", (1.0, 0.6, 0.25), 0.4, emission=(1.0, 0.55, 0.18), strength=40.0)
    rng = random.Random(FX["seed"] if seed is None else seed)
    px, py, _ = impact_point()
    objs = []

    def add(o, kind, **kw):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
        objs.append((o, kind, kw))

    for i in range(16):                                         # plume
        bpy.ops.mesh.primitive_ico_sphere_add(radius=1.0, subdivisions=3, location=(px, py, 0.1))
        o = bpy.context.active_object
        o.name = f"fx_plume_{i:02d}"
        o.data.materials.append(dust_mat)
        add(o, "plume", ang=rng.uniform(0, 2 * math.pi), vh=rng.uniform(0.3, 1.0), vz=rng.uniform(0.4, 1.3),
            r0=rng.uniform(0.18, 0.3))
    for i in range(14):                                         # ground ring
        bpy.ops.mesh.primitive_ico_sphere_add(radius=1.0, subdivisions=3, location=(px, py, 0.05))
        o = bpy.context.active_object
        o.name = f"fx_ring_{i:02d}"
        o.data.materials.append(dust_mat)
        add(o, "ring", ang=2 * math.pi * i / 14 + rng.uniform(-0.15, 0.15), vh=rng.uniform(1.6, 2.4),
            r0=rng.uniform(0.15, 0.24))
    chip_mat = m["stone"]
    for i in range(18):
        bpy.ops.mesh.primitive_ico_sphere_add(radius=1.0, subdivisions=1, location=(px, py, 0.05))
        o = bpy.context.active_object
        for v in o.data.vertices:
            v.co *= rng.uniform(0.7, 1.25)
        o.name = f"fx_chip_{i:02d}"
        o.data.materials.append(chip_mat)
        add(o, "chip", ang=rng.uniform(0, 2 * math.pi), vh=rng.uniform(1.2, 3.0), vz=rng.uniform(1.5, 3.4),
            r0=rng.uniform(0.025, 0.06), spin=(rng.uniform(-20, 20), rng.uniform(-20, 20), rng.uniform(-20, 20)))
    for i in range(12):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.006, depth=1.0, vertices=6, location=(px, py, 0.1))
        o = bpy.context.active_object
        o.name = f"fx_spark_{i:02d}"
        o.data.materials.append(spark_mat)
        add(o, "spark", ang=rng.uniform(0, 2 * math.pi), vh=rng.uniform(2.5, 5.0), vz=rng.uniform(1.0, 3.5))
    bpy.ops.mesh.primitive_plane_add(size=2.6, location=(px, py, 0.004))
    crack = bpy.context.active_object
    crack.name = "fx_cracks"
    crack.data.materials.append(crack_mat)
    crack.rotation_euler = (0.0, 0.0, math.radians(17))
    add(crack, "crack")
    cpt = Vector(contact_point())
    frame = Matrix.Identity(3)
    if CONTACT:                                          # weapon-on-weapon: sparks spray off the clash, local Z = the
        n = Vector(CONTACT["normal_world"])              # shaft normal toward the mace, more of them, faster
        frame = n.to_track_quat("Z", "Y").to_matrix()
        for i in range(16):
            bpy.ops.mesh.primitive_cylinder_add(radius=0.006, depth=1.0, vertices=6, location=tuple(cpt))
            o = bpy.context.active_object
            o.name = f"fx_spark_{12 + i:02d}"
            o.data.materials.append(spark_mat)
            add(o, "spark", ang=rng.uniform(0, 2 * math.pi), vh=rng.uniform(2.0, 4.5), vz=rng.uniform(0.5, 2.5))
    keep_kinds = {k for comp in FX["components"] for k in FX_KINDS[comp]}   # all objects are created first so the
    for o, kind, _kw in [x for x in objs if x[1] not in keep_kinds]:          # random draws (seeded) never shift
        bpy.data.objects.remove(o, do_unlink=True)
    objs = [x for x in objs if x[1] in keep_kinds]

    for f in range(scene.frame_start, scene.frame_end + 1):
        t = (f - start_frame) / FPS
        dens.default_value = 0.0 if t < 0 else FX["dust_density"] * math.exp(-t / FX["dust_decay_s"])
        dens.keyframe_insert("default_value", frame=f)
        crack_on.default_value = 0.0 if t < 0 else 1.0
        crack_on.keyframe_insert("default_value", frame=f)
        for o, kind, kw in objs:
            if kind == "crack":
                continue
            if t < 0:
                o.scale = (0.0, 0.0, 0.0)
            elif kind == "plume":
                drag = 1.0 - math.exp(-5.0 * t)
                d = kw["vh"] * drag / 5.0 * 2.5
                o.location = (px + d * math.cos(kw["ang"]), py + d * math.sin(kw["ang"]), 0.12 + kw["vz"] * drag / 2.5)
                s = kw["r0"] * (1.0 + 2.2 * drag)
                o.scale = (s, s, s * 0.85)
            elif kind == "ring":
                drag = 1.0 - math.exp(-4.0 * t)
                d = 0.15 + kw["vh"] * drag / 4.0 * 2.0
                o.location = (px + d * math.cos(kw["ang"]), py + d * math.sin(kw["ang"]), 0.08 + 0.12 * drag)
                s = kw["r0"] * (1.0 + 1.6 * drag)
                o.scale = (s * 1.3, s * 1.3, s * 0.55)
            elif kind == "chip":
                r = kw["r0"]
                z = max(r, 0.05 + kw["vz"] * t - 4.9 * t * t)
                travel = min(t, (kw["vz"] + math.sqrt(kw["vz"] ** 2 + 0.98)) / 9.8)
                o.location = (px + kw["vh"] * travel * math.cos(kw["ang"]), py + kw["vh"] * travel * math.sin(kw["ang"]), z)
                o.rotation_euler = tuple(w * travel for w in kw["spin"])
                o.scale = (r, r, r * 0.8)
            else:
                life = 5 / FPS
                if t > life:
                    o.scale = (0.0, 0.0, 0.0)
                else:
                    if CONTACT:
                        v0 = frame @ Vector((kw["vh"] * math.cos(kw["ang"]), kw["vh"] * math.sin(kw["ang"]), kw["vz"]))
                        vel = v0 + Vector((0.0, 0.0, -9.8 * t))
                        pos = cpt + v0 * t + Vector((0.0, 0.0, -4.9 * t * t))
                    else:
                        vel = Vector((kw["vh"] * math.cos(kw["ang"]), kw["vh"] * math.sin(kw["ang"]), kw["vz"] - 9.8 * t))
                        pos = Vector((px, py, 0.1)) + Vector((kw["vh"] * t * math.cos(kw["ang"]),
                                                             kw["vh"] * t * math.sin(kw["ang"]),
                                                             kw["vz"] * t - 4.9 * t * t))
                    o.location = tuple(pos)
                    o.rotation_euler = vel.to_track_quat("Z", "Y").to_euler()
                    fade = 1.0 - t / life
                    o.scale = (fade, fade, 0.06 + 0.10 * fade)
            o.keyframe_insert("location", frame=f)
            o.keyframe_insert("scale", frame=f)
            if kind in ("chip", "spark"):
                o.keyframe_insert("rotation_euler", frame=f)
    for datablock in [o for o, _, kw in objs if o.animation_data] + [dust_mat.node_tree, crack_mat.node_tree]:
        for fc in datablock.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"
    bpy.context.view_layer.layer_collection.children["fx_impact"].exclude = True
    scene.cycles.volume_bounces = 2                       # light dust volumes need multiple scattering
    if not FX["flash"]:
        return coll, None

    flash = bpy.data.collections.new("fx_flash")
    scene.collection.children.link(flash)
    at = tuple(cpt) if CONTACT else (px, py, 0.4)
    light = lk.point_light(scene, "fx_flash_light", at, 0.0, (1.0, 0.62, 0.32), radius=0.3, collection=flash)
    for f in range(scene.frame_start, scene.frame_end + 1):
        k = f - start_frame
        light.data.energy = float(FX["flash_energy_w"][k]) if 0 <= k < len(FX["flash_energy_w"]) else 0.0
        light.data.keyframe_insert("energy", frame=f)
    for fc in light.data.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
    bpy.context.view_layer.layer_collection.children["fx_flash"].exclude = True
    return coll, flash


# --- scene + spec ----------------------------------------------------------------------------------------------

def proxies() -> list[dict]:
    out = [p for p in camscene.proxies() if p["id"] != "actor"]
    out += [{"type": "aabb", "id": "asura", "min": [ROOT_AT[0] - 1.2, ROOT_AT[1] - 1.6, 0.0],
             "max": [ROOT_AT[0] + 1.9, ROOT_AT[1] + 1.2, 3.6]},
            {"type": "aabb", "id": "defender", "min": [DEFENDER_AT[0] - 0.9, DEFENDER_AT[1] - 0.9, 0.0],
             "max": [DEFENDER_AT[0] + 0.9, DEFENDER_AT[1] + 0.9, 3.0]},
            {"type": "aabb", "id": "braziers_front", "min": [-4.8, -2.6, 0.0], "max": [4.5, -2.0, 2.2]}]
    return out


def layers_manifest() -> dict:
    if LAYERS is not None:
        return LAYERS
    blur = {"holdout_others": True, "motion_blur_shutter": 0.5, "samples": 128}
    weapon = dict(blur, motion_blur_shutter=0.25)       # 90 deg: directional streak, head stays solid (showcase choice)
    return {"schema_version": 1, "id": "showcase_v1_layers", "shot": "showcase_v1", "layers": [
        {"id": "mace_protect", "kind": "protected_geometry", "objects": ["sc_mace_head", "sc_mace_shaft"],
         "render": weapon, "occlusion": "holdout", "order": 0, "grade": "per_channel_gain",
         "ghost_suppression": True, "ghost_mode": "swept_band", "ghost_fill": "temporal", "ghost_band_px": 8,
         "ghost_keep_objects": ["sc_asura"],          # the defender is static: temporal fill is safe on him
         "soften_px": 0.7,                            # match LTX's softness (the layer is a crisp Cycles render)
         "protection": {"track_object": "sc_mace_head", "authored_speed_widths": 0.5, "dilate_frames": 1,
                        "raw_retention_below": None, "include_frames": list(range(FRAMES))}},   # colour-blind look
        {"id": "impact_fx", "kind": "effect", "collections": ["fx_impact"], "render": blur, "occlusion": "holdout",
         "order": 1, "trigger": {"timeline": "sc_mace_slam_v1", "phase": "impact", "edge": "start"},
         "duration_frames": FRAMES - 29},
        {"id": "impact_flash", "kind": "effect", "collections": ["fx_flash"], "blend": "add",
         "render": {"holdout_others": False, "motion_blur_shutter": None, "samples": 96,
                    "light_only": ["fx_flash_light"]},
         "occlusion": "holdout", "order": 2, "trigger": {"timeline": "sc_mace_slam_v1", "phase": "impact",
                                                        "edge": "start"}, "duration_frames": 5}]}


def build(out_path: str, spec_path: str | None) -> dict:
    keys, events, phases = strike.choreography_frames(STRIKE_FRAMES)
    if parry():                                          # the blocked strike: same guard / wind-up / apex, contact on
        keys = blocked_keys(STRIKE_FRAMES)               # the trident, a rebound instead of the floor hold
        phases = [("rebound", "recoil", a, b) if i == "impact" else (i, k, a, b) for i, k, a, b in phases]
    scene = temple.setup_scene(RES)
    base = temple.make_materials()
    m = materials()
    tag_material_groups(m)
    cam = temple.add_camera(scene)
    finial = lk.plain("sc_finial_marker", (1.0, 0.0, 1.0))
    temple.build_environment(base, finial=finial)
    finish_environment(m, finial)
    upgrade_temple(m, scene)
    rig = strike.build_rig("sc_asura_rig")
    asura_objs = build_asura(m, rig)
    defender_info: dict = {"motion": "static (guard)", "at": DEFENDER_AT, "yaw_deg": DEFENDER_YAW_DEG}
    if DEFENDER_ASSET == "ascetic_defender_v1":
        reached = strike.key_poses(rig, keys)
        rig.location = ROOT_AT
        rig.rotation_euler = (0.0, 0.0, math.radians(ASURA_YAW_DEG))
        defender = build_defender(m)
        defender.location = DEFENDER_AT
        defender.rotation_euler = (0.0, 0.0, math.radians(DEFENDER_YAW_DEG))
        temple.tag(defender, "sc_defender", 2)
    else:
        drig = strike.build_rig("sc_defender_rig", DEF_PROFILE)
        defender, trident = build_defender_v2(m, drig)
        dposes = defender_parry_poses(STRIKE_FRAMES) if parry() else {1: DEF_POSES["d_guard"]}
        def_reached = key_defender(drig, dposes)
        drig.location = DEFENDER_AT
        drig.rotation_euler = (0.0, 0.0, math.radians(DEFENDER_YAW_DEG))
        drig.scale = (DEFENDER_SCALE,) * 3
        if parry():
            blocked, rebound, rechamber, info = solve_blocked_pose(rig, asura_objs[-1], drig)
            CONTACT.update(info)
            prof = strike.RigProfile(**{**strike.ASURA.__dict__, "poses": {
                **strike.POSES, "blocked": blocked, "rebound": rebound, "rechamber": rechamber}})
            reached = strike.key_poses(rig, keys, prof)
        else:
            reached = strike.key_poses(rig, keys)
        rig.location = ROOT_AT
        rig.rotation_euler = (0.0, 0.0, math.radians(ASURA_YAW_DEG))
        defender_info = {"motion": "rigged (trident_parry_v1)" if parry() else "rigged, held guard",
                         "asset": DEFENDER_ASSET, "action": DEFENDER_ACTION, "rig": "sc_defender_rig",
                         "at": DEFENDER_AT, "yaw_deg": DEFENDER_YAW_DEG, "scale": DEFENDER_SCALE,
                         "reached_rig_space": def_reached,
                         "events_blender_frame": parry_events(STRIKE_FRAMES) if parry() else {}}
        if parry():
            CONTACT["series"] = contact_series(scene, rig, asura_objs[-1], drig, defender, trident, asura_objs[0])
    lighting(scene)
    impact_frame = events["contact"]
    build_impact_fx(scene, impact_frame, m)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    traj = camscene.camera_samples(CAMERA_MOVE)
    npz = os.path.join(out_dir, "camera_motion.npz")
    traj.save_npz(npz)
    motion = {"schema_version": 1, "id": "showcase_orbit_push_in_v1", "units": "meters",
              "coordinate_system": "blender_z_up", "pose_convention": "camera_to_world",
              "rotation_format": "quaternion_wxyz", "trajectory": "camera_motion.npz",
              "trajectory_sha256": hashing.file_sha256(npz),
              "intrinsics": {"lens_mm": CAMERA_MOVE["lens_mm"], "sensor_width_mm": CAMERA_MOVE["sensor_mm"],
                             "sensor_height_mm": 24.0, "sensor_fit": CAMERA_MOVE["sensor_fit"],
                             "resolution_x": RES[0], "resolution_y": RES[1], "resolution_percentage": 100,
                             "clip_start": CAMERA_MOVE["clip_start"], "clip_end": CAMERA_MOVE["clip_end"]},
              "duration": f"{FRAMES}/{FPS}", "target_bindings": ["sc_asura.chest", "impact_point"],
              "constraints": {"minimum_clearance_m": MIN_CLEARANCE_M, "preserve_roll": True},
              "provenance": {"source": "authored", "confidence": "verified_in_scene", "scale": "metric_verified",
                             "notes": "showcase v1: M2-C/M3-A-family orbit + push-in, recomposed for 768x448"}}
    motion_path = os.path.join(out_dir, "camera_motion.json")
    common.write_json(motion_path, motion)
    oc_import_camera.apply(SimpleNamespace(samples=npz, time_key="t", intrinsics=motion_path, camera_name=cam.name,
                                           frame_start=scene.frame_start, set_scene_camera=True, save=out_path))
    clearance = camscene.clearance_per_frame(scene, cam, FRAMES)
    visibility = ({o: visible_fraction(scene, cam, bpy.data.objects[o]) for o in ("sc_mace_head", "sc_trident")}
                  if parry() else None)
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_path))

    eyes = traj.position
    move_info = {"camera_start_m": [round(v, 4) for v in eyes[0]], "camera_end_m": [round(v, 4) for v in eyes[-1]],
                 "chord_m": round(float(np.linalg.norm(eyes[-1] - eyes[0])), 4),
                 "path_m": round(float(np.linalg.norm(np.diff(eyes, axis=0), axis=1).sum()), 4),
                 "peak_speed_m_s": round(float(np.linalg.norm(np.diff(eyes, axis=0), axis=1).max() * FPS), 4),
                 "orbit_deg": CAMERA_MOVE["azimuth_deg"][1] - CAMERA_MOVE["azimuth_deg"][0]}
    timeline = strike.action_timeline(phases, STRIKE_FRAMES)
    timeline.update(id=TIMELINE_ID, actors=dict(TIMELINE_ACTORS))
    # actor roles are the compiler's (semantic ids, e.g. "shiva"): find them by engine object, not by name
    role_of = {oc_id: role for role, oc_id in TIMELINE_ACTORS.items()}
    for ph in timeline["phases"]:
        ph["actor"] = role_of.get("sc_asura", ph["actor"])
    if parry():
        def_phases, contacts = parry_timeline_parts(STRIKE_FRAMES, role_of.get("sc_asura", "asura"),
                                                    role_of.get("sc_defender", "defender"))
        timeline["phases"] += def_phases
        timeline["contacts"] = contacts
    else:
        timeline["phases"].append({"id": "defender_hold", "kind": "defense",
                                   "actor": role_of.get("sc_defender", "defender"),
                                   "start": "0", "end": strike.src_time(FRAMES)})
    if spec_path:
        common.write_json(os.path.join(os.path.dirname(os.path.abspath(spec_path)), "action_timeline.json"), timeline)
        spec = spec_dict(timeline, reached, keys, events, clearance, move_info, impact_frame - scene.frame_start)
        if DEFENDER_ASSET != "ascetic_defender_v1":
            spec["choreography"]["sc_defender"] = defender_info
            spec["tracking"]["defender_joints"] = {
                "rig": "sc_defender_rig", "weapon_bone": "trident", "weapon_object": "sc_trident",
                "body_object": "sc_defender", "stationary_bones": DEF_STATIONARY_BONES,
                "max_projection_err_px": 3.0, "max_stationary_m": 0.001}
        if parry():
            spec["tracking"]["visibility"] = visibility
            spec["choreography"]["contact"] = dict(CONTACT, frame_output=impact_frame - scene.frame_start,
                                                   attacker_action=ATTACKER_ACTION, defender_action=DEFENDER_ACTION)
            spec["choreography"]["sc_asura"]["source"] = ("build_temple_strike_scene POSES (guard/apex/recovery) + "
                                                          "blocked/rebound poses solved against the trident")
        common.write_json(spec_path, spec)
    print(f"[oc] SHOWCASE v1 scene saved: {out_path} ({move_info})")
    return {"clearance": clearance, "move": move_info}


def spec_dict(timeline, reached, keys, events, clearance, move_info, impact_out) -> dict:
    return {
        "shot": SHOT_ID,
        "label": "SHOWCASE OPTIMISATION RUN - NOT A CONTROLLED ADMISSION EXPERIMENT",
        "purpose": ("the best controlled cinematic action shot the system can make today (characters, look, lighting, "
                    "framing, resolution, effects optimised jointly; no capability claim)"),
        "frames": FRAMES, "fps": FPS, "resolution": list(RES),
        "scene": {"base": "M2-A temple (build_temple_shot_scene) re-surfaced and upgraded", "root_at": ROOT_AT,
                  "look_params": LOOK,
                  "asura_yaw_deg": ASURA_YAW_DEG, "defender_at": DEFENDER_AT, "defender_yaw_deg": DEFENDER_YAW_DEG,
                  "impact_point": impact_point(), "sun": SUN, "look": "AgX Medium High Contrast, dusk contre-jour, "
                  "haze 0.011, four braziers, sanctum doorway glow"},
        "choreography": {
            "sc_asura": {"rig": "sc_asura_rig", "root_at": ROOT_AT, "root_yaw_deg": ASURA_YAW_DEG,
                         "source": "build_temple_strike_scene POSES/KEYS (M2-B, original speed)",
                         "reached_rig_space": reached,
                         "keys": {str(f): {"pose": p, "interpolation": i, "easing": e}
                                  for f, (p, i, e) in sorted(keys.items())},
                         "events_blender_frame": events},
            "sc_defender": {"motion": "static (guard)", "at": DEFENDER_AT, "yaw_deg": DEFENDER_YAW_DEG},
            "action_timeline": timeline,
            "camera_move": dict(CAMERA_MOVE, **move_info),
            "camera_motion": {"manifest": "camera_motion.json", "samples": "camera_motion.npz"},
            "impact_output_frame": impact_out,
        },
        "camera_clearance": clearance,
        "clearance_proxies": proxies(),
        "characters": {"method": "oc_characters: metaball anatomy -> smooth mesh, swept tubes, shells, cloth panels; "
                                 "rest-space chain weights (pelvis/chest, arm chains, weapon fist on the mace bone)",
                       "skinning": SKINNING},
        "layers": layers_manifest(),
        "tracking": {
            "subjects": {
                "sc_asura": {"color": "crimson", "role": "primary", "ignore_occluders": ["sc_mace_head", "sc_mace_shaft"],
                             "checks": {"position": {"tol_px": 48, "area_tol": 0.25}}},
                "sc_mace_head": {"color": "gold_deep", "role": "primary", "ignore_occluders": ["sc_mace_shaft"],
                                 "gate": {"min_height_cells": 0.75, "min_width_cells": 0.75, "min_area_cells": 0.4,
                                          "min_excursion_cells": 2.0, "contrast_frames": "events",
                                          "require_visible_all_frames": True},
                                 "checks": {"timing": {"tol_frames": 2, "stop_px": 6, "min_excursion_frac": 0.5,
                                                       "min_detect_frac": 0.9, "min_dx_px": 48}}},
                "sc_defender": {"color": "blue", "role": "secondary", "checks": {"report_only": {}}},
            },
            "ground": ["m2a_floor"],
            "gate": {"min_height_cells": 2.0, "min_area_cells": 2.0, "min_width_cells": 1.5,
                     "min_control_contrast": 0.08, "require_in_frame": True},
            "joints": {"rig": "sc_asura_rig", "weapon_bone": "mace", "weapon_object": "sc_mace_head",
                       "body_object": "sc_asura", "stationary_bones": strike.STATIONARY_BONES,
                       "max_projection_err_px": 4.5, "max_stationary_m": 0.001},
            "timeline": {"apex_after_phase": "windup", "contact_after_phase": "strike", "tol_frames": 1},
            "camera_contract": {"samples": "camera_motion.npz", "max_position_err_m": 0.001, "max_angle_err_deg": 0.05},
            "clearance": {"min_m": MIN_CLEARANCE_M},
            "notes": "showcase: these checks validate the control inputs before generation; no classification",
        },
        "blender": common.blender_version(),
    }


def main() -> None:
    p = argparse.ArgumentParser(prog="build_showcase_scene")
    p.add_argument("--out", required=True)
    p.add_argument("--spec", default=None)
    p.add_argument("--look", default=None, help="JSON overrides of LOOK (look development only)")
    p.add_argument("--config", default=None, help="compiled scene_build JSON (D1 director)")
    a = p.parse_args(common.script_args())
    if a.config:
        apply_config(common.read_json(a.config))
    if a.look:
        import json

        LOOK.update(json.loads(a.look))
    build(a.out, a.spec)


if __name__ == "__main__":
    main()
