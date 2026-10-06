# D1 — Autonomous director foundation — 2026-10-06

**Question:** can the manually configured Showcase v1 production process be represented as a structured,
deterministic shot specification that the system executes automatically?

**Answer:** yes, for the Showcase class. A supported natural-language request is now translated into a DirectorPlan,
then a ShotSpec, then a CompiledShot, and the Blender scene, control passes, first frame, masks and preflight QC are
built automatically. The declarative Showcase v1 ShotSpec compiles to exactly the hand-configured production setup.

**No LTX generation was run in D1.** Everything here is software engineering plus deterministic Blender work. The
architecture is in `docs/decisions/ADR-0002-prompt-directed-production.md`.

## 1. What was built

| Piece | File | Role |
|---|---|---|
| Contracts | `src/onecreations/contracts/director.py` (DirectorPlan, ShotSpec, CompiledShot, ProcessingPolicy, SemanticObject, QCCheck, Stage, GenerationJob), `contracts/registry.py` (AssetRegistry) | the four separated layers; schemas exported |
| Asset registry | `library/registry.yaml` | 18 real entries (§3) |
| Registry access | `director/registry.py` | load, kind-checked lookup, alias matching |
| Action events | `director/actions.py` | presets → events (CONTACT = APEX + strike_frames), phases, timeline version, event → phase edge |
| Camera presets | `director/camera.py` | variants, overrides, admitted envelope, sampling (the engine's exact math) |
| Policies | `director/policies.py` | rules P1–P5 with provenance; explicit overrides |
| Validation | `director/validate.py` | 25 issue codes (SPEC_* and ENGINE_*) checked before execution |
| Compiler | `director/compiler.py` | ShotSpec → CompiledShot (scene build, layers, LTX job, grade, masks, QC, stages) |
| Prompt composition | `director/prompt.py` | appearance-only generation prompt from registry fragments |
| Interpreter | `director/interpreter.py` | `keyword_v1`: request → DirectorPlan, with an explicit unsupported lexicon |
| Planner | `director/planner.py` | DirectorPlan → ShotSpec |
| QC | `director/qc.py` | QC profile as data; preflight evaluator |
| Executor | `director/executor.py` | `dry_run` (no processes); `preflight` (Blender → controls → first frame → masks → QC; stops before LTX) |
| CLI | `onecreations director plan / validate / compile`, `onecreations generate "…" --dry-run | --preflight DIR` | without a mode, `generate` refuses: prompt → final video is not orchestrated yet |
| Engine | `integrations/blender/build_showcase_scene.py --config scene_build.json` | the compiled config overrides placements, camera, look, strike timing, effect components, flash, layers and ids; with no config the build is exactly Showcase v1 |
| Example | `examples/director/showcase_v1.shotspec.json` | Showcase v1 declared semantically |

## 2. Showcase v1 decision decomposition

**A** user intent · **B** director decision · **C** asset decision · **D** technical pipeline decision ·
**E** derived value · **F** validation / QC rule

| Decision (where it lived) | Class | Where it lives now |
|---|---|---|
| a demon attacks an ascetic with a mace, in a temple, at dusk, with an orbit, dust and debris | A | the request |
| attacker = asura, defender = ascetic, slam, guard, low orbit, dusk look, effect set | B | DirectorPlan (with evidence) → ShotSpec |
| continuous asura and ascetic bodies, armour, materials (`build_asura`, `build_defender`) | C | registry characters (builder, oc_id, pass index, anchors, material groups) |
| mace geometry, mounted on the `mace` bone (constants in the builder) | C | registry weapon `heavy_mace_v1` (parts, class, mount) |
| trident built into the defender mesh | C | `trident_v1`, integrated (not separable) |
| temple layout, upgrades, banners, braziers | C | `temple_courtyard_v1` (semantic parts GROUND, SHRINE, …) |
| ROOT_AT (−1.8, −4.0), yaw 30°, defender (0.70, −3.55), yaw −65°, scale 1.08 | B (staging) / C (defaults) | ShotSpec placements, or the asset's default placement |
| strike keys, strike_frames = 6, apex Blender 24, contact 30 | C (preset) + B (param) | `mace_slam_v1` (events, phases, parameter range 2–9) |
| apex f23, contact f29, hold end f34, end f48 | E | resolved by the compiler (CompiledShot.events) |
| CAMERA_MOVE target (−0.5, −3.9, 1.5), 24°, 7.6 → 6.3 m, 2.25 → 1.95 m, 32 mm | B (preset, variant) + E (target from anchor + offset) | `orbit_push_v1` low variant, `target: ASURA + (1.3, 0.1, 1.5)` |
| LOOK / SUN dicts (lights, haze, exposure, AgX) | C | `mythic_temple_dusk_v1` |
| 768×448, 49 frames, 8 steps, seed 1000, workflow, prompt text | D (profile) + B (seed) + E (prompt) | `ltx25_union_768_v1`; prompt composed from fragments, identical to the original |
| mace protection: 90° layer, swept-band temporal ghost fill, gain, soften, all frames | D | protection rule `fast_weapon_v2` |
| protect the mace (chosen by hand after M2-B / M3-A) | B → rule | P1 (heavy weapon, estimated peak ≥ 0.7 head widths/frame) |
| impact_fx at the `impact` phase start, flash for 5 frames, `FRAMES − 29` | E | effect events → `strike.CONTACT` → phase edge and duration |
| dust density / decay, flash energies, effect seed | C | vfx entries and compiler defaults |
| shake at frames 29–31 | E | `camera_jolt_v1` offsets from CONTACT |
| finish parameters | C | grade `showcase_v1` |
| joints ≤ 4.5 px, camera ≤ 1 mm, clearance ≥ 1 m, isolated background pixels, in-frame | F | QC profile `showcase_class_preflight_v1` |
| colour trackers (gold_deep / crimson) | F (not valid for this look) | not used; QC is geometric |

## 3. Registered assets (all real, all from Showcase v1 and earlier runs)

- **Characters:** `asura_showcase_v1` (rigged, m2b_humanoid_16bone) · `ascetic_defender_v1` (static)
- **Weapons:** `heavy_mace_v1` (rig bone `mace`) · `trident_v1` (integrated)
- **Environment:** `temple_courtyard_v1`
- **Actions:** `mace_slam_v1` (strike_frames 2–9) · `defender_guard_v1`
- **Camera:** `orbit_push_v1` (low / high)
- **Effects:** `impact_dust_v1` · `debris_v1` · `sparks_v1` · `floor_cracks_v1` · `impact_flash_v1` · `camera_jolt_v1`
- **Look:** `mythic_temple_dusk_v1`
- **Grade:** `showcase_v1`
- **Generation profile:** `ltx25_union_768_v1`
- **Protection rule:** `fast_weapon_v2`

Effect components can now be enabled individually. The builder still creates every component and then removes the
disabled ones, so the seeded random draws, and therefore the Showcase effects, are unchanged.

## 4. Showcase v1 reproduction (the key D1 test)

`examples/director/showcase_v1.shotspec.json` compiles to:

| Compared with the archived Showcase v1 records | Result |
|---|---|
| CompositeManifest (3 layers, every protection and ghost setting) | equal (validated contract) |
| ActionTimeline (phases, version, actors) | equal |
| CONTACT frame | 29 = archived `impact_output_frame` |
| placements (root, yaw, defender, yaw) | equal |
| look parameters, sun | equal |
| camera move (all keys) | equal |
| 49 camera samples vs the archived CSV | max position difference **0.0 m** |
| grade (finish parameters + shake [29, 30, 31]) | equal |
| LTX workflow after overrides, prompt text, seed 1000, 8 steps | **byte-identical** to `workflows/ltx25/showcase_v1_api.json` |
| Blender build from the compiled config vs the hand-configured build (Blender test) | every built-spec field identical; layers equal as a contract |
| export of the compiled build vs the actual Showcase v1 generation export | camera, object and joint array digests **identical** |

**Correction recorded here.** In the Showcase session, a "re-export digest" check compared keys that do not exist in
the export manifest, so it was vacuous (`None == None`). Redone properly in D1, the rebuilt default scene and the
compiled scene both reproduce the generation export's camera, object and joint digests. The Showcase conclusion
(inputs unchanged by the rebuild) holds.

## 5. Semantic events and CONTACT propagation

- **Unit test:** with `strike_frames: 8`, CONTACT resolves to 31. The impact_fx and flash layer triggers resolve to
  31 through the timeline, the impact_fx duration becomes 18, and the jolt starts at 31.
- **Blender test:** the builder's own timeline equals the compiled one; Blender reports contact frame 32 (= output
  31); the built layers equal the compiled layers.
- **No hand-maintained frame numbers remain.** Effects, compositor, grade and QC all refer to `strike.CONTACT`.

## 6. Prompt interpreter (`keyword_v1`) and scope

**Vocabulary** (registry aliases):

| Slot | Aliases |
|---|---|
| characters | asura / demon / rakshasa / horned demon / demon warrior; ascetic / defender / sage / yogi / shiva / lord shiva / mahadeva (proper names become the semantic id, e.g. SHIVA) |
| weapons | mace / gada / club; trident / trishula |
| environment | temple / courtyard / ruined temple / ancient temple / ruins / shrine |
| attack | slam / strike / smash / attack(s) / swing / hit / bash; "slow / deliberate" → strike_frames 9 |
| guard | guard / block / parry / defend / brace / stands (block or parry adds a warning: there is no weapon contact) |
| camera | orbit / push-in / dolly in / circling; variant low / low angle / heroic or high / raised |
| look | dusk / sunset / twilight / evening / golden hour / dark fantasy / mythological |
| effects | dust / debris / sparks / cracks / flash / jolt; none named → the action's default impact package |

**Unsupported, refused with a reason** (curated lexicon):
- other creatures and people (dragon, robot, horse, knight …)
- other places (Tokyo, city, forest, castle …)
- other weapons (sword, axe, spear, bow, gun …)
- other actions (flying, running, jumping, kicking …)
- other camera moves (FPV, drone, crane, zoom, pan, close-up …)
- other times and weather (night, rain, snow …)
- other effects (explosion, lightning, magic …)

Missing slots fall back to the only registered option, with a warning, because the engine always stages both actors.

**Examples (tested):**
- **D1 supported example:** asura / ascetic / slam / guard / low orbit / dusk / dust + debris; MACE → fast_weapon_v2.
- **The brief's example:** "Lord Shiva … Asura attacks … Shiva blocks …" is supported. The defender's semantic id is
  SHIVA, and the plan warns that block contact is unsupported.
- **"A dragon flying over Tokyo at night, shot with an FPV drone":** refused (character, environment, action, camera,
  look).

## 7. Dry run and preflight

**Dry run:** `onecreations generate "<supported prompt>" --dry-run` prints the plan decisions with their evidence,
the events, per-object policies, layers, generation settings, prompt and stages. A test patches `subprocess` to
prove no process starts. Without `--dry-run` or `--preflight`, `generate` refuses.

**Preflight, executed once:** `onecreations generate "<D1 supported example>" --preflight
G:\onecreations\renders\d1_preflight\prompt_001 --shot-id d1_prompt_001` completed end to end in **47 s**:
- build 3.1 s
- export with passes and probes 30.9 s
- depth control 2.9 s
- 64-sample first frame 2.8 s
- masks and QC

**All 10 preflight QC checks passed:**

| Check | Result |
|---|---|
| events resolved | yes |
| timeline equals engine | yes |
| weapon-bone projection | **2.11 px** (limit 4.5) |
| root stationary | 0.0 m |
| camera contract | 4.7e-7 m / 3.8e-5° |
| clearance | 1.95 m |
| actors in frame, all 49 frames | demon ≥ 24,438 px, defender ≥ 7,800 px, no border contact |
| mace visible | ≥ 2,471 px |
| depth | 14 isolated background pixels |
| first frame | same scene, camera and frame |

The post-generation checks (weapon attachment, contact timing, appearance persistence, layer integrity) and the final
check are declared but not run.

**Evidence** (G:, not in Git):
- `first_frame.png` and `depth_control.mp4`
- `masks/` with 12 semantic objects at f0 / APEX f23 / CONTACT f29 / f48
- `evidence.png` (first frame, control at CONTACT, ASURA mask, MACE mask)

The plan, ShotSpec, CompiledShot, masks index and report are in `admission_records/director/`.

## 8. Tests, resources, storage

- **Tests:** 180 pass, including the Blender tests (was 162). New: `tests/test_director.py` (16) and
  `tests/test_blender_director.py` (2). Schemas are current (4 new).
- **Spend and downloads:** ₹0; no cloud, no training, no downloads.
- **Compute:** no LTX run; GPU used only for a 64-sample still.
- **Storage:** G: 237.76 → 237.50 GiB. The preflight directory is 271 MB, mostly two 36 MB `.blend` files and the
  export. Showcase artifacts are kept.

## 9. Conservative capability claim

OneCreations can translate supported natural-language shot requests into a structured production specification and
automatically assemble the corresponding deterministic scene and control configuration from its existing asset
library. Executed once from a prompt: the Blender scene, control passes, depth control, first frame, semantic masks
and preflight QC, with LTX not invoked.

It cannot yet produce a final video from a prompt in one command. Generation, repair compositing, effect-layer
rendering and grade are proven stages that the director does not orchestrate yet. It also cannot handle shots
outside the registered library.

## 10. Remaining work before true prompt → final video

1. **Orchestrate the remaining proven stages after preflight:** the generation (submit the compiled workflow through
   the monitor), effect and protection layer renders, the hybrid composite, the grade and delivery.
2. **Implement the post-generation QC** declared here: grip attachment, contact timing, protected-layer integrity,
   appearance persistence.
3. **Make repair conditional on QC,** with retry rules as data.
4. **Masked edits:** per-material masks for sub-object edits.
5. **Wider library:** more assets, actions and cameras (each a registry entry with evidence).
6. **An LLM director** behind the same `DirectorPlan` interface.

## 11. Proposed D2

**D2: one-command prompt → final video for the Showcase class.**
- **Orchestration:** extend `onecreations generate` from preflight through generation (one LTX run, with monitor
  telemetry), layer renders, the hybrid composite, the grade and delivery, all driven only by the CompiledShot.
- **QC:** implement the post-generation checks.
- **Acceptance (pre-registered):** the D1 supported prompt yields a final video equivalent in structure to Showcase
  v1. D2 should also be the first consumer of the M3-B character upgrade, delivered as a new registry character
  version.
