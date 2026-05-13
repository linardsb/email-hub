# Tech Debt 00 — Status and Roadmap

**Source:** `TECH_DEBT_AUDIT.md` (2026-04-26, 70 findings F001–F070)
**Scope:** Reconcile audit doc with current `main`, sequence the open items into 21 executable sessions.
**Status:** Active — meta-plan; sub-plans referenced inline; new sub-plans created lazily.
**Generated:** 2026-05-04
**Last verified against `main`:** 2026-05-08 — see "Verification snapshot — 2026-05-08" below.

## Decisions locked

1. **Audit refresh runs first as a doc-only PR (Session 0).** Folding into Session 1 hides the doc baseline behind a code review and forces every later session to re-verify status.
2. **RLS approach: option B** (repo-layer enforcement; retire RLS migrations). RLS as defense-in-depth is only valuable if live — currently it's a comment that doesn't compile. Faster to land, debuggable, fewer DB infra changes.
3. **F013 closure splits across 2 sessions ≥2 weeks apart.** The legacy `_convert_recursive` is a load-bearing fallback when MJML compile fails; removing without telemetry risks silent production breakage. Instrument first (Session 7), wait for Grafana confirmation, remove (Session 18).
4. **Plan 01 (quick wins) owns F027–F029.** Plan 02 already shipped its agent + MCP scope work; the JWT items in Plan 02 are reference, not execution scope. Single-source ownership prevents double-execute.
5. **Sequencing assumes 1 contributor.** Parallelism flagged in the table; a team of 2+ can fan out tracks 10–17 against 5–8 trivially.
6. **Tier-1 stop point after Session 4** = "minimum-viable-secure" milestone. Production deploys are safe past this point and unsafe before it. Tag a release here.
7. **Sub-plans for sessions 10–20 are written lazily**, one session before execution. Avoids ~3500 LOC of speculative plan content drifting against `main`.
8. **Snapshot regression is the safety net for converter refactor** (Sessions 5–6). `make rendering-regression` zero-diff is the gate, not unit tests. Per-branch unit tests (F065) come after, in Session 17.
9. **Two sweep PRs at the end, by review domain.** Backend sweep (Session 19) and frontend sweep (Session 20). Heterogeneous content is fine inside one review domain; mixing backend/frontend in a sweep is not.

## Phase 1 — Audit doc reconciliation (Session 0 deliverable)

### Findings to flip OPEN → RESOLVED (inline annotation)

| ID | Evidence on disk | Closure ref |
|---|---|---|
| F006 | `app/streaming/{manager,subscriber,routes}.py` gone; `/ws/stream` mount removed from `app/main.py` | `eddcd1ac` (#40) |
| F007 | `app/example/` gone; `/api/v1/items` removed from `app/main.py` | `eddcd1ac` (#40) |
| F015 | `mjml_generator.py` + `penpot/converter.py` shim deleted; `DESIGN_SYNC__PENPOT_CONVERTER_ENABLED` flag removed | `eddcd1ac` |
| F018 | `app/qa_engine/custom_checks/` package, 11 files (a11y, brand, css, dark_mode, file_size, html, image, link, mso, personalisation, spam) | landed Apr 27 |
| F019 | `app/qa_engine/checks/_factory.py` exists | landed Apr 27 |
| F032 | `app/core/config/` is now a 14-file package (8999-LOC `__init__.py` is the re-export aggregator) | landed Apr 28 |
| F041 | already inline in audit; 332 per-icon files under `cms/apps/web/src/components/icons/generated/` | Plan 09a (#48) |
| F044 | `cms/apps/web/src/hooks/use-builder.ts` 215 LOC; `cms/apps/web/src/lib/builder/html-assembler.ts` exists with tests | landed |
| F048 | collaboration WS JWT wired | landed |
| F064 | hardcoded `linardsberzins@gmail.com` moved to `settings.auth.demo_user_email` | `eddcd1ac` |

### Fudge / partial items resolved to explicit status

| ID | New status | Closes when |
|---|---|---|
| F035 | OPEN — count refreshed | Audit refresh records the actual count (currently 67 `DESIGN_SYNC__*` entries in `.env.example`, up from the 47 stated in the audit). Cull session is out of scope here; goal: ≤30 active flags. |
| F043 | OPEN — PARTIAL (corrected from user-table claim) | 2026-05-04 verification: `grep -rl '@ts-nocheck' cms/apps/web/src` returns 10 files (down from the audit's 12). Closes when count reaches 0; tracked by Session 16 (`tech-debt-09c-ts-strict-tests.md`). |
| F063 | CLOSED (Session 20) | Approach (a): `.gitignore` flipped to blanket `data/debug/*/*` + 5 `!` exceptions for curated fixture types; stray `=2.0` file deleted; `docs/TODO-completed.md` rotated (phases 0-39 → archive); 25 phase-≤49 plans moved to `.agents/plans/_archive/`. `design.png` + `design_meta.json` surfaced as untracked during preflight but confirmed regenerable during execute and excluded. |

### Findings that stay OPEN

F001, F002, F003, F010, F011, F013, F014, F025, F026, F027, F028, F029, F030, F031, F036, F037, F038, F039, F040, F042, F043, F045, F046, F047, F049, F051, F052, F053, F054, F055, F056, F057, F058, F059, F060, F061, F062, F065, F066, F067, F068, F070.

### Sections to refresh

- **Top 5 — Fix These First:** items 3 (Phase 48) and 5 (dead code) drop out — shipped. Replace with F010/F011 (converter god funcs) and F052/F053 (Knowledge split).
- **Quick Wins checkboxes:** tick F050, F063, F064.
- **Open Questions:** Q2 → "RESOLVED — Phase 48 parked under `prototypes/ai-pipeline/`, see Plan 05B"; Q3 → "RESOLVED — `app/example/` deleted, `eddcd1ac`"; Q4 → "RESOLVED — `/ws/stream` deleted, `eddcd1ac`". Q1 collapses after Session 2 lands.
- **"Things That Look Bad But Are Actually Fine":** stale paths — `app/core/config.py` → now a package; `app/qa_engine/custom_checks.py` → now a package. Sweep refresh, no logic changes.

## Phase 2 — 21-session execution table

### Critical path (sessions 0–4, serial — Tier 1)

| # | Title | Findings | Plan ref | Verify | Effort |
|---|---|---|---|---|---|
| 0 | Audit refresh (doc-only) | F035 count, F042 size, F043 PARTIAL correction, F063 partial close, RESOLVED annotations on 10 findings | (this file, Phase 1) | doc PR review; `git status` clean; pre-commit passes | 30–60m |
| 1 | Multi-tenant repo scoping | F002, F003 | `tech-debt-03-multi-tenant-isolation.md` §A | new `tests/test_cross_tenant_leak.py` parametrized over 8 repos; `make check-full` | 1 session |
| 2 | RLS retirement + env doc | F001 | `tech-debt-03-multi-tenant-isolation.md` §B | `alembic upgrade head` clean; grep zero `BYPASSRLS` references; CLAUDE.md updated | 1 session |
| 3 | Frontend proxy + token security | F045, F046, F047 | `tech-debt-01-quick-wins.md` (frontend subset) | `make check-fe` + new proxy header tests + 401 invalidation test | 1 session |
| 4 | Auth cluster — JWT + lockout + revocation | F027, F028, F029, F031 | `tech-debt-01-quick-wins.md` (auth subset) | `make check` + token edge-case tests | 1 session |

**Tier-1 stop point.** Tag release here. Production deploys are safe past this line; before it they expose cross-tenant data and accept malformed JWTs.

### God-function decomposition (sessions 5–9)

| # | Title | Findings | Plan ref | Notes |
|---|---|---|---|---|
| 5 | RenderContext extraction | F010 | `tech-debt-08-converter-god-functions.md` (split as 08a) | **Pre-step:** capture `make rendering-regression` baselines. **Post-step:** zero-diff assertion. |
| 6 | `_convert_with_components` phase split | F011 | `tech-debt-08-converter-god-functions.md` §B | Split into `MatchPhase` / `RenderPhase` / `VerifyPhase` frozen dataclasses. Snapshot equivalence. |
| 7 | Legacy shim instrumentation | F013 (instrument only) | `tech-debt-08-converter-god-functions.md` §C1 (split as 08c) | structlog event + Prometheus counter at the 2 shim entry points + `DeprecationWarning`. **Starts the 2-week telemetry clock.** |
| 8 | DesignSyncService facade deletion | F012 closure | `tech-debt-08b-design-sync-service-deletion.md` | Delete the 1729-LOC delegating facade; rewrite ~30 caller imports. Mechanical. |
| 9 | `workspace/page.tsx` decomposition | F042 | `tech-debt-09-frontend-cleanup.md` §A | Extract `useWorkspaceTemplate`/`useWorkspaceDialogs`/`useWorkspaceFollowMode`/`useAgentMode`. **Parallel-safe with 5–8** (no shared files). |

### Parallel tracks (sessions 10–17 — fan out)

Six independent backend tracks (10–15) + two frontend/test tracks (16, 17). Schedule in any order once Tier-1 is green. Each is 1 session.

| # | Title | Findings | Plan ref | New plan? |
|---|---|---|---|---|
| 10 | Resilience cluster | F036, F037, F038, F040, F055 | `tech-debt-10-config-and-observability.md` (extend) | Extend Plan 10 |
| 11 | `/bootstrap` hardening | F030 | `tech-debt-12-auth-bootstrap.md` | New (lazy) |
| 12 | LLM adapter base class | F026 | `tech-debt-13-llm-adapter-base.md` | New (lazy) |
| 13 | Eval runner registry | F025 | `tech-debt-13b-eval-runner-registry.md` | New (lazy) |
| 14 | KnowledgeService split + RRF extract | F052, F053, F054 | `tech-debt-11-knowledge-split.md` | New (lazy) |
| 15 | Figma typed boundaries | F014 | `tech-debt-15-figma-typed-boundaries.md` | New (lazy) |
| 16 | Frontend test types + middleware default-deny | F051, F068 (F043 verify-only) | `tech-debt-09c-ts-strict-tests.md` (extend) | Extend |
| 17 | Connector + QA test gaps | F065, F066, F067 | Extends `tech-debt-04-connector-dedup.md` + `tech-debt-06-custom-checks-split.md` | Extend |

**Parallelism map (file disjointness verified):**
- 10 → `app/core/database.py`, `app/email_engine/service.py`, `app/scheduling/engine.py`, `app/notifications/emitter.py`, `app/qa_engine/repair/pipeline.py`
- 11 → `app/auth/routes.py`, `app/auth/service.py`
- 12 → `app/ai/adapters/{base,anthropic,openai_compat}.py`
- 13 → `app/ai/agents/evals/runner.py`
- 14 → `app/knowledge/{service,fusion,repository}.py`
- 15 → `app/design_sync/figma/{service,raw_types}.py`
- 16, 17 → `cms/` and `tests/` only

Six-way backend parallelism is safe. Track 16 + 17 add 2 more frontend/test contributors.

### Telemetry-gated closure (Session 18)

| # | Title | Findings | Plan ref | Trigger |
|---|---|---|---|---|
| 18 | Legacy shim removal | F013 closure | `tech-debt-08-converter-god-functions.md` §C2 | ≥2 weeks since Session 7 + Grafana shows zero hits at the 2 shim entry points. If non-zero hits → converts to caller-migration session, not removal. |

### Long tail — sweep PRs (sessions 19–20)

| # | Title | Findings | Plan ref |
|---|---|---|---|
| 19 | Backend sweep | F049 (SDK CI gate), F056, F057, F058, F059, F060, F061, F062, F070 | `tech-debt-19-backend-sweep.md` (lazy) |
| 20 ✅ | Frontend / repo sweep | F050, F063 closure | `tech-debt-20-frontend-sweep.md` |

## Verification snapshot — 2026-05-08

Each session below was verified against `main` at HEAD `f670a4f6`. `[STATE]` line records what is already in code; the prescriptive Steps remain unchanged so they can drive execution.

  ─────────────────────────────────────────────────────────────────────────
   1. Cluster F — F013-D3 cleanup
  ─────────────────────────────────────────────────────────────────────────
  [PLAN EXISTS] .agents/plans/f013-d3-operational-followup-cleanup.md
  [STATE] ✅ Code already done — `rg "^def convert\b|^def convert_mjml|^def _convert_recursive" app/design_sync/` returns 0 hits (commit `d9132c7c`). Reduce this session to a docs-only PR: TODO.md + `f013-d3-operational-followup-cleanup.md` Done When + `.agents/deferred-items.json`.
  Step 1: read the plan.
  Step 2: verify shims really are gone (rg "^def convert\b|def convert_mjml|
  def _convert_recursive" app/design_sync/).
  Step 3: edit TODO.md, the followup plan's "Done When", and
  .agents/deferred-items.json per the plan. No code changes. Fold into the
  next PR that touches TODO.md.

  ─────────────────────────────────────────────────────────────────────────
   2. Cluster A — Connector OAuth cache hardening (known-bug, security)
  ─────────────────────────────────────────────────────────────────────────
  [PLAN EXISTS] .agents/plans/tech-debt-04-connector-oauth-cache.md
  [STATE] ❌ Untouched — `app/connectors/{sfmc,adobe}/sync_provider.py:29,37` still carry `ClassVar[dict]` + `hashlib.sha256(...)[:16]`.
  Branch tech-debt/04-connector-oauth-cache.
  Step 1: /preflight-check the plan.
  Step 2: /be-execute the plan.
  Replace ClassVar SHA-256[:16] cache in app/connectors/{sfmc,adobe}/
  sync_provider.py with per-instance LruWithTtl(64) keyed by
  f"{vendor}:{client_id}". Drop hashlib + time imports. Add cross-tenant
  key + per-instance regression tests. Close tech-debt-04-sync-provider-
  duplication. Gate: make check-full.

  ─────────────────────────────────────────────────────────────────────────
   3. Cluster B — Alembic schema drift (known-bug, destructive risk)
  ─────────────────────────────────────────────────────────────────────────
  [PLAN EXISTS] .agents/plans/tech-debt-19-alembic-schema-drift.md
  [STATE] ❌ Untouched — no `normalize_schema_drift` migration in `alembic/versions/`; no `include_object` filter in `alembic/env.py`.
  Branch tech-debt/19-alembic-drift.
  Step 1: /preflight-check the plan.
  Step 2: /be-execute the plan.
  Hand-write a single normalize_schema_drift migration: NULL backfill →
  drop items table → TIMESTAMPTZ alter on ~30 cols → SET NOT NULL on 10
  cols → reconcile qa_overrides + memory_entries HNSW + column comments.
  Add include_object PK-index filter to alembic/env.py. Drop
  continue-on-error from CI. Close tech-debt-alembic-schema-drift.
  Gate: alembic check exits 0 against fresh DB.

  ─────────────────────────────────────────────────────────────────────────
   4. Session 11 — /bootstrap hardening (F030)
  ─────────────────────────────────────────────────────────────────────────
  [WRITE PLAN FIRST] .agents/plans/tech-debt-12-auth-bootstrap.md does not exist.
  [STATE] ❌ Untouched — `app/auth/service.py:350-355` still gates only on `settings.environment == "development"` + zero-user check. No loopback / bootstrap-secret factor.
  Branch sec/tech-debt-12-bootstrap-hardening.
  Step 1: /be-planning — produce tech-debt-12-auth-bootstrap.md covering
  loopback-origin check OR env-bound bootstrap secret as an additional
  factor on top of the existing ENVIRONMENT=development + zero-user check
  at app/auth/routes.py:43-56 and app/auth/service.py:350-355. Include a
  regression test asserting non-loopback origins are 403'd in development.
  Step 2: /preflight-check the new plan.
  Step 3: /be-execute. Gate: make check-full + the new regression test.

  ─────────────────────────────────────────────────────────────────────────
   5. Session 10 — Resilience cluster (F036/F037/F038/F039/F055)
  ─────────────────────────────────────────────────────────────────────────
  [EXTEND PLAN] .agents/plans/tech-debt-10-config-and-observability.md exists;
    add a new section for the 5 findings.
  [STATE] ⚠️ Partial — F036 already done (`app/core/config/database.py:10` `pool_size=20`). F037/F038/F039/F055 still open: `_call_builder` has no tenacity decorator; `app/scheduling/engine.py:78-81` uses `os.getpid()` not UUID + CAS; `_evaluate_jobs` not yet `asyncio.create_task`-ified; `app/qa_engine/repair/pipeline.py:66-72` logs stage failures but does not roll back. Drop F036 from scope.
  Branch refactor/tech-debt-10-resilience.
  Step 1: /be-planning --extend tech-debt-10-config-and-observability.md —
  add a new section covering F036 (DB pool 8→20+ at app/core/database.py),
  F037 (tenacity retry + circuit-breaker on Maizzle httpx call at
  app/email_engine/service.py:264), F038 (scheduling leader-lock UUID + CAS
  at app/scheduling/engine.py:78-81), F039 (non-blocking _evaluate_jobs via
  asyncio.create_task with tracking set), F055 (repair pipeline rollback on
  stage failure at app/qa_engine/repair/pipeline.py:66-72).
  Step 2: /preflight-check the extended plan.
  Step 3: /be-execute. Gate: make check-full + scheduling integration test.

  ─────────────────────────────────────────────────────────────────────────
   6. Cluster C — Tenant-isolation integration harness
  ─────────────────────────────────────────────────────────────────────────
  [PLAN EXISTS] .agents/plans/tech-debt-03-tenant-isolation-harness.md
  [STATE] ⚠️ Partial — `app/tests/test_tenant_isolation.py` exists, but no `_integration_engine` fixture, no `make test-integration` target, no `postgres-tenant-iso` compose service. Bulk of harness still missing.
  Branch tech-debt/03-tenant-iso-harness.
  Step 1: /preflight-check the plan.
  Step 2: /be-execute the plan.
  Add session-scoped _integration_engine fixture running
  alembic.command.upgrade(...,"head") against TEST_DATABASE__URL; per-test
  db fixture with TRUNCATE … RESTART IDENTITY CASCADE. Wire payload
  factories for templates/memory/qa_results/approvals; promote 4
  xfail(strict=True) entries to plain id=…. Add postgres-tenant-iso compose
  service + CI integration job + make test-integration target. Close
  tech-debt-03-…-harness. Gate: integration job runs green; no skips.

  ─────────────────────────────────────────────────────────────────────────
   7. Session F043 — Strict types in frontend tests (in-flight, 26 commits)
  ─────────────────────────────────────────────────────────────────────────
  [PLAN EXISTS] .agents/plans/tech-debt-09c-ts-strict-tests.md
  [STATE] ✅ Done — `rg -l "@ts-nocheck" cms/apps/web/src` returns 0 files. Drop this session; close F043 and the plan.
  Resume branch refactor/tech-debt-09c-ts-strict-tests (rebase on main).
  Step 1: read the plan.
  Step 2: verify @ts-nocheck count: rg -l "@ts-nocheck" cms/apps/web/src
          — work in size order from the smallest remaining file.
  Step 3: /fe-execute the plan.
  Replace mocks with vi.mocked<typeof useSWR>(...) +
  satisfies Partial<typeof import("...")>. Per-file commits prefixed
  test(cms): re-type X without @ts-nocheck (F043); production-code bugs
  in separate fix(web): commits. Gate: pnpm --filter web type-check 0
  errors; ≥774 tests passing; zero @ts-nocheck remaining.

  ─────────────────────────────────────────────────────────────────────────
   8. Session 9 — Workspace decomposition (F042)
  ─────────────────────────────────────────────────────────────────────────
  [PLAN EXISTS] .agents/plans/tech-debt-09-frontend-cleanup.md §B
  [STATE] ⚠️ Partial — `cms/apps/web/src/app/projects/[id]/workspace/page.tsx` already 390 LOC (was 771). `hooks/workspace/` already exports use-agent-mode, use-auto-compile, use-editor-state, use-workspace-actions, use-workspace-dialogs, use-workspace-export-actions, use-workspace-follow-mode, use-workspace-qa, use-workspace-template. Remaining work: slim 390 → ≤200 composition root + the 4 deep-relative-import fixes. Rescope as a finishing pass.
  Branch refactor/tech-debt-09-workspace-decomp (fresh off main; cherry-pick
  962cf10b from old branch, drop the rest).
  Step 1: read §B of the plan.
  Step 2: /preflight-check the plan.
  Step 3: /fe-execute the plan.
  Extract useAgentMode / useWorkspaceTemplate / useWorkspaceDialogs /
  useWorkspaceFollowMode / useEditorState into hooks/workspace/. Slim
  cms/apps/web/src/app/projects/[id]/workspace/page.tsx (771 LOC) to ≤200
  LOC composition root. Replace "../../../../components/icons" with
  "@/components/icons" across the 4 deep-relative-import files (closes F022
  frontend). Per-hook tests in hooks/workspace/__tests__/ that fail if state
  leaks back. Gate: make check-fe.

  ─────────────────────────────────────────────────────────────────────────
   9. Session 12 — LLM adapter base class (F026)
  ─────────────────────────────────────────────────────────────────────────
  [WRITE PLAN FIRST] .agents/plans/tech-debt-13-llm-adapter-base.md does not exist.
  [STATE] ❌ Untouched — `app/ai/adapters/` contains only `anthropic.py` + `openai_compat.py`; no `base.py`, no `BaseLLMProvider(ABC)`.
  Branch refactor/tech-debt-13-llm-adapter-base.
  Step 1: /be-planning — produce tech-debt-13-llm-adapter-base.md covering
  extraction of BaseLLMProvider(ABC) at app/ai/adapters/base.py and
  collapse of the ~150 LOC duplicated between
  app/ai/adapters/anthropic.py:105-200 and openai_compat.py:115-210.
  Subclasses override only complete / stream / _format_payload.
  Step 2: /preflight-check the new plan.
  Step 3: /be-execute. Gate: make check-full + adapter integration tests
  (both providers must still pass their full surface).

  ─────────────────────────────────────────────────────────────────────────
  10. Session 13 — Eval runner registry (F025)
  ─────────────────────────────────────────────────────────────────────────
  [WRITE PLAN FIRST] .agents/plans/tech-debt-13b-eval-runner-registry.md does
    not exist.
  [STATE] ❌ Untouched — `app/ai/agents/evals/runner.py` is 782 LOC; the `if agent == "scaffolder" / elif "dark_mode" / …` ladder still lives at ~line 548.
  Branch refactor/tech-debt-13b-eval-registry.
  Step 1: /be-planning — produce tech-debt-13b-eval-runner-registry.md
  covering replacement of the 159-LOC if-ladder in
  app/ai/agents/evals/runner.py:548 with a dict[AgentName, Callable]
  registry + shared _run_case template.
  Step 2: /preflight-check the new plan.
  Step 3: /be-execute. Gate: make eval-check + make eval-golden green;
  same verdicts as pre-refactor on existing trace fixtures.

  ─────────────────────────────────────────────────────────────────────────
  11. Session 14 — KnowledgeService split + RRF extract (F052, F053)
  ─────────────────────────────────────────────────────────────────────────
  [WRITE PLAN FIRST] .agents/plans/tech-debt-11-knowledge-split.md does not exist.
  [STATE] ❌ Untouched — `app/knowledge/service.py` is 1050 LOC; no `IngestionService` / `SearchService` / `TagService` / `GraphSearchService`; no `app/knowledge/fusion.py`.
  Branch refactor/tech-debt-11-knowledge-split.
  Step 1: /be-planning — produce tech-debt-11-knowledge-split.md covering
  F052 split of app/knowledge/service.py:73-1048 (god class, 22 methods)
  into IngestionService / SearchService / TagService / GraphSearchService,
  and F053 extraction of app/knowledge/fusion.py with rrf_fuse(...) +
  apply_rerank(...) from the inlined search() body (service.py:457-545).
  Step 2: /preflight-check the new plan.
  Step 3: /be-execute. Gate: make check-full + knowledge route tests + RAG
  eval delta ≤3pp.

  ─────────────────────────────────────────────────────────────────────────
  12. Session 15 — Figma typed boundaries (F014)
  ─────────────────────────────────────────────────────────────────────────
  [WRITE PLAN FIRST] .agents/plans/tech-debt-15-figma-typed-boundaries.md does
    not exist.
  [STATE] ❌ Untouched — `app/design_sync/figma/service.py` is now 1758 LOC (grown from 1454); no `raw_types.py` next to it.
  Branch refactor/tech-debt-15-figma-typed-boundaries.
  Step 1: /be-planning — produce tech-debt-15-figma-typed-boundaries.md
  covering split of _parse_node (app/design_sync/figma/service.py:1239-1454,
  216 LOC) and _parse_variables (:683-846, 164 LOC) into
  _parse_visual_props / _parse_text_props / _parse_layout_props, and a new
  app/design_sync/figma/raw_types.py with TypedDicts for the Figma JSON
  boundary. Target: eliminate 125 Any references + 7 # type: ignore.
  Step 2: /preflight-check the new plan.
  Step 3: /be-execute. Gate: make types + make converter-data-regression
  unchanged.

  ─────────────────────────────────────────────────────────────────────────
  13. Session 16 — Frontend test types + middleware default-deny (F051, F068)
  ─────────────────────────────────────────────────────────────────────────
  [EXTEND PLAN] .agents/plans/tech-debt-09c-ts-strict-tests.md exists;
    add F051 + F068 sections.
  [STATE] ❌ Untouched — `cms/apps/web/middleware.ts` returns `NextResponse.next()` when `getRouteKey(...)` is null; unknown routes are still implicitly allowed. F068 split of `use-data-hooks{,-2,-3}.test.ts` not started.
  Branch refactor/tech-debt-09c-fe-test-types.
  Step 1: /fe-planning --extend tech-debt-09c-ts-strict-tests.md — add a
  section for F051 (cms/apps/web/middleware.ts:7-21,53-72 default-deny for
  routes not in ROLE_PERMISSIONS, log the catch) and F068 (split
  use-data-hooks{,-2,-3}.test.ts — 615+715+990 LOC numbered split — into
  co-located per-hook files with shared __tests__/setup.ts).
  Step 2: /preflight-check the extended plan.
  Step 3: /fe-execute. Gate: make check-fe + a middleware test asserting
  unknown route 403'd.

  ─────────────────────────────────────────────────────────────────────────
  14. Session 17 — Connector + QA test gaps (F065, F066, F067)
  ─────────────────────────────────────────────────────────────────────────
  [EXTEND PLAN] .agents/plans/tech-debt-04-connector-dedup.md +
    .agents/plans/tech-debt-06-custom-checks-split.md exist; add coverage sections.
  [STATE] ⚠️ Partial — F066 effectively shipped: `app/connectors/tests/` already has `test_braze_service.py`, `test_sfmc_service.py`, `test_adobe_service.py`, `test_taxi_service.py`. F065 (`test_converter_service.py` covering `_convert_with_components` matrix) not present — only the regression/insights/memory/traces variants exist. F067 (`app/qa_engine/tests/test_checks.py` 1935 LOC) not split. Rescope to F065 + F067 only.
  Branch test/tech-debt-17-connector-qa-coverage.
  Step 1: /be-planning --extend both plans — F065 (add
  app/design_sync/tests/test_converter_service.py covering the
  _convert_with_components branch matrix: sibling/tree/custom-comp/verify
  on×off), F066 (per-service connector tests test_braze_service.py,
  test_sfmc_service.py, test_adobe_service.py, test_taxi_service.py
  covering 401 retry / lease failure / malformed JSON / KeyError — use
  the integration harness from Cluster C for DB-bound flows), F067 (split
  app/qa_engine/tests/test_checks.py — 1944 LOC — per-check mirroring
  app/qa_engine/checks/).
  Step 2: /preflight-check the extended plans.
  Step 3: /be-execute. Gate: make check-full + per-check coverage gate green.

  ─────────────────────────────────────────────────────────────────────────
  15. Cluster D — LEGO promotion + physical-card detector follow-up
  ─────────────────────────────────────────────────────────────────────────
  [PLAN EXISTS] .agents/plans/phase-50.8-lego-promotion-and-detector-followup.md
  [STATE] ❌ Untouched — `data/debug/` holds only `5/`, `6/`, `10/`, `manifest.yaml`, `reframe/`. No LEGO / performance_reimagined / slate fixtures yet.
  Branch phase/50.8-lego-promotion.
  Step 1: /preflight-check the plan.
  Step 2: /be-execute Phase α — extract structure.json + tokens.json for
  LEGO (node 2833-1869), performance_reimagined, slate via
  diagnose.extract; promote into data/debug/<N>/; add manifest rows; LEGO
  row carries expectations.sections[16].is_physical_card_surface: true.
  Run make converter-data-regression (38 → 41 passing).
  Step 3: only if LEGO §16 fails — execute Phase β: bounded recursive
  _walk_logo_candidates (gap-2); relax inner_bg gate (gap-3, option a or
  b per LEGO structure.json).
  Close all 4 deferred entries. Gate: make converter-data-regression +
  make golden-conformance.

  ─────────────────────────────────────────────────────────────────────────
  16. Cluster E — Restore pyright reportDeprecated = "error"
  ─────────────────────────────────────────────────────────────────────────
  [PLAN EXISTS] .agents/plans/tech-debt-pyright-deprecation-restore.md
  [STATE] ❌ Untouched — `pyproject.toml:325` still `reportDeprecated = "warning"`.
  Branch tech-debt/pyright-restore-deprecated.
  Step 1: /preflight-check the plan.
  Step 2: /be-execute Path 1 — bump pyright + drop the warning demotion at
  pyproject.toml:324; run make types.
  Step 3: only if Path 1 fails — execute Path 2: rewrite the 3
  AsyncIterator returns at app/core/database.py:41,
  app/core/scoped_db.py:131, app/main.py:71 to AsyncGenerator[T, None];
  re-run; restore reportDeprecated = "error".
  Close phase-deps-pyright-asynccontextmanager-deprecation.
  Gate: make types.

  ─────────────────────────────────────────────────────────────────────────
  17. Session 19 — Backend sweep (F033/F035/F049/F057/F059/F060/F061/F070)
  ─────────────────────────────────────────────────────────────────────────
  [WRITE PLAN FIRST] .agents/plans/tech-debt-19-backend-sweep.md does not exist.
  [STATE] ⚠️ Partial — F061 already done (`app/shared/color.py` exists). `.env.example` exists (F033 needs only the CI parity check). `cms/packages/sdk/openapi.json` exists (F049 needs only the live-API diff CI gate). F035 / F057 / F059 / F060 / F070 untouched: 5 trace files (`converter_traces.py`, `converter_insights.py`, `converter_memory.py`, `correction_tracker.py`, `converter_regression.py`) still separate; `app/ai/agents/base.py:80,170,251,328,329,331,405,412,553` still uses `getattr(request, ...)`.
  Branch chore/tech-debt-19-backend-sweep.
  Step 1: /be-planning — produce tech-debt-19-backend-sweep.md covering
  F033 (.env.example from Pydantic Settings + CI parity check), F035
  (DESIGN_SYNC__* flag cull to ≤30; drop flags untouched >180 days), F049
  (SDK CI gate diffing live OpenAPI from booted backend vs.
  cms/packages/sdk/openapi.json), F057 (make db-squash on a maintenance
  window — runs on the post-Cluster-B clean schema), F059 (route exception
  logging through structlog; disable engine.echo in dev or pipe through
  redact_event_dict), F060 (unify app/design_sync/{converter_traces,
  converter_insights,converter_memory,correction_tracker,
  converter_regression}.py into one traces/ subpackage with a single
  TraceWriter), F061 (extract app/shared/color.py — hex→RGB, brightness,
  distance — from deliverability_analyzer / repair/brand / converter),
  F070 (define AgentRequest(Protocol) with output_mode / effective_tier /
  client_id; remove getattr(request, …, default) at
  app/ai/agents/base.py:74,358,365).
  Step 2: /preflight-check the new plan.
  Step 3: /be-execute. Gate: make check-full.

  ─────────────────────────────────────────────────────────────────────────
  18. Session 20 — Frontend / repo sweep (F050, F063)
  ─────────────────────────────────────────────────────────────────────────
  [WRITE PLAN FIRST] .agents/plans/tech-debt-20-frontend-sweep.md does not exist.
  [STATE] ❌ Untouched — `cms/apps/web/src/types/css-compiler.ts` header still says *"TODO: Replace with SDK re-exports after `make sdk` regeneration."* `.gitignore` (a) vs (b) decision still pending.
  Branch chore/tech-debt-20-frontend-sweep.
  Step 1: /fe-planning — produce tech-debt-20-frontend-sweep.md covering
  F050 (finish SDK re-export of cms/apps/web/src/types/css-compiler.ts —
  last hand-written file in the trio; outlook.ts/chaos.ts already done)
  and F063 (resolve .gitignore blanket-ignore decision: option (a)
  data/debug/*/* blanket-ignore + ! exceptions for the 5 curated fixture
  types, OR (b) declare current pattern final via refreshed line-113
  comment; rotate TODO-completed.md; archive plans older than active phase).
  Step 2: /preflight-check the new plan.
  Step 3: /fe-execute. Gate: make check-fe.

  Plan-state summary (post-2026-05-08 verification):
  - ✅ Already done — 2 sessions: 1 (F013-D3 shims gone, docs-only PR remains), 7 (F043 @ts-nocheck count is 0).
  - ⚠️ Partial / rescope — 5 sessions: 5 (drop F036), 6 (test file exists, harness missing), 8 (771 → 390 LOC, finish to ≤200), 14 (drop F066), 17 (drop F061; F033/F049 only need CI gate).
  - ❌ Untouched — 11 sessions: 2, 3, 4, 9, 10, 11, 12, 13, 15, 16, 18.

## Plan dependency graph

```
0 (audit refresh)
  └─ 1 (multi-tenant scoping) ── 2 (RLS retirement)
       └─ 3 (proxy security)
            └─ 4 (auth cluster)         ← TIER-1 STOP POINT (tag release)
                 └─ 5 (RenderContext)
                      └─ 6 (_convert_with_components)
                           └─ 7 (instrument shims) ─ ─ 2 weeks ─ ─ 18 (remove shims)
                                └─ 8 (facade deletion)
                                     └─ 9 (workspace decomposition)
                                          └─ 10–17 (fan out, parallel-safe)
                                               └─ 19, 20 (sweep)
```

## Verification protocol per session

Every session ends with:
1. `make check-full` (backend) or `make check-fe` (frontend) green
2. New regression test asserting the finding-specific behavior
3. PR description references the F00N IDs closed
4. Inline `**RESOLVED** (<commit>, <plan ref>)` annotation in `TECH_DEBT_AUDIT.md`, in the same PR
5. Sessions 5–8 also require `make rendering-regression` zero-diff against pre-session baseline

## Sub-plan creation rule

Lazy. New sub-plans (sessions 11, 12, 13, 14, 15, 19, 20) are written one session before their execution, not preemptively. The meta-plan is the index; each sub-plan inherits scope from the row above. Reasons:

- Plan stubs drift; better to write fresh against current `main` at execution time.
- 7 new plan files would add ~3500 LOC of speculative content before any code lands.
- Per project rule: plans cap at 700 LOC each; this meta-plan is the routing layer.

## Out of scope

- Decisions in "Things That Look Bad But Are Actually Fine" — the audit already justified each.
- `.agents/deferred-items.json` Phase 50.7 LEGO entries — different lineage from F00N findings, tracked separately under `.claude/rules/deferred-items.md`.
- Repo housekeeping beyond F063 (rotating `TODO-completed.md`, archiving plans older than the active phase).
- F018 / F019 verification beyond confirming the files exist on disk (already done in Phase 1 evidence column).

## Hand-off

**Next session: 1** (Multi-tenant repo scoping). Session 0 ran on 2026-05-04: `TECH_DEBT_AUDIT.md` doc refresh landed; `.gitignore` flip for F063 closure deferred to a future micro-session pending maintainer affirmation of approach (a) vs. (b). Session 20 ran on 2026-05-13 with maintainer affirmation of approach (a): blanket `data/debug/*/*` ignore + 5 `!` exceptions for curated types. Untracked `design.png` + `design_meta.json` files surfaced during preflight and were initially folded into the exception list as a presumed 6th/7th type; during execute, grep confirmed they are regenerable Figma exports (`service.py:229`, `diagnose/extract.py:146/316`) and were dropped — they stay IGNORED via the blanket pattern. F050 + F063 closed fully.
