"""External-compute spend ledger with gate enforcement (ADR-0001 D4).

    ledger.py status
    ledger.py check --gpu h100_pcie --hours 2 [--rate 360] [--extra-inr 200]
    ledger.py add --provider runpod --category gpu --gpu h100_pcie --hours 1.5 \
                  --amount-inr 540 --description "G5 admission"

`check` exits 1 when the projected spend would cross the active gate; run it before every launch.
`add` always records the charge (the ledger must stay truthful) but exits 2 if a ceiling is breached.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = REPO_ROOT / "budget" / "policy.json"
DEFAULT_LEDGER = REPO_ROOT / "budget" / "ledger.csv"
FIELDS = ["date", "provider", "category", "gpu", "hours", "amount_inr", "description"]
CATEGORIES = {"gpu", "storage", "transfer", "api", "other"}


@dataclass
class Policy:
    hard_ceiling_inr: float
    gate_a_ceiling_inr: float
    gate_b_unlocked: bool
    rates: dict[str, float]

    @property
    def active_ceiling(self) -> float:
        return self.hard_ceiling_inr if self.gate_b_unlocked else self.gate_a_ceiling_inr

    @property
    def active_gate(self) -> str:
        return "B" if self.gate_b_unlocked else "A"


def load_policy(path: Path = DEFAULT_POLICY) -> Policy:
    raw = json.loads(path.read_text(encoding="utf-8"))
    policy = Policy(
        hard_ceiling_inr=float(raw["hard_ceiling_inr"]),
        gate_a_ceiling_inr=float(raw["gate_a_ceiling_inr"]),
        gate_b_unlocked=bool(raw["gate_b_unlocked"]),
        rates={k: float(v) for k, v in raw["planning_rates_inr_per_hour"].items()},
    )
    if policy.gate_a_ceiling_inr > policy.hard_ceiling_inr:
        raise ValueError("gate A ceiling exceeds the hard ceiling")
    return policy


def read_entries(path: Path = DEFAULT_LEDGER) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def total_spent(entries: list[dict[str, str]]) -> float:
    return sum(float(e["amount_inr"]) for e in entries)


def project(policy: Policy, spent: float, gpu: str | None, hours: float,
            rate: float | None = None, extra_inr: float = 0.0) -> tuple[float, bool, str]:
    """Return (projected_cost, allowed, message) for a planned job."""
    if hours < 0 or extra_inr < 0:
        raise ValueError("hours and extra_inr must be non-negative")
    if rate is None:
        if gpu is None:
            rate = 0.0
        elif gpu in policy.rates:
            rate = policy.rates[gpu]
        else:
            raise ValueError(f"unknown gpu '{gpu}'; known: {sorted(policy.rates)} (or pass --rate)")
    cost = rate * hours + extra_inr
    after = spent + cost
    ceiling = policy.active_ceiling
    allowed = after <= ceiling
    msg = (f"projected ₹{cost:,.0f} ({hours:g} h × ₹{rate:,.0f}/h + ₹{extra_inr:,.0f}); "
           f"spent ₹{spent:,.0f} → ₹{after:,.0f} of gate {policy.active_gate} ceiling ₹{ceiling:,.0f}")
    return cost, allowed, msg


def cmd_status(policy: Policy, entries: list[dict[str, str]]) -> int:
    spent = total_spent(entries)
    by_cat: dict[str, float] = {}
    for e in entries:
        by_cat[e["category"]] = by_cat.get(e["category"], 0.0) + float(e["amount_inr"])
    print(f"Spent:        ₹{spent:,.0f}")
    print(f"Active gate:  {policy.active_gate} (ceiling ₹{policy.active_ceiling:,.0f})")
    print(f"Remaining:    ₹{policy.active_ceiling - spent:,.0f} in gate, "
          f"₹{policy.hard_ceiling_inr - spent:,.0f} to hard ceiling")
    for cat, amt in sorted(by_cat.items()):
        print(f"  {cat:<9} ₹{amt:,.0f}")
    print(f"Entries:      {len(entries)}")
    return 0


def cmd_check(policy: Policy, entries: list[dict[str, str]], args: argparse.Namespace) -> int:
    _, allowed, msg = project(policy, total_spent(entries), args.gpu, args.hours, args.rate, args.extra_inr)
    print(("OK: " if allowed else "REFUSED: ") + msg)
    if args.rate is None and args.gpu:
        print("note: planning rate used — confirm the live payable rate and re-run with --rate before launch.")
    if allowed:
        print("reminder: the owner must explicitly approve this launch in the current session.")
    return 0 if allowed else 1


def cmd_add(policy: Policy, ledger: Path, args: argparse.Namespace) -> int:
    if args.category not in CATEGORIES:
        raise ValueError(f"category must be one of {sorted(CATEGORIES)}")
    if args.amount_inr < 0:
        raise ValueError("amount must be non-negative")
    entries = read_entries(ledger)
    row = {
        "date": args.date or dt.date.today().isoformat(),
        "provider": args.provider,
        "category": args.category,
        "gpu": args.gpu or "",
        "hours": f"{args.hours:g}" if args.hours is not None else "",
        "amount_inr": f"{args.amount_inr:.2f}",
        "description": args.description,
    }
    new_file = not ledger.exists()
    with ledger.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)
    after = total_spent(entries) + args.amount_inr
    print(f"recorded ₹{args.amount_inr:,.2f}; total ₹{after:,.2f}")
    if after > policy.hard_ceiling_inr:
        print(f"BREACH: hard ceiling ₹{policy.hard_ceiling_inr:,.0f} exceeded — stop all paid compute and tell the owner.")
        return 2
    if after > policy.active_ceiling:
        print(f"BREACH: gate {policy.active_gate} ceiling ₹{policy.active_ceiling:,.0f} exceeded — stop and tell the owner.")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows consoles/pipes may default to cp1252, which can't encode "₹".
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    p.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    c = sub.add_parser("check")
    c.add_argument("--gpu")
    c.add_argument("--hours", type=float, default=0.0)
    c.add_argument("--rate", type=float, help="live payable ₹/h incl. taxes/fees (overrides planning rate)")
    c.add_argument("--extra-inr", type=float, default=0.0, help="storage/transfer/other for this job")
    a = sub.add_parser("add")
    a.add_argument("--provider", required=True)
    a.add_argument("--category", required=True, choices=sorted(CATEGORIES))
    a.add_argument("--gpu")
    a.add_argument("--hours", type=float)
    a.add_argument("--amount-inr", type=float, required=True)
    a.add_argument("--description", required=True)
    a.add_argument("--date")
    args = p.parse_args(argv)

    policy = load_policy(args.policy)
    if args.cmd == "status":
        return cmd_status(policy, read_entries(args.ledger))
    if args.cmd == "check":
        return cmd_check(policy, read_entries(args.ledger), args)
    return cmd_add(policy, args.ledger, args)


if __name__ == "__main__":
    sys.exit(main())
