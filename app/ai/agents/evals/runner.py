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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


async def run_scaffolder_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single scaffolder test case and return the trace."""
    from app.ai.agents.scaffolder.schemas import ScaffolderRequest
    from app.ai.agents.scaffolder.service import ScaffolderService

    service = ScaffolderService()
    request = ScaffolderRequest(brief=case["brief"], stream=False, run_qa=True)

    start = time.monotonic()
    try:
        response = await service.generate(request)
        elapsed = time.monotonic() - start
        trace: dict[str, Any] = {
            "id": case["id"],
            "agent": "scaffolder",
            "dimensions": case["dimensions"],
            "input": {"brief": case["brief"]},
            "output": {
                "html": response.html,
                "qa_results": [r.model_dump() for r in (response.qa_results or [])],
                "qa_passed": response.qa_passed,
                "model": response.model,
            },
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if case.get("design_context"):
            trace["design_context"] = case["design_context"]
        return trace
    except Exception as e:
        elapsed = time.monotonic() - start
        trace = {
            "id": case["id"],
            "agent": "scaffolder",
            "dimensions": case["dimensions"],
            "input": {"brief": case["brief"]},
            "output": None,
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": f"{type(e).__name__}: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if case.get("design_context"):
            trace["design_context"] = case["design_context"]
        return trace


async def run_dark_mode_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single dark mode test case and return the trace."""
    from app.ai.agents.dark_mode.schemas import DarkModeRequest
    from app.ai.agents.dark_mode.service import DarkModeService

    service = DarkModeService()
    request = DarkModeRequest(
        html=case["html_input"],
        color_overrides=case.get("color_overrides"),
        preserve_colors=case.get("preserve_colors"),
        stream=False,
        run_qa=True,
    )

    start = time.monotonic()
    try:
        response = await service.process(request)
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "dark_mode",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": case["html_input"][:5000],
                "html_length": len(case["html_input"]),
                "color_overrides": case.get("color_overrides"),
                "preserve_colors": case.get("preserve_colors"),
            },
            "output": {
                "html": response.html,
                "qa_results": [r.model_dump() for r in (response.qa_results or [])],
                "qa_passed": response.qa_passed,
                "model": response.model,
            },
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "dark_mode",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": case["html_input"][:5000],
                "html_length": len(case["html_input"]),
                "color_overrides": case.get("color_overrides"),
                "preserve_colors": case.get("preserve_colors"),
            },
            "output": None,
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": f"{type(e).__name__}: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }


async def run_content_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single content test case and return the trace."""
    from app.ai.agents.content.schemas import ContentRequest
    from app.ai.agents.content.service import ContentService

    service = ContentService()
    inp = case["input"]
    request = ContentRequest(
        operation=inp["operation"],
        text=inp["text"],
        tone=inp.get("tone"),
        brand_voice=inp.get("brand_voice"),
        num_alternatives=inp.get("num_alternatives", 1),
        stream=False,
    )

    start = time.monotonic()
    try:
        response = await service.generate(request)
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "content",
            "dimensions": case["dimensions"],
            "input": inp,
            "output": {
                "content": response.content,
                "operation": response.operation,
                "spam_warnings": [w.model_dump() for w in response.spam_warnings],
                "model": response.model,
            },
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "content",
            "dimensions": case["dimensions"],
            "input": inp,
            "output": None,
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": f"{type(e).__name__}: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }


async def run_outlook_fixer_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single Outlook Fixer test case and return the trace."""
    from app.ai.agents.outlook_fixer.schemas import OutlookFixerRequest
    from app.ai.agents.outlook_fixer.service import OutlookFixerService

    service = OutlookFixerService()
    html_input: str = str(case["html_input"])
    request = OutlookFixerRequest(
        html=html_input,
        issues=None,
        stream=False,
        run_qa=True,
    )

    start = time.monotonic()
    try:
        response = await service.process(request)
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "outlook_fixer",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": html_input,
                "html_length": len(html_input),
            },
            "output": {
                "html": response.html,
                "fixes_applied": response.fixes_applied,
                "qa_results": [r.model_dump() for r in (response.qa_results or [])],
                "qa_passed": response.qa_passed,
                "model": response.model,
            },
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "outlook_fixer",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": html_input,
                "html_length": len(html_input),
            },
            "output": None,
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": f"{type(e).__name__}: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }


async def run_accessibility_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single accessibility test case and return the trace."""
    from app.ai.agents.accessibility.schemas import AccessibilityRequest
    from app.ai.agents.accessibility.service import AccessibilityService

    service = AccessibilityService()
    html_input: str = str(case["html_input"])
    request = AccessibilityRequest(
        html=html_input,
        focus_areas=None,
        stream=False,
        run_qa=True,
    )

    start = time.monotonic()
    try:
        response = await service.process(request)
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "accessibility",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": html_input,
                "html_length": len(html_input),
            },
            "output": {
                "html": response.html,
                "skills_loaded": response.skills_loaded,
                "qa_results": [r.model_dump() for r in (response.qa_results or [])],
                "qa_passed": response.qa_passed,
                "model": response.model,
            },
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "accessibility",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": html_input,
                "html_length": len(html_input),
            },
            "output": None,
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": f"{type(e).__name__}: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }


async def run_personalisation_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single personalisation test case and return the trace."""
    from app.ai.agents.personalisation.schemas import PersonalisationRequest
    from app.ai.agents.personalisation.service import PersonalisationService

    service = PersonalisationService()
    html_input: str = str(case["html_input"])
    platform: str = str(case["platform"])
    requirements: str = str(case["requirements"])
    request = PersonalisationRequest(
        html=html_input,
        platform=platform,  # pyright: ignore[reportArgumentType]
        requirements=requirements,
        stream=False,
        run_qa=True,
    )

    start = time.monotonic()
    try:
        response = await service.process(request)
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "personalisation",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": html_input,
                "html_length": len(html_input),
                "platform": platform,
                "requirements": requirements,
            },
            "output": {
                "html": response.html,
                "platform": response.platform,
                "tags_injected": response.tags_injected,
                "qa_results": [r.model_dump() for r in (response.qa_results or [])],
                "qa_passed": response.qa_passed,
                "model": response.model,
            },
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "personalisation",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": html_input,
                "html_length": len(html_input),
                "platform": platform,
                "requirements": requirements,
            },
            "output": None,
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": f"{type(e).__name__}: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }


async def run_code_reviewer_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single code reviewer test case and return the trace."""
    from app.ai.agents.code_reviewer.schemas import CodeReviewRequest
    from app.ai.agents.code_reviewer.service import CodeReviewService

    service = CodeReviewService()
    html_input: str = str(case["html_input"])
    focus: str = str(case.get("focus", "all"))
    request = CodeReviewRequest(
        html=html_input,
        focus=focus,  # pyright: ignore[reportArgumentType]
        stream=False,
        run_qa=True,
    )

    start = time.monotonic()
    try:
        response = await service.process(request)
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "code_reviewer",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": html_input,
                "html_length": len(html_input),
                "focus": focus,
            },
            "output": {
                "html": response.html,
                "issues": [i.model_dump() for i in response.issues],
                "summary": response.summary,
                "skills_loaded": response.skills_loaded,
                "qa_results": [r.model_dump() for r in (response.qa_results or [])],
                "qa_passed": response.qa_passed,
                "model": response.model,
            },
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "code_reviewer",
            "dimensions": case["dimensions"],
            "input": {
                "html_input": html_input,
                "html_length": len(html_input),
                "focus": focus,
            },
            "output": None,
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": f"{type(e).__name__}: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }


async def run_knowledge_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single knowledge test case and return the trace."""
    from app.ai.agents.knowledge.schemas import KnowledgeRequest
    from app.ai.agents.knowledge.service import KnowledgeAgentService
    from app.core.database import get_db_context
    from app.knowledge.services.search import SearchService as RAGService

    service = KnowledgeAgentService()
    question: str = str(case["question"])
    domain: str | None = case.get("domain")
    request = KnowledgeRequest(question=question, domain=domain)

    start = time.monotonic()
    try:
        async with get_db_context() as db:
            rag_service = RAGService(db)
            response = await service.process(request, rag_service)
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "knowledge",
            "dimensions": case["dimensions"],
            "input": {
                "question": question,
                "domain": domain,
            },
            "output": {
                "answer": response.answer,
                "sources": [s.model_dump() for s in response.sources],
                "confidence": response.confidence,
                "skills_loaded": response.skills_loaded,
                "model": response.model,
            },
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "knowledge",
            "dimensions": case["dimensions"],
            "input": {
                "question": question,
                "domain": domain,
            },
            "output": None,
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": f"{type(e).__name__}: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
        }


async def run_innovation_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run a single innovation test case and return the trace."""
    from app.ai.agents.innovation.schemas import InnovationRequest
    from app.ai.agents.innovation.service import InnovationService

    service = InnovationService()
    technique: str = str(case["technique"])
    category: str | None = case.get("category")
    request = InnovationRequest(technique=technique, category=category)

    start = time.monotonic()
    try:
        response = await service.process(request)
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "innovation",
            "dimensions": case["dimensions"],
            "input": {
                "technique": technique,
                "category": category,
            },
            "output": {
                "prototype": response.prototype,
                "feasibility": response.feasibility,
                "client_coverage": response.client_coverage,
                "risk_level": response.risk_level,
                "recommendation": response.recommendation,
                "fallback_html": response.fallback_html,
                "confidence": response.confidence,
                "skills_loaded": response.skills_loaded,
                "model": response.model,
            },
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        elapsed = time.monotonic() - start
        return {
            "id": case["id"],
            "agent": "innovation",
            "dimensions": case["dimensions"],
            "input": {
                "technique": technique,
                "category": category,
            },
            "output": None,
            "expected_challenges": case.get("expected_challenges"),
            "elapsed_seconds": round(elapsed, 2),
            "error": f"{type(e).__name__}: {e}",
            "timestamp": datetime.now(UTC).isoformat(),
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

    cases: list[dict[str, Any]]
    runner: Any
    if agent == "scaffolder":
        cases = list(SCAFFOLDER_TEST_CASES)
        if include_uploaded:
            gen = TemplateEvalGenerator()
            for tmpl_cases in gen.load_all().values():
                for c in tmpl_cases:
                    if c.get("case_type") in (
                        "selection_positive",
                        "selection_negative",
                    ):
                        cases.append(c)
        runner = run_scaffolder_case
    elif agent == "dark_mode":
        cases = DARK_MODE_TEST_CASES
        runner = run_dark_mode_case
    elif agent == "content":
        cases = CONTENT_TEST_CASES
        runner = run_content_case
    elif agent == "outlook_fixer":
        cases = OUTLOOK_FIXER_TEST_CASES
        runner = run_outlook_fixer_case
    elif agent == "accessibility":
        cases = ACCESSIBILITY_TEST_CASES
        runner = run_accessibility_case
    elif agent == "personalisation":
        cases = PERSONALISATION_TEST_CASES
        runner = run_personalisation_case
    elif agent == "code_reviewer":
        cases = CODE_REVIEWER_TEST_CASES
        runner = run_code_reviewer_case
    elif agent == "knowledge":
        cases = KNOWLEDGE_TEST_CASES
        runner = run_knowledge_case
    elif agent == "innovation":
        cases = INNOVATION_TEST_CASES
        runner = run_innovation_case
    else:
        raise ValueError(f"Unknown agent: {agent}")

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
        choices=[
            "scaffolder",
            "dark_mode",
            "content",
            "outlook_fixer",
            "accessibility",
            "personalisation",
            "code_reviewer",
            "knowledge",
            "innovation",
            "all",
        ],
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

    agents = (
        [
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
        if args.agent == "all"
        else [args.agent]
    )

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
