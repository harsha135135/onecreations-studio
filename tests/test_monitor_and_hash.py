import hashlib
import json
import sys

from tools.admission import monitor
from tools.registry import hash_files


def test_monitor_wraps_command_and_writes_record(tmp_path):
    rc = monitor.main(["--label", "unit test", "--interval", "0.1", "--out-dir", str(tmp_path), "--notes", "ci",
                       "--meta", "frames=49", "width=512",
                       "--", sys.executable, "-c", "import time; time.sleep(0.5)"])
    assert rc == 0
    records = [json.loads(line) for line in (tmp_path / "records.jsonl").read_text().splitlines()]
    assert len(records) == 1
    rec = records[0]
    assert rec["label"] == "unit test"
    assert rec["exit_code"] == 0
    assert rec["settings"] == {"frames": "49", "width": "512"}
    assert rec["outcome"] is None and rec["provenance"] == "measured"
    assert rec["summary"]["samples"] >= 1
    assert rec["summary"]["peak_ram_used_mb"] > 0
    assert (tmp_path / rec["samples_csv"]).exists()


def test_monitor_propagates_failure_exit_code(tmp_path):
    rc = monitor.main(["--label", "fail", "--interval", "0.1", "--out-dir", str(tmp_path),
                       "--", sys.executable, "-c", "raise SystemExit(3)"])
    assert rc == 3


def test_summarize_flags():
    rows = [{"gpu_mem_used_mb": 11500, "ram_used_mb": 30000, "ram_available_mb": 2000,
             "swap_used_mb": 9000, "proc_tree_rss_mb": 20000}]
    s = monitor.summarize(rows, {"gpu_mem_used_mb": 300, "swap_used_mb": 2000})
    assert "gpu_over_target_11000mb" in s["auto_flags"]
    assert "paging_suspected" in s["auto_flags"]
    assert s["swap_growth_mb"] == 7000


def test_hash_matches_hashlib(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"onecreations" * 100_000)
    assert hash_files.sha256_file(f) == hashlib.sha256(f.read_bytes()).hexdigest()
    assert hash_files.main([str(f)]) == 0
    assert hash_files.main([str(tmp_path / "missing.bin")]) == 1
