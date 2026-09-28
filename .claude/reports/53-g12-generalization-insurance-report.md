# Implementation Report — G12 Generalization Insurance (Phase S: Mammut Semantic-Split Spike)

**Plan**: `.agents/plans/53-g12-generalization-insurance.md`
**Branch**: `feature/g12-generalization-insurance` (off `origin/main 60c98bc6`)
**Status**: **PARTIAL — Phase S COMPLETE (PARK + DELETE, user-ratified 2026-07-22); Phase O BLOCKED on user Figma keys (second PR); Phase C partial (S-scoped close-out done)**

**Committed set = docs only.** On the ratified PARK the user chose DELETE: the flag + splitter
code + S-driven test changes were reverted to `origin/main`; the record is the decision doc,
ceiling §4, ledger note, and this branch's git history.

## Summary

Executed **Phase S** (the independent, unblocked mammut semantic-split spike) end-to-end:
added a default-off flag, implemented the prompt-named deterministic role-seam actuator
(Arm 1) behind it, measured it on the A2 ladder + advisory A3, and wrote a ship-or-park
decision doc. **Result: PARK** — the mechanism raises mammut's count 12→16 but breaks the
7/8/9=8/10/8 floor (perf 10→14, slate 8→10, maap 13→18, starbucks 9→10) and does not improve
pixel fidelity. **Phase O** (onboard cases 11–13) is hard-blocked pending user-supplied Figma
file key(s) + `FIGMA_TOKEN` and ships as a separate PR. **Phase C** close-out done for the
S-scoped parts (flag registered, ceiling §4 records the cap, full backend gate green).

## Tasks completed (Phase S + S-scoped Phase C)

- **S1** flag `semantic_split_enabled: bool = False` → `app/core/config/design_sync.py` (UPDATE)
- **S2** register `DESIGN_SYNC__SEMANTIC_SPLIT_ENABLED` → `feature-flags.yaml` (UPDATE) + `.env.example` regen (UPDATE)
- **S3** Arm-1 `_split_sections_by_role_seams()` + helpers, wired at `analyze_layout:382` → `app/design_sync/figma/layout_analyzer.py` (UPDATE, +168)
- **S4** measured flag-ON across cases 5–10 (A2 ladder) + A3 for cases 8/10 (see tables below)
- **S5** Arm 2 (offline VLM fixture) — **not pursued** (documented measured-negative; rationale in decision doc)
- **S6** ship-or-park decision doc → `.agents/plans/53-g12-mammut-seam-decision.md` (CREATE) — **PARK recommended**
- **C1 (partial)** ceiling §4 mammut residual refreshed with G12 evidence → `docs/converter-fidelity-ceiling.md` (UPDATE)
- **C2** full backend gate green (below)
- **C3** TODO.md Track-G status refreshed (on disk, **not committed** — gitignored)
- Ledger note appended to `phase-53-d3-mammut-below-candidate-undercount` → `.agents/deferred-items.json` (UPDATE)

**DELETE (S6 outcome, ratified):** S1–S3 code (`design_sync.py` flag, `feature-flags.yaml`
entry, `.env.example` line, `layout_analyzer.py` splitter + helpers) and the S-driven test
edits (`test_layout_analyzer.py` split suite, `test_config_design_sync.py` bound, VLM mock
line) were reverted to `origin/main`. **Committed diff = `docs/converter-fidelity-ceiling.md`
+ `.agents/deferred-items.json` + the new decision doc + plan + this report.**

## Tests added

`app/design_sync/tests/test_layout_analyzer.py::TestSemanticRoleSeamSplit` (5, all pass):
- `test_flag_off_returns_input_unchanged` — off → same list object (byte-identical proof)
- `test_flag_on_splits_two_heading_stack` — on → 2 heading-led slices → 2 synthetic solo candidates, accurate y/height
- `test_flag_on_single_heading_editorial_not_split` — 1 heading (the mammut editorial shape) → intact
- `test_flag_on_horizontal_row_not_split` — horizontal ≥2-column row (§C2b trap) → intact
- `test_flag_on_banded_candidate_not_split` — `parent_wrapper_id` set → out of scope, intact

Two stub updates driven by the new config field:
- `test_config_design_sync.py::test_design_sync_field_count_bounded` bound 58→59 (+comment)
- `test_vlm_section_classifier.py::_mock_layout_settings` gains `semantic_split_enabled: False`

_All three test changes were the executable proof of the mechanism during the spike (5 split
tests green; full backend suite 8497 green); **reverted to `origin/main` on the ratified DELETE.**_

## Measured evidence

### A2 ladder (deterministic, `python -m app.design_sync.tests.ladder_harness`)

| case | target | render OFF | render **ON** | verdict |
|---|---:|---:|---:|---|
| 7 lego | 8 | 8 | 8 | ✅ held |
| 8 perf | 10 | 10 | **14** | ❌ over +4 (§C2b regression) |
| 9 slate | 8 | 8 | **10** | ❌ over +2 |
| 5 maap | 13 | 13 | **18** | ❌ over +5 |
| 6 starbucks | 9 | 9 | **10** | ❌ over +1 |
| 10 mammut | 18 | 12 | **16** | moved +4, via over-seg |

Ship gate (mammut→18 **AND** floor holds) fails on 4/5 cases. Flag-OFF byte-identical
(corpus suite 107 passed / 2 xfailed unchanged).

### A3 advisory pixel (`scripts/score-fidelity-cases.py`)

| case | full OFF→ON | median OFF→ON |
|---|---|---|
| 8 perf | 0.822 → 0.845 | 0.840 → 0.881 |
| 10 mammut | 0.720 → **0.716** | 0.827 → **0.793** |

Count rises without fidelity gain — over-segmentation, not recovery. Case 8's full-image rise
is A3 section-instability, not a real gain (count regressed 10→14).

## Validation results

Full `make check-full` gate green (backend + frontend):
- `make lint` (ruff format+check) — pass
- `make types` (mypy + pyright) — **0 errors** (pre-existing warnings only)
- `make test` — **8497 passed, 115 skipped, 2 xfailed, 0 failed**
- `make security-check` / `validate-overlays` / `lint-numeric` / `golden-conformance` (26 pass) — pass
- `make flag-audit` — pass (88 flags) · `make check-env-drift` — pass · `make migration-lint` — exit 0
- `make check-fe` — pass (prettier clean · tsc clean · **780 frontend tests pass** · lint-polling OK)

Post-DELETE re-verify (final docs-only tree): `make flag-audit` — **87 flags** (spike flag gone)
· `make check-env-drift` — pass · previously-touched test files — 97 passed · split suite — 0 collected (removed).

## Deviations from the plan

1. **PARK, not ship** — the spike outcome the plan flagged as "genuinely open" resolved to PARK
   on measured evidence (floor break). Intended: the decision doc with measured evidence was the
   deliverable "either way."
2. **Arm 2 not implemented** — documented measured-negative (plan §S5 sanctions this). The gap is
   out-of-scope band-grouping + the §C2b horizontal trap; an offline-VLM per-case seam annotation
   is not a generalizable rule and would not change the verdict.
3. **Diagnosis correction** — the plan's/deferred-item's premise ("6 missing sections inside fat
   candidates") is wrong: `analyze_layout` already emits 17 sections; band-grouping (out of scope)
   re-collapses to 12. Recorded in the decision doc + ceiling §4.
4. **Spec/code gap flagged** — `_MJ_CONTENT_ROLES` has no "heading" role, so the plan's "seam on
   heading-role children" is synthesized (uppercase / font step); that synthesis can't separate a
   section heading from an in-editorial eyebrow/CTA-link — the root cause of the floor break.
5. **Flag fate = DELETE (user-ratified).** The plan offers keep-vs-delete on PARK. Because the
   mechanism is measured-*harmful* when enabled (breaks 4/5), it is not switch-on insurance, so
   per Simplicity-First the flag + splitter + S-driven test edits were removed; the decision doc,
   ceiling §4, ledger note, and branch history are the full record. (AC #6/#7 — flag registered /
   flag-off byte-identical — were satisfied during the spike, then deliberately unwound by DELETE.)

## Issues encountered

- Two `make`-gate side-effects stamped today's date into `app/ai/agents/*/skill-versions.yaml`
  (`hash: pending` rows) — unrelated to G12, reverted before commit.

## Not done (blocked / deferred to the second PR)

- **Phase O** (AC #1–#5): onboard cases 11–13 — **blocked on user Figma file key(s) + `FIGMA_TOKEN`**.
- **Phase C** corpus rows (ceiling §2/§3 for the new cases) — depend on Phase O.
