"""Canonical JSON and content hashes for deterministic manifests and cache keys.

Determinism means: the same logical content gives the same bytes and the same sha256, regardless of dict order,
float noise below 12 significant digits, tuples vs lists, or numpy scalars. NPZ files embed zip timestamps, so arrays
are hashed by content (`array_digest`), never by file bytes.

Stdlib + optional numpy: imported by Blender-side scripts as well as the main package.
"""

from __future__ import annotations

import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

try:  # numpy is optional for the canonicalizer itself
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None

FLOAT_SIG_DIGITS = 12
_CHUNK = 16 * 1024 * 1024


def _canon_float(x: float) -> float | int:
    if not math.isfinite(x):
        raise ValueError(f"non-finite float {x!r} cannot be canonicalized")
    if x == 0:
        return 0.0  # folds -0.0
    y = float(f"{x:.{FLOAT_SIG_DIGITS}g}")
    return y


def canonicalize(obj: Any) -> Any:
    """Convert to plain JSON types with canonical floats; Fractions become "n/d" strings."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return _canon_float(obj)
    if isinstance(obj, Fraction):
        return str(obj.numerator) if obj.denominator == 1 else f"{obj.numerator}/{obj.denominator}"
    if isinstance(obj, Mapping):
        out = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"JSON object keys must be str, got {type(k).__name__}")
            out[k] = canonicalize(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [canonicalize(v) for v in obj]
    if isinstance(obj, Path):
        return obj.as_posix()
    if _np is not None:
        if isinstance(obj, _np.ndarray):
            return canonicalize(obj.tolist())
        if isinstance(obj, _np.generic):
            return canonicalize(obj.item())
    if hasattr(obj, "model_dump"):  # pydantic models
        return canonicalize(obj.model_dump(mode="json"))
    raise TypeError(f"cannot canonicalize {type(obj).__name__}")


def canonical_json(obj: Any) -> str:
    return json.dumps(canonicalize(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def write_canonical_json(path: str | Path, obj: Any) -> None:
    """Human-readable but deterministic: sorted keys, 2-space indent, canonical floats, trailing newline."""
    text = json.dumps(canonicalize(obj), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def array_digest(arrays: Mapping[str, Any]) -> str:
    """sha256 over (name, dtype, shape, C-order bytes) of each array, in sorted name order."""
    if _np is None:  # pragma: no cover
        raise RuntimeError("numpy is required for array_digest")
    h = hashlib.sha256()
    for name in sorted(arrays):
        a = _np.ascontiguousarray(_np.asarray(arrays[name]))
        if a.dtype.byteorder == ">" or (a.dtype.byteorder == "=" and not _np.little_endian):
            a = a.astype(a.dtype.newbyteorder("<"))
        h.update(name.encode("utf-8") + b"\0")
        h.update(a.dtype.str.encode("ascii") + b"\0")
        h.update(json.dumps(list(a.shape)).encode("ascii") + b"\0")
        h.update(a.tobytes())
    return h.hexdigest()


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()
