"""Locate and run Blender headless with the scripts in `integrations/blender/`.

Blender lookup order: $ONECREATIONS_BLENDER → Blender 4.5 LTS default install paths (macOS, Windows) → any other
Blender app/`blender` on PATH. The project pins Blender 4.5 LTS; other versions run but are reported.
"""

from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INTEGRATIONS = REPO_ROOT / "integrations" / "blender"
ENV_VAR = "ONECREATIONS_BLENDER"
PINNED_SERIES = "4.5"


class BlenderError(RuntimeError):
    pass


def _candidates() -> list[str]:
    out = []
    env = os.environ.get(ENV_VAR)
    if env:
        out.append(env)
    system = platform.system()
    if system == "Darwin":
        out += ["/Applications/Blender 4.5.app/Contents/MacOS/Blender", "/Applications/Blender.app/Contents/MacOS/Blender"]
    elif system == "Windows":
        base = os.environ.get("ProgramFiles", r"C:\Program Files")
        out += sorted(glob.glob(os.path.join(base, "Blender Foundation", "Blender 4.5*", "blender.exe")), reverse=True)
        out += sorted(glob.glob(os.path.join(base, "Blender Foundation", "Blender*", "blender.exe")), reverse=True)
    which = shutil.which("blender")
    if which:
        out.append(which)
    return out


def find_blender() -> Path | None:
    for c in _candidates():
        if c and Path(c).is_file():
            return Path(c)
    return None


def blender_version(exe: Path) -> str:
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, timeout=60)
    first = (out.stdout or "").strip().splitlines()
    return first[0].replace("Blender ", "").strip() if first else "unknown"


def is_pinned(version: str) -> bool:
    return version.startswith(PINNED_SERIES)


def run_script(script: str, args: list[str], blend: str | Path | None = None, exe: Path | None = None,
               timeout: int = 900) -> subprocess.CompletedProcess:
    """Run integrations/blender/<script> in background mode; raises BlenderError with the output tail on failure."""
    exe = exe or find_blender()
    if exe is None:
        raise BlenderError(f"Blender not found; set {ENV_VAR} or install Blender {PINNED_SERIES} LTS")
    script_path = INTEGRATIONS / script
    if not script_path.is_file():
        raise BlenderError(f"no such integration script: {script_path}")
    cmd = [str(exe), "--background", "--factory-startup"]
    if blend is not None:
        cmd.append(str(blend))
    cmd += ["--python-exit-code", "1", "--python", str(script_path), "--", *map(str, args)]
    env = dict(os.environ, PYTHONNOUSERSITE="1")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + "\n" + proc.stderr).strip().splitlines()[-40:])
        raise BlenderError(f"{script} failed (exit {proc.returncode}):\n{tail}")
    return proc
