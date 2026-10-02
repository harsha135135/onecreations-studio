import base64
import hashlib
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tools.admission import comfy_run

GRAPH = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "x.safetensors"}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "a temple"}},
    "3": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise_seed": 0}},
    "4": {"class_type": "VAEDecodeTiled", "inputs": {}},
    "5": {"class_type": "SaveVideo", "inputs": {}},
}


def frame(obj) -> bytes:
    data = json.dumps(obj).encode()
    n = len(data)
    head = bytes([0x81, n]) if n < 126 else bytes([0x81, 126]) + n.to_bytes(2, "big")
    return head + data


class StubComfy:
    """Just enough of ComfyUI: /system_stats, /prompt, /history/<id>, /ws with execution events."""

    def __init__(self, fail_jobs=()):
        self.prompts, self.fail_jobs, self.done = [], set(fail_jobs), {}
        self.submitted = threading.Event()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/system_stats":
                    return self._json({"system": {"comfyui_version": "stub"}, "devices": []})
                if self.path.startswith("/history/"):
                    pid = self.path.split("/")[-1]
                    return self._json({pid: stub.done[pid]} if pid in stub.done else {})
                if self.path.startswith("/ws"):
                    return self._ws()
                self._json({}, 404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.prompts.append(body["prompt"])
                self._json({"prompt_id": f"p{len(stub.prompts)}", "number": len(stub.prompts)})
                stub.submitted.set()

            def _ws(self):
                key = self.headers["Sec-WebSocket-Key"]
                accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode())
                                          .digest()).decode()
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                self.wfile.write(frame({"type": "status", "data": {"status": {"exec_info": {"queue_remaining": 0}},
                                                                    "padding": "x" * 300}}))
                self.wfile.flush()
                served = 0
                while served < 10:
                    if not stub.submitted.wait(timeout=5):
                        return
                    stub.submitted.clear()
                    served += 1
                    pid = f"p{len(stub.prompts)}"
                    fail = len(stub.prompts) in stub.fail_jobs

                    def send(kind, **data):
                        self.wfile.write(frame({"type": kind, "data": dict(data, prompt_id=pid)}))
                        self.wfile.flush()
                        time.sleep(0.03)

                    send("execution_start", timestamp=1000)
                    for node in ("1", "2", "3"):
                        send("executing", node=node)
                    for v in (1, 2, 3):
                        send("progress", node="3", value=v, max=3)
                    if fail:
                        stub.done[pid] = {"status": {"status_str": "error", "completed": False, "messages": [
                            ["execution_start", {"timestamp": 1000}],
                            ["execution_error", {"timestamp": 2000, "node_id": "3", "node_type": "SamplerCustomAdvanced",
                                                 "exception_type": "torch.OutOfMemoryError",
                                                 "exception_message": "CUDA out of memory"}]]}, "outputs": {}}
                        send("execution_error", node_id="3")
                        continue
                    for node in ("4", "5"):
                        send("executing", node=node)
                    stub.done[pid] = {"status": {"status_str": "success", "completed": True, "messages": [
                        ["execution_start", {"timestamp": 1000}], ["execution_success", {"timestamp": 3500}]]},
                        "outputs": {"5": {"images": [{"filename": f"{pid}_00001.mp4", "subfolder": "", "type": "output"}]}}}
                    send("executing", node=None)
                    send("execution_success", timestamp=3500)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def workflow(tmp_path):
    p = tmp_path / "wf_api.json"
    p.write_text(json.dumps(GRAPH))
    return p


def test_jobs_phases_and_seeds(tmp_path, workflow):
    stub = StubComfy()
    try:
        out = tmp_path / "report.json"
        rc = comfy_run.main(["--workflow", str(workflow), "--server", stub.url, "--repeat", "2",
                             "--seed", "3/noise_seed=1000", "--report", str(out), "--timeout", "30"])
    finally:
        stub.close()
    assert rc == 0
    rep = json.loads(out.read_text())
    assert [p["3"]["inputs"]["noise_seed"] for p in stub.prompts] == [1000, 1001]
    assert len(rep["jobs"]) == 2 and rep["provenance"] == "measured"
    job = rep["jobs"][0]
    assert job["status"] == "success" and job["comfy_exec_s"] == 2.5
    assert job["overrides"] == {"3/noise_seed": 1000}
    assert job["outputs"][0]["filename"] == "p1_00001.mp4"
    assert set(job["phases_s"]) >= {"load", "text_encode", "denoise", "vae_decode", "output"}
    assert job["phases_s"]["denoise"] > 0
    assert job["denoise_steps"]["3"]["steps"] == 3
    assert [n["phase"] for n in job["nodes"]] == ["load", "text_encode", "denoise", "vae_decode", "output"]


def test_failed_job_reports_error_and_exit_code(tmp_path, workflow):
    stub = StubComfy(fail_jobs={1})
    try:
        out = tmp_path / "report.json"
        rc = comfy_run.main(["--workflow", str(workflow), "--server", stub.url, "--repeat", "2",
                             "--report", str(out), "--timeout", "30"])
    finally:
        stub.close()
    assert rc == 1
    rep = json.loads(out.read_text())
    assert len(rep["jobs"]) == 1  # stops after the first failure
    assert rep["jobs"][0]["status"] == "error"
    assert rep["jobs"][0]["error"]["exception"] == "torch.OutOfMemoryError"


def test_launch_that_dies_is_reported_with_log_events(tmp_path, workflow):
    log = tmp_path / "comfy.log"
    out = tmp_path / "report.json"
    child = "print('Total VRAM 12282 MB'); print('Requested to load LTXV'); print('Traceback: boom'); raise SystemExit(4)"
    rc = comfy_run.main(["--workflow", str(workflow), "--server", "http://127.0.0.1:9", "--ready-timeout", "20",
                         "--launch-log", str(log), "--report", str(out), "--", sys.executable, "-c", child])
    assert rc == 2
    rep = json.loads(out.read_text())
    assert "exited during startup" in rep["error"] and rep["comfy_exit_code"] == 4
    lines = [e["line"] for e in rep["log_events"]]
    assert "Requested to load LTXV" in lines and "Traceback: boom" in lines
    assert log.read_text(encoding="utf-8").count("]") >= 3  # every line carries a timestamp


def test_phase_rules_and_overrides():
    assert comfy_run.phase_of("CLIPLoader") == "load"
    assert comfy_run.phase_of("LatentUpscaleModelLoader") == "load"
    assert comfy_run.phase_of("LTXVConditioning") == "text_encode"
    assert comfy_run.phase_of("KSamplerSelect") == "denoise"
    assert comfy_run.phase_of("LTXVAudioVAEDecode") == "vae_decode"
    assert comfy_run.phase_of("ManualSigmas") == "other"
    assert comfy_run.parse_override("a1:23/noise_seed=5") == ("a1:23", "noise_seed", "5")
    g, applied = comfy_run.apply_overrides(GRAPH, ["2/text=\"x\"", "1/unet_name=y.safetensors"], None, 0)
    assert g["2"]["inputs"]["text"] == "x" and g["1"]["inputs"]["unet_name"] == "y.safetensors"
    assert GRAPH["2"]["inputs"]["text"] == "a temple"  # original untouched
    with pytest.raises(ValueError):
        comfy_run.parse_override("noslash=1")
