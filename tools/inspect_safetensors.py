"""Inspect a .safetensors file from its header only — no weights are loaded, so a 22 GB file is fine.

    inspect_safetensors.py model.safetensors                 # dtype/param totals + metadata
    inspect_safetensors.py adapter.safetensors --lora-summary # LoRA modules, ranks, alphas
    inspect_safetensors.py a.safetensors --list --grep attn   # list tensors matching a substring
    inspect_safetensors.py a.safetensors --json               # machine-readable summary

Used for the T2 admission step "inspect module names/shapes locally" (v1 §16): it tells you the Union
IC-LoRA's real rank and target modules before any GPU time is rented.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

MAX_HEADER_BYTES = 100 * 1024 * 1024
DTYPE_BYTES = {"F64": 8, "F32": 4, "F16": 2, "BF16": 2, "I64": 8, "I32": 4, "I16": 2, "I8": 1, "U8": 1,
               "BOOL": 1, "F8_E4M3": 1, "F8_E5M2": 1, "U16": 2, "U32": 4, "U64": 8}

# (down/A suffix, up/B suffix) naming conventions seen in diffusers/peft and kohya-style files.
LORA_PAIRS = [
    (".lora_A.weight", ".lora_B.weight"),
    (".lora_down.weight", ".lora_up.weight"),
    (".lora_A.default.weight", ".lora_B.default.weight"),
]
ALPHA_SUFFIX = ".alpha"


def read_header(path: Path) -> tuple[dict, dict]:
    with path.open("rb") as f:
        raw = f.read(8)
        if len(raw) != 8:
            raise ValueError("file too small to be safetensors")
        (n,) = struct.unpack("<Q", raw)
        if n <= 0 or n > MAX_HEADER_BYTES:
            raise ValueError(f"implausible header size {n}")
        header = json.loads(f.read(n).decode("utf-8"))
    metadata = header.pop("__metadata__", {}) or {}
    return header, metadata


def numel(shape: list[int]) -> int:
    return math.prod(shape) if shape else 1


def summarize(header: dict) -> dict:
    by_dtype: Counter = Counter()
    params = 0
    nbytes = 0
    for info in header.values():
        n = numel(info["shape"])
        params += n
        by_dtype[info["dtype"]] += n
        nbytes += info["data_offsets"][1] - info["data_offsets"][0]
    return {"tensors": len(header), "params": params, "data_bytes": nbytes, "params_by_dtype": dict(by_dtype)}


def lora_summary(header: dict) -> dict:
    modules: dict[str, dict] = {}
    for name, info in header.items():
        for down, up in LORA_PAIRS:
            if name.endswith(down):
                m = modules.setdefault(name[: -len(down)], {})
                m["down_shape"] = info["shape"]
            elif name.endswith(up):
                m = modules.setdefault(name[: -len(up)], {})
                m["up_shape"] = info["shape"]
    for name, info in header.items():
        if name.endswith(ALPHA_SUFFIX) and name[: -len(ALPHA_SUFFIX)] in modules:
            modules[name[: -len(ALPHA_SUFFIX)]]["has_alpha"] = True

    ranks: Counter = Counter()
    families: dict[str, set] = defaultdict(set)
    incomplete = []
    for mod, m in modules.items():
        if "down_shape" not in m or "up_shape" not in m:
            incomplete.append(mod)
            continue
        rank = m["down_shape"][0]
        if m["up_shape"][-1] != rank:
            incomplete.append(mod)
            continue
        m["rank"] = rank
        ranks[rank] += 1
        # family = module path with block indices collapsed, e.g. transformer_blocks.N.attn1.to_q
        families[re.sub(r"\.\d+\.", ".N.", mod)].add(rank)
    return {
        "lora_modules": sum(ranks.values()),
        "rank_histogram": dict(sorted(ranks.items())),
        "module_families": {k: sorted(v) for k, v in sorted(families.items())},
        "incomplete_or_mismatched": sorted(incomplete),
        "alpha_tensors": sum(1 for m in modules.values() if m.get("has_alpha")),
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", type=Path)
    p.add_argument("--lora-summary", action="store_true")
    p.add_argument("--list", action="store_true", help="list tensors with dtype and shape")
    p.add_argument("--grep", default=None, help="substring filter for --list")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    header, metadata = read_header(args.file)
    out: dict = {"file": str(args.file), "metadata": metadata, **summarize(header)}
    if args.lora_summary:
        out["lora"] = lora_summary(header)
    if args.list:
        out["tensor_list"] = [
            {"name": k, "dtype": v["dtype"], "shape": v["shape"]}
            for k, v in sorted(header.items())
            if args.grep is None or args.grep in k
        ]

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    print(f"file:     {out['file']}")
    print(f"tensors:  {out['tensors']:,}")
    print(f"params:   {out['params']:,}  ({out['data_bytes'] / 1024**3:.2f} GiB of tensor data)")
    print("dtypes:   " + ", ".join(f"{k}={v:,}" for k, v in out["params_by_dtype"].items()))
    if metadata:
        print("metadata:")
        for k, v in metadata.items():
            v = str(v)
            print(f"  {k}: {v[:200]}{'…' if len(v) > 200 else ''}")
    if args.lora_summary:
        lo = out["lora"]
        print(f"LoRA modules: {lo['lora_modules']}   alpha tensors: {lo['alpha_tensors']}")
        print(f"rank histogram: {lo['rank_histogram']}")
        print("module families (block index collapsed → ranks):")
        for fam, rks in lo["module_families"].items():
            print(f"  {fam}  {rks}")
        if lo["incomplete_or_mismatched"]:
            print(f"WARNING: {len(lo['incomplete_or_mismatched'])} incomplete/mismatched pairs, e.g. "
                  f"{lo['incomplete_or_mismatched'][:3]}")
    if args.list:
        for t in out["tensor_list"]:
            print(f"  {t['dtype']:<8} {str(t['shape']):<24} {t['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
