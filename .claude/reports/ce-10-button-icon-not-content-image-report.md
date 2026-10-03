# Implementation Report — CE-10 button icons stop counting as content images (#428)

**Plan**: `.agents/plans/ce-10-button-icon-not-content-image.md`   **Branch**: `feat/ce-10-button-icon-not-content-image` (off `origin/main` `522f11ed`)   **Status**: COMPLETE through T11; T12 (`piv-commit` → `piv-validate` → `piv-create-pr`) pending

## Summary

Images inside a detected button frame no longer count as section, column or content-group images. The button's icon is measured on its leaf, through single-child FRAME/GROUP wrappers, and `icon_node_id` names that leaf. A section holding only one or two buttons now classifies as CTA, on both the mj path and the generic path. Excluded icons stay exported through `ButtonElementResponse.icon_node_id` and `_collect_image_node_ids`. On the corpus, all five lost CTAs now render: slate (c9) WATCH THE VIDEO and SHOP NOW, reframe Register now, Grab your spot and Register for livestream. Non-target cases are byte-identical.

## Tasks completed

- T1 branch + preflight → `feat/ce-10-button-icon-not-content-image` off `origin/main` `522f11ed`; probe `grep -c '^case='` = 10 before the change (observed).
- T2 RED tests → `app/design_sync/tests/test_button_icon_exclusion.py` (CREATE).
- T3 image exclusion + icon leaf → `app/design_sync/figma/layout_analyzer.py` (UPDATE). Changes:
  - `_extract_images` and `_walk_for_images` gain `exclude_node_ids`. The check runs first; both recursive calls thread it.
  - The callers at section extraction, `_detect_mj_columns`, `_build_column_groups` and `_extract_content_groups` pass their button ids. `_classify_section` is unchanged.
  - New `_icon_leaf`. `_walk_for_buttons` keeps the direct-child type and "icon" name gate, then measures the leaf. When the leaf is not a VECTOR, FRAME or IMAGE (for example a GROUP of vectors), it measures the direct child, as base did (D9).
- T4 button-only rule → `layout_analyzer.py` (UPDATE). New `_is_button_only` and `_BUTTON_ONLY_ROLES`. The mj rule (CTA 0.90) sits after the social and nav checks. The dead `_classify_by_content` condition is replaced in place (0.70, same position).
- T5 export → `app/design_sync/schemas.py`, `app/design_sync/service.py`, `app/design_sync/import_service.py` (UPDATE). The icon is appended inside the per-section loop, before the section-frame fallback. SDK regenerated: `cms/packages/sdk/openapi.json` and `cms/packages/sdk/src/client/types.gen.ts`, the only two files in `git diff --stat cms/packages/sdk` (observed).
- T6 → `app/design_sync/jev_shadow/shadow.py` comment (UPDATE).
- T7 baselines → `data/debug/9/expected.html`, `data/debug/reframe/expected.html` (UPDATE), `data/debug/content_check_allowlist.yaml` (UPDATE, see D4), `data/debug/reframe/manifest.yaml` (UPDATE, see D10).
- T8 ledger + F1 → `.agents/deferred-items.json` (UPDATE), `app/design_sync/tests/test_icon_label_columns.py` (UPDATE).
- T9 mutation proofs → `.tmpscratch/ce10/mutate.txt`, `.tmpscratch/ce10/mutate_f1.txt` (gitignored scratch).
- T10 A3 + gate + re-stamp → `data/debug/fidelity_baseline.json` (UPDATE).
- T11 visual check → `.tmpscratch/ce10/shots/*.png`; this report.

## Tests added

`test_button_icon_exclusion.py`: 31 passed, 5 skipped (observed, `uv run pytest app/design_sync/tests/test_button_icon_exclusion.py -q`). The skips are the CTA-order test on the non-target cases 5, 6, 7, 8 and 10.

| Class | Rows | Base | After |
|---|---|---|---|
| `TestImageExclusion` | text + button (slug `text-block`); image + heading + button (slug `article-card`); vector icon; button with image fill; large icon (80 px image in a 90 px wrapper, still excluded); mj columns; position columns; content groups | 8 red | green |
| `TestIconLeaf` | wrapper 430 → leaf; wrapper 40 → leaf; 80 px leaf → None; guard: GROUP-of-vectors leaf keeps the wrapper id | 2 red, 2 pass | green |
| `TestButtonOnlyClassification` | mj one button → CTA/`cta-button`; mj two → `cta-pair`; generic one → CTA; guards: mj 4 links not CTA, mj button + spacer = CONTENT, generic 4 links = NAV | 3 red, 3 guards pass | green |
| `TestIconExport` | icon exported; guard: dedupe; response field; guard: social icons reach the fill through `_layout_to_response` → `_collect_image_node_ids` → `match_section(image_urls=…)` | 2 red, 2 guards pass | green (the social guard went red after T3 and before T5, as the plan predicted) |
| `TestCorpusInvariants` (local only) | no image under a button in any container, all 7 cases; c9 and reframe CTA labels present, c9 copy before button | 4 red (c9, reframe) | green |

The RED run is saved at `.tmpscratch/ce10/red.txt`: 18 failed, 11 passed, 5 skipped. Every failure is an `AssertionError`, none a `TypeError` or `AttributeError` (observed). The large-icon and GROUP rows were added after that run. Large-icon is red on base (observed, base `layout_analyzer.py` checked out). The GROUP row passes on base: it guards against the branch's first version, and M8 proves it.

F1: two params added to `test_non_tile_shapes_do_not_route_to_td`, `real-plus-placeholder` and `height-only-too-big`.

### Mutation table (observed, `.tmpscratch/ce10/mutate.py` → `mutate.txt`; each mutation restored, `git diff` unchanged afterwards)

| Mutation | Red | Matches plan |
|---|---|---|
| M1 no exclude at section extraction | 5 section rows (text + button, image + heading, vector, image fill, large icon) | yes. `TestIconLeaf` green |
| M2 no exclude in `_detect_mj_columns` | mj-columns row only | yes |
| M3 no exclude in `_extract_content_groups` | content-groups row only | yes |
| M3b no exclude in `_build_column_groups` | position-columns row only | yes. The mj-columns row stays green |
| M4 measure the wrapper, not the leaf | leaf rows 430 and 40, **plus the social guard** | yes, with one extra red. `icon_node_id` names the wrapper, so the export URL is keyed by the wrapper and the leaf URL is absent |
| M5 remove the mj CTA rule | mj one-button and two-button rows | yes. The generic row stays green |
| M6 drop the `<= 2` bound | mj 4-link guard, **plus the generic 4-link NAV guard** | yes, with one extra red. The generic CTA rule runs before NAV |
| M8 drop the GROUP-leaf fallback | GROUP row only | added with D9 |
| M7 drop the icon export append | icon-exported row and social guard | yes. The response-field row stays green |
| F1a drop `len(labels) != len(texts)` | `real-plus-placeholder` only | yes |
| F1b drop the height clause | `height-only-too-big` only | yes. `git diff --stat component_matcher.py` empty after restore |

## Validation results

All results observed on this checkout, on the final working tree (committed as `chore(wip)`).

- `make converter-data-regression`: 89 passed, 48 skipped, 4 xfailed, after retiring the four reframe #428 xfails (D10).
- `make sdk-check`: "SDK is up to date".
- Probe (Level 4 #1): `probe_btn_imgs.py | grep -c '^case='` = **0**, down from 10 (AC 1).
- After the D9 fix, fresh captures of all 7 cases are byte-identical (`cmp`) to the audited T7 captures, so the A3 figures and the gate re-stamp still hold.
- `uv run pytest` on the Level 2 suite list (exclusion, layout_analyzer, cta_fidelity, image_export_fidelity, icon_label_columns, jev_shadow, component_matcher) plus `test_content_checks.py`: **454 passed, 5 skipped**.
- `test_jev_shadow.py`: **24 passed**, test unchanged.
- `uv run ruff format --check app/design_sync/` clean. `uv run ruff check --no-fix app/design_sync/` clean.
- `make types`: mypy clean (1393 files). pyright 0 errors after fixing one partially-unknown type in the new test (`set().union(*…)` replaced by a typed loop).
- `make snapshot-test`: 38 passed, 12 skipped, 2 xfailed.
- Ladder: `test_converter_data_regression.py -k ladder` 7 passed. `git diff origin/main -- data/debug/ladder_snapshot.json` empty.
- `test_content_checks.py`: 56 passed, after retiring the c9 `cta_count` entry (D4).
- `make golden-conformance`: 26 passed, 9 skipped. `make lint-numeric` clean. `TestCommittedFixtures`: 15 passed.
- `make fidelity-gate`: PASS before the re-stamp and PASS after it (pinned Playwright 1.63.0 image).
- Not yet run, pending in `piv-validate` on the final commit: `make check-full`, and `make ci-fe` because `cms/` changed.

### Baseline audit (T7, observed)

Fresh captures of all seven cases, compared with `diff --ignore-all-space` against the committed `expected.html`:

| Case | Changed lines |
|---|---|
| 5, 6, 7, 8, 10 | 0 |
| 9 | 158 |
| reframe | 175 |

Every c9 hunk sits in `section_5` (contained icon `2833:2126`, i.e. section `2833:2117`) or `section_7` (contained `2833:2143`, i.e. `2833:2132`).

Every reframe hunk sits in the three sections that contained `2833:1506`, `2833:1560` and `2833:1596`, i.e. sections `2833:1497`, `2833:1553` and `2833:1589`.

The overwritten baselines are byte-identical to the audited captures (`cmp`). The raw `git diff --stat` for reframe is 1007 lines; with `-w` it is 173. The rest is indentation churn from the different component nesting.

The branch-vs-base-vs-spike run is in `.tmpscratch/ce10/{base,branch,spikepatch}.jsonl`:

- The real change gives HTML identical to the spike-2 `--patch` output on all 7 cases.
- Slug moves match S2 and S3 exactly:
  - c9 `2833:2117` col-icon → text-block
  - c9 `2833:2132` image-grid → article-card
  - reframe `2833:1497` col-icon → text-block
  - reframe `2833:1553` and `2833:1589` content/image-block → cta/cta-button
- Section counts are 13/9/8/10/8/12, reframe 11, unchanged (S4).

### A3 (observed, `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py`)

"Before" is the same checkout with `layout_analyzer.py` checked out from `origin/main`. The other changed `.py` files do not touch the render path.

| case | full_image | section_min | section_median |
|---|---|---|---|
| 5 maap | 0.866 → 0.866 | 0.663 → 0.663 | 0.885 → 0.885 |
| 6 Starbucks | 0.813 → 0.813 | 0.466 → 0.466 | 0.757 → 0.757 |
| 7 Lego | 0.840 → 0.840 | 0.546 → 0.546 | 0.868 → 0.868 |
| 8 performance | 0.863 → 0.863 | 0.808 → 0.808 | 0.865 → 0.865 |
| 9 slate | 0.709 → **0.812** | 0.303 → **0.528** | 0.761 → **0.889** |
| 10 mammut | 0.736 → 0.736 | 0.064 → 0.064 | 0.834 → 0.834 |
| reframe | 0.844 → **0.854** | 0.550 → 0.550 | 0.878 → **0.890** |

Non-target Δ is 0.000 on all three metrics, consistent with byte-identity. Inside c9 and reframe, every harness section moves, because the harness rescales render height to the reference. The largest harness per-section drops are reframe −0.012 and c9 −0.009. These are scorer jitter on changed cases (memory `reference_a3_scorer_section_instability`). The CE-1 gate, keyed by node, shows only the five target sections moving:

### CE-1 gate (observed, pinned-image `scripts/fidelity-gate.py check --cases 9 reframe`, then `make fidelity-restamp CASES="9 reframe"`, stamp commit `17b03bd8`)

| case | node | before | after | Δ |
|---|---|---|---|---|
| 9 | `2833:2117` | 0.3424 | 0.8798 | +0.5374 improved |
| 9 | `2833:2132` | 0.8763 | 0.8738 | −0.0025 pass (margin 0.005) |
| reframe | `2833:1497` | 0.8821 | 0.9074 | +0.0253 improved |
| reframe | `2833:1553` | 0.8682 | 0.8971 | +0.0289 improved |
| reframe | `2833:1589` | 0.8577 | 0.8966 | +0.0389 improved |
| 9, reframe | every other section | | | +0.0000 |

`git diff data/debug/fidelity_baseline.json` touches only those five scores and appends one stamp. `make fidelity-gate` PASS after the re-stamp.

### Visual (T11, observed: Playwright at 600 px, `.tmpscratch/ce10/shots/`)

All five CTAs render after their copy or heading, in design order. Differences from the hand builds, none of them introduced by CE-10, since each CTA was absent before:

- **Arrow icon absent.** Out of scope; new ledger entry `ce-10-cta-icon-not-rendered`.
- **Reframe CTAs are content-width and centred.** The design has full-width bars with the label on the left. Pre-existing cta-button seed behaviour.
- **c9 SHOP NOW renders as a solid orange fill.** The design is an orange outline. Recorded here only (stay-in-ticket rule). It is a candidate for a ghost-button fidelity ticket; no open ledger entry covers outline buttons (grep, observed).
- **Two "Shop Now" VML defaults in reframe (S6).** Ledger `ce-2-cta-button-vml-twin-unfilled`, CE-11.

## Deviations from the plan

- **D1. Column and content-group rows call the extractors directly.** The rows (d), (d2) and (e) call `_detect_mj_columns`, `_detect_column_layout_with_groups(…, GENERIC)` and `_extract_content_groups` instead of going through `analyze_layout`. Two-column test sections get split by `semantic_peel` into solo sections, so `analyze_layout` never exposes `column_groups` for them. A direct call exercises exactly the caller each mutation targets, and M2, M3 and M3b each redden only their own row.
- **D2. Generic test sections sit second of four, 200 px tall.** The plan said "a page with ≥2 sections". With three sections, the position fallback types index `total-2` as SOCIAL. At 60–150 px height it types a button child as CTA, which would make the RED row pass on base for the wrong reason.
- **D3. `/preflight-check` not run; ledger reconciled manually.** I grepped `code_refs` for the touched files. Three extra matches were substring noise (`service.py` inside `converter_service.py` and `figma/service.py`). One real extra: `phase-53g-g11-contentgroup-column-divider-gap` (`_extract_content_groups`) → **avoid**. The exclusion adds no dividers field and changes no divider path.
- **D4. Retired the allowlist entry `case 9 cta_count` (owner #428) in `data/debug/content_check_allowlist.yaml`.** `test_content_checks_hold_allowlist` fails when an owned entry starts passing ("retire the entry (owner #428)"). The plan allowed editing this file only with a stated reason; this is the reason. No reframe entry existed.
- **D5. The corpus invariant reads the converter's own matched sections.** It uses `_converter_matches` from `test_icon_label_columns.py`. The probe ran its own `analyze_layout`; the converter's sections are the production ones. The descendant map comes from `normalize_tree(structure.json)`, as in the probe.
- **D6. The F3 rewrite replaces the whole false sentence.** That includes "No single slot_type renders raw table HTML in BOTH paths", which is false for the same reason: `attr` works in both paths. The new text cites `component_renderer.py:1010-1017`.
- **D7. The A3 "before" run checked out `origin/main`'s `layout_analyzer.py` instead of `git stash`.** The changes were already in the wip commit when T10 ran. Only `layout_analyzer.py` affects corpus render; the schema, service, import and shadow changes do not.
- **D8. The button + spacer guard asserts `CONTENT`.** That is the base value, observed passing on base, used instead of a computed "equal to base".
- **D9. GROUP-leaf fallback in `_walk_for_buttons`, not in the plan.** The advisor found that a 24 px FRAME `icon` wrapping a GROUP of vectors resolves to the GROUP leaf. The GROUP failed the type test, so `icon_node_id` became `None`, where base set the wrapper id. With the vectors now excluded from images, that icon would be neither in images nor exported, a regression against base. Reproduced, then fixed: when the leaf type is not measurable, the direct child is measured as before. GROUP row and M8 added. Corpus output is unchanged.
- **D10. Retired four strict xfails owned by #428 in `data/debug/reframe/manifest.yaml`:** `test_required_content`, `test_cta_colors`, `test_cta_vml`, `test_component_selection`. They XPASS(strict) now, and the manifest says the fixing PR deletes them. The plan did not list this file. `test_component_selection` passes although `2833:1497` routes to `text-block` (the button renders inside it) and the manifest row expects `button-filled`. Not changed.
- **D11. Ledger edited directly, not through the `deferred-items` skill.** The edits follow the schema in `.claude/rules/deferred-items.md`. `ce-10-unnamed-button-icon-not-exported` is widened to the three shapes that get no `icon_node_id` (unnamed, over 64 px, button image fill); its id is kept from the plan.
- **D12. `test_c9_tree_path_social_label_has_no_placeholder` is now a strict xfail** (`app/design_sync/tests/test_bridge_roundtrip.py`), found by the first `make check-full` (1 failed). The tree path is non-production (flag off). c9's two new CTAs carry href `'#'` and `TreeCompiler` rejects them, so the tree path falls back to the legacy renderer. This is the known entry `ce-9-tree-path-corpus-compile-fallback`, which already covered cases 5, 6 and reframe; c9 is added to its summary and code_refs. User chose this option (O1) over fixing `'#'` handling in this PR.

## Issues encountered

- **PR #469 (revert of CE-9) is still OPEN** (observed, `gh pr view 469`). Per U1 the user closes it; the agent did not touch it. A1: if it merges instead, stop and re-run S1–S6.
- No CE-6 branch is open (`gh pr list --search "CE-6 in:title"` empty).
- **Pre-commit hook.** `end-of-file-fixer` rewrote the untracked plan file on the first commit attempt; it was re-staged and committed.
- **Alembic head:** `drop_routing_history`. No migration in this ticket.
- **Converter-fix skill drift.** `.claude/skills/converter-fix/SKILL.md:25` still says "`reframe` is `reference_only`, never converted". It has been live since CE-3. Not edited, out of ticket.
- The brief's "heuristic 0/5" figure for `_o2_heuristic` no longer describes the code. The icon ids are now the leaves and absent from `section.images`. The brief was not re-run.
- Unreferenced icon assets and their `.gitignore` allowlist lines (`2833_2126`, `_2143`, `_1506`, `_1560`, `_1596`) are left in place, as the plan's non-goals say.
- After the PR opens, memory `project_pr468_carried_fixes` is to be deleted (T12).
