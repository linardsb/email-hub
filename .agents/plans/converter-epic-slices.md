# Converter fidelity epic: ticket slices

Status: **created on GitHub** (2026-09-30): epic #439, tickets #419–#438, CE-25 as #448 (mapping table below; #440–#443 are CE-21 to CE-24 from another session, not sliced here). Issues get created only after the user says "create".
Source: converter epic brief 2026-09-29 (vault, not in repo). §6a and its "Revised sequence for the epic" win over §8/§9 wherever they differ.
Base: origin/main `da8dbd86` (observed: `git fetch` 2026-09-29, origin/main == `da8dbd86`). Branch `plan/converter-epic-slices`.
Line refs below were re-verified at `da8dbd86` (observed, read-only scout pass 2026-09-29). They replace the brief's refs where the two differ.
Re-check 2026-09-30 (observed: `git fetch`, origin/main == `31598a90`): the eight new commits touch none of the cited converter, scorer, CI or template paths (`git diff --stat da8dbd86 origin/main`), so the refs stand.

**Answers recorded 2026-09-30:** Q1 larger O3 sample (CE-15), Q2 keep CE-16, Q3 pull CE-17 forward, Q6 three or more held-out files (CE-5), Q7 CE-19 spike on maap plus one held-out design. Q4 (Figma token) and Q5 (Outlook source) stay open. D1 = yes (2026-09-30).

**D1 (authorisation to build) = yes** (user, 2026-09-30, when CE-1 started). CE-1 (#419) merged 2026-10-01 as #446.

## Epic summary

Figma-to-email output renders in the right order and stacks on mobile, but design styling does not survive (colours, fonts, padding, widths, button shapes). The epic first builds a regression gate that can see those breaks. It then fixes the causes the audit named (R1–R10) on the current template architecture. Last, a spike tests whether compiling from primitives (O1) should replace template filling for the remaining T8 work.

**Target is any well-built Figma email, not the seven fixtures.** The fixtures are evidence that a failure class exists; they are not the thing being fixed. All seven were built with the Email Love plugin, so the corpus is biased towards clean files; CE-5 adds held-out files the fixes are never tuned on.

Already done, not re-sliced: T1 (#409/#410), AI-layer import (#404), Jev shadow classifier (#413). The T2–T8 drafts are absorbed below (mapping in the last table).

## Conventions every ticket carries

| Rule | Applies to |
|---|---|
| Failing test first (RED), then the fix | every converter-output ticket |
| 600px side-by-side of the affected case against `email-templates/training_HTML/for_converter_engine/<design>/manual_component_build.html`; performance has no hand build, so compare against its `visual_design.png` | every converter-output ticket |
| `make check-full` green on the head; section-count ladder unchanged (`test_ladder_no_drift`, `app/design_sync/tests/test_converter_data_regression.py:266`, rendered counts 13/9/8/10/8/12 for cases 5–10) | every converter-output ticket |
| Full-corpus A3 before/after (`scripts/score-fidelity-cases.py`); a non-target drop beyond scorer jitter stops for the user's ratification (`converter-fix` skill) | every converter-output ticket |
| Per-section fidelity gate from CE-1 passes, or the baseline is re-stamped with a stated reason | every converter-output ticket after CE-1 merges |
| Report at a named path; figures tagged observed / derived / expected | shadow and measurement tickets |
| Pass rule written and committed before any label is read: breaks = 0, fixes ≥ 1, n ≥ 16, Wilson 95% lower bound ≥ 0.80, leave-one-design-out (the #413 rule) | Jev and VLM tickets (CE-15, CE-16) |
| Issue bodies cite P/R/T codes only: no vault paths, no forum contributor names | every issue (repo is public) |
| Figures copied from the brief are tagged "brief, not re-run" until a ticket re-derives them | every issue |
| **Generality rule.** A fix is a rule on Figma structure (node type, auto-layout fields, text presence, geometry ratios), never keyed on a design name, node id, fixture colour or fixture pixel value. Its unit test builds a minimal Figma node tree for the failure class (Figma input, not email HTML, so the real-fixtures rule holds); the fixture is the regression evidence. The done check states an invariant over every case, not a result for one design | every converter-output ticket |
| Held-out check: once CE-5 lands, no per-section drop on the held-out cases beyond the margin, and their scores are never used to tune a fix | every converter-output ticket after CE-5 |
| "Wrong if" lines marked (brief) are quoted from the brief; lines marked (derived) are written here because the brief has none | every ticket |

## Case map (observed at HEAD)

| Case | Design | Committed inputs | Hand build | In `CASES` |
|---|---|---|---|---|
| 5 | maap | structure, tokens, assets, `rendered_w600.png`, `visual_design.png` | yes | yes |
| 6 | Starbucks | structure, tokens | yes | yes |
| 7 | Lego | structure, tokens | yes | yes (no reference PNG in repo) |
| 8 | performance | structure, tokens | no (`hub_converter_build.html` only) | yes |
| 9 | slate | structure, tokens | yes | yes |
| 10 | mammut | structure, tokens | yes | yes |
| reframe | reframe | `expected.html` (= hand build), manifest; `reference_only: true` | yes | no |

`raw_figma.json` and reference PNGs other than maap's are gitignored or untracked (`.gitignore:138-146`).

## Tickets needing user input

| Input | Blocks | Why |
|---|---|---|
| Figma token | CE-3 (reframe regeneration, maap re-sync) | Both need a live Figma REST pull. Give it early: CE-3 re-stamps the CE-1 baseline, so every converter ticket that starts after CE-3 inherits a stable baseline. |
| Outlook render source: Litmus Instant API vs manual | CE-4, CE-11 Outlook check, CE-19 kill test 3 | Brief: Litmus Instant API returns client screenshots (sourced, not tried); Email on Acid API not verified; Mailpit renders nothing. |
| Three or more non-Email-Love Figma files (Q6 answered: three or more; the files themselves are still needed) | CE-5, the held-out check on every converter ticket, wrong-if checks in CE-6, CE-16, CE-18, CE-15 transfer | All 7 fixtures were built with the Email Love plugin (auto-layout everywhere, ~90% `mj-*` names, brief). One file shows whether transfer fails; it cannot show that it holds. |

## Tickets

### CE-0: Epic issue

- Body: the epic summary above, the conventions table, and the task-list rows in the shape `.claude/skills/piv-next/next.sh` parses (see "Epic task list" at the end). Label `epic` (create the label once if missing).

### Wave 1: measurement (sequence step 1)

#### CE-1: Per-section fidelity baseline gate

- **Closes:** no R-cause directly. Makes R1–R9 measurable; covers P4 and A4, and the scorer half of T7.
- **Scope:**
  1. Commit `data/debug/fidelity_baseline.json`: per case, per section id, the section score from `visual_scorer.score_fidelity` (`app/design_sync/visual_scorer.py:137`). Fail when a section drops more than a set margin below its own baseline (no fixed absolute cut; brief: healthy bands score 0.65–0.9, not re-run).
  2. Slice the rendered HTML by section id, not by design y, so vertical drift does not misalign bands.
  3. Commit downscaled (600px-wide) reference PNGs for cases 5, 6, 8, 9, 10. Lego (7) has no reference PNG in the repo: mark it skipped in the baseline with that reason.
  4. Add Chromium to the backend CI job (`.github/workflows/ci.yml:22`; today only the frontend job installs it, `:367-368`). Pin OS image and Playwright version.
  5. Delete the two stub metrics hardcoded to 1.0 (`app/design_sync/tests/regression_runner.py:121`, `:136`; fields `:100`, `:103`).
  6. Add a documented re-stamp command (make target) with a required reason string, used by CE-3 and by any ticket that improves a section.
- **Runs where (expected, not yet run):** CI, on committed `structure.json` + `tokens.json` + downscaled PNGs only. Nothing in the gate reads gitignored `raw_figma.json`.
- **Image assets (observed):** case 6, 9 and 10 outputs reference `/api/v1/design-sync/assets/2833:<id>.png`; only case 5 has committed assets (`data/debug/5/assets/`). Without an asset step, image bands render broken in CI and their baselines mean nothing. Scope therefore includes committing downscaled assets for cases 6–10 (or a deterministic placeholder with those bands excluded, decided at planning), served to the renderer offline.
- **Comparability:** scores against downscaled PNGs are not comparable to historical full-resolution A3 figures; later tickets report one or the other, never mixed.
- **Done check:** (a) two CI runs on the same head produce per-section scores within the margin; (b) sensitivity proof: locally revert #409's `_fills_social` change and the gate fails on Starbucks or mammut; (c) section-id slicing proof: a change that only redistributes height (the G11 icon-shrink kind, which moved design-y band scores both ways) leaves unchanged sections within the margin; (d) report `docs/fidelity-gate.md` with the margin, how it was chosen, and the observed run-to-run spread.
- **Wrong if (brief):** two CI runs differ by more than the margin, or mammut and Starbucks don't fall below baseline before their fixes (made testable here as the #409 revert).
- **Files (estimate):** `visual_scorer.py`, `scripts/score-fidelity-cases.py`, new `app/design_sync/tests/test_fidelity_gate.py`, `regression_runner.py`, `ci.yml`, `Makefile`, reference PNGs, assets for 6–10, baseline JSON. ~800–1200 lines incl. tests.
- **Depends on:** none.

#### CE-2: Content checks the pixel mean cannot see (T7 task 3)

- **Closes:** no R-cause. Detects R1 regressions, R5, the R4 `#0066cc` leak and CTA loss (R2/R3).
- **Scope:** four per-case checks over converter output, each comparing to the design, not to a constant: (1) unsubscribe link present when the design has unsubscribe text; (2) every `font-family` ends in a generic family; (3) no `#0066cc` unless the design contains it; (4) CTA count ≥ design CTA count. Known current failures sit in a committed allow-list keyed to the ticket that fixes each (CE-7 for fonts, etc.); a new failure not on the list fails the test.
- **Done check:** RED on current main for at least one check on mammut or Starbucks (expected: font generic family, since T4 is open); allow-list entries retire as their tickets merge; report of current failures in the PR body.
- **Wrong if (brief, T7):** the new check does not fail on current main for mammut or Starbucks.
- **Files:** new `app/design_sync/tests/test_content_checks.py` + small helper module. ~400–600 lines.
- **Depends on:** none. Parallel with CE-1 (no shared files).

#### CE-3: Corpus refresh: re-sync maap, regenerate reframe (T7 tasks 1–2) — needs Figma token

- **Closes:** measurement blind spots: maap snapshot lacks stroke fields (outline buttons fall back to blue); reframe has never run through the current converter.
- **Scope:** re-sync case 5 `structure.json`; run `python -m app.design_sync.diagnose.extract` for reframe (node `2833-1491`, brief); set `reference_only: false`; add reframe to `CASES` (`scripts/score-fidelity-cases.py:33`), to `ladder_snapshot.json`, and to the CE-1 baseline via its re-stamp command. Record every baseline and ladder change with its reason.
- **Done check:** reframe scored by A3 and by the CE-1 gate; case 5 structure carries stroke fields; ladder test green with the new row; before/after A3 table for case 5.
- **Wrong if (derived):** re-synced maap changes non-stroke structure enough to move case-5 sections the gate had baselined (then the re-stamp needs a per-section explanation before merge).
- **Files:** `data/debug/5/*`, `data/debug/reframe/*`, `data/debug/manifest.yaml`, `ladder_snapshot.json`, `fidelity_baseline.json`, `score-fidelity-cases.py`. Mostly data; ~200 lines code.
- **Depends on:** CE-1 (needs the re-stamp command). Needs input: Figma token.

#### CE-4: Outlook render source decision and one render per design (T7 task 4, part of A6) — needs input

- **Closes:** blind spot: no real Outlook or inbox render exists in the repo; all Outlook findings (R10) are inferred from markup.
- **Scope:** first inventory the existing render code in `app/rendering/` (`litmus/`, `eoa/`, `local/` emulators, `gate.py`, `visual_diff.py`; observed 2026-10-01, wiring to the converter not checked) and reuse it if it works; then record the decision (Litmus Instant API vs manual) in `docs/outlook-render-source.md`; produce one classic-Outlook render per design from current main. Where they are stored (repo, downscaled, or an external path) is decided in the ticket against repo size.
- **Done check:** decision doc merged; one render per design stored or linked; report lists what each render shows about buttons (baseline for CE-10).
- **Wrong if (derived):** the chosen source cannot render the classic Outlook engine (Word renderer), only new Outlook.
- **Files:** docs + a small script if API. ~100–300 lines.
- **Depends on:** none. Needs input: render source (and API credentials if Litmus).

#### CE-5: Held-out corpus of non-Email-Love designs — needs input

- **Closes:** no R-cause. Tests transfer: P2 wrong-if "a real client file has no `layoutMode`", P5 wrong-if "disagreement rates shift on non-Email-Love designs", Jev name-leak concern.
- **Scope:** extract three or more files, ideally from different builders (hand-built without auto-layout, another plugin, a client design team), as new `data/debug/<n>/` cases marked `held_out: true`; add to `CASES`, ladder and baseline; report auto-layout coverage (share of frames with `layoutMode`, sizing field counts) and name conventions per file in the style of the brief's P2 table. Record the current per-section scores before any wave-2 fix merges, so every later fix is measured against a design it never saw.
- **Done check:** report `docs/held-out-corpus.md`; each case scored by A3 and the gate; held-out flag enforced (the gate reports these cases separately).
- **Wrong if (brief, P2):** a real client file has no `layoutMode` (then CE-6/CE-16 need the `tree_normalizer` fallback, `app/design_sync/figma/tree_normalizer.py:192`, which has no confirmed test).
- **Depends on:** CE-1. Needs input: the files (and the Figma token). Priority: land before wave 2 if the files exist, so every fix has a held-out check.

### Wave 2: first converter fixes (sequence step 2, plus T2/T3/T5/T6 alongside)

#### CE-6: Read auto-layout sizing fields (P2 step 1)

- **Closes:** nothing visible on its own. Prerequisite for R6 (CE-11) and the width part of R9 (CE-12).
- **Correction to the brief (observed):** the width source is not "never read". `email_design_document.py:1597-1602` sets `container_width` from `layout.overall_width` (widest top-level frame, `layout_analyzer.py:394`) clamped to 400–800, and case 9 `expected.html` already carries 10× `width="640"` next to 8× `width="600"`. So R9 at HEAD is mostly templates baking 600, not a missing read. This ticket verifies the source instead of rewriting it.
- **Scope:** declare `layoutSizingHorizontal/Vertical`, `layoutGrow`, `layoutAlign`, `layoutPositioning`, `layoutWrap`, `minWidth/maxWidth` in `app/design_sync/figma/raw_types.py` (none declared today); read them in `figma/service.py:408-422`; carry them onto the analysed nodes. Take email width from the root frame and assert it equals `container_width` for every case. No behaviour change to column widths in this ticket.
- **Done check:** unit tests on parsing each field; a per-case test that root width = `container_width` (600 or 640); all corpus outputs byte-identical (read-and-record only); counts per design match the brief's P2 table (re-derived, tagged observed).
- **Wrong if (brief, P2):** a real client file has no `layoutMode` (checked once CE-5 lands).
- **Files:** `raw_types.py`, `figma/service.py`, `layout_analyzer.py` (node model), tests. ~400–600 lines.
- **Depends on:** CE-1.

#### CE-7: Font fallback stacks by category (T4)

- **Closes:** R5.
- **Scope:** one stack builder: sans → `Helvetica, Arial, sans-serif`; serif → `Georgia, 'Times New Roman', serif`; mono → `'Courier New', Courier, monospace`, chosen from the Figma font's category. Route every font write through it: `_replace_heading_font` (`component_renderer.py:1540`), `_replace_body_font` (`:1547`), dispatch at `:1464/:1468`, the font regexes at `:368-398`, and the matcher's generic fallback (grep `sans-serif` in `component_matcher.py`).
- **Done check:** RED first via CE-2's font check (fails on mammut and Starbucks today), then green on every case and allow-list entry removed; test on the builder per category, including a font family the corpus does not contain. Evidence: mammut "BUILD YOUR LAYERS" renders mono at 600px side-by-side.
- **Wrong if (derived):** mammut CTAs still render in a serif after every write carries a stack (then the cause is a missing hook, which is plumbing for CE-13).
- **Files:** `component_renderer.py`, `component_matcher.py`, new builder module, tests. ~300–500 lines.
- **Depends on:** CE-2.

#### CE-8: Image-with-caption columns rendered as background images (T2)

- **Closes:** R3 (image-over-caption routing) and the `_outer` override target bug.
- **Scope:** route image-over-caption columns to a column image component with a real `<img>`, not `hero-block` (`component_matcher.py:279`, `:282`); make the `_outer` override (`component_renderer.py:1411`, regexes `:552-570`) target the outer cell's background, not the first `background-color` in the block. `hero-block.html:3` 600px `v:rect` in a 296px cell is inferred Outlook overflow: note, fix only if the component change removes it.
- **Done check:** RED unit tests on a minimal node tree (column = image node + caption text) and on the `_outer` target; invariant over every case: no background-image component inside a column cell, and every image node in a column reaches the output as an `<img>`. Evidence: maap two-up helmet section at 600px side-by-side.
- **Wrong if (derived):** the maap images stay invisible after routing to a real `<img>` column (then CE-3's re-synced snapshot or asset export is the cause).
- **Files:** `component_matcher.py`, `component_renderer.py`, possibly a column-image template. ~300–600 lines.
- **Depends on:** CE-1.

#### CE-9: Columns without button text classed as CTAs (T3)

- **Closes:** R3 (nav columns routed as CTAs).
- **Scope:** do not class a column as CTA without button-like text (`component_matcher.py:295-300`); icon + short label columns route to the nav path (`:315-318`, `:380-382`) or an icon-column component; stop `_strip_empty_cta_chrome` (`component_renderer.py:1144`) from eating those columns.
- **Done check:** RED routing test on a minimal node tree (row of icon + short label columns, no button frame); invariant over every case: no column is classed CTA unless it holds a button frame or button-like text, and every icon and label node in a nav row reaches the output. Evidence: Starbucks nav band, all icons and labels in one row at 640px, 2×2 or clean stack at 375px, no stray "Follow us" (ledger `phase-53g-t1-tree-path-social-label-default`).
- **Wrong if (derived):** labels come back but icons stay missing (then the fill step, not routing, drops them).
- **Files:** `component_matcher.py`, `component_renderer.py`, tests. ~300–500 lines.
- **Depends on:** CE-1.

#### CE-10: Button icon counted as a content image (T5)

- **Closes:** R2.
- **Scope:** give `_extract_images` (`app/design_sync/figma/layout_analyzer.py:1460`) an exclude list for images inside a detected button frame, as `_extract_texts` has; test icon size on the icon node, not the parent frame (`:1855-1865`).
- **Done check:** RED test on a minimal node tree (button frame containing a small vector or image icon); invariant over every case: no image inside a detected button frame counts as a section image. Evidence: slate renders WATCH THE VIDEO and SHOP NOW with their headings; reframe keeps all three CTAs (only once CE-3 lands; if CE-3 is not merged, record that half as pending in the PR).
- **Wrong if (derived):** slate's section still flips to col-icon/image-grid after the exclude (then another image path feeds the matcher). Related brief data: Jev o2 got 5/5 where the heuristic got 0/5, n = 5, too small to wire (brief, not re-run).
- **Files:** `layout_analyzer.py`, tests. ~300–500 lines.
- **Depends on:** CE-1; reframe half on CE-3.

#### CE-11: VML on every button path (T6)

- **Closes:** R10.
- **Scope:** port `email-templates/components/golden-references/vml-rounded-button-variants.html` into every button path: `button-filled`, `button-ghost`, `cta`, `cta-pair`, and the text-block and column CTA paths (today only `cta-button.html` emits `v:roundrect`, `component_renderer.py:~1500`). Use design radius, fill, stroke and size. One VML builder.
- **Done check:** RED unit test on the VML builder; every CTA in the corpus outputs sits inside an MSO conditional with `v:roundrect`; Outlook render check against CE-4's renders once CE-4 lands.
- **Wrong if (derived):** CE-4's Outlook renders show buttons already keep shape without VML (then R10 is lower priority than inferred).
- **Files:** `component_renderer.py`, button templates, new VML builder, tests. ~500–900 lines.
- **Depends on:** CE-1. **Same-file conflict:** button templates are also codemod targets in CE-13. Land CE-11 before CE-13 touches button templates.

#### CE-12: Style override no-op census and runtime top-15 (A1, P1a kill test)

- **Closes:** no R-cause. Decides whether CE-13 is worth doing and which 15 templates it covers.
- **Scope:** log every `TokenOverride` emitted vs whether the output changed (`_apply_token_overrides`, `component_renderer.py:1398`); run across all corpus cases; count runtime template usage per case. Classify each no-op as plumbing (no hook) or judgment (hook exists, wrong role/value), re-deriving the brief's 7 plumbing / 3 judgment / 1 mixed split.
- **Done check:** report `docs/style-override-census.md` with no-op counts per template and property, the runtime top-15 list, and the re-derived split (observed). The top 15 comes from 7 Email Love designs, so it is biased; re-count with the CE-5 held-out cases if they have landed, and list templates the held-out cases use that the fixtures do not.
- **Wrong if (brief, P1a):** logging "override emitted but output unchanged" across the cases shows near-zero no-ops. If so, CE-13 is dropped or re-scoped.
- **Files:** `component_renderer.py` (debug logging behind a flag or test-only hook), a script, report. ~200–400 lines.
- **Depends on:** CE-1. Can start in wave 2.

### Wave 3: role hooks, width, sizing, Jev (sequence steps 3–4)

#### CE-13: `data-role` style hooks on the runtime top-15 templates (P1a)

- **Closes:** R7, the plumbing half of R4, and routes R5 writes through CE-7's builder. Does not close R6, R2, R3, R10.
- **Scope:** codemod `data-role="heading|body|cta|surface|card|cell"` into the 15 templates CE-12 names; replace the per-role regex code (`component_renderer.py:368-398`, `:552-570` and the `_apply_token_overrides` branches from `:1398`) with one role-keyed applier; add padding, align and font targets for `_cta` and per-role `_cell` targeting. Templates outside the 15 keep the old path.
- **Done check:** RED tests per role target; CE-12's census re-run shows the plumbing no-ops gone for the 15 templates; A3 full corpus; side-by-sides for the cases with the most no-ops.
- **Wrong if (brief, P1a):** as CE-12. Carried: a classifier can address at most 3–4 of the 11 style failures (brief, derived 27–36%), so this ticket carries the other 7.
- **Files:** 15 templates, `component_renderer.py`, `component_matcher.py` (`_build_token_overrides` `:2935`), codemod script, tests. ~1000–1500 lines. Split by template group if review gets too large.
- **Depends on:** CE-12, CE-7, CE-11 (button templates), CE-19 (A2: runs only if the spike recommends staying on templates; otherwise re-scoped or dropped).

#### CE-14: Per-character style runs in body text (R8, P1a remainder)

- **Closes:** R8.
- **Scope:** carry family, weight and letter-spacing in `StyleRun` (today footer-only, without those fields); render runs as spans in body text through the role applier.
- **Done check:** RED test on a run with a size change (performance stat units 12px, not 50px); slate black-on-dark text fixed; side-by-sides for performance and slate.
- **Wrong if (derived):** performance units stay 50px after runs render (then the analyser drops runs before rendering, `layout_analyzer.py` run parse).
- **Files:** `layout_analyzer.py`, `component_renderer.py`, tests. ~400–700 lines.
- **Depends on:** CE-13.

#### CE-15: Jev style-role shadow test (o4) and pre-registered O3 re-run

- **Closes:** no R-cause. Decides whether Jev picks roles for the judgment half of R4 (heading vs body `layout_analyzer.py:~2038`, card vs band `_detect_inner_bg` `:2162`).
- **Scope:**
  1. **Pre-registration commit before any label is read:** the #413 pass rule, the question designs (Choice with every option described; candidates as text, not bare node ids; `none` moved to a separate Noul for O3), label source, the hash of the label file.
  2. Add `o4_text_role` (options heading, body, label_eyebrow, legal) and `o4_surface_role` (section_band, card_surface, button_fill, none) to `app/design_sync/jev_shadow/questions.py`, `shadow.py`, `scripts/jev_shadow_report.py`; labels in `data/debug/jev_shadow_labels.yaml` from the hand builds.
  3. Re-run O3 with the new question design.
- **n and design count:** the brief's 157 texts / 72 filled frames (brief, not re-run) include performance, which has no hand build. Recount after dropping it; leave-one-design-out runs over 6 designs (7 with reframe after CE-3).
- **O3 at n = 20 (derived, Wilson 95% lower bound):** 18/20 → 0.699, 19/20 → 0.764, 20/20 → 0.839. So the #413 rule (≥ 0.80) passes only at 20/20. The brief's wrong-if ("stays below 18/20") is looser than the pass rule. **Decided (Q1, 2026-09-30): pre-register a larger O3 sample, n ≥ 30.** Derived, same bound: 29/30 → 0.833 (one miss passes), 37/40 → 0.801 (three misses pass), 47/50 → 0.838. The exact n is fixed in the pre-registration commit, bounded by how many O3 candidates the corpus yields.
- **Done check:** report `docs/jev-shadow-report-o4.md` with pass/fail per point against the pre-registered rule; pre-registration commit precedes the label commit in history.
- **Wrong if (brief):** the re-worded O3 run stays below 18/20, or `o4_text_role` breaks on any held-out design.
- **Files:** `jev_shadow/*`, `scripts/jev_shadow_report.py`, labels, report. ~600–1000 lines. No converter output change (shadow only).
- **Depends on:** none (parallel with CE-13). Label hygiene: ~90% of node names are `mj-*` (brief), so a pass may not transfer; CE-5 is the transfer check.

#### CE-16: FIXED/FILL column widths and gutter columns (P2 step 2) — scope addition (Q2: kept, 2026-09-30)

- **Closes:** R6, and the column-width part of R7.
- **Scope:** feed FIXED/FILL/HUG into `compute_column_width_fractions` (`layout_analyzer.py:1358`): FIXED → `td width=N`, FILL (grow = 1) → equal share of the remainder resolved to px, HUG → measured width. Keep FIXED empty columns as gutters instead of dropping them (`:1301-1309`). Geometry inference stays the fallback when sizing is absent.
- **Done check:** RED test on a minimal node tree with FILL / FIXED gutter / FILL columns (the failure class; maap's `[FILL 272, FIXED 8, FILL 272]`, brief, is regression evidence only); mammut and slate tiles separated at 600px; CE-1 per-section scores move up on the R6 sections.
- **Wrong if (brief, P2):** tiles still fuse after keeping gutters, or per-section scores do not move on R6/R9 cases.
- **Files:** `layout_analyzer.py`, tests. ~400–700 lines. Ledger overlap: `phase-53g-g9-img-not-rescaled-with-column`.
- **Depends on:** CE-6.

#### CE-17: Parameterise the 600px width in templates (R9 remainder) — pulled forward from T8 (Q3: pulled forward, 2026-09-30)

- **Closes:** R9 (slate sideways scroll, logo stretched to 560px).
- **Scope:** replace baked 600 in templates (`full-width-image.html:5`, `col-icon.html:3`, and every other template the grep finds) with the document's `container_width`. The brief put this in T8; it is pulled forward because CE-6 showed the width source already reads 640, so templates are the remaining cause.
- **Done check:** RED test: no hardcoded 600 in a 640 case's output; slate and Starbucks render without horizontal scroll at 640; reframe too once CE-3 lands.
- **Wrong if (brief, P2):** per-section scores do not move on R9 cases.
- **Files:** templates (overlap with CE-13's 15), `component_renderer.py`, tests. ~300–600 lines.
- **Depends on:** CE-6, CE-13 (same template files; land after the codemod).

#### CE-25: Jev section-boundary shadow question (o5) — added 2026-10-01 (A1)

- **Closes:** no R-cause directly. Tests whether a model should make the boundary call where geometry is ambiguous. Today boundaries are pure heuristics (`_get_section_candidates` `layout_analyzer.py:661`, `_expand_container_wrappers` `:681`, semantic peel `:717`); no model touches boundaries, and none of the O1–O3 questions ask about them (observed, scout pass 2026-10-01).
- **Scope:**
  1. Pre-registration commit before any label is read: the #413 rule, question design, label source, label-file hash.
  2. Add `o5_boundary` to `app/design_sync/jev_shadow/questions.py`, `shadow.py`, `scripts/jev_shadow_report.py`: for each section candidate with two or more child groups, "one section or more than one?"; for each adjacent candidate pair, "same section?". Candidates described as text (child types, text excerpts, geometry), not bare node ids.
  3. Labels from the hand builds' section boundaries; compare Jev with the heuristic's split.
- **Done check:** report `docs/jev-shadow-report-o5.md` with pass/fail against the pre-registered rule; output byte-identical (shadow only).
- **Wrong if (derived):** Jev does not split the known under-count cases (mammut renders 12 sections against a target of 18, ledger `phase-53-d3-mammut-below-candidate-undercount`), or it breaks on held-out designs (CE-5).
- **Files:** `jev_shadow/*`, `scripts/jev_shadow_report.py`, labels, report. ~500–900 lines. Same files as CE-15: run in parallel, rebase in merge order.
- **Depends on:** none.

### Wave 4: vision fallback (sequence step 5)

#### CE-18: VLM fallback triggered by Jev-heuristic disagreement, shadow first (P5, A5)

- **Closes:** no R-cause directly. Supports R1/R2/R3 classification; shadow mode changes no output.
- **Scope:** pre-register the pass rule and the disagreement definition before labels are read; make `match_all` (`component_matcher.py:141`) usable from an async caller in `converter_service._match_phase` (`:670`); add a per-section crop helper (offline: crop the reference PNG by section bounds; live: per-node export as `fidelity_service.py` does); switch `match_section_with_vlm_fallback` (`:165`) from the confidence gate (`LOW_MATCH_CONFIDENCE_THRESHOLD = 0.6`, `app/design_sync/tuning.py:12`, flags 0 sections on this corpus per the brief, not re-run) to disagreement, behind `vlm_fallback_enabled` (`app/core/config/design_sync.py:46`). Log the VLM verdict; do not apply it. Measure cost and latency.
- **Done check:** report `docs/vlm-disagreement-shadow.md`: VLM accuracy on the rows where Jev and heuristic disagree, vs Jev on the same rows (brief: 24 caught type errors, not re-run), cost and latency per section.
- **Wrong if (brief, P5):** the VLM is no better than Jev on the 24 caught errors, or disagreement rates shift on non-Email-Love designs (needs CE-5).
- **Files:** `component_matcher.py`, `converter_service.py`, crop helper, report script, tests. ~700–1100 lines.
- **Depends on:** CE-1; transfer check on CE-5.

### Wave 5: architecture spike (sequence step 6)

#### CE-19: O1 spike on the MJML path (P1b / P3)

- **Closes:** no R-cause. Decides T8 fix-sprint vs primitives rewrite.
- **Scope:** a node-tree emitter producing `mj-wrapper/section/column/text/button/image/spacer` for maap plus one held-out CE-5 design (Q7; the brief's version is maap only), mapping fill, padding, radius, font fields and style runs to MJML attributes, behind `output_format="mjml"` (`convert_document_mjml`, `converter_service.py:408`). Throwaway branch unless it passes.
- **Kill tests:** nested surfaces needed (card on band, illegal in MJML); output over Gmail's 102KB clip (maap measured, mammut extrapolated); Outlook buttons lose radius or stroke (CE-4 source). MJML 4.18's `mj-button` emits no VML (observed 2026-10-01: no `roundrect` in any `mjml-*` package in the sidecar), so the spike wraps buttons with CE-11's VML builder; without it kill test 3 fails by construction.
- **Done check:** report `docs/o1-spike.md`: CE-1 per-section scores vs current converter on each spike design, how much of the emitter needed design-specific code, the three kill tests with results, and a recommendation for CE-20.
- **Wrong if (brief, P1b):** the maap spike needs nested surfaces, mammut exceeds 102KB, or Outlook buttons lose radius and stroke.
- **Overlap:** `.agents/plans/universal-figma-converter.md` (status planned) and `.agents/plans/tree-compiler.md` cover similar ground; read both before planning this ticket.
- **Depends on:** CE-1, CE-4, CE-5 (held-out spike design, Q7), CE-6, CE-11 (VML builder). Moved ahead of CE-13 on 2026-10-01 (A2): the role-hook work waits for the spike's verdict, so it is not built on templates the spike may replace.

#### CE-20: T8 residual (placeholder, scoped after CE-19)

- **Closes:** remaining R4 (judgment half: `#0066cc` when `fill_color` unset, wrong button text role, `_outer`/`_inner` on dark bands), event-card misread from a date in copy (`component_matcher.py:479-500`), first-column-only padding, eyebrow flush.
- **Scope:** set by CE-19's recommendation, and by CE-15 if Jev passes for roles. Create the issue with "blocked on CE-19" and no implementation scope.
- **Wrong if (derived):** CE-19 recommends the rewrite; then this ticket is replaced, not executed.
- **Depends on:** CE-19 (and CE-15 for the role-picker option).

## Dependency graph

| Ticket | Depends on | Parallel group | Needs input |
|---|---|---|---|
| CE-1 gate | none | W1 | no |
| CE-2 content checks | none | W1 | no |
| CE-3 corpus refresh | CE-1 | W1 (after CE-1) | Figma token |
| CE-4 Outlook source | none | W1 | render source |
| CE-5 held-out corpus | CE-1 | W1 (before W2 if files exist) | files (Q6), token |
| CE-6 sizing read | CE-1 | W2 | no |
| CE-7 fonts (T4) | CE-2 | W2 | no |
| CE-8 caption columns as background images (T2) | CE-1 | W2 | no |
| CE-9 CTA without button text (T3) | CE-1 | W2 | no |
| CE-10 button icon (T5) | CE-1 (reframe half: CE-3) | W2 | no |
| CE-11 VML (T6) | CE-1 (Outlook check: CE-4) | W2 | no |
| CE-12 no-op census | CE-1 | W2 | no |
| CE-13 role hooks | CE-12, CE-7, CE-11, CE-19 | W4 | no |
| CE-14 style runs | CE-13 | W5 | no |
| CE-15 Jev o4 + O3 | none | W3 (parallel with CE-13) | no (Q1: n ≥ 30) |
| CE-16 widths + gutters | CE-6 | W3 | no |
| CE-17 template width | CE-6, CE-13 | W5 | no |
| CE-18 VLM shadow | CE-1 (transfer: CE-5) | W4 | no |
| CE-19 O1 spike | CE-1, CE-4, CE-5, CE-6, CE-11 | W3 | no (Q7: maap + one held-out) |
| CE-20 T8 residual | CE-19 (CE-15) | W4 | no |
| CE-25 Jev boundary o5 | none | W1 | no |

**File-overlap notes for parallel worktrees:** CE-8, CE-9 and CE-11 all touch `component_renderer.py`/`component_matcher.py` in different functions; run in parallel worktrees but rebase in merge order. CE-6, CE-10 and CE-16 all touch `layout_analyzer.py`. CE-11 → CE-13 → CE-17 share templates, so they run in sequence.

## Suggested execution order

Revised 2026-10-01 (A2: spike before role hooks; A1: CE-25 added). CE-21 to CE-24 (#440–#443: convert CLI, design_sync MCP tools, output lint and size check, Figma MCP debug server) were added to the epic by another session on 2026-09-30 and are not sliced in this file; the epic issue is their source.

| Wave | Tickets | Notes |
|---|---|---|
| 1 | CE-1, CE-2, CE-4, CE-15, CE-25 in parallel | CE-15 and CE-25 share `jev_shadow/*`: rebase in merge order |
| 2 | CE-3, CE-5, CE-6, CE-7, CE-8, CE-9, CE-10, CE-11, CE-12, CE-18 | CE-3 and CE-5 land early (stable baseline, held-out check). Same-file: CE-6/CE-10 (`layout_analyzer.py`); CE-8/CE-9/CE-11 (renderer/matcher) |
| 3 | CE-19 spike, CE-16 | CE-19 needs CE-4, CE-5, CE-6, CE-11 |
| 4 | CE-13 (only if CE-19 says stay on templates), CE-20 scoped | CE-20 also needs CE-15 |
| 5 | CE-14, CE-17 | follow CE-13 |

## Deferred-items ledger touching these tickets

| Entry | Ticket | Decision |
|---|---|---|
| `phase-53-a2-advisory-section-gate` | CE-1 | carry forward; CE-1 is a pixel gate, not the section-count gate. Decide at planning whether to make A2 strict in the same PR |
| `phase-53f-decorative-image-flag` | CE-10 | avoid; decorative vs content image is a separate classifier. Re-check if CE-10's exclude list touches it |
| `phase-53f-eyebrow-partial-padding-cell-theft` | CE-13 | close candidate: per-role `_cell` targeting |
| `phase-53g-g9-img-not-rescaled-with-column` | CE-16 | close candidate if widths resolve to px at the image |
| `phase-53g-band-item-spacing-defaults-vs-wrapper-padding` | CE-6 / CE-16 | close candidate once `itemSpacing` and sizing are read directly |
| `phase-53g-g3-template-cta-padding-uncovered` | CE-13 (and CE-11 touches the same templates) | close candidate: `_cta` padding target |
| `phase-53g-g5-pill-white-on-light-latent` | CE-13 | carry forward unless the `_cta` text-colour target covers it |
| `phase-53g-t1-social-non-icon-images-as-icons` | CE-9 | avoid unless the icon-column route fixes it too |
| `phase-53g-t1-tree-path-social-label-default` | CE-9 | avoid; tree path is non-production (flag off) |
| `phase-53g-g4-tree-html-slot-row-shape` | CE-19 | carry forward; relevant only if the spike reuses the tree path |
| `phase-53-d3-mammut-below-candidate-undercount` | CE-25 | evidence for the o5 question; close only if a later ticket wires a boundary fix |

## T-draft absorption

| Draft | Absorbed into |
|---|---|
| T2 maap images | CE-8 (generalised to the failure class) |
| T3 Starbucks nav | CE-9 (generalised to the failure class) |
| T4 font stacks | CE-7 (builder) + CE-13 (routing through role applier) |
| T5 button icon | CE-10 |
| T6 VML | CE-11 (Outlook check via CE-4) |
| T7 task 1–2 (maap re-sync, reframe) | CE-3 |
| T7 task 3 (content checks) | CE-2 |
| T7 task 4 (Outlook decision) | CE-4 |
| T8 R6 gutters | CE-16 |
| T8 R7/R8 padding and runs | CE-13, CE-14 |
| T8 R9 640px | CE-17 (pulled forward) |
| T8 R4 defaults, event-card date | CE-20 |

## Epic task list (CE-0 body; `CE-n` replaced by issue numbers at creation)

- [ ] CE-1 — Per-section fidelity baseline gate (depends on none)
- [ ] CE-2 — Content checks: unsubscribe, generic font family, default blue 0066cc, CTA count (depends on none)
- [ ] CE-3 — Corpus refresh: re-sync maap, regenerate reframe (depends on CE-1 · needs Figma token)
- [ ] CE-4 — Outlook render source decision and one render per design (depends on none · needs input)
- [ ] CE-5 — Held-out corpus of non-Email-Love designs (depends on CE-1 · needs files)
- [ ] CE-6 — Read auto-layout sizing fields (depends on CE-1)
- [ ] CE-7 — Font fallback stacks by category (depends on CE-2)
- [ ] CE-8 — Image-with-caption columns rendered as background images (depends on CE-1)
- [ ] CE-9 — Columns without button text classed as CTAs (depends on CE-1)
- [ ] CE-10 — Button icon counted as a content image (depends on CE-1)
- [ ] CE-11 — VML on every button path (depends on CE-1)
- [ ] CE-12 — Style override no-op census and runtime top-15 (depends on CE-1)
- [ ] CE-13 — data-role style hooks on the top-15 templates (depends on CE-12, CE-7, CE-11, CE-19)
- [ ] CE-14 — Per-character style runs in body text (depends on CE-13)
- [ ] CE-15 — Jev o4 style-role shadow test and pre-registered O3 re-run (depends on none · O3 n ≥ 30)
- [ ] CE-16 — FIXED/FILL column widths and gutter columns (depends on CE-6)
- [ ] CE-17 — Parameterise the 600px width in templates (depends on CE-6, CE-13)
- [ ] CE-18 — VLM fallback on Jev-heuristic disagreement, shadow (depends on CE-1)
- [ ] CE-19 — O1 spike on the MJML path (depends on CE-1, CE-4, CE-5, CE-6, CE-11)
- [ ] CE-20 — T8 residual, scoped after the spike (depends on CE-19, CE-15)
- [ ] CE-25 — Jev section-boundary shadow question o5 (depends on none)

## GitHub issues (created 2026-09-30)

| Ticket | Issue |
|---|---|
| CE-0 epic | #439 |
| CE-1 | #419 |
| CE-2 | #420 |
| CE-3 | #421 |
| CE-4 | #422 |
| CE-5 | #423 |
| CE-6 | #424 |
| CE-7 | #425 |
| CE-8 | #426 |
| CE-9 | #427 |
| CE-10 | #428 |
| CE-11 | #429 |
| CE-12 | #430 |
| CE-13 | #431 |
| CE-14 | #432 |
| CE-15 | #433 |
| CE-16 | #434 |
| CE-17 | #435 |
| CE-18 | #436 |
| CE-19 | #437 |
| CE-20 | #438 |
| CE-25 | #448 |
