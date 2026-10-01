#!/usr/bin/env python3
"""Per-section fidelity gate CLI (CE-1, #419). Docs: docs/fidelity-gate.md.

Runs inside the pinned Playwright image via make:

    make fidelity-gate                                  # check (CI step)
    make fidelity-restamp REASON="..." [CASES="5 6"] [FROM=path/scores.json]

Direct use (inside the image):
    uv run python scripts/fidelity-gate.py check [--cases 5 6] [--dump-crops]
    uv run python scripts/fidelity-gate.py restamp --reason "..." [--cases 5 6] [--from scores.json]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.design_sync.fidelity_gate import GateError, check, restamp  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")
    p_check = sub.add_parser("check", help="score and compare against the baseline (default)")
    p_check.add_argument("--cases", nargs="*", help="case ids (default: all gated)")
    p_check.add_argument("--dump-crops", action="store_true", help="write design|render crop pairs")
    p_stamp = sub.add_parser("restamp", help="rewrite the baseline (pinned image only)")
    p_stamp.add_argument("--reason", required=True, help="why the baseline changes")
    p_stamp.add_argument("--cases", nargs="*", help="case ids (default: all gated)")
    p_stamp.add_argument("--from", dest="from_path", type=Path, help="stamp from a scores.json")
    args = parser.parse_args()

    try:
        if args.cmd == "restamp":
            baseline, report = restamp(args.reason, cases=args.cases, from_path=args.from_path)
            print(report.format(verdict=False))  # before -> after, not a gate verdict
            print(f"stamped: {baseline.stamps[-1].model_dump()}")
            return 0
        report = check(
            cases=getattr(args, "cases", None), dump_crops=getattr(args, "dump_crops", False)
        )
    except GateError as exc:
        print(f"fidelity-gate: {exc}", file=sys.stderr)
        return 2
    print(report.format())
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
