# Feature: button icons stop counting as content images (CE-10, #428)

The following plan should be complete, but validate documentation and codebase patterns and task sanity before you start implementing. Pay special attention to naming of existing utils, types and models.

**Spike scripts** (gitignored, main checkout): `.tmpscratch/ce10/probe_btn_imgs.py` (lists every image that sits inside a detected button frame, per section and column, every case) and `.tmpscratch/ce10/spike2.py` (monkeypatch spike of the planned change; `--patch` on, no flag = base; prints one JSON line per case with slugs and HTML). Run both with `PYTHONPATH=. uv run python <script>`. They are evidence tools, not the implementation: spike2 rebuilds buttons without `extra_hints` and filters images at the top level only (T3 does it properly).

## Decisions ratified by the user (2026-10-03, planning chat)

| # | Decision |
|---|---|
| U1 | CE-9 (#468) stays on main. Revert PR #469 is to be closed unmerged by the user. CE-10 branches off `origin/main` with CE-9 present and carries the PR #468 review fixes F1, F3 and F4 (memory `project_pr468_carried_fixes`). |
| U2 | The reframe button-only spacer drop is fixed in the **classifier** (`layout_analyzer.py`), not the matcher. Both the mj-* path and the generic path. |
| U3 | Excluded button icons stay exported: `icon_node_id` points at the measured inner icon node, `ButtonElementResponse` gains `icon_node_id`, and `import_service._collect_image_node_ids` exports button icons. |

## Evidence

### Planning probes (observed 2026-10-03 at `b815f189`, whose tree equals `origin/main` `522f11ed`: `git diff --stat b815f189 origin/main` empty)

| id | Probe | Result |
|---|---|---|
| E1 | `probe_btn_imgs.py`, all 7 cases | 5 sections hold an image inside a detected button frame, each counted twice (section + `col1`), none in `child_content_groups`: c9 `2833:2117` (WATCH THE VIDEO, img `2833:2126` 24×24), c9 `2833:2132` (SHOP NOW, img `2833:2143` 24×24), reframe `2833:1497` (Register now, `2833:1506` 17×17), `2833:1553` (Grab your spot, `2833:1560`), `2833:1589` (Register for livestream, `2833:1596`). Cases 5, 6, 7, 8, 10: none |
| E2 | Node shape (`structure.json`) | Every hit is `mj-button` FRAME → [TEXT label, `afterIcon-Frame` FRAME → IMAGE]. Wrapper width: c9 40 and 48 px; reframe 430, 416 px (FILL width) |
| E3 | `icon_node_id` today | c9: the wrapper FRAME (`2833:2125`, `2833:2142`), not the IMAGE that `section.images` and the export carry. Reframe: `None`, because `_walk_for_buttons` tests the 430 px wrapper against the 64 px cap (`layout_analyzer.py:1862-1872`) |
| E4 | Roles and slugs today | c9 `2833:2117` roles `text-with-icon` → `col-icon`; `2833:2132` → `image-grid`; reframe `2833:1497` → `col-icon`; `2833:1553`, `2833:1589` → `image-block` |
| E5 | Baselines | `grep -ci` of all five CTA labels in `data/debug/{9,reframe}/expected.html`: 0. Every one of the five CTAs is dropped today |
| E6 | Exclude-only spike (images filtered, no classifier change) | c9 renders both CTAs and "HOT TRIP, COOL GEAR."; reframe `2833:1553`/`2833:1589` fall to `spacer` (CONTENT, buttons only, no texts/images → `_score_candidates` returns `("spacer", 0.5)`, `component_matcher.py:450-451`) |
| E7 | Why `spacer`: classifier | `_classify_mj_section` walks into button frames (`_walk_mj_children`, `:1023`) and counts the label TEXT and icon IMAGE as section roles, so a button-only section reads as image+text+button → CONTENT (`:999-1000`). Generic path: `_classify_by_content`'s "Button-only → CTA" rule (`:1109-1111`) is dead code, because `_classify_section` passes unexcluded texts (`:945`) and a detected button always has a TEXT child |
| E8 | Export path | Production exports only `section.images` (`import_service.py:589-595`); `ButtonElementResponse` (`schemas.py:491-497`) has no icon field; `_fills_social` resolves icons via `image_urls[btn.icon_node_id]` then `image_urls[btn.node_id]`, then falls back to `section.images` (`component_matcher.py:2673-2700`). `run_case_conversion` passes no `image_urls`, so the corpus gate cannot see export loss |

### Spike 2 (observed 2026-10-03, `spike2.py --patch` vs base, same checkout)

| id | Result |
|---|---|
| S1 | Cases 5, 6, 7, 8, 10: HTML byte-identical to base, slugs unchanged |
| S2 | c9: `2833:2117` col-icon → text-block, `2833:2132` image-grid → article-card; output contains WATCH THE VIDEO, SHOP NOW, HOT TRIP, COOL GEAR |
| S3 | Reframe: `2833:1497` col-icon → text-block; `2833:1553`, `2833:1589` CONTENT/image-block → CTA/cta-button; output contains Register now, Grab your spot, Register for livestream |
| S4 | Rendered section counts unchanged for all 7 cases: 13/9/8/10/8/12, reframe 11 |
| S5 | New reframe buttons: fills `#C6FC6A`, `#FFBAF3`, `#06D5FF`, label `color:#000000` (design `text_color` `#000000` on `2833:1504/1558/1594`) |
| S6 | Reframe output gains 2 × "Shop Now": the two new `cta-button` sections' Outlook VML `<center>` default (`email-templates/components/cta-button.html:8`), ledger `ce-2-cta-button-vml-twin-unfilled` |

## Feature Description

A button frame in Figma often holds its label and a small trailing icon (an arrow). The layout analyzer collects that icon as a section image. One stray 24 px image flips the matcher: a text + button section becomes `col-icon`, an image + heading + button section becomes `image-grid`, and a section holding only a button becomes `image-block`. In every one of those, the CTA is lost. On the corpus that drops all five CTAs on slate (case 9) and reframe.

## User Story

As an email developer converting a Figma design
I want a CTA with a trailing icon to render as a CTA
So that sections keep their buttons and headings instead of turning into icon grids.

## Problem Statement

Text extraction excludes detected button subtrees (`_extract_texts(..., exclude_node_ids=button_node_ids)`, `layout_analyzer.py:494`); image extraction does not (`:495`, `:946`, `:1298`, `:1338`, `:2014`). The button's icon detection also measures the wrapper frame, not the icon, so a FILL-width wrapper hides the icon (`icon_node_id=None`). Once the icon is excluded, a button-only section has no remaining classifier signal and falls to `spacer` (E6, E7).

## Solution Statement

1. `_extract_images` / `_walk_for_images` take `exclude_node_ids` and skip those subtrees, mirroring `_walk_for_texts` (`:1428-1457`). Every extraction caller (`:495`, `:1298`, `:1338`, `:2014`) passes the button ids it already computes; the generic classifier call (`:946`) is left alone.
2. `_walk_for_buttons` measures the icon on its leaf (follow a single-child FRAME/GROUP chain, stopping at an icon-sized (≤ 64 px) wrapper with its own fill, image-ref or effects) and sets `icon_node_id` to the leaf (styled-wrapper stop added by PR #470 review M1).
3. New predicate `_is_button_only(node, buttons)`: 1–2 buttons and nothing outside the button subtrees except structural frames. `_classify_mj_section` returns CTA on it (after the social/nav checks); `_classify_by_content`'s dead button-only rule uses it.
4. Export continuity: `ButtonElementResponse.icon_node_id`, populated in `service.py`, exported by `_collect_image_node_ids`.

The generality rule holds: every rule reads node type, subtree membership, child count and geometry, never a name of a design, id or colour.

## Out of Scope / Non-Goals

- Rendering the icon inside a CTA. No CTA seed reads `icon_node_id`; the after-icon arrow is absent before and after this ticket. New soft ledger entry (T8).
- The cta-button VML twin's "Shop Now" default (`ce-2-cta-button-vml-twin-unfilled`, CE-11 #429 territory).
- Dropping the `"icon"` name requirement in icon detection. An unnamed icon inside a button gets no `icon_node_id`, so it is excluded and not exported. New speculative ledger entry (T8).
- Any exclusion in the generic `_classify_section` (`:945-947`): texts and images stay as today, because its hero, NAV and footer rules read them and no corpus case exercises that path (all mj-named; held-out CE-5 #423 still open). The generic path changes only through the bounded button-only predicate.
- Removing the now-unreferenced icon assets and their `.gitignore` allowlist lines (`2833_2126`, `_2143`, `_1506`, `_1560`, `_1596`). No test requires the reverse direction; leave them.
- The matcher (`_score_candidates`), the tree-bridge path (flag off), the converter-fix skill's stale "reframe is reference_only" line (note in report).

## Feature Metadata

**Feature Type**: Bug Fix · **Complexity**: Medium · **Systems**: `app/design_sync/figma/layout_analyzer.py`, `app/design_sync/schemas.py`, `app/design_sync/service.py`, `app/design_sync/import_service.py`, `app/design_sync/jev_shadow/shadow.py` (comment), SDK (`cms/packages/sdk`), corpus baselines c9 + reframe · **Dependencies**: none new
**Render path**: default renderer only. **Target cases**: 9, reframe. **Non-target**: 5, 6, 7, 8, 10 (byte-identical, S1).

## Related Work

**Implements**: #428 (CE-10) · **Epic**: #439, conventions table in the issue body
**Back-references**: `.agents/plans/ce-9-nav-columns-not-cta.md` (same-day CE ticket, corpus-invariant test pattern, re-stamp ordering, F1/F3/F4 source); `.agents/plans/ce-1-fidelity-baseline-gate.md` (gate, re-stamp); `.agents/plans/ce-3-corpus-refresh.md` (reframe live).
**Same-file tickets**: CE-6 (#424) also edits `layout_analyzer.py` (epic wave 2). Check `gh pr list` for an open CE-6 branch at T1; rebase in merge order.
**Forward-references**: (none yet)

## Deferred Items Touching This Plan

| id | match | decision | why |
|----|-------|----------|-----|
| `phase-53f-decorative-image-flag` | `layout_analyzer.py` `_walk_for_images`; epic table names CE-10 | avoid | The exclude skips button subtrees before the small-decoration branch (`:1615-1661`) runs; that branch's behaviour outside buttons is unchanged. Decorative vs content stays a separate classifier |
| `phase-53-d3-mammut-below-candidate-undercount` | `layout_analyzer.py` | avoid | Candidate discovery untouched; ladder unchanged (S4) |
| `phase-53g-t1-social-non-icon-images-as-icons` | `component_matcher.py` `_fills_social` | avoid | Matcher untouched. The social fallback reads `section.images`; U3 keeps button icons reachable through `icon_node_id` instead |
| `phase-53g-g5-pill-white-on-light-latent` | new reframe `cta-button`s on light fills | avoid | Design `text_color` `#000000` is threaded (S5) |
| `phase-53g-g3-template-cta-padding-uncovered` | new reframe `cta-button`s | carry forward | Padding not threaded on the template CTA path; pre-existing for every cta-button |
| `ce-2-cta-button-vml-twin-unfilled` | new reframe `cta-button`s (S6) | carry forward | Two more seeds show the VML default; root cause is CE-11 scope |
| `ce-9-tree-path-corpus-compile-fallback` | reframe tree path, `'#'` button hrefs | carry forward | Tree path non-production; more reframe buttons do not change the fallback |
| `phase-53g6-card-tree-path-text-only` | ledger edit (F3) | carry forward + F3 text fix | Correct the false "breaks attr handling" sentence only |
| `ce-9-peel-row-fixed-width-wrap`, `ce-9-c6-mobile-page-overflow`, `ce-9-tree-path-corpus-compile-fallback` | F4 | carry forward + stamp | Stamp `introduced_commit` `pending` → `522f11ed` |

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `app/design_sync/figma/layout_analyzer.py`: `:491-496` (section extraction; texts exclude buttons, images do not), `:912-948` `_classify_section` (generic path; images computed before buttons at `:945-947`), `:951-1020` `_classify_mj_section` (role walk, rule order: social `:985`, nav `:987`, image+text+button → CONTENT `:999`), `:1023-1040` `_walk_mj_children`, `:1043-1051` `_get_mj_role`, `:320-331` `_MJ_CONTENT_ROLES`, `:1063-1124` `_classify_by_content` (dead rule `:1109-1111`), `:1282-1372` `_detect_mj_columns` / `_build_column_groups`, `:1416-1457` `_extract_texts` / `_walk_for_texts` (the exclusion pattern to mirror), `:1460-1464` `_extract_images`, `:1571-1679` `_walk_for_images` (four branches, `skip_vectors` recursion), `:1553-1568` `_rasterizable_vector`, `:1805-1902` `_extract_buttons` / `_walk_for_buttons` (icon block `:1858-1872`), `:1927-1951` `_compute_content_roles`, `:1991-2034` `_extract_content_groups`.
- `app/design_sync/component_matcher.py:99-152` `match_section`, `:270-356` `_match_by_type`, `:359-460` `_score_candidates`, `:2649-2716` `_fills_social` (read only).
- `app/design_sync/schemas.py:491-497` `ButtonElementResponse`; `app/design_sync/service.py:147-155` (response build); `app/design_sync/import_service.py:570-606` `_collect_image_node_ids`.
- `app/design_sync/jev_shadow/shadow.py:185-192` `_o2_heuristic` (its comment describes the old slate behaviour); `:53`, `:164-166` (o2 candidates come from the tree, not `section.images`).
- Tests: `app/design_sync/tests/test_layout_analyzer.py:1153-1202` (`_make_text_node`, `_make_button_frame`, `_make_section_structure`), `:1667-1760` `TestButtonTextExclusionFixes` (pattern to mirror); `app/design_sync/tests/test_cta_fidelity.py:149-231` (`_make_button_node`, `TestButtonExtraction`); `app/design_sync/tests/test_image_export_fidelity.py:146-180` (`TestCollectImageNodeIdsExportPreference`, MagicMock layout); `app/design_sync/tests/test_icon_label_columns.py:340-397` (`_live_cases`, `_converter_matches`, `TestCorpusInvariants`), `:231-248` (F1 target); `app/design_sync/tests/test_jev_shadow.py:365-401` (o2 count 2, agree-all on case 9).
- `.claude/skills/converter-fix/SKILL.md` and `references/baselines-and-gates.md`, `references/a3-scoring.md`; `docs/fidelity-gate.md` (re-stamp).

### New Files to Create

- `app/design_sync/tests/test_button_icon_exclusion.py`: node-tree RED tests, export tests, corpus invariant.
- `.claude/reports/ce-10-button-icon-not-content-image-report.md`: report (tracked in the PR, CE-9 precedent).

### Patterns to Follow

- Exclusion: `_walk_for_texts` returns early on `node.id in exclude_node_ids` (`layout_analyzer.py:1434-1435`) and threads the kwarg through recursion (`:1457`). `_walk_for_images` must thread it through both recursive calls (`:1614`, `:1679`).
- Button ids: `_collect_button_node_ids(_extract_buttons(node, extra_hints=...))`, already computed beside every image call except `:946`.
- Tests: minimal `DesignNode` trees through `analyze_layout` then `match_section`, as `TestButtonTextExclusionFixes`; corpus invariants skip when fixtures are absent, as `test_icon_label_columns.py:362`.
- Logging: none added (pure functions). Email HTML: no template change.
- Lint: ruff config `pyproject.toml:126`; no rule flags a new keyword-only parameter or a module-level helper. Strict mypy/pyright: annotate `exclude_node_ids: set[str] | None = None`.

---

## STEP-BY-STEP TASKS

### T1 SETUP branch, base and preflight

- **IMPLEMENT**: `git restore app/ai/agents/dark_mode/skill-versions.yaml app/ai/agents/scaffolder/skill-versions.yaml` (stale `make test` date stamps on the CE-9 branch). `git fetch origin && git switch -c feat/ce-10-button-icon-not-content-image origin/main`. Record `git rev-parse origin/main` as BASE. `gh pr view 469 --json state`: if still OPEN, tell the user (U1 says they close it; the agent does not close PRs). `gh pr list --search "CE-6 in:title"` for a parallel `layout_analyzer.py` branch. Run `/preflight-check .agents/plans/ce-10-button-icon-not-content-image.md` and reconcile its deferred table with this plan's.
- **GOTCHA**: work in the main checkout, where the gitignored A3 inputs (reference PNGs, assets) are present. In a worktree, copy them first per `references/a3-scoring.md`.
- **VALIDATE**: `git status --short` shows only the untracked review/report files; `PYTHONPATH=. uv run python .tmpscratch/ce10/probe_btn_imgs.py 2>/dev/null | grep -c '^case='` = 10 (E1).
- **SATISFIES**: setup.

### T2 CREATE the tests and prove RED

- **IMPLEMENT** `app/design_sync/tests/test_button_icon_exclusion.py` with local builders (no fixture names, ids or colours from the corpus):
  - `_btn(id, *, icon_wrapper_w)`: FRAME named `mj-button` (fill `#123456`, h 48) → [TEXT label, FRAME `afterIcon-Frame` (w `icon_wrapper_w`, h 17) → IMAGE 17×17]. A `generic` variant names the button `button` and the wrapper `arrow-icon`.
  - `_mj_section(children)`: `mj-wrapper` → `mj-section` → `mj-column` → children, with x/y/width/height set so `analyze_layout` sees one section.
  - `TestImageExclusion` (RED): (a) text frame + button, wrapper 40 → `section.images == []`, `"text-with-icon" not in section.content_roles`, `match_section(...).component_slug == "text-block"`; (b) 560×373 image + heading + button → `len(section.images) == 1`, slug `article-card`; (c) parametrize the icon as VECTOR 16×16 named `icon` directly under the button (the `_rasterizable_vector` branch); (d) mj column path: two `mj-column`s each with a button+icon → every `column_groups[i].images == []`; (d2) position column path (`_build_column_groups`, `:1338`): a non-mj section with two side-by-side child frames at the same y, each text + button+icon → every `column_groups[i].images == []`; (e) content-group path: a non-mj section with two child frames, each text + button+icon → every `child_content_groups[i].images` empty.
  - `TestIconLeaf` (RED on reframe shape): `_walk_for_buttons` on wrapper 430 → `icon_node_id ==` the IMAGE id; wrapper 40 → the IMAGE id (today the wrapper id); IMAGE 80×80 under a 90 px wrapper → `None`.
  - `TestButtonOnlyClassification` (RED): mj section holding only a button (wrapper 430) → `section_type == CTA`, slug `cta-button`; two buttons → `cta-pair`; generic-named section (`Section 3`, wrapped in a page with ≥2 sections so the position rules apply) holding only a button → CTA. Guards (pass on base, labelled `guard` in the id): mj section of 4 `mj-button` links and nothing else → not CTA; mj section with button + `mj-spacer` → type equal to base; generic section of 4 `link`-named buttons → `NAV`.
  - `TestIconExport` (RED): `DesignImportService._collect_image_node_ids` on a MagicMock layout whose section has `images=[]` and `buttons=[btn(icon_node_id="ic:1")]` → `"ic:1" in node_ids`; dedupes an id already in images. Response test: `ButtonElementResponse(node_id="b", text="Go", icon_node_id="ic:1").icon_node_id == "ic:1"`. Production-path guard (end to end through export): a social section (`mj-social` wrapper, two labelled buttons, each with a wrapper FRAME `social-icon-Frame` holding an IMAGE leaf; the wrapped shape, because a direct IMAGE child already resolves on base) → `analyze_layout` → the service's own section-to-response conversion (`service.py:128-170`) → `node_ids` from `_collect_image_node_ids` → `image_urls = {nid: f"https://cdn.example/{nid}.png" for nid in node_ids}` → `match_section(section, 0, image_urls=image_urls)` → both leaf icon URLs appear in the social fill. This is a guard, not RED: on base it passes through the `section.images` fallback (`component_matcher.py:2695-2700`); after T3 without T5 it goes red (icon neither in images nor exported), which M7 proves.
  - `TestCorpusInvariants` (skipif no fixtures; CI skips, local only): over `_live_cases()`, for every section, column group and content group, no image `node_id` is a descendant of any button `node_id` in that same container (walk `structure.json` after `normalize_tree`, like `probe_btn_imgs.py`); c9 and reframe output contain their five CTA labels (case-insensitive).
- **PATTERN**: `test_layout_analyzer.py:1667-1690`; `test_image_export_fidelity.py:146-163`; `test_icon_label_columns.py:340-370`.
- **GOTCHA**: RED must fail on assertions, not on `TypeError` from the new kwarg or response field. Call `_collect_image_node_ids` with a real `ButtonElementResponse` only after T5 adds the field; until then build the button as a `MagicMock` with `icon_node_id` set, so the RED run fails on the missing id, not on Pydantic.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_button_icon_exclusion.py -q -p no:cacheprovider`: RED rows fail on assertions, guard rows pass. Save the output to `.tmpscratch/ce10/red.txt`.
- **SATISFIES**: AC 1, AC 2, AC 3, AC 4.

### T3 IMPLEMENT the image exclusion and icon leaf

- **IMPLEMENT** in `layout_analyzer.py`:
  - `_extract_images(node, *, exclude_node_ids: set[str] | None = None)` and `_walk_for_images(..., skip_vectors=..., exclude_node_ids=...)`: return early when `node.id in exclude_node_ids`; pass the kwarg through both recursive calls. `_extract_images` drops the root's own id from the set, so a button-shaped extraction root keeps its images (PR #470 review M2).
  - Callers: `:495` pass `button_node_ids`; `:1298`, `:1338` pass `btn_ids`; `:2014` pass `button_ids`. Leave `_classify_section` `:945-947` unchanged (texts and images): its hero and bottom-footer rules read `has_images`, the corpus is all mj-named so nothing measures that path, and `_is_button_only` (T4) does its own subtree walk.
  - `_icon_leaf(node) -> DesignNode`: while `node.type in (FRAME, GROUP)` and `len(node.children) == 1` and the wrapper is not both styled (`fill_color`, `image_ref` or `effects_summary`) and within the 64 px icon cap, step into the child. In `_walk_for_buttons` (`:1858-1872`) keep the `"icon" in child.name.lower()` test on the direct child, then measure `leaf = _icon_leaf(child)`: type in (VECTOR, FRAME, IMAGE), `leaf.width`/`leaf.height` ≤ 64, `icon_node_id = leaf.id`.
- **GOTCHA**: the `is_background` FRAME branch (`:1594-1614`) and the frame-wrapping-image branch run before recursion; the exclude check must come first in `_walk_for_images` so an excluded button with an `image_ref` fill is skipped too. `_detect_mj_columns`/`_build_column_groups` call `_extract_buttons` without `extra_hints` today; do not add hints (behaviour change outside the ticket).
- **VALIDATE**: `TestImageExclusion` and `TestIconLeaf` green; `uv run pytest app/design_sync/tests/test_cta_fidelity.py app/design_sync/tests/test_layout_analyzer.py app/design_sync/tests/test_image_export_fidelity.py -q -p no:cacheprovider` green; `uv run ruff check --no-fix app/design_sync/ && uv run ruff format --check app/design_sync/figma/layout_analyzer.py app/design_sync/tests/test_button_icon_exclusion.py`.
- **SATISFIES**: AC 1, AC 2.

### T4 IMPLEMENT the button-only classifier rule

- **IMPLEMENT** `_is_button_only(node, buttons) -> bool` in `layout_analyzer.py` next to `_walk_mj_children`: `1 <= len(buttons) <= 2`, and a walk of `node`'s subtree that skips button subtrees finds no TEXT with `text_content`, no IMAGE, no FRAME with `image_ref`, no visible VECTOR, and no node whose `_get_mj_role(name)` is outside `{"section", "column", "wrapper", "button"}`.
  - `_classify_mj_section`: after the nav check (`:986-987`), `if _is_button_only(node, _extract_buttons(node)): return EmailSectionType.CTA, 0.90`.
  - `_classify_by_content` (`:1109-1111`): replace the dead condition with `_is_button_only(node, buttons)`; keep confidence 0.70 and its position in the rule order.
- **GOTCHA**: never move the predicate above the social/nav/footer checks (4-button navs, S1 neutrality). The 1–2 bound keeps link rows out (`cta-pair` handles 2, `component_matcher.py:316-318`). `_classify_section` has no `button_name_hints`; `_extract_buttons(node)` without hints is the existing classifier behaviour (`:947`).
- **VALIDATE**: `TestButtonOnlyClassification` green (RED rows and guards); `PYTHONPATH=. uv run python .tmpscratch/ce10/spike2.py` against the branch (no `--patch`) prints the S2/S3 slugs and S1 byte-identity when diffed against a base run taken at BASE (`git stash` the `.py` changes, run, unstash).
- **SATISFIES**: AC 3.

### T5 IMPLEMENT export continuity and the SDK

- **IMPLEMENT**: `ButtonElementResponse.icon_node_id: str | None = None` (`schemas.py:491-497`); `service.py:149-155` passes `icon_node_id=btn.icon_node_id`; `_collect_image_node_ids` (`import_service.py:589-595`): after the images loop, for each `btn in section.buttons` with `btn.icon_node_id` not already in `node_ids`, append it. Update the docstring in one line. Then `make sdk-snapshot && make sdk-local`.
- **GOTCHA**: `service.py:149` is the only `ButtonElementResponse` builder and `:165` the only `LayoutAnalysisResponse` builder outside tests (observed, grep), so no second path leaves `icon_node_id` unset.
- **GOTCHA**: the fallback "export section frames when no images" (`:598-600`) fires when `node_ids` is empty. Today the icons sit in `section.images`, so a layout whose only images are button icons never hits it. Append the icons **before** that check to keep it so; appending after would newly export every section frame for such layouts. The SDK diff must touch only `openapi.json` and `src/client/types.gen.ts` (`git diff --stat cms/packages/sdk`).
- **VALIDATE**: `TestIconExport` green; `uv run pytest app/design_sync/tests/test_image_export_fidelity.py -q`; `make sdk-check` clean after commit-staging; `make ci-fe` green (cms/ changed: CLAUDE.md DoD).
- **SATISFIES**: AC 4.

### T6 UPDATE the jev_shadow comment and run its tests

- **IMPLEMENT**: `shadow.py:186-187` comment: the icon IMAGE is no longer in `section.images`; `icon_node_id` names the leaf, so the heuristic answers `button_icon` for it.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_jev_shadow.py -q`: green. Expected (derived): o2 candidates come from the tree (`shadow.py:164-166`), so the count stays 2; the test handler answers 0.9 for ids in `icon_node_id`, which now equal the IMAGE ids, and the heuristic returns `button_icon` for them, so `agree` stays True. If it goes red, read the failure before editing the test; do not loosen the assertion. `grep -rln "jev_shadow_labels\|_o2_heuristic" app/design_sync/tests` returned nothing at planning (observed), so no test pins heuristic agreement against the committed labels. Note in the report that the brief's "heuristic 0/5" figure no longer describes the code (brief, not re-run).
- **SATISFIES**: AC 5.

### T7 REGENERATE and AUDIT the baselines

- **IMPLEMENT**: capture all seven cases to a fresh directory: `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/snapshot-capture.py <case> --output .tmpscratch/ce10/cap/<case>.html`; `diff --ignore-all-space` against committed `expected.html`. Trace every changed line in c9 and reframe to the five sections in E1. Then `--overwrite` cases 9 and reframe only.
- **GOTCHA**: each capture must print "Output saved"; `--output` refuses an existing file. Never `make snapshot-capture` (hardcodes `--overwrite`). A whitespace-only c8 diff is known churn: restore it.
- **VALIDATE**: non-targets 5, 6, 7, 8, 10: 0 changed lines; in `data/debug/9/expected.html`, "From the Davis Dam" (`2833:2121`, the body copy above WATCH THE VIDEO; its section has no separate heading) precedes WATCH THE VIDEO, and "HOT TRIP, COOL GEAR." (`2833:2138`, 36 px heading) precedes SHOP NOW (string-index order, asserted in the corpus invariant too); Register now, Grab your spot, Register for livestream in `data/debug/reframe/expected.html` ≥ 1 each; `make snapshot-test` green; `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k ladder -q` green and `git diff origin/main -- data/debug/ladder_snapshot.json` empty; `uv run pytest app/design_sync/tests/test_content_checks.py -q` (CTA count rows for c9/reframe; if a row fails because CTAs now exist, update `data/debug/content_check_allowlist.yaml` only with a stated reason); `make golden-conformance`; `make lint-numeric`; `uv run pytest "app/design_sync/tests/test_fidelity_gate.py::TestCommittedFixtures" -q`.
- **SATISFIES**: AC 2, AC 3, AC 6.

### T8 UPDATE the ledger and carry F1

- **IMPLEMENT** via the `deferred-items` skill:
  - F3: correct the `phase-53g6-card-tree-path-text-only` summary sentence (`attr` goes through `_fill_text_slot`, `component_renderer.py:1010-1017`, a raw insert).
  - F4: stamp `introduced_commit` `522f11ed` on the three `ce-9-*` entries.
  - Add `ce-10-cta-icon-not-rendered` (known-bug, re-graded from soft by PR #470 review L3): CTA seeds ignore `ButtonElement.icon_node_id`, so a design's after-icon arrow is absent; closes when the button path renders the icon at design size. `code_refs` `component_matcher.py` CTA fills, `layout_analyzer.py` `_walk_for_buttons`.
  - Add `ce-10-unnamed-button-icon-not-exported` (speculative): an image inside a button whose wrapper and leaf names lack "icon" gets no `icon_node_id`, is excluded from `section.images`, and is not exported; a labelled social button with such an icon renders no icon. Closes when every excluded button image is exported or the predicate stops needing the name.
  - New entries use `introduced_commit: "pending"` (stamped after merge).
- F1: add the two params to `test_non_tile_shapes_do_not_route_to_td` (`test_icon_label_columns.py:231-246`): `_tile_section(texts=[_label("APP"), _label("Lorem ipsum", node_id="t2")])` id `real-plus-placeholder`, and an icon `ImagePlaceholder` with `width=42, height=65` id `height-only-too-big`. Mutate each clause out of `_is_icon_label_tile` (`component_matcher.py:1312`, the clause the reviewer cited is at `:1331`) in turn and confirm the new param goes red; restore.
- **VALIDATE**: `python3 -c "import json; json.load(open('.agents/deferred-items.json'))"`; `uv run pytest app/design_sync/tests/test_icon_label_columns.py -q`; the two mutations each turn exactly the new param red (record in `.tmpscratch/ce10/mutate_f1.txt`); `git diff --stat app/design_sync/component_matcher.py` empty after restore.
- **SATISFIES**: AC 7.

### T9 PROVE the tests by mutation (both halves)

- **IMPLEMENT**: for each mutation, run the named RED test and the named guard, record both results in `.tmpscratch/ce10/mutate.txt`, then restore:
  - M1 drop `exclude_node_ids` at `:495` → `TestImageExclusion::a` red, `TestIconLeaf` green.
  - M2 drop it at `:1298` → the column test red, the section test (a) green.
  - M3 drop it at `:2014` → the content-group test red.
  - M3b drop it at `:1338` → (d2) red, (d) green.
  - M4 revert `_icon_leaf` (measure `child`) → `TestIconLeaf` wrapper-430 row red, wrapper-40 row red (id is the wrapper), `TestImageExclusion` green.
  - M5 remove the mj CTA rule → mj button-only rows red, generic row green.
  - M6 drop the `<= 2` bound → the 4-button mj guard red.
  - M7 drop the icon append in `_collect_image_node_ids` → `TestIconExport` and the end-to-end social guard red; the `ButtonElementResponse` field test green.
- **VALIDATE**: every row matches; `git diff` shows no mutation left.
- **SATISFIES**: AC 1–4.

### T10 SCORE A3, run the CE-1 gate, re-stamp

- **IMPLEMENT**: make a `chore(wip):` commit of T2–T9 so the stamp's `commit` names a commit that produces the scores (CE-9 F6 precedent; `piv-commit` folds it). A3 before (stash the `.py` changes, same checkout) and after: `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py` (move any old `.tmpscratch/fidelity/` aside first). `make fidelity-gate` (Colima running). Then `make fidelity-restamp CASES="9 reframe" REASON="CE-10 #428: button icons excluded from section images; c9 2833:2117 <Δ>, 2833:2132 <Δ>; reframe 2833:1497 <Δ>, 2833:1553 <Δ>, 2833:1589 <Δ>; other sections +0.0000"` with this run's figures; re-run `make fidelity-gate`.
- **GOTCHA**: a drop beyond margin on any section, or a non-target A3 move beyond jitter, stops for the user's ratification before the re-stamp (CLAUDE.md "Converter changes carry full-corpus A3"). Per-section drops on changed sections are scorer artefacts until composites say otherwise (`reference_a3_scorer_section_instability`). Expected: non-target A3 Δ 0.0000 (derived from S1 byte-identity).
- **VALIDATE**: A3 table has 7 rows; gate passes after re-stamp; `git diff --stat -- data/debug/fidelity_baseline.json` touches only c9/reframe rows and the stamp list.
- **SATISFIES**: AC 6.

### T11 VISUAL check and report

- **IMPLEMENT**: 600 px side-by-side of c9 sections `2833:2117`/`2833:2132` against `email-templates/training_HTML/for_converter_engine/<slate dir>/manual_component_build.html` and reframe's three CTA sections against its hand build (find dirs with `ls email-templates/training_HTML/for_converter_engine/`). Judge presence and order of heading, body, button; the arrow is absent (Out of Scope). Write the report: evidence tags, mutation table, A3 table, gate rows, deviations, the converter-fix skill drift note.
- **VALIDATE**: report exists at `.claude/reports/ce-10-button-icon-not-content-image-report.md`; every figure tagged.
- **SATISFIES**: AC 6, AC 8.

### T12 GATE and hand off

- **IMPLEMENT**: `piv-commit` (`fix(design-sync): keep button icons out of section images (CE-10)`), `piv-validate` (`make check-full` via `record-gate.sh`, plus `make ci-fe` for the SDK change), `piv-create-pr` (draft, base `origin/main`, body per converter-fix "PR body", "Closes #428"), then watch CI. Delete memory `project_pr468_carried_fixes` and its MEMORY.md line after the PR opens.
- **VALIDATE**: `git diff --stat origin/main...HEAD` lists exactly: `.agents/deferred-items.json`, `.agents/plans/ce-10-button-icon-not-content-image.md`, `.claude/reports/ce-10-...-report.md`, `app/design_sync/figma/layout_analyzer.py`, `app/design_sync/schemas.py`, `app/design_sync/service.py`, `app/design_sync/import_service.py`, `app/design_sync/jev_shadow/shadow.py`, `app/design_sync/tests/test_button_icon_exclusion.py`, `app/design_sync/tests/test_icon_label_columns.py`, `cms/packages/sdk/openapi.json`, `cms/packages/sdk/src/client/types.gen.ts`, `data/debug/9/expected.html`, `data/debug/reframe/expected.html`, `data/debug/fidelity_baseline.json` (+ `content_check_allowlist.yaml` only if T7 needed it).
- **SATISFIES**: AC 8.

---

## TESTING STRATEGY

### Unit Tests

`test_button_icon_exclusion.py`: minimal Figma node trees (Figma input, so the real-fixtures rule holds) for each extraction path (section, mj column, position column via `_build_column_groups`, content group), icon leaf measurement, classifier on both naming conventions, export and response field. Existing suites that must stay green: `test_layout_analyzer.py`, `test_cta_fidelity.py`, `test_image_export_fidelity.py`, `test_component_matcher.py`, `test_icon_label_columns.py`, `test_jev_shadow.py`, `test_content_checks.py`.

### Integration Tests

Social guard through `analyze_layout` → `match_section` with `image_urls` (the production lookup the corpus cannot see, E8). Corpus invariant over every live case (local only; `structure.json` skips in CI). `make snapshot-test`, `make converter-data-regression`, `make fidelity-gate`.

### Edge Cases

| Edge case | Verified in |
|---|---|
| Icon as VECTOR directly in the button (no wrapper) | `TestImageExclusion::c` |
| FILL-width icon wrapper (430 px) | `TestIconLeaf`, reframe corpus invariant |
| Icon larger than 64 px inside a button | `TestIconLeaf` (None); still excluded from images by subtree, `TestImageExclusion` |
| Button frame with an `image_ref` fill | T3 GOTCHA; add a row to `TestImageExclusion` |
| Two buttons, nothing else | `TestButtonOnlyClassification` (`cta-pair`) |
| Four link-buttons, nothing else (mj and generic) | guards, M6 |
| Button + spacer only | guard (type equal to base) |
| Labelled social button with icon | social guard, M7 |
| Icon id already exported as an image | `TestIconExport` dedupe row |
| Unnamed icon in a button | ledger `ce-10-unnamed-button-icon-not-exported`; not tested |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

- `uv run ruff format --check app/design_sync/` and `uv run ruff check --no-fix app/design_sync/`
- `make types`, `make lint-numeric`, `make golden-conformance`

### Level 2: Unit Tests

- `uv run pytest app/design_sync/tests/test_button_icon_exclusion.py app/design_sync/tests/test_layout_analyzer.py app/design_sync/tests/test_cta_fidelity.py app/design_sync/tests/test_image_export_fidelity.py app/design_sync/tests/test_icon_label_columns.py app/design_sync/tests/test_jev_shadow.py app/design_sync/tests/test_component_matcher.py -q -p no:cacheprovider`

### Level 3: Integration / gates

- `make snapshot-test`, `make converter-data-regression`, `make fidelity-gate`, `make sdk-check`
- `make check-full` via `piv-validate`; `make ci-fe` (SDK under `cms/`). No eval gate: no diff under `app/ai/agents/` or the judges.

### Level 4: Manual Validation

1. `PYTHONPATH=. uv run python .tmpscratch/ce10/probe_btn_imgs.py 2>/dev/null | grep -c '^case='` on the branch: 0 (was 10, E1).
2. Side-by-side at 600 px (T11), against the hand builds.
3. Open `data/debug/reframe/expected.html` in a browser: three filled buttons with black labels on lime, pink and cyan.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: No image inside a detected button frame counts as a section, column or content-group image, on a minimal node tree (RED-first) and over every live case (corpus invariant, local).
- [ ] AC 2: Slate (c9) output renders WATCH THE VIDEO after its section copy (`2833:2121`) and SHOP NOW after its heading HOT TRIP, COOL GEAR. (`2833:2138`), in design order (issue done check).
- [ ] AC 3: Reframe output renders all three CTAs (CE-3 merged, so this half is not pending); a button-only section classifies as CTA on both mj and generic naming, bounded to 1–2 buttons.
- [ ] AC 4: `icon_node_id` names the measured icon leaf; button icons are exported through `_collect_image_node_ids`; the SDK is regenerated.
- [ ] AC 5: `test_jev_shadow.py` green; `_o2_heuristic` comment current.
- [ ] AC 6: Non-targets 5, 6, 7, 8, 10 byte-identical; ladder unchanged from base; full-corpus A3 before/after (7 rows); `make fidelity-gate` passes after the c9/reframe re-stamp with every moved section named; any non-target drop beyond jitter ratified by the user. The epic's held-out check does not apply: CE-5 (#423) is open, so there are no held-out cases yet.
- [ ] AC 7: F1, F3, F4 carried; two new ledger entries added; mutation proofs recorded (T9).
- [ ] AC 8: `make check-full` and `make ci-fe` green on the committed head; draft PR open; report written.

## COMPLETION CHECKLIST

- [ ] T1–T12 done in order, each VALIDATE run
- [ ] RED output saved before the fix (`.tmpscratch/ce10/red.txt`)
- [ ] Baseline audit traced every changed line; non-targets 0 lines
- [ ] Gate, A3, ladder, content checks, snapshot tests green
- [ ] Report written with tagged figures; memory `project_pr468_carried_fixes` removed

## OPEN QUESTIONS / ASSUMPTIONS

- A1: #469 is closed by the user before the PR opens (U1). If it merges instead, stop: CE-9's `_match_by_type` CTA→CONTENT rule and `_is_icon_label_tile` disappear, F1 is moot, and S1–S6 must be re-run.
- A2: The mj CTA confidence 0.90 matches the other mj role rules (`:984-991`); nothing downstream thresholds on it (grep `classification_confidence` before changing it).
- A3: T5's ordering keeps today's fallback behaviour (derived: icons were in `node_ids` before, and stay there). Worst case if placed after the check: icon-only layouts export every section frame, a silent extra Figma export load.
- A4: Spike figures are monkeypatch results. T4 and T7 re-derive them from the real change; if they differ, the real change wins and the plan gets an AMENDMENT.

## NOTES

- Why the classifier, not the matcher (U2): the failure class is "button internals counted as section content", which is what the image exclusion fixes for `analyze_layout`; the classifier's role walk is the same class. The matcher one-liner would have rendered the same corpus result (observed, first spike) but left `section_type` wrong for every downstream reader (token overrides, jev o1).
- Why bound 1–2: the role-walk change alone (first spike) would turn an mj row of four `mj-button` links from NAV into CTA, because skipping button internals removes the "text" role the nav rule reads. Bounding and placing the rule after social/nav keeps those rows on their current path.
- The generic `_classify_by_content` rule at `:1109` has been unreachable since buttons began requiring a TEXT child; replacing its condition revives it in bounded form rather than adding a second rule.

## AMENDMENTS

- 2026-10-03 — advisor pass before hand-off: generic `_classify_section` left untouched (narrower option); social guard rebuilt end to end through export so M7 can fail; position-column test + M3b added; slate heading order made explicit; held-out check marked not applicable.
- 2026-10-03 — implementation (report `.claude/reports/ce-10-button-icon-not-content-image-report.md`, D1–D11). Superseded or added:
  - T2 (d)/(d2)/(e): call `_detect_mj_columns`, `_detect_column_layout_with_groups(…, GENERIC)` and `_extract_content_groups` directly; `analyze_layout` peels two-column test sections into solo sections (D1). Generic rows place the section second of four, 200 px tall, so no position rule fires on base (D2). Button + spacer guard asserts `CONTENT` (D8). Added rows: `large-icon` (80 px image in a 90 px wrapper, still excluded) and a GROUP-of-vectors guard.
  - T3: `_walk_for_buttons` measures the direct child when `_icon_leaf` ends on a type outside (VECTOR, FRAME, IMAGE), e.g. a GROUP, keeping base's `icon_node_id` (D9); T9 gains M8 (drop that fallback → GROUP row red).
  - T1: `/preflight-check` replaced by a manual ledger grep; `phase-53g-g11-contentgroup-column-divider-gap` added as avoid (D3).
  - T7: retire the c9 `cta_count` allowlist entry (owner #428, D4) and the four reframe strict xfails owned by #428 in `data/debug/reframe/manifest.yaml` (D10); T12's diff list gains both files.
  - T8: ledger edited directly per `.claude/rules/deferred-items.md`, not via the skill (D11); `ce-10-unnamed-button-icon-not-exported` widened to unnamed, over-64 px and button-image-fill shapes; F3 replaces the whole false sentence (D6).
  - T10: A3 "before" took `layout_analyzer.py` from `origin/main` instead of `git stash` (changes already in a wip commit, D7). Corpus invariant reads the converter's matched sections via `_converter_matches` (D5).
  - T12: first `make check-full` failed `test_c9_tree_path_social_label_has_no_placeholder` (tree path falls back on c9's new `'#'` CTA hrefs, ledger `ce-9-tree-path-corpus-compile-fallback`). User chose to mark it a strict xfail and add c9 to that entry (D12); the diff list gains `app/design_sync/tests/test_bridge_roundtrip.py`.
