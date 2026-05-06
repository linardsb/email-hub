# Tech Debt 08 (Follow-up) — Parts B, C, D1, D3

**Source:** Continuation of `.agents/plans/tech-debt-08-converter-god-functions.md`. Part A landed in commit `7c538a55` on `refactor/tech-debt-08-converter-decomp`.
**Scope:** Remaining work — `_convert_with_components` split (B), `DesignSyncService` carve-out (C), legacy shim telemetry + later removal (D1, D3).
**Estimated effort:** **2 sessions minimum.** D3 is hard-blocked by a 14-day telemetry window after D1 ships.
**Prerequisite:** Part A merged. Snapshot baseline captured (`data/snapshot/baseline.before` exists, or recapture before starting).

## Findings still open

- F011 `_convert_with_components` 325 LOC — Critical
- F012 `DesignSyncService` 49 methods, 1729 LOC — Critical
- F013 legacy converter shims still wired — Critical

## Pre-flight

```bash
git checkout refactor/tech-debt-08-converter-decomp   # or branch off main if A merged
make check
make snapshot-test
make snapshot-visual
cp -r data/snapshot/baseline data/snapshot/baseline.before  # if not already saved
```

The Part A refactor introduced `RenderContext` (`app/design_sync/render_context.py`) and per-node renderers in `converter.py`. The single production callsite is in `converter_service.py:_convert_with_components`. Treat that file as the working surface for Part B.

**Lesson from Part A:** the original plan undercounted test callsite migrations (14 → 49 actual). For Part B, run a similar grep before starting:
```bash
rg -n "_convert_with_components|_match_phase|_render_phase|_verify_phase|_compile_phase" app/design_sync/
```

---

## Part B — Split `_convert_with_components` (F011)

### B1. Define phase dataclasses

**New file:** `app/design_sync/conversion_phases.py`:
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class MatchPhase:
    matches: list[ComponentMatch]
    group_map: dict[int, RepeatingGroup]
    sibling_groups: list[RepeatingGroup]

@dataclass(frozen=True)
class RenderPhase:
    html: str
    section_traces: list[SectionTrace]
    rendered_group_ids: set[int]

@dataclass(frozen=True)
class VerifyPhase:
    final_html: str
    fidelity: float
    corrections_applied: int
    iterations: int

@dataclass(frozen=True)
class CompilePhase:
    final_html: str
    contract_results: list[ContractResult]
```

### B2. Refactor `_convert_with_components`

`app/design_sync/converter_service.py` — locate the current `_convert_with_components` (line numbers shifted post-Part A; use `rg -n "async def _convert_with_components"`). Body becomes:

```python
async def _convert_with_components(self, structure, tokens, options) -> ConversionResult:
    match = await self._match_phase(structure, tokens, options)
    render = await self._render_phase(match, tokens, options)
    if options.verify_enabled:
        verify = await self._verify_phase(render, structure, options)
    else:
        verify = VerifyPhase.from_render(render)
    compile_ = await self._compile_phase(verify, options)
    return ConversionResult.from_phases(match, render, verify, compile_)
```

Each `_*_phase` is ≤ 80 LOC.

### B3. Per-phase tests

`app/design_sync/tests/test_conversion_phases.py` — one test class per phase, mocking the prior phase's output. Aim for ≥1 happy-path + ≥1 edge-case per phase.

### B4. Verify

```bash
make snapshot-visual          # zero pixel diff vs baseline.before
make snapshot-test
make converter-data-regression
make test app/design_sync/ -v
```

---

## Part C — `DesignSyncService` carve-out (F012)

### C1. Identify boundaries

`app/design_sync/service.py` already has section comments. Confirmed groups:
- Connections (sync, OAuth, status)
- Assets (download, manifest)
- Imports (HTML import, parse, mapping)
- Webhooks (Figma webhook, debounced sync)
- Tokens & structure (the core conversion bridge)
- Project access (RBAC for design connections)

### C2. Carve

```
app/design_sync/services/
  __init__.py
  connection_service.py   ← was: methods 1-12 of DesignSyncService
  assets_service.py       ← methods 13-18
  import_service.py       ← already exists at app/design_sync/import_service.py;
                            move ownership boundary or merge here
  webhook_service.py      ← methods 19-23
  conversion_service.py   ← methods 24-35 (the core that talks to converter_service)
  access_service.py       ← project-access checks (small)
```

**This PR: facade only.** `DesignSyncService` becomes a thin (~50 LOC) facade holding the 6 carved service refs and delegating each public method. **Do not delete the class in this PR** — ~30 test fixtures (`test_webhook.py`, `test_import_service.py`, `test_build_document.py`) instantiate `DesignSyncService(mock_db)` directly, plus MCP tools / blueprint engine / routes import it. Mass-migrating callers in the same PR balloons the diff and risks breaking unrelated paths.

A follow-up plan **`tech-debt-08b-design-sync-service-deletion.md`** must be opened before this PR merges. It tracks: (a) migrating each route handler in `routes.py` from facade → direct carved-service `Depends`, (b) migrating MCP tools and blueprint engine references, (c) updating test fixtures to mock the specific carved service, (d) deleting the facade. Reference 08b in the `Done when` checklist below.

### C3. Routes update

`app/design_sync/routes.py` — currently has many inline imports inside handlers (around line 1060 pre-Part-A; verify with `rg -n "^    from app" app/design_sync/routes.py`). **In this PR**, routes still depend on `DesignSyncService` (the facade). Inline imports can be tidied opportunistically but the DI-per-carved-service migration lands in 08b. Route file shrinks materially only after 08b.

### C4. Verify

```bash
make check
make test app/design_sync/ -v
```

---

## Part D — Legacy shim retirement (F013)

**THIS SPANS TWO PRs** because of the telemetry window.

### D1. PR-1: Add telemetry

`app/design_sync/converter_service.py` — locate the shim entries (pre-Part-A line numbers were `441,505,1024`; re-grep with `rg -n "convert_design|convert_layout|_convert_recursive" app/design_sync/converter_service.py`). At each shim entry, emit:

```python
import inspect, warnings
logger.info(
    "design_sync.converter.shim_called",
    entry=__name__,
    caller=inspect.stack()[1].function,
)
warnings.warn(
    "convert_design/convert_layout shim is deprecated; use convert_document",
    DeprecationWarning,
    stacklevel=2,
)
```

Migrate the two known callers:
- `app/design_sync/service.py:362` (verify line) → call `convert_document` directly.
- `app/design_sync/penpot/service.py:165` (verify line) → same.

After the call-site migration, the only path that hits the shims is from external code (none expected).

### D2. Wait 2 weeks (calendar-tracked)

The window is non-negotiable — its purpose is to detect *unknown* external callers. Skipping = silent breakage risk for consumers we don't know about.

After D1 merges, append a tracking row to the active `TODO.md` "Operational follow-ups" section (or create one) with a target date 14 days out. Compute the date from the **D1 merge date**, not from when this plan is read. Example template:

> **YYYY-MM-DD — F013 D3 readiness check.** Run `grep -c design_sync.converter.shim_called traces/*.jsonl traces/structured.log 2>/dev/null` (and any centralised log store the team uses). If count is **zero**, proceed to D3. If **non-zero**, identify each caller from the `caller=` log field, migrate it to `convert_document`, and reset the timer to a fresh +14 days.

Do not take any code action on D3 in the same session as D1.

### D3. PR-2: Remove the shims

After 2 clean weeks:
- Delete `_convert_recursive` (formerly `converter_service.py:1013-1156`; re-locate by name) — only if it's not the MJML-failure fallback. **Verify**: the MJML fallback path was at `:530` and is *separate* from the shim entries. Keep it.
- Delete the shim methods (`convert_design`, `convert_layout`).
- Delete `node_to_email_html` from `app/design_sync/converter.py` if `_convert_recursive` no longer needs it. ~750 LOC out (post Part A's per-node split, the byte-count is smaller but the symbol is the same).

**Pre-deletion safety extraction** (carry-over from original plan risk note): `node_to_email_html` and its helpers (`_relative_luminance`, `_contrast_ratio`, etc. — see audit F024-F025) may be imported by other modules in `app/design_sync/`. Run `rg -n "from app.design_sync.converter import" app/` first; extract those helpers to `app/shared/color.py` *before* deleting `converter.py`, otherwise imports break.

### D4. Verify

```bash
make snapshot-visual
# All cases pass — the shims weren't doing anything different.
```

---

## Verification (final)

```bash
make check
make test app/design_sync/ -v
make snapshot-test
make snapshot-visual         # zero pixel diff vs baseline.before
make converter-data-regression
```

## Rollback

Each part (B/C/D1/D3) is an independent revert. The most invasive is C — services carve-out. If carved services have import cycles, fold back into `service.py` and revisit boundaries.

## Risk notes

- **Part D requires calendar discipline.** The telemetry window is *real*. Don't skip to D3 because "no one is calling it" — verify with logs.
- **`node_to_email_html` is exported as a public symbol.** Other modules in `app/design_sync/` import its helpers. Extract those helpers to `app/shared/color.py` *before* deleting `converter.py` in D3.
- **`DesignSyncService` is referenced from MCP tools, routes, blueprint engine.** A facade-then-direct-dep migration is safest: keep facade in place for one PR (C), migrate callers in a follow-up (08b).
- **Snapshot tests are the safety net.** They've caught regressions in Phases 41, 47, 49. Trust them; if a snapshot diff appears, treat it as a bug.

## Done when

- [x] **Part B** — shipped in `bf66bd0a`. Implementation diverged from the plan: **3 phases** (`_match_phase` / `_render_phase` / `_assemble_phase`) instead of the planned 4. Verify/Compile from the plan didn't apply — verification is an MJML-path concern (`_apply_verification`), and quality contracts merged into `_assemble_phase`. LOC caps not strictly met: `_convert_with_components` is ~54 LOC (cap 30), `_render_phase` is ~122 LOC (cap 80) — the cache/group/custom-gen branches resist further splitting without harming readability. Per-phase tests live in `app/design_sync/tests/test_conversion_phases.py`.
- [x] **Part C** — shipped in `ab8d0b54`. Six carved services exist under `app/design_sync/services/` (`connection_service.py`, `assets_service.py`, `import_service.py`, `webhook_service.py`, `conversion_service.py`, `access_service.py`). The `DesignSyncService` facade was carved here and **subsequently deleted in 08b** (`246b0712` + `fe85d60c` + `f28f8fb1`); `service.py` shrunk to 387 LOC. Follow-up plan `tech-debt-08b-design-sync-service-deletion.md` is checked in.
- [x] **Part D1** — shipped in `8b996b4c`. Telemetry live at three shim entries (`converter_service.py:475`, `:555`, `:1163`). Tracking row in `TODO.md` Operational follow-ups: **2026-05-11 — F013 D3 readiness check** (D1 merged 2026-04-27).
- [ ] **Part D3** — calendar-blocked by D2. Earliest action **2026-05-11** (5 days from 2026-05-06). Do not attempt before the readiness grep returns zero.
- [ ] **Mark F011, F012, F013 as RESOLVED in `TECH_DEBT_AUDIT.md`** — F011 + F012 already resolvable today; F013 stays open until D3.
