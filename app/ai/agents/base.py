# pyright: reportUnknownVariableType=false, reportGeneralTypeIssues=false
# ruff: noqa: ANN401
"""Base agent service — shared pipeline for HTML transformer agents.

Eliminates ~80% code duplication across scaffolder, dark_mode, outlook_fixer,
accessibility, and personalisation agents.  Each subclass overrides only
what's unique: model tier, user message construction, skill detection,
and post-processing.

Uses ``Any`` for request/response types because each agent has its own
Pydantic schema.  Concrete subclasses narrow the types in their overrides.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.ai.multimodal import ContentBlock, ImageBlock, TextBlock

from app.ai.agents.audit import hash_input, log_agent_decision
from app.ai.agents.exceptions import ToolCapExceededError
from app.ai.agents.types import BaseAgentRequest
from app.ai.blueprints.protocols import AgentHandoff, HandoffStatus
from app.ai.exceptions import AIExecutionError
from app.ai.fallback import call_with_fallback
from app.ai.protocols import Message
from app.ai.registry import get_registry
from app.ai.routing import TaskTier, get_fallback_chain, resolve_model
from app.ai.sanitize import sanitize_prompt, validate_output
from app.ai.security.prompt_guard import scan_for_injection
from app.ai.shared import extract_confidence, extract_html, sanitize_html_xss
from app.ai.token_budget import TokenBudgetManager
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.qa_engine.checks import ALL_CHECKS
from app.qa_engine.schemas import QACheckResult

logger = get_logger(__name__)

# Confidence scoring instruction appended to system prompts
CONFIDENCE_INSTRUCTION = (
    "\n\nEnd your response with <!-- CONFIDENCE: X.XX --> where X.XX is your "
    "confidence (0.00-1.00) in the output quality."
)


class _ToolCallCounter:
    """Per-``process()`` tool-call cap + planning-step accumulator.

    Instantiated once per ``process()`` invocation (never a module global) so
    it resets between calls. ``record_tool_call`` raises ``ToolCapExceededError``
    on the ``max_calls + 1``-th call.
    """

    def __init__(self, *, agent: str, max_calls: int) -> None:
        self.agent = agent
        self.max_calls = max_calls
        self.count = 0
        self.planning_steps: list[str] = []

    def record_tool_call(self, step: str | None = None) -> None:
        self.count += 1
        if self.count > self.max_calls:
            raise ToolCapExceededError(self.agent, self.max_calls)
        if step:
            self.planning_steps.append(step)

    def record_planning_step(self, step: str) -> None:
        """Record a reasoning step without counting it as a tool call."""
        self.planning_steps.append(step)


class BaseAgentService:
    """Shared agent pipeline: prompt → LLM → post-process → QA.

    Subclasses MUST set ``agent_name`` and implement ``_build_user_message``
    and ``detect_relevant_skills``.  Optionally override ``_post_process``,
    ``_run_qa``, ``_build_response``, and class-level config attributes.
    """

    # ── Class-level config (override in subclass) ──
    agent_name: str = ""
    model_tier: TaskTier = "standard"
    max_tokens: int = 8192
    run_qa_default: bool = True
    stream_prefix: str = "agent"
    output_mode_default: str = "html"
    _output_mode_supported: bool = False
    sanitization_profile: str = "default"
    # Names of request fields carrying user-supplied free text.
    # Subclasses MUST list every string field that ``_build_user_message``
    # interpolates so the prompt-injection guard scans (and, in strip mode,
    # writes back) all attack-reachable inputs — not just the primary one.
    # Non-string fields (dicts, lists) need bespoke handling and are skipped.
    _user_input_fields: tuple[str, ...] = ()

    # ── Output mode ──

    def _get_output_mode(self, request: BaseAgentRequest) -> str:
        """Extract output_mode from request, with fallback to class default.

        Agent-specific request schemas declare ``output_mode`` themselves
        (Scaffolder, DarkMode, Content, etc.) — ``BaseAgentRequest`` only
        carries orchestrator-injected fields, so dynamic lookup remains the
        safe access pattern for the per-agent field.
        """
        value = getattr(request, "output_mode", self.output_mode_default)
        return str(value)

    # ── Subclass hooks ──

    def build_system_prompt(
        self,
        relevant_skills: list[str],
        output_mode: str = "html",
        *,
        client_id: str | None = None,
    ) -> str:
        """Build the system prompt from skill files.

        Every agent has its own ``prompt.py`` with ``build_system_prompt()``.
        Override this method to call the agent-specific version.
        """
        raise NotImplementedError

    def detect_relevant_skills(self, request: Any) -> list[str]:  # noqa: ARG002
        """Detect which L3 skill files to load for this request.

        Override with agent-specific keyword detection.
        """
        return []

    def _build_user_message(self, request: Any) -> str:
        """Build the user message from the request.

        MUST be overridden by every subclass.
        """
        raise NotImplementedError

    # ── Pipeline hooks (override when behaviour differs) ──

    def _post_process(self, raw_content: str) -> str:
        """Post-process raw LLM output into clean HTML.

        Default: extract_html + sanitize_html_xss.
        Override for non-HTML agents (e.g., content → extract_content).
        """
        html = extract_html(raw_content)  # raises ValueError if non-HTML
        return sanitize_html_xss(html, profile=self.sanitization_profile)

    async def _run_qa(self, html: str) -> tuple[list[QACheckResult], bool]:
        """Run QA checks on the output.

        Override for agents that need custom QA ordering (e.g., dark_mode)
        or QA on input rather than output (e.g., code_reviewer).
        """
        qa_results: list[QACheckResult] = []
        for check in ALL_CHECKS:
            check_result = await check.run(html)
            qa_results.append(check_result)
        qa_passed = all(r.passed for r in qa_results)
        return qa_results, qa_passed

    def _build_response(
        self,
        *,
        request: Any,
        html: str,
        qa_results: list[QACheckResult] | None,
        qa_passed: bool | None,
        model_id: str,
        confidence: float | None,
        skills_loaded: list[str],
        raw_content: str,
    ) -> Any:
        """Construct the final response object.

        MUST be overridden — each agent has its own response schema.
        The ``request`` is passed through so agents can include request
        fields in the response (e.g., personalisation.platform).
        """
        raise NotImplementedError

    def _get_model_tier(self, request: Any) -> TaskTier:  # noqa: ARG002
        """Return the model tier for this request.

        Override to vary tier per-request (e.g., content agent uses
        different tiers per operation) without mutating instance state.
        """
        return self.model_tier

    def _should_run_qa(self, request: BaseAgentRequest) -> bool:
        """Whether to run QA checks for this request.

        Override to suppress QA in the base pipeline (e.g., code_reviewer
        runs QA on input HTML, not output). Like ``output_mode``, ``run_qa``
        is agent-specific so we still read it dynamically.
        """
        value = getattr(request, "run_qa", self.run_qa_default)
        return bool(value)

    # ── Multimodal helpers ──

    @staticmethod
    def _text_block(text: str) -> TextBlock:
        """Create a TextBlock (convenience for subclasses)."""
        from app.ai.multimodal import TextBlock

        return TextBlock(text=text)

    @staticmethod
    def _image_block(data: bytes, media_type: str = "image/png") -> ImageBlock:
        """Create a validated ImageBlock (convenience for subclasses)."""
        from app.ai.multimodal import ImageBlock, validate_content_block

        block = ImageBlock(data=data, media_type=media_type, source="base64")
        validate_content_block(block)
        return block

    def _build_multimodal_messages(
        self,
        *,
        system_prompt: str,
        user_text: str,
        context_blocks: list[ContentBlock] | None = None,
    ) -> list[Message]:
        """Build message list with optional multimodal content blocks.

        When context_blocks is provided, the user message content is a list
        of ContentBlock (text + images/audio). Otherwise, falls back to
        plain string content for backward compatibility.
        """
        from app.ai.multimodal import TextBlock, validate_content_blocks

        sanitized_text = sanitize_prompt(user_text)

        if context_blocks:
            validate_content_blocks(context_blocks)
            blocks: list[ContentBlock] = [TextBlock(text=sanitized_text)]
            blocks.extend(context_blocks)
            user_content: str | list[ContentBlock] = blocks
        else:
            user_content = sanitized_text

        return [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_content),
        ]

    # ── Shared pipeline ──

    async def _process_structured(self, request: Any) -> Any:
        """New pipeline: LLM -> structured JSON -> deterministic assembly.

        Override in subclass when implementing structured mode.
        """
        raise NotImplementedError(f"{self.agent_name} does not support structured output mode")

    def _scan_request(self, request: Any) -> Any:
        """Pre-LLM defense: scan every user-input field for prompt injection.

        - Mode "block" raises ``PromptInjectionError`` (422) before any work.
        - Mode "strip" returns a request whose user-input fields have flagged
          spans removed (via ``_apply_sanitized_input``) so the structured
          pipeline reads the cleaned values.
        - Mode "warn" logs but leaves the request untouched.

        Runs once per request — covers both ``html`` and ``structured``
        output modes because it executes upstream of the mode dispatch.
        Iterates every entry in ``_user_input_fields`` so multi-field agents
        (e.g. Personalisation: html + requirements) get full coverage.
        """
        settings = get_settings()
        if not settings.security.prompt_guard_enabled:
            return request
        if not self._user_input_fields:
            return request

        sanitized_updates: dict[str, str] = {}
        for field in self._user_input_fields:
            raw = getattr(request, field, "")
            if not isinstance(raw, str) or not raw:
                continue
            scan = scan_for_injection(raw, mode=settings.security.prompt_guard_mode)
            # block mode: scan_for_injection already raised PromptInjectionError
            if scan.sanitized is not None and scan.sanitized != raw:
                sanitized_updates[field] = scan.sanitized

        if sanitized_updates:
            request = self._apply_sanitized_input(request, sanitized_updates)
        return request

    def _apply_sanitized_input(self, request: Any, updates: dict[str, str]) -> Any:
        """Write sanitized values back to the request's user-input fields.

        Uses Pydantic ``model_copy(update=...)`` — no re-validation, so
        length constraints on the original fields don't reject strip-mode
        output. Override only when an agent needs custom merge semantics.
        """
        if not updates:
            return request
        return request.model_copy(update=updates)

    def _wrap_user_message(self, raw: str) -> str:
        """Wrap the message in the ``<USER_INPUT>`` delimiter.

        The wrapper tag is the structural boundary that agent system
        prompts reference: LLMs are told to treat anything inside as
        untrusted data, never instructions. The injection scan is
        already done upstream in ``_scan_request``.
        """
        return f"<USER_INPUT agent={self.agent_name!r}>\n{raw}\n</USER_INPUT>"

    def _enforce_token_cap(self, messages: list[Message], model: str) -> int:
        """Return estimated input tokens; raise if input + response exceeds cap.

        ``settings.security.agent_max_total_tokens`` is the per-run hard
        ceiling. ``self.max_tokens`` is the LLM response cap. Sum must not
        exceed the configured ceiling — otherwise the call is short-circuited
        with 503 (defense-in-depth on top of provider context limits).
        """
        cap = get_settings().security.agent_max_total_tokens
        budget = TokenBudgetManager(model=model)
        estimate = budget.estimate_tokens(messages)
        projected = estimate.total_tokens + self.max_tokens
        if projected > cap:
            logger.warning(
                "ai.agent_token_cap_exceeded",
                agent=self.agent_name,
                model=model,
                input_tokens=estimate.total_tokens,
                response_cap=self.max_tokens,
                projected=projected,
                limit=cap,
            )
            raise ServiceUnavailableError(
                f"Agent '{self.agent_name}' exceeds token cap ({projected} > {cap})"
            )
        return estimate.total_tokens

    async def process(
        self,
        request: BaseAgentRequest,
        context_blocks: list[ContentBlock] | None = None,
    ) -> Any:
        """Execute the full agent pipeline (non-streaming).

        Wraps ``_process_impl`` with the per-run security envelope:
          1. Kill switch (``SECURITY__DISABLED_AGENTS``) → 503
          2. Wall-clock timeout (``SECURITY__AGENT_MAX_RUN_SECONDS``) → 503
          3. Audit log (``ai.agent_decision``) on every exit path
        """
        settings = get_settings()
        started_at = time.monotonic()

        telemetry: dict[str, Any] = {
            "agent": self.agent_name,
            "user_id": request.user_id,
            "blueprint_run_id": request.blueprint_run_id,
            "model": "",
            "prompt_version": request.prompt_version,
            "input_hash": "",
            "output_summary": "",
            "tokens_in": 0,
            "tokens_out": 0,
            "tool_calls_made": 0,
            "planning_steps": [],
        }

        # K_max — per-session tool-call cap (fresh per invocation → resets).
        counter = _ToolCallCounter(
            agent=self.agent_name,
            max_calls=settings.security.agent_max_tool_calls,
        )

        # G3 — Kill switch: short-circuit before any work.
        if self.agent_name in settings.security.disabled_agents:
            logger.warning("ai.agent_disabled", agent=self.agent_name)
            await self._revoke_credentials_on_kill(reason="kill_switch")
            log_agent_decision(**telemetry, duration_ms=0, decision="disabled")
            raise ServiceUnavailableError(f"Agent '{self.agent_name}' is disabled")

        decision = "ok"
        try:
            return await asyncio.wait_for(
                self._process_impl(request, context_blocks, telemetry, counter),
                timeout=settings.security.agent_max_run_seconds,
            )
        except TimeoutError as exc:
            decision = "timeout"
            logger.warning(
                "ai.agent_timeout",
                agent=self.agent_name,
                limit_s=settings.security.agent_max_run_seconds,
            )
            raise ServiceUnavailableError(
                f"Agent '{self.agent_name}' timed out after "
                f"{settings.security.agent_max_run_seconds}s"
            ) from exc
        except ToolCapExceededError:
            decision = "cap_exceeded"
            raise
        except Exception:
            if decision == "ok":
                decision = "error"
            raise
        finally:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            telemetry["tool_calls_made"] = counter.count
            telemetry["planning_steps"] = counter.planning_steps
            log_agent_decision(**telemetry, duration_ms=duration_ms, decision=decision)

    async def _process_impl(
        self,
        request: BaseAgentRequest,
        context_blocks: list[ContentBlock] | None,
        telemetry: dict[str, Any],
        counter: _ToolCallCounter,
    ) -> Any:
        """Inner pipeline (no security envelope).

        Routes to structured pipeline when output_mode="structured" and supported.

        Steps:
        1. Resolve model from tier
        2. Detect skills + build system prompt
        3. Build user message → injection scan + delimiter wrap
        4. Token cap check
        5. Call LLM
        6. Post-process output
        7. Extract confidence
        8. Run QA checks (if enabled)
        9. Build and return response

        ``telemetry`` is mutated in-place so the outer ``process`` wrapper can
        emit a single ``ai.agent_decision`` audit line in its finally block.
        """
        # G1 — injection scan runs before output_mode dispatch so the
        # structured-output path is also guarded. Block mode raises here;
        # strip mode returns a request with the user-input field cleaned.
        request = self._scan_request(request)
        output_mode = self._get_output_mode(request)
        if output_mode == "structured" and self._output_mode_supported:
            counter.record_planning_step(f"{self.agent_name}:structured")
            return await self._process_structured(request)

        settings = get_settings()
        provider_name = settings.ai.provider
        base_tier = self._get_model_tier(request)
        model = resolve_model(base_tier)
        model_id = f"{provider_name}:{model}"
        telemetry["model"] = model_id

        # Progressive disclosure — load only relevant skill files
        relevant_skills = self._detect_skills_from_request(request)
        system_prompt = self.build_system_prompt(
            relevant_skills, output_mode=output_mode, client_id=request.client_id
        )
        system_prompt += CONFIDENCE_INSTRUCTION

        # G2 — wrap in <USER_INPUT> delimiter. Scan already ran in _scan_request.
        raw_user_message = self._build_user_message(request)
        telemetry["input_hash"] = hash_input(raw_user_message)
        user_message = self._wrap_user_message(raw_user_message)

        # Build messages (multimodal-aware)
        messages = self._build_multimodal_messages(
            system_prompt=system_prompt,
            user_text=user_message,
            context_blocks=context_blocks,
        )

        # G4 — token cap (defense-in-depth on top of provider context).
        telemetry["tokens_in"] = self._enforce_token_cap(messages, model)

        logger.info(
            f"agents.{self.agent_name}.process_started",
            provider=provider_name,
            model=model,
            skills_loaded=relevant_skills,
        )

        # Call LLM (with fallback chain if configured)
        registry = get_registry()
        chain = get_fallback_chain(base_tier)

        try:
            if chain and chain.has_fallbacks:
                result = await call_with_fallback(
                    chain, registry, messages, max_tokens=self.max_tokens
                )
            else:
                provider = registry.get_llm(provider_name)
                result = await provider.complete(
                    messages, model_override=model, max_tokens=self.max_tokens
                )
        except Exception as e:
            logger.error(
                f"agents.{self.agent_name}.process_failed",
                error=str(e),
                error_type=type(e).__name__,
                provider=provider_name,
            )
            if isinstance(e, AIExecutionError):
                raise
            raise AIExecutionError(f"{self.agent_name} processing failed") from e

        # Post-process output
        raw_content = validate_output(result.content)
        confidence = extract_confidence(raw_content)
        html = self._post_process(raw_content)

        usage = result.usage or {}
        telemetry["tokens_out"] = int(
            usage.get("output_tokens") or usage.get("completion_tokens") or 0
        )
        telemetry["output_summary"] = raw_content[:200]

        logger.info(
            f"agents.{self.agent_name}.process_completed",
            model=model_id,
            html_length=len(html),
            confidence=confidence,
            usage=result.usage,
        )

        # CRAG validation loop (if mixin present and enabled)
        from app.ai.agents.validation_loop import CRAGMixin

        if isinstance(self, CRAGMixin) and settings.knowledge.crag_enabled:
            html, crag_corrections = await self._crag_validate_and_correct(
                html, system_prompt, model
            )
            if crag_corrections:
                logger.info(
                    f"agents.{self.agent_name}.crag_accepted",
                    corrections=crag_corrections,
                )

        # Optional QA checks
        qa_results: list[QACheckResult] | None = None
        qa_passed: bool | None = None
        should_run_qa = self._should_run_qa(request)

        if should_run_qa:
            qa_results_list, qa_passed = await self._run_qa(html)
            qa_results = qa_results_list

            logger.info(
                f"agents.{self.agent_name}.qa_completed",
                qa_passed=qa_passed,
                checks_passed=sum(1 for r in qa_results if r.passed),
                checks_total=len(qa_results),
            )

        return self._build_response(
            request=request,
            html=html,
            qa_results=qa_results,
            qa_passed=qa_passed,
            model_id=model_id,
            confidence=confidence,
            skills_loaded=relevant_skills,
            raw_content=raw_content,
        )

    async def stream_process(
        self,
        request: BaseAgentRequest,
        context_blocks: list[ContentBlock] | None = None,
    ) -> AsyncIterator[str]:
        """Stream agent output as SSE-formatted chunks.

        QA is skipped in streaming mode (requires complete output).
        Streaming honours the kill switch + injection scan + delimiter wrap;
        wall-clock timeout is delegated to ``ai.stream_timeout_seconds``.
        """
        settings = get_settings()

        # G3 — Kill switch
        if self.agent_name in settings.security.disabled_agents:
            logger.warning("ai.agent_disabled", agent=self.agent_name, mode="stream")
            await self._revoke_credentials_on_kill(reason="kill_switch")
            raise ServiceUnavailableError(f"Agent '{self.agent_name}' is disabled")

        # G1 — injection scan (block raises; strip returns a sanitized request)
        request = self._scan_request(request)

        provider_name = settings.ai.provider
        model = resolve_model(self._get_model_tier(request))
        model_id = f"{provider_name}:{model}"
        response_id = f"{self.stream_prefix}-{uuid.uuid4().hex[:12]}"

        relevant_skills = self._detect_skills_from_request(request)
        output_mode = self._get_output_mode(request)
        system_prompt = self.build_system_prompt(
            relevant_skills, output_mode=output_mode, client_id=request.client_id
        )
        system_prompt += CONFIDENCE_INSTRUCTION

        # G2 — wrap user message before LLM (scan already ran above)
        user_message = self._wrap_user_message(self._build_user_message(request))
        messages = self._build_multimodal_messages(
            system_prompt=system_prompt,
            user_text=user_message,
            context_blocks=context_blocks,
        )

        # G4 — token cap (input pre-check; streaming has no per-call response cap)
        self._enforce_token_cap(messages, model)

        logger.info(
            f"agents.{self.agent_name}.stream_started",
            provider=provider_name,
            model=model,
        )

        registry = get_registry()
        provider = registry.get_llm(provider_name)

        try:
            async for chunk in provider.stream(
                messages, model_override=model, max_tokens=self.max_tokens
            ):  # type: ignore[attr-defined]
                sse_data = {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_id,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": chunk},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(sse_data)}\n\n"

        except Exception as e:
            logger.error(
                f"agents.{self.agent_name}.stream_failed",
                error=str(e),
                error_type=type(e).__name__,
                provider=provider_name,
            )
            if isinstance(e, AIExecutionError):
                raise
            raise AIExecutionError(f"{self.agent_name} streaming failed") from e

        yield "data: [DONE]\n\n"

        logger.info(
            f"agents.{self.agent_name}.stream_completed",
            response_id=response_id,
            provider=provider_name,
        )

    # ── Handoff helpers ──

    def to_handoff(
        self,
        *,
        html: str,
        confidence: float | None = None,
        qa_passed: bool | None = None,
        decisions: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
        component_refs: tuple[str, ...] = (),
    ) -> AgentHandoff:
        """Build a standardised AgentHandoff from agent output.

        Blueprint nodes can call this instead of manually constructing
        AgentHandoff, ensuring consistent field population across all agents.
        """
        status = HandoffStatus.WARNING if qa_passed is False else HandoffStatus.OK

        return AgentHandoff(
            status=status,
            agent_name=self.agent_name,
            artifact=html,
            decisions=decisions,
            warnings=warnings,
            component_refs=component_refs,
            confidence=confidence,
        )

    # ── Internal helpers ──

    def _detect_skills_from_request(self, request: Any) -> list[str]:
        """Adapter that calls detect_relevant_skills with the right args.

        Override if your skill detection signature differs from the default.
        """
        return self.detect_relevant_skills(request)

    async def _revoke_credentials_on_kill(self, *, reason: str) -> None:
        """Revoke this agent's credential leases (51.1).

        Called from the G3 kill-switch paths in ``process`` and ``stream_process``
        so an agent disabled mid-flight cannot obtain a fresh credential lease
        even if its in-process check is bypassed. Failures are swallowed —
        revocation is best-effort and must never mask the original 503.
        """
        if not self.agent_name:
            return
        try:
            from app.core.credentials import revoke_for_agent

            await revoke_for_agent(self.agent_name, reason)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "ai.agent_revocation_failed",
                agent=self.agent_name,
                reason=reason,
                error=str(exc),
            )
