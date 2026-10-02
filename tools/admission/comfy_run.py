"""Submit an API-format workflow to ComfyUI, wait for each job, and report timings per job and per phase.

    # ComfyUI already running on the default port:
    comfy_run.py --workflow workflows/ltx25/r1_t2v_api.json --repeat 2 --seed "75/noise_seed=1000" --report r1.json

    # launch ComfyUI as a child (so tools/admission/monitor.py sees its memory), run, then shut it down;
    # everything after `--` is the ComfyUI command line:
    monitor.py --label ltx25-r1a --meta ... -- python tools/admission/comfy_run.py --workflow ... --report ... \
        --launch-log G:/onecreations/experiments/.../comfy.log -- G:/.../python.exe main.py --port 8188 ...

Per job: wall time from submit to completion, ComfyUI's own execution time, outputs and status. Per phase
(from the websocket `executing`/`progress` events, classified by node class): load, text_encode, denoise,
vae_decode, output, other; plus denoise step times. With --launch, startup time and timestamped ComfyUI log lines
(model load/offload messages, OOM, tracebacks) are recorded too. Node timings measure when ComfyUI runs each node;
model weights may move to the GPU lazily inside a later node, which the log events show.

Exit code: 0 all jobs succeeded · 1 a job failed or was interrupted · 2 ComfyUI not reachable/launch died · 3 timeout.
Stdlib only (psutil, if present, is used to stop the launched process tree).
"""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import json
import os
import queue
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

PHASE_RULES = [  # first match on the node class name wins
    ("load", ("Loader",)),
    ("text_encode", ("TextEncode", "Conditioning")),
    ("denoise", ("SamplerCustom", "KSampler")),
    ("vae_decode", ("Decode",)),
    ("output", ("Save", "VideoCombine", "CreateVideo")),
]
LOG_EVENT_RE = re.compile(
    r"(Requested to load|loaded (completely|partially)|Model .*(loaded|unloaded)|unload|offload|lowvram|"
    r"Prompt executed in|out of memory|OutOfMemory|Traceback|Error|To see the GUI|Starting server|"
    r"Total VRAM|pytorch version|Set vram state|Device:)", re.IGNORECASE)


def phase_of(class_type: str) -> str:
    for phase, keys in PHASE_RULES:
        if any(k in class_type for k in keys):
            return phase
    return "other"


def parse_override(text: str) -> tuple[str, str, str]:
    """'75/noise_seed=1000' -> ('75', 'noise_seed', '1000'). Node ids may contain ':' (subgraphs), never '/'."""
    key, sep, value = text.partition("=")
    node, sep2, name = key.rpartition("/")
    if not sep or not sep2 or not node or not name:
        raise ValueError(f"expected NODE/INPUT=VALUE, got {text!r}")
    return node, name, value


def apply_overrides(graph: dict, sets: list[str], seed: str | None, job_index: int) -> tuple[dict, dict]:
    g = copy.deepcopy(graph)
    applied = {}
    for item in sets:
        node, name, value = parse_override(item)
        if node not in g:
            raise KeyError(f"--set: node {node!r} not in workflow")
        try:
            g[node]["inputs"][name] = json.loads(value)
        except json.JSONDecodeError:
            g[node]["inputs"][name] = value
        applied[f"{node}/{name}"] = g[node]["inputs"][name]
    if seed:
        node, name, value = parse_override(seed)
        if node not in g:
            raise KeyError(f"--seed: node {node!r} not in workflow")
        g[node]["inputs"][name] = int(value) + job_index
        applied[f"{node}/{name}"] = g[node]["inputs"][name]
    return g, applied


# --- minimal websocket client (server->client text frames; enough for ComfyUI's /ws) -------------------------

class WebSocket:
    def __init__(self, host: str, port: int, path: str, timeout: float = 10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        self.buf = b""
        while b"\r\n\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("websocket handshake: connection closed")
            self.buf += chunk
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0] + b" ":
            raise ConnectionError(f"websocket handshake refused: {head.splitlines()[0]!r}")
        self.sock.settimeout(None)

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self) -> tuple[int, bytes] | None:
        """Next complete message as (opcode, payload); None when the server closes."""
        message, first_opcode = b"", None
        while True:
            b1, b2 = self._read(2)
            fin, opcode, masked, n = b1 & 0x80, b1 & 0x0F, b2 & 0x80, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if masked else None
            data = self._read(n)
            if mask:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if opcode == 0x8:
                return None
            if opcode == 0x9:  # ping -> masked pong
                m = os.urandom(4)
                payload = bytes(c ^ m[i % 4] for i, c in enumerate(data[:125]))
                self.sock.sendall(bytes([0x8A, 0x80 | len(payload)]) + m + payload)
                continue
            if opcode == 0xA:
                continue
            if opcode != 0:
                first_opcode = opcode
            message += data
            if fin:
                return first_opcode or 0x1, message

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


# --- ComfyUI HTTP ---------------------------------------------------------------------------------------------

class Comfy:
    def __init__(self, server: str):
        self.server = server.rstrip("/")
        u = urllib.parse.urlparse(self.server)
        self.host, self.port = u.hostname or "127.0.0.1", u.port or 80

    def get(self, path: str, timeout: float = 10.0):
        with urllib.request.urlopen(self.server + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path: str, body: dict, timeout: float = 30.0):
        req = urllib.request.Request(self.server + path, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")

    def ready(self) -> bool:
        try:
            self.get("/system_stats", timeout=3)
            return True
        except (OSError, ValueError):
            return False


class Launched:
    """ComfyUI started as a child; its output is timestamped into a log and scanned for memory/error events."""

    def __init__(self, cmd: list[str], log_path: Path | None, t0: float):
        self.t0, self.events, self.lines = t0, [], 0
        self.log = log_path.open("w", encoding="utf-8") if log_path else None
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     encoding="utf-8", errors="replace", bufsize=1,
                                     env=dict(os.environ, PYTHONUNBUFFERED="1"))
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self) -> None:
        for raw in self.proc.stdout:
            t = round(time.monotonic() - self.t0, 3)
            for line in raw.replace("\r", "\n").splitlines():
                if not line.strip():
                    continue
                self.lines += 1
                if self.log:
                    self.log.write(f"[{t:10.3f}] {line}\n")
                    self.log.flush()
                if LOG_EVENT_RE.search(line) and len(self.events) < 2000:
                    self.events.append({"t_s": t, "line": line.strip()[:400]})

    def alive(self) -> bool:
        return self.proc.poll() is None

    def stop(self) -> int | None:
        if self.alive():
            procs = []
            if psutil is not None:
                try:
                    procs = psutil.Process(self.proc.pid).children(recursive=True)
                except psutil.Error:
                    procs = []
            self.proc.terminate()
            for p in procs:
                try:
                    p.terminate()
                except psutil.Error:
                    pass
            try:
                self.proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            if psutil is not None:
                psutil.wait_procs(procs, timeout=15)
        self.thread.join(timeout=10)
        if self.log:
            self.log.close()
        return self.proc.returncode


def node_timings(events: list[tuple[float, dict]], graph: dict, prompt_id: str) -> dict:
    """Per-node and per-phase durations from websocket events of one prompt (times in s since its submit)."""
    starts: list[tuple[float, str | None]] = []
    cached: list[str] = []
    progress: dict[str, list[float]] = {}
    for t, msg in events:
        data = msg.get("data") or {}
        if data.get("prompt_id") not in (None, prompt_id):
            continue
        kind = msg.get("type")
        if kind == "executing":
            starts.append((t, data.get("node")))
        elif kind == "execution_cached":
            cached += [str(n) for n in data.get("nodes") or []]
        elif kind == "progress" and data.get("node") is not None:
            progress.setdefault(str(data["node"]), []).append(t)
        elif kind in ("execution_success", "execution_error", "execution_interrupted"):
            starts.append((t, None))
    nodes, phases = [], {}
    for (t, node), (t_next, _) in zip(starts, starts[1:]):
        if node is None:
            continue
        cls = (graph.get(str(node)) or {}).get("class_type", "?")
        dur = round(t_next - t, 3)
        nodes.append({"node": str(node), "class_type": cls, "phase": phase_of(cls), "start_s": round(t, 3),
                      "duration_s": dur})
        phases[phase_of(cls)] = round(phases.get(phase_of(cls), 0.0) + dur, 3)
    steps = {}
    for n in nodes:
        ts = progress.get(n["node"])
        if n["phase"] == "denoise" and ts:
            gaps = [b - a for a, b in zip([n["start_s"]] + ts[:-1], ts)]
            later = sorted(gaps[1:]) or gaps
            steps[n["node"]] = {"steps": len(ts), "first_step_s": round(gaps[0], 3),
                                "median_step_s": round(later[len(later) // 2], 3)}
    return {"phases_s": phases, "nodes": nodes, "cached_nodes": cached, "denoise_steps": steps}


def history_summary(hist: dict) -> dict:
    status = hist.get("status") or {}
    stamps = {m[0]: (m[1] or {}).get("timestamp") for m in status.get("messages") or [] if isinstance(m, list)}
    start = stamps.get("execution_start")
    end = stamps.get("execution_success") or stamps.get("execution_error") or stamps.get("execution_interrupted")
    outputs = []
    for node, out in (hist.get("outputs") or {}).items():
        for key, items in out.items():
            if isinstance(items, list):
                outputs += [{"node": node, "kind": key, "filename": i.get("filename"), "subfolder": i.get("subfolder")}
                            for i in items if isinstance(i, dict) and i.get("filename")]
    error = None
    for m in status.get("messages") or []:
        if isinstance(m, list) and m and m[0] == "execution_error":
            d = m[1] or {}
            error = {"node": d.get("node_id"), "class_type": d.get("node_type"),
                     "exception": d.get("exception_type"), "message": str(d.get("exception_message", ""))[:2000]}
    return {"status": status.get("status_str"), "completed": status.get("completed"),
            "comfy_exec_s": round((end - start) / 1000.0, 3) if start and end else None,
            "outputs": outputs, "error": error}


def run_job(comfy: Comfy, ws_events: "queue.Queue | None", graph: dict, client_id: str, timeout: float) -> dict:
    events: list[tuple[float, dict]] = []
    if ws_events is not None:
        while not ws_events.empty():
            ws_events.get_nowait()
    t_submit = time.monotonic()
    code, resp = comfy.post("/prompt", {"prompt": graph, "client_id": client_id})
    if code != 200 or "prompt_id" not in resp:
        return {"status": "rejected", "http_status": code, "error": resp, "wall_s": 0.0}
    pid = resp["prompt_id"]
    deadline = t_submit + timeout
    done = False
    while time.monotonic() < deadline and not done:
        if ws_events is not None:
            try:
                t, msg = ws_events.get(timeout=1.0)
                events.append((t - t_submit, msg))
                data = msg.get("data") or {}
                if data.get("prompt_id") == pid and (
                        msg.get("type") in ("execution_success", "execution_error", "execution_interrupted")
                        or (msg.get("type") == "executing" and data.get("node") is None)):
                    done = True
                continue
            except queue.Empty:
                pass
        else:
            time.sleep(1.0)
        try:
            hist = comfy.get(f"/history/{pid}")
            if pid in hist and (hist[pid].get("status") or {}).get("completed") is not None:
                done = True
        except (OSError, ValueError):
            pass
    wall = round(time.monotonic() - t_submit, 3)
    if not done:
        return {"prompt_id": pid, "status": "timeout", "wall_s": wall}
    hist = {}
    for _ in range(10):
        try:
            hist = comfy.get(f"/history/{pid}").get(pid, {})
            if hist:
                break
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    job = {"prompt_id": pid, "wall_s": wall, **history_summary(hist)}
    if events:
        job.update(node_timings(events, graph, pid))
    return job


def start_ws_reader(comfy: Comfy, client_id: str) -> "queue.Queue | None":
    try:
        ws = WebSocket(comfy.host, comfy.port, f"/ws?clientId={client_id}")
    except OSError as e:
        print(f"[comfy_run] websocket unavailable ({e}); phase timings off, polling /history", file=sys.stderr)
        return None
    q: queue.Queue = queue.Queue()

    def reader() -> None:
        try:
            while True:
                m = ws.recv()
                if m is None:
                    return
                opcode, payload = m
                if opcode == 0x1:
                    try:
                        q.put((time.monotonic(), json.loads(payload.decode("utf-8"))))
                    except ValueError:
                        pass
        except (OSError, ConnectionError):
            return

    threading.Thread(target=reader, daemon=True).start()
    return q


def wait_ready(comfy: Comfy, launched: Launched | None, t0: float, ready_timeout: float, report: dict) -> int:
    while not comfy.ready():
        if launched and not launched.alive():
            report["error"] = f"ComfyUI exited during startup (code {launched.proc.returncode})"
            return 2
        if time.monotonic() - t0 > ready_timeout:
            report["error"] = "ComfyUI not reachable before --ready-timeout"
            return 2
        time.sleep(0.5)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    launch: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, launch = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workflow", type=Path, required=True, help="API-format workflow JSON (ComfyUI 'Export (API)')")
    p.add_argument("--server", default="http://127.0.0.1:8188")
    p.add_argument("--repeat", type=int, default=1, help="jobs in sequence (first = cold if ComfyUI just started)")
    p.add_argument("--seed", default=None, metavar="NODE/INPUT=BASE", help="job i uses BASE+i (else ComfyUI caches)")
    p.add_argument("--set", action="append", default=[], metavar="NODE/INPUT=JSON", help="input override, all jobs")
    p.add_argument("--timeout", type=float, default=3600.0, help="per job, seconds")
    p.add_argument("--ready-timeout", type=float, default=600.0)
    p.add_argument("--launch-log", type=Path, default=None, help="with a launch command: timestamped ComfyUI log")
    p.add_argument("--report", type=Path, default=None, help="write the JSON report here")
    args = p.parse_args(argv)

    t0 = time.monotonic()
    graph = json.loads(args.workflow.read_text(encoding="utf-8"))
    report = {"started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
              "workflow": str(args.workflow), "workflow_sha256": hashlib.sha256(args.workflow.read_bytes()).hexdigest(),
              "server": args.server, "launch": launch or None, "jobs": [], "provenance": "measured"}
    comfy = Comfy(args.server)
    launched = Launched(launch, args.launch_log, t0) if launch else None
    try:
        rc = wait_ready(comfy, launched, t0, args.ready_timeout, report)
        if rc == 0:
            report["startup_s"] = round(time.monotonic() - t0, 3) if launched else None
            try:
                report["system_stats"] = comfy.get("/system_stats")
            except (OSError, ValueError):
                pass
            client_id = uuid.uuid4().hex
            ws_events = start_ws_reader(comfy, client_id)
            for i in range(args.repeat):
                g, applied = apply_overrides(graph, args.set, args.seed, i)
                job = {"index": i, "overrides": applied, **run_job(comfy, ws_events, g, client_id, args.timeout)}
                report["jobs"].append(job)
                print(f"[comfy_run] job {i}: {job.get('status')} wall {job.get('wall_s')} s "
                      f"comfy {job.get('comfy_exec_s')} s phases {job.get('phases_s')}", flush=True)
                if job.get("status") == "timeout":
                    rc = 3
                    break
                if job.get("status") != "success":
                    rc = 1
                    break
    finally:
        if launched:
            report["comfy_exit_code"] = launched.stop()
            report["log_events"] = launched.events
            report["launch_log"] = str(args.launch_log) if args.launch_log else None
        report["total_wall_s"] = round(time.monotonic() - t0, 3)
        text = json.dumps(report, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(text, encoding="utf-8")
            print(f"[comfy_run] wrote {args.report}")
        else:
            print(text)
    return rc


if __name__ == "__main__":
    sys.exit(main())
