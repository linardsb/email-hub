# Phase 54.0 — Agent Self-Improvement Loops: Activate-vs-Retire Decision

**Status:** ✅ Ratified · **Decided by:** user (Linards) · **Date:** 2026-06-22 · **Gate:** `TODO.md` §54.0
**Basis:** `docs/agentic_rl_memory_handoff_findings.md` §3.1/§3.3 (live-vs-inert tables), §2.1/§2.4 (anti-patterns), §7.3 (strategic framing); advisory leans from `.agents/plans/flags-2026-09-15-graduate-or-kill-worksheet.md`.
**Scope:** the agent-generation pipeline only — does **NOT** touch converter fidelity (Phase 52–53; deterministic, outside the agent loop).

> **Decision gate only. No config / code / manifest was changed by this document, and no `removal_date` was re-bumped.** Execution is Phase 54.1 → 54.2 (for activates), a removal PR (for deletes), or a permanent-opt-in PR (for the keep) — all tracked separately.

## Ratified per-loop decisions (8 loops)

| # | Flag | Decision | Rationale | Ratified |
|---|------|----------|-----------|----------|
| 1 | `AI__ADAPTIVE_ROUTING_ENABLED` | **DELETE** | Doubly inert — engine computes `effective_tier` (layer_20) but **no node reads it**; `routing_history` keyed on constant `"standard"`. Activating needs node-wiring *beyond* the flag; beta, 0 dedicated tests, no demonstrated lift. | user 2026-06-22 |
| 2 | `BLUEPRINT__RECOVERY_LEDGER_ENABLED` | **ACTIVATE** | Findings-doc lead pick (§5/B2). Contextual-bandit fixer-reroute; QA-outcome reward (less human-label-dependent than the judge loops) — but alpha / 0 tests and cold-start may underperform the static `route_advisor`, so validate behind 54.2. **⇒ commits to 54.1.** | user 2026-06-22 |
| 3 | `BLUEPRINT__JUDGE_AGGREGATION_ENABLED` | **DELETE** | Multi-judge verdict aggregation; only adds value with calibrated judges; alpha, 0 tests, no signal. | user 2026-06-22 |
| 4 | `BLUEPRINT__CONFIDENCE_CALIBRATION_ENABLED` | **DELETE** | Reward-calibrated gating; the most corpus-dependent loop; alpha, 0 tests. | user 2026-06-22 |
| 5 | `BLUEPRINT__INSIGHT_PROPAGATION_ENABLED` | **DELETE** | Cross-agent insight bus; "written-but-unread" family (`format_upstream_constraints`/`upstream_learnings` unread); alpha, 0 tests. | user 2026-06-22 |
| 6 | `BLUEPRINT__CORRECTION_EXAMPLES_ENABLED` | **DELETE** | Retry-time few-shot from corrections; not P54-named; no downstream consumer; alpha, 0 tests. | user 2026-06-22 |
| 7 | `CORRECTION_TRACKER__ENABLED` | **KEEP (opt-in)** | Worksheet `(b)/(c)` — keep-vs-kill, not activate-vs-kill. It is the **converter rule-learning seam** (`CorrectionTracker → ConverterRuleSuggestion`, Track A3) for the active 53.x program; preserve default-OFF rather than rebuild later. **Does NOT trigger 54.1.** | user 2026-06-22 |
| 8 | `BLUEPRINT__JUDGE_ON_RETRY` | **ACTIVATE** | Findings-doc lead pick — the **only** online reward (inline judge on recovery retry). Judge-based ⇒ **requires** calibrated judges (54.1) or it feeds the loop noise. Not in the 26-flag batch (pure P54 call). **⇒ commits to 54.1.** | user 2026-06-22 |

**Tally:** 2 ACTIVATE · 5 DELETE · 1 KEEP-opt-in.

## 54.1 verdict: **REQUIRED**

≥1 activate (in fact **2**: `recovery_ledger`, `judge_on_retry`) ⇒ Phase 54.1 (build the reward corpus) is a **hard prerequisite** before either flag is flipped. Enabling on today's empty/stale `traces/` would make agent output *worse* — uncalibrated reward is noise (findings §2.1/§2.4). 54.1 sub-items (per `TODO.md` §54.1):

- Seed/commit the gitignored `traces/` so a fresh deploy has `analysis.json` for `failure_warnings`.
- Populate the `{agent}_human_labels.jsonl` files so judges hit TPR≥0.85 / TNR≥0.80 (gates `judge_on_retry`).
- Set a small `EVAL__PRODUCTION_SAMPLE_RATE` to collect on-policy verdicts.
- Register `MemoryCompactionPoller` (`app/memory/compaction.py:60`) in `app/main.py` — defined but never instantiated.
- ✅ Done 2026-06-11 — memory recall dead-on-read fix (`0b0313aa`).

Then **54.2:** flip each activated flag behind a before/after `make eval-calibration-gate` + golden-set comparison; keep only loops that lift pass-rate without regressing the 3pp/5pp gates or cost.

## Execution (separate from this gate — NOT performed here)

- **ACTIVATE ×2** (`recovery_ledger`, `judge_on_retry`): no flag flip until 54.1 lands; then 54.2 measured rollout. They stay default-OFF until then.
- **DELETE ×5** (`adaptive_routing`, `judge_aggregation`, `confidence_calibration`, `insight_propagation`, `correction_examples`): removal PR(s) — delete the flag, gated branches, config field, `.env.example` line, manifest entry, and tests. For `adaptive_routing` also remove the inert `effective_tier` computation. ai-team, off fresh main; `make check` + `make eval-check`.
- **KEEP ×1** (`correction_tracker`): `feature-flags.yaml` → `removal_date: null` + `permanent_reason` (converter Track A3 seam); leave default-OFF, code as-is.

## Cross-references

- **Ledger:** `.agents/deferred-items.json` → `flags-2026-06-15-batch-reschedule`. These 8 are the 7 P54-cohort flags it deferred **plus** `JUDGE_ON_RETRY` (which is *not* in that 26-flag batch). The ledger entry stays `deferred` until the directions above are executed.
- **Worksheet:** `.agents/plans/flags-2026-09-15-graduate-or-kill-worksheet.md` (advisory a/b/c leans).
- **Audit:** `docs/agentic_rl_memory_handoff_findings.md` (2026-06-05, 5-agent read-only audit).
