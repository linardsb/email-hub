# Feature: corpus refresh, re-sync maap and bring reframe into the measured corpus (CE-3, #421)

The following plan should be complete, but validate documentation, codebase patterns and task sanity before you start implementing. Pay attention to the names of existing utils, types and models, and import from the right files.

Base: origin/main `28c944ea` (observed: `git log -1 origin/main`, 2026-10-02). All `file:line` refs below were read at that head. Branch: `feat/ce-3-corpus-refresh`, cut from `origin/main`.

**One-pass confidence: 10/10.** The whole change was built and measured in a throwaway spike before this plan was finalised. Every behaviour, per-section figure, gate result, owner and test outcome the tasks rely on was observed on that spike (evidence below). The one step the spike could not run is the reframe image export, which needs the user's Figma token; the code path that consumes its output (re-stamp, gate check, committed-fixture tests) was rehearsed end to end with a placeholder reference and passes except for the one test that checks the assets are committed.

**Reference implementation:** `.tmpscratch/ce3/spike.diff` (gitignored, main checkout; 19 files). Worktree `.tmpscratch/ce3-spike` (detached, WIP commit `b7718df4` = exactly that diff; the placeholder probe of E26 sits uncommitted on top, copies in `.tmpscratch/ce3/probe/`; the worktree's `.venv` is an untracked symlink and must never be committed). The spike was reviewed by two fresh subagents (code review + claim re-check); their corrections are folded in (AMENDMENTS). Scratch artefacts in `.tmpscratch/ce3/`: `a3_before.json`, `a3_after.json`, `gate_base.json`, `gate_after_5.json`, `cap/<n>.html`. The implementer ports the diff (`git apply .tmpscratch/ce3/spike.diff`) and re-runs every VALIDATE on the branch; nothing below depends on an unmeasured assumption.

## Decisions ratified by the user (2026-10-02, planning chat)

| # | Decision | Effect |
|---|---|---|
| U1 | **Offline re-parse + token for assets only.** Structures come from re-parsing the local `raw_figma.json` snapshots with today's parser; reframe reuses the shared `tokens.json`. `FIGMA_TOKEN` is used only to export reframe's 16 node-keyed image assets | No live `diagnose.extract` run. Every fixture stays on one Figma file version (`2333309355688754162`, `lastModified 2026-03-21T08:56:07Z`) |
| U2 | **Strict owner-keyed known failures.** Reframe's failing manifest expectations stay in the manifest and run as `xfail(strict=True)`, each row naming its owner; the fixing ticket deletes its row (same ratchet as `data/debug/content_check_allowlist.yaml`) | New `known_failures` field on `CaseManifest`; owner = `#<issue>` or a deferred-items id, enforced by a guard test |
| U3 | **Full case-5 re-parse, explained per section.** Commit the parser's output verbatim; regenerate `expected.html` and `rendered_w600.png`; re-stamp the gate with a per-section reason | The ticket's "wrong if" fires by design; every moved section is mapped to its cause (E16) |

## Evidence

### Planning probes (observed 2026-10-02, scratchpad + trial worktree, both at `28c944ea`)

| # | Question | Result |
|---|---|---|
| E1 | Are the corpus `tokens.json` files design-specific? | No. `md5` of `data/debug/{5..10}/tokens.json` is identical (`bf5cd5c4…`): one whole-file token set for Figma file `VUlWjZGAEVZr3mK1EawsYR` (all 7 `figma_link.txt` point at it) |
| E2 | Do local raw snapshots carry strokes and match the corpus file version? | `data/debug/5/raw_figma.json` and `data/debug/reframe/raw_figma.json` (untracked, local only) are node responses for `2833:1623` / `2833:1491`, both `version 2333309355688754162`; case-5 raw has 122 `strokes` keys |
| E3 | Case-5 re-parse vs committed `structure.json` | Same 123 node ids; geometry and `corner_radius` unchanged (the F7 patch is reproduced). New/changed: `visible`, `opacity`, `style_runs` (123 each), `counter_axis_align` 53, `primary_axis_align` 43, `text_align` 22, `scale_mode` 12, `image_ref` 12, `stroke_color`/`stroke_weight` 3 nodes |
| E4 | Reframe re-parse vs committed `structure.json` (#413) | 17 diff lines, all `image_ref` null → hash, plus a trailing newline. No stroke nodes in reframe |
| E5 | Does `image_ref` change converter output? | No. Case 5 with `image_ref` nulled == full re-parse (byte-identical); reframe with it populated == committed |
| E7 | Reframe through today's converter (copied tokens) | 11 sections; all 3 CTA labels, their bg colours and any `v:roundrect` missing; banned fonts `Inter, Arial, Helvetica, sans-serif` ×4 (head + shell) and `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto` ×4 (section 1); banned colours `#444444` ×12, `#555555` ×2, `#333333` ×1 (sections 2–6, 9, 15); "Can’t make it" renders with U+2019; 16 distinct asset srcs; frame 640 × 3608 |
| E9 | Tests that auto-discover reframe once `tokens.json` exists | `test_bridge_roundtrip.py:423` glob, `test_jev_shadow*.py`, `test_fidelity_case_scorer.py`: green |
| E10 | CE-2 content checks, case 5 after re-parse (`content_checks --empty-allowlist`) | Same rows as base except `unsubscribe_link` links 1 → 2 (still pass); no allowlist row flips |
| E11 | Dump-schema round trip on every committed structure | reframe: 0 nodes differ. Case 5: 15 distinct keys missing (14 or 15 per node). Cases 6–10: the same 4 keys missing (`effects_summary`, `line_height_relative`, `rotation`, `scale_mode`) |
| E12 | Design truth for the case-5 changes (`raw_figma.json`) | Footer texts `2833:1742`, `2833:1744`: `textAlignHorizontal: LEFT` in a 512px frame, so `center → left` is design-correct as captured. "unsubscribe here" style-run override fill `#222222` (0.1333 grey) with the emaillove hyperlink, so the dark link colour is the design's own |
| E13 | Are reframe's 16 assets on disk anywhere? | No. `data/design-assets/5/` holds 655 other reframe node renders, none of the 16; `.agents/figma-cache/exports.json` has none; full-disk `find` empty. Token step stays |

### Spike (observed 2026-10-02, worktree `.tmpscratch/ce3-spike` at `28c944ea` + spike diff)

| # | What | Result |
|---|---|---|
| E14 | A3 before (base), `score-fidelity-cases.py`, 6 rows | full / min / median: 5 0.866/0.663/0.885 · 6 0.813/0.466/0.757 · 7 0.840/0.546/0.868 · 8 0.863/0.808/0.865 · 9 0.709/0.303/0.761 · 10 0.736/0.064/0.834 (`a3_before.json`) |
| E15 | Freshness test (Task 1) | RED on old case 5: 11 keys (`corner_radii`, `corner_radius`, `counter_axis_align`, `hyperlink`, `opacity`, `primary_axis_align`, `stroke_color`, `stroke_weight`, `style_runs`, `text_align`, `visible`); 7 passed after re-parse; mutation `_KNOWN_LAGGING_KEYS = frozenset()` → 5 failed (6–10), 2 passed (5, reframe) |
| E16 | Case-5 baseline audit (capture all six to scratch, `--ignore-all-space` diff) | 5: +14/−14; 6–10: empty; no `<p>`/`<h*>`. Changed lines by section (re-derived per line, confirmed by the claim re-check): `section_1` (`2833:1629`) text-align ×4 + "Discover" `border:1px solid #000000` (stroke); `section_2` (`2833:1643`), `section_4` (`2833:1650`) text-align; `section_5` (`2833:1655`) and `section_7` (`2833:1687`) divider `#e0e0e0 → #222222` (stroke); `section_8` (`2833:1693`) text-align (no gate move); `section_14` (`2833:1738`) footer `center → left` + design hyperlinks (Facebook, Strava → emaillove URL; "unsubscribe here" → `{{unsubscribeUrl}}`, colour `#222222`) |
| E17 | Ladder after re-parse + reframe row (`ladder_harness --write`) | Existing rows unchanged; one `reframe` row added: target 12, candidates 11, analyzed 16, rendered 11, bands 11, `wrappers[1507=5, 1602=2] solo=9` |
| E18 | A3 after (spike), 6 rows | case 5 full −0.0002, min +0.0004, median +0.0003, per-band max |Δ| 0.0050 (design-y band jitter, `a3-scoring.md`); cases 6–10 exactly 0.0000 on every number (`a3_after.json`) |
| E19 | CE-1 gate (`make fidelity-gate`, pinned image) | PASSED on base and on the spike. Spike vs base per section: only case 5 moves, 6 sections: `2833:1629` −0.0013, `2833:1643` −0.0028, `2833:1650` +0.0009, `2833:1655` +0.0014, `2833:1687` +0.0043, `2833:1738` +0.0022 (all inside margin 0.005; all in E16's changed sections). Cases 6–10 identical to base |
| E20 | Base drift vs the committed baseline | Base itself already differs from `fidelity_baseline.json` on 4 footer sections: 6 `2833:1475` −0.0011, 8 `2833:2348` −0.0005, 9 `2833:2149` −0.0004, 10 `2833:1270` +0.0001. These are CE-2's #450 footer moves (CE-2 plan E13 lists the same four sections; 8/9/10 match to 4 dp, 6 differs by 0.0001: −0.0012 there), never re-stamped. Not caused by CE-3 |
| E21 | CE-2 tests re-anchored (Task 5) | 171 passed. Mutations: `_repoint` disabled → `test_case_5_only_design_anchor_repointed` and `test_merge_tag_href_is_not_repointed` RED (+5 sibling tests); merge-tag guard narrowed to `{{unsubscribeUrl` → `test_merge_tag_href_is_not_repointed` RED; counter ignores href → `test_hash_href_is_not_an_unsubscribe_link` RED. All reverted |
| E22 | Owner tracing for reframe failures | CTAs: every `mj-button` (`2833:1503/1557/1593`) contains an `afterIcon-Frame`; their sections render as `bannerimg` of the icon (`2833:1560`, `2833:1596`) with no label → CE-10 #428's class. 11 vs 12: hand build splits Figma wrapper `2833:1497` (intro text + "Register now") into sections 2 and 3 (`manual_component_build.html:262-317`) → semantic under-count, `phase-53-a2-advisory-section-gate`. Inter: `convert_typography` (`token_transforms.py:948-953`) takes the first style whose name contains body/paragraph/text/regular (its docstring's "most common family" is stale); in the whole-file token set that is "Button Text", Inter 16px (observed by calling it on `reframe/tokens.json`); same 4 occurrences in cases 5 and 6 → new entry `ce-3-file-wide-tokens-body-font`. `-apple-system` stack (hero `dm_fontc`) and greys `#444444`/`#555555`/`#333333` (col-icon, event-card slots): template defaults never overridden → CE-13 #431 |
| E23 | `known_failures` ratchet | Reframe: 9 rows → 8 strict xfails (`test_font_family` has 2 rows, merged into one mark); the suite's other 2 xfails are the pre-existing case-10 target gates. Mutations: row on a passing test (case 6 `test_no_nested_p_tags`) → `XPASS(strict)` FAIL; a reframe row deleted → that test FAILS; owner typo → guard test FAILS. All reverted |
| E24 | Ledger edits | `.agents/deferred-items.json` round-trips byte-identically with `json.dumps(indent=2, ensure_ascii=False) + "\n"`; spike adds 2 entries and appends notes to `phase-53.7-asset-reexport-prerequisite` and `phase-53-a2-advisory-section-gate` (no close); the `chore/stamp-ledger-pr450` diff (`6084c4d9`) still applies on top (`git apply --check`, offsets +1) |
| E25 | Gates on the spike | `make types`: 0 errors. `make test`: 8866 passed, 10 xfailed, 1 failed = `test_every_referenced_asset_committed[reframe]` (placeholder probe, assets not exported). ruff check/format clean on changed files |
| E27 | Review fixes (after the code-review subagent) | `raises=AssertionError` on the strict xfail: a `TypeError` injected into `test_cta_vml` → reframe FAILS instead of xfailing; `_KNOWN_LAGGING_KEYS` keyed per case: listing case 5 → "no longer lags" FAIL; guard rejects rows on `reference_only` cases and count rows without `target_sections` (by reading); `--cases` needs ≥1 id and labels a partial `.gitignore` block "APPEND". After the fixes: design_sync suite 2567 passed, 10 xfailed, 1 failed (asset probe); `make types` 0 errors; ruff clean |
| E26 | Placeholder probe (Task 9b rehearsal: `reference_1x.png` from `visual_design.png` at 640, no assets) | `make fidelity-restamp CASES="reframe"` stamps 16 sections, frame 640, 0 unmarked, 0 skipped; `make fidelity-gate` PASSED; `test_fidelity_gate.py` with reframe in `CASES`: 74 passed, 1 failed (assets not committed) |

## Feature Description

Two corpus fixtures are stale for measurement. Case 5 (maap) was extracted on 2026-06-06 with the old adapter and carries no stroke, alignment, text-align or style-run fields, so outline buttons, dividers and footer links fall back to defaults that no later fix can move. Reframe has had a `structure.json` since #413 but no `tokens.json`, `reference_only: true`, and is absent from A3, the section ladder and the CE-1 gate. This ticket refreshes case 5 and makes reframe a live corpus case on every measurement surface the epic uses.

## User Story

As the engineer working the converter fidelity epic
I want maap measured from a current-schema structure and reframe measured at all
So that every later converter ticket starts from a stable baseline that can see stroke, alignment and CTA breaks on seven designs

## Problem Statement

- `data/debug/5/structure.json` lacks up to 15 fields the current parser emits (E11); fixes to strokes, alignment and text runs cannot move case 5.
- Reframe never runs through the converter in CI (`reference_only: true`, `data/debug/reframe/manifest.yaml:8`); its manifest assertions run against the hand-built HTML (`test_converter_data_regression.py:94-98`).
- CE-1's baseline and A3 (`scripts/score-fidelity-cases.py:33`) cover cases 5–10 only; the baseline also lags base by #450's four footer moves (E20).

## Solution Statement

Port the spike: offline re-parse script, case-5 structure and baselines, reframe made live with the shared tokens, a converter snapshot, strict owner-keyed `known_failures`, a ladder row, and a schema-freshness invariant. After the user's asset export, write reframe's 1x reference, commit its assets, re-stamp the gate (case 5 with per-section reasons, cases 6/8/9/10 to absorb #450, reframe as a new case), and report A3 before/after.

## Out of Scope / Non-Goals

- Not fixing any reframe failure: CTAs (#428), template font/colour defaults (#431), whole-file tokens (new ledger entry), 11-vs-12 (A2 entry). Rows are owned, not fixed.
- Not fixing the "Discover" outline CTA's `#0066cc` fill (E16); `default_blue` for case 5 is owned by #438.
- Not re-syncing cases 6–10 (ledger entry `ce-3-fixture-schema-lag-6-10`).
- Not adding reframe to other hardcoded case lists: `content_checks.py:41`, `test_outlook_ghost_arithmetic.py:56`, `test_unsubscribe_links.py:44`, `test_jev_shadow_state.py:29`, `export-case-assets.py:33` defaults. Listed as follow-ups in the report.
- No converter (non-test) module under `app/design_sync/` changes.

## Feature Metadata

**Feature Type**: Enhancement (measurement corpus)
**Estimated Complexity**: Medium (data-heavy; ~230 lines of test and script code, observed in the spike diff)
**Primary Systems Affected**: `data/debug/`, design_sync tests, fidelity scripts, CE-1 baseline, ledger
**Dependencies**: Docker/Colima (pinned Playwright image), local Playwright for A3, user-run `FIGMA_TOKEN` export (Task 9)

## Related Work

**Implements**: #421 (CE-3) · **Epic**: #439, plan `.agents/plans/converter-epic-slices.md` §CE-3 (`:95-101`)

**Back-references**: `.agents/plans/ce-1-fidelity-baseline-gate.md` (re-stamp, "Adding a case"); `.agents/plans/ce-2-content-checks.md` (allowlist ratchet; the 3 re-anchored tests; E13 footer moves = E20); `.agents/plans/49.9-data-driven-converter-regression.md` (`reference_only`, reframe manifest).

**Forward-references**: CE-10 (#428) deletes the 4 CTA rows; CE-13 (#431) deletes 2; CE-5 (#423) reuses `resync-case-structure.py` and the add-a-case path.

## Deferred Items Touching This Plan

Grep run 2026-10-02 over `.agents/deferred-items.json` (status `deferred`) for every path in this plan and phase 53/CE-3.

| id | match | decision | why |
|----|-------|----------|-----|
| `phase-53.7-asset-reexport-prerequisite` | `score-fidelity-cases`, `export-case-assets`, assets | carry forward (note appended) | CE-1 already resolved the gate half and left it open for A3, which reads untracked full-resolution `visual_design.png` (tracked only for maap). CE-3 extends the gate half to reframe; the A3 half stays open. (An early draft closed it; the code-review subagent caught it.) |
| `phase-53-a2-advisory-section-gate` | ladder files, target gates | carry forward (note appended); **owner** of reframe's 2 count rows | Reframe's 11-vs-12 is the semantic under-count class this entry tracks (E22) |
| `phase-53-d3-mammut-below-candidate-undercount` | `manifest.yaml`, `ladder_harness.py` | avoid | Only a reframe row is appended |
| `phase-53g-g7-per-side-stroke-capture` | stroke | avoid | Uniform `strokeWeight` only (E3); no renderer change |
| `phase-53g-g5-pill-white-on-light-latent` | CTA colour | avoid | Case-5 CTAs keep captured `text_color` (E16 shows no label colour change) |

New entries this plan adds (in the spike): `ce-3-file-wide-tokens-body-font` (known-bug), `ce-3-fixture-schema-lag-6-10` (speculative).

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `app/design_sync/diagnose/extract.py:256-283` — per-campaign parse and cached-token load; `scripts/resync-case-structure.py` mirrors it
- `app/design_sync/diagnose/report.py` — `dump_structure_to_json` / `load_structure_from_json`
- `app/design_sync/tests/manifest_schema.py:15-60`, `regression_runner.py:32-72`
- `app/design_sync/tests/test_converter_data_regression.py:70-139` (fixtures), `:287-298` (`_target_gate_params`), `:313-410` (manifest assertions)
- `app/design_sync/tests/test_snapshot_regression.py:53-64`, `:228-262`, `:295-334`
- `app/design_sync/tests/ladder_harness.py:46` (`_CASE_IDS`)
- `app/design_sync/fidelity_gate.py:363-364` (`_case_sort_key`, non-digit ids), `:434-438` (`gated_cases()` = dirs with `reference_1x.png`)
- `app/design_sync/tests/test_fidelity_gate.py:54` (`CASES`), `:296-320` (`TestCommittedFixtures`; `_tracked` reads `git ls-files`)
- `app/design_sync/fidelity_gate.py:45-46` imports `regression_runner`; that is why the pytest-dependent helper lives in its own `app/design_sync/tests/known_failures.py`
- `scripts/export-case-assets.py`, `scripts/prepare-fidelity-fixtures.py:35-100`, `scripts/score-fidelity-cases.py:33`, `scripts/snapshot-capture.py:33-62`
- `app/design_sync/tests/test_fidelity_case_scorer.py:18-26` (`rendered_w600.png` regen one-liner)
- `docs/fidelity-gate.md` §Re-stamping, §Adding a case; `.claude/skills/converter-fix/SKILL.md` §3–§5

### Files the spike diff touches (19)

New: `scripts/resync-case-structure.py`, `app/design_sync/tests/known_failures.py`, `data/debug/reframe/tokens.json`.
Modified: `.agents/deferred-items.json`, `app/design_sync/tests/{ladder_harness,manifest_schema,test_content_checks,test_converter_data_regression,test_snapshot_regression,test_unsubscribe_links}.py`, `data/debug/5/{expected.html,rendered_w600.png,structure.json}`, `data/debug/{ladder_snapshot.json,manifest.yaml}`, `data/debug/reframe/{expected.html,manifest.yaml}`, `scripts/{prepare-fidelity-fixtures,score-fidelity-cases}.py`.
Added after the token step (not in the diff): `data/debug/reframe/reference_1x.png`, `data/debug/reframe/assets/*.png` (16), `.gitignore` allowlist block, `data/debug/fidelity_baseline.json` stamps, `test_fidelity_gate.py:54` `"reframe"`, `docs/fidelity-gate.md`, `.claude/reports/ce-3-corpus-refresh-report.md`.

### Patterns to Follow

- **Per-param marks**: `_target_gate_params` / `_section_count_params` concatenate `known_failure_marks(cid, "<test name>")` onto their existing marks.
- **Fixture-level marks**: `apply_known_failures(request, case_id)` calls `request.applymarker` for `request.function.__name__`.
- **Two causes on one test** = two rows with different owners; the strict xfail only XPASSes when both land, and the second fixer deletes both.
- **Ledger writes**: `json.dumps(d, indent=2, ensure_ascii=False) + "\n"` (byte-identical round trip, E24).
- **Lint**: ruff `--no-fix` only; `make types` covers `app/` (strict pyright), scripts are outside its `include`.

---

## IMPLEMENTATION PLAN

### Phase 1: Port and verify the spike (no token)
Tasks 0–8. Every step re-runs its spike validation on the branch.

### Phase 2: Reframe assets and gate (token step)
Tasks 9–11. **Depends on:** the user running Task 9. Phase 1 can be committed as a green checkpoint first: `test_fidelity_gate.py` does not include reframe until Task 11, so the suite is green without assets.

### Phase 3: Record
Tasks 12–14.

---

## STEP-BY-STEP TASKS

### Task 0 — Preflight and A3 before
- **IMPLEMENT**: `git fetch && git switch -c feat/ce-3-corpus-refresh origin/main`. `/preflight-check .agents/plans/ce-3-corpus-refresh.md`. Copy untracked inputs the branch needs from the main checkout if absent: `data/debug/{5,reframe}/raw_figma.json`, `email-templates/training_HTML/for_converter_engine/*/*ual_design.png`. A3 before: `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py`, keep `scores.json` as `.tmpscratch/ce3/a3_before.json`.
- **GOTCHA**: never export `DESIGN_SYNC__SECTION_CACHE_ENABLED=false` into a pytest shell (3 false `test_section_cache` failures, observed at planning).
- **VALIDATE**: A3 table equals E14 to 3 dp.
- **SATISFIES**: AC4

### Task 1 — Apply the spike diff
- **IMPLEMENT**: `git apply .tmpscratch/ce3/spike.diff` (binary diff; includes `rendered_w600.png`). If the diff no longer applies (main moved), rebuild by hand from Tasks 2–8, which describe each part.
- **VALIDATE**: `git diff --stat` = the 19 files listed above.
- **SATISFIES**: all Phase 1 ACs

### Task 2 — Re-parse script and case-5 structure
- **WHAT**: `scripts/resync-case-structure.py` (`<case> [--node-id] [--out]`, mirrors `extract.py:256-279`, prints Figma version). Case 5 = its output.
- **VALIDATE**: `uv run python scripts/resync-case-structure.py 5 --out .tmpscratch/ce3/5.json && cmp .tmpscratch/ce3/5.json data/debug/5/structure.json` (byte-identical); `uv run python scripts/resync-case-structure.py reframe --out .tmpscratch/ce3/rf.json`, `diff` against the committed reframe structure shows only `image_ref` lines and EOF (E4); 3 nodes with non-null `stroke_color` in case 5.
- **SATISFIES**: AC2

### Task 3 — Schema-freshness invariant (RED-first, post-hoc on the branch)
- **WHAT**: `TestFixtureFreshness` + `_KNOWN_LAGGING_KEYS: dict[str, frozenset[str]]` (cases 6–10 → the 4 keys; a listed key a case now carries fails as stale) in `test_converter_data_regression.py`.
- **VALIDATE**: `git show origin/main:data/debug/5/structure.json > data/debug/5/structure.json`, run `-k freshness` → case 5 RED with the 11 keys of E15; restore with `uv run python scripts/resync-case-structure.py 5` (the re-parse is still uncommitted here); rerun → 7 passed. Mutations: empty map → 5 failed (6–10); add `"5"` to the map → case 5 fails "no longer lags" (E27); revert. Say "RED-first post-hoc" in the report.
- **SATISFIES**: AC2

### Task 4 — Case-5 baselines audit
- **WHAT**: `data/debug/5/expected.html` and `rendered_w600.png` from the re-parsed structure.
- **VALIDATE**: capture 5–10 with `scripts/snapshot-capture.py <n> --output .tmpscratch/ce3/cap/<n>.html` and diff `--ignore-all-space` against the branch's `expected.html`: all empty (the branch already holds the new case 5). Against `origin/main`'s case 5: +14/−14 in the sections of E16. `uv run pytest app/design_sync/tests/test_snapshot_regression.py app/design_sync/tests/test_fidelity_case_scorer.py -q` green.
- **SATISFIES**: AC6

### Task 5 — CE-2 tests re-anchored
- **WHAT**: `test_hash_href_is_not_an_unsubscribe_link` (`count=1` on the mutation); `test_case_5_unchanged` → `test_case_5_only_design_anchor_repointed` (exact expected output: the design anchor's href swapped, scoped to that anchor because Facebook/Strava share the URL); `test_merge_tag_href_is_not_repointed` mutates the shipped case-5 output (2 unsubscribe anchors) to `{{preferencesUrl}}` and expects a no-op.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_content_checks.py app/design_sync/tests/test_unsubscribe_links.py -q` → 171 passed; re-run E21's three mutations, record RED, revert (`git diff --quiet app/design_sync/unsubscribe_links.py app/design_sync/tests/content_checks.py`).
- **SATISFIES**: AC6

### Task 6 — `known_failures` schema, hooks, guard
- **WHAT**: `KnownFailure` + `CaseManifest.known_failures` (`manifest_schema.py`); `app/design_sync/tests/known_failures.py` (`known_failure_marks` returns one `xfail(strict=True, raises=AssertionError)` mark whose reason joins every row for that test; `apply_known_failures`); hooks in fixtures `case`/`converter_case`/`case_with_result`, `_target_gate_params`, `_section_count_params`; guard `test_known_failures_name_hooked_tests_and_owners` (test name in the hooked set, owner `#<n>` or ledger id, non-empty reason, case not `reference_only`, count rows only where `target_sections` exists).
- **GOTCHA**: the hooked set excludes `TestSectionLadder` and `test_snapshot_matches` on purpose: a ladder or snapshot row is always fixable by regenerating, so they must never be xfailed. A skip inside the test beats the fixture's xfail (case 6 `test_required_content` skips), so mutation probes must use a test that runs.
- **VALIDATE**: E23's three mutations (use `test_no_nested_p_tags[6]` for the XPASS probe) and E27's crash probe, each reverted.
- **SATISFIES**: AC3

### Task 7 — Quote/entity normalisation
- **WHAT**: `_fold_quotes` / `_decoded_text` shared by `test_required_content` and `test_component_selection`.
- **VALIDATE**: covered by Task 8's suite run (reframe "Can't make it" hint matches; cases 5–10 unchanged).
- **SATISFIES**: AC3

### Task 8 — Reframe live
- **WHAT**: `tokens.json` (copy of the shared file, E1); `reframe/manifest.yaml` `reference_only: false`, `count: 11`, 9 `known_failures` rows (E22 owners: 4 × `#428`, `test_font_family` × {`ce-3-file-wide-tokens-body-font`, `#431`}, `test_text_color` `#431`, `test_rendered_matches_target` + `test_section_count` `phase-53-a2-advisory-section-gate`); top-level `manifest.yaml` row (`sections: 11`, `target_sections: 12`); `_CASE_IDS` + `"reframe"`; `ladder_snapshot.json` reframe row (E17); `reframe/expected.html` = converter snapshot (the old file was hand-build-derived; the hand build stays at `email-templates/training_HTML/for_converter_engine/reframe_2025/manual_component_build.html`); ledger: 2 new entries + notes on `phase-53.7-asset-reexport-prerequisite` and `phase-53-a2-advisory-section-gate` (E24).
- **VALIDATE**: `uv run python -m app.design_sync.tests.ladder_harness --write` then `git diff data/debug/ladder_snapshot.json` empty (already written); `uv run pytest app/design_sync/tests/ -q -m "not integration and not benchmark and not visual_regression and not collab"` → 0 failed, 10 xfailed = 8 reframe + 2 pre-existing case 10 (E23).
- **CHECKPOINT**: `make types`, then commit Phase 1 (`feat(design-sync): re-sync maap and make reframe a live corpus case (CE-3)`), showing `git diff --stat origin/main...HEAD` first.
- **SATISFIES**: AC2, AC3, AC5, AC6

### Task 9 — Reframe assets (user-run, `FIGMA_TOKEN`)
- **IMPLEMENT**: ask the user to run in **their own terminal, outside the Claude session** (a `!` command would write the token into the transcript): `cd <repo-or-worktree> && FIGMA_TOKEN=<token> uv run python scripts/export-case-assets.py reframe`. It reads node ids from the committed `reframe/expected.html`, so it runs after Task 8.
- **VALIDATE**: `ls data/debug/reframe/assets | wc -l` = 16 = `grep -o 'design-sync/assets/[^"]*\.png' data/debug/reframe/expected.html | sort -u | wc -l`; review any file the script flags under 512 bytes. `.agents/figma-cache/exports.json` is gitignored (`.gitignore:255`).
- **SATISFIES**: AC1

### Task 10 — Reference and asset fixtures
- **IMPLEMENT**: `uv run python scripts/prepare-fidelity-fixtures.py --cases reframe` (writes `reference_1x.png` 640 × 3608, derived 7216 × 640/1280; downscales the 16 assets to ≤600px, full-res to gitignored `assets_fullres/`). Paste the printed `.gitignore` block after the case-10 block.
- **GOTCHA**: never run it without `--cases` (rewrites every case). The printed block is partial: **append** its reframe lines, do not replace the existing block. From here until Task 11, `test_baseline_covers_every_case` fails by design.
- **VALIDATE**: `git status --short data/debug` adds only reframe files; `git check-ignore data/debug/reframe/assets/*.png data/debug/reframe/reference_1x.png` prints nothing.
- **SATISFIES**: AC1

### Task 11 — A3 after and gate re-stamps
- **IMPLEMENT**: A3 after (7 rows). Then three stamps, each with its own reason:
  1. `make fidelity-restamp CASES="5" REASON="CE-3 #421: maap re-synced from raw_figma (strokes, text-align, style-run links); moved 2833:1629 -0.0013, 2833:1643 -0.0028, 2833:1650 +0.0009, 2833:1655 +0.0014, 2833:1687 +0.0043, 2833:1738 +0.0022; causes in .claude/reports/ce-3-corpus-refresh-report.md"` (re-derive the deltas from this run's `scores.json`; they must equal E19).
  2. `make fidelity-restamp CASES="6 8 9 10" REASON="CE-3 #421: absorb #450 (CE-2) footer-link moves never stamped: 6 2833:1475 -0.0011, 8 2833:2348 -0.0005, 9 2833:2149 -0.0004, 10 2833:1270 +0.0001"` (re-derive from this run; must equal E20). Purpose: the epic's "CE-3 leaves a stable baseline for every later ticket"; inputs for these cases are unchanged by CE-3 (E19).
  3. `make fidelity-restamp CASES="reframe" REASON="CE-3 #421: add case reframe"`.
  Then add `"reframe"` to `test_fidelity_gate.py:54`, `git add` the reframe fixtures, run the test module.
- **GOTCHA**: if any case-5 delta differs from E19 or any case 6–10 A3 number moves, stop (the spike says they cannot). Gate and A3 numbers are never mixed.
- **VALIDATE**: `make fidelity-gate` PASSED; `uv run pytest app/design_sync/tests/test_fidelity_gate.py -q` all green (E26 shows 74 passed + the asset test, which Task 10 turns green); `jq '.stamps[-3:]' data/debug/fidelity_baseline.json` shows the three reasons; `jq '.cases.reframe.sections | length'` = 16.
- **SATISFIES**: AC1, AC4

### Task 12 — Docs
- **IMPLEMENT**: `docs/fidelity-gate.md`: reframe row in the case table (frame 640, 16 sections, min/median/unmarked from stamp 3, tagged observed); a dated paragraph under §Re-stamping naming the three CE-3 stamps and why. Append to `docs/converter-fidelity-ceiling.md` only if its §3 cites case-5 numbers that moved (check; A3 summary metrics moved ≤0.0004, single bands up to 0.0050, E18).
- **VALIDATE**: every figure tagged observed/derived.
- **SATISFIES**: AC7

### Task 13 — Ledger check
- **IMPLEMENT**: confirm the spike's ledger edits (2 new entries with `introduced_commit: "pending"`, 2 notes, no close) and that `git ls-files 'data/debug/*/assets/*' | cut -d/ -f3 | sort -u` now lists 5–10 and reframe (the gate half the 53.7 note claims). Stamp `pending` after squash with the `deferred-items` skill.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k known_failures -q` green (owner ids resolve).
- **SATISFIES**: AC7

### Task 14 — Report and full gate
- **IMPLEMENT**: `.claude/reports/ce-3-corpus-refresh-report.md`: spike pointer; RED-first post-hoc output; E16 audit table with E12 design-truth column; E21/E23 mutations; known-failure rows with owners (E22); A3 before/after (7 rows, reframe before = n/a); gate stamp table (E19, E20, reframe); follow-ups (case lists, Out of Scope). Re-derive every figure on the branch; tag each. Then `piv-validate` (`make check-full`, includes `make fidelity-gate`), `piv-commit`, `piv-create-pr` (draft), watch CI.
- **GOTCHA**: `make check-full` runs `make lint` (rewrites) and `make test` (rewrites `skill-versions.yaml` dates); diff and restore. If `chore/stamp-ledger-pr450` has merged first, rebase; its 2-line ledger hunk applies cleanly (E24).
- **VALIDATE**: `make check-full` green on the committed head (observed).
- **SATISFIES**: all

---

## TESTING STRATEGY

### Unit Tests
- `TestFixtureFreshness` (RED-first post-hoc, mutation), `known_failures` guard + 3 mutations, CE-2 re-anchors + 3 mutations, quote normalisation via reframe.

### Integration Tests
- design_sync suite over 7 cases; `make test`; `make fidelity-gate` in the pinned image; A3 (advisory, local).

### Edge Cases

| Edge case | Verified in |
|---|---|
| Structure lagging the dump schema beyond the named lag set | Task 3 + mutation (E15) |
| Known-failure row on a test that now passes | Task 6 XPASS mutation (E23) |
| Known-failure row with a typo'd owner or test | guard test + mutation (E23) |
| Known-failure row deleted while the defect remains | Task 6 mutation (E23) |
| Skip inside a test masking its xfail | Task 6 GOTCHA (observed on case 6) |
| Design link sharing a URL with sibling links | Task 5 anchor-scoped expectation (observed failure, then fix) |
| `prepare-fidelity-fixtures` touching other cases | Task 10 `--cases` + `git status` |
| Blank asset render | Task 9 review (<512 bytes) |
| Non-digit case id in the gate | E26 (`_case_sort_key`, stamp, check) |
| Baseline drift not caused by this ticket | E20 + stamp 2's reason |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
- `uv run ruff format --check scripts/ app/design_sync/tests/` · `uv run ruff check --no-fix scripts/ app/design_sync/tests/` · `make types`

### Level 2: Unit Tests
- `uv run pytest app/design_sync/tests/ -q -m "not integration and not benchmark and not visual_regression and not collab"` · `make test` (restore `skill-versions.yaml`)

### Level 3: Integration
- `make fidelity-gate` · `make check-full` via `piv-validate`

### Level 4: Manual Validation
1. `.tmpscratch/fidelity/case5_side_by_side.png` and `casereframe_side_by_side.png` from Task 11's A3 run.
2. 600px side-by-side: `data/debug/5/expected.html` vs `maap/manual_component_build.html`; reframe at 640 vs `reframe_2025/manual_component_build.html` (expected: CTAs show as icon banners, the CE-10 starting point).
3. If a reframe gate section scores near 0, run `scripts/fidelity-gate.py check --cases reframe --dump-crops` in the image.

### Level 5: Additional
- `uv run python -m app.design_sync.tests.content_checks --empty-allowlist` — matches E10.

---

## ACCEPTANCE CRITERIA

- [ ] AC1 Reframe scored by A3 (7th row) and by the CE-1 gate (16 baselined sections, `make fidelity-gate` passes, `test_fidelity_gate.py` green with reframe in `CASES`).
- [ ] AC2 Case 5 `structure.json` carries stroke fields (3 nodes) and every case passes the schema-freshness invariant modulo the named, ledger-owned lag set.
- [ ] AC3 Reframe runs through the converter in every manifest-driven test; each failing expectation is a strict `known_failures` row with a resolvable owner.
- [ ] AC4 A3 before/after (full corpus) and a per-section gate explanation for every moved case-5 section; cases 6–10 flat.
- [ ] AC5 Ladder green with the reframe row; case 5–10 rows unchanged (13/9/8/10/8/12).
- [ ] AC6 Case-5 baselines regenerated with an audited diff; cases 6–10 byte-identical; 3 CE-2 tests re-anchored with mutation proof.
- [ ] AC7 Every baseline and ladder change recorded with its reason (3 stamps, report, docs, ledger).
- [ ] `make check-full` green on the committed head.

## COMPLETION CHECKLIST

- [ ] Tasks 0–14 in order, each VALIDATE run on the branch
- [ ] No converter (non-test) module under `app/design_sync/` changed
- [ ] `git diff --stat origin/main...HEAD` = the 19 spike files + Task 9–14 additions
- [ ] Draft PR opened; CI watched

---

## OPEN QUESTIONS / ASSUMPTIONS

- **A1** The live Figma file has not changed in a way that matters since 2026-03-21 (U1 accepts this; every fixture shares that version, E2).
- **A2** Stamp 2 (absorbing #450's unstamped footer moves into cases 6/8/9/10) is in scope because the epic names CE-3 as the ticket that leaves a stable baseline. If the user prefers CE-3 to stamp only 5 and reframe, drop stamp 2; nothing else changes.
- No other open question: the risks raised at first planning (footer alignment, owners, ledger-branch overlap) were measured (E12, E19, E22, E24).

## NOTES

- Offline re-parse equals `diagnose.extract` here: per-campaign mode parses `raw["nodes"][id]["document"]` with `_parse_node` and loads cached tokens (`extract.py:256-283`); the local raws are those node responses (E2) and the tokens are the shared file (E1).
- Reframe's committed structure is kept (only `image_ref` differs, no output effect, E4/E5); `data/debug/jev_shadow_labels.yaml:1732` labels its nodes.
- Footer `center → left` and the dark unsubscribe link are design-correct as captured (E12). Whether the design itself intends a near-invisible link on the dark footer is a design question, not a converter one.
- `.claude/hooks/pre_tool_use.py` blocks agent Bash commands that look like secret access (it fired twice during planning, once on a `.env` grep); keep the token step user-run regardless.
- The whole-file token set explains part of reframe's font failure and also affects every other case (E22); it is logged, not fixed, because changing tokens moves all baselines.

## AMENDMENTS

- 2026-10-02 — Rebuilt on a full spike (user: "address all risks"). Resolved: footer alignment and link colour are design truth (E12); case-5 gate moves are inside margin and mapped (E16, E19); all reframe owners traced (E22); ledger-branch overlap applies cleanly (E24). Added stamp 2 for #450's unstamped drift (E20). `known_failures` helper moved from `regression_runner.py` to its own module because `fidelity_gate.py` imports the runner.
- 2026-10-02 — Fresh-subagent verification. Code review (2 High, 2 Medium, 1 Medium-Low, 4 Low) → fixed in the spike: premature close of `phase-53.7-asset-reexport-prerequisite` reverted to a note; `.venv` symlink removed from the spike commit; `raises=AssertionError`; per-case lag map with stale check; guard rejects dead rows; `--cases nargs="+"` + "APPEND" label; merged two-row reasons; ledger `code_refs` with lines; A2 entry notes reframe. Claim re-check (~45 claims, 6 discrepancies) → corrected: E16 section mapping, E22 font mechanism (first "text"-named style, not most common family; manifest reason and ledger entry fixed too), E23 xfail count, E20 case-6 figure, E11 per-node wording, E18 band maximum. Spike re-committed as `b7718df4`, diff regenerated.
- 2026-10-02 — Implemented (report `.claude/reports/ce-3-corpus-refresh-report.md`). Superseded as shipped: branch base is `origin/main` `47700119` (#451 merged the ledger stamp, so no Task 14 rebase); Task 3 RED lists 15 keys (the per-case lag map gives case 5 no allowance, so the 4 shared keys show too); Task 2 `resync-case-structure.py` writes a final newline (end-of-file hook) and reframe's re-parse now differs only on `image_ref`; `.secrets.baseline` gains the 7 case-5 `image_ref` hashes (user-chosen, O1); `.pre-commit-config.yaml` large-file exemption covers `data/debug/reframe/`; Task 11 stamps were taken with `FROM=` from one pinned-image check run; Task 9 ran via a clipboard-reading scratch script in the user's terminal. Files added beyond the list: `.secrets.baseline`, `.pre-commit-config.yaml`.
