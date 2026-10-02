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


def test_parse_gpu_line_reads_pcie_fields():
    g = monitor.parse_gpu_line("NVIDIA GeForce RTX 4070, 591.74, 129, 12282, 3, 3.04, 1, 16, 4, 16")
    assert g["mem_used_mb"] == 129 and g["pcie_gen"] == 1 and g["pcie_width"] == 16
    assert g["pcie_gen_max"] == 4 and g["pcie_width_max"] == 16
    g = monitor.parse_gpu_line("GPU, 1.0, 100, 12282, [N/A], [N/A], [N/A], [N/A], 4, 16")
    assert g["util_pct"] is None and g["pcie_gen"] is None


def test_pcie_under_load_and_expectation():
    def row(util, gen, width):
        return {"gpu_mem_used_mb": 5000, "gpu_util_pct": util, "pcie_gen": gen, "pcie_width": width}

    baseline, end = row(2, 1, 16), row(1, 1, 16)
    good = monitor.summarize([row(3, 1, 16), row(95, 4, 16), row(93, 4, 16)], baseline, end, (4, 16))
    assert good["pcie_under_load"] == {"gen4 x16": 2} and good["min_pcie_width_under_load"] == 16
    assert good["pcie_start"] == "gen1 x16" and good["pcie_end"] == "gen1 x16" and good["expect_pcie"] == "gen4 x16"
    assert not any(f.startswith("pcie") for f in good["auto_flags"])
    bad = monitor.summarize([row(95, 4, 4), row(93, 4, 16)], baseline, end, (4, 16))
    assert bad["pcie_under_load"] == {"gen4 x4": 1, "gen4 x16": 1} and bad["min_pcie_width_under_load"] == 4
    assert "pcie_below_expected" in bad["auto_flags"]
    idle = monitor.summarize([row(5, 1, 16)], baseline, end, (4, 16))
    assert "pcie_no_load_samples" in idle["auto_flags"] and idle["pcie_under_load"] == {}
    assert "pcie_below_expected" not in monitor.summarize([row(95, 4, 4)], baseline, end, None)["auto_flags"]
    assert monitor.parse_expect_pcie("4x16") == (4, 16) and monitor.parse_expect_pcie("gen3x8") == (3, 8)
    assert monitor.parse_expect_pcie("none") is None


def test_commit_and_pagefile_flags():
    baseline = {"swap_used_mb": 100, "swap_total_mb": 27648, "commit_total_mb": 15000}
    rows = [{"commit_total_mb": 50000, "commit_limit_mb": 60160, "swap_used_mb": 300, "swap_total_mb": 27648},
            {"commit_total_mb": 56000, "commit_limit_mb": 60160, "swap_used_mb": 400, "swap_total_mb": 30000}]
    s = monitor.summarize(rows, baseline)
    assert s["peak_commit_total_mb"] == 56000 and s["commit_limit_mb"] == 60160
    assert s["peak_commit_pct"] == 93.1 and "commit_near_limit" in s["auto_flags"]
    assert s["pagefile_total_growth_mb"] == 2352 and "pagefile_grew" in s["auto_flags"]
    assert "paging_suspected" not in s["auto_flags"]


def test_commit_mb_is_windows_only():
    commit, limit = monitor.commit_mb()
    if sys.platform == "win32":
        assert commit > 0 and limit >= commit
    else:
        assert commit is None and limit is None


def test_hash_matches_hashlib(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"onecreations" * 100_000)
    assert hash_files.sha256_file(f) == hashlib.sha256(f.read_bytes()).hexdigest()
    assert hash_files.main([str(f)]) == 0
    assert hash_files.main([str(tmp_path / "missing.bin")]) == 1
