"""Build the R2D control-diagnostic scene: motion that is impossible to miss, for testing depth-guided video control.

    blender -b --factory-startup --python build_control_diagnostic_scene.py -- --out r2d.blend --spec spec.json

Deliberately plain (not cinematic). Static camera so every motion in the frame belongs to an object:
- OC_Camera: (0, -10, 1.6) looking horizontally along +Y, 35 mm / 36 mm sensor, 512x320, 49 frames @ 24 fps.
- r2d_box (pass 1): red 2.4 x 1.0 x 1.6 m box on the floor at y = -3 (7 m from the camera), sliding LEFT -> RIGHT,
  x -2.3 -> +2.3 (LINEAR, frames 1 -> 49). ~2.7 Union-guide cells wide, centroid travels ~5 cells.
- r2d_ball (pass 2): blue sphere r 0.8 m floating at z = 2.6 (above the box lane, never overlapping it), moving
  TOWARD the camera, y +5 -> -4 (15 m -> 6 m; LINEAR); projected diameter ~53 -> ~133 px.
- r2d_floor (pass 3): mid-grey plane z = 0. r2d_wall (pass 4): light-grey plane at y = +10 (20 m).
Flat colours + Standard view transform so the generated video can be tracked by colour. --spec writes the exact
keyframes/camera so the analysis does not depend on reading the .blend.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402

import oc_blender_common as common  # noqa: E402

FRAMES, FPS, RES = 49, 24, (512, 320)
CAMERA = {"location": [0.0, -10.0, 1.6], "rotation_euler_deg": [90.0, 0.0, 0.0], "lens_mm": 35.0, "sensor_mm": 36.0}
BOX = {"size": [2.4, 1.0, 1.6], "y": -3.0, "z": 0.8, "x_start": -2.3, "x_end": 2.3, "color": [0.8, 0.03, 0.03]}
BALL = {"radius": 0.8, "x": 0.0, "z": 2.6, "y_start": 5.0, "y_end": -4.0, "color": [0.03, 0.12, 0.85]}
FLOOR_COLOR, WALL_COLOR, WALL_Y = [0.35, 0.35, 0.35], [0.75, 0.75, 0.75], 10.0


def material(name: str, rgb: list[float]):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.9
    return mat


def linear_keys(obj) -> None:
    ad = obj.animation_data
    if ad and ad.action:
        for fc in ad.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def tag(obj, oc_id: str, pass_index: int | None = None, mat=None) -> None:
    obj["oc_id"] = oc_id
    if pass_index is not None:
        obj.pass_index = pass_index
    if mat is not None:
        obj.data.materials.append(mat)


def build(out_path: str, spec_path: str | None) -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene = bpy.context.scene
    scene.unit_settings.system, scene.unit_settings.scale_length = "METRIC", 1.0
    scene.render.fps, scene.render.fps_base = FPS, 1.0
    scene.frame_start, scene.frame_end = 1, FRAMES
    scene.render.resolution_x, scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1.0
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.6, 0.6, 0.6, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6

    cam_data = bpy.data.cameras.new("OC_Camera")
    cam_data.lens, cam_data.sensor_width, cam_data.sensor_fit = CAMERA["lens_mm"], CAMERA["sensor_mm"], "AUTO"
    cam_data.clip_start, cam_data.clip_end = 0.1, 200.0
    cam = bpy.data.objects.new("OC_Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = CAMERA["location"]
    cam.rotation_euler = [math.radians(a) for a in CAMERA["rotation_euler_deg"]]
    tag(cam, "r2d_camera")

    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(BOX["x_start"], BOX["y"], BOX["z"]))
    box = bpy.context.active_object
    box.name = "r2d_box"
    box.scale = BOX["size"]
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    box.keyframe_insert("location", frame=1)
    box.location.x = BOX["x_end"]
    box.keyframe_insert("location", frame=FRAMES)
    linear_keys(box)
    tag(box, "r2d_box", 1, material("r2d_red", BOX["color"]))

    bpy.ops.mesh.primitive_uv_sphere_add(radius=BALL["radius"], segments=48, ring_count=24,
                                         location=(BALL["x"], BALL["y_start"], BALL["z"]))
    ball = bpy.context.active_object
    ball.name = "r2d_ball"
    bpy.ops.object.shade_smooth()
    ball.keyframe_insert("location", frame=1)
    ball.location.y = BALL["y_end"]
    ball.keyframe_insert("location", frame=FRAMES)
    linear_keys(ball)
    tag(ball, "r2d_ball", 2, material("r2d_blue", BALL["color"]))

    bpy.ops.mesh.primitive_plane_add(size=80.0, location=(0.0, 10.0, 0.0))
    floor = bpy.context.active_object
    floor.name = "r2d_floor"
    tag(floor, "r2d_floor", 3, material("r2d_floor_grey", FLOOR_COLOR))

    bpy.ops.mesh.primitive_plane_add(size=80.0, location=(0.0, WALL_Y, 20.0), rotation=(math.radians(90), 0.0, 0.0))
    wall = bpy.context.active_object
    wall.name = "r2d_wall"
    tag(wall, "r2d_wall", 4, material("r2d_wall_grey", WALL_COLOR))

    sun = bpy.data.objects.new("r2d_sun", bpy.data.lights.new("r2d_sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(40), 0.0, math.radians(20))
    scene.collection.objects.link(sun)

    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_path))
    if spec_path:
        common.write_json(spec_path, {
            "purpose": "R2D control diagnostic: unmistakable left->right and toward-camera motion, static camera",
            "frames": FRAMES, "fps": FPS, "resolution": list(RES), "camera": CAMERA,
            "objects": {
                "r2d_box": dict(BOX, pass_index=1, motion="LEFT->RIGHT, x linear over frames 1..49, y/z fixed"),
                "r2d_ball": dict(BALL, pass_index=2, motion="TOWARD camera, y linear over frames 1..49 (15 m -> 6 m)"),
                "r2d_floor": {"pass_index": 3, "z": 0.0, "color": FLOOR_COLOR},
                "r2d_wall": {"pass_index": 4, "y": WALL_Y, "color": WALL_COLOR},
            },
            "blender": common.blender_version(),
        })
    print(f"[oc] control diagnostic scene saved: {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(prog="build_control_diagnostic_scene")
    p.add_argument("--out", required=True)
    p.add_argument("--spec", default=None, help="write the exact scene/motion spec JSON here")
    a = p.parse_args(common.script_args())
    build(a.out, a.spec)


if __name__ == "__main__":
    main()
