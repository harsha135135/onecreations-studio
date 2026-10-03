"""Finished-look building blocks for the temple shots (M3-A on): procedural PBR materials, a cinematic dusk world with
light volumetric haze, three-point lighting, and more detailed (still rig-compatible) character geometry.

bpy + stdlib only. Everything is procedural (no image textures, no downloads), so a scene stays reproducible from
its script. The look changes surfaces and lighting; it never moves the authored geometry, rig or camera, so depth,
object index and silhouettes rendered from the same scene stay aligned with the control by construction.
Colour discipline (kept for the image-space trackers): gold only on the mace head, red only on the demon's skin and
cloth, banners in green / magenta / cyan, no saturated blue or green elsewhere.
"""

from __future__ import annotations

import math
import random

import bpy

# --- node helpers --------------------------------------------------------------------------------------------


def _new(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def _material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    return mat, nt, nt.nodes["Principled BSDF"]


def _ramp(nt, fac_socket, a, b, pos=(0.3, 0.7)):
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].position, r.color_ramp.elements[1].position = pos
    r.color_ramp.elements[0].color, r.color_ramp.elements[1].color = (*a, 1.0), (*b, 1.0)
    nt.links.new(fac_socket, r.inputs["Fac"])
    return r


def _mul(nt, a_socket, b_socket):
    m = nt.nodes.new("ShaderNodeMixRGB")
    m.blend_type = "MULTIPLY"
    m.inputs["Fac"].default_value = 1.0
    nt.links.new(a_socket, m.inputs["Color1"])
    nt.links.new(b_socket, m.inputs["Color2"])
    return m


def _bump(nt, height_socket, strength, distance=0.02, normal_socket=None):
    bmp = _new(nt, "ShaderNodeBump", Strength=strength, Distance=distance)
    nt.links.new(height_socket, bmp.inputs["Height"])
    if normal_socket is not None:
        nt.links.new(normal_socket, bmp.inputs["Normal"])
    return bmp


def _coords(nt, kind="Object"):
    return nt.nodes.new("ShaderNodeTexCoord").outputs[kind]


# --- materials -----------------------------------------------------------------------------------------------


def stone(name, a=(0.42, 0.36, 0.29), b=(0.26, 0.22, 0.18), scale=3.5, crack_scale=9.0, dirt=0.5, fluting=0.0):
    """Weathered carved stone: two-tone noise, darker weathering patches, voronoi cracks, crevice dirt (AO), bump."""
    mat, nt, bsdf = _material(name)
    co = _coords(nt)
    n1 = _new(nt, "ShaderNodeTexNoise", Scale=scale, Detail=8.0, Roughness=0.6)
    n2 = _new(nt, "ShaderNodeTexNoise", Scale=0.7, Detail=4.0)
    vor = _new(nt, "ShaderNodeTexVoronoi", Scale=crack_scale)
    vor.feature = "DISTANCE_TO_EDGE"
    for n in (n1, n2, vor):
        nt.links.new(co, n.inputs["Vector"])
    base = _ramp(nt, n1.outputs["Fac"], b, a, (0.35, 0.65))
    weather = _ramp(nt, n2.outputs["Fac"], (0.62, 0.58, 0.54), (1.0, 1.0, 1.0), (0.35, 0.7))
    cracks = _ramp(nt, vor.outputs["Distance"], (0.45, 0.42, 0.40), (1.0, 1.0, 1.0), (0.0, 0.05))
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.6
    dirt_r = _ramp(nt, ao.outputs["AO"], (dirt, dirt * 0.95, dirt * 0.9), (1.0, 1.0, 1.0), (0.2, 0.9))
    c = _mul(nt, _mul(nt, _mul(nt, base.outputs["Color"], weather.outputs["Color"]).outputs["Color"],
                      cracks.outputs["Color"]).outputs["Color"], dirt_r.outputs["Color"])
    nt.links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
    rough = _ramp(nt, n1.outputs["Fac"], (0.78, 0.78, 0.78), (0.97, 0.97, 0.97))
    nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    height = nt.nodes.new("ShaderNodeMath")
    height.operation = "ADD"
    nt.links.new(n1.outputs["Fac"], height.inputs[0])
    nt.links.new(vor.outputs["Distance"], height.inputs[1])
    bump = _bump(nt, height.outputs["Value"], 0.45, 0.03)
    if fluting:
        wave = _new(nt, "ShaderNodeTexWave", Scale=fluting, Distortion=0.0)
        wave.wave_type, wave.bands_direction = "BANDS", "X"
        nt.links.new(co, wave.inputs["Vector"])
        bump = _bump(nt, wave.outputs["Fac"], 0.25, 0.04, bump.outputs["Normal"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def flagstones(name):
    """Worn flagstone floor: per-stone tone variation, recessed dark joints, cracks and dirt."""
    mat, nt, bsdf = _material(name)
    co = _coords(nt)
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (0.38, 0.32, 0.26, 1.0)
    brick.inputs["Color2"].default_value = (0.28, 0.24, 0.19, 1.0)
    brick.inputs["Mortar"].default_value = (0.13, 0.11, 0.09, 1.0)
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = 0.025
    brick.inputs["Brick Width"].default_value = 1.2
    brick.inputs["Row Height"].default_value = 0.6
    noise = _new(nt, "ShaderNodeTexNoise", Scale=6.0, Detail=10.0, Roughness=0.65)
    big = _new(nt, "ShaderNodeTexNoise", Scale=0.35, Detail=3.0)
    vor = _new(nt, "ShaderNodeTexVoronoi", Scale=4.0)
    vor.feature = "DISTANCE_TO_EDGE"
    for n in (brick, noise, big, vor):
        nt.links.new(co, n.inputs["Vector"])
    grime = _ramp(nt, noise.outputs["Fac"], (0.72, 0.68, 0.64), (1.0, 1.0, 1.0), (0.3, 0.7))
    patches = _ramp(nt, big.outputs["Fac"], (0.7, 0.66, 0.6), (1.0, 1.0, 1.0), (0.3, 0.75))
    cracks = _ramp(nt, vor.outputs["Distance"], (0.5, 0.47, 0.44), (1.0, 1.0, 1.0), (0.0, 0.03))
    c = _mul(nt, _mul(nt, _mul(nt, brick.outputs["Color"], grime.outputs["Color"]).outputs["Color"],
                      patches.outputs["Color"]).outputs["Color"], cracks.outputs["Color"])
    nt.links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.88
    h = nt.nodes.new("ShaderNodeMath")
    h.operation = "MULTIPLY"
    nt.links.new(brick.outputs["Fac"], h.inputs[0])
    h.inputs[1].default_value = -1.0
    b1 = _bump(nt, h.outputs["Value"], 0.6, 0.03)
    b2 = _bump(nt, noise.outputs["Fac"], 0.3, 0.02, b1.outputs["Normal"])
    nt.links.new(b2.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def skin(name, base, dark, sss_radius=(1.0, 0.25, 0.12), pores=45.0, muscle=5.0, sheen=0.0):
    mat, nt, bsdf = _material(name)
    co = _coords(nt)
    n1 = _new(nt, "ShaderNodeTexNoise", Scale=muscle, Detail=4.0)
    n2 = _new(nt, "ShaderNodeTexNoise", Scale=pores, Detail=2.0)
    for n in (n1, n2):
        nt.links.new(co, n.inputs["Vector"])
    col = _ramp(nt, n1.outputs["Fac"], dark, base, (0.3, 0.7))
    nt.links.new(col.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Subsurface Weight"].default_value = 0.25
    bsdf.inputs["Subsurface Radius"].default_value = sss_radius
    bsdf.inputs["Subsurface Scale"].default_value = 0.04
    bsdf.inputs["Roughness"].default_value = 0.48
    if sheen:
        bsdf.inputs["Sheen Weight"].default_value = sheen
    b1 = _bump(nt, n1.outputs["Fac"], 0.25, 0.05)
    b2 = _bump(nt, n2.outputs["Fac"], 0.12, 0.004, b1.outputs["Normal"])
    nt.links.new(b2.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def metal(name, color, rough=(0.25, 0.45), hammered=30.0, scratches=True):
    mat, nt, bsdf = _material(name)
    co = _coords(nt)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    n = _new(nt, "ShaderNodeTexNoise", Scale=8.0, Detail=6.0)
    vor = _new(nt, "ShaderNodeTexVoronoi", Scale=hammered)
    for t in (n, vor):
        nt.links.new(co, t.inputs["Vector"])
    r = _ramp(nt, n.outputs["Fac"], (rough[0],) * 3, (rough[1],) * 3)
    nt.links.new(r.outputs["Color"], bsdf.inputs["Roughness"])
    b = _bump(nt, vor.outputs["Distance"], 0.18, 0.01)
    if scratches:
        w = _new(nt, "ShaderNodeTexWave", Scale=60.0, Distortion=8.0)
        nt.links.new(co, w.inputs["Vector"])
        b = _bump(nt, w.outputs["Fac"], 0.08, 0.004, b.outputs["Normal"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def cloth(name, color, weave=120.0, sheen=0.35, folds=0.0):
    mat, nt, bsdf = _material(name)
    co = _coords(nt)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Sheen Weight"].default_value = sheen
    w1 = _new(nt, "ShaderNodeTexWave", Scale=weave)
    w1.bands_direction = "X"
    w2 = _new(nt, "ShaderNodeTexWave", Scale=weave)
    w2.bands_direction = "Z"
    for t in (w1, w2):
        nt.links.new(co, t.inputs["Vector"])
    b = _bump(nt, w1.outputs["Fac"], 0.12, 0.003)
    b = _bump(nt, w2.outputs["Fac"], 0.12, 0.003, b.outputs["Normal"])
    if folds:
        f = _new(nt, "ShaderNodeTexWave", Scale=folds, Distortion=3.0)
        f.bands_direction = "X"
        nt.links.new(co, f.inputs["Vector"])
        b = _bump(nt, f.outputs["Fac"], 0.5, 0.04, b.outputs["Normal"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def plain(name, color, rough=0.6, emission=None, strength=0.0, metallic=0.0):
    mat, nt, bsdf = _material(name)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def finished_materials() -> dict:
    """The finished palette. Keys mirror the blockout palette where the role is the same."""
    return {
        "stone": stone("lk_stone", fluting=0.0),
        "pillar_stone": stone("lk_pillar", fluting=9.0),
        "shrine_stone": stone("lk_shrine", a=(0.40, 0.34, 0.27), b=(0.24, 0.20, 0.16), scale=5.0),
        "floor": flagstones("lk_floor"),
        "shrine_dark": plain("lk_shrine_dark", (0.02, 0.018, 0.015), 0.9),
        "asura_skin": skin("lk_asura_skin", base=(0.55, 0.05, 0.035), dark=(0.30, 0.02, 0.015)),
        "asura_cloth": cloth("lk_asura_cloth", (0.26, 0.025, 0.02), folds=6.0),
        "iron": metal("lk_iron", (0.22, 0.20, 0.19), rough=(0.28, 0.5)),
        "gold": metal("lk_gold", (0.86, 0.60, 0.20), rough=(0.18, 0.35), hammered=40.0, scratches=False),
        "leather": cloth("lk_leather", (0.12, 0.06, 0.03), weave=40.0, sheen=0.1),
        "ivory": stone("lk_ivory", a=(0.80, 0.74, 0.60), b=(0.62, 0.55, 0.43), scale=12.0, crack_scale=30.0, dirt=0.75),
        "eye": plain("lk_eye", (0.9, 0.35, 0.05), 0.3, emission=(1.0, 0.32, 0.04), strength=6.0),
        "hair": plain("lk_hair", (0.03, 0.025, 0.02), 0.7),
        "ascetic_skin": skin("lk_ascetic_skin", base=(0.26, 0.40, 0.56), dark=(0.16, 0.25, 0.36),
                             sss_radius=(0.4, 0.5, 1.0)),
        "white_cloth": cloth("lk_white_cloth", (0.78, 0.74, 0.66), folds=9.0),
        "beads": plain("lk_beads", (0.09, 0.07, 0.065), 0.5),      # dark, low saturation: never reads as gold
    }


def banner(name, color):
    """Dyed cloth banner: saturated base (kept for colour tracking), weave and a few folds."""
    return cloth(name, color, weave=90.0, sheen=0.2, folds=4.0)


# --- world, lighting, atmosphere -----------------------------------------------------------------------------


def cinematic_world(scene, haze_density=0.0):
    """Dusk sky gradient (warm horizon, dusky violet-grey zenith; no saturated blue) and light volumetric haze."""
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.35
    co = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(co.outputs["Generated"], sep.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (1.0, 0.62, 0.36, 1.0)
    els[1].position, els[1].color = 0.6, (0.48, 0.40, 0.44, 1.0)
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    if haze_density > 0:
        vol = nt.nodes.new("ShaderNodeVolumePrincipled")
        vol.inputs["Density"].default_value = haze_density
        vol.inputs["Anisotropy"].default_value = 0.55
        vol.inputs["Color"].default_value = (1.0, 0.92, 0.82, 1.0)
        nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return world


def haze_volume(scene, bounds_min=(-7.5, -22.0, 0.0), bounds_max=(7.5, 16.0, 9.0), density=0.006):
    """Bounded volumetric haze (an untagged, volume-only box around the courtyard). Unlike a world volume it leaves
    the sky visible and the sun unattenuated outside the box; with no surface shader it does not enter the depth or
    object-index passes (verified by the export's depth-convention check and the index pass)."""
    size = [b - a for a, b in zip(bounds_min, bounds_max)]
    center = [(a + b) / 2 for a, b in zip(bounds_min, bounds_max)]
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    box = bpy.context.active_object
    box.name = "lk_haze"
    box.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    mat = bpy.data.materials.new("lk_haze")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = density
    vol.inputs["Anisotropy"].default_value = 0.55
    vol.inputs["Color"].default_value = (1.0, 0.92, 0.82, 1.0)
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    box.data.materials.append(mat)
    box.visible_shadow = True
    return box


def cinematic_lights(scene, key_rotation_deg=(64.0, 0.0, -32.0)):
    """Low warm key sun (long shadows, shafts through the haze), weak cool fill, warm rim behind the actors."""
    out = []
    sun = bpy.data.objects.new("lk_key_sun", bpy.data.lights.new("lk_key_sun", "SUN"))
    sun.data.energy, sun.data.color, sun.data.angle = 6.0, (1.0, 0.76, 0.52), math.radians(1.5)
    sun.rotation_euler = [math.radians(a) for a in key_rotation_deg]
    out.append(sun)
    fill = bpy.data.objects.new("lk_fill", bpy.data.lights.new("lk_fill", "AREA"))
    fill.data.energy, fill.data.color, fill.data.size = 600.0, (0.58, 0.64, 0.82), 10.0
    fill.location, fill.rotation_euler = (0.0, -16.0, 6.0), (math.radians(65), 0.0, 0.0)
    out.append(fill)
    rim = bpy.data.objects.new("lk_rim", bpy.data.lights.new("lk_rim", "AREA"))
    rim.data.energy, rim.data.color, rim.data.size = 2500.0, (1.0, 0.70, 0.45), 4.0
    rim.location, rim.rotation_euler = (-2.0, 4.0, 5.5), (math.radians(-55), 0.0, math.radians(180))
    out.append(rim)
    for o in out:
        scene.collection.objects.link(o)
    return out


def cinematic_render_look(scene):
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - High Contrast"
    scene.view_settings.exposure = -0.3


# --- geometry helpers (shared by the finished characters) -----------------------------------------------------


def _active():
    return bpy.context.active_object


def _smooth(o, subdiv=1):
    if subdiv:
        mod = o.modifiers.new("subd", "SUBSURF")
        mod.levels = mod.render_levels = subdiv
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def tapered(r1, r2, depth, loc, mat, rot=(0.0, 0.0, 0.0), verts=20, subdiv=1):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=depth, location=loc, rotation=rot, vertices=verts)
    o = _active()
    o.data.materials.append(mat)
    return _smooth(o, subdiv)


def ball(r, loc, mat, scale=(1.0, 1.0, 1.0), subdiv=0):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=32, ring_count=16)
    o = _active()
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    return _smooth(o, subdiv)


def rounded_box(size, loc, mat, bevel=0.08, subdiv=1):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = _active()
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    mod = o.modifiers.new("bevel", "BEVEL")
    mod.width, mod.segments = bevel, 3
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=mod.name)
    o.data.materials.append(mat)
    return _smooth(o, subdiv)


def torus(major, minor, loc, mat, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=loc, rotation=rot,
                                     major_segments=32, minor_segments=10)
    o = _active()
    o.data.materials.append(mat)
    return _smooth(o, 0)


def horn(base, tip_dir, length, r, mat, segments=5, curl=0.35):
    """A curved horn: a chain of tapering cones bending toward +Z/outward."""
    parts = []
    x, y, z = base
    dx, dy, dz = tip_dir
    for i in range(segments):
        t = i / segments
        seg = length / segments
        rr1, rr2 = r * (1 - t), r * (1 - (i + 1) / segments) + 0.004
        ang = math.atan2(math.hypot(dx, dy), dz) + curl * t
        az = math.atan2(dy, dx)
        cx = x + math.sin(ang) * math.cos(az) * seg / 2
        cy = y + math.sin(ang) * math.sin(az) * seg / 2
        cz = z + math.cos(ang) * seg / 2
        parts.append(tapered(rr1, rr2, seg * 1.05, (cx, cy, cz), mat, rot=(0.0, ang, az), verts=16, subdiv=0))
        x += math.sin(ang) * math.cos(az) * seg
        y += math.sin(ang) * math.sin(az) * seg
        z += math.cos(ang) * seg
    return parts


def spikes(center, radius, mat, count=10, length=0.17, r=0.06, seed=3):
    rng = random.Random(seed)
    out = []
    golden = math.pi * (3 - math.sqrt(5))
    for i in range(count):
        yv = 1 - (i + 0.5) * 2 / count
        rad = math.sqrt(1 - yv * yv)
        th = golden * i + rng.uniform(-0.1, 0.1)
        d = (math.cos(th) * rad, math.sin(th) * rad, yv)
        loc = tuple(c + di * (radius + length / 2 - 0.02) for c, di in zip(center, d))
        ang = math.acos(max(-1.0, min(1.0, d[2])))
        az = math.atan2(d[1], d[0])
        out.append(tapered(r, 0.0, length, loc, mat, rot=(0.0, ang, az), verts=12, subdiv=0))
    return out


# --- showcase additions (2026-10-03; the M3-A functions above are unchanged) ----------------------------------


def creature_skin(name, base, dark, cavity=(0.05, 0.01, 0.008), sss_radius=(1.0, 0.3, 0.15), sss=0.3, rough=0.46,
                  muscle=4.0, pores=60.0):
    """Skin with cavity darkening (AO) and a little sheen, for sculpted metaball bodies."""
    mat, nt, bsdf = _material(name)
    co = _coords(nt)
    n1 = _new(nt, "ShaderNodeTexNoise", Scale=muscle, Detail=5.0, Roughness=0.55)
    n2 = _new(nt, "ShaderNodeTexNoise", Scale=pores, Detail=2.0)
    for n in (n1, n2):
        nt.links.new(co, n.inputs["Vector"])
    col = _ramp(nt, n1.outputs["Fac"], dark, base, (0.3, 0.72))
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.12
    cav = _ramp(nt, ao.outputs["AO"], cavity, (1.0, 1.0, 1.0), (0.35, 0.95))
    c = _mul(nt, col.outputs["Color"], cav.outputs["Color"])
    nt.links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Subsurface Weight"].default_value = sss
    bsdf.inputs["Subsurface Radius"].default_value = sss_radius
    bsdf.inputs["Subsurface Scale"].default_value = 0.05
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Sheen Weight"].default_value = 0.15
    b1 = _bump(nt, n1.outputs["Fac"], 0.3, 0.04)
    b2 = _bump(nt, n2.outputs["Fac"], 0.1, 0.003, b1.outputs["Normal"])
    nt.links.new(b2.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def worn_metal(name, color, wear=(0.55, 0.52, 0.48), rough=(0.32, 0.6), grime=0.45, hammered=25.0):
    """Dark worn metal: brighter scuffed edges (pointiness), grime in cavities (AO), hammered bump."""
    mat, nt, bsdf = _material(name)
    co = _coords(nt)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    edge = _ramp(nt, geo.outputs["Pointiness"], (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.52, 0.62))
    mix = nt.nodes.new("ShaderNodeMixRGB")
    nt.links.new(edge.outputs["Color"], mix.inputs["Fac"])
    mix.inputs["Color1"].default_value = (*color, 1.0)
    mix.inputs["Color2"].default_value = (*wear, 1.0)
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 0.08
    g = _ramp(nt, ao.outputs["AO"], (grime, grime * 0.9, grime * 0.8), (1.0, 1.0, 1.0), (0.3, 0.95))
    c = _mul(nt, mix.outputs["Color"], g.outputs["Color"])
    nt.links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 1.0
    n = _new(nt, "ShaderNodeTexNoise", Scale=12.0, Detail=6.0)
    vor = _new(nt, "ShaderNodeTexVoronoi", Scale=hammered)
    for t in (n, vor):
        nt.links.new(co, t.inputs["Vector"])
    r = _ramp(nt, n.outputs["Fac"], (rough[0],) * 3, (rough[1],) * 3)
    nt.links.new(r.outputs["Color"], bsdf.inputs["Roughness"])
    b = _bump(nt, vor.outputs["Distance"], 0.2, 0.008)
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def gradient_bone(name, root, tip, rough=0.42, rings=18.0):
    """Horn / tusk: colour from `root` to `tip` along the tube's UV V (0 root -> 1 tip), growth rings as bump."""
    mat, nt, bsdf = _material(name)
    uv = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs["Vector"])
    col = _ramp(nt, sep.outputs["Y"], root, tip, (0.05, 0.85))
    noise = _new(nt, "ShaderNodeTexNoise", Scale=30.0, Detail=4.0)
    nt.links.new(_coords(nt), noise.inputs["Vector"])
    streak = _ramp(nt, noise.outputs["Fac"], (0.78, 0.76, 0.72), (1.0, 1.0, 1.0), (0.3, 0.7))
    c = _mul(nt, col.outputs["Color"], streak.outputs["Color"])
    nt.links.new(c.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    wave = _new(nt, "ShaderNodeTexWave", Scale=rings, Distortion=1.5)
    wave.bands_direction = "Y"
    nt.links.new(uv.outputs["UV"], wave.inputs["Vector"])
    b = _bump(nt, wave.outputs["Fac"], 0.3, 0.006)
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def fire(name, color=(1.0, 0.42, 0.08), core=(1.0, 0.82, 0.45), strength=18.0, scale=4.0, mask=(-0.15, 0.25)):
    """A still flame: emission from a noise-broken vertical gradient (generated coords, z up), transparent outside."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(_coords(nt, "Generated"), sep.inputs["Vector"])
    noise = _new(nt, "ShaderNodeTexNoise", Scale=scale, Detail=6.0, Distortion=1.2)
    nt.links.new(_coords(nt), noise.inputs["Vector"])
    fall = nt.nodes.new("ShaderNodeMath")
    fall.operation = "SUBTRACT"
    nt.links.new(noise.outputs["Fac"], fall.inputs[0])
    nt.links.new(sep.outputs["Z"], fall.inputs[1])
    mask = _ramp(nt, fall.outputs["Value"], (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), mask)
    hue = _ramp(nt, fall.outputs["Value"], color, core, (0.0, 0.45))
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    nt.links.new(hue.outputs["Color"], em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mask.outputs["Color"], mix.inputs[0])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[1])
    nt.links.new(em.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return mat


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def dusk_world(scene, horizon=(0.95, 0.42, 0.20), mid=(0.42, 0.26, 0.28), zenith=(0.08, 0.08, 0.13), strength=0.45,
               sun_dir=(0.46, 0.80, 0.37), glow=(1.0, 0.55, 0.25), glow_power=24.0, glow_strength=2.5):
    """Low-key dusk sky: warm horizon -> dusky band -> dark zenith, plus a warm glow around `sun_dir` (pointing
    TOWARD the sun)."""
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    co = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(co.outputs["Generated"], sep.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*horizon, 1.0)
    els[1].position, els[1].color = 0.55, (*zenith, 1.0)
    band = els.new(0.12)
    band.color = (*mid, 1.0)
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(co.outputs["Generated"], dot.inputs[0])
    dot.inputs[1].default_value = _unit(sun_dir)
    clamp = nt.nodes.new("ShaderNodeMath")
    clamp.operation = "MAXIMUM"
    nt.links.new(dot.outputs["Value"], clamp.inputs[0])
    clamp.inputs[1].default_value = 0.0
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    nt.links.new(clamp.outputs["Value"], pw.inputs[0])
    pw.inputs[1].default_value = glow_power
    gs = nt.nodes.new("ShaderNodeMath")
    gs.operation = "MULTIPLY"
    nt.links.new(pw.outputs["Value"], gs.inputs[0])
    gs.inputs[1].default_value = glow_strength
    add = nt.nodes.new("ShaderNodeMixRGB")
    add.blend_type = "ADD"
    nt.links.new(gs.outputs["Value"], add.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], add.inputs["Color1"])
    add.inputs["Color2"].default_value = (*glow, 1.0)
    nt.links.new(add.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return world


def look_euler(direction):
    """Euler (XYZ) pointing an object's local -Z along `direction` (lights, cameras)."""
    from mathutils import Vector

    return Vector(direction).to_track_quat("-Z", "Y").to_euler()


def area_light(scene, name, location, target, energy, color, size, collection=None):
    light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
    light.data.energy, light.data.color, light.data.size = energy, color, size
    light.location = location
    light.rotation_euler = look_euler([t - l for t, l in zip(target, location)])
    (collection or scene.collection).objects.link(light)
    return light


def point_light(scene, name, location, energy, color, radius=0.15, collection=None):
    light = bpy.data.objects.new(name, bpy.data.lights.new(name, "POINT"))
    light.data.energy, light.data.color, light.data.shadow_soft_size = energy, color, radius
    light.location = location
    (collection or scene.collection).objects.link(light)
    return light


def sun_light(scene, name, elevation_deg, heading_deg, energy, color, angle_deg=1.2):
    """A sun whose light travels at `elevation_deg` below the horizon toward heading `heading_deg` (rotation about
    world Z of the +Y direction)."""
    sun = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
    sun.data.energy, sun.data.color, sun.data.angle = energy, color, math.radians(angle_deg)
    sun.rotation_euler = (math.radians(90.0 - elevation_deg), 0.0, math.radians(heading_deg))
    scene.collection.objects.link(sun)
    return sun
