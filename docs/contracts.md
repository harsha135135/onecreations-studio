# Contracts and conventions (Session A)

The shot package — not a prompt — is the central object (v1 §7). Every contract is a pydantic v2 model in
`src/onecreations/contracts/` with a generated JSON Schema in `schemas/` (`uv run onecreations schemas export`;
a test fails if they drift). Unknown fields are errors, so typos in hand-written manifests are caught.

## Conventions

| Topic | Convention | Enforced by |
|---|---|---|
| Units | meters | contracts (`units: meters`) |
| World | Blender Z-up, right-handed | `geometry/conventions.py` |
| Camera pose | **camera_to_world** 4×4 in **Blender camera axes**: −Z forward, +Y up, +X right | `validate_rigid` rejects scale/shear and det −1 (flipped axis) |
| Other camera frames | OpenCV/COLMAP: `c2w_cv = c2w_blender · diag(1,−1,−1,1)`; OpenGL camera axes = Blender's | `blender_c2w_to_opencv`, `opencv_c2w_to_blender` |
| Rotation | quaternion **wxyz**, sign-continuous along a trajectory | `geometry/quat.py` |
| Intrinsics | Blender params (lens, sensor, sensor fit, shift, resolution, pixel aspect, clip) **and** derived K | `geometry/intrinsics.py` (AUTO fit uses sensor *width*, like Blender) |
| Pixels | origin top-left, +u right, +v down, pixel centres at +0.5; image rows top-down | exporter flips Blender's bottom-up images |
| Depth | **planar** view-space depth (meters); `inf` = background | exporter measures Blender's convention by ray casts before converting |
| Time | exact rationals (`Fraction`), JSON `"9/10"`; fps `{num, den}` | `timebase.py`, `RationalTime` |
| Time domains | **source time** (choreography t = 0) for camera motions, choreography, events; **output time** for shot frames | `TimeWarp` (output → source, monotonic, holds allowed) |
| Blender frames | source time 0 = scene `frame_start`; frame = frame_start + source × scene fps (fractional allowed) | `oc_export.py` |
| Determinism | canonical JSON (sorted keys, 12 significant digits, `-0.0 → 0.0`); arrays hashed by content, not NPZ bytes | `hashing.py` |

## Contracts

| Contract | File | Notes |
|---|---|---|
| `Project` | `contracts/assets.py` | Index of assets and relative paths to all other manifests |
| `CharacterAsset` | `contracts/assets.py` | v1 §9 design authority: measurements, handedness, skeleton map, weapon sockets (4×4), symbols that must not mirror, state variants, rights |
| `CameraMotion` | `contracts/camera.py` | v1 §10: samples file (.npz/.csv), intrinsics, constraints, provenance incl. **scale** and **up-axis** status |
| `ActionTimeline` | `contracts/action.py` | Roles → asset IDs (motion survives character swaps), phases, contact intervals linked to events |
| `TimeWarpModel` | `contracts/action.py` | Output → source time keys |
| `VFXEvent` | `contracts/vfx.py` | v1 §11 schema (the event *system* is Session B) |
| `Shot` | `contracts/shot.py` | v1 §13 + `generation.controls`, `reference_count`, `width/height` |
| `ModelBackend` | `contracts/backend.py` | What a backend supports; filled from measured admission, never assumed |
| `ExperimentRecord` | `contracts/records.py` | Validates `training/**/experiment-card*.yaml` |
| `AdmissionRecord` | `contracts/records.py` | Validates `admission_records/records.jsonl` lines from `tools/admission/monitor.py` |
| `ExportManifest` | `contracts/export.py` | Blender export bundle (below) |

## Shot validation (`onecreations validate-shot PROJECT_DIR`)

Issue codes (errors unless noted): `SHOT_UNKNOWN_{ASSET,SCENE_STATE,LIGHTING,REFERENCE,CHOREOGRAPHY,CAMERA,TIMEWARP,EVENT,REGION,BACKEND}`,
`SHOT_ACTOR_ASSET_MISSING`, `SHOT_FRAME_COUNT_NOT_INTEGER`, `SHOT_TIMEWARP_DOMAIN`, `SHOT_CHOREO_COVERAGE`,
`SHOT_CAMERA_COVERAGE`, `SHOT_CAMERA_UNLOADED` (warning), `SHOT_EVENT_OUTSIDE`, `SHOT_CONTACT_EVENT_MISSING`
(warning if the contact isn't required), `SHOT_CONTACT_EVENT_MISMATCH`, `SHOT_REGION_CONFLICT`,
`SHOT_BACKEND_UNSUPPORTED_CONTROL`, `SHOT_TOO_MANY_REFERENCES`, `SHOT_BACKEND_DIMENSIONS`,
`SHOT_BACKEND_FRAMES` (warning: needs windowing), `SHOT_BACKEND_NOT_ADMITTED` (warning), `SHOT_SOURCE_START_IGNORED` (warning).

The validator also reports each event's exact output time and frame position (e.g. the diagnostic wall impact lands at
frame 909/7 ≈ 129.857, not on a frame), which VFX, audio and review all share.

## Cache keys (`cachekeys.py`)

`control_render ← scene, camera, choreography, timewarp, control_export_settings` ·
`vfx_cache ← scene, choreography, timewarp, events` · `audio_placement ← events, timewarp, audio_assets` ·
`beauty_render ← scene, camera, choreography, timewarp, lighting, vfx_cache, render_settings` ·
`generation ← control_render, references, backend_profile, prompt, seed, generation_settings` ·
`composite ← beauty_render, generation, masks, composite_recipe`.
Changing the camera invalidates control/beauty/generation/composite but not VFX or audio (tested).

## Blender export bundle

Produced by `integrations/blender/oc_export.py` (or `onecreations blender export`), verified by
`onecreations.blender_bundle.load_bundle` (manifest content hash + every array digest).

| File | Contents |
|---|---|
| `export_manifest.json` | Blender version, conventions, scene, shot (fps, frame count, timewarp keys), per-frame output/source time and exact Blender frame, camera intrinsics + K, tagged objects, depth-convention check, `deferred` list, `content_sha256` |
| `camera_samples.npz` | `t` (output s), `t_source`, `blender_frame`, `position`, `quaternion_wxyz`, `c2w`, `lens_mm`, `shift_x`, `shift_y` |
| `objects.npz` | `<oc_id>` → (F,4,4) matrix_world for each object with an `oc_id` custom property |
| `joints.npz` | `<oc_id>.heads` / `<oc_id>.tails` → (F,J,3) world-space bones of tagged armatures |
| `probes.npz` | `points`, `ndc` from Blender's `world_to_camera_view` (cross-check only, `--probes`) |
| `passes.npz` | `depth_m` planar float32 (`inf` background), `object_index` uint16, `normal` world-space float32 (`--passes`) |

Pass rendering: Cycles CPU, 1 sample, seed 0, pixel filter width 0.01, no denoising or motion blur, so every pixel
is one ray through (nearly) its centre. That makes the index and depth passes exact per pixel (not antialiased, v1 §10).

### Measured on the Mac (Blender 4.5.14 LTS, macOS arm64, diagnostic scene, 160×90)

- Cycles depth pass is **planar**: median error 1.4 µm against ray-cast planar depth vs 0.29 m against Euclidean (45 probes).
- Our projection (exported c2w + K, including lens shift) matches Blender's `world_to_camera_view` to ≈ 0.0005 px.
- Unprojecting the stored depth puts floor pixels at z = 0 and wall pixels at y = 6 within ≈ 6 µm.
- The cube's object-index mask matches its projected bounding box within 0.5 px; the occluder pass is visible as a
  drop in cube pixels at frames 12–13.
- Two exports of the same scene produce identical canonical manifests (same content hash, same array digests).

These are CPU/Blender measurements for the data contract, not GPU or model measurements. Re-run `pytest -m blender`
on the Windows desktop to confirm the same on Blender 4.5 for Windows.

### Measured on the Windows desktop (Blender 4.5.14 LTS, Windows 11 x64, same scene, 2026-10-02)

The 11 headless-Blender tests pass. Below are the actual values the tests only threshold, with pass rendering on Cycles CPU as above:

| Check | Mac | Windows |
|---|---|---|
| Depth convention (45 probes) | planar; median error 1.4 µm planar vs 0.29 m Euclidean | planar; **1.54 µm** planar vs **0.286 m** Euclidean |
| Projection vs `world_to_camera_view` | ≈ 0.0005 px | **0.00053 px** (3.3e-6 normalized); depth agrees to 1.0e-5 m |
| Plane recovery from depth | ≈ 6 µm | floor \|z\| ≤ **4.6 µm**, wall \|y − 6\| ≤ **5.3 µm** (all 24 frames) |
| Cube mask vs projected box | within 0.5 px | **0.459 px**; cube pixels 499 (f0) → 216 (f12–13 occluded) → 550 (f16) |
| Same-machine export determinism | identical canonical manifests | identical (content hash, camera and pass digests) |

Windows digests are recorded so a later cross-platform comparison is possible. Byte-identity across platforms is still deferred, see below.
The values are content_sha256 `1c853bef…b53985`, camera samples `38ee76b4…528d1d79` and passes `43321b4c…31c54f76`. Full values are in
`docs/measurements/2026-10-02-desktop-m1.md`.

**Re-export vs rebuild** (measured 2026-10-03 on the M2-A scene):
- Re-exporting a saved `.blend` is bit-identical: same content hash.
- Rebuilding the scene from its script and then exporting gives bit-identical depth and object index, and identical camera, object and probe arrays. The normal pass differs by float32 noise (|Δ| ≤ 1.5e-5), so the content hash changes.
- Depth controls derive from depth only, so they are unaffected.

**Camera import → export in a real scene** (M2-C, 2026-10-03):
- An authored `CameraMotion` (`CameraTrajectory` npz, one sample per frame, fixed 35 mm, SHA-256 pinned in the manifest) was keyed onto the scene camera by `oc_import_camera` and exported by `oc_export`.
- The export reproduces it within 4.8e-7 m and 2.6e-5°, with the lens fixed and t = k/24 exact.
- Camera clearance was checked two ways: exact Blender closest-point distances, and `camera.retarget.clearance_report` on AABB proxies.
- Details: `docs/measurements/2026-10-03-m2c-camera.md`.

**Joints in a real scene** (M2-B, 2026-10-03): `joints.npz` from a rigidly skinned 16-bone rig is consistent with the render.
- The weapon bone's tail, projected with `geometry.intrinsics.project`, lands within 0.57 px (median 0.30) of the weapon object's object-index centroid (pixel centres at +0.5).
- Unkeyed bones move 0.0 m.
- Details: `docs/measurements/2026-10-03-m2b-temple-strike.md`.

## Deferred in Session A (documented, not built)

Cryptomatte decoding · beauty/AOV production renders · motion vectors · joint visibility flags ·
pass rendering at sub-frame source times (refused by the exporter unless `--allow-subframe-passes`) ·
collision-aware automatic path adjustment (clearance is reported, not fixed) · COLMAP distortion models,
rolling shutter, gyro alignment · visualizer preview rendering (viewport .blend only) · byte-identical outputs
across platforms (canonical manifests/hashes only).
