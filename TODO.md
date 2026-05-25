# [REDACTED] Email Innovation Hub — Implementation Roadmap

> Derived from `[REDACTED]_Email_Innovation_Hub_Plan.md` Sections 2-16
> Architecture: Security-first, development-pattern-adjustable, GDPR-compliant
> Pattern: Each task = one planning + implementation session

---

> **Completed phases (0–49):** See [docs/TODO-completed.md](docs/TODO-completed.md)
>
> Summary: Phases 0-10 (core platform, auth, projects, email engine, components, QA engine, connectors, approval, knowledge graph, full-stack integration). Phase 11 (QA hardening — 38 tasks, template-first architecture, inline judges, production trace sampling, design system pipeline). Phase 12 (Figma-to-email import — 9 tasks). Phase 13 (ESP bidirectional sync — 11 tasks, 4 providers). Phase 14 (blueprint checkpoint & recovery — 7 tasks). Phase 15 (agent communication — typed handoffs, phase-aware memory, adaptive routing, prompt amendments, knowledge prefetch). Phase 16 (domain-specific RAG — query router, structured ontology queries, HTML chunking, component retrieval, CRAG validation, multi-rep indexing). Phase 17 (visual regression agent & VLM-powered QA). Phase 18 (rendering resilience & property-based testing). Phase 19 (Outlook transition advisor & email CSS compiler). Phase 20 (Gmail AI intelligence & deliverability). Phase 21 (real-time ontology sync & competitive intelligence). Phase 22 (AI evolution infrastructure). Phase 23 (multimodal protocol & MCP agent interface — 197 tests). Phase 24 (real-time collaboration & visual builder — 9 subtasks). Phase 25 (platform ecosystem & advanced integrations — 15 subtasks). Phase 26 (email build pipeline performance & CSS optimization — 5 subtasks). Phase 27 (email client rendering fidelity & pre-send testing — 6 subtasks). Phase 28 (export quality gates & approval workflow — 3 subtasks). Phase 29 (design import enhancements — 2 subtasks). Phase 30 (end-to-end testing & CI quality — 3 subtasks). Phase 31 (HTML import fidelity & preview accuracy — 8 subtasks). Phase 32 (agent email rendering intelligence — 12 subtasks: centralized client matrix, content rendering awareness, import annotator skills, knowledge lookup tool, cross-agent insight propagation, eval-driven skill updates, visual QA feedback loop, MCP agent tools, skill versioning, per-client skill overlays). Phase 33 (design token pipeline overhaul — 12 subtasks). Phase 34 (CRAG accept/reject gate — 3 subtasks). Phase 35 (next-gen design-to-email pipeline — 11 subtasks: MJML compilation, tree normalizer, MJML generation, section templates, AI layout intelligence, visual fidelity scoring, correction learning loop, W3C design tokens, Figma webhooks, section caching). Phase 36 (universal email design document & multi-format import hub — 7 subtasks: EmailDesignDocument JSON Schema, converter refactor, Figma/Penpot adapters, MJML import, HTML reverse engineering, Klaviyo + HubSpot ESP export). Phase 37 (golden reference library for AI judge calibration — 5 subtasks: expand golden component library with VML/MSO/ESP/innovation templates, reference loader & criterion mapping, wire into judge prompts, re-run pipeline & measure improvement, complete human labeling). Phase 38 (pipeline fidelity fix — 8 subtasks). Phase 39 (pipeline hardening — 7 subtasks). Phase 40 (converter snapshot & visual regression testing — 7 subtasks). Phase 41 (converter bgcolor continuity + VLM classification — 7 subtasks). Phase 42 (HTTP caching, smart polling & data fetching hardening — 7 subtasks). Phase 43 (judge feedback loop & self-improving calibration). Phase 44 (workflow hardening, CI gaps & operational maturity — 12 subtasks). Phase 45 (scheduling, notifications & build debounce — 6 subtasks). Phase 46 (provider resilience & connector extensibility — 5 subtasks: credential pool with rotation/cooldowns, LLM key rotation, ESP key rotation, credential health dashboard, dynamic ESP connector discovery via plugin system). Phase 47 (VLM visual verification loop & component library expansion — 10 subtasks: section screenshot cropping, VLM section-by-section diff, deterministic correction applicator, verification loop orchestrator, pipeline integration, component gap analysis 89→150+, extended matcher scoring, custom component generation AI fallback, verification tests, diagnostic trace enhancement; fidelity ladder: 85%→93%→97%→99%). Phase 48 (agent pipeline DAG, adversarial quality loops & cross-repo pattern adoption — 13 subtasks: pipeline DAG schema + template registry, parallel agent executor, typed artifact protocol, adversarial evaluator agent, quality contracts and stage gates, EmailTree JSON schema, scaffolder tree-mode generation, deterministic tree compiler, QA meta-evaluation framework, synthetic adversarial email generator, MCP response caching + schema compression, knowledge-graph proactive QA pipeline, agent execution hook system with profiles). Phase 49 (design-sync converter structural fidelity — 9 subtasks: sibling pattern detector, repeating-group renderer, section-to-component classification improvements, token override element-type expansion, per-node slot content extraction fidelity, per-email token scoping from shared Figma files, CTA fidelity button color/shape extraction, design-sync → EmailTree bridge, data-driven converter regression framework).

---

## Phase 50 — Tech Debt Closeout & Audit Reconciliation (4/11 subtasks)

Final closure of the remaining tech-debt audit items, plus reconciliation of the stale `TECH_DEBT_AUDIT.md` doc against current `main`. Sessions 1–20 closed 53 of 70 findings; the audit table still marks 17 of those false-OPEN because the doc lagged the merges. Of the 17 audit-OPEN findings, 13 are fully shipped in code (flip to RESOLVED), 4 are still real work (F025 not started; F042/F057/F066 partial). Phase 50 closes those 4 + refreshes the doc + drains the deferred-items ledger. Phase 51 (AI security pass) starts after Phase 50 lands so the planning baseline is clean.

### Execution order

§50.1–§50.4 are shipped. The remaining work is **six grabbable, self-contained sub-phases**. Each lists its plan path + start signal + done signal so a fresh session can pick one off the list and execute end-to-end without prior context. Pick them off the table top-down.

| # | Subtask | State | Plan | Effort | Parallel-safe with | Blocks |
|---|---------|-------|------|--------|--------------------|--------|
| A | **§50.6.1 — Memory embedding stub** | `[Plan Ready]` | `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.1 | ~30min | B, C, D, E, F | — |
| B | **§50.6.2 — Briefs BOLA isolation test** | `[Plan Ready]` | `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.2 | ~45min | A, C, D, E, F | — |
| C | **§50.6.3 — Squawk Python-migrations cleanup** | `[Plan Ready]` | `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.3 | ~1h | A, B, D, E, F | — |
| D | **§50.6.4 — DESIGN_SYNC__* flag cull (split PR-1/PR-2)** | `[Plan Ready]` | `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.4 | ~2h | A, B, C, E, F | — |
| E | **§50.7 — Squash Multi-DB Redesign** | `[Plan Ready]` | `.agents/plans/tech-debt-19-squash-multi-db-redesign.md` | ~½d | A, B, C, D | §50.5 |
| F | **§50.5 — Execute Migration Squash** | `[BLOCKED on §50.7]` | `.agents/plans/tech-debt-19-runbook-db-squash.md` | ~2.5h + maintenance window | — | — |

§50.8 is **dropped from the active list** — its purpose was to add a tripwire while §50.7 was in flight; §50.7's PR removes the tripwire as part of landing, so adding it now is net-zero. Header `[SKIP]` left in place for traceability.

After Phase 50 drains, Phase 51 (Agentic Security Hardening — 7 `[Plan Ready]` subtasks) opens. Phase 51 is a separate workstream and not blocked by anything in Phase 50.

### Shipped

| § | Subtask | Commit | Note |
|---|---------|--------|------|
| 50.1 | Audit refresh | `4602430e` | 13 false-OPEN findings flipped to RESOLVED in `TECH_DEBT_AUDIT.md`. |
| 50.2 | F025 eval runner registry | `0ecc6b65` | 9-branch if-ladder → `dict[AgentName, AgentSpec]` registry in `app/ai/agents/evals/runner.py`. On `refactor/tech-debt-13b-eval-runner-registry`. |
| 50.3 | F042 workspace hooks | `bff50b12` | Nine workspace hooks under `cms/apps/web/src/hooks/workspace/`; page.tsx is composition shell. |
| 50.4 | F066 Braze/Taxi connector tests | `cf231b09` | `app/connectors/{braze,taxi}/tests/test_*.py` cover 401 retry + lease failure. On `tech-debt/phase-50-followups`. |

### 50.1 Audit Refresh (Session 0) `[Backend, Documentation]` `[RESOLVED]`

**Resolved in commit `4602430e`** — `TECH_DEBT_AUDIT.md` rows updated + `.agents/plans/tech-debt-00-status-and-roadmap.md:48` refreshed.

Doc-only PR. Flipped 13 false-OPEN findings in `TECH_DEBT_AUDIT.md` to `**RESOLVED**` with commit citations. Removed the stale-signal problem that had been forcing every planning session to re-verify status against `main`.

**Findings to flip (13):**
- **F014** Figma typed boundaries — `app/design_sync/figma/raw_types.py` + `_parse_visual_props` (`figma/service.py:554`), `_parse_text_props` (`:465`), `_parse_layout_props` (`:381`)
- **F038** Scheduling leader-lock fencing — UUID identity at `app/scheduling/engine.py:46,100`
- **F039** Scheduling inline awaits — `asyncio.create_task` at `app/scheduling/engine.py:186`
- **F045** Frontend token cache 401 invalidation — `clearTokenCache()` wired at `cms/apps/web/src/lib/sdk.ts:27-28`
- **F049** SDK drift CI gate — `make sdk-check` target + `scripts/export-openapi.py --live` + `.github/workflows/ci.yml` `sdk-check` job (commit `bd36239b`)
- **F052** KnowledgeService god class split — `app/knowledge/services/{graph,ingestion,search,tags}.py`; `service.py` 1048 → 53 LOC
- **F053** RRF + rerank extraction — `app/knowledge/fusion.py`
- **F055** Repair pipeline stage rollback — snapshot revert at `app/qa_engine/repair/pipeline.py:67-74`
- **F060** Trace module consolidation — `app/design_sync/traces/` package (commit `ee7093b3`)
- **F061** Color util extraction — `app/shared/color.py` with 7+ consumers
- **F065** Untested converter orchestrator — `app/design_sync/tests/test_converter_service.py` exists
- **F067** QA check test split — no monolithic `test_checks.py`; per-check files in `app/qa_engine/tests/test_*.py`
- **F070** AgentRequest Protocol — `app/ai/agents/base.py` (commit `bd36239b`)

**Findings to mark PARTIAL (4, remaining work scoped to 50.2–50.5):**
- **F025** still OPEN — see 50.2
- **F042** partial (390/771 LOC, 1 of 4 hooks) — see 50.3
- **F057** partial (runbook shipped, execution pending) — see 50.5
- **F066** partial (SFMC/Adobe done, Braze/Taxi pending) — see 50.4

**Plan:** None needed (doc-only).
**Deliverable:** Updated `TECH_DEBT_AUDIT.md` rows + 1-line refresh of `tech-debt-00-status-and-roadmap.md:48`.
**Verify:** `git diff` shows doc-only changes; `pre-commit` passes; spot-check 2-3 RESOLVED annotations against the cited commit SHAs.
**Effort:** ~1h.

### 50.2 F025 — Eval Runner Registry `[Backend]` `[RESOLVED]`

**Resolved in commit `0ecc6b65`** (on branch `refactor/tech-debt-13b-eval-runner-registry`, awaiting PR).

Replaced the 9-branch if-ladder in `app/ai/agents/evals/runner.py` with a `dict[AgentName, AgentSpec]` registry + shared `_run_case` template. Net ~200 LOC reduction. Tests at `app/ai/agents/evals/tests/test_runner_registry.py` cover `AGENT_REGISTRY` ↔ `AGENT_NAMES` symmetry, callable specs, canonical trace shape. JSONL trace shape unchanged. Plan: `.agents/plans/tech-debt-13b-eval-runner-registry.md`.

### 50.3 F042 — Workspace Page Hook Extraction Completion `[Frontend]` `[RESOLVED]`

**Resolved in commit `bff50b12`** (Plan 09 §B). All planned hooks landed under `cms/apps/web/src/hooks/workspace/`: `use-workspace-template.ts`, `use-workspace-dialogs.ts`, `use-workspace-follow-mode.ts`, plus `use-agent-mode.ts`, `use-editor-state.ts`, `use-auto-compile.ts`, `use-workspace-actions.ts`, `use-workspace-export-actions.ts`, `use-workspace-qa.ts`. `page.tsx` consumes all nine and contains zero god-component anti-patterns — no `useEffect` chains, all `useState` collapsed into hooks, render tree is pure prop-passing into 5 sub-components (`WorkspaceToolbar`, `WorkspaceMainPanels`, `WorkspaceRightRail`, `WorkspaceDialogs`, `CommandPalette`).

`page.tsx` sits at 390 LOC rather than the original <200 LOC target, but the residual length is JSX prop-wiring on a composition shell, not god-component logic. The <200 LOC bar was a proxy for the underlying anti-pattern, which is gone. Tests for all five planned hooks exist in `cms/apps/web/src/hooks/workspace/__tests__/`.

### 50.4 F066 — Braze + Taxi Per-Service Connector Tests `[Backend, Testing]` `[RESOLVED]`

**Resolved in commit `cf231b09`** (on branch `tech-debt/phase-50-followups`, awaiting PR).

Added `app/connectors/braze/tests/test_braze_service.py` + `app/connectors/taxi/tests/test_taxi_service.py` covering 401 → lease evict + retry once → success. Closes F066. Mirrors the existing SFMC/Adobe per-service test shape from `.agents/plans/tech-debt-04-connector-dedup.md:245-248`.

### 50.5 F057 — Execute Migration Squash `[Backend, Database]` `[BLOCKED — design flaw]`

> ⚠️ **DO NOT RUN `make db-squash`.** The squash scripts and the runbook share a latent design flaw: `alembic revision --autogenerate` runs against the populated DB, where `target_metadata` already matches the live schema, so the generated baseline's `upgrade()` body is empty (`pass`). Production DB cutover would succeed deceptively, but the next fresh-DB bootstrap (CI, onboarding, DR restore) creates no schema and the app crashes on first request. See `.agents/deferred-items.json` → `tech-debt-19-squash-empty-baseline` for the empirical reproduction and the multi-DB redesign sketch.

Squash 46 alembic migrations to a single baseline using `make db-squash`. Runbook + dry-run script shipped in `8aa83103`. Requires production maintenance window — coordinate with deployment cadence. Drop the `alembic/versions/2eb1d5b05ad3_merge_heads.py` merge artifact in the same operation.

**Prerequisite:** §50.7 (F057a — Squash Multi-DB Redesign) must ship and close `tech-debt-19-squash-empty-baseline` before this phase can be unblocked.
**Plan:** ⚠️ `.agents/plans/tech-debt-19-runbook-db-squash.md` + `scripts/squash-migrations-dryrun.sh` — design-broken (see warning above); needs redesign per §50.7 before execution.
**Deliverable:**
- New consolidated baseline migration in `alembic/versions/` (single `down_revision = None` file)
- 46 historical migrations deleted (or archived per runbook)
- `alembic heads` reports single head; `alembic upgrade head` clean on fresh DB
- Operator postmortem in `docs/migrations/` noting cutover SHA + restoration procedure
**Verify:** Dry-run: `bash scripts/squash-migrations-dryrun.sh` on staging DB clone shows zero schema drift vs HEAD. Execute: maintenance-window cutover with rollback plan (restore from snapshot). Post-cutover: `make db-migrate` on empty DB succeeds; existing prod DB applies baseline as no-op.
**Effort:** ~1h in maintenance window + ~1h staging dry-run + ~30m post-verification.

### 50.6 Deferred-Items Ledger Cleanup `[Backend, Testing]` `[Plan Ready — split into 4 grabbable subtasks]`

Close the four open entries in `.agents/deferred-items.json`. Each entry's `closes_when` field is the spec; entries are load-bearing memory and worth draining. **Each subtask below is independently grabbable** — pick one and execute in a fresh context.

**Master plan:** ✅ `.agents/plans/tech-debt-19-deferred-items-cleanup.md` (198 lines — recommended sub-order, per-item tasks with file lists + acceptance criteria, decision tree for the squawk item).

#### 50.6.1 Memory Isolation Embedding Stub `[Plan Ready]` `[~30min]`

**Plan:** `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.1.
**Deferred entry:** `tech-debt-03-memory-isolation-embedding-stub`.
**Start signal:** clean branch checked out off `main`.
**What:** Add `embedding_stub` fixture in `app/tests/conftest.py` returning a deterministic zero-vector (dim 1536 per `app/knowledge/embedding.py:177`). Drop `@pytest.mark.xfail` on the Memory parametrise in `app/tests/test_tenant_isolation.py`; thread the new fixture in.
**Done signal:** `uv run pytest app/tests/test_tenant_isolation.py -k memory -v` passes without xfail; `make check` green; deferred entry flipped to `closed` with `closed_commit`.

#### 50.6.2 Briefs BOLA-by-Creator Isolation Test `[Plan Ready]` `[~45min]`

**Plan:** `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.2.
**Deferred entry:** `tech-debt-03-briefs-user-isolation-test`.
**Start signal:** clean branch checked out off `main`. Read `app/projects/tests/test_bola.py` first — that is the reference pattern to mirror.
**What:** Create `app/briefs/tests/test_user_isolation.py` covering user A creates brief → user B (same org) cannot read/update/delete via route OR repository. Explicitly assert that same-org-different-user is the contrast case (briefs are per-creator, not org-scoped).
**Done signal:** new test file passes; route + repository layers both exercised; same-org case in assertions; `make check` green; deferred entry flipped.

#### 50.6.3 Squawk Python-Migrations Decision + Cleanup `[Plan Ready]` `[~1h]`

**Plan:** `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.3.
**Deferred entry:** `tech-debt-squawk-python-migrations`.
**Start signal:** clean branch + **decision made on Option (a) vs (b)** (plan recommends (b) absent evidence of migration bugs slipping through).
**What — Option (b) (recommended):** Remove squawk hook from `.pre-commit-config.yaml:94`. Drop squawk job from `.github/workflows/ci.yml`. Update `Makefile` `migration-lint` target (remove or no-op). Strip `# squawk-ignore` comments from `alembic/versions/normalize_schema_drift.py`. Add manual-review guidance to `.claude/rules/architecture.md` or new `.claude/docs/migration-safety.md`.
**Done signal:** no more misleading "passing" advisory in CI; either real Python-aware linter exists (a) or gap is documented (b); `make check` green; deferred entry flipped.

#### 50.6.4 DESIGN_SYNC__* Flag Cull (PR-1 only this subtask) `[Plan Ready]` `[~2h]`

**Plan:** `.agents/plans/tech-debt-19-deferred-items-cleanup.md` §50.6.4.
**Deferred entry:** `tech-debt-19-design-sync-flag-cull-deeper`.
**Start signal:** clean branch. Read `app/core/config/design_sync.py` (62 fields) + `feature-flags.yaml` and classify each field as (constantize) / (retire-feature) / (keep).
**Scope split — important:** This subtask delivers **PR-1 (constantize set only)** — additive, no behavior change, no test deletion. PR-2 (retire-feature set) is a separate follow-up subtask gated on PR-1 merging — leave a new deferred-items entry pointing at the retire-feature candidate list when PR-1 ships.
**What — PR-1:** For each (constantize) field: move to a `Final` constant in `app/design_sync/tuning.py`, update consumers, delete the config field. Add bounded-count regression test in `app/core/tests/test_config_design_sync.py` (`assert len(DesignSyncConfig.model_fields) <= 45`). Do NOT touch any (retire-feature) candidates this round.
**Done signal:** `len(DesignSyncConfig.model_fields)` between 45 and 50 (~15-17 fields constantized); `make flag-audit` clean; `make check-full` green; new deferred entry created for PR-2.

**Done signal for §50.6 overall:** all four sub-entries `closed` in `.agents/deferred-items.json` + a new entry exists for the §50.6.4 PR-2 retire-feature work.

### 50.7 F057a — Squash Multi-DB Redesign `[Backend, Database]` `[Plan Ready]`

Prerequisite for §50.5. Rewrite the squash flow shared by `scripts/squash-migrations.sh`, `scripts/squash-migrations-dryrun.sh`, and the runbook to separate the "schema source" DB from the "autogenerate target" DB so the generated baseline contains `CreateTable` for every model (currently empty `pass`). Closes deferred entry `tech-debt-19-squash-empty-baseline`.

**Plan:** ✅ `.agents/plans/tech-debt-19-squash-multi-db-redesign.md` (146 lines — three-DB design, file-by-file change list, acceptance criteria, risks).
**Deliverable:**
- `scripts/squash-migrations-dryrun.sh` rewritten to use three throwaway containers (reference, autogenerate target, validation) + inline `op.create_table` count assertion + end-to-end `pg_dump` parity check.
- `scripts/squash-migrations.sh` (destructive sibling) rewritten to autogenerate against an ephemeral empty container instead of production. Production stays untouched until the final stamp.
- `.agents/plans/tech-debt-19-runbook-db-squash.md` procedure step 5 updated; ⚠️ BLOCKED callout removed.
- `.agents/deferred-items.json` → `tech-debt-19-squash-empty-baseline` flipped to `closed`.
- `TECH_DEBT_AUDIT.md` F057 row updated from `BLOCKED` to `READY`.
**Verify:** `bash scripts/squash-migrations-dryrun.sh` exits 0 end-to-end; `grep -c "op.create_table"` on generated baseline equals `len(Base.metadata.tables)`; `diff schema_A.sql schema_C.sql` empty; `make check-full` green.
**Effort:** ~½d (script rewrites + runbook + end-to-end dry-run).

### 50.8 F057b — Squash Defense-in-Depth `[Backend, DevOps]` `[SKIP — superseded by §50.7]`

Plan kept on disk for historical reference (`.agents/plans/tech-debt-19-squash-defense-in-depth.md`), but **do not execute**. Rationale: the tripwire's purpose is to block accidental `make db-squash` execution *while* §50.7 is in flight. §50.7's own PR removes the tripwire as part of landing — adding it now is net-zero churn and would be reverted in the very next PR.

**Re-open this only if:** §50.7 slips past a date someone is actively planning a maintenance window for, AND there is a credible risk an operator runs the destructive script before §50.7 ships. Neither condition currently applies.

---

## Phase 51 — Agentic Security Hardening (0/7 subtasks)

Close the seven gaps between the existing G1–G5 envelope (commit `3f96ceb5`, Apr 25 2026 — `app/ai/agents/base.py`, `app/ai/agents/audit.py`) and the architectural mandates in `docs/security/agentic-defense-in-depth.md`. G1–G5 ships sanitization, USER_INPUT delimiter, in-process kill flag, token+time caps, and a single audit line — necessary but not sufficient for the Autonomous AI Trifecta: `Risk = (Autonomy × Power) / Assurance`. Power grew Phase 45–50 (cron jobs in `app/scheduling/`, plugin connectors in `app/plugins/`, VLM verify loop in `app/design_sync/visual_verify.py`, custom-component generation in `app/design_sync/custom_component_generator.py`, full-design PNG pipeline in 50.1) — assurance must catch up via control planes that bypass the model's interpretation loop entirely.

**Plan:** ✅ `.agents/plans/51-agentic-security-hardening.md` (full spec, all 7 subtasks scoped).
**Order:** Strict serial — each subtask builds on the previous chain head. Parallel execution forbidden until 51.4 ships (the audit chain is the dependency for 51.7's `ai.agent_killed` entries).
**Rollout:** All 7 ship behind `SECURITY__*` feature flags for progressive enable without redeploy.
**Non-negotiables:**
- No regressions to G1–G5. New layers wrap, never replace.
- Default-deny on policy ambiguity (51.5).
- Per-action security overhead ≤ 50ms p95 (excluding HITL waits in 51.6); new `make bench` case `bench_security_envelope`.
- Calibration gate (`make eval-calibration-gate`) within 5pp after each subtask.
- Existing 2037+ `app/ai` tests must pass after each subtask.
- ≥ 80 new tests across the 7 subtasks.
**Effort:** ~10–14 dev-days total.

### 51.1 Credential Revocation on Kill `[Backend, Security]` `[Plan Ready]`

When the kill switch trips, immediately revoke all credentials held by the offending agent via `app/core/credentials.py::revoke_for_agent()` (already exists at `:301`). Audit chain entry on revocation. Closes the failure mode where `SECURITY__DISABLED_AGENTS` is checked by the same process running the offending loop — if that process is hung or OOM, the in-band check never fires.

**Plan:** §51.1 of `.agents/plans/51-agentic-security-hardening.md`.
**Deliverable:**
- Hook `revoke_for_agent()` into kill-switch trip path (find call site of `SECURITY__DISABLED_AGENTS` check; emit revocation alongside the deny)
- New `SECURITY__REVOKE_ON_KILL_ENABLED` flag (default `true`) in `app/core/config/security.py`
- Audit chain entry: `ai.agent_credentials_revoked` event with agent_id + reason + revoked_credential_ids
- Tests in `app/core/tests/test_credentials_revocation.py` extending existing suite — kill→revoke→retry-blocked path
**Verify:** `uv run pytest app/core/tests/test_credentials_revocation.py -v` + `make check`.
**Reduces:** Power axis when assurance signals breach.
**Effort:** ½d.

### 51.2 Safe Compaction — Pinned Safety Instructions `[Backend, Security]` `[Plan Ready]`

OpenClaw-class fix: when the context window slides or compacts, pin the system prompt + safety constraints so they never drop. Apply to all blueprint engine sliding-window operations and any agent service that does conversational compaction. Tests verify safety instructions persist after simulated compaction events.

**Plan:** §51.2 of `.agents/plans/51-agentic-security-hardening.md`.
**Deliverable:**
- `app/ai/security/safe_compaction.py` — `PinnedPrompt` wrapper that carries safety constraints through compaction operations
- Integration into `BaseAgentService.process` envelope so all 9 agents inherit it
- Integration into `BlueprintEngine` for cross-node memory sliding
- New `SECURITY__SAFE_COMPACTION_ENABLED` flag (default `true`)
- Property test: 10k random compaction events, safety instruction count must stay ≥1 in every output
**Verify:** New test file `app/ai/security/tests/test_safe_compaction.py` (~15 tests) + `make eval-calibration-gate` no regression.
**Reduces:** Assurance failure mode where the in-band check disappears mid-loop.
**Effort:** 1–2d.

### 51.3 Tool-Call Cap + Planning Telemetry `[Backend, Security]` `[Plan Ready]`

Add `SECURITY__AGENT_MAX_TOOL_CALLS` deterministic circuit breaker — closes the K_max trio with the existing `AGENT_MAX_RUN_SECONDS` time cap and `AGENT_MAX_TOTAL_TOKENS` token cap. Capture intermediate reasoning steps as structured telemetry per planning step. Hook into `BlueprintEngine._execute_from` step recorder.

**Plan:** §51.3 of `.agents/plans/51-agentic-security-hardening.md`.
**Deliverable:**
- `SECURITY__AGENT_MAX_TOOL_CALLS: int = 100` (default) in `app/core/config/security.py`
- Counter in `BaseAgentService.process` that raises `AgentKMaxExceededError` (new exception under `app/ai/security/exceptions.py`) when cap exceeded
- Planning-step telemetry: emit `ai.agent_planning_step` event per `_execute_from` iteration with step_id + tool_call_count + cumulative_tokens + elapsed_ms
- New `bench_security_envelope` case in `make bench`
**Verify:** New test `app/ai/security/tests/test_tool_call_cap.py` covering at-cap + over-cap + per-agent-override paths. Telemetry assertions in `app/ai/blueprints/tests/test_engine.py`.
**Reduces:** Autonomy — bounds how far an agent can drift before deterministic stop.
**Effort:** 1d.

### 51.4 Tamper-Evident Append-Only Audit `[Backend, Security]` `[Plan Ready]`

Convert `AgentAuditLog` to a chained-hash append-only structure (Merkle chain or hash-pointer per entry). Loki logs remain for query convenience; the chained log is the canonical record. Replay verification CLI for audit reconciliation. Killing an agent (51.7) emits an `ai.agent_killed` entry that is part of this chain — this is why 51.7 blocks on 51.4.

**Plan:** §51.4 of `.agents/plans/51-agentic-security-hardening.md`.
**Deliverable:**
- `app/ai/agents/audit.py::AgentAuditLog` extended with `prev_hash: str` + `entry_hash: str` columns (alembic migration)
- Insert path computes `entry_hash = sha256(prev_hash || json(entry))`; rejects if `prev_hash` doesn't match latest
- `app/ai/agents/audit_chain.py::verify_chain()` walks the chain and returns first divergence point
- CLI: `python -m app.ai.agents.audit_chain verify` for ops use
- New `SECURITY__AUDIT_CHAIN_ENABLED` flag (default `true`)
**Verify:** `app/ai/agents/tests/test_audit_chain.py` — append 100 entries, verify; tamper with row 50, verify reports divergence at row 50.
**Reduces:** Assurance — audit trail can no longer be silently rewritten.
**Effort:** 1–2d.

### 51.5 Toxic-Combination Policy DSL `[Backend, Security]` `[Plan Ready]`

Implement a Progen-like DSL for declarative policy invariants. Example rule: `DENY tool[internal_db_read] WHEN session.has(tool[outbound_network])`. Policy engine evaluates per tool invocation; default-deny on rule ambiguity. Replaces procedural enforcement scattered across agent services with declarative rules.

**Plan:** §51.5 of `.agents/plans/51-agentic-security-hardening.md`.
**Deliverable:**
- `app/ai/security/policy/__init__.py` package
- `app/ai/security/policy/dsl.py` — Lark-based grammar for `ALLOW|DENY tool[X] WHEN <expr>`; rule loader from `app/ai/security/policy/rules.yaml`
- `app/ai/security/policy/evaluator.py` — `Evaluator.check(action, session_context) -> Decision(allowed, reason)`; default-deny on ambiguity
- Wire into `BaseAgentService.process` envelope as the pre-dispatch gate
- Initial ruleset: 5-10 known toxic combinations (internal-DB-read + outbound-network, credential-read + external-API-write, etc.)
- New `SECURITY__POLICY_DSL_ENABLED` flag (default `true`)
**Verify:** `app/ai/security/policy/tests/test_evaluator.py` (~25 tests) covering allow/deny/ambiguous; integration test that wires through a real agent invocation.
**Reduces:** Autonomy + Power — explicit toxic-combination boundaries.
**Effort:** 2–3d.

### 51.6 HITL Cryptographic Signatures `[Backend, Frontend, Security]` `[Plan Ready]`

Non-reversible or high-impact actions require an external cryptographic signature the agent cannot fabricate. Frontend approval UI prompts for signature; backend verifier checks before dispatch. Wire into export-to-ESP and credential rotation as first targets. One frontend touch — approval dialog signature input.

**Plan:** §51.6 of `.agents/plans/51-agentic-security-hardening.md`.
**Deliverable:**
- `app/ai/security/hitl.py` — `SignatureChallenge` + `verify_signature(action_id, signature, public_key)`; Ed25519 keypair per operator
- New table `hitl_approvals` (action_id, signature, signer_id, signed_at, ttl)
- Backend gate: `app/approval/service.py` or new `app/ai/security/hitl_gate.py` checks signature before dispatching ESP export / credential rotation
- Frontend: extend `cms/apps/web/src/components/approvals/decision-bar.tsx` with WebAuthn signature input
- New `SECURITY__HITL_REQUIRED_FOR: list[str]` config (defaults `["esp_export", "credential_rotate"]`)
**Verify:** `app/ai/security/tests/test_hitl.py` (~20 tests) covering valid/invalid/expired signatures + agent-fabrication rejection. Frontend smoke via Playwright (`cms/apps/web/playwright/approval-signature.spec.ts`).
**Reduces:** Autonomy — hard gate on irreversible operations.
**Effort:** 1–2d.

### 51.7 Infra-Level Kill + Sandboxed Tool Execution `[Backend, DevOps, Security]` `[Plan Ready]`

Move agent MCP tool execution into a separate sidecar process (`services/tool-runner/`) with cgroup/namespace isolation. Out-of-band kill switch operates at the orchestrator layer — terminates the sidecar regardless of agent LLM state. Maizzle sidecar already proves the pattern. Containerise agent MCP tools (`app/mcp/tools/`) into the new sidecar. Blocks on 51.4 (audit chain captures `ai.agent_killed` entries).

**Plan:** §51.7 of `.agents/plans/51-agentic-security-hardening.md`.
**Deliverable:**
- `services/tool-runner/` — new Node or Python sidecar with single endpoint `POST /execute` (tool_name, args) → result
- Dockerfile with cgroup limits (memory, CPU, network egress allowlist); seccomp profile
- `app/mcp/tools/` invocations rerouted through HTTP client to the sidecar (replaces in-process import path)
- Orchestrator-level kill: `app/ai/security/kill_switch.py::kill_agent(agent_id)` sends `SIGTERM` to the sidecar PID + writes `ai.agent_killed` chain entry (consumes 51.4)
- `docker-compose.yml` adds the tool-runner service
- New `SECURITY__SANDBOXED_TOOLS_ENABLED` flag (default `false` until soak); flip to `true` after observation period
**Verify:** `services/tool-runner/tests/` integration tests + `app/mcp/tests/test_sandbox_dispatch.py`. Manual kill drill: start agent, trigger kill mid-tool-call, verify sidecar process terminates within 1s + audit chain entry recorded.
**Reduces:** Power — toxic combinations enforced at the OS boundary, not in-process.
**Effort:** 3–5d.
