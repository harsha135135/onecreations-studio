# OneCreations run d3_run1: FAILED

Request: Create a cinematic shot of a horned Asura attacking an ascetic defender with a heavy mace in an ancient ruined temple at dusk. The defender parries the blow with a trident. Use a low orbit and push-in.

| Stage | Status | Seconds | Note |
|---|---|---|---|
| PLAN | done | 0.01 |  |
| VALIDATE | done | 0.0 |  |
| COMPILE | done | 0.01 |  |
| BLENDER_BUILD | cached | 0.0 |  |
| CONTROL_RENDER | cached | 0.0 |  |
| FIRST_FRAME | cached | 0.0 |  |
| PREFLIGHT_QC | cached | 0.0 |  |
| LTX_GENERATE | cached | 0.0 |  |
| POST_GENERATION_QC | failed | 5.87 | StageError: post-generation QC: non-repairable failure in contact_timing |
| REPAIR | not_run |  |  |
| VFX | not_run |  |  |
| COMPOSITE | not_run |  |  |
| GRADE | not_run |  |  |
| FINAL_QC | not_run |  |  |
| DELIVER | not_run |  |  |

## Director decisions

- environment: temple_courtyard_v1 (prompt, 'ruined temple')
- attacker: asura_v2 (prompt, 'horned asura')
- defender: ascetic_defender_v2 (prompt, 'defender')
- attacker.action: mace_slam_v1 (prompt, 'attacking')
- defender.action: trident_parry_v1 (prompt, 'parries')
- attacker.action: mace_strike_blocked_v1 (rule)
- attacker.weapon: heavy_mace_v1 (prompt, 'mace')
- defender.weapon: trident_v2 (prompt, 'trident')
- camera: orbit_push_v1 (prompt, 'orbit')
- camera.variant: low (prompt, 'low')
- look: mythic_temple_dusk_v1 (prompt, 'dusk')
- vfx: sparks_v1 (default)
- vfx: clash_flash_v1 (default)
- protection: MACE -> fast_weapon_v2 (rule, 'P1')
- protection: TRIDENT -> contact_weapon_v1 (rule, 'P6')

Not delivered: POST_GENERATION_QC - StageError: post-generation QC: non-repairable failure in contact_timing
