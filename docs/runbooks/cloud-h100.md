# Runbook M7 — H100 admission and Gate A pilot (gates G5, G6)

**Locked until G4 passes and the owner explicitly approves the launch in-session.**
Budget rules: ADR-0001 D4. Hard ceiling ₹15,000 total; Gate A ₹5,000 cumulative.

## Before renting anything

1. `git pull`; confirm `STATUS.md` shows G4 passed.
2. Check live prices (Runpod or chosen provider) for H100 PCIe 80 GB, H100 SXM, A100 80 GB, H200. Compute the **payable** rate
   in ₹ including taxes/fees.
3. Pre-check every job:
   ```bash
   uv run python tools/budget/ledger.py status
   uv run python tools/budget/ledger.py check --gpu h100_pcie --hours 2 --rate <live ₹/h> --extra-inr <storage>
   ```
   A REFUSED result means don't launch. OK still needs the owner's go-ahead.
4. Prepare everything locally first (ADR-0001 D7): pinned trainer commit, data + manifests + caches packaged,
   trainer-native config, launch script with a wall-clock limit, validation script.
5. Never commit API keys; keep them in environment variables or the provider CLI's own store.

## G5 — H100 admission (≤ 2 h, ≤ ₹710 at planning rate)

One H100 PCIe 80 GB, single GPU. Inside the 2 h:

1. Environment up from the pinned commit; upload data/caches.
2. Load the exact full model + Union adapter (or the chosen IC-LoRA init).
3. **One forward/backward step** → save → reload.
4. Run the **target inference graph** (ideally the same one admitted on the 4070) with the saved adapter, and compare against
   the untouched adapter on 2–3 held-out clips.
5. Record step time, peak memory and the output comparison.

Stop and stop the pod if any step fails. Shape compatibility alone is not a pass; output and control behaviour must survive.
H200 replaces the H100 only if 80 GB OOM is **measured** (it costs ~1.59× per hour).

## Gate A pilot (≤ 8 H100 h total including G5)

Allocation from v1 §17: 2 h admission/caching + 4 h short adaptation + 2 h validation/export.

- Wall-clock auto-stop on every job; checkpoints every N steps; download checkpoints + logs; **stop the pod immediately after export**;
  delete paid volumes when done (storage keeps billing).
- Log each charge: `ledger.py add --provider <p> --category gpu --gpu h100_pcie --hours <h> --amount-inr <actual> --description "..."`.
- Back on the 4070: evaluate the pilot adapter on held-out shots vs. the pretrained conditioned graph (v1 §21 adapter experiment).

## G6 — Gate B decision (owner)

Request Gate B only if the pilot **beats the pretrained conditioned graph on held-out acceptance** without worsening hard
constraints. The owner sets `"gate_b_unlocked": true` (with `gate_b_unlocked_by`, `_on`, `_evidence`) in `budget/policy.json`
and commits it. Gate B allocation: up to 32 H100 h total (2 + 10 first run + 10 continuation/ablation + 8 validation + 2 export).

If the pilot doesn't beat pretrained: keep the pretrained graph, keep the remaining money unspent, record the negative result.
