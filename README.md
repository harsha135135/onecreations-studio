# OneCreations Studio

A locally owned cinematic production system: Blender-centred characters, choreography, camera paths and timed VFX,
with a replaceable video-generation stage (primary candidate: LTX-2.5) and narrow adapters only where measurements justify them.

**Status and next steps: [`STATUS.md`](STATUS.md)** — read it first.

| Document | Purpose |
|---|---|
| [`STATUS.md`](STATUS.md) | Current phase, milestones/gates, end goal, hard rules, session log |
| [`docs/contracts.md`](docs/contracts.md) | Conventions (units, axes, pixels, depth, time), contracts, validator codes, cache keys, Blender export bundle |
| [`docs/decisions/ADR-0001-hardware-and-compute-strategy.md`](docs/decisions/ADR-0001-hardware-and-compute-strategy.md) | 4070-first → H100 only after admission; ₹15,000 ceiling; model selection by quality |
| [`docs/research/2026-10-01-decision-v1.md`](docs/research/2026-10-01-decision-v1.md) | Full research and design document (v1 snapshot) |
| [`docs/runbooks/`](docs/runbooks) | Desktop setup (M1), admission ladders (M3), local training (M6), cloud H100 (M7) |
| [`model_registry/models.yaml`](model_registry/models.yaml) | Candidate models, roles, licenses, hashes, admission outcomes |
| [`training/`](training) | Experiment cards for T1 (FLUX.2-klein LoRA), T2-small (Wan2.1-VACE-1.3B), T2 (LTX-2.5 Union IC-LoRA) |
| [`budget/`](budget) | Spend policy and ledger (enforced by `tools/budget/ledger.py`) |

## Code layout (maps to v1 §28)

| Path | v1 §28 role |
|---|---|
| `src/onecreations/contracts/`, `schemas/` | `packages/contracts` — asset, shot, camera, action, event, backend, record and export schemas |
| `src/onecreations/timebase.py` | shared exact time + output→source TimeWarp |
| `src/onecreations/geometry/`, `src/onecreations/camera/` | camera conventions, intrinsics, trajectory/motion library (FPV import, retargeting) |
| `src/onecreations/shotpkg/` | shot-package loading and cross-reference validation (`packages/continuity` starts here) |
| `src/onecreations/cachekeys.py`, `hashing.py` | `packages/jobs` cache keys and deterministic manifests |
| `integrations/blender/` | scene validation and deterministic exports, camera import, trajectory visualizer |
| `examples/diagnostic/` | tiny rights-cleared diagnostic project |
| `tools/` | admission monitor, budget ledger, safetensors inspector, hashing, Windows env check |

## Hardware

- **Desktop (GPU work):** Windows 11, RTX 4070 12 GB, i7-14700K, 32 GB RAM.
- **Laptop (development):** macOS — docs, tooling, CPU-only tests.
- **Cloud:** H100 PCIe 80 GB for the LTX-2.5 adapter experiment only, after local gates; ≤ ₹15,000 total.

## Tooling

```bash
uv sync
uv run pytest -q                                   # all tests; Blender tests skip if Blender 4.5 isn't found
uv run pytest -q -m blender                        # only the headless-Blender contract tests
uv run onecreations validate-shot examples/diagnostic
uv run onecreations camera stats examples/diagnostic/camera/temple_dive_to_parry_v1.csv
uv run onecreations blender info
uv run onecreations blender build-diagnostic --out diag.blend
uv run onecreations blender export diag.blend --out diag_export --passes --probes
uv run onecreations blender visualize --samples diag_export/camera_samples.npz --intrinsics diag_export/export_manifest.json --velocity --save viz.blend
uv run python tools/budget/ledger.py status
uv run python tools/admission/monitor.py --label <name> --meta key=value ... -- <command>
uv run python tools/inspect_safetensors.py <file.safetensors> --lora-summary
uv run python tools/registry/hash_files.py <files...>
```

Windows only: `powershell -ExecutionPolicy Bypass -File tools\windows\check_env.ps1`

Model weights, datasets, renders and caches are never committed; they live under the data root (default `D:\onecreations\`).
