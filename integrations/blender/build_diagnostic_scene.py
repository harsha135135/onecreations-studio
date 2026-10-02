"""Build the v1 §15 diagnostic scene and save it as a .blend.

    blender -b --factory-startup --python build_diagnostic_scene.py -- --out diag.blend

Contents (all tagged with `oc_id`, meshes with `pass_index`):
- OC_Camera: 35 mm, 36 mm sensor, AUTO fit, shift (0.05, −0.03), 160×90; location keyed LINEAR from (0,−8,1.5) at
  frame 1 to (2,−7,1.8) at frame 25 (= 1 s @ 24 fps); rotation keyed LINEAR (looking at the origin, 10° roll at end).
- diag_cube (1): unit cube moving x −1.5 → 1.5 at y 0, z 0.5.
- diag_asym (2): cone lying on its side, rotating 0 → 90° about Z (asymmetric silhouette).
- diag_occluder (3): tall thin box crossing in front of the cube at y −4.
- diag_wall (4): plane at y = 6 facing −Y. diag_floor (5): plane at z = 0.
- diag_rig: two-bone armature whose lower bone bends 0 → 60°.
Frame range 1–24 at 24/1 fps; source time 0 = frame 1.

Optional `--resolution WxH --frames N` (defaults 160x90, 24) make larger/longer control renders for admission rungs;
the motion keeps the same start/end poses, stretched over N frames (camera end key at N+1). Tests use the defaults.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from mathutils import Euler, Vector  # noqa: E402

import oc_blender_common as common  # noqa: E402
from onecreations.geometry import conventions, quat  # noqa: E402

CAM_START, CAM_END = (0.0, -8.0, 1.5), (2.0, -7.0, 1.8)


def clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def linear_keys(obj) -> None:
    for datablock in (obj, getattr(obj, "data", None)):
        ad = getattr(datablock, "animation_data", None)
        if ad and ad.action:
            for fc in ad.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"


def add_mesh_box(name, size, location):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def tag(obj, oc_id, pass_index=None):
    obj["oc_id"] = oc_id
    if pass_index is not None:
        obj.pass_index = pass_index


def look_quat(eye, target, roll_deg=0.0):
    m = conventions.look_at(eye, target, roll_rad=math.radians(roll_deg))
    return tuple(quat.from_matrix(m[:3, :3]))


def build(out_path: str, resolution: tuple[int, int] = (160, 90), frames: int = 24) -> None:
    clear_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.fps, scene.render.fps_base = 24, 1.0
    scene.frame_start, scene.frame_end = 1, frames
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1.0

    cam_data = bpy.data.cameras.new("OC_Camera")
    cam_data.lens, cam_data.sensor_width, cam_data.sensor_fit = 35.0, 36.0, "AUTO"
    cam_data.shift_x, cam_data.shift_y = 0.05, -0.03
    cam_data.clip_start, cam_data.clip_end = 0.1, 200.0
    cam = bpy.data.objects.new("OC_Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.rotation_mode = "QUATERNION"
    for frame, loc, roll in ((1, CAM_START, 0.0), (frames + 1, CAM_END, 10.0)):
        cam.location = loc
        cam.rotation_quaternion = look_quat(loc, (0.0, 0.0, 0.5), roll)
        cam.keyframe_insert("location", frame=frame)
        cam.keyframe_insert("rotation_quaternion", frame=frame)
    linear_keys(cam)
    tag(cam, "diag_camera")

    cube = add_mesh_box("diag_cube", (1.0, 1.0, 1.0), (-1.5, 0.0, 0.5))
    cube.keyframe_insert("location", frame=1)
    cube.location = (1.5, 0.0, 0.5)
    cube.keyframe_insert("location", frame=frames)
    linear_keys(cube)
    tag(cube, "diag_cube", 1)

    bpy.ops.mesh.primitive_cone_add(radius1=0.4, depth=1.2, location=(2.5, 1.5, 0.5))
    asym = bpy.context.active_object
    asym.name = "diag_asym"
    asym.rotation_euler = Euler((math.radians(90), 0.0, 0.0))
    asym.keyframe_insert("rotation_euler", frame=1)
    asym.rotation_euler = Euler((math.radians(90), 0.0, math.radians(90)))
    asym.keyframe_insert("rotation_euler", frame=frames)
    linear_keys(asym)
    tag(asym, "diag_asym", 2)

    occ = add_mesh_box("diag_occluder", (0.3, 0.3, 3.0), (-6.0, -4.0, 1.5))
    occ.keyframe_insert("location", frame=1)
    occ.location = (6.0, -4.0, 1.5)
    occ.keyframe_insert("location", frame=frames)
    linear_keys(occ)
    tag(occ, "diag_occluder", 3)

    bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0.0, 6.0, 5.0), rotation=(math.radians(90), 0.0, 0.0))
    wall = bpy.context.active_object
    wall.name = "diag_wall"
    tag(wall, "diag_wall", 4)

    bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.active_object
    floor.name = "diag_floor"
    tag(floor, "diag_floor", 5)

    arm_data = bpy.data.armatures.new("diag_rig")
    rig = bpy.data.objects.new("diag_rig", arm_data)
    scene.collection.objects.link(rig)
    rig.location = (-2.5, 1.5, 0.0)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    upper = arm_data.edit_bones.new("upper")
    upper.head, upper.tail = Vector((0, 0, 0)), Vector((0, 0, 1))
    lower = arm_data.edit_bones.new("lower")
    lower.head, lower.tail = Vector((0, 0, 1)), Vector((0, 0, 2))
    lower.parent, lower.use_connect = upper, True
    bpy.ops.object.mode_set(mode="OBJECT")
    pb = rig.pose.bones["lower"]
    pb.rotation_mode = "XYZ"
    pb.rotation_euler = (0.0, 0.0, 0.0)
    pb.keyframe_insert("rotation_euler", frame=1)
    pb.rotation_euler = (math.radians(60), 0.0, 0.0)
    pb.keyframe_insert("rotation_euler", frame=frames)
    linear_keys(rig)
    tag(rig, "diag_rig")

    sun_data = bpy.data.lights.new("diag_sun", "SUN")
    sun = bpy.data.objects.new("diag_sun", sun_data)
    sun.rotation_euler = Euler((math.radians(50), 0.0, math.radians(30)))
    scene.collection.objects.link(sun)

    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out_path))
    print(f"[oc] diagnostic scene saved: {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(prog="build_diagnostic_scene")
    p.add_argument("--out", required=True)
    p.add_argument("--resolution", default="160x90", help="WxH")
    p.add_argument("--frames", type=int, default=24)
    a = p.parse_args(common.script_args())
    w, h = (int(v) for v in a.resolution.lower().split("x"))
    build(a.out, (w, h), a.frames)


if __name__ == "__main__":
    main()
