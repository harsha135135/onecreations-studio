import json

import pytest

from tools.budget import ledger


def write_policy(tmp_path, gate_b=False):
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({
        "hard_ceiling_inr": 15000,
        "gate_a_ceiling_inr": 5000,
        "gate_b_unlocked": gate_b,
        "planning_rates_inr_per_hour": {"h100_pcie": 355, "rtx4090": 95},
    }))
    return path


def test_check_allows_within_gate_a(tmp_path):
    policy, led = write_policy(tmp_path), tmp_path / "ledger.csv"
    rc = ledger.main(["--policy", str(policy), "--ledger", str(led), "check", "--gpu", "h100_pcie", "--hours", "8"])
    assert rc == 0  # 8 h x 355 = 2,840 <= 5,000


def test_check_refuses_crossing_gate_a(tmp_path):
    policy, led = write_policy(tmp_path), tmp_path / "ledger.csv"
    rc = ledger.main(["--policy", str(policy), "--ledger", str(led), "check", "--gpu", "h100_pcie", "--hours", "15"])
    assert rc == 1  # 5,325 > 5,000


def test_check_counts_existing_spend_and_live_rate(tmp_path):
    policy, led = write_policy(tmp_path), tmp_path / "ledger.csv"
    assert ledger.main(["--policy", str(policy), "--ledger", str(led), "add", "--provider", "runpod",
                        "--category", "gpu", "--gpu", "h100_pcie", "--hours", "8",
                        "--amount-inr", "3000", "--description", "pilot"]) == 0
    # 3,000 spent + 6 h x 360 = 5,160 > 5,000
    assert ledger.main(["--policy", str(policy), "--ledger", str(led), "check", "--gpu", "h100_pcie",
                        "--hours", "6", "--rate", "360"]) == 1
    # Gate B unlocked: same job fits under 15,000
    policy_b = write_policy(tmp_path, gate_b=True)
    assert ledger.main(["--policy", str(policy_b), "--ledger", str(led), "check", "--gpu", "h100_pcie",
                        "--hours", "6", "--rate", "360"]) == 0


def test_add_records_breach_but_flags_it(tmp_path):
    policy, led = write_policy(tmp_path), tmp_path / "ledger.csv"
    rc = ledger.main(["--policy", str(policy), "--ledger", str(led), "add", "--provider", "runpod",
                      "--category", "gpu", "--amount-inr", "5200", "--description", "overrun"])
    assert rc == 2
    assert ledger.total_spent(ledger.read_entries(led)) == pytest.approx(5200)


def test_unknown_gpu_without_rate_is_an_error(tmp_path):
    policy = ledger.load_policy(write_policy(tmp_path))
    with pytest.raises(ValueError):
        ledger.project(policy, 0, "b200", 1)


def test_repo_policy_is_consistent():
    policy = ledger.load_policy()
    assert policy.hard_ceiling_inr == 15000
    assert policy.gate_a_ceiling_inr == 5000
    assert policy.gate_b_unlocked is False
