# Plan: Tech-Debt 13b — Eval Runner Registry (F025)

## Context

`TECH_DEBT_AUDIT.md:67` (F025, severity High, size M) flags `app/ai/agents/evals/runner.py:548` (`run_agent`, 159 LOC) as a per-agent if-ladder that grows by one branch per new agent. Two symptoms: (a) adding a 10th agent requires editing a central function in three places (the if-ladder, the argparse choices list at `:713-723`, and the `agents` list at `:752-764`); (b) the nine per-agent case runners (`run_scaffolder_case` … `run_innovation_case`, lines 40-545) are each 50-60 LOC of near-identical boilerplate (service init → request build → time.monotonic → try/except → trace dict).

The fix prescribed in the audit: **registry + template**.
1. Replace the if-ladder with `dict[AgentName, AgentSpec]` keyed by a `Literal` agent name.
2. Extract a shared `_run_case` template that handles timing, error capture, and the common trace fields — leaving per-agent runners as thin adapters (~10-15 LOC each).

This is a pure refactor — no behavior change, no new endpoints, no schema changes. Trace JSONL shape stays identical (the eval calibration gate `make eval-calibration-gate` is the safety net).

**Branch:** `refactor/tech-debt-13b-eval-runner-registry`

## Current Duplication (byte-for-byte audit)

### The if-ladder

`runner.py:564-601` — `if agent == "scaffolder": cases = …; runner = …; elif agent == "dark_mode": …` × 9 branches. Each branch sets two locals (`cases`, `runner`) from imported constants and per-agent case-runner functions. The scaffolder branch additionally folds in `--include-uploaded` template eval cases (`:566-574`).

Triplicated agent-name list:
- `runner.py:564-601` — if-ladder (9 branches)
- `runner.py:713-723` — argparse `choices=[…, "all"]`
- `runner.py:752-764` — `agents = ["scaffolder", … ]` literal list when `--agent all`

### The per-agent case runners

| Function | Lines | Service class | Request schema | Method |
|---|---|---|---|---|
| `run_scaffolder_case` | 40-86 | `ScaffolderService` | `ScaffolderRequest(brief, stream, run_qa)` | `.generate(req)` |
| `run_dark_mode_case` | 89-145 | `DarkModeService` | `DarkModeRequest(html, color_overrides, preserve_colors, stream, run_qa)` | `.process(req)` |
| `run_content_case` | 148-196 | `ContentService` | `ContentRequest(operation, source_text, …)` | `.process(req)` |
| `run_outlook_fixer_case` | 199-252 | `OutlookFixerService` | `OutlookFixerRequest(html, …)` | `.process(req)` |
| `run_accessibility_case` | 255-308 | `AccessibilityService` | `AccessibilityRequest(html, …)` | `.process(req)` |
| `run_personalisation_case` | 311-372 | `PersonalisationService` | `PersonalisationRequest(html, platform, …)` | `.process(req)` |
| `run_code_reviewer_case` | 375-433 | `CodeReviewerService` | `CodeReviewerRequest(html, …)` | `.process(req)` |
| `run_knowledge_case` | 436-489 | `KnowledgeService` | `KnowledgeRequest(question, …)` | `.process(req)` |
| `run_innovation_case` | 492-545 | `InnovationService` | `InnovationRequest(prompt, …)` | `.process(req)` |

**Shared shape** (every runner):
1. Import service + request schema (lazy, inside function)
2. Construct service (zero-arg, or in scaffolder/knowledge: see "Edge cases")
3. Build request from `case` dict
4. `start = time.monotonic()` → call → `elapsed = time.monotonic() - start`
5. On success: build trace dict with `id`, `agent`, `dimensions`, `input`, `output`, `expected_challenges`, `elapsed_seconds`, `error=None`, `timestamp`
6. On exception: build trace dict with same shape but `output=None`, `error=f"{type(e).__name__}: {e}"`
7. Some runners attach `design_context` if `case.get("design_context")` (scaffolder only)
8. Some truncate large input fields (e.g., `case["html_input"][:5000]` in dark_mode)

### Edge cases (per-agent specifics that the template must accommodate)

- **Scaffolder** — folds in template-uploaded cases when `include_uploaded=True` (currently in the if-ladder, not the case runner). Belongs in the registry's `cases_loader`, not in `_run_case`.
- **Scaffolder** — attaches `case["design_context"]` to the trace dict if present (`:68-69, 84-85`).
- **Dark Mode** — truncates `html_input` to 5000 chars in the `input` field for trace compactness (`:112`).
- **Knowledge** — service needs a DB session (`KnowledgeService.search` requires `AsyncSession`). The eval pathway uses a global session per `agents/CLAUDE.md`. Verify during execution.
- **Output serialization** — each runner serializes its response differently (scaffolder: html + qa_results + qa_passed + model; dark_mode: probably similar with `darkened_html`; content: operation-specific output; knowledge: answer + sources + confidence). The template must accept an `output_serializer` callable.

## Contract Constraints (do not violate)

- **Trace JSONL shape stays identical.** Any field name change breaks `analysis.py`, `failure_warnings.py`, `improvement_tracker.py`, `production_sampler.py`, `judge_runner.py`. The shape is the contract.
- **Per-agent case-runner function names stay as top-level symbols** (`run_scaffolder_case`, …). External callers exist (`skill_ab.py:63-69` imports `run_agent` directly, not the per-case runners — verify no other imports via grep before deletion; conservative default: keep them as thin wrappers calling `_run_case`).
- **`run_agent` keeps its current signature.** Two real callers: `runner.py:769` (the `main()` `--agent all` loop) and `skill_ab.py:69`. Signature: `async def run_agent(agent: str, output_dir: Path, *, dry_run, batch_size, delay, skip_existing, include_uploaded, include_adversarial) -> None`. Both args and kwargs preserved.
- **`AgentName` literal** = `Literal["scaffolder", "dark_mode", "content", "outlook_fixer", "accessibility", "personalisation", "code_reviewer", "knowledge", "innovation"]`. Defined in `runner.py` (not a new module). Matches the project's "Literal Enums" pattern noted in `app/ai/CLAUDE.md`.
- **`AGENT_NAMES: tuple[AgentName, ...]`** = the literal tuple, used by argparse `choices=[*AGENT_NAMES, "all"]` and the `--agent all` expansion at `:752-764`. Removes the triplication.
- **Dry-run path stays untouched in shape.** `mock_traces.generate_mock_trace(case, agent)` already takes `(case, agent_name)` so no per-agent dispatch needed — the existing `dry_run` branch in `run_agent` (`:624-635, 680-689`) calls it directly and ignores the per-case runner. Keep this behavior; the template is only invoked on the real path.
- **Adversarial branch keeps using `runner` callable** (`:695`). After refactor, `runner` is resolved from the registry, not the local `runner` variable.
- **No changes to JSONL on-disk format.** `redact_value(trace)` wrap (`:633, 643, 687, 696`) stays where it is.

## Files to Create/Modify

- **Modify** `app/ai/agents/evals/runner.py` — the only source file changed.
  - Add `AgentName` Literal + `AGENT_NAMES` tuple near the top (~10 LOC).
  - Add `AgentSpec` dataclass / TypedDict (`cases_loader`, `case_runner`, optional `extra_trace_fields`) — ~15 LOC.
  - Add `AGENT_REGISTRY: dict[AgentName, AgentSpec]` populated with the 9 agents — ~30 LOC.
  - Add `_run_case(agent: AgentName, case, *, service_factory, request_builder, response_serializer, input_serializer) -> dict[str, Any]` helper — ~40 LOC, captures timing + error + builds trace dict.
  - Rewrite the 9 per-agent case runners as ~10-15 LOC adapters calling `_run_case`. Net reduction: ~9 × ~40 LOC = ~360 LOC saved minus ~150 LOC added by template + registry = **~200 LOC net reduction**.
  - Replace if-ladder at `:564-601` with `spec = AGENT_REGISTRY[agent]; cases = spec.cases_loader(include_uploaded=include_uploaded); runner = spec.case_runner`.
  - Replace argparse `choices=[…]` at `:713-723` with `choices=[*AGENT_NAMES, "all"]`.
  - Replace the `agents = […]` list at `:752-764` with `agents = list(AGENT_NAMES)`.
- **No changes** to `app/ai/agents/evals/skill_ab.py` — its `run_agent(agent, output_dir, dry_run=dry_run)` call is signature-compatible.
- **No changes** to per-agent service files, request schemas, judge files, or trace consumers.
- **No new test file** — refactor is covered by:
  - `make eval-check` (analysis + regression on existing traces)
  - `make eval-golden` (deterministic golden test, CI gate)
  - `make eval-calibration-gate` (TPR/TNR delta < 5pp)
  - New unit test: `app/ai/agents/evals/tests/test_runner_registry.py` (~30 LOC) — asserts `AGENT_REGISTRY` covers exactly `AGENT_NAMES`, each spec has callable `cases_loader` + `case_runner`, and `_run_case` produces a trace dict with the canonical 8 fields (`id`, `agent`, `dimensions`, `input`, `output`, `expected_challenges`, `elapsed_seconds`, `error`, `timestamp`) plus `design_context` when supplied.

## Implementation Steps

### Step 1 — Add `AgentName`, `AGENT_NAMES`, and `AgentSpec`

Near the top of `runner.py` (after the synthetic-data imports):

```python
AgentName = Literal[
    "scaffolder", "dark_mode", "content", "outlook_fixer", "accessibility",
    "personalisation", "code_reviewer", "knowledge", "innovation",
]
AGENT_NAMES: tuple[AgentName, ...] = (
    "scaffolder", "dark_mode", "content", "outlook_fixer", "accessibility",
    "personalisation", "code_reviewer", "knowledge", "innovation",
)

@dataclass(frozen=True)
class AgentSpec:
    cases_loader: Callable[..., list[dict[str, Any]]]
    case_runner: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
```

### Step 2 — Extract `_run_case` template

```python
async def _run_case(
    agent: AgentName,
    case: dict[str, Any],
    *,
    invoke: Callable[[dict[str, Any]], Awaitable[Any]],
    input_serializer: Callable[[dict[str, Any]], dict[str, Any]],
    output_serializer: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    """Shared timing + error capture + trace dict assembly.

    Concrete adapters pass:
    - invoke(case) → response (handles service init + request build + service method call)
    - input_serializer(case) → dict for trace["input"]
    - output_serializer(response) → dict for trace["output"]
    """
    start = time.monotonic()
    base: dict[str, Any] = {
        "id": case["id"],
        "agent": agent,
        "dimensions": case["dimensions"],
        "input": input_serializer(case),
        "expected_challenges": case.get("expected_challenges"),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    try:
        response = await invoke(case)
        base["output"] = output_serializer(response)
        base["error"] = None
    except Exception as e:
        base["output"] = None
        base["error"] = f"{type(e).__name__}: {e}"
    base["elapsed_seconds"] = round(time.monotonic() - start, 2)
    if case.get("design_context"):
        base["design_context"] = case["design_context"]
    return base
```

### Step 3 — Rewrite the 9 case runners as thin adapters

Per agent, ~10-15 LOC replacing ~50-60. Example for scaffolder:

```python
async def run_scaffolder_case(case: dict[str, Any]) -> dict[str, Any]:
    from app.ai.agents.scaffolder.schemas import ScaffolderRequest
    from app.ai.agents.scaffolder.service import ScaffolderService

    async def _invoke(c: dict[str, Any]) -> Any:
        service = ScaffolderService()
        return await service.generate(ScaffolderRequest(brief=c["brief"], stream=False, run_qa=True))

    return await _run_case(
        "scaffolder", case,
        invoke=_invoke,
        input_serializer=lambda c: {"brief": c["brief"]},
        output_serializer=lambda r: {
            "html": r.html,
            "qa_results": [x.model_dump() for x in (r.qa_results or [])],
            "qa_passed": r.qa_passed,
            "model": r.model,
        },
    )
```

Repeat for the 8 others. Per-agent specifics (dark_mode's 5000-char truncation, content's operation switch, etc.) live in their `input_serializer` lambdas.

### Step 4 — Build `AGENT_REGISTRY`

After the 9 adapter functions:

```python
def _scaffolder_cases(include_uploaded: bool = False) -> list[dict[str, Any]]:
    cases = list(SCAFFOLDER_TEST_CASES)
    if include_uploaded:
        gen = TemplateEvalGenerator()
        for tmpl_cases in gen.load_all().values():
            cases.extend(c for c in tmpl_cases if c.get("case_type") in ("selection_positive", "selection_negative"))
    return cases

def _static_cases(constant: list[dict[str, Any]]) -> Callable[..., list[dict[str, Any]]]:
    def _load(**_: object) -> list[dict[str, Any]]:
        return list(constant)
    return _load

AGENT_REGISTRY: dict[AgentName, AgentSpec] = {
    "scaffolder":      AgentSpec(_scaffolder_cases, run_scaffolder_case),
    "dark_mode":       AgentSpec(_static_cases(DARK_MODE_TEST_CASES), run_dark_mode_case),
    "content":         AgentSpec(_static_cases(CONTENT_TEST_CASES), run_content_case),
    "outlook_fixer":   AgentSpec(_static_cases(OUTLOOK_FIXER_TEST_CASES), run_outlook_fixer_case),
    "accessibility":   AgentSpec(_static_cases(ACCESSIBILITY_TEST_CASES), run_accessibility_case),
    "personalisation": AgentSpec(_static_cases(PERSONALISATION_TEST_CASES), run_personalisation_case),
    "code_reviewer":   AgentSpec(_static_cases(CODE_REVIEWER_TEST_CASES), run_code_reviewer_case),
    "knowledge":       AgentSpec(_static_cases(KNOWLEDGE_TEST_CASES), run_knowledge_case),
    "innovation":      AgentSpec(_static_cases(INNOVATION_TEST_CASES), run_innovation_case),
}
```

### Step 5 — Collapse `run_agent` if-ladder

`runner.py:562-601` becomes:

```python
if agent not in AGENT_REGISTRY:
    raise ValueError(f"Unknown agent: {agent}")
spec = AGENT_REGISTRY[cast(AgentName, agent)]
cases = spec.cases_loader(include_uploaded=include_uploaded)
runner = spec.case_runner
```

Everything below (file write loop, dry-run branch, adversarial branch) stays unchanged — they reference `runner` and `cases` exactly the same way.

### Step 6 — Replace argparse choices + `agents` list

`runner.py:713-723` and `:752-764` both become references to `AGENT_NAMES`:

```python
parser.add_argument("--agent", choices=[*AGENT_NAMES, "all"], required=True)
…
agents = list(AGENT_NAMES) if args.agent == "all" else [args.agent]
```

### Step 7 — Add registry coverage test

Create `app/ai/agents/evals/tests/test_runner_registry.py`:

```python
def test_registry_covers_all_agent_names():
    assert set(AGENT_REGISTRY) == set(AGENT_NAMES)

def test_each_spec_has_callables():
    for name, spec in AGENT_REGISTRY.items():
        assert callable(spec.cases_loader)
        assert callable(spec.case_runner)

async def test_run_case_produces_canonical_trace_shape():
    # mock invoke + serializers; assert trace has the 8 required fields
    trace = await _run_case("scaffolder", {"id": "x", "dimensions": {}}, ...)
    assert set(trace) >= {"id", "agent", "dimensions", "input", "output",
                          "expected_challenges", "elapsed_seconds", "error", "timestamp"}
```

## Verification

In order:

1. `uv run ruff format app/ai/agents/evals/runner.py && uv run ruff check app/ai/agents/evals/runner.py`
2. `make types` — pyright strict on the new Literal + dataclass + Callable type signatures.
3. `uv run pytest app/ai/agents/evals/tests/test_runner_registry.py -v` — new test passes.
4. `uv run python -m app.ai.agents.evals.runner --agent scaffolder --output /tmp/eval-test --dry-run` — smoke. Verify trace JSONL written, fields match pre-refactor.
5. `diff` the dry-run JSONL output before vs after on a single agent — must be byte-identical except `timestamp`. **This is the key behavioral gate.**
6. `make eval-golden` — deterministic CI gate, no LLM. Must pass with no diff.
7. `make eval-check` — analysis + regression. Per-agent regression tolerance is 3pp (`AGENT_REGRESSION_TOLERANCE`).
8. `make eval-calibration-gate` — TPR/TNR delta within 5pp. Sanity check; we don't change judge behavior so should be 0 delta.
9. `make check-full` — full backend gate (lint + types + tests + security + golden conformance + flag audit + migration lint).

## Rollback

Single-file refactor, isolated to `app/ai/agents/evals/runner.py` + one new test. Rollback = `git revert <commit>` if any of the above gates fail. No DB migrations, no env-var changes, no schema changes. Trace JSONL on disk is unaffected because the on-disk format is unchanged.

## Out of scope (do not bundle)

- Renaming `process` vs `generate` on agent services to unify the method name. Two services use `generate` (scaffolder, others?), seven use `process`. Worth a separate small PR; out of scope here.
- Pulling the per-agent input/output serializers into the per-agent `service.py` as `to_eval_trace_input()` / `to_eval_trace_output()` methods. Cleaner separation but a different review domain (touches 9 agent packages instead of 1 eval file). Defer.
- The argparse-to-Typer migration ("`runner.py` should be a CLI subcommand of a single `eval` Typer app"). Pre-existing nit; doesn't change with F025.
- `mock_traces.generate_mock_trace(case, agent)` — currently bypasses the per-case runner. Could be plugged into the registry as `spec.mock_runner` for symmetry, but no current call site needs this and adding it widens scope. Leave for follow-up if a use case emerges.
