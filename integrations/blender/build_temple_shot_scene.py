"""Build the M2-A representative shot: a procedural temple courtyard with a humanoid-shaped rigid proxy that translates.

    blender -b --factory-startup --python build_temple_shot_scene.py -- --out m2a.blend --spec shot_spec.json

M2-A raises difficulty along one axis only (synthetic primitives -> representative environment). It tests whole-body
RIGID TRANSLATION of a humanoid-shaped proxy; it says nothing about articulated character motion (that is M2-B).
- OC_Camera: static, (0, -10, 2.2), pitched 6 deg down, 35 mm / 36 mm sensor, 512x320, 49 frames @ 24 fps.
- m2a_asura (pass 1): ~2.6 m crimson humanoid proxy (primitives joined into one rigid object) holding a gold mace,
  translating diagonally LEFT -> RIGHT while approaching: (-2.2, -3.5) -> (1.3, -4.5), i.e. 6.5 m -> 5.5 m,
  keeping the whole silhouette (mace held upright) inside the frame.
  No rotation, no articulation. It passes in front of the colonnade and the secondary figure; nothing occludes it.
- m2a_shiva (pass 2): static ~2.2 m ash-blue ascetic proxy with a trident on the shrine platform (~16.6 m).
- m2a_colonnade (3), m2a_shrine (4: platform, steps, stepped tower, doorway), m2a_walls (5), m2a_rubble (6),
  m2a_floor (7: stone tiles). Procedural stone materials, warm low sun, warm-grey sky (no blue, no fire, so the
  crimson/blue subjects stay separable by colour for the analysis).
--spec writes the exact scene, choreography and the pre-registered tracking/gate rules used by control_diagnostic.py.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import oc_blender_common as common  # noqa: E402

FRAMES, FPS, RES = 49, 24, (512, 320)
CAMERA = {"location": [0.0, -10.0, 2.2], "rotation_euler_deg": [84.0, 0.0, 0.0], "lens_mm": 35.0, "sensor_mm": 36.0}
ASURA_PATH = {"start": [-2.2, -3.5, 0.0], "end": [1.3, -4.5, 0.0], "frames": [1, FRAMES]}
SHIVA_AT = [0.5, 6.6, 1.2]
PILLAR_X, PILLAR_YS = 3.2, [-2.0, 0.5, 3.0, 5.5]
PLATFORM = {"center": [0.0, 8.5, 0.6], "size": [9.0, 5.0, 1.2]}
COLORS = {
    "stone_a": [0.55, 0.50, 0.42], "stone_b": [0.40, 0.36, 0.30], "mortar": [0.22, 0.20, 0.17],
    "shrine_dark": [0.12, 0.10, 0.08], "asura_skin": [0.62, 0.06, 0.05], "asura_cloth": [0.45, 0.04, 0.04],
    "gold": [0.85, 0.62, 0.20], "shiva_skin": [0.25, 0.45, 0.78], "white_cloth": [0.85, 0.83, 0.78],
    "iron": [0.25, 0.25, 0.27],
}
SKY = [0.60, 0.50, 0.42]


# --- materials -----------------------------------------------------------------------------------------------

def flat_material(name: str, rgb: list[float], roughness: float = 0.8):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def stone_material(name: str, a: list[float], b: list[float], scale: float = 3.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 6.0
    mix = nt.nodes.new("ShaderNodeMixRGB")
    mix.inputs["Color1"].default_value = (*a, 1.0)
    mix.inputs["Color2"].default_value = (*b, 1.0)
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], mix.inputs["Fac"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    return mat


def tile_material(name: str):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (*COLORS["stone_a"], 1.0)
    brick.inputs["Color2"].default_value = (*COLORS["stone_b"], 1.0)
    brick.inputs["Mortar"].default_value = (*COLORS["mortar"], 1.0)
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = 0.03
    brick.inputs["Brick Width"].default_value = 1.2
    brick.inputs["Row Height"].default_value = 0.6
    nt.links.new(coord.outputs["Object"], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9
    return mat


# --- geometry helpers ----------------------------------------------------------------------------------------

def box(size, location, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    return o


def cylinder(radius, depth, location, mat, rotation=(0.0, 0.0, 0.0), vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, rotation=rotation,
                                        vertices=vertices)
    o = bpy.context.active_object
    o.data.materials.append(mat)
    return o


def cone(r1, r2, depth, location, mat, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=depth, location=location, rotation=rotation,
                                    vertices=24)
    o = bpy.context.active_object
    o.data.materials.append(mat)
    return o


def sphere(radius, location, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=24, ring_count=12)
    o = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    return o


def join(parts, name):
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = name
    return o


def tag(obj, oc_id: str, pass_index: int | None = None) -> None:
    obj["oc_id"] = oc_id
    if pass_index is not None:
        obj.pass_index = pass_index


def set_origin(obj, point) -> None:
    """Place the object's origin at `point` (world) without moving geometry."""
    saved = bpy.context.scene.cursor.location.copy()
    bpy.context.scene.cursor.location = point
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    bpy.context.scene.cursor.location = saved


# --- builders ------------------------------------------------------------------------------------------------

def build_asura(m):
    """~2.6 m crimson humanoid proxy built around (0, 0, 0) = feet centre, facing -Y (the camera)."""
    parts = [
        cylinder(0.17, 1.1, (-0.25, 0.0, 0.55), m["asura_skin"]),
        cylinder(0.17, 1.1, (0.25, 0.0, 0.55), m["asura_skin"]),
        cone(0.62, 0.36, 0.85, (0.0, 0.0, 0.95), m["asura_cloth"]),
        box((0.95, 0.52, 0.95), (0.0, 0.0, 1.75), m["asura_skin"]),
        sphere(0.24, (-0.6, 0.0, 2.12), m["gold"]),
        sphere(0.24, (0.6, 0.0, 2.12), m["gold"]),
        cylinder(0.13, 0.95, (-0.68, 0.0, 1.62), m["asura_skin"]),
        cylinder(0.13, 0.85, (0.72, 0.0, 1.62), m["asura_skin"], rotation=(0.0, math.radians(-12), 0.0)),
        sphere(0.26, (0.0, 0.0, 2.42), m["asura_skin"]),
        cone(0.08, 0.0, 0.32, (-0.15, 0.0, 2.72), m["gold"], rotation=(0.0, math.radians(-15), 0.0)),
        cone(0.08, 0.0, 0.32, (0.15, 0.0, 2.72), m["gold"], rotation=(0.0, math.radians(15), 0.0)),
        cylinder(0.05, 1.5, (0.92, 0.0, 2.1), m["iron"], rotation=(0.0, math.radians(10), 0.0)),
        sphere(0.24, (1.05, 0.0, 2.9), m["gold"]),
    ]
    obj = join(parts, "m2a_asura")
    set_origin(obj, (0.0, 0.0, 0.0))
    return obj


def build_shiva(m):
    """~2.2 m ash-blue ascetic proxy with a trident, built around (0, 0, 0) = feet centre."""
    parts = [
        cylinder(0.13, 0.9, (-0.18, 0.0, 0.45), m["shiva_skin"]),
        cylinder(0.13, 0.9, (0.18, 0.0, 0.45), m["shiva_skin"]),
        cone(0.45, 0.28, 0.75, (0.0, 0.0, 0.8), m["white_cloth"]),
        box((0.7, 0.4, 0.75), (0.0, 0.0, 1.45), m["shiva_skin"]),
        cylinder(0.1, 0.75, (-0.45, 0.0, 1.35), m["shiva_skin"]),
        cylinder(0.1, 0.75, (0.45, 0.0, 1.35), m["shiva_skin"]),
        sphere(0.21, (0.0, 0.0, 2.0), m["shiva_skin"]),
        sphere(0.14, (0.0, 0.0, 2.27), m["stone_b"]),
        cylinder(0.035, 2.4, (0.62, 0.0, 1.2), m["iron"]),
        cylinder(0.03, 0.35, (0.62, 0.0, 2.55), m["iron"]),
        cylinder(0.03, 0.3, (0.5, 0.0, 2.5), m["iron"]),
        cylinder(0.03, 0.3, (0.74, 0.0, 2.5), m["iron"]),
        cylinder(0.02, 0.28, (0.62, 0.0, 2.36), m["iron"], rotation=(0.0, math.radians(90), 0.0)),
    ]
    obj = join(parts, "m2a_shiva")
    set_origin(obj, (0.0, 0.0, 0.0))
    return obj


def setup_scene(res=RES):
    """Clear the file and set the shared M2 render/time settings; returns the scene. `res` changes only the output
    size: the camera keeps its 35 mm lens and 36 mm sensor with AUTO fit (horizontal for landscape), so the horizontal
    field of view is kept and the vertical one follows the aspect ratio."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = "METRIC", 1.0
    scene.render.fps, scene.render.fps_base = FPS, 1.0
    scene.frame_start, scene.frame_end = 1, FRAMES
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1.0
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (*SKY, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.55
    return scene


def make_materials() -> dict:
    m = {k: flat_material(f"m2a_{k}", v) for k, v in COLORS.items() if k not in ("stone_a", "stone_b", "mortar")}
    m["stone"] = stone_material("m2a_stone", COLORS["stone_a"], COLORS["stone_b"])
    m["stone_b"] = flat_material("m2a_stone_b", COLORS["stone_b"])
    m["gold"].node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 0.6
    return m


def add_camera(scene):
    cam_data = bpy.data.cameras.new("OC_Camera")
    cam_data.lens, cam_data.sensor_width, cam_data.sensor_fit = CAMERA["lens_mm"], CAMERA["sensor_mm"], "AUTO"
    cam_data.clip_start, cam_data.clip_end = 0.1, 300.0
    cam = bpy.data.objects.new("OC_Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = CAMERA["location"]
    cam.rotation_euler = [math.radians(a) for a in CAMERA["rotation_euler_deg"]]
    tag(cam, "m2a_camera")
    return cam


def build_environment(m, finial=None) -> None:
    """Floor, colonnade, shrine, walls and rubble (pass indices 7, 3, 4, 5, 6). `finial` overrides the gold
    shrine finial's material (M2-B keeps gold unique to the weapon)."""
    bpy.ops.mesh.primitive_plane_add(size=120.0, location=(0.0, 20.0, 0.0))
    floor = bpy.context.active_object
    floor.name = "m2a_floor"
    floor.data.materials.append(tile_material("m2a_tiles"))
    tag(floor, "m2a_floor", 7)

    pillar_parts = []
    for side in (-1, 1):
        for y in PILLAR_YS:
            x = side * PILLAR_X
            pillar_parts += [box((0.95, 0.95, 0.35), (x, y, 0.175), m["stone"]),
                             cylinder(0.33, 3.6, (x, y, 2.15), m["stone"]),
                             box((0.95, 0.95, 0.3), (x, y, 4.1), m["stone"]),
                             box((1.1, 1.1, 0.25), (x, y, 4.375), m["stone"])]
    tag(join(pillar_parts, "m2a_colonnade"), "m2a_colonnade", 3)

    px, py, pz = PLATFORM["center"]
    sx, sy, sz = PLATFORM["size"]
    front = py - sy / 2
    shrine_parts = [box((sx, sy, sz), (px, py, pz), m["stone"])]
    for i, h in enumerate((0.9, 0.6, 0.3)):
        shrine_parts.append(box((4.0, 0.35, h), (0.0, front - 0.175 - 0.35 * i, h / 2), m["stone"]))
    z = sz
    for w, d, h in ((5.0, 3.6, 2.6), (4.0, 2.9, 1.8), (3.0, 2.2, 1.5), (2.0, 1.5, 1.2)):
        shrine_parts.append(box((w, d, h), (0.0, py + 0.6, z + h / 2), m["stone"]))
        z += h
    shrine_parts.append(sphere(0.55, (0.0, py + 0.6, z + 0.4), finial or m["gold"]))
    shrine_parts.append(box((1.2, 0.1, 1.9), (0.0, py + 0.6 - 1.8 - 0.05, sz + 0.95), m["shrine_dark"]))
    tag(join(shrine_parts, "m2a_shrine"), "m2a_shrine", 4)

    walls = [box((0.6, 20.0, 3.5), (-7.0, 6.0, 1.75), m["stone"]), box((0.6, 20.0, 3.5), (7.0, 6.0, 1.75), m["stone"]),
             box((14.6, 0.6, 5.0), (0.0, 13.5, 2.5), m["stone"])]
    tag(join(walls, "m2a_walls"), "m2a_walls", 5)

    rng = random.Random(7)
    rubble = []
    for _ in range(9):
        side = rng.choice((-1, 1))
        x = side * rng.uniform(4.2, 6.3)
        y = rng.uniform(-1.0, 5.0)
        s = rng.uniform(0.3, 0.7)
        r = box((s * rng.uniform(0.8, 1.6), s, s * rng.uniform(0.5, 1.0)), (x, y, s / 3), m["stone"])
        r.rotation_euler = (0.0, 0.0, math.radians(rng.uniform(0, 90)))
        rubble.append(r)
    tag(join(rubble, "m2a_rubble"), "m2a_rubble", 6)


def add_shiva(m):
    shiva = build_shiva(m)
    shiva.location = SHIVA_AT
    tag(shiva, "m2a_shiva", 2)
    return shiva


def add_sun(scene):
    sun = bpy.data.objects.new("m2a_sun", bpy.data.lights.new("m2a_sun", "SUN"))
    sun.data.energy = 4.0
    sun.data.color = (1.0, 0.84, 0.68)
    sun.rotation_euler = (math.radians(62), 0.0, math.radians(-38))
    scene.collection.objects.link(sun)
    return sun


def scene_spec() -> dict:
    return {"sky": SKY, "colors": COLORS, "pillars": {"x": PILLAR_X, "ys": PILLAR_YS},
            "platform": PLATFORM, "shiva_at": SHIVA_AT, "rubble_seed": 7,
            "sun": {"energy": 4.0, "color": [1.0, 0.84, 0.68], "rotation_euler_deg": [62, 0, -38]}}


def build(out_path: str, spec_path: str | None) -> None:
    scene = setup_scene()
    m = make_materials()
    add_camera(scene)
    build_environment(m)
    add_shiva(m)

    asura = build_asura(m)
    asura.location = ASURA_PATH["start"]
    asura.keyframe_insert("location", frame=ASURA_PATH["frames"][0])
    asura.location = ASURA_PATH["end"]
    asura.keyframe_insert("location", frame=ASURA_PATH["frames"][1])
    for fc in asura.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    tag(asura, "m2a_asura", 1)
    add_sun(scene)

    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_path))
    if spec_path:
        common.write_json(spec_path, {
            "shot": "m2a_temple",
            "purpose": ("M2-A: representative environment; whole-body RIGID TRANSLATION of a humanoid-shaped proxy "
                        "(no articulation, no rotation), static camera"),
            "frames": FRAMES, "fps": FPS, "resolution": list(RES), "camera": CAMERA,
            "scene": scene_spec(),
            "choreography": {"m2a_asura": dict(ASURA_PATH, interpolation="LINEAR", rotation="none",
                                               motion="LEFT->RIGHT while approaching (6.5 m -> 5.5 m)")},
            "tracking": {
                "subjects": {
                    "m2a_asura": {"color": "red", "role": "primary",
                                  "checks": {"lateral": {"monotone_tol_px": 16, "min_travel_frac": 0.5},
                                             "approach": {"min_gain_frac": 0.5, "monotone_tol": 0.15}}},
                    "m2a_shiva": {"color": "blue", "role": "secondary", "checks": {"report_only": {}}},
                },
                "ground": ["m2a_floor"],
                "static_structures": ["m2a_colonnade", "m2a_shrine", "m2a_walls"],
                "gate": {"min_height_cells": 2.0, "min_area_cells": 2.0, "min_width_cells": 1.5,
                         "min_travel_cells": 4.0, "min_control_contrast": 0.08},
                "notes": "static-structure drift is report-only (owner, 2026-10-02); coherence is judged from gross "
                         "spatial/structural relationships with visual evidence",
            },
            "blender": common.blender_version(),
        })
    print(f"[oc] M2-A temple shot scene saved: {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(prog="build_temple_shot_scene")
    p.add_argument("--out", required=True)
    p.add_argument("--spec", default=None)
    a = p.parse_args(common.script_args())
    build(a.out, a.spec)


if __name__ == "__main__":
    main()
