# Feature-Flag Graduate-or-Kill Decision Worksheet — 2026-09-15 batch (26 flags)

> **Status:** research complete, **decisions pending per owner team**. This is a
> worksheet, not an executed change. No code/config/manifest/ledger was modified
> to produce it.
>
> **Scope:** the 26 in-house, default-OFF flags rescheduled `2026-06-15 → 2026-09-15`,
> tracked in `.agents/deferred-items.json` → `flags-2026-06-15-batch-reschedule`
> (cross-checked against `feature-flags.yaml` `removal_date: "2026-09-15"` — exactly 26).
> The 8 `Sibling action` flags are already permanent opt-in — **out of scope, leave them.**
>
> **The terminal states** (pick one per flag — a product call, use the owner team; don't guess):
> - **(a) GRADUATE** default-on: flip config default `True`, inline the enabled path, delete the `if settings.<x>:` guards, drop the field + `.env.example` line + manifest entry.
> - **(b) KEEP permanent opt-in**: `feature-flags.yaml` → `removal_date: null` + `permanent_reason`; leave default `False`, code as-is. *(Likely the modal outcome.)*
> - **(c) KILL**: delete the feature impl, gated code, config field, `.env.example` line, manifest entry, and its tests.
>
> **Hard rules:** surgical per flag · never `ruff --fix` with TCH rules · **do NOT bump removal dates again** (that's the band-aid this replaces) · one PR per owner team off **fresh main** (after #291 lands).

---

## Key findings (read first)

1. **All 26 are confirmed default-OFF** in `app/core/config/` — none is secretly shipped. There is no "graduate by removal" freebie subset; every one needs a real call.

2. **⚠️ 5 flags are the SAME decision as `TODO.md` Phase 54** — *"Activate or Retire the Agent Self-Improvement Loops"* (54.0 = decision gate, **not yet committed**; 54.2 = "Enable behind a measured rollout **or delete**"). P54's 54.0/54.2 enumerate the loops **by name**; the ones that fall in *this* batch are:
   `ai.adaptive_routing_enabled`, `blueprint.recovery_ledger_enabled`,
   `blueprint.judge_aggregation_enabled`, `blueprint.confidence_calibration_enabled`,
   `blueprint.insight_propagation_enabled` (all `alpha`/`beta`, ~0 dedicated app tests).
   Do **not** resolve these independently — route them through the P54.0 gate; the live choice is **(a) activate-with-measurement** vs **(c) kill**. (54.2 flags adaptive-routing as *doubly* inert — no node reads `effective_tier` — so it's activate-and-wire or delete.)
   - **Same "built-but-inert" family but NOT in P54's named list:** `blueprint.correction_examples_enabled`, `correction_tracker.enabled`. P54 doesn't formally gate them — ai-team should weigh them *alongside* P54 but decide on their own merits.
   - P54 **also** covers `BLUEPRINT__JUDGE_ON_RETRY`, which is **not** in this 26-flag batch — so "resolve the batch" ≠ "resolve P54"; the loop set is broader than these 5.

3. **Dependency inheritance** — several flags are children of infra/integration flags that are *already* permanent opt-in, so they inherit a **(b)** lean:
   - `ai.visual_qa_enabled` → headless-browser/screenshot infra + VLM cost (mirrors `RENDERING__SCREENSHOTS`, already permanent).
   - `ai.visual_qa_autofix_enabled` → child of `visual_qa`.
   - `skill_extraction.enabled` → only meaningful when `TEMPLATES__UPLOAD` (permanent opt-in) is on.
   - `design_sync.fidelity_enabled` → needs rendered screenshots + Figma export (infra + token).

4. **Modal outcome is likely (b)** — matches the prompt's expectation and the 8 sibling reclassifications (external dep / infra / cost). Genuine **(a) graduate** candidates are the *local, proven, safety/quality* mechanisms (`cost_governor`, `token_budget`, the two local QA checks). **(c) kill** candidates are the unproven self-improvement loops under P54.

### Blast-radius methodology
Counts are Python references in `app/`, from `rg`. **prod files** = files containing the token, **excluding** `app/core/config/**` and test files; **test files** = `test_*.py` matches.
- For field-name tokens (e.g. `visual_qa_enabled`) the count ≈ the guard/usage sites — a good **graduate** effort proxy (remove these guards).
- For ⓖ **group-name tokens** (`correction_tracker`, `skill_extraction`, `qa_*`) the count spans the *whole subsystem*, not just the `if enabled:` guard — that's the **kill** effort proxy, and overstates graduate effort.
- "0 test files" ≠ untested everywhere (integration/eval suites exist), but it's a real signal that graduating default-on lacks a unit safety net.

---

## ai-team — 19 flags

| # | Flag (`AI__`/`KNOWLEDGE__`/`BLUEPRINT__`…) | settings path | status | prod / test files | Advisory lean | Rationale (owner decides) |
|---|---|---|---|---|---|---|
| 1 | `ADAPTIVE_ROUTING_ENABLED` | `ai.adaptive_routing_enabled` | beta | 1 / 0 | **⚠️ P54** (a/c) | Named in P54's loop list (54.0/54.2). *Doubly* inert — no node reads `effective_tier`. Decide via P54.0: activate-and-wire or delete. |
| 2 | `VISUAL_QA_ENABLED` | `ai.visual_qa_enabled` | beta | 2 / 3 | **(b)** | Needs screenshot/headless-browser infra + VLM spend; mirrors already-permanent `RENDERING__SCREENSHOTS`. |
| 3 | `VISUAL_QA_AUTOFIX_ENABLED` | `ai.visual_qa_autofix_enabled` | alpha | 1 / 1 | **(b)** | Child of #2; auto-applies VLM edits — keep behind explicit enablement (or (c) if not pursued). |
| 4 | `TOKEN_BUDGET_ENABLED` | `ai.token_budget_enabled` | beta | 1 / 3 | **(a)** lean | Local prompt/response budgeting (safety/efficiency), reasonable test coverage. Owner confirms behavior parity. |
| 5 | `PROMPT_STORE_ENABLED` | `ai.prompt_store_enabled` | beta | 3 / 2 | **(b)** lean | Versioned-prompt management capability; enable when teams adopt it — not required default-on. |
| 6 | `COST_GOVERNOR_ENABLED` | `ai.cost_governor_enabled` | beta | 3 / 4 | **(a)** lean | Overspend prevention is a safety control you generally want on; best-tested AI flag (4 test files). |
| 7 | `MULTIMODAL_CONTEXT_ENABLED` | `ai.multimodal_context_enabled` | alpha | 1 / 1 | **(b)** | Alpha; needs multimodal-capable model (cost/capability). Opt-in. |
| 8 | `KNOWLEDGE__CRAG_ENABLED` | `knowledge.crag_enabled` | beta | 3 / 2 | **(b)** lean | Adds an LLM validation loop per query (cost/latency); enable where grounding matters. |
| 9 | `KNOWLEDGE__ROUTER_ENABLED` | `knowledge.router_enabled` | beta | 1 / 1 | **(b)** / (a) | Query-strategy selection; graduate if measured to improve retrieval, else opt-in. |
| 10 | `KNOWLEDGE__MULTI_REP_ENABLED` | `knowledge.multi_rep_enabled` | beta | 1 / 1 | **(b)** | Extra indexing compute/storage + LLM calls; opt-in. |
| 11 | `BLUEPRINT__CHECKPOINTS_ENABLED` | `blueprint.checkpoints_enabled` | beta | 2 / 0 | **(b)** / (a) | Run-checkpoint persistence (durability, **not** a self-improvement loop). Storage cost → opt-in, or (a) if cheap & wanted. |
| 12 | `BLUEPRINT__RECOVERY_LEDGER_ENABLED` | `blueprint.recovery_ledger_enabled` | alpha | 1 / 0 | **⚠️ P54** (a/c) | Self-improvement loop — decide via Phase 54.0 gate, not standalone. |
| 13 | `BLUEPRINT__CORRECTION_EXAMPLES_ENABLED` | `blueprint.correction_examples_enabled` | alpha | 1 / 0 | **(b)** / (c) | Retry-time few-shot correction; *not* in P54's named loop list but same inert family — weigh alongside P54, decide on merits. |
| 14 | `BLUEPRINT__JUDGE_AGGREGATION_ENABLED` | `blueprint.judge_aggregation_enabled` | alpha | 1 / 0 | **⚠️ P54** (a/c) | Self-improvement loop — Phase 54.0. |
| 15 | `BLUEPRINT__CONFIDENCE_CALIBRATION_ENABLED` | `blueprint.confidence_calibration_enabled` | alpha | 1 / 0 | **⚠️ P54** (a/c) | Self-improvement loop — Phase 54.0. |
| 16 | `BLUEPRINT__INSIGHT_PROPAGATION_ENABLED` | `blueprint.insight_propagation_enabled` | alpha | 1 / 0 | **⚠️ P54** (a/c) | Self-improvement loop — Phase 54.0. |
| 17 | `CORRECTION_TRACKER__ENABLED` | `correction_tracker.enabled` | alpha | ⓖ 4 / 2 | **(b)** / (c) | "...for agent self-improvement" but *not* in P54's named loop list — weigh alongside P54, decide on merits. Kill scope = whole tracker subsystem (~14 refs/4 files). |
| 18 | `SKILL_EXTRACTION__ENABLED` | `skill_extraction.enabled` | beta | ⓖ 3 / 1 | **(b)** | Only meaningful when `TEMPLATES__UPLOAD` (permanent opt-in) is on → inherits opt-in. Kill scope = extraction subsystem (~13 refs/3 files). |
| 19 | `VARIANTS__ENABLED` | `variants.enabled` | beta | 2 / 1 | **(a)** / (b) | User-facing A/B campaign feature w/ its own API route. Graduate if it's a supported product capability; else opt-in. **Product call.** Kill scope > guard count (route + service + assembler). |

## qa-team — 4 flags

| # | Flag (`QA_…__ENABLED`) | settings path | status | prod / test files | Advisory lean | Rationale |
|---|---|---|---|---|---|---|
| 20 | `QA_OUTLOOK_ANALYZER__ENABLED` | `qa_outlook_analyzer.enabled` | beta | ⓖ 2 / 1 | **(a)** lean | Local static analysis (Word-engine deps), no external dep → good QA-gate graduate candidate. |
| 21 | `QA_DELIVERABILITY__ENABLED` | `qa_deliverability.enabled` | beta | ⓖ 2 / 1 | **(a)** lean | Local ISP-aware scoring (bundled `isp_profiles.yaml`); QA-gate candidate. |
| 22 | `QA_GMAIL_PREDICTOR__ENABLED` | `qa_gmail_predictor.enabled` | alpha | ⓖ 3 / 1 | **(b)** | Calls an LLM (external API key + cost) → opt-in. |
| 23 | `QA_BIMI__ENABLED` | `qa_bimi.enabled` | beta | ⓖ 3 / 2 | **(b)** lean | Performs DNS lookups + SVG network fetch (network dependency) → opt-in, or (a) if the QA gate tolerates network calls. |

## platform-team — 2 flags

| # | Flag (`EMAIL_ENGINE__…`) | settings path | status | prod / test files | Advisory lean | Rationale |
|---|---|---|---|---|---|---|
| 24 | `CSS_COMPILER_ENABLED` | `email_engine.css_compiler_enabled` | beta | 2 / 2 | **(a)** / (b) | Local target-client CSS optimization in build pipeline. Graduate if output verified across target clients; else opt-in. |
| 25 | `SCHEMA_INJECTION_ENABLED` | `email_engine.schema_injection_enabled` | beta | 2 / 2 | **(b)** lean | Adds Schema.org JSON-LD — not wanted for every campaign → opt-in, or (a) if universally desired. |

## design-team — 1 flag

| # | Flag (`DESIGN_SYNC__…`) | settings path | status | prod / test files | Advisory lean | Rationale |
|---|---|---|---|---|---|---|
| 26 | `FIDELITY_ENABLED` | `design_sync.fidelity_enabled` | beta | 1 / 0 | **(b)** | SSIM scoring needs rendered screenshots + Figma export (infra + token); already advisory/case-5-only in CI per the pixel-metric deferred item. Opt-in. |

---

## How to action a decision (once an owner has chosen)

1. Confirm a/b/c with the owner team (above) — **don't guess.**
2. Map flag → settings path (table) and re-grep usages: `rg "<token>" app -g '*.py'`.
3. Apply the change for that flag only (see terminal-state recipes in the header).
4. Per batch: `make check` green (incl. **check-env-drift** — `.env.example` must stay in sync with `app/core/config/`). For agent/judge flags (`ai.*`, `blueprint.*`, `knowledge.*`, `correction_tracker`) also `make eval-check`.
5. Update the ledger entry per resolved flag; flip `flags-2026-06-15-batch-reschedule` → `status: closed` when all 26 are done.
6. One PR per owner team, branched off **fresh main**.

## Sign-off tracker (fill in per flag)

| Flag | Owner | Decision (a/b/c) | Decided by | PR |
|---|---|---|---|---|
| AI__ADAPTIVE_ROUTING | ai-team | (via P54.0) | | |
| AI__VISUAL_QA | ai-team | b | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| AI__VISUAL_QA_AUTOFIX | ai-team | b | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| AI__TOKEN_BUDGET | ai-team | a (graduate, keep-flag) | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| AI__PROMPT_STORE | ai-team | b | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| AI__COST_GOVERNOR | ai-team | a (graduate, keep-flag) | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| AI__MULTIMODAL_CONTEXT | ai-team | b | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| KNOWLEDGE__CRAG | ai-team | b | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| KNOWLEDGE__ROUTER | ai-team | b | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| KNOWLEDGE__MULTI_REP | ai-team | b | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| BLUEPRINT__CHECKPOINTS | ai-team | b | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| BLUEPRINT__RECOVERY_LEDGER | ai-team | (via P54.0) | | |
| BLUEPRINT__CORRECTION_EXAMPLES | ai-team | (weigh w/ P54) | | |
| BLUEPRINT__JUDGE_AGGREGATION | ai-team | (via P54.0) | | |
| BLUEPRINT__CONFIDENCE_CALIBRATION | ai-team | (via P54.0) | | |
| BLUEPRINT__INSIGHT_PROPAGATION | ai-team | (via P54.0) | | |
| CORRECTION_TRACKER | ai-team | (weigh w/ P54) | | |
| SKILL_EXTRACTION | ai-team | b | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| VARIANTS | ai-team | a (graduate, strict-remove) | user 2026-06-22 | chore/flags-ai-team-2026-09-15 |
| QA_OUTLOOK_ANALYZER | qa-team | | | |
| QA_DELIVERABILITY | qa-team | | | |
| QA_GMAIL_PREDICTOR | qa-team | | | |
| QA_BIMI | qa-team | | | |
| EMAIL_ENGINE__CSS_COMPILER | platform-team | | | |
| EMAIL_ENGINE__SCHEMA_INJECTION | platform-team | | | |
| DESIGN_SYNC__FIDELITY | design-team | | | |
