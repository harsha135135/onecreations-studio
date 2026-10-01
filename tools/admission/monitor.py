"""Run a job (or watch the machine) and record GPU / RAM / pagefile usage for admission ladders.

    # wrap a command (everything after `--` is the job):
    monitor.py --label ltx25-r1 --meta width=512 height=320 frames=49 quant=int8-convrot steps=8 \
               --notes "official 2.5 distilled workflow" -- python run_job.py ...

    # watch while you run something by hand (e.g. queue a ComfyUI workflow), stop with Ctrl+C:
    monitor.py --label ltx25-r2-depth --attach

Writes   <out-dir>/<stamp>_<label>.csv   (one row per sample)
and appends a summary to <out-dir>/records.jsonl.

GPU numbers come from `nvidia-smi` and are *device-wide* (include display/driver memory), which is what the
v1 §18 "≤10.5–11 GB observed total" target refers to. Auto flags are heuristics; a human sets `outcome`.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import psutil
except ImportError:  # keep the tool usable for a quick look even without deps
    psutil = None

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "admission_records"
GPU_TARGET_MB = 11_000          # v1 §18 proposed upper target (observed total, 12 GB card)
PAGING_GROWTH_FLAG_MB = 1_024   # swap/pagefile growth that suggests paging during the job
MB = 1024 * 1024


def query_gpu() -> dict | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--query-gpu=name,driver_version,memory.used,memory.total,utilization.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip().splitlines()
    except (subprocess.SubprocessError, OSError):
        return None
    if not out:
        return None
    name, driver, used, total, util, power = [x.strip() for x in out[0].split(",")]

    def num(x: str) -> float | None:
        try:
            return float(x)
        except ValueError:
            return None

    return {"name": name, "driver": driver, "mem_used_mb": num(used), "mem_total_mb": num(total),
            "util_pct": num(util), "power_w": num(power)}


def tree_rss_mb(pid: int | None) -> float | None:
    if psutil is None or pid is None:
        return None
    try:
        root = psutil.Process(pid)
        procs = [root] + root.children(recursive=True)
    except psutil.Error:
        return None
    total = 0
    for p in procs:
        try:
            total += p.memory_info().rss
        except psutil.Error:
            pass
    return total / MB


def sample(t0: float, pid: int | None) -> dict:
    row: dict = {"t_s": round(time.monotonic() - t0, 2)}
    gpu = query_gpu()
    row["gpu_mem_used_mb"] = gpu["mem_used_mb"] if gpu else None
    row["gpu_util_pct"] = gpu["util_pct"] if gpu else None
    row["gpu_power_w"] = gpu["power_w"] if gpu else None
    if psutil is not None:
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        row["ram_used_mb"] = round((vm.total - vm.available) / MB)
        row["ram_available_mb"] = round(vm.available / MB)
        row["swap_used_mb"] = round(sw.used / MB)
    else:
        row["ram_used_mb"] = row["ram_available_mb"] = row["swap_used_mb"] = None
    rss = tree_rss_mb(pid)
    row["proc_tree_rss_mb"] = round(rss) if rss is not None else None
    return row


def host_info() -> dict:
    gpu = query_gpu()
    info = {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()} {platform.version()}",
        "cpu": platform.processor() or platform.machine(),
        "python": sys.version.split()[0],
        "gpu_name": gpu["name"] if gpu else None,
        "gpu_driver": gpu["driver"] if gpu else None,
        "gpu_mem_total_mb": gpu["mem_total_mb"] if gpu else None,
    }
    if psutil is not None:
        info["ram_total_mb"] = round(psutil.virtual_memory().total / MB)
        info["swap_total_mb"] = round(psutil.swap_memory().total / MB)
    return info


def peak(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return max(vals) if vals else None


def summarize(rows: list[dict], baseline: dict) -> dict:
    s = {
        "peak_gpu_mem_used_mb": peak(rows, "gpu_mem_used_mb"),
        "peak_ram_used_mb": peak(rows, "ram_used_mb"),
        "min_ram_available_mb": min((r["ram_available_mb"] for r in rows if r.get("ram_available_mb") is not None),
                                    default=None),
        "peak_swap_used_mb": peak(rows, "swap_used_mb"),
        "peak_proc_tree_rss_mb": peak(rows, "proc_tree_rss_mb"),
        "baseline_gpu_mem_used_mb": baseline.get("gpu_mem_used_mb"),
        "baseline_swap_used_mb": baseline.get("swap_used_mb"),
        "samples": len(rows),
    }
    flags = []
    if s["peak_gpu_mem_used_mb"] is not None and s["peak_gpu_mem_used_mb"] > GPU_TARGET_MB:
        flags.append(f"gpu_over_target_{GPU_TARGET_MB}mb")
    if s["peak_swap_used_mb"] is not None and baseline.get("swap_used_mb") is not None:
        growth = s["peak_swap_used_mb"] - baseline["swap_used_mb"]
        s["swap_growth_mb"] = growth
        if growth > PAGING_GROWTH_FLAG_MB:
            flags.append("paging_suspected")
    if s["peak_gpu_mem_used_mb"] is None:
        flags.append("no_gpu_data")
    s["auto_flags"] = flags
    return s


def run(label: str, cmd: list[str], attach: bool, interval: float, out_dir: Path, notes: str,
        settings: dict | None = None) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_label = "".join(c if c.isalnum() or c in "-_." else "_" for c in label)
    csv_path = out_dir / f"{stamp}_{safe_label}.csv"

    t0 = time.monotonic()
    started = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    baseline = sample(t0, None)
    rows: list[dict] = []
    stop = threading.Event()
    proc: subprocess.Popen | None = None
    exit_code: int | None = None
    interrupted = False

    def sampler() -> None:
        while not stop.is_set():
            rows.append(sample(t0, proc.pid if proc else None))
            stop.wait(interval)

    if cmd:
        proc = subprocess.Popen(cmd)
    thread = threading.Thread(target=sampler, daemon=True)
    thread.start()
    try:
        if proc is not None:
            exit_code = proc.wait()
        else:
            print(f"[monitor] attached; sampling every {interval}s — press Ctrl+C to stop", flush=True)
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        interrupted = True
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                exit_code = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                exit_code = proc.wait()
    finally:
        stop.set()
        thread.join(timeout=interval + 15)
    wall = time.monotonic() - t0

    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    record = {
        "label": label,
        "started_at": started,
        "wall_seconds": round(wall, 1),
        "mode": "attach" if not cmd else "command",
        "command": cmd,
        "exit_code": exit_code,
        "interrupted": interrupted,
        "notes": notes,
        "settings": settings or {},
        "host": host_info(),
        "summary": summarize(rows, baseline),
        "samples_csv": csv_path.name if rows else None,
        "outcome": None,  # set by a human: "pass" | "partial" | "fail", plus reason
        "provenance": "measured",
    }
    with (out_dir / "records.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(json.dumps(record["summary"], indent=2))
    print(f"[monitor] wrote {csv_path.name if rows else '(no samples)'} and appended records.jsonl")
    if exit_code is not None:
        return exit_code
    return 130 if interrupted else 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", required=True)
    p.add_argument("--attach", action="store_true", help="no command: sample until Ctrl+C")
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    p.add_argument("--notes", default="")
    p.add_argument("--meta", nargs="*", default=[], metavar="KEY=VALUE",
                   help="structured settings for the record (resolution, frames, quant, steps, hashes, ...)")
    args = p.parse_args(argv)
    settings = {}
    for item in args.meta:
        key, sep, value = item.partition("=")
        if not sep or not key:
            p.error(f"--meta expects KEY=VALUE, got {item!r}")
        settings[key] = value
    if not cmd and not args.attach:
        p.error("give a command after `--`, or use --attach")
    if cmd and args.attach:
        p.error("--attach cannot be combined with a command")
    if psutil is None:
        print("[monitor] warning: psutil missing — RAM/pagefile not recorded (run `uv sync`)", file=sys.stderr)
    return run(args.label, cmd, args.attach, args.interval, args.out_dir, args.notes, settings)


if __name__ == "__main__":
    sys.exit(main())
