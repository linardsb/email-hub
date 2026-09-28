# Feature: G12 — Generalization insurance + Mammut seam decision (Track G · final prompt)

Validate every file:line and symbol against current `main` before editing — line numbers below are
**hints pinned to symbols** (the anchor), not addresses. **Branch off `origin/main` = `60c98bc6`**
(G11 / #365 merged 2026-07-20; the G11 item-3 loader-parity fix — `report.py:_node_from_dict` round-trips
`line_height_relative` — is on main and is the prerequisite that protects live-Figma fixture regen here).
Distinct pin: the TODO.md Track-G G-prompt file:line refs this plan must not invalidate are pinned to the
older `a660262c` (2026-07-07) — grep the symbol, not the line.

## Feature Description

Prove the converter generalizes to *any* Figma email design instead of asserting it. Three workstreams:

1. **Onboard 2–3 NEW community designs** (different authors/structure than the 6 fixtures) as cases **11–13**,
   with the honest current-converter output adopted as their baselines and A3-scored — the "first contact" test
   that every defect class G1–G11 closed still holds on unseen designs.
2. **Mammut seam decision spike** (`phase-53-d3-mammut-below-candidate-undercount`) — a time-boxed, two-arm,
   deterministic-apply attempt to close the case-10 12-vs-18 undercount behind a default-off flag, resolved
   ship-or-park with a decision doc.
3. **Close-out** — refresh the fidelity-ceiling doc with the expanded corpus, register the new flag, run the
   full gate, and update the living TODO.md Track-G status (never committed).

## User Story

As the converter's owner, I want new never-seen Figma designs scored on the same ladder as the fixtures, and
the mammut undercount either closed or documented as an honest cap — so "works on any design" is a measured
claim with new-case A3 rows as evidence, not an assertion.

## Problem Statement

- The corpus is **6 fixtures from ONE community file** (`FILE_KEY=VUlWjZGAEVZr3mK1EawsYR`). Every G1–G11 fix was
  measured only against them; nothing proves a *different author's* structure doesn't regress a closed class or
  surface a novel one. The onboarding scripts hardcode that single file key → cannot ingest foreign designs.
- **Mammut (case 10) undercounts 12 vs 18** and the gap sits **below candidate level** (raw band count = 12).
  The shipped D3 peel (`semantic_peel_enabled`, default ON) closed maap/starbucks but structurally cannot reach
  mammut (zero `mj-wrapper→single mj-section→≥2 col` shapes). The 6 missing sections are stacked content roles
  *inside* fat candidates. §C2b proved a naive structural split over-segments and the seam boundary is *semantic*.
- The ceiling doc, flag registry, and TODO status all describe a 6-case world.

## Solution Statement

- **(WS1)** Parameterize the two export scripts for foreign file keys; per new case commit
  `structure.json`+`tokens.json`+`expected.html`+per-case `manifest.yaml`, add a top-level manifest entry, extend
  the ladder `_CASE_IDS`, regen the drift snapshot; render a full-frame reference PNG and A3-score; run a
  **closed-class visual audit** classifying every defect as closed-regression / known-open / **novel** (→ ledger
  + follow-up prompt, never patched inline).
- **(WS2)** Add `DESIGN_SYNC__SEMANTIC_SPLIT_ENABLED` (default OFF). Behind it, a post-pass
  `_split_sections_by_role_seams()` at the expanded-candidate boundary emits synthetic shallow nodes at
  role-transition seams (`parent_wrapper_id=None` so they survive band grouping and raise the count). **Arm 1**:
  deterministic role-seam from the live classifier. **Arm 2** (if Arm 1 stalls, inside the time-box): VLM proposes
  seams *offline* into a committed `vlm_classifications`-style fixture, read **deterministically** at apply-time.
  Measure both on the ladder; **ship-or-park** in `.agents/plans/53-g12-mammut-seam-decision.md`.
- **(WS3)** Extend ceiling §3 tables (+ §2 per-client prose); `make .env.example` + commit; `make check-full`;
  refresh TODO.md Track-G intro rows.

## Out of Scope / Non-Goals

- **Not** patching any novel defect class the new cases surface — it goes to `.agents/deferred-items.json` + a
  follow-up prompt list, per the prompt. Only closed-class **regressions** are bugs to fix here.
- **Not** wiring the VLM into the *live* pipeline. Arm 2 is offline-proposal → committed fixture → deterministic
  read. `vlm_fallback_enabled` / `vlm_classification_enabled` stay default-off.
- **Not** changing `semantic_peel_enabled` (default-ON, shipped), band grouping, or absorb-spacer semantics.
- **Not** committing new-case **assets** or **reference PNGs** (local-only, like cases 6–10) — A3 scoring stays
  advisory/local. Only structure/tokens/expected/manifest are committed.
- **Not** editing the frozen snapshot `.agents/plans/53-g-production-readiness-prompt-sequence.md` (absent from the
  tracked tree — a no-op guardrail) and **not** committing `TODO.md` (gitignored).

## Feature Metadata

**Feature Type**: New Capability (corpus generalization) + time-boxed Spike (mammut seam) + Docs/close-out
**Estimated Complexity**: High (WS1 mechanical-but-broad + judgement-heavy audit; WS2 plumbing cheap, discriminator
is the open research question; WS3 surgical)
**Primary Systems Affected**: `scripts/` (export/extract/score), `data/debug/`, `app/design_sync/tests/ladder_harness.py`,
`app/design_sync/figma/layout_analyzer.py`, `app/core/config/design_sync.py`, `feature-flags.yaml`,
`docs/converter-fidelity-ceiling.md`, `TODO.md`
**Dependencies**: **USER must supply Figma file key(s) + a `FIGMA_TOKEN` with read access** to the new files
(hard blocker for WS1). WS2 has no external dependency.

## Related Work

**Implements**: Track G · **G12** (the only unexecuted G-prompt; TODO.md `#### G12` line ~458). **Epic**: Track G
(G1–G12); audit source `.agents/plans/53-g-production-readiness-prompt-sequence.md` (frozen, not in tracked tree).

**Back-references**:
- G11 (#365 `60c98bc6`) — item-3 loader parity protects new-case fixture regen; items 1/2 closed divider +
  decoration classes the WS1 audit must confirm hold. Two G11 entries are literally tagged "G12 territory":
  `phase-53g-g11-social-section-drops-column-content`, `phase-53g-g11-contentgroup-column-divider-gap`.
- D3 semantic peel (`.agents/plans/53-d-fork-a-execution.md` §D3; `docs/phase-53-track-c-spike.md` §C2b) — the
  prior actuator + the "boundary is semantic" finding the WS2 spike inherits.
- 53.1 fork decision (`.agents/plans/53-1-fork-decision.md`) — the decision-doc format WS2's doc mirrors.

**Forward-references**: any novel-class follow-up prompts WS1 emits (append here as created). — (none yet)

---

## CONTEXT REFERENCES

### Corpus map (READ FIRST — the prompt's "cN" = case N)

6 fixtures under `data/debug/<N>/` numbered **5–10**: **5=maap · 6=starbucks · 7=LEGO · 8=performance_reimagined
(a.k.a. "Ferrari" in G-prompts) · 9=slate · 10=mammut** (`scripts/score-fidelity-cases.py:33-40`,
`data/debug/manifest.yaml`). New cases are **11, 12, 13**. Live ladder (measured on main): render/target =
7→8/8 · 8→10/10 · 9→8/8 · **10→12/18** · 5→13/13 · 6→9/9. **Non-regression floor for WS2: 7/8/9 hold 8/10/8, 5/6
hold 13/9, mammut moves 12→toward 18.**

### Relevant Codebase Files — READ THESE BEFORE IMPLEMENTING

**WS1 — onboarding mechanics** (Agent-A-verified; two discovery paths, both must be fed):
- `scripts/extract-snapshot-cases.py` — `FILE_KEY` :28, `CASES` :31-34 (**hardcoded to cases 6/10 + one file key**).
  Fetches node → `structure.json`+`tokens.json` via `diagnose.report` dump helpers. **Parameterize.**
- `scripts/export-case-assets.py` — `FILE_KEY` :30, `DEFAULT_CASES` :33, `render_urls` :67 (Figma images API,
  scale 2, 429-backoff). Renders the *individual* image node-ids in `expected.html`. **Parameterize + add a
  full-frame reference render.**
- `scripts/snapshot-capture.py` — `python scripts/snapshot-capture.py <N> --overwrite` loads
  `structure.json`+`tokens.json` via `load_structure_from_json` (the G11-fixed loader) → `convert_document` →
  writes `data/debug/<N>/expected.html`. **This is how the baseline is adopted.**
- `app/design_sync/tests/ladder_harness.py` — `_CASE_IDS = ("5".."10")` **:46 (HARDCODED — MUST extend for
  11/12/13; drives the drift gate + `test_rendered_matches_target`)**; `SEMANTIC_UNDERCOUNT_CASES = frozenset({"10"})`
  :62 (add a new case only if it under-counts → xfail; else strict); `load_target_sections()` :80 reads top-level
  `data/debug/manifest.yaml.target_sections`; `write_ladder_snapshot()` / `--write` :251/:293 regenerates
  `data/debug/ladder_snapshot.json`.
- `app/design_sync/tests/test_converter_data_regression.py` — ladder drift `TestSectionLadder.test_ladder_no_drift`
  :266 + `test_rendered_matches_target` :300 (parametrize `discover_ladder_case_ids()` → `_CASE_IDS`); universal
  checks auto-discover `data/debug/*/manifest.yaml` (per-case manifest → **free pickup**).
- `app/design_sync/tests/test_snapshot_regression.py` — `_get_active_case_ids()` :62 reads **top-level
  manifest `status:active`** (a SECOND discovery path — the case must be in BOTH `_CASE_IDS` and the top-level
  manifest); `TestSnapshotRegression.test_snapshot_matches` :228 requires committed `expected.html`.
- `app/design_sync/tests/test_bridge_roundtrip.py` :420 — globs `data/debug/*/structure.json` → **auto-runs on
  new cases**; confirm green.
- `app/design_sync/tests/manifest_schema.py` — `CaseManifest` (per-case: `name` + `sections.count` required;
  `figma_node`, `description`, `patterns` optional). Minimal example: `data/debug/7/manifest.yaml`.
- `app/design_sync/fidelity_case_scorer.py` — `render_case_png(case_dir)` :193, `score_case_fidelity(case_dir,
  ref_bytes, rendered)` :91 (case_dir-driven, hardcodes no ids). `scripts/score-fidelity-cases.py` supplies the
  reference bytes by globbing `email-templates/training_HTML/for_converter_engine/<template>/*ual_design.png`.
- `test_outlook_ghost_arithmetic.py` — `_CASES` :56 + `_EXPECTED_GHOSTS` :64 (hardcoded; **extend BOTH or NEITHER**
  — a case in `_CASES` without `_EXPECTED_GHOSTS` KeyErrors at :253. Default: leave both; new cases simply aren't
  ghost-gated).

**WS2 — semantic-split spike surface** (Agent-B-verified):
- `app/design_sync/figma/layout_analyzer.py` — **insertion point :382** (right after
  `_expand_container_wrappers`); the live role classifier `_classify_by_content` :1058, `_get_mj_role` :1038,
  `_MJ_CONTENT_ROLES` :315-326; peel-helper neighborhood `_peel_rows` :764, `_grandkids_are_cards` :836,
  `_expand_container_wrappers` :676 (peel branch :712 — mirror its `parent_wrapper_id=None` trick + `_Y_TOLERANCE`
  row grouping); `_calculate_spacing` :609 (why synthetic-node y/height must be accurate); VLM merge param
  `vlm_classifications` threaded at `analyze_layout` :341 / merged `component_matcher.py:408-441` (Arm 2 reuse).
- `app/design_sync/protocol.py:110` — `DesignNode` (frozen dataclass → `dataclasses.replace`-able for synthetic
  split nodes: `replace(node, id=f"{node.id}:s{k}", children=slice, y=<slice top>, height=<slice bbox>)`).
- `app/design_sync/converter_service.py` — `_match_phase` :670 → `group_by_wrapper` (`sibling_detector.py:153`);
  `sections_count = len(grouped_sections)` (the rendered count the ladder reads).
- `app/core/config/design_sync.py:101` — `semantic_peel_enabled` (the flag to sit beside; **note it shipped
  default TRUE despite its plan saying off** — the new flag is a SEPARATE knob, default FALSE).
- `docs/phase-53-track-c-spike.md` §C2b (:59-95) — rejected naive recursion (LEGO 8→18, maap 9→19) + the
  semantic-boundary proof (starbucks 4 cards→4 vs perf 4 stats→1). **Read before writing the discriminator.**

**WS3 — docs/flags/close-out** (Agent-C-verified):
- `docs/converter-fidelity-ceiling.md` — §2 feature-capability table + per-client prose (:23); §3 **three per-case
  tables**: section-count ladder (:51-58), Track-F A3 (:83-90), **Track-G A3 (:132-139, the current baseline to
  extend)**; §4 residual tracker (:180, where a mammut PARK is recorded).
- `feature-flags.yaml` — schema `name/description/owner/created/removal_date/status/permanent_reason`; mirror
  `DESIGN_SYNC__SEMANTIC_PEEL_ENABLED` (:430-435). Gate: `make flag-audit` (in check + check-full) fails on a null
  `removal_date` without `permanent_reason` or an expired date.
- `app/core/config/design_sync.py` — **no `Field()`**; bare `name: type = default  # ENV_VAR` (+ optional `#`
  block). Add `semantic_split_enabled: bool = False  # DESIGN_SYNC__SEMANTIC_SPLIT_ENABLED`.
- `TODO.md` (gitignored — grep, never commit) — intro score row **:35**, Track-G header tag **:37**; G12 body
  :458-484; pin/frozen paragraph :39 (leave). **No G-prompt after G12** → "patch later G-prompts" is a no-op.
- `.agents/deferred-items.json` — the authoritative closed/open class catalog for the WS1 audit + the ship/park
  target `phase-53-d3-mammut-below-candidate-undercount` (:431).

### New Files to Create

- `.agents/plans/53-g12-mammut-seam-decision.md` — ship-or-park decision doc (WS2), mirrors `53-1-fork-decision.md`.
- `data/debug/{11,12,13}/{structure.json,tokens.json,expected.html,manifest.yaml}` — new-case fixtures (committed).
- `data/debug/{11,12,13}/assets/*.png` + `email-templates/training_HTML/for_converter_engine/<t>/…ual_design.png`
  — local-only (gitignored), for advisory A3.
- `.claude/reports/53-g12-generalization-insurance-report.md` — implementation report (untracked, house rule).

### Patterns to Follow

- **Flag-gated spike, byte-identical-when-off** (peel/band-grouping precedent): flag `False` → new helper never
  called → candidate list byte-identical → ladder + snapshot unchanged. This is Arm-1's default-off proof.
- **Synthetic-node emission** mirrors the peel branch (`layout_analyzer.py:712`): `parent_wrapper_id=None`,
  accurate `y`/`height`; the existing per-candidate loop extracts + classifies for free.
- **Decision-doc shape** (from `53-1-fork-decision.md`): The question → Measured evidence (A2 ladder + A3 table) →
  findings → Decision + Effort ledger → Deferred-items reconciliation → Sign-off.
- **New-case commit set** (Agent-A-verified minimal): `data/debug/<N>/{structure.json,tokens.json,expected.html,
  manifest.yaml}` + top-level manifest entry + `_CASE_IDS` + regen `ladder_snapshot.json`.

---

## IMPLEMENTATION PLAN

Three phases. **Phase S is independent and unblocked NOW; Phase O is HARD-BLOCKED on user Figma keys+token;
Phase C depends on both.** PR strategy (see NOTES): **Phase S ships as its own PR** (flag + split code + decision
doc + any mammut-PARK ceiling §4 note) before keys arrive; **Phases O+C ship as a second PR** once keys land. If
keys arrive first, order is O → S → C; either way the mammut decision needs only the existing 5–9 floor.

### Phase S — Mammut semantic-split spike  `[independent; unblocked; own PR; time-box ≤1–1.5 days]`
Flag → Arm 1 (deterministic role-seam) → measure → Arm 2 (VLM-fixture) only if Arm 1 stalls → ship-or-park doc.

### Phase O — Onboard cases 11–13  `[blocked_by: USER Figma keys + FIGMA_TOKEN]`
**Depends on:** user input only (not Phase S). Parameterize scripts → export/extract each case → adopt baseline →
register (two discovery paths + ladder) → reference PNG + A3 → closed-class visual audit.

### Phase C — Close-out  `[depends on Phase S + Phase O]`
Ceiling doc corpus/numbers → confirm flag registered → `make check-full` → TODO.md status → report.

---

## STEP-BY-STEP TASKS

Execute in order within a phase. Phases S and O are independent in **scope**, but both mutate
`ladder_harness.py:62 SEMANTIC_UNDERCOUNT_CASES` (S6 may remove `"10"` on ship; O4 may add `"11/12/13"`) and both
regen `ladder_snapshot.json` — so **run them sequentially** (the recommended two-PR path: S merges → O branches off
the new main), OR, if truly parallel across worktrees, O must **rebase on S** before regenerating the snapshot.
Not naively concurrent on those two files.

### Phase S — Mammut semantic-split spike

#### S1 · ADD flag `DESIGN_SYNC__SEMANTIC_SPLIT_ENABLED`
- **IMPLEMENT**: `semantic_split_enabled: bool = False  # DESIGN_SYNC__SEMANTIC_SPLIT_ENABLED` in `DesignSyncConfig`.
- **PATTERN**: `app/core/config/design_sync.py:101` (beside `semantic_peel_enabled`; **no `Field()`** — bare default
  + trailing env-var comment, optional `#` block above).
- **GOTCHA**: the peel flag is default-ON; this one is default-OFF and a separate knob. Env resolves via
  `env_nested_delimiter="__"` automatically.
- **VALIDATE**: `uv run python -c "from app.core.config import Settings; print(Settings().design_sync.semantic_split_enabled)"` → `False`.
- **SATISFIES**: AC #6 (flag registered, default-off).

#### S2 · REGISTER flag (feature-flags.yaml + .env.example)
- **IMPLEMENT**: mirror `DESIGN_SYNC__SEMANTIC_PEEL_ENABLED`: `created: "2026-07-22"`, `removal_date: "2026-10-22"`
  (~90d), `status: alpha`, `owner: design-team`, description naming the spike + default-off; **no** `permanent_reason`.
  Then `make .env.example` and commit the regenerated file.
- **PATTERN**: `feature-flags.yaml:430-435`.
- **GOTCHA**: `check-full` runs `flag-audit` (expired/null-without-reason date **fails** + blocks push) **and**
  `check-env-drift` (stale `.env.example` **fails**). Both must be satisfied here.
- **VALIDATE**: `make flag-audit` clean; `git diff --exit-code .env.example` after `make .env.example` (no residual drift).
- **SATISFIES**: AC #6.

#### S3 · IMPLEMENT Arm 1 — deterministic role-seam split (behind the flag)
- **IMPLEMENT**: `_split_sections_by_role_seams(candidates)` called once at `layout_analyzer.py:382`, guarded by
  `if get_settings().design_sync.semantic_split_enabled:`. For each candidate tuple whose node carries ≥2
  role-transition seams (v0 heuristic: contiguous slices bounded by heading-role children per `_get_mj_role` /
  `_MJ_CONTENT_ROLES`, restricted to **vertical** stacks — do NOT split horizontal ≥2-column rows, the §C2b trap),
  emit N synthetic tuples via `dataclasses.replace(node, id=f"{node.id}:s{k}", children=slice, y=<slice top>,
  height=<slice bbox>)`, `parent_wrapper_id=None`.
- **PATTERN**: peel branch `layout_analyzer.py:712` (synthetic emission + `parent_wrapper_id=None`); discriminator
  lives beside `_peel_rows`/`_grandkids_are_cards` (:764-857).
- **GOTCHA**: the seam DISCRIMINATOR is the whole spike — §C2b proved naive rules over-segment. Keep it conservative;
  LEGO (21 analyze-sections) is the over-segmentation canary; the `t=3 i=6` mammut product/nav target is closest to
  perf's cards-vs-stats shape and most likely to bleak — measure it. Synthetic `y`/`height` MUST be accurate or
  `_calculate_spacing` (:609) emits wrong gaps.
- **VALIDATE**: flag-OFF → `make snapshot-test` byte-identical; flag-ON → `python -m app.design_sync.tests.ladder_harness`.
- **SATISFIES**: AC #7 (mammut spike measured).

#### S4 · MEASURE Arm 1 on the ladder + A3
- **IMPLEMENT**: run the ladder flag-ON; record render for 5/6/7/8/9/**10**; run `uv run python
  scripts/score-fidelity-cases.py --cases 7 8 9 10` (advisory, needs local assets) for A3 deltas.
- **GOTCHA**: **ship gate** = mammut 12→toward 18 **AND** 7/8/9 hold 8/10/8 **AND** 5/6 hold 13/9 **AND** no case's
  A3 drops beyond noise. Any 7/8/9 regression = the §C2b failure mode → tighten discriminator or proceed to Arm 2.
- **VALIDATE**: capture the ladder table (both ways) into the decision doc.
- **SATISFIES**: AC #7.

#### S5 · (CONDITIONAL) IMPLEMENT Arm 2 — VLM-fixture seam (only if Arm 1 stalls, within the time-box)
- **IMPLEMENT**: an offline VLM proposes split seams per fat candidate → persist to a committed
  `vlm_classifications`-style fixture per case; the flag-gated apply reads that fixture **deterministically** (same
  input → same seams). Reuse the Phase-41.7 `vlm_classifications` param threaded into `analyze_layout` (:341) /
  merged (`component_matcher.py:408-441`); `data/debug/*/vlm_classifications.json` is gitignore-allowlisted.
- **PATTERN**: D3 plan §D3 (`.agents/plans/53-d-fork-a-execution.md:80-96`) — "deterministic baseline first, VLM to
  measure against."
- **GOTCHA**: apply-time stays deterministic (fixture read, no live LLM). This is the arm the prompt names. If the
  time-box expires before Arm 2 converges, record it as "not reached, why" — a measured negative is a valid outcome.
- **VALIDATE**: ladder flag-ON with the fixture; same ship gate as S4.
- **SATISFIES**: AC #7.

#### S6 · DECIDE — write `53-g12-mammut-seam-decision.md` (ship or park)
- **IMPLEMENT**: mirror `53-1-fork-decision.md`: The question · Measured evidence (A2 ladder both-ways + A3 table,
  per arm) · findings · **Decision** · Effort ledger · Deferred-items reconciliation · Sign-off.
  - **SHIP** (mammut converges, floor holds): keep flag default-off pending soak (or flip per user), remove `"10"`
    from `SEMANTIC_UNDERCOUNT_CASES` (:62) → its target gate flips **strict**, regen `ladder_snapshot.json`, update
    `phase-53-d3-…` ledger toward closed.
  - **PARK** (floor breaks or gap unclosed): flag stays default-off, record the residual in ceiling §4, update the
    `phase-53-d3-…` ledger note (its `closes_when` already allows "documented as honest cap"). **State the flag's
    fate in the decision doc:** a dormant default-off flag with `removal_date: 2026-10-22` will trip `flag-audit`
    in ~90d and block ALL pushes (foot-gun `reference_prepush_hook_flag_audit`) — so on PARK, either **delete the
    dormant split code + flag** or **bump `removal_date` with a `permanent_reason`**.
- **GOTCHA**: user decides ship-vs-park from the table — present numbers, recommend, don't pre-decide.
- **VALIDATE**: `make check-full` (flag-off path unchanged regardless of decision).
- **SATISFIES**: AC #7, AC #8 (decision doc exists with A2/A3 evidence).

### Phase O — Onboard cases 11–13  `[needs USER Figma keys + FIGMA_TOKEN]`

#### O1 · REFACTOR the two export scripts for foreign file keys
- **IMPLEMENT**: add per-case `file_key` + `node_id` + `id` + `name` inputs (CLI args or a small config list) to
  `extract-snapshot-cases.py` (replace module `FILE_KEY` :28 / `CASES` :31) and `export-case-assets.py` (thread a
  `file_key` into `render_urls` :67, replace `FILE_KEY` :30). Keep the existing community key as the default so
  cases 6/10 still reproduce.
- **PATTERN**: existing `render_urls` batching + 429-backoff (`export-case-assets.py:42-82`).
- **GOTCHA**: new authors ⇒ new keys — this is a real code change, not a no-op. Surgical: don't restructure, just
  parameterize.
- **VALIDATE**: dry-run against case 6 with its known key → byte-identical `structure.json` to committed.
- **SATISFIES**: AC #1.

#### O2 · EXPORT + EXTRACT each new case
- **IMPLEMENT**: for each user-supplied `(file_key, node_id)`: run extract → `data/debug/<N>/structure.json`
  +`tokens.json`; run export-assets → `data/debug/<N>/assets/*.png` (local-only); render the **full campaign
  node** at scale 2 → `email-templates/training_HTML/for_converter_engine/<template>/visual_design.png` (local-only,
  the A3 reference the scorer needs — neither script produced this before).
- **GOTCHA**: `FIGMA_TOKEN` must have read access to the new files (403 otherwise). Reference PNG + assets stay
  gitignored (do NOT add allowlist exceptions).
- **VALIDATE**: files exist + non-trivial sizes; `_open` reports no 403/blank renders.
- **SATISFIES**: AC #1, AC #4.

#### O3 · ADOPT baseline + HAND-COUNT target
- **IMPLEMENT**: `python scripts/snapshot-capture.py <N> --overwrite` → `expected.html`; open it + the design;
  hand-count the **visual** sections → `target_sections`; note the converter's current `sections_count`.
- **GOTCHA**: `snapshot-capture` uses the G11-fixed `load_structure_from_json` — this is exactly the loader-parity
  path G11 protected; confirm `line_height_relative` survives if the design uses AUTO/% line-heights.
- **VALIDATE**: `expected.html` renders in a browser; counts recorded.
- **SATISFIES**: AC #1, AC #5.

#### O4 · REGISTER each case (BOTH discovery paths + ladder)
- **IMPLEMENT**: (a) per-case `data/debug/<N>/manifest.yaml` (`CaseManifest`: `name`, `figma_node`, `description`,
  `sections.count`); (b) top-level `data/debug/manifest.yaml` entry (`id`, `name`, `source`, `figma_node`,
  `sections`=current, `target_sections`=hand-count, `status: active`, `design_image: false`, `visual_threshold:
  0.95`); (c) extend `ladder_harness.py:46 _CASE_IDS` with `"11","12","13"`; (d) add to `SEMANTIC_UNDERCOUNT_CASES`
  :62 **only if** the case under-counts; (e) `python -m app.design_sync.tests.ladder_harness --write` → commit
  `ladder_snapshot.json`.
- **PATTERN**: existing entries in both manifests; `data/debug/7/manifest.yaml` (minimal per-case).
- **GOTCHA**: **two discovery paths** — `_CASE_IDS` (ladder/regression) AND top-level manifest `status:active`
  (snapshot suite). Miss either → that gate silently skips the case. `design_image:false` keeps
  `test_snapshot_visual.py` dormant (no `design.png` needed).
- **VALIDATE**: `make converter-data-regression` + `make snapshot-test` both **collect** 11/12/13 (not skip);
  `test_bridge_roundtrip.py` green on the new structures.
- **SATISFIES**: AC #1, AC #2.

#### O5 · CLOSED-CLASS VISUAL AUDIT (the "first contact" test)
- **IMPLEMENT**: eyeball each new render vs its design for every G1–G11 **closed-class signature** (derive the list
  from `.agents/deferred-items.json` `status:closed` converter entries) — at minimum: decorations at native size
  (not ballooned); in-column/band horizontal rules present; button padding from auto-layout + radius from Figma
  (square=0, not 4px); CTA label color matches design; image `alt` meaningful (no raw node-name / empty); footer
  legal + logo present; band bg/spacing continuity; composite cards/spec-tables render inner content; typography
  tokens applied. Classify each defect — **G12 patches NOTHING inline** (prompt instruction); every finding is
  recorded and its fix deferred to a follow-up prompt, so the O3 baseline is never re-cut:
  - **closed-class regression** (a shipped G1–G11 fix broke on a new author's structure) → `known-bug` ledger
    entry + a **high-priority** follow-up prompt (fix deliberately later with its own RED test — do NOT hot-patch
    here; that would invalidate the just-locked O4 baseline and conflate onboarding with a bug-fix).
  - **known-open** (matches a `deferred` entry, e.g. social-section-drops-column-content, large-decorative-photo,
    per-side stroke, ContentGroup-column-divider) → note + carry forward.
  - **novel class** → NEW `.agents/deferred-items.json` entry + a follow-up prompt appended to the plan's
    Forward-references / a `53-g13-*` prompt list.
- **GOTCHA**: this AC is **not** a byte-gate — the adopted `expected.html` freezes whatever the converter emits, so
  a baked-in closed-class defect passes the snapshot silently. Only the manual visual audit falsifies it. Because
  G12 fixes nothing, O4 (register/validate) safely precedes O5 (audit) — the baseline is stable.
- **VALIDATE**: audit checklist recorded in the report; ledger updated; follow-up prompts listed.
- **SATISFIES**: AC #3, AC #5.

#### O6 · A3-SCORE the new cases (advisory baseline)
- **IMPLEMENT**: add `"11"/"12"/"13": "<template>"` to `scripts/score-fidelity-cases.py:33` CASES; run
  `uv run python scripts/score-fidelity-cases.py --cases 11 12 13`; record full_image / section_min / section_median
  as the **honest baseline** rows.
- **GOTCHA**: advisory/local-only (needs the O2 reference PNG + assets). Not a CI gate.
- **VALIDATE**: scores.json + composites written; rows captured for the ceiling doc + decision doc.
- **SATISFIES**: AC #4.

### Phase C — Close-out

#### C1 · UPDATE ceiling doc §2/§3 (expanded corpus + refreshed numbers)
- **IMPLEMENT**: add 11/12/13 rows to §3 section-count ladder (:51-58) + §3 Track-G A3 table (:132-139); expand §2
  per-client prose to note the new authors' structures; if mammut PARKed, record its residual in §4.
- **GOTCHA**: §2 has no per-case numbers (feature-level) — the numeric rows are all §3. Keep §3 baseline
  provenance honest (state the main SHA the numbers were measured on).
- **VALIDATE**: doc renders; tables well-formed; case count now 8–9.
- **SATISFIES**: AC #8.

#### C2 · CONFIRM flag registered (from S2) + full gate
- **IMPLEMENT**: verify `feature-flags.yaml` + `.env.example` carry the flag (done in S2 if S ran first; else do it
  here). Run `make check-full`.
- **VALIDATE**: `make check-full` green (lint + types + tests + security + golden + flag-audit + env-drift +
  migration lint).
- **SATISFIES**: AC #6, AC #9.

#### C3 · UPDATE TODO.md Track-G status (NEVER commit)
- **IMPLEMENT**: refresh the intro score row (:35) + Track-G header tag (:37) if scores moved / cases added; mark
  G12 done. Leave the pin/frozen paragraph (:39).
- **GOTCHA**: `TODO.md` is gitignored (`/TODO.md`) — edit on disk, never stage. "Patch later G-prompts" = no-op
  (G12 is last); "don't edit the frozen snapshot" = no-op (absent from tree) — keep both as guardrails.
- **VALIDATE**: `git status` shows `TODO.md` untracked/ignored (not staged).
- **SATISFIES**: AC #10.

#### C4 · WRITE the implementation report
- **IMPLEMENT**: `.claude/reports/53-g12-generalization-insurance-report.md` — corpus movement, audit results +
  novel-class list, spike decision + ladder tables, gate output, deviations.
- **VALIDATE**: report complete.
- **SATISFIES**: AC #10.

---

## TESTING STRATEGY

### Unit / component
- WS2 Arm 1: a flag-ON test asserting a known mammut fat candidate splits into ≥2 sections at a role seam, and a
  flag-OFF test asserting byte-identical candidate output (the default-off proof). A control asserting a horizontal
  ≥2-column row (perf-shape) is **not** split.
- WS1 O1: a script-parameterization test (case-6 known key → committed `structure.json` byte-identical).

### Integration / corpus (the diff-audit)
- `make snapshot-test` + `make converter-data-regression` must **collect** 11/12/13 and pass; `test_bridge_roundtrip`
  auto-runs on the new structures. WS2 flag-OFF leaves all existing baselines byte-identical.

### Edge cases
- New case that under-counts (→ `SEMANTIC_UNDERCOUNT_CASES`, xfail) vs on-target (strict).
- New case whose design uses AUTO/% line-heights (exercises the G11 loader fix).
- Foreign file key with a `FIGMA_TOKEN` lacking access (403 handled with a clear error).
- Mammut Arm-1 discriminator firing on the `t=3 i=6` product/nav target (perf-shape leak) — must be caught by the
  7/8/9 floor.

---

## VALIDATION COMMANDS

### Level 1 — Syntax & types
`uv run ruff check --no-fix <touched> && uv run pyright <touched>`

### Level 2 — Unit
`uv run pytest app/design_sync/tests/ -k "ladder or snapshot or split or bridge_roundtrip" -q`

### Level 3 — Corpus / integration
`make snapshot-test` · `make converter-data-regression` · `python -m app.design_sync.tests.ladder_harness`

### Level 4 — A3 pixel fidelity (advisory, local, Playwright+assets)
`uv run python scripts/score-fidelity-cases.py --cases 7 8 9 10 11 12 13`

### Level 5 — Full gate
`make check-full` (includes `flag-audit` + `check-env-drift` — both fail on flag/`.env.example` mistakes).

---

## ACCEPTANCE CRITERIA

- [ ] **AC #1** — 2–3 new designs (different authors) onboarded as cases 11–13 with committed
      `structure.json`+`tokens.json`+`expected.html`+per-case `manifest.yaml` and a top-level manifest entry.
- [ ] **AC #2** — Both discovery paths + the ladder include 11/12/13; `make converter-data-regression` +
      `make snapshot-test` collect (not skip) and pass; `ladder_snapshot.json` regenerated + committed.
- [ ] **AC #3** — Closed-class visual audit run per new case; each G1–G11 **closed** class either holds on first
      contact OR its regression is recorded (ledger + high-priority follow-up). ALL findings (closed-class
      regressions, known-open, novel) are ledgered + follow-up-prompted, **never patched inline** — G12 measures,
      it does not fix; the `expected.html` baseline is never re-cut.
- [ ] **AC #4** — New-case A3 rows (full_image/section_min/section_median) recorded as the honest baseline (advisory).
- [ ] **AC #5** — 8–9-case ladder table produced (`target_sections` hand-counted per new case).
- [ ] **AC #6** — `DESIGN_SYNC__SEMANTIC_SPLIT_ENABLED` added (config, default-off, no `Field()`), registered in
      `feature-flags.yaml` (future `removal_date`), `.env.example` regenerated; `make flag-audit` clean.
- [ ] **AC #7** — Mammut spike executed (Arm 1; Arm 2 if Arm 1 stalls within the time-box), measured on the ladder
      + A3 with the 7/8/9=8/10/8 floor; flag-OFF leaves the corpus byte-identical.
- [ ] **AC #8** — `53-g12-mammut-seam-decision.md` records the ship-or-park decision with the A2/A3 evidence table;
      ceiling doc §2/§3 updated for the expanded corpus (+ §4 if PARK).
- [ ] **AC #9** — `make check-full` passes (zero regressions).
- [ ] **AC #10** — TODO.md Track-G intro status refreshed (never committed); implementation report written.

---

## COMPLETION CHECKLIST

- [ ] Phase S: flag added + registered; Arm 1 (+Arm 2 if needed) measured; decision doc written; flag-off proof green.
- [ ] Phase O: scripts parameterized; 3 cases exported/extracted/adopted/registered/audited/scored.
- [ ] Phase C: ceiling doc updated; `make check-full` green; TODO.md refreshed (unstaged); report written.
- [ ] `git diff` reviewed for parallel-work leakage; TODO.md + local-only assets/reference PNGs NOT staged.
- [ ] Ledger: `phase-53-d3-…` updated per decision; novel entries added; two G11 "G12 territory" entries checked
      against the new cases.

---

## OPEN QUESTIONS / ASSUMPTIONS

- **[BLOCKER] Figma keys + token** — WS1 (Phase O) cannot start until the user supplies the file key(s) + a
  `FIGMA_TOKEN` with read access. WS2 (Phase S) proceeds independently. *Assumption:* the new designs are real
  community email designs with a single top campaign node each (like the fixtures).
- **vlm_fallback path is dead/test-only** — the prompt names it, but `match_section_with_vlm_fallback` is unwired and
  LLM-based, while the prompt demands *deterministic apply*. **Resolution:** Arm 1 uses the LIVE deterministic role
  classifier; Arm 2 uses the VLM to propose seams *offline* into a committed fixture read deterministically
  (satisfies both "the vlm path" and "deterministic apply"). Flag if the user intended live-VLM wiring instead.
- **Spike outcome is genuinely open** — §C2b shows the seam boundary is semantic; the deterministic discriminator
  may not separate mammut's targets from perf's stat row without regressing case 8. The plan does not assume ship;
  the *decision doc with measured evidence* is the deliverable either way.
- **Case count 2 vs 3** — "8–9 case ladder" ⇒ 2 or 3 new cases. Assume 3 if the user provides 3 keys; 2 is
  acceptable. More cases = stronger insurance.
- **PR strategy** — one plan, two PRs (S standalone, then O+C). Stated so the spike can merge before keys arrive; the
  user may instead prefer a single PR — either is compatible with this plan.

## NOTES (open canvas)

**Why two arms (advisor-corrected).** "Deterministic apply" ≠ "no VLM." The repo commits `vlm_classifications.json`
per case and threads it into `analyze_layout` (Phase 41.7). A VLM that proposes seams offline into a committed
fixture, read deterministically at apply-time, IS deterministic apply AND is the arm the prompt names — it's the D3
"baseline-first, VLM-to-measure-against" pattern. Arm 1 (deterministic role-seam) goes first because it's cheap and
may thread the needle on mammut's *vertical* editorial stacks; Arm 2 only if Arm 1 stalls, inside the time-box. A
park that never tried the prompt-named mechanism is a weak decision; "Arm 1 failed on X, Arm 2 reached/not-reached
because Y" is a strong one.

**Why §C2b doesn't pre-decide PARK.** That trap was the *peel* on **horizontal** 4-column rows (starbucks cards vs
perf stats — same shape, opposite answers). Mammut's targets are mostly **vertical** stacks (`t=6 i=2` editorials);
a heading→heading vertical seam need not trigger the cards-vs-stats ambiguity, so perf (case 8) can stay untouched.
BUT mammut's `t=3 i=6` product/nav target is closer to perf's shape — that's the one to watch on the 7/8/9 floor.

**Insertion = Option B** (post-pass at :382, naming-agnostic) over Option A (an `elif` inside
`_expand_container_wrappers`) — Option A inherits the MJML + `wrapper_unwrap_enabled` gates and can't reach mammut's
exploded-band editorial targets (emitted by the container-unwrap branch, not seen as candidates).

**Decoupling.** The mammut decision needs only the existing 5–9 floor (mammut = case 10). The 8–9-case ladder is
*confirmation* for the decision doc, not a dependency — so Phase S ships even if keys arrive late.

**700-line discipline.** The spike's measured evidence, per-arm ladder tables, and §C2b prior-art live in the
**decision doc**, not here — this plan carries only the insertion point, the two arms, and the gate.

## VERIFICATION LOG (evidence, gathered 2026-07-22 against `origin/main 60c98bc6`)

- **Ladder measured live** (Agent B ran `ladder_harness`): 7=8/8 · 8=10/10 · 9=8/8 · **10=12/18** · (5=13/13 · 6=9/9
  from manifest). Non-regression floor confirmed.
- **Two discovery paths** (Agent A, `git ls-files` + test reads): `ladder_harness.py:46 _CASE_IDS` hardcoded (ladder
  gates) vs `test_snapshot_regression.py:62` top-level manifest `status:active` — both must be fed. `structure.json`
  /`tokens.json`/`expected.html`/`manifest.yaml` ARE committed (gitignore allowlist); assets + reference PNGs
  local-only. **Corrects stale memory** `reference_local_converter_tests_red`: new cases are CI-gated on
  section-count + byte-snapshot (settle converter output before committing `expected.html`).
- **Spike surface** (Agent B): `vlm_fallback` path dead/test-only; live role signal = `_get_mj_role`/
  `_MJ_CONTENT_ROLES`/`_classify_by_content`; insertion :382; peel `parent_wrapper_id=None` trick at :712;
  `semantic_peel_enabled` shipped default-ON.
- **Docs/flags** (Agent C): ceiling §3 tables at :51-58 / :132-139; `feature-flags.yaml` schema + SEMANTIC_PEEL
  analogue :430-435; `design_sync.py` uses no `Field()`; `check-full` runs flag-audit + check-env-drift; TODO.md
  gitignored, G12 is the last G-prompt, frozen snapshot absent from tracked tree; `a660262c` = real 51.3/#329 commit.

## AMENDMENTS

- (empty at creation)
