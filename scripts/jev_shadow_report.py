"""Jev shadow classifier: offline runner and disagreement report (plan T9).

Drives each design through the real ``convert_document`` path, captures the
component matches that shipped, runs the Jev shadow pass on them and appends
the records to ``traces/jev_shadow.jsonl``. ``--summary`` joins the records with
hand-authored labels and prints the report tables.

Usage (from repo root):

    uv run python scripts/jev_shadow_report.py --check-key
    uv run python scripts/jev_shadow_report.py --cases 6 --dry-run
    DESIGN_SYNC__JEV_SHADOW_ENABLED=true uv run python scripts/jev_shadow_report.py
    uv run python scripts/jev_shadow_report.py --emit-label-template
    uv run python scripts/jev_shadow_report.py --summary

It is a script, not a test: CI never calls the Jev API.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.core.config import get_settings  # noqa: E402
from app.design_sync.jev_shadow import shadow  # noqa: E402
from app.design_sync.jev_shadow.client import JevClient, JevError  # noqa: E402
from app.design_sync.jev_shadow.shadow import (  # noqa: E402
    BUTTON_ICON,
    index_nodes,
    plan_section,
    run_jev_shadow,
)
from app.design_sync.tests.jev_shadow_capture import capture_case  # noqa: E402
from app.design_sync.tests.test_snapshot_regression import _normalize_html  # noqa: E402

ALL_CASES = ("5", "6", "7", "8", "9", "10", "reframe")
DEFAULT_LABELS = REPO / "data" / "debug" / "jev_shadow_labels.yaml"
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9)
DECISION_POINTS = ("o1_type", "o1_template", "o2_button_icon", "o3_slot")
REQUIRED_LABELS = frozenset({"o1_type", "o1_template", "o2_button_icon"})
MIN_N = 16  # zero-error Wilson lower bound reaches 0.80 only at n >= 16 (plan T12)
Z = 1.96

Key = tuple[str, str, str, str]  # case, section_node_id, decision_point, subject


# ── Run ──────────────────────────────────────────────────────────


def _run(cases: list[str]) -> int:
    settings = get_settings().design_sync
    if not settings.jev_shadow_enabled:
        print(
            "DESIGN_SYNC__JEV_SHADOW_ENABLED is off; set it to true for a real run.",
            file=sys.stderr,
        )
        return 1
    if not settings.jev_api_key.get_secret_value():
        print("DESIGN_SYNC__JEV_API_KEY is empty.", file=sys.stderr)
        return 1
    total_tokens = total_records = total_errors = 0
    for case_id in cases:
        captured = capture_case(case_id)
        if case_id != "reframe":
            expected = (REPO / "data" / "debug" / case_id / "expected.html").read_text()
            if _normalize_html(captured.html) != _normalize_html(expected):
                print(
                    f"case {case_id}: HTML differs from expected.html under capture",
                    file=sys.stderr,
                )
                return 1
        records = asyncio.run(
            run_jev_shadow(captured.structure, captured.matches, run_label=case_id)
        )
        tokens = sum(r.input_tokens or 0 for r in records)
        errors = sum(1 for r in records if r.error)
        o1 = sum(1 for r in records if r.decision_point == "o1_type")
        print(
            f"case {case_id}: sections={len(captured.matches)} o1_records={o1} "
            f"records={len(records)} errors={errors} input_tokens={tokens}"
        )
        total_tokens += tokens
        total_records += len(records)
        total_errors += errors
    print(f"total: records={total_records} errors={total_errors} input_tokens={total_tokens}")
    print(f"records appended to {shadow.SHADOW_PATH}")
    return 0


def _dry_run(cases: list[str]) -> int:
    requests = questions = 0
    for case_id in cases:
        captured = capture_case(case_id)
        nodes = index_nodes(captured.structure)
        total = len(captured.matches)
        for i, match in enumerate(captured.matches):
            plan = plan_section(match, nodes[match.section.node_id], i, total)
            requests += 1
            questions += len(plan.questions)
            if i == 0:
                body = {"state": plan.section_state.state, "questions": plan.questions}
                print(f"── case {case_id}, section 0 request ──")
                print(json.dumps(body, indent=2))
        print(f"case {case_id}: {total} requests built")
    print(f"dry run: {requests} requests, {questions} questions, nothing sent")
    return 0


def _check_key() -> int:
    key = get_settings().design_sync.jev_api_key.get_secret_value()
    if not key:
        print("DESIGN_SYNC__JEV_API_KEY is empty.", file=sys.stderr)
        return 1

    async def call() -> int:
        client = JevClient(key)
        try:
            resp = await client.system_one(
                {"text": "Help! My payouts have been failing for 3 days."},
                {"is_urgent": {"type": "noul", "instructions": "Does this convey urgency?"}},
            )
        except JevError as exc:
            print(f"status={exc.status} request_id={exc.request_id} error={exc}")
            return 1
        finally:
            await client.aclose()
        print(f"status=200 model={resp.model} request_id={resp.request_id}")
        return 0

    return asyncio.run(call())


# ── Records + labels ─────────────────────────────────────────────


def _load_records() -> dict[Key, dict[str, Any]]:
    """Latest record per decision (later runs supersede earlier ones)."""
    out: dict[Key, dict[str, Any]] = {}
    if not shadow.SHADOW_PATH.exists():
        return out
    for line in shadow.SHADOW_PATH.read_text().splitlines():
        rec = json.loads(line)
        key = (rec["run_label"], rec["section_node_id"], rec["decision_point"], rec["subject"])
        out[key] = rec
    return out


def _load_labels(path: Path) -> dict[Key, dict[str, Any]]:
    if not path.exists():
        return {}
    data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    out: dict[Key, dict[str, Any]] = {}
    for case_id, sections in data.items():
        for section_id, points in (sections or {}).items():
            for point, subjects in (points or {}).items():
                for subject, entry in (subjects or {}).items():
                    out[(str(case_id), str(section_id), point, str(subject))] = entry
    return out


def _emit_label_template(path: Path) -> int:
    existing = _load_labels(path)
    if any(e.get("label") is not None for e in existing.values()):
        print(f"{path} has labels already; refusing to overwrite.", file=sys.stderr)
        return 1
    records = _load_records()
    if not records:
        print(f"no records in {shadow.SHADOW_PATH}; run the shadow pass first.", file=sys.stderr)
        return 1
    hints: dict[tuple[str, str], str] = {}
    for case_id in sorted({k[0] for k in records}):
        for match in capture_case(case_id).matches:
            section = match.section
            first_text = section.texts[0].content[:60] if section.texts else ""
            hints[(case_id, section.node_id)] = f"{section.node_name} | {first_text}"
    tree: dict[str, Any] = {}
    for (case_id, section_id, point, subject), rec in sorted(records.items()):
        if rec["skipped"]:
            continue
        entry = {
            "heuristic": rec["heuristic_answer"],
            "jev": rec["jev_answer"],
            "jev_confidence": rec["jev_confidence"],
            "hint": hints.get((case_id, section_id), ""),
            "label": None,
            "source": None,
        }
        tree.setdefault(case_id, {}).setdefault(section_id, {}).setdefault(point, {})[subject] = (
            entry
        )
    path.write_text(yaml.safe_dump(tree, sort_keys=False, allow_unicode=True, width=120))
    print(f"wrote {sum(1 for r in records.values() if not r['skipped'])} rows to {path}")
    return 0


# ── Summary ──────────────────────────────────────────────────────


def _is_icon(value: str | None) -> bool:
    return value == BUTTON_ICON


def _correct(point: str, answer: str | None, label: str) -> bool:
    if point == "o2_button_icon":
        return _is_icon(answer) == _is_icon(label)
    return answer == label


def wilson_lower(successes: int, n: int) -> float:
    if n == 0:
        return 0.0
    p = successes / n
    denom = 1 + Z**2 / n
    centre = p + Z**2 / (2 * n)
    margin = Z * math.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2))
    return (centre - margin) / denom


def _fix_break(rows: list[dict[str, Any]], t: float) -> tuple[int, int]:
    """Overrides at threshold t: fixes (Jev right, heuristic wrong) vs breaks."""
    fixes = breaks = 0
    for r in rows:
        if r["conf"] < t or r["jev_ok"] == r["heur_ok"]:
            continue
        if r["jev_ok"]:
            fixes += 1
        else:
            breaks += 1
    return fixes, breaks


def _pick_threshold(rows: list[dict[str, Any]]) -> float | None:
    for t in THRESHOLDS:
        fixes, breaks = _fix_break(rows, t)
        if breaks == 0 and fixes >= 1:
            return t
    return None


def _summary(labels_path: Path) -> int:
    labels = _load_labels(labels_path)
    records = _load_records()
    missing = [k for k, e in labels.items() if k[2] in REQUIRED_LABELS and e.get("label") is None]
    if not labels or missing:
        print(
            f"{len(missing)} O1/O2 labels still null in {labels_path}; label them first.",
            file=sys.stderr,
        )
        return 1

    rows_by_point: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key, entry in labels.items():
        rec = records.get(key)
        label = entry.get("label")
        if rec is None or label is None or rec["jev_answer"] is None:
            continue
        point = key[2]
        rows_by_point[point].append(
            {
                "key": key,
                "case": key[0],
                "heur": rec["heuristic_answer"],
                "jev": rec["jev_answer"],
                "conf": float(rec["jev_confidence"] or 0.0),
                "label": label,
                "heur_ok": _correct(point, rec["heuristic_answer"], str(label)),
                "jev_ok": _correct(point, rec["jev_answer"], str(label)),
            }
        )

    for point in DECISION_POINTS:
        rows = rows_by_point.get(point, [])
        print(f"\n## {point} (n={len(rows)})\n")
        if not rows:
            print("no labelled rows")
            continue
        agree = sum(1 for r in rows if r["heur"] == r["jev"])
        right = [r["conf"] for r in rows if r["jev_ok"]]
        wrong = [r["conf"] for r in rows if not r["jev_ok"]]
        print(
            "| n | agree | disagree | heuristic acc | Jev acc | mean conf right | mean conf wrong |"
        )
        print("|---|---|---|---|---|---|---|")
        print(
            f"| {len(rows)} | {agree} | {len(rows) - agree} "
            f"| {sum(r['heur_ok'] for r in rows)}/{len(rows)} | {len(right)}/{len(rows)} "
            f"| {sum(right) / len(right) if right else float('nan'):.2f} "
            f"| {sum(wrong) / len(wrong) if wrong else float('nan'):.2f} |"
        )
        disagreements = [r for r in rows if r["heur"] != r["jev"]]
        if disagreements:
            print("\n| case | section | subject | heuristic | Jev | conf | label |")
            print("|---|---|---|---|---|---|---|")
            for r in disagreements:
                c, s, _p, subj = r["key"]
                print(
                    f"| {c} | {s} | {subj} | {r['heur']} | {r['jev']} | {r['conf']:.2f} | {r['label']} |"
                )

        print("\n| t | fixes | breaks | n at >= t | Jev correct at >= t | Wilson 95% lower |")
        print("|---|---|---|---|---|---|")
        verdict: str | None = None
        for t in THRESHOLDS:
            fixes, breaks = _fix_break(rows, t)
            above = [r for r in rows if r["conf"] >= t]
            ok = sum(1 for r in above if r["jev_ok"])
            lower = wilson_lower(ok, len(above))
            print(f"| {t} | {fixes} | {breaks} | {len(above)} | {ok} | {lower:.3f} |")
            if (
                verdict is None
                and breaks == 0
                and fixes >= 1
                and len(above) >= MIN_N
                and lower >= 0.80
            ):
                verdict = f"{t}"

        print("\nLeave-one-design-out (threshold picked on the other designs):\n")
        print("| held out | t | fixes | breaks |")
        print("|---|---|---|---|")
        lodo_break = False
        for held in sorted({r["case"] for r in rows}):
            t_pick = _pick_threshold([r for r in rows if r["case"] != held])
            if t_pick is None:
                print(f"| {held} | none | - | - |")
                continue
            fixes, breaks = _fix_break([r for r in rows if r["case"] == held], t_pick)
            lodo_break = lodo_break or breaks > 0
            print(f"| {held} | {t_pick} | {fixes} | {breaks} |")

        if verdict is not None and not lodo_break:
            print(f"\nRule result: wire in at t={verdict}.")
        else:
            reason = (
                "leave-one-design-out break"
                if verdict
                else "no threshold meets breaks=0, fixes>=1, n>=16, Wilson>=0.80"
            )
            print(f"\nRule result: don't wire it in ({reason}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cases", default=",".join(ALL_CASES), help="comma-separated case ids")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument(
        "--summary", action="store_true", help="join records with labels; print tables"
    )
    parser.add_argument("--dry-run", action="store_true", help="build requests, send nothing")
    parser.add_argument("--emit-label-template", action="store_true")
    parser.add_argument(
        "--check-key", action="store_true", help="one smoke request; never prints the key"
    )
    args = parser.parse_args()
    cases = [c.strip() for c in args.cases.split(",") if c.strip()]

    if args.check_key:
        return _check_key()
    if args.dry_run:
        return _dry_run(cases)
    if args.emit_label_template:
        return _emit_label_template(args.labels)
    if args.summary:
        return _summary(args.labels)
    return _run(cases)


if __name__ == "__main__":
    sys.exit(main())
