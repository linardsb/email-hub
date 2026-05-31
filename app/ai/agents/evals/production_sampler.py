"""Production trace sampling for offline judge feedback loop.

Samples successful blueprint runs, enqueues for async LLM judging,
and merges verdicts back into the analysis report.
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import Any

from app.ai.agents.evals.error_analysis import build_analysis_report, load_verdicts
from app.ai.agents.evals.judges import JUDGE_REGISTRY
from app.ai.agents.evals.judges.schemas import JudgeInput, JudgeVerdict
from app.ai.protocols import CompletionResponse, Message
from app.ai.registry import get_registry
from app.ai.routing import resolve_model
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.poller import DataPoller
from app.core.redaction import redact_pii, redact_value
from app.core.redis import get_redis

logger = get_logger(__name__)


async def enqueue_for_judging(
    run_id: str,
    blueprint_name: str,
    brief: str,
    html: str,
    agents_executed: list[str],
    sample_rate: float | None = None,
) -> bool:
    """Probabilistically enqueue a completed blueprint run for offline judging.

    Args:
        run_id: Unique blueprint run ID.
        blueprint_name: Name of the blueprint that was executed.
        brief: The original brief text.
        html: Final HTML output.
        agents_executed: List of agent names that ran in this pipeline.
        sample_rate: Override sample rate (uses config default if None).

    Returns:
        True if the trace was enqueued, False if skipped.
    """
    settings = get_settings()
    rate = sample_rate if sample_rate is not None else settings.eval.production_sample_rate

    if rate <= 0.0:
        return False

    if random.random() > rate:
        return False

    trace_payload = {
        "trace_id": f"prod-{run_id}-{uuid.uuid4().hex[:8]}",
        "run_id": run_id,
        "blueprint_name": blueprint_name,
        "brief": redact_pii(brief),
        "html": redact_pii(html),
        "agents_executed": agents_executed,
    }

    try:
        redis = await get_redis()
        await redis.lpush(
            settings.eval.production_queue_key,
            json.dumps(trace_payload),
        )
        logger.info(
            "eval.production_sampler.enqueued",
            run_id=run_id,
            trace_id=trace_payload["trace_id"],
        )
        return True
    except Exception:
        logger.warning(
            "eval.production_sampler.enqueue_failed",
            run_id=run_id,
            exc_info=True,
        )
        return False


async def _judge_trace(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Run all applicable judges on a single production trace.

    Returns a list of verdict dicts (one per agent that was judged).
    """
    settings = get_settings()
    registry = get_registry()
    provider = registry.get_llm(settings.ai.provider)
    model = resolve_model("lightweight")

    verdicts: list[dict[str, Any]] = []

    for agent_name in trace.get("agents_executed", []):
        judge_cls = JUDGE_REGISTRY.get(agent_name)
        if judge_cls is None:
            continue

        judge = judge_cls()
        judge_input = JudgeInput(
            trace_id=trace["trace_id"],
            agent=agent_name,
            input_data={"brief": trace["brief"]},
            output_data={"html": trace["html"]},
            expected_challenges=[],
        )

        prompt = judge.build_prompt(judge_input)

        try:
            response: CompletionResponse = await provider.complete(
                [Message(role="user", content=prompt)],
                temperature=0.0,
                model=model,
            )
            verdict: JudgeVerdict = judge.parse_response(response.content, judge_input)

            verdicts.append(
                {
                    "trace_id": trace["trace_id"],
                    "source": "production",
                    "agent": agent_name,
                    "overall_pass": verdict.overall_pass,
                    "criteria": [
                        {
                            "criterion": cr.criterion,
                            "passed": cr.passed,
                            "reasoning": cr.reasoning,
                        }
                        for cr in verdict.criteria_results
                    ],
                }
            )

            logger.info(
                "eval.production_sampler.judged",
                trace_id=trace["trace_id"],
                agent=agent_name,
                overall_pass=verdict.overall_pass,
            )
        except Exception:
            logger.warning(
                "eval.production_sampler.judge_failed",
                trace_id=trace["trace_id"],
                agent=agent_name,
                exc_info=True,
            )

    return verdicts


def _append_verdicts(verdicts: list[dict[str, Any]], path: Path) -> None:
    """Append verdict dicts as JSONL lines.

    PII is redacted from verdict reasoning before writing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for v in verdicts:
            f.write(json.dumps(redact_value(v)) + "\n")


def refresh_analysis(
    synthetic_verdicts_dir: Path | None = None,
    production_verdicts_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Merge production + synthetic verdicts and regenerate analysis.json.

    Args:
        synthetic_verdicts_dir: Directory with *_verdicts.jsonl files (default: traces/).
        production_verdicts_path: Path to production_verdicts.jsonl (default: from config).
        output_path: Where to write merged analysis.json (default: traces/analysis.json).

    Returns:
        The merged analysis report dict.
    """
    settings = get_settings()
    traces_dir = Path("traces")

    syn_dir = synthetic_verdicts_dir or traces_dir
    prod_path = production_verdicts_path or Path(settings.eval.verdicts_path)
    out_path = output_path or traces_dir / "analysis.json"

    # Load all synthetic verdicts
    all_verdicts: list[dict[str, Any]] = []
    for f in sorted(syn_dir.glob("*_verdicts.jsonl")):
        if f.name == "production_verdicts.jsonl":
            continue  # handled separately
        all_verdicts.extend(load_verdicts(f))

    # Load production verdicts
    if prod_path.exists():
        prod_verdicts = load_verdicts(prod_path)
        all_verdicts.extend(prod_verdicts)
        logger.info(
            "eval.production_sampler.production_verdicts_loaded",
            path=str(prod_path),
            count=len(prod_verdicts),
        )

    if not all_verdicts:
        logger.warning("eval.production_sampler.no_verdicts_found")
        return {}

    report = build_analysis_report(all_verdicts)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        json.dump(report, fh, indent=2)

    logger.info(
        "eval.production_sampler.analysis_refreshed",
        total_verdicts=len(all_verdicts),
        output=str(out_path),
    )

    return report


class ProductionJudgeWorker(DataPoller):
    """Background worker that processes enqueued production traces.

    Pulls traces from Redis queue, runs agent-specific judges,
    appends verdicts to production_verdicts.jsonl.
    Uses DataPoller pattern (same as OutcomeGraphPoller, CanIEmailSyncPoller).
    """

    def __init__(self) -> None:
        settings = get_settings()
        super().__init__(
            name="production-judge-worker",
            interval_seconds=settings.eval.worker_interval_seconds,
        )
        self._queue_key = settings.eval.production_queue_key
        self._verdicts_path = Path(settings.eval.verdicts_path)
        self._batch_size = 10  # Process up to 10 traces per cycle

    async def fetch(self) -> list[dict[str, Any]]:
        """Pull pending traces from Redis queue."""
        redis = await get_redis()
        traces: list[dict[str, Any]] = []

        for _ in range(self._batch_size):
            raw = await redis.rpop(self._queue_key)
            if raw is None:
                break
            traces.append(json.loads(str(raw)))  # pyright: ignore[reportUnknownArgumentType]

        return traces

    async def enrich(self, raw: object) -> list[dict[str, Any]]:
        """Judge each trace."""
        traces: list[dict[str, Any]] = raw  # type: ignore[assignment]
        if not traces:
            return []

        all_verdicts: list[dict[str, Any]] = []
        for trace in traces:
            verdicts = await _judge_trace(trace)
            all_verdicts.extend(verdicts)

        return all_verdicts

    async def store(self, data: object) -> None:
        """Append verdicts to JSONL and refresh analysis."""
        verdicts: list[dict[str, Any]] = data  # type: ignore[assignment]
        if not verdicts:
            return

        _append_verdicts(verdicts, self._verdicts_path)

        # Refresh merged analysis after new verdicts
        refresh_analysis()

        logger.info(
            "eval.production_judge_worker.cycle_completed",
            verdicts_written=len(verdicts),
        )
