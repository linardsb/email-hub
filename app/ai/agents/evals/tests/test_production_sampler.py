"""Tests for production trace sampling and offline judge feedback loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.agents.evals.production_sampler import (
    ProductionJudgeWorker,
    _append_verdicts,
    _judge_trace,
    enqueue_for_judging,
    refresh_analysis,
)


class TestEnqueueForJudging:
    """Tests for probabilistic Redis enqueue."""

    @pytest.mark.asyncio
    async def test_enqueue_disabled_when_rate_zero(self) -> None:
        result = await enqueue_for_judging(
            run_id="run-1",
            blueprint_name="campaign",
            brief="Test brief",
            html="<html></html>",
            agents_executed=["scaffolder"],
            sample_rate=0.0,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_enqueue_always_when_rate_one(self) -> None:
        mock_redis = AsyncMock()
        with patch(
            "app.ai.agents.evals.production_sampler.get_redis",
            return_value=mock_redis,
        ):
            result = await enqueue_for_judging(
                run_id="run-2",
                blueprint_name="campaign",
                brief="Test brief",
                html="<html></html>",
                agents_executed=["scaffolder"],
                sample_rate=1.0,
            )
        assert result is True
        mock_redis.lpush.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_payload_structure(self) -> None:
        mock_redis = AsyncMock()
        with patch(
            "app.ai.agents.evals.production_sampler.get_redis",
            return_value=mock_redis,
        ):
            await enqueue_for_judging(
                run_id="run-3",
                blueprint_name="campaign",
                brief="My brief",
                html="<div>Hello</div>",
                agents_executed=["scaffolder", "dark_mode"],
                sample_rate=1.0,
            )
        call_args = mock_redis.lpush.call_args
        payload = json.loads(call_args[0][1])
        assert payload["run_id"] == "run-3"
        assert payload["blueprint_name"] == "campaign"
        assert payload["brief"] == "My brief"
        assert payload["agents_executed"] == ["scaffolder", "dark_mode"]
        assert payload["trace_id"].startswith("prod-run-3-")

    @pytest.mark.asyncio
    async def test_enqueue_redis_failure_returns_false(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.lpush.side_effect = ConnectionError("Redis down")
        with patch(
            "app.ai.agents.evals.production_sampler.get_redis",
            return_value=mock_redis,
        ):
            result = await enqueue_for_judging(
                run_id="run-4",
                blueprint_name="campaign",
                brief="Test",
                html="<html></html>",
                agents_executed=["scaffolder"],
                sample_rate=1.0,
            )
        assert result is False


class TestAppendVerdicts:
    """Tests for JSONL append."""

    def test_append_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "verdicts.jsonl"
        verdicts: list[dict[str, Any]] = [
            {"trace_id": "t1", "agent": "scaffolder", "overall_pass": True},
        ]
        _append_verdicts(verdicts, path)
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["trace_id"] == "t1"

    def test_append_adds_to_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "verdicts.jsonl"
        path.write_text('{"existing": true}\n')
        _append_verdicts([{"new": True}], path)
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2


class TestRefreshAnalysis:
    """Tests for merging production + synthetic verdicts."""

    def test_refresh_merges_sources(self, tmp_path: Path) -> None:
        # Write synthetic verdict
        syn_path = tmp_path / "scaffolder_verdicts.jsonl"
        syn_path.write_text(
            json.dumps(
                {
                    "trace_id": "syn-1",
                    "agent": "scaffolder",
                    "overall_pass": True,
                    "criteria": {"structure": {"passed": True, "reasoning": "ok"}},
                }
            )
            + "\n"
        )

        # Write production verdict
        prod_path = tmp_path / "production_verdicts.jsonl"
        prod_path.write_text(
            json.dumps(
                {
                    "trace_id": "prod-1",
                    "agent": "scaffolder",
                    "overall_pass": False,
                    "criteria": {"structure": {"passed": False, "reasoning": "bad"}},
                }
            )
            + "\n"
        )

        output = tmp_path / "analysis.json"
        report = refresh_analysis(
            synthetic_verdicts_dir=tmp_path,
            production_verdicts_path=prod_path,
            output_path=output,
        )

        assert output.exists()
        assert report["summary"]["total_traces"] == 2

    def test_refresh_no_verdicts_returns_empty(self, tmp_path: Path) -> None:
        report = refresh_analysis(
            synthetic_verdicts_dir=tmp_path,
            production_verdicts_path=tmp_path / "nonexistent.jsonl",
            output_path=tmp_path / "analysis.json",
        )
        assert report == {}


class TestProductionJudgeWorker:
    """Tests for the DataPoller-based worker."""

    @pytest.mark.asyncio
    async def test_fetch_empty_queue(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.rpop.return_value = None
        with patch(
            "app.ai.agents.evals.production_sampler.get_redis",
            return_value=mock_redis,
        ):
            worker = ProductionJudgeWorker()
            result = await worker.fetch()
        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_returns_traces(self) -> None:
        trace = json.dumps({"trace_id": "t1", "agents_executed": ["scaffolder"]})
        mock_redis = AsyncMock()
        mock_redis.rpop.side_effect = [trace, None]
        with patch(
            "app.ai.agents.evals.production_sampler.get_redis",
            return_value=mock_redis,
        ):
            worker = ProductionJudgeWorker()
            result = await worker.fetch()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_store_skips_empty(self) -> None:
        worker = ProductionJudgeWorker()
        # Should not raise or write anything
        await worker.store([])

    @pytest.mark.asyncio
    async def test_enrich_delegates_to_judge_trace(self) -> None:
        """enrich() with non-empty traces calls _judge_trace per trace."""
        traces = [
            {
                "trace_id": "t1",
                "brief": "b",
                "html": "<p>hi</p>",
                "agents_executed": ["scaffolder"],
            },
        ]
        mock_verdict: dict[str, Any] = {
            "trace_id": "t1",
            "source": "production",
            "agent": "scaffolder",
            "overall_pass": True,
            "criteria": [],
        }
        with patch(
            "app.ai.agents.evals.production_sampler._judge_trace",
            return_value=[mock_verdict],
        ):
            worker = ProductionJudgeWorker()
            result = await worker.enrich(traces)
        assert len(result) == 1
        assert result[0]["trace_id"] == "t1"


class TestJudgeTrace:
    """Tests for _judge_trace — LLM judge call + verdict assembly."""

    @pytest.mark.asyncio
    async def test_produces_verdict_per_agent(self) -> None:
        """Judges each agent in the trace and returns structured verdicts."""
        from app.ai.agents.evals.judges.schemas import CriterionResult, JudgeVerdict
        from app.ai.protocols import CompletionResponse

        trace: dict[str, Any] = {
            "trace_id": "prod-test-abc",
            "brief": "Campaign brief",
            "html": "<table><tr><td>hello</td></tr></table>",
            "agents_executed": ["scaffolder"],
        }

        mock_verdict = JudgeVerdict(
            trace_id="prod-test-abc",
            agent="scaffolder",
            overall_pass=True,
            criteria_results=[
                CriterionResult(criterion="structure", passed=True, reasoning="Looks good"),
            ],
        )

        # Judge has sync methods (build_prompt, parse_response)
        mock_judge = MagicMock()
        mock_judge.build_prompt.return_value = "Judge this HTML"
        mock_judge.parse_response.return_value = mock_verdict

        # Provider has async complete()
        mock_provider = AsyncMock()
        mock_provider.complete.return_value = CompletionResponse(
            content='{"overall_pass": true}',
            model="gpt-4o-mini",
        )

        # Registry has sync get_llm()
        mock_registry = MagicMock()
        mock_registry.get_llm.return_value = mock_provider

        with (
            patch(
                "app.ai.agents.evals.production_sampler.JUDGE_REGISTRY",
                {"scaffolder": lambda: mock_judge},
            ),
            patch(
                "app.ai.agents.evals.production_sampler.get_registry",
                return_value=mock_registry,
            ),
            patch(
                "app.ai.agents.evals.production_sampler.resolve_model",
                return_value="gpt-4o-mini",
            ),
        ):
            verdicts = await _judge_trace(trace)

        assert len(verdicts) == 1
        v = verdicts[0]
        assert v["trace_id"] == "prod-test-abc"
        assert v["source"] == "production"
        assert v["agent"] == "scaffolder"
        assert v["overall_pass"] is True
        assert v["criteria"][0]["criterion"] == "structure"

        mock_judge.build_prompt.assert_called_once()
        mock_provider.complete.assert_called_once()
        mock_judge.parse_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_agents_without_judge(self) -> None:
        """Agents not in JUDGE_REGISTRY are silently skipped."""
        trace: dict[str, Any] = {
            "trace_id": "prod-test-xyz",
            "brief": "Brief",
            "html": "<p>hi</p>",
            "agents_executed": ["nonexistent_agent"],
        }

        mock_registry = MagicMock()
        empty_registry: dict[str, object] = {}
        with (
            patch(
                "app.ai.agents.evals.production_sampler.JUDGE_REGISTRY",
                empty_registry,
            ),
            patch(
                "app.ai.agents.evals.production_sampler.get_registry",
                return_value=mock_registry,
            ),
            patch(
                "app.ai.agents.evals.production_sampler.resolve_model",
                return_value="gpt-4o-mini",
            ),
        ):
            verdicts = await _judge_trace(trace)

        assert verdicts == []

    @pytest.mark.asyncio
    async def test_llm_failure_skips_agent_continues(self) -> None:
        """LLM error for one agent doesn't crash the batch."""
        from app.ai.agents.evals.judges.schemas import CriterionResult, JudgeVerdict
        from app.ai.protocols import CompletionResponse

        trace: dict[str, Any] = {
            "trace_id": "prod-test-err",
            "brief": "Brief",
            "html": "<p>hi</p>",
            "agents_executed": ["scaffolder", "dark_mode"],
        }

        # Both judges are sync
        mock_judge_scaffolder = MagicMock()
        mock_judge_scaffolder.build_prompt.return_value = "prompt"

        mock_judge_dark = MagicMock()
        mock_judge_dark.build_prompt.return_value = "prompt"
        mock_judge_dark.parse_response.return_value = JudgeVerdict(
            trace_id="prod-test-err",
            agent="dark_mode",
            overall_pass=True,
            criteria_results=[
                CriterionResult(criterion="contrast", passed=True, reasoning="ok"),
            ],
        )

        # Provider: first call raises, second succeeds
        mock_provider = AsyncMock()
        mock_provider.complete.side_effect = [
            RuntimeError("LLM timeout"),
            CompletionResponse(content='{"pass": true}', model="gpt-4o-mini"),
        ]

        mock_registry = MagicMock()
        mock_registry.get_llm.return_value = mock_provider

        with (
            patch(
                "app.ai.agents.evals.production_sampler.JUDGE_REGISTRY",
                {
                    "scaffolder": lambda: mock_judge_scaffolder,
                    "dark_mode": lambda: mock_judge_dark,
                },
            ),
            patch(
                "app.ai.agents.evals.production_sampler.get_registry",
                return_value=mock_registry,
            ),
            patch(
                "app.ai.agents.evals.production_sampler.resolve_model",
                return_value="gpt-4o-mini",
            ),
        ):
            verdicts = await _judge_trace(trace)

        # scaffolder failed, dark_mode succeeded → 1 verdict
        assert len(verdicts) == 1
        assert verdicts[0]["agent"] == "dark_mode"
