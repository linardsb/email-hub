"""Jev shadow pass: mappings, resolver, client parsing, flag gate, errors, agreement (plan T8).

Jev is always mocked with ``httpx.MockTransport``; canned bodies follow the
documented response shape ``{model, answers, usage}`` (docs.typesafe.ai/api.md,
read 2026-09-28). Real fixtures only: cases 5, 6 and 9.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import functools
import importlib.util
import inspect
import json
import re
import textwrap
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.design_sync import component_matcher
from app.design_sync.figma.layout_analyzer import EmailSectionType
from app.design_sync.jev_shadow import shadow as shadow_mod
from app.design_sync.jev_shadow.client import JevClient, JevError
from app.design_sync.jev_shadow.questions import (
    NONE_OPTION,
    SECTION_TYPE_OPTIONS,
    SLUG_DESCRIPTIONS,
    resolve_slots,
)
from app.design_sync.jev_shadow.shadow import (
    SectionPlan,
    ShadowRecord,
    index_nodes,
    plan_section,
    run_jev_shadow,
)
from app.design_sync.tests.jev_shadow_capture import CapturedCase, capture_case

Handler = Callable[[httpx.Request], httpx.Response]


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def cases() -> dict[str, CapturedCase]:
    return {c: capture_case(c) for c in ("5", "6", "9")}


@pytest.fixture
def shadow_on(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    ds = get_settings().design_sync
    monkeypatch.setattr(ds, "jev_shadow_enabled", True)
    monkeypatch.setattr(ds, "jev_api_key", SecretStr("test-key"))
    out = tmp_path / "jev_shadow.jsonl"
    monkeypatch.setattr(shadow_mod, "SHADOW_PATH", out)
    yield out


def _client(handler: Handler) -> JevClient:
    return JevClient(
        "test-key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def _body(answers: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": "jev-1.13.0",
        "answers": answers,
        "usage": {"input_tokens": 318, "output_tokens": 34},
    }


def _choice(choice: str, options: list[str], confidence: float = 0.81) -> dict[str, Any]:
    rest = (1.0 - confidence) / max(len(options) - 1, 1)
    probs = {o: (confidence if o == choice else rest) for o in options}
    return {"type": "choice", "choice": choice, "probabilities": probs, "confidence": confidence}


def _default_answers(questions: dict[str, Any]) -> dict[str, Any]:
    """A valid answer per question: first option for Choice, 0.2 for Noul."""
    out: dict[str, Any] = {}
    for qid, q in questions.items():
        if q["type"] == "noul":
            out[qid] = {"type": "noul", "noul": 0.2}
        else:
            options = list(q["criteria"])
            out[qid] = _choice(options[0], options)
    return out


def _plans(case: CapturedCase) -> dict[str, SectionPlan]:
    """Section plans keyed by the state's position string (unique per section)."""
    nodes = index_nodes(case.structure)
    total = len(case.matches)
    out: dict[str, SectionPlan] = {}
    for i, m in enumerate(case.matches):
        plan = plan_section(m, nodes[m.section.node_id], i, total)
        out[plan.section_state.state["section"]["position"]] = plan  # type: ignore[index]
    return out


def _position(request: httpx.Request) -> str:
    return str(json.loads(request.content)["state"]["section"]["position"])


# ── Mappings + resolver ──────────────────────────────────────────


def _dict_literal(fn: Callable[..., Any], *, values: bool = False) -> set[str]:
    """String keys (or values) of the first dict literal assigned in ``fn``."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    for node in ast.walk(tree):
        if isinstance(node, (ast.AnnAssign, ast.Assign)) and isinstance(node.value, ast.Dict):
            items = node.value.values if values else node.value.keys
            return {
                i.value for i in items if isinstance(i, ast.Constant) and isinstance(i.value, str)
            }
    raise AssertionError(f"no dict literal in {fn.__name__}")


def test_mapping_section_types_cover_enum() -> None:
    assert set(SECTION_TYPE_OPTIONS) == set(EmailSectionType)


def test_mapping_slugs_equal_builder_keys_plus_column_slugs() -> None:
    builder = _dict_literal(component_matcher._build_slot_fills)
    columns = _dict_literal(component_matcher._match_column_layout, values=True)
    assert len(builder) == 60
    assert columns == {"column-layout-2", "column-layout-3", "column-layout-4"}
    assert set(SLUG_DESCRIPTIONS) == builder | columns


def test_resolve_two_slots_prefer_same_node() -> None:
    answers = {
        "heading": {"n1": 0.9, "n2": 0.1, NONE_OPTION: 0.0},
        "body": {"n1": 0.6, "n2": 0.3, NONE_OPTION: 0.1},
    }
    assert resolve_slots(answers) == {"heading": "n1", "body": "n2"}


def test_resolve_none_option_and_exhausted_candidates() -> None:
    answers = {
        "a": {"n1": 0.95, NONE_OPTION: 0.05},
        "b": {"n1": 0.7, NONE_OPTION: 0.3},
        "c": {"n1": 0.8},
    }
    assert resolve_slots(answers) == {"a": "n1", "b": None, "c": None}


# ── Client ───────────────────────────────────────────────────────


async def test_client_parses_documented_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "jev-1.13.0"
        return httpx.Response(
            200,
            json=_body(
                {
                    "is_urgent": {"type": "noul", "noul": 0.95},
                    "department": {
                        "type": "choice",
                        "choice": "billing",
                        "probabilities": {"billing": 0.88, "technical": 0.12, "sales": 0.0},
                        "confidence": 0.81,
                    },
                }
            ),
            headers={"x-typesafe-request-id": "req_123"},
        )

    resp = await _client(handler).system_one({"text": "x"}, {})
    assert resp.request_id == "req_123"
    assert resp.usage.input_tokens == 318
    assert resp.answers["department"].type == "choice"


async def test_client_401_raises_jev_error() -> None:
    client = _client(lambda _r: httpx.Response(401, json={"error": "unauthorized"}))
    with pytest.raises(JevError) as exc:
        await client.system_one({}, {})
    assert exc.value.status == 401


async def test_client_malformed_body_raises_jev_error() -> None:
    client = _client(lambda _r: httpx.Response(200, json={"answers": {"q": {"type": "noul"}}}))
    with pytest.raises(JevError):
        await client.system_one({}, {})


# ── Flag gate ────────────────────────────────────────────────────


async def test_flag_off_makes_no_request(
    cases: dict[str, CapturedCase], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings().design_sync, "jev_shadow_enabled", False)
    monkeypatch.setattr(get_settings().design_sync, "jev_api_key", SecretStr("test-key"))

    def handler(_r: httpx.Request) -> httpx.Response:
        raise AssertionError("Jev must not be called with the flag off")

    case = cases["6"]
    out = await run_jev_shadow(case.structure, case.matches, run_label="t", client=_client(handler))
    assert out == []


async def test_no_key_makes_no_request(
    cases: dict[str, CapturedCase], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings().design_sync, "jev_shadow_enabled", True)
    monkeypatch.setattr(get_settings().design_sync, "jev_api_key", SecretStr(""))

    def handler(_r: httpx.Request) -> httpx.Response:
        raise AssertionError("Jev must not be called without a key")

    case = cases["6"]
    out = await run_jev_shadow(case.structure, case.matches, run_label="t", client=_client(handler))
    assert out == []


# ── Shadow pass ──────────────────────────────────────────────────


async def test_errors_are_recorded_and_other_sections_continue(
    cases: dict[str, CapturedCase], shadow_on: Path
) -> None:
    case = cases["6"]
    total = len(case.matches)

    def handler(request: httpx.Request) -> httpx.Response:
        position = _position(request)
        if position.startswith(f"section 1 of {total}"):
            return httpx.Response(529, json={"error": "overloaded"})
        if position.startswith(f"section 2 of {total}"):
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(
            200, json=_body(_default_answers(json.loads(request.content)["questions"]))
        )

    records = await run_jev_shadow(
        case.structure, case.matches, run_label="err", client=_client(handler)
    )
    by_section: dict[int, list[ShadowRecord]] = {}
    for r in records:
        by_section.setdefault(r.section_index, []).append(r)
    assert set(by_section) == {m.section_idx for m in case.matches}
    first, second = case.matches[0].section_idx, case.matches[1].section_idx
    assert all(r.error and "529" in r.error for r in by_section[first])
    assert all(r.error and "ReadTimeout" in r.error for r in by_section[second])
    assert all(r.jev_answer is None for r in by_section[first] + by_section[second])
    rest = [r for idx, rs in by_section.items() if idx not in (first, second) for r in rs]
    assert rest and all(r.error is None for r in rest)
    assert len(shadow_on.read_text().splitlines()) == len(records)


async def test_disagreement_on_r1_social_section(
    cases: dict[str, CapturedCase], shadow_on: Path
) -> None:
    case = cases["6"]
    target = next(m for m in case.matches if m.section.node_id == "2833:1475")
    assert target.section.section_type == EmailSectionType.SOCIAL

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        answers = _default_answers(body["questions"])
        if body["state"]["section"]["name"] == target.section.node_name:
            options = list(body["questions"]["o1_type"]["criteria"])
            answers["o1_type"] = _choice("footer", options, confidence=0.91)
        return httpx.Response(200, json=_body(answers))

    records = await run_jev_shadow(
        case.structure, [target], run_label="r1", client=_client(handler)
    )
    o1 = next(r for r in records if r.decision_point == "o1_type")
    assert o1.heuristic_answer == "social"
    assert o1.jev_answer == "footer"
    assert o1.jev_confidence == pytest.approx(0.91)
    assert o1.agree is False
    assert o1.probabilities is not None and o1.probabilities["footer"] == pytest.approx(0.91)
    assert o1.input_tokens == 318
    assert shadow_on.exists()


async def test_o3_container_fills_are_skipped_not_asked(
    cases: dict[str, CapturedCase], shadow_on: Path
) -> None:
    case = cases["5"]
    asked: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        questions = json.loads(request.content)["questions"]
        asked.update(q for q in questions if q.startswith("o3_"))
        return httpx.Response(200, json=_body(_default_answers(questions)))

    records = await run_jev_shadow(
        case.structure, case.matches, run_label="o3", client=_client(handler)
    )
    # On case 5 the container fills that hold nested tables are the footer pair
    # and the nav links; its ``col_N`` fills each hold one node and are asked.
    container = [
        r
        for r in records
        if r.decision_point == "o3_slot"
        and r.subject in {"footer_editorial", "footer_legal", "nav_links"}
    ]
    assert {r.subject for r in container} == {"footer_editorial", "footer_legal", "nav_links"}
    for r in container:
        assert r.skipped is True
        assert r.heuristic_answer in {"unmapped", "multi_node"}
        assert r.jev_answer is None
        assert f"o3_{r.subject}" not in asked


async def test_o3_displaced_slot_carries_resolved_option_confidence(
    cases: dict[str, CapturedCase], shadow_on: Path
) -> None:
    """Two slots top-rank the same node: the loser's confidence is its resolved option's."""
    case = cases["5"]
    plans = _plans(case)
    target = next(
        p for p in plans.values() if len([q for q in p.questions if q.startswith("o3_")]) >= 2
    )
    asked = [q for q in target.questions if q.startswith("o3_")]
    winner, loser = asked[0], asked[1]

    def handler(request: httpx.Request) -> httpx.Response:
        questions = json.loads(request.content)["questions"]
        answers = _default_answers(questions)
        options = list(questions[winner]["criteria"])
        shared, second = options[0], options[1]
        answers[winner] = _choice(shared, options, confidence=0.9)
        answers[loser] = {
            "type": "choice",
            "choice": shared,
            "probabilities": dict.fromkeys(options, 0.0)
            | {shared: 0.8, second: 0.15, NONE_OPTION: 0.05},
            "confidence": 0.8,
        }
        return httpx.Response(200, json=_body(answers))

    records = await run_jev_shadow(
        case.structure, [target.match], run_label="disp", client=_client(handler)
    )
    by_slot = {r.subject: r for r in records if r.decision_point == "o3_slot"}
    lost = by_slot[loser.removeprefix("o3_")]
    assert lost.jev_confidence == pytest.approx(0.15)
    assert by_slot[winner.removeprefix("o3_")].jev_confidence == pytest.approx(0.9)


async def test_all_agree_when_jev_echoes_heuristics(
    cases: dict[str, CapturedCase], shadow_on: Path
) -> None:
    case = cases["9"]
    plans = _plans(case)

    def handler(request: httpx.Request) -> httpx.Response:
        questions = json.loads(request.content)["questions"]
        plan = plans[_position(request)]
        section = plan.match.section
        answers = _default_answers(questions)
        answers["o1_type"] = _choice(
            section.section_type.value, list(questions["o1_type"]["criteria"])
        )
        answers["o1_template"] = _choice(
            plan.match.component_slug, list(questions["o1_template"]["criteria"])
        )
        for fid in plan.o2_candidates:
            icon = fid in {b.icon_node_id for b in section.buttons}
            short = plan.section_state.short_id(fid)
            answers[f"o2_{short}"] = {"type": "noul", "noul": 0.9 if icon else 0.1}
        for slot in plan.o3_slots:
            qid = f"o3_{slot.slot_id}"
            if qid in questions:
                short = plan.section_state.short_id(slot.sources[0])
                assert short is not None
                answers[qid] = _choice(short, list(questions[qid]["criteria"]))
        return httpx.Response(200, json=_body(answers))

    before = copy.deepcopy(case.matches)
    records = await run_jev_shadow(
        case.structure, case.matches, run_label="ok", client=_client(handler)
    )
    assert case.matches == before  # never mutates the shipped matches

    o1 = [r for r in records if r.decision_point == "o1_type"]
    assert len(o1) == len(case.matches)  # one per section, column layouts included
    assert sum(1 for r in records if r.decision_point == "o2_button_icon") == 2
    compared = [r for r in records if not r.skipped]
    assert compared and all(r.agree is True for r in compared)
    assert all(r.error is None for r in records)


async def test_section_exception_outside_request_does_not_stop_run(
    cases: dict[str, CapturedCase], shadow_on: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = cases["6"]
    failing = case.matches[0].section_idx
    real_plan = shadow_mod.plan_section

    def plan_or_raise(match: component_matcher.ComponentMatch, *args: Any) -> SectionPlan:
        if match.section_idx == failing:
            raise ValueError("boom")
        return real_plan(match, *args)

    monkeypatch.setattr(shadow_mod, "plan_section", plan_or_raise)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_body(_default_answers(json.loads(request.content)["questions"]))
        )

    records = await run_jev_shadow(
        case.structure, case.matches, run_label="raise", client=_client(handler)
    )
    assert {r.section_index for r in records} == {m.section_idx for m in case.matches} - {failing}
    assert len(shadow_on.read_text().splitlines()) == len(records)


async def test_trace_write_failure_returns_records(
    cases: dict[str, CapturedCase], shadow_on: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = cases["9"]
    blocker = shadow_on.parent / "not_a_dir"
    blocker.write_text("")
    monkeypatch.setattr(shadow_mod, "SHADOW_PATH", blocker / "jev_shadow.jsonl")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_body(_default_answers(json.loads(request.content)["questions"]))
        )

    records = await run_jev_shadow(
        case.structure, case.matches, run_label="disk", client=_client(handler)
    )
    assert records


def test_shadow_path_is_anchored_to_repo_root() -> None:
    repo = Path(__file__).resolve().parents[3]
    assert shadow_mod.SHADOW_PATH == repo / "traces" / "jev_shadow.jsonl"


def test_log_events_are_two_part() -> None:
    source = inspect.getsource(shadow_mod)
    events = re.findall(r'logger\.\w+\(\s*"([^"]+)"', source)
    assert events
    assert all(re.fullmatch(r"design_sync\.[a-z_]+", e) for e in events), events


# ── Report rule (scripts/jev_shadow_report.py) ───────────────────


def _report_script() -> Any:
    path = Path(__file__).resolve().parents[3] / "scripts" / "jev_shadow_report.py"
    spec = importlib.util.spec_from_file_location("jev_shadow_report", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rule_result_reports_insufficient_evidence_below_min_n() -> None:
    script = _report_script()
    assert script.rule_result(None, False, 5) == "insufficient evidence (n < 16)"
    assert script.rule_result(None, False, 92).startswith("don't wire it in (no threshold")
    assert script.rule_result("0.8", True, 92) == "don't wire it in (leave-one-design-out break)"
    assert script.rule_result("0.8", False, 92) == "wire in at t=0.8"


def test_run_fails_when_trace_write_is_lost(
    cases: dict[str, CapturedCase], shadow_on: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _report_script()
    readonly = shadow_on.parent / "readonly"
    readonly.mkdir()
    readonly.chmod(0o500)
    monkeypatch.setattr(shadow_mod, "SHADOW_PATH", readonly / "jev_shadow.jsonl")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_body(_default_answers(json.loads(request.content)["questions"]))
        )

    def capture(case_id: str) -> CapturedCase:
        return cases[case_id]

    monkeypatch.setattr(script, "capture_case", capture)
    monkeypatch.setattr(
        script, "run_jev_shadow", functools.partial(run_jev_shadow, client=_client(handler))
    )
    try:
        assert script._run(["9"]) == 1
    finally:
        readonly.chmod(0o700)


def test_append_writes_the_payload_in_one_call(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[str] = []

    class Handle:
        def __enter__(self) -> Handle:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def write(self, data: str) -> int:
            writes.append(data)
            return len(data)

    class Target:
        parent = Path()

        def open(self, *args: Any, **kwargs: Any) -> Handle:
            return Handle()

    rec: dict[str, Any] = {f.name: None for f in dataclasses.fields(ShadowRecord)}
    records = [dataclasses.replace(ShadowRecord(**rec), subject=str(i)) for i in range(3)]
    monkeypatch.setattr(shadow_mod, "SHADOW_PATH", Target())
    shadow_mod._append(records)
    assert len(writes) == 1
    assert writes[0].endswith("\n")
    assert [json.loads(line)["subject"] for line in writes[0].splitlines()] == ["0", "1", "2"]


def _shadow_line(jev_answer: str | None) -> str:
    return json.dumps(
        {
            "run_label": "5",
            "section_node_id": "1:2",
            "decision_point": "o1_type",
            "subject": "section",
            "heuristic_answer": "hero",
            "jev_answer": jev_answer,
            "jev_confidence": 0.9 if jev_answer else None,
            "skipped": False,
        }
    )


@pytest.mark.parametrize(
    "lines",
    [
        [_shadow_line("hero"), _shadow_line(None)],  # later failed run supersedes a good one
        [],  # section produced no record at all
    ],
)
def test_summary_fails_when_a_labelled_row_has_no_usable_record(
    lines: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _report_script()
    trace = tmp_path / "jev_shadow.jsonl"
    trace.write_text("".join(line + "\n" for line in lines))
    monkeypatch.setattr(shadow_mod, "SHADOW_PATH", trace)
    labels = tmp_path / "labels.yaml"
    labels.write_text('"5":\n  "1:2":\n    o1_type:\n      section:\n        label: hero\n')
    assert script._summary(labels) == 1


async def test_section_failure_log_carries_traceback(
    cases: dict[str, CapturedCase], shadow_on: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class Recorder:
        def __getattr__(self, _level: str) -> Callable[..., None]:
            def log(event: str, **kw: Any) -> None:
                calls.append((event, kw))

            return log

    monkeypatch.setattr(shadow_mod, "logger", Recorder())

    def plan_or_raise(*_args: Any) -> SectionPlan:
        raise ValueError("boom")

    monkeypatch.setattr(shadow_mod, "plan_section", plan_or_raise)
    case = cases["6"]
    await run_jev_shadow(
        case.structure, case.matches, run_label="tb", client=_client(lambda _r: httpx.Response(500))
    )
    failed = [kw for event, kw in calls if event == "design_sync.jev_shadow_section_failed"]
    assert failed
    assert all(kw.get("exc_info") is True for kw in failed)
