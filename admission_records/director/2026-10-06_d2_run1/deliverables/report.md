# OneCreations run d2_run1: SUCCEEDED

Request: Create a cinematic shot of a horned Asura attacking an ascetic defender with a heavy mace in an ancient ruined temple at dusk. The defender guards with a trident. Use a low orbit and push-in. Add dust, debris, sparks and floor cracks on impact.

| Stage | Status | Seconds | Note |
|---|---|---|---|
| PLAN | done | 0.03 |  |
| VALIDATE | done | 0.0 |  |
| COMPILE | done | 0.03 |  |
| BLENDER_BUILD | done | 3.87 |  |
| CONTROL_RENDER | done | 240.32 |  |
| FIRST_FRAME | done | 18.26 |  |
| PREFLIGHT_QC | done | 7.64 |  |
| LTX_GENERATE | done | 49.28 |  |
| POST_GENERATION_QC | done | 5.72 |  |
| REPAIR | done | 104.76 |  |
| VFX | done | 65.57 |  |
| COMPOSITE | done | 6.29 |  |
| GRADE | done | 1.34 |  |
| FINAL_QC | done | 10.68 |  |
| DELIVER | done | 0.37 |  |

## Director decisions

- environment: temple_courtyard_v1 (prompt, 'ruined temple')
- attacker: asura_v2 (prompt, 'horned asura')
- defender: ascetic_defender_v1 (prompt, 'defender')
- attacker.weapon: heavy_mace_v1 (prompt, 'mace')
- defender.weapon: trident_v1 (prompt, 'trident')
- attacker.action: mace_slam_v1 (prompt, 'attacking')
- defender.action: defender_guard_v1 (prompt, 'guards')
- camera: orbit_push_v1 (prompt, 'orbit')
- camera.variant: low (prompt, 'low')
- look: mythic_temple_dusk_v1 (prompt, 'dusk')
- vfx: impact_dust_v1 (prompt)
- vfx: debris_v1 (prompt)
- vfx: sparks_v1 (prompt)
- vfx: floor_cracks_v1 (prompt)
- protection: MACE -> fast_weapon_v2 (rule, 'P1')

Final video: G:\onecreations\runs\d2_run1\deliverables\final.mp4
Preview (reference | raw | final): G:\onecreations\runs\d2_run1\deliverables\preview.mp4
