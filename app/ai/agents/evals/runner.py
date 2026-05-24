# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""Eval runner — executes synthetic test cases against agents and collects traces.

Usage:
    python -m app.ai.agents.evals.runner --agent scaffolder --output traces/
    python -m app.ai.agents.evals.runner --agent dark_mode --output traces/
    python -m app.ai.agents.evals.runner --agent content --output traces/
    python -m app.ai.agents.evals.runner --agent personalisation --output traces/
    python -m app.ai.agents.evals.runner --agent knowledge --output traces/
    python -m app.ai.agents.evals.runner --agent all --output traces/

Each trace includes: input, agent output, metadata, and timing.
Traces are saved as JSONL for downstream error analysis and judge evaluation.
"""

import argparse
import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.ai.agents.evals.synthetic_data_accessibility import ACCESSIBILITY_TEST_CASES
from app.ai.agents.evals.synthetic_data_code_reviewer import CODE_REVIEWER_TEST_CASES
from app.ai.agents.evals.synthetic_data_content import CONTENT_TEST_CASES
from app.ai.agents.evals.synthetic_data_dark_mode import DARK_MODE_TEST_CASES
from app.ai.agents.evals.synthetic_data_innovation import INNOVATION_TEST_CASES
from app.ai.agents.evals.synthetic_data_knowledge import KNOWLEDGE_TEST_CASES
from app.ai.agents.evals.synthetic_data_outlook_fixer import OUTLOOK_FIXER_TEST_CASES
from app.ai.agents.evals.synthetic_data_personalisation import PERSONALISATION_TEST_CASES
from app.ai.agents.evals.synthetic_data_scaffolder import SCAFFOLDER_TEST_CASES
from app.ai.agents.evals.template_eval_generator import TemplateEvalGenerator
from app.core.logging import get_logger
from app.core.redaction import redact_value

logger = get_logger(__name__)


AgentName = Literal[
    "scaffolder",
    "dark_mode",
    "content",
    "outlook_fixer",
    "accessibility",
    "personalisation",
    "code_reviewer",
    "knowledge",
    "innovation",
]

AGENT_NAMES: tuple[AgentName, ...] = (
    "scaffolder",
    "dark_mode",
    "content",
    "outlook_fixer",
    "accessibility",
    "personalisation",
    "code_reviewer",
    "knowledge",
    "innovation",
)


@dataclass(frozen=True)
class AgentSpec:
    """Eval-runner registration for one agent.

    ``cases_loader`` accepts ``include_uploaded: bool`` and returns the case list.
    ``case_runner`` is the per-case adapter that wraps ``_run_case``.
    """

    cases_loader: Callable[..., list[dict[str, Any]]]
    case_runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def _run_case(
    agent: AgentName,
    case: dict[str, Any],
    *,
    invoke: Callable[[dict[str, Any]], Awaitable[Any]],
    input_serializer: Callable[[dict[str, Any]], dict[str, Any]],
    output_serializer: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    """Shared timing + error capture + canonical trace dict assembly.

    The trace field order (``id, agent, dimensions, input, output,
    expected_challenges, elapsed_seconds, error, timestamp``) is the on-disk
    JSONL contract consumed by ``analysis.py``, ``failure_warnings.py``,
    ``improvement_tracker.py``, ``production_sampler.py``, and
    ``judge_runner.py``. Do not reorder.
    """
    start = time.monotonic()
    output_value: dict[str, Any] | None
    error_value: str | None
    try:
        response = await invoke(case)
        output_value = output_serializer(response)
        error_value = None
    except Exception as e:
        output_value = None
        error_value = f"{type(e).__name__}: {e}"
    elapsed = time.monotonic() - start
    trace: dict[str, Any] = {
        "id": case["id"],
        "agent": agent,
        "dimensions": case["dimensions"],
        "input": input_serializer(case),
        "output": output_value,
        "expected_challenges": case.get("expected_challenges"),
        "elapsed_seconds": round(elapsed, 2),
        "error": error_value,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if case.get("design_context"):
        trace["design_context"] = case["design_context"]
    return trace


async def run_scaffolder_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single scaffolder test case and return the trace."""
    from app.ai.agents.scaffolder.schemas import ScaffolderRequest
    from app.ai.agents.scaffolder.service import ScaffolderService

    async def _invoke(c: dict[str, Any]) -> Any:  # noqa: ANN401
        service = ScaffolderService()
        request = ScaffolderRequest(brief=c["brief"], stream=False, run_qa=True)
        return await service.generate(request)

    return await _run_case(
        "scaffolder",
        case,
        invoke=_invoke,
        input_serializer=lambda c: {"brief": c["brief"]},
        output_serializer=lambda r: {
            "html": r.html,
            "qa_results": [x.model_dump() for x in (r.qa_results or [])],
            "qa_passed": r.qa_passed,
            "model": r.model,
        },
    )


async def run_dark_mode_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single dark mode test case and return the trace."""
    from app.ai.agents.dark_mode.schemas import DarkModeRequest
    from app.ai.agents.dark_mode.service import DarkModeService

    async def _invoke(c: dict[str, Any]) -> Any:  # noqa: ANN401
        service = DarkModeService()
        request = DarkModeRequest(
            html=c["html_input"],
            color_overrides=c.get("color_overrides"),
            preserve_colors=c.get("preserve_colors"),
            stream=False,
            run_qa=True,
        )
        return await service.process(request)

    return await _run_case(
        "dark_mode",
        case,
        invoke=_invoke,
        input_serializer=lambda c: {
            "html_input": c["html_input"][:5000],
            "html_length": len(c["html_input"]),
            "color_overrides": c.get("color_overrides"),
            "preserve_colors": c.get("preserve_colors"),
        },
        output_serializer=lambda r: {
            "html": r.html,
            "qa_results": [x.model_dump() for x in (r.qa_results or [])],
            "qa_passed": r.qa_passed,
            "model": r.model,
        },
    )


async def run_content_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single content test case and return the trace."""
    from app.ai.agents.content.schemas import ContentRequest
    from app.ai.agents.content.service import ContentService

    async def _invoke(c: dict[str, Any]) -> Any:  # noqa: ANN401
        service = ContentService()
        inp = c["input"]
        request = ContentRequest(
            operation=inp["operation"],
            text=inp["text"],
            tone=inp.get("tone"),
            brand_voice=inp.get("brand_voice"),
            num_alternatives=inp.get("num_alternatives", 1),
            stream=False,
        )
        return await service.generate(request)

    return await _run_case(
        "content",
        case,
        invoke=_invoke,
        input_serializer=lambda c: c["input"],
        output_serializer=lambda r: {
            "content": r.content,
            "operation": r.operation,
            "spam_warnings": [w.model_dump() for w in r.spam_warnings],
            "model": r.model,
        },
    )


async def run_outlook_fixer_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single Outlook Fixer test case and return the trace."""
    from app.ai.agents.outlook_fixer.schemas import OutlookFixerRequest
    from app.ai.agents.outlook_fixer.service import OutlookFixerService

    async def _invoke(c: dict[str, Any]) -> Any:  # noqa: ANN401
        service = OutlookFixerService()
        request = OutlookFixerRequest(
            html=str(c["html_input"]),
            issues=None,
            stream=False,
            run_qa=True,
        )
        return await service.process(request)

    return await _run_case(
        "outlook_fixer",
        case,
        invoke=_invoke,
        input_serializer=lambda c: {
            "html_input": str(c["html_input"]),
            "html_length": len(str(c["html_input"])),
        },
        output_serializer=lambda r: {
            "html": r.html,
            "fixes_applied": r.fixes_applied,
            "qa_results": [x.model_dump() for x in (r.qa_results or [])],
            "qa_passed": r.qa_passed,
            "model": r.model,
        },
    )


async def run_accessibility_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single accessibility test case and return the trace."""
    from app.ai.agents.accessibility.schemas import AccessibilityRequest
    from app.ai.agents.accessibility.service import AccessibilityService

    async def _invoke(c: dict[str, Any]) -> Any:  # noqa: ANN401
        service = AccessibilityService()
        request = AccessibilityRequest(
            html=str(c["html_input"]),
            focus_areas=None,
            stream=False,
            run_qa=True,
        )
        return await service.process(request)

    return await _run_case(
        "accessibility",
        case,
        invoke=_invoke,
        input_serializer=lambda c: {
            "html_input": str(c["html_input"]),
            "html_length": len(str(c["html_input"])),
        },
        output_serializer=lambda r: {
            "html": r.html,
            "skills_loaded": r.skills_loaded,
            "qa_results": [x.model_dump() for x in (r.qa_results or [])],
            "qa_passed": r.qa_passed,
            "model": r.model,
        },
    )


async def run_personalisation_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single personalisation test case and return the trace."""
    from app.ai.agents.personalisation.schemas import PersonalisationRequest
    from app.ai.agents.personalisation.service import PersonalisationService

    async def _invoke(c: dict[str, Any]) -> Any:  # noqa: ANN401
        service = PersonalisationService()
        request = PersonalisationRequest(
            html=str(c["html_input"]),
            platform=str(c["platform"]),  # pyright: ignore[reportArgumentType]
            requirements=str(c["requirements"]),
            stream=False,
            run_qa=True,
        )
        return await service.process(request)

    return await _run_case(
        "personalisation",
        case,
        invoke=_invoke,
        input_serializer=lambda c: {
            "html_input": str(c["html_input"]),
            "html_length": len(str(c["html_input"])),
            "platform": str(c["platform"]),
            "requirements": str(c["requirements"]),
        },
        output_serializer=lambda r: {
            "html": r.html,
            "platform": r.platform,
            "tags_injected": r.tags_injected,
            "qa_results": [x.model_dump() for x in (r.qa_results or [])],
            "qa_passed": r.qa_passed,
            "model": r.model,
        },
    )


async def run_code_reviewer_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single code reviewer test case and return the trace."""
    from app.ai.agents.code_reviewer.schemas import CodeReviewRequest
    from app.ai.agents.code_reviewer.service import CodeReviewService

    async def _invoke(c: dict[str, Any]) -> Any:  # noqa: ANN401
        service = CodeReviewService()
        request = CodeReviewRequest(
            html=str(c["html_input"]),
            focus=str(c.get("focus", "all")),  # pyright: ignore[reportArgumentType]
            stream=False,
            run_qa=True,
        )
        return await service.process(request)

    return await _run_case(
        "code_reviewer",
        case,
        invoke=_invoke,
        input_serializer=lambda c: {
            "html_input": str(c["html_input"]),
            "html_length": len(str(c["html_input"])),
            "focus": str(c.get("focus", "all")),
        },
        output_serializer=lambda r: {
            "html": r.html,
            "issues": [i.model_dump() for i in r.issues],
            "summary": r.summary,
            "skills_loaded": r.skills_loaded,
            "qa_results": [x.model_dump() for x in (r.qa_results or [])],
            "qa_passed": r.qa_passed,
            "model": r.model,
        },
    )


async def run_knowledge_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single knowledge test case and return the trace."""
    from app.ai.agents.knowledge.schemas import KnowledgeRequest
    from app.ai.agents.knowledge.service import KnowledgeAgentService
    from app.core.database import get_db_context
    from app.knowledge.services.search import SearchService as RAGService

    async def _invoke(c: dict[str, Any]) -> Any:  # noqa: ANN401
        service = KnowledgeAgentService()
        request = KnowledgeRequest(
            question=str(c["question"]),
            domain=c.get("domain"),
        )
        async with get_db_context() as db:
            rag_service = RAGService(db)
            return await service.process(request, rag_service)

    return await _run_case(
        "knowledge",
        case,
        invoke=_invoke,
        input_serializer=lambda c: {
            "question": str(c["question"]),
            "domain": c.get("domain"),
        },
        output_serializer=lambda r: {
            "answer": r.answer,
            "sources": [s.model_dump() for s in r.sources],
            "confidence": r.confidence,
            "skills_loaded": r.skills_loaded,
            "model": r.model,
        },
    )


async def run_innovation_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single innovation test case and return the trace."""
    from app.ai.agents.innovation.schemas import InnovationRequest
    from app.ai.agents.innovation.service import InnovationService

    async def _invoke(c: dict[str, Any]) -> Any:  # noqa: ANN401
        service = InnovationService()
        request = InnovationRequest(
            technique=str(c["technique"]),
            category=c.get("category"),
        )
        return await service.process(request)

    return await _run_case(
        "innovation",
        case,
        invoke=_invoke,
        input_serializer=lambda c: {
            "technique": str(c["technique"]),
            "category": c.get("category"),
        },
        output_serializer=lambda r: {
            "prototype": r.prototype,
            "feasibility": r.feasibility,
            "client_coverage": r.client_coverage,
            "risk_level": r.risk_level,
            "recommendation": r.recommendation,
            "fallback_html": r.fallback_html,
            "confidence": r.confidence,
            "skills_loaded": r.skills_loaded,
            "model": r.model,
        },
    )


def _scaffolder_cases(*, include_uploaded: bool = False) -> list[dict[str, Any]]:
    """Scaffolder cases, optionally folding in uploaded-template selection cases."""
    cases: list[dict[str, Any]] = list(SCAFFOLDER_TEST_CASES)
    if include_uploaded:
        gen = TemplateEvalGenerator()
        for tmpl_cases in gen.load_all().values():
            for c in tmpl_cases:
                if c.get("case_type") in ("selection_positive", "selection_negative"):
                    cases.append(c)
    return cases


def _static_cases(
    constant: list[dict[str, Any]],
) -> Callable[..., list[dict[str, Any]]]:
    """Build a cases_loader that returns a copy of a static case list, ignoring kwargs."""

    def _load(**_: object) -> list[dict[str, Any]]:
        return list(constant)

    return _load


AGENT_REGISTRY: dict[AgentName, AgentSpec] = {
    "scaffolder": AgentSpec(_scaffolder_cases, run_scaffolder_case),
    "dark_mode": AgentSpec(_static_cases(DARK_MODE_TEST_CASES), run_dark_mode_case),
    "content": AgentSpec(_static_cases(CONTENT_TEST_CASES), run_content_case),
    "outlook_fixer": AgentSpec(_static_cases(OUTLOOK_FIXER_TEST_CASES), run_outlook_fixer_case),
    "accessibility": AgentSpec(_static_cases(ACCESSIBILITY_TEST_CASES), run_accessibility_case),
    "personalisation": AgentSpec(
        _static_cases(PERSONALISATION_TEST_CASES), run_personalisation_case
    ),
    "code_reviewer": AgentSpec(_static_cases(CODE_REVIEWER_TEST_CASES), run_code_reviewer_case),
    "knowledge": AgentSpec(_static_cases(KNOWLEDGE_TEST_CASES), run_knowledge_case),
    "innovation": AgentSpec(_static_cases(INNOVATION_TEST_CASES), run_innovation_case),
}


async def run_agent(
    agent: str,
    output_dir: Path,
    *,
    dry_run: bool = False,
    batch_size: int = 5,
    delay: float = 3.0,
    skip_existing: bool = False,
    include_uploaded: bool = False,
    include_adversarial: bool = False,
) -> None:
    """Run all test cases for an agent and write traces to JSONL."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if agent not in AGENT_REGISTRY:
        raise ValueError(f"Unknown agent: {agent}")
    spec = AGENT_REGISTRY[agent]
    cases = spec.cases_loader(include_uploaded=include_uploaded)
    runner = spec.case_runner

    output_file = output_dir / f"{agent}_traces.jsonl"
    mode_label = " (dry-run)" if dry_run else ""

    # Load existing trace IDs for resume capability
    existing_ids: set[str] = set()
    if skip_existing and output_file.exists():
        with Path.open(output_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    existing_ids.add(json.loads(line)["id"])
        if existing_ids:
            logger.info(f"Resuming: {len(existing_ids)} existing traces found in {output_file}")

    file_mode = "a" if existing_ids else "w"
    logger.info(f"Running {len(cases)} test cases for {agent}{mode_label}...")

    trace_count = 0
    error_count = 0

    with Path.open(output_file, file_mode) as f:
        if dry_run:
            from app.ai.agents.evals.mock_traces import generate_mock_trace

            for i, case in enumerate(cases, 1):
                if case["id"] in existing_ids:
                    logger.debug(f"  [{i}/{len(cases)}] {case['id']}... SKIPPED (exists)")
                    continue
                logger.debug(f"  [{i}/{len(cases)}] {case['id']}... (dry-run)")
                trace = generate_mock_trace(case, agent)
                f.write(json.dumps(redact_value(trace)) + "\n")
                f.flush()
                trace_count += 1
        else:
            for i, case in enumerate(cases, 1):
                if case["id"] in existing_ids:
                    logger.debug(f"  [{i}/{len(cases)}] {case['id']}... SKIPPED (exists)")
                    continue
                logger.debug(f"  [{i}/{len(cases)}] {case['id']}...")
                trace = await runner(case)
                f.write(json.dumps(redact_value(trace)) + "\n")
                f.flush()
                trace_count += 1
                if trace["error"] is not None:
                    error_count += 1
                status = "OK" if trace["error"] is None else f"ERROR: {trace['error']}"
                logger.debug(f"    {status} ({trace['elapsed_seconds']}s)")
                if (i % batch_size == 0) and i < len(cases):
                    logger.debug(f"  Rate limit pause ({delay}s)...")
                    await asyncio.sleep(delay)

    total = trace_count + len(existing_ids)
    passed = total - error_count
    logger.info(f"Done: {passed}/{total} succeeded. Traces: {output_file}")

    # --- Adversarial cases (separate output file) ---
    if include_adversarial:
        from app.ai.agents.evals.adversarial import adversarial_to_runner_dict, get_all_cases

        adv_cases_raw = get_all_cases(agent)
        adv_cases = [adversarial_to_runner_dict(ac) for ac in adv_cases_raw]
        adv_output_file = output_dir / f"{agent}_adversarial_traces.jsonl"

        adv_existing: set[str] = set()
        if skip_existing and adv_output_file.exists():
            with Path.open(adv_output_file) as af:
                for line in af:
                    stripped = line.strip()
                    if stripped:
                        adv_existing.add(json.loads(stripped)["id"])

        adv_mode = "a" if adv_existing else "w"
        adv_count = 0
        adv_errors = 0
        logger.info(f"Running {len(adv_cases)} adversarial cases for {agent}{mode_label}...")

        with Path.open(adv_output_file, adv_mode) as af:
            if dry_run:
                from app.ai.agents.evals.mock_traces import generate_mock_trace

                for case in adv_cases:
                    if case["id"] in adv_existing:
                        continue
                    trace = generate_mock_trace(case, agent)
                    af.write(json.dumps(redact_value(trace)) + "\n")
                    af.flush()
                    adv_count += 1
            else:
                for i, case in enumerate(adv_cases, 1):
                    if case["id"] in adv_existing:
                        continue
                    logger.debug(f"  [{i}/{len(adv_cases)}] {case['id']}...")
                    trace = await runner(case)
                    af.write(json.dumps(redact_value(trace)) + "\n")
                    af.flush()
                    adv_count += 1
                    if trace["error"] is not None:
                        adv_errors += 1
                    if (i % batch_size == 0) and i < len(adv_cases):
                        await asyncio.sleep(delay)

        adv_total = adv_count + len(adv_existing)
        adv_passed = adv_total - adv_errors
        logger.info(f"Adversarial: {adv_passed}/{adv_total} succeeded. Traces: {adv_output_file}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run agent evals")
    parser.add_argument(
        "--agent",
        choices=[*AGENT_NAMES, "all"],
        required=True,
    )
    parser.add_argument("--output", type=Path, default=Path("traces"))
    parser.add_argument("--dry-run", action="store_true", help="Generate mock traces without LLM")
    parser.add_argument(
        "--batch-size", type=int, default=5, help="Traces per batch before delay (default: 5)"
    )
    parser.add_argument(
        "--delay", type=float, default=3.0, help="Seconds between batches (default: 3.0)"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip test cases already in output file (resume after crash)",
    )
    parser.add_argument(
        "--include-uploaded",
        action="store_true",
        help="Include eval cases from uploaded templates",
    )
    parser.add_argument(
        "--include-adversarial",
        action="store_true",
        help="Include adversarial test cases (written to separate JSONL)",
    )
    args = parser.parse_args()

    agents = list(AGENT_NAMES) if args.agent == "all" else [args.agent]

    for agent in agents:
        await run_agent(
            agent,
            args.output,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            delay=args.delay,
            skip_existing=args.skip_existing,
            include_uploaded=args.include_uploaded,
            include_adversarial=args.include_adversarial,
        )


if __name__ == "__main__":
    asyncio.run(main())
