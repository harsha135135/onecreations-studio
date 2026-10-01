"""Streaming SHA-256 of model/asset files for `model_registry/models.yaml` and dataset manifests.

    hash_files.py D:\\onecreations\\models\\ltx\\*.safetensors
    hash_files.py --json file1 file2 > hashes.json

Reads in 16 MiB chunks, so multi-GB checkpoints don't need to fit in RAM.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import sys
from pathlib import Path

CHUNK = 16 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def expand(patterns: list[str]) -> list[Path]:
    # Windows shells don't expand globs, so do it here.
    paths: list[Path] = []
    for pat in patterns:
        matches = glob.glob(pat)
        paths.extend(Path(m) for m in (sorted(matches) if matches else [pat]))
    return paths


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    results = []
    missing = 0
    for path in expand(args.files):
        if not path.is_file():
            print(f"missing: {path}", file=sys.stderr)
            missing += 1
            continue
        digest = sha256_file(path)
        results.append({"file": path.name, "path": str(path), "bytes": path.stat().st_size, "sha256": digest})
        if not args.json:
            print(f"{digest}  {path.stat().st_size:>14,}  {path}", flush=True)
    if args.json:
        print(json.dumps(results, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
