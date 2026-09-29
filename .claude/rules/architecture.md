---
description: Email Hub architecture — modules, QA checks, agents, eval framework
paths: "**/*.{py,ts,tsx}"
---

# Architecture Reference

## API Modules

projects (`/api/v1/projects`), email_engine (`/api/v1/email`), components (`/api/v1/components`), qa_engine (`/api/v1/qa`), connectors (`/api/v1/connectors`), approval (`/api/v1/approvals`), templates (`/api/v1/templates`), personas (`/api/v1/personas`), rendering (`/api/v1/rendering`), knowledge (`/api/v1/knowledge`), memory (`/memory`), blueprints (`/api/v1/blueprints`), ontology (`/api/v1/ontology`), design_sync (`/api/v1/design-sync`), workflows (`/api/v1/workflows` — Kestra orchestration, `KESTRA__ENABLED`), templates/upload (`/api/v1/templates/upload` — self-serve HTML upload pipeline, `TEMPLATES__UPLOAD_ENABLED`), skills (`/api/v1/skills` — skill extraction management, `SKILL_EXTRACTION__ENABLED`), reports (`/api/v1/reports` — Typst PDF reports, `REPORTING__ENABLED`), evals/templates (`/api/v1/evals/templates` — template-sourced eval case management, `TEMPLATES__UPLOAD_ENABLED`), variants (`/api/v1/agents/scaffolder/generate-variants` — multi-variant A/B campaign assembly, `VARIANTS__ENABLED`), scheduling (`/api/v1/scheduling` — cron job CRUD + manual trigger + run history, `SCHEDULING__ENABLED`), credentials (`/api/v1/credentials` — credential pool health dashboard, admin-only, `CREDENTIALS__ENABLED`).

## QA Gate (14 checks in `app/qa_engine/checks/`)

html_validation, css_support, css_audit (per-build CSS compatibility matrix), file_size, link_validation, spam_score, dark_mode, accessibility, fallback (MSO), image_optimization, brand_compliance, personalisation_syntax, liquid_syntax. Each: `async run(html, config) -> QACheckResult`. `deliverability` check integrates ISP-aware analysis via `deliverability_analyzer.py` (Gmail/Microsoft/Yahoo profiles from `data/isp_profiles.yaml`).

## 9 AI Agents

Scaffolder, Dark Mode, Content, Outlook Fixer, Accessibility, Personalisation, Code Reviewer, Knowledge, Innovation. All have 5-criteria judges + SKILL.md files. Blueprint engine orchestrates as state machine nodes.

**Structured output mode (11.22.8):** 7 downstream agents return structured decision schemas (`app/ai/agents/schemas/*_decisions.py`) instead of raw HTML. `plan_merger.py` merges decisions into `EmailBuildPlan`. `TemplateAssembler` is the single HTML generation point. Outlook Fixer is diagnostic-only in structured mode.

## Eval System (`app/ai/agents/evals/`)

Binary pass/fail LLM judges calibrated via TPR/TNR. Key files: `runner.py`, `judge_runner.py`, `judges/`, `dimensions.py`, `synthetic_data_*.py`, `calibration.py`, `qa_calibration.py`, `regression.py`, `skill_ab.py`, `improvement_tracker.py`, `golden_cases.py`.

**Inline judges (11.23):** `app/ai/blueprints/inline_judge.py` bridges `JUDGE_REGISTRY` into live blueprint execution on recovery retries (`iteration > 0`). Lightweight model tier, `temperature=0.0`, failure-safe. Config: `BLUEPRINT__JUDGE_ON_RETRY=true`.

**Eval-driven iteration (11.22.9):** `improvement_tracker.py` records pass rate deltas to `traces/improvement_log.jsonl`. `golden_cases.py` validates 7 templates deterministically in CI (`make eval-golden`). `dimensions.py` includes template-first criteria (template_selection_accuracy, slot_fill_quality, design_token_coherence). `regression.py` enforces 3pp per-agent tolerance via `AGENT_REGRESSION_TOLERANCE`. Scaffolder has 22 synthetic test cases (10 template selection edge cases added).

**Production trace sampling (11.24):** `app/ai/agents/evals/production_sampler.py` closes the eval feedback loop. Successful blueprint runs are probabilistically enqueued to Redis (`service.py` post-run hook), `ProductionJudgeWorker` (DataPoller) processes the queue with LLM judges, verdicts append to `traces/production_verdicts.jsonl`, `refresh_analysis()` merges with synthetic verdicts into `traces/analysis.json`. Existing `failure_warnings.py` reads merged analysis — agents learn from production failures. Config: `EVAL__PRODUCTION_SAMPLE_RATE` (default `0.0` = disabled). Command: `make eval-refresh`.

## Design System & Brand Pipeline (11.25)

**Design System (11.25.1):** Per-project brand identity in `app/projects/design_system.py`. `DesignSystem` frozen Pydantic with `BrandPalette`, `Typography`, `LogoConfig`, `FooterConfig`, `SocialLink` + dynamic token maps (`colors`, `fonts`, `font_sizes`, `spacing`). JSON column on `Project`. API: GET/PUT/DELETE `/api/v1/projects/{id}/design-system`. `resolve_color_map()` merges `BrandPalette` fields + explicit `colors` dict. `design_system_to_brand_rules()` bridges to brand compliance.

**Component → Section Bridge (11.25.2):** `app/components/section_adapter.py` converts `ComponentVersion` → `SectionBlock` via 5-stage pipeline. `ComponentVersionLike` Protocol. `get_cached_section()` caches by version ID. `slot_definitions` + `default_tokens` JSON columns on `ComponentVersion`.

**Project-Scoped Template Registry (11.25.3):** `app/projects/template_config.py` — `ProjectTemplateConfig` with `SectionOverride`, `CustomSection`, `disabled_templates`, `preferred_templates`. `get_for_project()` + `list_for_selection_scoped()` on `TemplateRegistry`.

**Agent Pipeline Constraint Injection (11.25.4):** Design system as generation constraints. `DefaultTokens` on `GoldenTemplate` + `SectionBlock` declares per-template/component default hex values. `ScaffolderPipeline._design_pass_from_system()` builds `DesignTokens` deterministically (zero LLM). `_build_locked_fills()` locks footer/logo slots. `TemplateAssembler` applies role-based palette replacement (find default hex → replace with client hex), font replacement, logo dimension enforcement, social link injection, dark mode color replacement, brand color sweep safety net (Euclidean RGB nearest-match). LAYER 11 in `BlueprintEngine._build_node_context()` injects design system + resolved color/font maps + template_config into all node contexts. Pipeline layout pass uses `list_for_selection_scoped()` when template_config is set.

**Consistency Enforcement (11.25.5):** `app/qa_engine/repair/brand.py` — `BrandRepair` stage 8 in repair pipeline. Deterministic off-palette color correction (Euclidean RGB distance), footer legal text injection, logo URL correction. `RepairPipeline` accepts `design_system`. E2e test: design system → pipeline → repair → QA validation.

## Frontend (`cms/`)

**Builder:** `components/builder/` — visual email builder with DnD component palette, sortable canvas, sandboxed preview, undo/redo. `panels/` — property panel (Content/Style/Responsive/Advanced tabs, palette-restricted color picker, slot editors, design system token overrides, responsive toggles, MSO conditional, HTML attribute editor). `hooks/use-builder.ts` — state reducer + HTML assembler (slot fills, 13-token CSS overrides, dark mode CSS, MSO ghost tables, scoped section CSS, URI/CSS sanitization).

**Builder Sync:** `lib/builder-sync/` — bidirectional code↔builder sync. `ast-mapper.ts` HTML parser with ESP token preservation (Liquid/Handlebars/AMPscript/ERB), structural ESP internalization, dynamic column group detection, `parseInlineStyle` quote-aware CSS parser. `sync-engine.ts` debounced sync (builder wins). `section-markers.ts` + `annotation-utils.ts` for section merge/split/unwrap/rename.

**Collaboration:** `components/collaboration/` — presence panel, collaboration banner, conflict resolver, remote cursor styles. `hooks/use-presence.ts` — awareness state + follow mode.

**Tolgee TMS:** `hooks/use-tolgee.ts` — SWR hooks for connection, languages, sync, pull, locale build. `components/tolgee/` — translation key panel, side-by-side locale preview, per-locale QA matrix, in-context overlay, connection dialog.

**Design System:** `types/design-system-config.ts` — DesignSystemConfig + palette swatch extraction.

**Ecosystem:** `components/ecosystem/` — unified dashboard (overview quadrants, plugin manager, workflow execution with Gantt timeline, report generator with PDF preview, Penpot connection browser). SWR hooks: `use-plugins`, `use-workflows`, `use-reports`, `use-penpot`. Route: `/ecosystem`.

**Rendering:** `components/rendering/` — pre-send rendering gate (traffic-light badge, per-client confidence bars, admin override) + dashboard (preview grid for 14 clients, confidence summary, calibration health panel). `hooks/use-rendering-gate.ts`, `hooks/use-rendering-dashboard.ts`. Wired into export dialog + push-to-ESP dialog. Dashboard tab on `/renderings`.

**Approvals:** `components/approvals/` — approval request dialog, gate panel (blocks export/push), status badge, decision bar, feedback panel, audit timeline, version compare. `hooks/use-approvals.ts` (8 SWR hooks). `hooks/use-export-pre-check.ts` — combined QA + rendering + approval pre-check. List page `/approvals`, detail page `/approvals/[id]`.

## Maizzle Sidecar

`services/maizzle-builder/` — POST /build (+ `target_clients` → `optimization` metadata), POST /preview, POST /compile-mjml (MJML → email HTML via `mjml-compile.js`, + optional PostCSS optimization via `target_clients`), GET /health (+ `ontology_version` + `mjml_version`). Consolidated CSS pipeline: `postcss-email-optimize.js` PostCSS plugin (ontology-driven elimination/conversion) + Lightning CSS minification, runs before Maizzle/Juice inlining. MJML compilation via `mjml-compile.js` (pure function, testable independently). Ontology synced via `scripts/sync-ontology.js` (`make sync-ontology`).
