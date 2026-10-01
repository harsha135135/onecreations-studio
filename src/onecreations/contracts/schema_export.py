"""Write / check JSON Schemas for every contract in `schemas/`."""

from __future__ import annotations

import json
from pathlib import Path

from onecreations.contracts import CONTRACTS

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = REPO_ROOT / "schemas"


def render_schemas() -> dict[str, str]:
    out = {}
    for name, model in sorted(CONTRACTS.items()):
        schema = model.model_json_schema(mode="validation")
        schema["$id"] = f"onecreations/{name}.schema.json"
        out[f"{name}.schema.json"] = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return out


def write_schemas(directory: Path = SCHEMA_DIR) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for fname, text in render_schemas().items():
        path = directory / fname
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def stale_schemas(directory: Path = SCHEMA_DIR) -> list[str]:
    """Names of schema files that are missing or differ from the current contracts."""
    stale = []
    for fname, text in render_schemas().items():
        path = directory / fname
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(fname)
    return stale
