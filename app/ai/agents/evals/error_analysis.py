"""Error analysis: cluster failures from judge verdicts into a taxonomy.

CLI: python -m app.ai.agents.evals.error_analysis \
       --verdicts traces/scaffolder_verdicts.jsonl \
       --output traces/scaffolder_analysis.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.ai.agents.evals.schemas import FailureCluster
from app.core.logging import get_logger

logger = get_logger(__name__)


def load_verdicts(path: Path) -> list[dict[str, Any]]:
    """Load verdict JSONL file into list of dicts."""
    verdicts: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                verdicts.append(json.loads(stripped))
    return verdicts


def cluster_failures(verdicts: list[dict[str, Any]]) -> list[FailureCluster]:
    """Group failed criteria by agent+criterion, extract patterns.

    Clusters failures by (agent, criterion) pair. Each cluster contains
    all trace IDs that failed that criterion and sample reasonings for
    manual inspection.
    """
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)

    for verdict in verdicts:
        if verdict.get("error"):
            continue
        agent: str = verdict["agent"]
        for cr in verdict.get("criteria_results", []):
            if not cr["passed"]:
                groups[(agent, cr["criterion"])].append(
                    {"trace_id": verdict["trace_id"], "reasoning": cr["reasoning"]}
                )

    clusters: list[FailureCluster] = []
    for (agent, criterion), items in sorted(groups.items()):
        cluster_id = f"{agent}:{criterion}"
        trace_ids = [item["trace_id"] for item in items]
        sample_reasonings = [item["reasoning"] for item in items[:3]]
        pattern = _extract_pattern(sample_reasonings)

        clusters.append(
            FailureCluster(
                cluster_id=cluster_id,
                agent=agent,
                criterion=criterion,
                pattern=pattern,
                trace_ids=trace_ids,
                sample_reasonings=sample_reasonings,
                count=len(items),
            )
        )

    return sorted(clusters, key=lambda c: c.count, reverse=True)


def _extract_pattern(reasonings: list[str]) -> str:
    """Derive a human-readable failure pattern from sample reasonings."""
    if not reasonings:
        return "unknown"
    first = reasonings[0]
    return first[:120] if len(first) > 120 else first


def compute_pass_rates(
    verdicts: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Compute per-criterion pass rates grouped by agent.

    Returns: {agent: {criterion: pass_rate}}
    """
    counts: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"passed": 0, "total": 0})
    )

    for verdict in verdicts:
        if verdict.get("error"):
            continue
        agent: str = verdict["agent"]
        for cr in verdict.get("criteria_results", []):
            counts[agent][cr["criterion"]]["total"] += 1
            if cr["passed"]:
                counts[agent][cr["criterion"]]["passed"] += 1

    rates: dict[str, dict[str, float]] = {}
    for agent, criteria in sorted(counts.items()):
        rates[agent] = {}
        for criterion, ct in sorted(criteria.items()):
            rates[agent][criterion] = ct["passed"] / ct["total"] if ct["total"] > 0 else 0.0
    return rates


def build_analysis_report(
    verdicts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build complete error analysis report from verdict data.

    Returns JSON-serializable dict with:
    - summary: total traces, pass/fail/error counts
    - pass_rates: per-agent per-criterion rates
    - failure_clusters: sorted by count desc
    - top_failures: top 3 failure clusters (priority fixes)
    """
    total = len(verdicts)
    errors = sum(1 for v in verdicts if v.get("error"))
    passed = sum(1 for v in verdicts if v.get("overall_pass") and not v.get("error"))
    failed = total - passed - errors

    clusters = cluster_failures(verdicts)
    pass_rates = compute_pass_rates(verdicts)

    return {
        "summary": {
            "total_traces": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "overall_pass_rate": (passed / (total - errors) if (total - errors) > 0 else 0.0),
        },
        "pass_rates": pass_rates,
        "failure_clusters": [
            {
                "cluster_id": c.cluster_id,
                "agent": c.agent,
                "criterion": c.criterion,
                "pattern": c.pattern,
                "count": c.count,
                "trace_ids": c.trace_ids,
                "sample_reasonings": c.sample_reasonings,
            }
            for c in clusters
        ],
        "top_failures": [
            {"cluster_id": c.cluster_id, "count": c.count, "pattern": c.pattern}
            for c in clusters[:3]
        ],
    }


def main() -> None:
    """CLI entry point for error analysis."""
    parser = argparse.ArgumentParser(description="Analyze eval judge verdicts")
    parser.add_argument("--verdicts", required=True, help="Path to verdicts JSONL (or directory)")
    parser.add_argument("--output", required=True, help="Path to write analysis JSON")
    args = parser.parse_args()

    verdicts_path = Path(args.verdicts)
    output_path = Path(args.output)

    all_verdicts: list[dict[str, Any]] = []
    if verdicts_path.is_dir():
        for f in sorted(verdicts_path.glob("*_verdicts.jsonl")):
            if "_adversarial_" in f.name:
                continue
            all_verdicts.extend(load_verdicts(f))
    else:
        all_verdicts = load_verdicts(verdicts_path)

    if not all_verdicts:
        logger.error("No verdicts found.")
        sys.exit(1)

    report = build_analysis_report(all_verdicts)

    # Load adversarial verdicts separately if available
    if verdicts_path.is_dir():
        adv_verdicts: list[dict[str, Any]] = []
        for f in sorted(verdicts_path.glob("*_adversarial_verdicts.jsonl")):
            adv_verdicts.extend(load_verdicts(f))
        if adv_verdicts:
            adv_pass_rates = compute_pass_rates(adv_verdicts)
            adv_passed = sum(
                1 for v in adv_verdicts if v.get("overall_pass") and not v.get("error")
            )
            adv_total_valid = sum(1 for v in adv_verdicts if not v.get("error"))
            adv_overall = adv_passed / adv_total_valid if adv_total_valid > 0 else 0.0
            if adv_overall < 0.40:
                adv_status = "FAIL"
            elif adv_overall < 0.60:
                adv_status = "WARN"
            else:
                adv_status = "PASS"
            report["adversarial"] = {
                "total": len(adv_verdicts),
                "overall_pass_rate": adv_overall,
                "pass_rates": adv_pass_rates,
                "status": adv_status,
            }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as out_f:
        json.dump(report, out_f, indent=2)
        out_f.write("\n")  # trailing newline: idempotent regen + end-of-file-fixer compliant

    s = report["summary"]
    logger.info("=== Error Analysis ===")
    logger.info(
        f"Traces: {s['total_traces']} "
        f"(passed={s['passed']}, failed={s['failed']}, errors={s['errors']})"
    )
    logger.info(f"Overall pass rate: {s['overall_pass_rate']:.1%}")

    if report["top_failures"]:
        logger.info("Top failure clusters:")
        for tf in report["top_failures"]:
            logger.info(f"  [{tf['count']}x] {tf['cluster_id']}: {tf['pattern'][:80]}")

    if "adversarial" in report:
        adv: dict[str, Any] = report["adversarial"]
        status: str = adv["status"]
        status_icon = {"PASS": "OK", "WARN": "WARN", "FAIL": "FAIL"}[status]
        logger.info(
            f"Adversarial: {adv['overall_pass_rate']:.1%} ({adv['total']} cases) [{status_icon}]"
        )

    logger.info(f"Full report: {output_path}")


if __name__ == "__main__":
    main()
