# Plan: Tech-Debt 13 — LLM Adapter Base Class (F026)

## Context

`TECH_DEBT_AUDIT.md:68` (F026, severity High, size M) flags ~150 LOC of duplication between `app/ai/adapters/anthropic.py:105-200` and `app/ai/adapters/openai_compat.py:115-210`. The duplicates are five shared infrastructure helpers (token budget, cost governance, structured-output extraction, vision capability, message-payload skeleton). The fix prescribed in the audit: extract `BaseLLMProvider(ABC)` at `app/ai/adapters/base.py`; subclasses override only `complete` / `stream` / `_format_payload`.

This is a pure refactor — no behavior change, no new endpoints, no migrations. Surface stays identical because the registry, `Settings.ai`, and the credential pool wiring are untouched, and concrete subclass methods keep their existing names so the test surfaces (which reach into `_apply_token_budget`, `_check_cost_budget`, `_report_cost` as instance methods — see `app/ai/tests/test_phase22_integration.py:298,334,490,854` and `test_cost_governor.py:279,295,319`) keep passing without edits.

**Branch:** `refactor/tech-debt-13-llm-adapter-base`

## Current Duplication (byte-for-byte audit)

Verified by reading both files end-to-end:

| Helper | Anthropic LOC | OpenAI LOC | Identical? |
|---|---|---|---|
| `_apply_token_budget` | `anthropic.py:105-120` | `openai_compat.py:115-130` | ✅ identical |
| `_check_cost_budget` | `anthropic.py:122-134` | `openai_compat.py:132-144` | ✅ identical |
| `_report_cost` | `anthropic.py:136-155` | `openai_compat.py:146-165` | ✅ identical |
| `_extract_structured_output` (`@staticmethod`) | `anthropic.py:157-169` | `openai_compat.py:167-179` | ✅ identical |
| `_check_vision_capability` | `anthropic.py:171-182` | `openai_compat.py:181-192` | ✅ identical (one comment word differs) |
| `_build_messages_payload` | `anthropic.py:184-226` | `openai_compat.py:194-216` | ⚠️ structurally similar, **different return shape** — Anthropic returns `(system_parts, chat_messages, has_cache_control)`, OpenAI returns `list[dict]`. Keep per-subclass; rename to `_format_payload`. |
| `_serialize_content_blocks` (`@staticmethod`) | `anthropic.py:458-519` | `openai_compat.py:453-505` | ❌ provider-specific formats — keep per-subclass |
| `complete` / `stream` / `close` / `__init__` | — | — | ❌ provider-specific — keep per-subclass |

Net: ~75 LOC of pure duplicates per file (5 helpers × ~15 LOC avg) plus ~50 LOC of near-duplicated payload-builder skeleton. Extracting the 5 pure duplicates yields ~150 LOC reduction (75 saved in each file, ~120-130 LOC added in `base.py`).

## Contract Constraints (do not violate)

- **`LLMProvider` Protocol** (`app/ai/protocols.py:106-140`) defines `complete()` and `stream()` only. `runtime_checkable`. Concrete subclasses satisfy it via duck-typing; the ABC does **not** need to inherit from it (and probably shouldn't, to avoid metaclass conflicts between `ABC` and `_ProtocolMeta`).
- **Registry consumers** (`app/ai/registry.py:213-230`) instantiate via `registry.register_llm("openai", OpenAICompatProvider)` etc. The five `# type: ignore[arg-type]` comments at `registry.py:221-230` document the Protocol/concrete-class typing gap that already exists. The base-class refactor does not require removing them; leaving them as-is keeps this PR a pure refactor. (Optional cleanup noted below.)
- **Test surfaces** patch instance methods:
  - `provider._check_cost_budget = AsyncMock()` (`test_phase22_integration.py:335,481`)
  - `provider._report_cost = tracked_report` (`test_phase22_integration.py:334,490`)
  - `provider._apply_token_budget = tracked_apply` (`test_phase22_integration.py:854`)
  - `await provider._check_cost_budget()` (`test_cost_governor.py:279,295`)
  - `await provider._report_cost(...)` (`test_cost_governor.py:319`)

  These all work because Python MRO resolves instance attribute → bound method on subclass → bound method on base. The base-class extraction is transparent to these test sites; **no edits needed for the helper extraction**.

- **One exception**: `test_multimodal_adapters.py` reaches into the renamed payload-builder directly at three sites (lines 383, 409, 449 — both OpenAI's single-list return and Anthropic's 3-tuple return). These three callsites are renamed `_build_messages_payload` → `_format_payload` **atomically with the source rename** (see "Files to Create/Modify"). No assertion changes; pure identifier swap.
- **`self._model` invariant**: `_apply_token_budget` reads `kwargs.get("model_override", self._model)`. The base class will document that subclasses must set `self._model` in `__init__`. Both already do (`anthropic.py:57`, `openai_compat.py:68`).
- **Credential pool wiring** (`anthropic.py:60-92`, `openai_compat.py:71-96`) stays in subclasses — pool naming differs (Anthropic uses hardcoded `"anthropic"`; OpenAI uses `settings.ai.provider` value), and client construction differs (`anthropic.AsyncAnthropic` vs `httpx.AsyncClient`).

## Files to Create/Modify

- **Create** `app/ai/adapters/base.py` — `BaseLLMProvider(ABC)` with five shared helpers + three abstract methods. ~130 LOC including imports and docstrings.
- **Modify** `app/ai/adapters/anthropic.py` — make class inherit from `BaseLLMProvider`; delete the five duplicated helpers; rename `_build_messages_payload` → `_format_payload`; drop now-unused imports (`StructuredOutputBlock` if no longer referenced after extraction — verify by grep). Expected ~75 LOC reduction.
- **Modify** `app/ai/adapters/openai_compat.py` — same shape. Expected ~75 LOC reduction.
- **Modify** `app/ai/tests/test_multimodal_adapters.py` — three rename-only edits (lines 383, 409, 449): `provider._build_messages_payload(...)` → `provider._format_payload(...)`. No assertions or test-shape changes. Edit **atomically** with the source rename in Step 2/3 so the gate never sees a partial state.
- **No changes** to `app/ai/adapters/__init__.py` (currently empty; keep it empty — no public export of `BaseLLMProvider` needed since registry imports concrete classes directly).
- **No changes** to `app/ai/registry.py` — type ignores stay (separate concern; tracked as optional cleanup).
- **No assertion or test-shape changes** to any other test file. Patches like `provider._check_cost_budget = AsyncMock()` (`test_phase22_integration.py:335,481`), `provider._report_cost = tracked_report` (`:334,490`), `provider._apply_token_budget = tracked_apply` (`:854`), and `test_cost_governor.py:279,295,319` resolve through MRO to the base class without edit.

## Implementation Steps

### Step 1 — Create `app/ai/adapters/base.py`

```python
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
"""Shared infrastructure for LLM provider adapters.

Concrete adapters (AnthropicProvider, OpenAICompatProvider) inherit from
BaseLLMProvider and implement complete()/stream()/_format_payload()/close().
The base provides token budget trimming, cost governance, structured-output
extraction, and vision capability lookup — features that are byte-for-byte
identical between providers.

Subclasses must set `self._model: str` in __init__ (used by _apply_token_budget
as the fallback when kwargs lacks model_override).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.ai.multimodal import StructuredOutputBlock
from app.ai.protocols import CompletionResponse, Message
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class BaseLLMProvider(ABC):
    """Abstract base for LLM provider adapters.

    Provides shared utilities for token budget enforcement, cost governance,
    structured-output payload extraction, and vision capability lookup.
    Concrete subclasses implement the provider-specific complete()/stream()/
    _format_payload()/close() surface.
    """

    _model: str  # subclass __init__ must set this

    # ── Abstract surface ──

    @abstractmethod
    async def complete(
        self, messages: list[Message], **kwargs: object
    ) -> CompletionResponse:
        """Send a chat completion request. Subclass-specific."""
        ...

    @abstractmethod
    async def stream(
        self, messages: list[Message], **kwargs: object
    ) -> AsyncIterator[str]:
        """Stream completion tokens as they are generated. Subclass-specific."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release underlying HTTP/SDK clients. Subclass-specific."""
        ...

    # ── Shared helpers (moved verbatim from anthropic.py / openai_compat.py) ──

    def _apply_token_budget(
        self, messages: list[Message], kwargs: dict[str, object]
    ) -> list[Message]:
        """Trim messages to fit token budget if enabled."""
        settings = get_settings()
        if not settings.ai.token_budget_enabled:
            return messages
        from app.ai.token_budget import TokenBudgetManager

        model = str(kwargs.get("model_override", self._model))
        budget_mgr = TokenBudgetManager(
            model=model,
            reserve_tokens=settings.ai.token_budget_reserve,
            max_context_tokens=settings.ai.token_budget_max,
        )
        return budget_mgr.trim_to_budget(messages)

    async def _check_cost_budget(self) -> None:
        """Check budget before making an API call. Raises BudgetExceededError if over budget."""
        settings = get_settings()
        if not settings.ai.cost_governor_enabled:
            return
        from app.ai.cost_governor import BudgetStatus, get_cost_governor

        governor = get_cost_governor()
        status = await governor.check_budget()
        if status == BudgetStatus.EXCEEDED:
            from app.ai.exceptions import BudgetExceededError

            raise BudgetExceededError("Monthly AI budget exceeded")

    async def _report_cost(
        self, model: str, usage: dict[str, int] | None, kwargs: dict[str, object]
    ) -> None:
        """Report token usage to cost governor if enabled. Fire-and-forget."""
        settings = get_settings()
        if not settings.ai.cost_governor_enabled or usage is None:
            return
        try:
            from app.ai.cost_governor import get_cost_governor

            governor = get_cost_governor()
            await governor.record(
                model=model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                agent=str(kwargs.get("agent_name", "")),
                project_id=str(kwargs.get("project_id", "")),
            )
        except Exception:
            logger.debug("cost_governor.report_failed", model=model)

    @staticmethod
    def _extract_structured_output(
        messages: list[Message],
    ) -> StructuredOutputBlock | None:
        """Extract StructuredOutputBlock from the last message, if present."""
        if not messages:
            return None
        last = messages[-1]
        if isinstance(last.content, list):
            for block in last.content:
                if isinstance(block, StructuredOutputBlock):
                    return block
        return None

    def _check_vision_capability(self, model: str) -> bool:
        """Check if the model supports vision via capability registry."""
        try:
            from app.ai.capability_registry import (
                ModelCapability,
                get_capability_registry,
            )

            registry = get_capability_registry()
            spec = registry.get(model)
            if spec is None:
                return True  # Unknown model — assume capable
            return ModelCapability.VISION in spec.capabilities
        except Exception:
            return True  # Registry unavailable — don't block
```

**Notes on this file:**
- The abstract `stream()` signature **mirrors** the existing `LLMProvider` Protocol form at `app/ai/protocols.py:130` (`async def stream(...) -> AsyncIterator[str]: ...`). That exact shape already passes `make check-full` today, so the ABC declared identically should pass pyright-strict's Liskov check against concrete `async def stream(...) -> AsyncIterator[str]: yield ...` implementations. (Concrete async-generator overrides of `async def` declarations with body `...` is the standard Python pattern.)
- The shared helpers reference `self._model` only inside `_apply_token_budget`. All other helpers are model-agnostic. Both subclasses set `self._model` in `__init__` (`anthropic.py:57`, `openai_compat.py:68`).
- `pyright` pragma at top mirrors the one in `anthropic.py:1` for the `Any`-leaning LLM payload surface.
- Type-check sanity check before execute: `pyright --strict app/ai/adapters/base.py` should be clean. If it flags the `stream()` signature, fall back to the literal Protocol-style declaration (no body modification needed — same shape).

### Step 2 — Refactor `app/ai/adapters/anthropic.py`

Apply these changes (use `Edit` for each — no full rewrite):

1. **Add import** (with the existing `from app.ai...` imports):
   ```python
   from app.ai.adapters.base import BaseLLMProvider
   ```

2. **Change class declaration** (line 34):
   ```diff
   - class AnthropicProvider:
   + class AnthropicProvider(BaseLLMProvider):
   ```

3. **Delete** the duplicated helper bodies (lines 105-182 in the current file):
   - `_apply_token_budget` (105-120)
   - `_check_cost_budget` (122-134)
   - `_report_cost` (136-155)
   - `_extract_structured_output` (157-169)
   - `_check_vision_capability` (171-182)

4. **Rename `_build_messages_payload` → `_format_payload`** (line 184) — pure rename; the body stays. Update the single callsite at line 252 (`complete`) and line 399 (`stream`). The Anthropic version returns the 3-tuple `(system_parts, chat_messages, has_cache_control)`; that signature is preserved.

5. **Verify no unused imports remain.** After step 3 deletes, audit `anthropic.py`'s top imports:
   - `from app.ai.multimodal import (...)` — `AudioBlock`, `ContentBlock`, `ImageBlock`, `StructuredOutputBlock`, `TextBlock`, `ToolResultBlock`, `normalize_content`, `validate_content_blocks` — all still used in `_format_payload` / `_serialize_content_blocks` / `complete`. Keep.
   - `from app.ai.exceptions import AIConfigurationError, AIExecutionError` — still used. Keep.
   - `from app.ai.protocols import CompletionResponse, Message` — still used. Keep.
   - `from app.core.config import get_settings` — still used in `__init__`. Keep.
   - `from app.core.credentials import ...` — still used. Keep.
   - `from app.core.logging import get_logger` — still used. Keep.
   - `from typing import Any, cast` — still used. Keep.
   - `import contextlib` — still used in `close`. Keep.

6. **`close()` and `stream()` and `complete()` and `__init__`** stay as-is (provider-specific bodies; just method-resolution targets for the ABC).

7. **`_serialize_content_blocks` (`@staticmethod`)** stays as-is — Anthropic-specific format.

Expected new line count: `anthropic.py` drops from 533 → ~458.

### Step 3 — Refactor `app/ai/adapters/openai_compat.py`

Mirror of Step 2:

1. **Add import**:
   ```python
   from app.ai.adapters.base import BaseLLMProvider
   ```

2. **Change class declaration** (line 47):
   ```diff
   - class OpenAICompatProvider:
   + class OpenAICompatProvider(BaseLLMProvider):
   ```

3. **Delete** duplicated helpers (lines 115-192):
   - `_apply_token_budget` (115-130)
   - `_check_cost_budget` (132-144)
   - `_report_cost` (146-165)
   - `_extract_structured_output` (167-179)
   - `_check_vision_capability` (181-192)

4. **Rename `_build_messages_payload` → `_format_payload`** (line 194). Body stays. Update callsites at line 242 (`complete`) and line 384 (`stream`).

5. **Verify imports** — same audit as Step 2.5. `StructuredOutputBlock` is still used in `_serialize_content_blocks`'s `isinstance` branch (line 503) → keep.

6. **`__init__`, `complete`, `stream`, `close`, `_serialize_content_blocks`** stay as-is.

Expected new line count: `openai_compat.py` drops from 514 → ~439.

### Step 4 — Run the gate

```bash
# Per-target adapter tests first (fastest signal)
pytest app/ai/tests/test_multimodal_adapters.py \
       app/ai/tests/test_phase22_integration.py \
       app/ai/tests/test_key_rotation.py \
       app/ai/tests/test_cost_governor.py \
       -x -q

# Full backend gate
make check-full
```

Expected result: all pre-existing tests pass unchanged. No new tests required for a pure refactor — the existing test surface already exercises every extracted helper (cost governor tests reach into `_check_cost_budget` and `_report_cost`; phase22 tests cover `_apply_token_budget`).

### Step 5 (optional) — Registry type-ignore cleanup

`app/ai/registry.py:221-230` has five `# type: ignore[arg-type]` markers because the type signature on `register_llm` accepts `type[LLMProvider]` (a Protocol type) and pyright doesn't recognize the concrete classes as compatible despite duck-typing satisfaction.

After this refactor, the concrete classes share a real base class. Two cleanup options — **do NOT do these in the same PR** to keep the diff scoped:

- **Option A** (separate follow-up plan): change `register_llm` to accept `type[BaseLLMProvider] | type[LLMProvider]` (or simply `type[BaseLLMProvider]` if all built-ins go through the base).
- **Option B** (separate follow-up plan): add `BaseLLMProvider` to the `LLMProvider` Protocol's `assert_type` chain via a runtime check.

Both are out-of-scope for tech-debt-13. Leave the type ignores in place.

## Security Checklist

This refactor adds **no new endpoints**, modifies **no auth flow**, touches **no user-supplied input handling**, and changes **no database queries**.

Per the per-feature security scoping rules:

- **Auth + rate limiting** — N/A (no endpoints added/modified)
- **Input validation** — N/A (no new request schemas)
- **Error response leakage** — Existing error messages preserved verbatim. `AIExecutionError`/`AIConfigurationError` raised exactly as before.
- **Credential exposure** — Credential pool wiring is **not** moved into the base; stays in each subclass `__init__` to preserve current behavior. No new code path reads keys.
- **Logging PII** — No new log statements. Existing `logger.info("ai.provider.completion_completed", ...)` etc. stay in subclasses.
- **Prompt injection** — N/A (provider-layer; injection guard runs upstream in `app/ai/security/prompt_guard.py`).
- **SQL injection / SSRF / SSRF-like** — N/A.
- **Semgrep** — Refactor only; no new patterns. If Semgrep flags inheritance changes it's a false positive (see `.claude/rules/security.md` decision tree).

## Verification

- [ ] `make check-full` passes clean (ruff 26-rule lint, mypy strict, pyright strict, pytest, security-check, golden-conformance, flag-audit, migration-lint)
- [ ] `pytest app/ai/tests/test_phase22_integration.py app/ai/tests/test_multimodal_adapters.py app/ai/tests/test_key_rotation.py app/ai/tests/test_cost_governor.py -v` — all pass with **zero test-file edits**
- [ ] `git diff --stat` shows exactly three files changed: `app/ai/adapters/anthropic.py` (-~75 LOC), `app/ai/adapters/openai_compat.py` (-~75 LOC), `app/ai/adapters/base.py` (+~130 LOC). Net ≈ -20 to -50 LOC depending on docstring expansion in base.py.
- [ ] `grep -nE "_apply_token_budget|_check_cost_budget|_report_cost|_extract_structured_output|_check_vision_capability" app/ai/adapters/anthropic.py app/ai/adapters/openai_compat.py` — returns **only** rename-of-callsites and `super()` references (no duplicate `def`).
- [ ] Adapter integration tests in `test_phase22_integration.py` (lines 416-465 — `test_cost_governor_cross_provider`) cover both providers' shared infrastructure. Verify their assertions still hold.
- [ ] Registry still resolves both providers: `python -c "from app.ai.registry import get_registry; r = get_registry(); print(type(r.get_llm('anthropic')).__mro__)"` shows `[..., BaseLLMProvider, ABC, object]`.
- [ ] **TECH_DEBT_AUDIT.md update — flip in this same PR.** Edit the F026 row at `TECH_DEBT_AUDIT.md:68` to read: **"RESOLVED (Plan 13). `BaseLLMProvider(ABC)` at `app/ai/adapters/base.py` centralizes token-budget, cost-governor, structured-output extraction, and vision capability checks. Subclasses override only `complete`/`stream`/`_format_payload`/`close`/`__init__`."** Per `project_f030_audit_pending.md`, F030's RESOLVED note was deferred to "the next tech-debt PR" — **this is that PR**, so include the F030 row flip here as well (`TECH_DEBT_AUDIT.md:72`) to clear the carry-forward. If F030's exact RESOLVED phrasing is unsettled, batch it to the next tech-debt PR instead and update `project_f030_audit_pending.md` accordingly — but never leave both deferrals open.

## Out of Scope (do not do in this PR)

- Removing `# type: ignore[arg-type]` from `app/ai/registry.py` (Step 5 — separate plan).
- Splitting `_serialize_content_blocks` into a base helper (signatures and target formats differ enough that this would introduce more abstraction tax than it removes).
- Pushing `complete()`/`stream()` into a template method that calls `_invoke()` + `_parse_response()` hooks. The user-stated direction is "subclasses override only `complete`/`stream`/`_format_payload`" — keep the body explicit.
- Adding a `__init__` template (e.g., setting `self._model` in base). The provider-specific client setup is divergent enough (Anthropic uses pool-or-direct branching with cache; OpenAI uses a single httpx client with conditional headers) that a shared `__init__` would either be empty or trap a footgun.
- Unifying credential-pool naming convention (`"anthropic"` literal vs `settings.ai.provider` value). Tracked separately under Phase 46.2 follow-ups.

## Risk & Rollback

- **Risk: low.** Pure refactor. Pre-existing tests already exercise the extracted helpers. No public surface change. No runtime behavior change.
- **Rollback:** `git revert` the single commit. The three-file change is self-contained.
- **Most likely failure mode:** A `from app.ai.adapters.base import BaseLLMProvider` circular import if `base.py` accidentally imports a module that imports from the adapters. **Mitigation:** `base.py` imports only from `app.ai.multimodal`, `app.ai.protocols`, and `app.core.logging` (and `app.core.config.Settings` via TYPE_CHECKING) — all leaf modules. The deferred imports inside helper bodies (e.g., `from app.ai.token_budget import TokenBudgetManager`) stay deferred to preserve the existing lazy-init pattern.

## Execution Notes (added 2026-05-11)

The first gate run after extraction failed: `TestTokenBudgetAdapterIntegration::test_openai_complete_trims_messages_before_send` got 10 messages where it expected `<10` (trimmed). Root cause: **24 test sites across `test_phase22_integration.py` (14), `test_key_rotation.py` (7), and `test_cost_governor.py` (3)** patch `app.ai.adapters.{anthropic,openai_compat}.get_settings` — the per-module symbol where the original helpers looked up `get_settings()`. After naive extraction those lookups moved to `app.ai.adapters.base.get_settings`, leaving the patches dangling.

**Pivot: hook method instead of bulk test edits.** Rather than edit 24 patch sites, `base.py` adds one abstract method `_get_settings(self) -> Settings`. Helpers (`_apply_token_budget`, `_check_cost_budget`, `_report_cost`) call `self._get_settings()`. Each concrete subclass overrides it with a 3-line stub:

```python
def _get_settings(self) -> Any:  # noqa: ANN401
    return get_settings()  # uses the module-local (and test-patched) symbol
```

This is a dependency-inversion seam: the base owns the policy (when to read settings); subclasses own the binding (which `get_settings` to consult). All 24 patches keep working unchanged — the patched per-module `get_settings` is reached via the subclass override.

**New contract requirement:** any future `BaseLLMProvider` subclass must implement `_get_settings`. Documented in `base.py`'s class docstring and module docstring. The hook is abstract (not concrete) so omitting it is a `TypeError: Can't instantiate abstract class` at construction time — fail-fast.

**Final shipped surface:**
- `base.py` 164 LOC (5 shared helpers + 4 abstract: `complete`/`stream`/`close`/`_get_settings`)
- `anthropic.py` 533 → 463 LOC (–70)
- `openai_compat.py` 514 → 444 LOC (–70)
- `test_multimodal_adapters.py` 3 callsite renames only (`_build_messages_payload` → `_format_payload`)
- `TECH_DEBT_AUDIT.md` F026 + F030 (carry-forward) flipped to RESOLVED in same PR

**Other gate notes:**
- `stream()` abstract is declared `def` (not `async def`) returning `AsyncIterator[str]` — this is the canonical pattern for declaring an async-generator method abstractly, and was needed because `async def stream(...) -> AsyncIterator[str]: ...` raised `reportIncompatibleMethodOverride` (pyright treats `async def ... -> X: ...` as `Coroutine[..., X]`, not `X`). The advisor pre-flagged this; the plan's "fallback note" was wrong-direction but the fix was easy.
- 36 `reportPrivateUsage` warnings in `test_multimodal_adapters.py` are **pre-existing** (verified by git stash + pyright on the pre-refactor tree) and unrelated to the refactor.
