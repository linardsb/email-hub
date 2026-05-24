"""Coverage tests for the eval-runner registry (F025).

Asserts the structural invariants the refactor depends on:
- AGENT_REGISTRY covers exactly AGENT_NAMES (no missing/extra agents).
- Each AgentSpec has callable cases_loader + case_runner.
- _run_case assembles the canonical trace dict on both success and error paths,
  and threads optional design_context through.

These run without an LLM and are part of `make check`.
"""

from typing import Any

import pytest

from app.ai.agents.evals.runner import (
    AGENT_NAMES,
    AGENT_REGISTRY,
    _run_case,  # pyright: ignore[reportPrivateUsage]
)


def test_registry_covers_all_agent_names() -> None:
    assert set(AGENT_REGISTRY) == set(AGENT_NAMES)


def test_registry_has_no_extras() -> None:
    # AGENT_NAMES is the source of truth — registry must not silently grow.
    assert len(AGENT_REGISTRY) == len(AGENT_NAMES)


def test_each_spec_has_callables() -> None:
    for spec in AGENT_REGISTRY.values():
        assert callable(spec.cases_loader)
        assert callable(spec.case_runner)


def test_cases_loader_accepts_include_uploaded() -> None:
    # The if-ladder used to pass include_uploaded only to scaffolder.
    # The static cases_loader must accept (and ignore) the kwarg, so the
    # uniform `spec.cases_loader(include_uploaded=...)` call in run_agent is safe.
    for spec in AGENT_REGISTRY.values():
        cases = spec.cases_loader(include_uploaded=False)
        assert isinstance(cases, list)


@pytest.mark.asyncio
async def test_run_case_produces_canonical_trace_shape_on_success() -> None:
    async def _invoke(_c: dict[str, Any]) -> dict[str, str]:
        return {"hello": "world"}

    case: dict[str, Any] = {"id": "case-1", "dimensions": {"axis": "value"}}
    trace = await _run_case(
        "scaffolder",
        case,
        invoke=_invoke,
        input_serializer=lambda c: {"echo": c["id"]},
        output_serializer=lambda r: r,
    )

    assert set(trace) >= {
        "id",
        "agent",
        "dimensions",
        "input",
        "output",
        "expected_challenges",
        "elapsed_seconds",
        "error",
        "timestamp",
    }
    assert trace["id"] == "case-1"
    assert trace["agent"] == "scaffolder"
    assert trace["dimensions"] == {"axis": "value"}
    assert trace["input"] == {"echo": "case-1"}
    assert trace["output"] == {"hello": "world"}
    assert trace["error"] is None
    assert isinstance(trace["elapsed_seconds"], float)


@pytest.mark.asyncio
async def test_run_case_captures_errors_with_type_and_message() -> None:
    async def _invoke(_c: dict[str, Any]) -> dict[str, str]:
        raise RuntimeError("boom")

    trace = await _run_case(
        "dark_mode",
        {"id": "x", "dimensions": {}},
        invoke=_invoke,
        input_serializer=lambda _c: {},
        output_serializer=lambda _r: {},
    )

    assert trace["output"] is None
    assert trace["error"] == "RuntimeError: boom"


@pytest.mark.asyncio
async def test_run_case_threads_design_context_when_present() -> None:
    async def _invoke(_c: dict[str, Any]) -> dict[str, str]:
        return {}

    case: dict[str, Any] = {
        "id": "x",
        "dimensions": {},
        "design_context": {"figma_node": "1:2"},
    }
    trace = await _run_case(
        "scaffolder",
        case,
        invoke=_invoke,
        input_serializer=lambda _c: {},
        output_serializer=lambda _r: {},
    )

    assert trace["design_context"] == {"figma_node": "1:2"}


@pytest.mark.asyncio
async def test_run_case_omits_design_context_when_absent() -> None:
    async def _invoke(_c: dict[str, Any]) -> dict[str, str]:
        return {}

    trace = await _run_case(
        "scaffolder",
        {"id": "x", "dimensions": {}},
        invoke=_invoke,
        input_serializer=lambda _c: {},
        output_serializer=lambda _r: {},
    )

    assert "design_context" not in trace
