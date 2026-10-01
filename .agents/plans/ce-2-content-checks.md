# Feature: content checks over converter output, plus unsubscribe and text-link fixes (CE-2, #420)

The following plan should be complete, but validate documentation, codebase patterns and task sanity before you start implementing. Pay attention to the names of existing utils, types and models, and import from the right files.

Base: origin/main `6e3cf84d` (observed: `git fetch` 2026-10-01). All `file:line` refs below were read at that head. Branch: `feat/ce-2-content-checks`.

**One-pass confidence: 10/10.** The whole change was built and measured in a throwaway spike before this plan was finalised (evidence below). Every behaviour, per-case figure, gate result and test outcome the tasks rely on was observed on that spike. The implementer ports a working diff and writes the tests around it; no task depends on an unmeasured assumption.

## Decisions ratified by the user (2026-10-01, planning chat)

| # | Decision | Effect |
|---|---|---|
| U1 | Fix the missing unsubscribe link **inside CE-2** (issue scoped CE-2 as test-only) | CE-2 is a converter-output ticket: RED first, snapshot audit, ladder, fidelity gate, A3 |
| U2 | Rule O1: link the phrase wherever it renders (not footer re-classification) | One post-render pass; design-agnostic |
| U3 | `#0066cc` allow-list entries keyed to **#438** (CE-20) | No fix here |
| U4 | "Address all risks": fold in the text-link loss (R3) | `_column_text_row` renders link runs |
| U5 | A design link on an unsubscribe phrase points at `{{unsubscribeUrl}}`, not the Figma URL | href rewrite in the pass |

## Spike evidence (observed 2026-10-01)

Spike: detached worktree `.claude/worktrees/ce2-spike` at `6e3cf84d`. Its full diff (4 files, incl. the MJML cache-hit call) is saved at **`.tmpscratch/ce2/spike.diff`** (gitignored, main checkout) and is the reference implementation for Tasks 6–9. Prototypes next to it: `checks_proto.py` (output readers), `walker.py` (design CTA walker), `c1.out` (phrase scan).

| # | Question | Result (observed) |
|---|---|---|
| E1 | Base state of the four checks | see table "Measured state" below (`checks_proto.py` + scout probes on `6e3cf84d`) |
| E2 | Default-path diff, pass only | 5, 7 byte-identical; 6, 8, 9, 10 change only by one inline `<a href="{{unsubscribeUrl}}">` each, coloured from the enclosing cell (`#707070`, `#FFFFFF`, `#F9F9F9`, `#000000`) |
| E3 | Formatter reflow | with the pass before `format_email_html`, the anchor went on its own line and `Unsubscribe</a>⏎.` rendered "Unsubscribe ." — fixed by running the pass **after** the formatter and by Task 8's formatter glue |
| E4 | Fidelity gate, pass only (`make fidelity-gate`) | PASSED; only the four footer sections moved: 6 `2833:1475` −0.0001, 8 `2833:2348` −0.0002, 9 `2833:2149` −0.0004, 10 `2833:1270` +0.0001 (margin 0.005); every other section 0.0000 |
| E5 | A3, pass only (`score-fidelity-cases.py --cases 5 6 7 8 9 10`) | every full-image composite unchanged to 4 dp; only case 10 section_min 0.0635→0.0639 and case 9 section 10 0.947→0.946 |
| E6 | MJML path (real Maizzle sidecar, Node 24) | base: 0 unsubscribe links in **all six** cases; with the pass: exactly 1 in each (+82 chars) |
| E7 | Tree path (`DESIGN_SYNC__TREE_BRIDGE_ENABLED=true`, `output_format="tree"`) | tree produced for 7–10, fell back for 5, 6; pass adds 1 link in 8, 9, 10; case 7 tree output has no footer text at all (pre-existing tree-path loss, logged Task 12) |
| E8 | Phrase scan over 201 `email-templates/**/*.html` + 7 `structure.json` | 38 matches, 0 false positives (`c1.out`); literals: "adopt outdoor gear", "subscribe now", "Subscribe" → no match; 17 multi-language phrases → match |
| E9 | Pass safety, combined spike (`probe2.py`) | per case 5–10: 0 nested anchors; every comment (incl. MSO blocks) and `<head>` byte-identical pre/post; lxml parses; `link_unsubscribe_text(pre_pass_html) == converted_html` (idempotent, so safe on cached HTML) |
| E10 | R3 prototype (link runs in `_column_text_row`) | changes only 6, 8; restores 7 + 2 design links; `#0066cc` count unchanged (1/0); with `collapse_breaks=False`, `<br />` count unchanged (6: 14→14, 8: 6→6) |
| E11 | Formatter glue (Task 8) | joins text and inline tags that touch with no whitespace; also fixes Lego's pre-existing "link ." (case 7, 3 lines); no other case changes |
| E12 | Combined spike, `pytest app/design_sync/tests` (unit markers) | 2353 passed, 5 failed = `test_snapshot_matches[6..10]` only (expected regen) |
| E13 | Combined spike, fidelity gate + A3 | gate PASSED (76 sections); moved: 6 `2833:1475` −0.0012, 8 `2833:2348` −0.0005, 9 `2833:2149` −0.0004, 10 `2833:1270` +0.0001; all others 0.0000; no re-stamp needed. A3 full-image: 6 0.8128→0.8126, 8 0.8633→0.8632, others unchanged; case 10 section_min 0.0635→0.0639 |
| E14 | Output readers on combined spike (`checks_proto.py` + `probe2.py`) | `{{unsubscribeUrl}}` hrefs per case 5–10: 1/1/2/1/1/1 (base 1/0/1/0/0/0); bare fonts, blue and CTA counts unchanged from base; `&quot;Geist Mono&quot;` mutation detected as bare; `'Geist Mono', monospace !important` accepted |
| E15 | Combined spike, `make types` / `make test` / `make golden-conformance` | mypy clean, pyright 0 errors; `make test` 8652 passed, 5 failed = `test_snapshot_matches[6..10]` only (expected regen); golden conformance 26 passed, 9 skipped |

## Measured state at base (observed, E1)

| Case | Design | Design has unsubscribe text | Output unsubscribe `<a>` | Bare font families | `#0066cc` | Design CTAs | Output CTAs |
|---|---|---|---|---|---|---|---|
| 5 | maap | yes | yes | Courier New, Helvetica | 4 | 8 | 8 |
| 6 | Starbucks | yes | **no** | Roboto | 1 | 2 | 2 |
| 7 | Lego | yes | yes | Noto Sans | 3 | 9 | 9 |
| 8 | performance | yes | **no** | Arial | 0 | 2 | 2 |
| 9 | slate | yes | **no** | Arial | 0 | 2 | **0** |
| 10 | mammut | yes | **no** | Geist Mono, Helvetica | 0 | 2 | 2 |

- `#0066cc` is in no `structure.json` colour field, but in every case's `tokens.json` (shared palette, line 844). The design side of check 3 reads `structure.json` only.
- Design CTA count from the standalone walker over `structure.json` = 8/2/9/2/2/2 (`walker.py`), equal to `sum(len(s.buttons))` over the analysed layout.
- Slate's lost CTAs: `WATCH THE VIDEO` (`2833:2123`), `SHOP NOW` (`2833:2140`), named in CE-10 #428's done check.
- Done check "RED on mammut or Starbucks": font and unsubscribe checks fail on both.

## Feature Description

1. **Content checks** (`test_content_checks.py` + helper + committed allow-list): four per-case checks, each compared to the design file; strict allow-list keyed to fixing tickets.
2. **Unsubscribe pass** (`app/design_sync/unsubscribe_links.py`): in every output path (default, MJML, tree), (a) any `<a>` whose text is an unsubscribe phrase and whose href is not an ESP merge tag (`{{…}}`) gets `href="{{unsubscribeUrl}}"`; (b) if no unsubscribe link exists afterwards, every unlinked phrase in visible text is wrapped in `<a href="{{unsubscribeUrl}}">` coloured like its cell.
3. **Text-link fix**: `_column_text_row` renders style-run links (`_render_text_runs`) with the text's own colour and line breaks preserved.
4. **Formatter glue**: `format_email_html` keeps text and inline tags that touch in the source on one line.

## User Story

As the converter maintainer
I want a test that fails when output loses the unsubscribe link, falls back to a non-generic font, leaks the default blue or drops a design CTA, and a converter that always ships a working unsubscribe link
So that content regressions the pixel gate cannot see are caught on the PR that causes them, and no converted email goes out without a compliant unsubscribe.

## Problem Statement

CE-1's per-section pixel mean barely moves for a missing link, font fallback, blue link or missing button (E4: a whole new link moves a section by ≤ 0.0004). Four of six cases ship without an unsubscribe link on the default path, and **all six** on the MJML path (E6). Column text drops every design link (E10).

## Out of Scope / Non-Goals

- Fonts (CE-7 #425), `#0066cc` (CE-20 #438), slate's lost CTAs (CE-10 #428): allow-list entries.
- Inserting a link when the design has no unsubscribe phrase (compliance policy, not this ticket).
- Bare "Preferences"/"Update preferences": not an unsubscribe affordance; the phrase set is unsubscribe/opt-out and their translations.
- Tree path footer loss on Lego (E7): logged, Task 12. Tree path is off by default.
- Non-link run styling (bold/italic) in column text: `_render_text_runs` renders links only; unchanged behaviour for nodes without link runs (E10).
- `quality_contracts.check_completeness` (`app/design_sync/quality_contracts.py:133-192`) stays as is.

## Feature Metadata

**Feature Type**: New Capability (checks) + Bug Fix (unsubscribe, text links, formatter)
**Estimated Complexity**: Medium
**Primary Systems Affected**: `converter_service.py`, `component_matcher.py`, `html_formatter.py`, new `unsubscribe_links.py`; tests; `data/debug/{6,7,8,9,10}/expected.html`
**Dependencies**: none new

## Related Work

**Implements**: #420 (CE-2) · **Epic**: #439, `.agents/plans/converter-epic-slices.md:86-92`

**Back-references**: `.agents/plans/converter-epic-slices.md` (scope, conventions); `.agents/plans/ce-1-fidelity-baseline-gate.md` (gate, test-module pattern); `.claude/skills/converter-fix/SKILL.md` + `references/baselines-and-gates.md` (snapshot audit, A3).

**Forward-references**: CE-7 #425, CE-10 #428 and CE-20 #438 each delete their allow-list rows or this test fails ("retire entry").

## Deferred Items Touching This Plan

Grepped `.agents/deferred-items.json` 2026-10-01 for `0066cc`, `unsubscribe`, `font`, `cta`, `footer`, `style_run`, `link_url`, `_column_text_row`, `_render_text_runs`, `html_formatter`, `regression_runner`, `converter_service`, `component_matcher` (observed).

| id | match | decision | why |
|----|-------|----------|-----|
| `phase-53-a2-advisory-section-gate` | `regression_runner.py` | carry forward | No segmentation change; ladder unchanged (E12). |
| `phase-53g-g3-template-cta-padding-uncovered` | CTA | avoid | Count check, not padding. |
| `phase-53g-g5-pill-white-on-light-latent` | CTA text colour | avoid | Not touched. |
| `phase-53g-g4-tree-html-slot-row-shape` | tree path | avoid | The tree call site only post-processes final HTML. |
| `phase-53g-t1-social-non-icon-images-as-icons`, `phase-53g-t1-tree-path-social-label-default` | social section | avoid | Task 7 changes text cells only; images and labels untouched (E10: only link lines change). |
| `phase-53g6-card-tree-path-text-only`, `phase-53g-g4-general-sub-template-recursion` | noise | avoid | Not touched. |
| entry at ledger line ~381 (52.5 "button url lost upstream" misdiagnosis) | `style_run.link_url` | avoid | Notes that footer style-run links may be "genericized"; E10 shows they now pass through as design URLs. Mention in report. |
| new: `ce-2-tree-path-drops-footer-text` | E7 | **add** (Task 12) | Found here; tree path out of scope. |

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `.tmpscratch/ce2/spike.diff` — the reference implementation.
- `app/design_sync/converter_service.py:1002-1094` (`_assemble_phase`; `format_email_html` at `:1042`), `:520-616` (`_convert_mjml_from_layout`; `inject_section_markers` at `:579`), `:740-795` (tree path; `if not tree_html: return None` at `:774-775`).
- `app/design_sync/component_matcher.py:648` (`_safe_text`), `:659` (`_multiline_to_br`), `:732-739` (`_safe_url`), `:745-811` (`_column_text_row`), `:2188-2194` (`_FOOTER_LINK_STYLE`, `_FOOTER_MULTI_BR_RE`, `_BR`), `:2196-2248` (`_render_text_runs`), `:2340-2360` (`_footer_unsub_row`), `:2420-2423` ("Coexist" policy).
- `app/design_sync/html_formatter.py:108-252` (`format_email_html`: tokeniser `:94-97`, inline-leaf accumulation `:150-174`, plain text `:249`).
- `app/design_sync/quality_contracts.py:159-173` (button counter mirrored by the test).
- `app/qa_engine/checks/deliverability.py:81`, `:379-388` (unsubscribe link predicate shape).
- `app/qa_engine/custom_checks/brand.py:18-27` (`_GENERIC_FONTS`; copy, don't import private names).
- `app/design_sync/figma/layout_analyzer.py:1805-1860` (`_walk_for_buttons`, mirrored by the design walker).
- `app/design_sync/tests/regression_runner.py:48-61`; `manifest_schema.py` (Pydantic schema pattern); `test_converter_data_regression.py:52-66` (MSO regexes); `test_fidelity_gate.py:52-63` (`CASES`, cached `_convert`); `test_convert_document.py:53-175` (minimal node tree → `convert_document`); `ladder_harness.py` (test helper with CLI); `test_html_formatter.py` (formatter test style); `test_component_matcher_footer.py` (`_render_text_runs` tests).

### New Files to Create

- `app/design_sync/unsubscribe_links.py`
- `app/design_sync/tests/test_unsubscribe_links.py`
- `app/design_sync/tests/content_checks.py`
- `app/design_sync/tests/test_content_checks.py`
- `data/debug/content_check_allowlist.yaml` (top-level `data/debug/*` files are tracked; confirm with `git check-ignore`)

### Patterns to Follow

- Logging: `get_logger(__name__)`; events `design_sync.unsubscribe_link_repointed` (`count`) and `design_sync.unsubscribe_text_linked` (`count`).
- `ContentCheck(StrEnum)` + `CHECKS: dict[ContentCheck, …]` + test `set(CHECKS) == set(ContentCheck)`.
- `@dataclass(frozen=True)` results; Pydantic `extra="forbid"` for the allow-list.
- Strict mypy/pyright; raw JSON as `dict[str, Any]`. Never `ruff --fix` with TC rules.
- Ruff `RUF001` flags a literal `’` in source: write it as `’` inside the regex (E: spike lint run).

---

## IMPLEMENTATION PLAN

- **Phase 1 (Tasks 0–5):** checks, allow-list, tests; RED proof on base.
- **Phase 2 (Tasks 6–9):** the four code changes, each RED first. **Depends on** Phase 1 (the unsubscribe check is the case-level RED test).
- **Phase 3 (Tasks 10–13):** snapshot audit and regen, gates, A3, ledger, report, PR.

---

## STEP-BY-STEP TASKS

### Task 0: Branch, baseline, cleanup

- **IMPLEMENT**: `git fetch && git switch -c feat/ce-2-content-checks origin/main`; record `git rev-parse origin/main`. A3 before: `uv run python scripts/score-fidelity-cases.py --cases 5 6 7 8 9 10` (needs the gitignored reference PNGs and assets present in the main checkout; E5 values are the expected baseline). Remove the spike: `git worktree remove --force .claude/worktrees/ce2-spike` (its diff is in `.tmpscratch/ce2/spike.diff`).
- **VALIDATE**: `git status` shows only the four untracked PR-413 review files (never stage them).
- **SATISFIES**: AC #10.

### Task 1: CREATE `app/design_sync/tests/content_checks.py` — design readers

- **IMPLEMENT**: `load_structure`, `iter_visible_nodes` (skip `visible is False` subtrees), `design_text` (`\xa0`, ` `, ` ` → space), `design_has_unsubscribe` (imports `UNSUBSCRIBE_RE` from `app.design_sync.unsubscribe_links`), `design_has_default_blue` (`fill_color`, `text_color`, `stroke_color`, `style_runs[].color_hex`; `#0066cc`/`#06c` case-insensitive), `design_cta_count` (port `.tmpscratch/ce2/walker.py`: FRAME/COMPONENT/INSTANCE, exactly one TEXT child with non-empty `text_content` ≤ 30 chars, `height` ≤ 80, name hint in `("button","btn","cta","action","link","mj-button")` or `fill_color` upper not in `("#FFFFFF","#FFF","")`; counted nodes not recursed).
- **GOTCHA**: read `structure.json` only — never `layout.sections[].buttons` (moves with CE-9/CE-10) and never `tokens.json` (contains `#0066CC` in every case).
- **VALIDATE**: Task 4 pins.
- **SATISFIES**: AC #1–#4.

### Task 2: ADD output readers and checks to `content_checks.py`

- **IMPLEMENT** (port `.tmpscratch/ce2/checks_proto.py`):
  - `output_unsubscribe_links(html)`: lxml `<a>` count where `UNSUBSCRIBE_RE` matches href or `text_content()`, and href not in `("", "#")`.
  - `output_bare_fonts(html)`: lxml attribute values (`style` split on `;` → `font-family`; `face`), plus `font-family\s*:\s*([^;}]+)` over `<style>` blocks, plus the same two readers over the body of each `<!--[if …]>…<![endif]-->` block (lxml sees MSO as comments). Last comma item, `!important` removed, quotes stripped, lowercased, must be in `{serif, sans-serif, monospace, cursive, fantasy, system-ui, ui-serif, ui-sans-serif, ui-monospace, ui-rounded}`. Detail: sorted distinct failing families with quotes stripped, joined by `|`.
  - `output_default_blue(html)`: `#0066cc\b|#06c\b`, case-insensitive, full HTML.
  - `strip_mso(html)` (copy of the two regexes at `test_converter_data_regression.py:52-66`); `output_cta_count(html)`: on `strip_mso(html)`, `<a>` with `display:inline-block` (spaces removed) and `padding` in style.
  - `CheckResult(case, check, passed, detail)`; checks: `unsubscribe_link` (n/a pass when design has no phrase, else `links=<n>`, pass iff ≥ 1), `font_generic`, `default_blue` (n/a pass when design has it, else `count=<n>`), `cta_count` (`output=<o> design=<d>`, pass iff o ≥ d). `run_case`, `run_all` over `CASES = ["5","6","7","8","9","10"]`.
- **GOTCHA**: never regex raw attributes after `html.unescape` (`&quot;Geist Mono&quot;` would slip through a `[^;"]` class, E14). Strip MSO before counting CTAs (VML from CE-11 #429 doubles buttons).
- **SATISFIES**: AC #1–#4.

### Task 3: CREATE allow-list model, `evaluate`, CLI, and the YAML

- **IMPLEMENT**: `AllowEntry(case, check, owner, detail, note="")` with `owner` matching `^#\d+$`, `Allowlist(entries)` rejecting duplicate `(case, check)`, `extra="forbid"`. `evaluate(results, allowlist) -> list[str]`: (1) failed + no entry → "new failure"; (2) failed + detail differs → "failure changed; update the entry"; (3) passed + entry → "now passes; retire the entry (owner #N)"; (4) entry for a case not run → "stale entry". CLI `python -m app.design_sync.tests.content_checks [--empty-allowlist]` prints a Markdown table (case, check, result, detail, owner) and exits 1 on problems.
- YAML, re-derived by running the CLI **after Phase 2** (never copied from here): `font_generic` × 6 → `#425`; `default_blue` 5/6/7 → `#438`; `cta_count` 9 → `#428`. No `unsubscribe_link` rows (E14: all pass after Phase 2).
- **GOTCHA**: pinned detail stops a new bare font hiding behind CE-7's row; rule 3 makes retirement automatic.
- **VALIDATE**: `git check-ignore -v data/debug/content_check_allowlist.yaml` prints nothing.
- **SATISFIES**: AC #5, #6.

### Task 4: CREATE `app/design_sync/tests/test_content_checks.py`

- **IMPLEMENT**: enum coverage; design pins (`design_cta_count` = 8/2/9/2/2/2, `design_has_unsubscribe` all true, `design_has_default_blue` all false, and walker == `sum(len(s.buttons))` per case); reader tests on real converted HTML with mutations (remove `{{unsubscribeUrl}}` anchors → fails; `font-family:Geist Mono;` → `font-family:&quot;Geist Mono&quot;;` → still bare; → `'Geist Mono', monospace !important` → that occurrence accepted; duplicate a CTA `<a>` inside an `<!--[if mso]>` block → count unchanged); `evaluate` rules 1–4 on hand-built `CheckResult` lists; schema rejects duplicates and bad owners; `test_content_checks_hold_allowlist`.
- **GOTCHA**: mutations start from a real converted case, never synthetic email HTML.
- **VALIDATE (RED, record in report)**: `uv run python -m app.design_sync.tests.content_checks --empty-allowlist` exits 1, listing `font_generic` and `unsubscribe_link` failures on 6 and 10 at least (E1).
- **SATISFIES**: AC #1–#6, #11.

### Task 5: No commit yet

Phase 1 is RED on the unsubscribe rows by design. First commit after Task 10 (check + fixes together, all green). No `xfail` scaffolding.

### Task 6: CREATE `app/design_sync/unsubscribe_links.py` (RED first)

- **IMPLEMENT**: port from `spike.diff`. Public: `UNSUBSCRIBE_RE` (word-bounded, multi-language: en `unsubscribe|opt[\s-]?out`; de `abmelden|abbestellen`; fr `(se )?désabonner|(se )?désinscrire|désinscription`; es `darse de baja|date de baja|cancelar (la )?suscripción`; it `disiscriviti|annulla (l’)?iscrizione`; nl `afmelden|uitschrijven`; pt `descadastrar|cancelar (a )?inscrição`; sv/da/no `avregistrera|avsluta prenumerationen|afmeld`; pl `wypisz się`; accent classes as in the spike), `has_unsubscribe_link(html)`, `link_unsubscribe_text(html)`.
  - Step 1, repoint: every `<a>` whose stripped inner text matches and whose href does not start with `{{` gets `href="{{unsubscribeUrl}}"`; other attributes kept. Log `design_sync.unsubscribe_link_repointed`. Comments are not edited by this step either (E9: comments byte-identical); keep a test for it.
  - Step 2, guard: if `has_unsubscribe_link` → return.
  - Step 3, wrap: tokenise `(<!--.*?-->|<[^>]+>)`; stack of open tags with last `color:` from `style`; void tags and `/>` not pushed; comments never edited; text inside `a`/`style`/`script`/`title`/`head` never edited; each phrase in other text → `<a href="{{unsubscribeUrl}}" style="color:{nearest stack colour or inherit};text-decoration:underline;">{match}</a>`. Log `design_sync.unsubscribe_text_linked`.
- **GOTCHA**: the href is a literal, never escaped (`component_matcher.py:2340-2348`). Never use `_FOOTER_LINK_STYLE` or `#0066cc`. `{{preferencesUrl}}` "Manage Preferences" anchors are untouched (no phrase match, starts with `{{`).
- **Tests first** (`test_unsubscribe_links.py`):
  - Minimal Figma node trees (mirror `test_convert_document.py:86-175`) converted with `convert_document`: (a) TEXT "Privacy Policy | Unsubscribe", `text_color="#F9F9F9"` → exactly one `{{unsubscribeUrl}}` anchor in the text colour; record the slug it matched; (b) TEXT "adopt outdoor gear" → no anchor; (c) TEXT "Hier abmelden" → one anchor.
  - Function level on real case HTML (monkeypatch `app.design_sync.converter_service.link_unsubscribe_text` to identity, convert, then call the real function): case 5 unchanged; case 9 gains the anchor with `#F9F9F9`; case 7's design anchor is repointed, nothing wrapped; MSO-block text never edited; CTA anchors never nested; result parses with lxml.
  - Literal-string table for `UNSUBSCRIBE_RE` (E8 list: matches and non-matches).
  - Run against base → assertion failures (record).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_unsubscribe_links.py -q` red, green after Task 9.
- **SATISFIES**: AC #7, #8.

### Task 7: UPDATE `component_matcher.py` — link runs in column text (RED first)

- **IMPLEMENT** (from `spike.diff`): `_render_text_runs(text, *, link_fallback: str = "#0066cc", collapse_breaks: bool = True)`; `default_color = _safe_color(text.text_color, link_fallback)`; final return collapses `<br />` runs only when `collapse_breaks`. In `_column_text_row` (`:811`): if any run has `link_url`, inner = `_render_text_runs(text, link_fallback=_safe_color(text.text_color), collapse_breaks=False)`, else `_multiline_to_br(text.content)` as today.
- **GOTCHA**: footer callers keep both defaults, so cases 5 and 7 stay byte-identical (E10). `collapse_breaks=False` is required: without it Starbucks and performance lose 5 and 2 paragraph breaks (E10 first prototype).
- **Tests first**: in `test_column_text_styling.py` style, a `TextBlock` with a link run → `<a href=…>` present, colour = node colour, `<br />` count equals `_multiline_to_br(content)`'s; a `TextBlock` without `text_color` → link colour is `_safe_color(None)` (not `#0066cc`). Generality rule: one minimal Figma node tree (mirror `test_convert_document.py:86-175`) whose TEXT node carries a `style_runs` entry with `link_url`, laid out as a multi-column row so it routes through `_column_text_row`, run through `convert_document` → the link is in the output.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_column_text_styling.py app/design_sync/tests/test_component_matcher_footer.py -q`.
- **SATISFIES**: AC #9.

### Task 8: UPDATE `html_formatter.py` — keep touching inline content on one line (RED first)

- **IMPLEMENT** (from `spike.diff`): track `prev_flow` (last emitted line ends with text or an inline leaf) and `prev_raw` (previous raw token, whitespace tokens included). A plain-text token, or an inline-leaf group, whose raw source touches the previous flow line with no whitespace either side is appended to `lines[-1]`; every other emission resets `prev_flow`.
- **GOTCHA**: only `converter_service.py:1042` and `diagnose/runner.py:273` call the formatter (observed grep). Case 7 changes 3 lines (a pre-existing "link ." fixed), no other case changes beyond Task 6/7 (E11).
- **Tests first** (`test_html_formatter.py`): use the real fragment from Lego's base `data/debug/7/expected.html` (the footer `<a …>…</a>` followed by `.`, E11) re-joined unformatted → formatted output keeps `</a>.` on one line; the case 10 footer fragment (`|    <a …>Unsubscribe</a>`, whitespace before the tag) keeps today's split; a `<br />` between text resets the glue. No hand-written email HTML.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_html_formatter.py -q`.
- **SATISFIES**: AC #9.

### Task 9: UPDATE `converter_service.py` — three call sites

- **IMPLEMENT**: `from app.design_sync.unsubscribe_links import link_unsubscribe_text` (sorted import block, after `tuning`); `result_html = link_unsubscribe_text(format_email_html(result_html))` (`:1042`); `compiled_html = link_unsubscribe_text(inject_section_markers(compile_result.html, layout))` (`:579`; the MJML cache at `:586-592` then stores post-pass HTML); MJML cache hit `html=link_unsubscribe_text(cached.html)` (`:548-549`, so entries cached before this ships also get the link; idempotent per E9); `tree_html = link_unsubscribe_text(tree_html)` right after `if not tree_html: return None` (`:774-775`).
- **GOTCHA**: the default call must run **after** `format_email_html` (E3). The section cache stores pre-assemble sections; the pass runs on every assemble.
- **Tests**: MJML path — mirror the compile mock in `test_e2e_mjml_pipeline.py`/`test_mjml_compile.py` and assert one `{{unsubscribeUrl}}` anchor for a minimal tree whose text holds the phrase; tree path — the minimal tree with `output_format="tree"` and the flag patched on; if the tree compile falls back, assert via the fallback and say so.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_unsubscribe_links.py app/design_sync/tests/test_content_checks.py -q` green; CLI shows `unsubscribe_link` pass on all six.
- **SATISFIES**: AC #7, #8.

### Task 10: Snapshot audit and regen, gates, A3, commit

- **IMPLEMENT** (`.claude/skills/converter-fix/references/baselines-and-gates.md`):
  1. `rm -f <scratch>/<n>.html; uv run python scripts/snapshot-capture.py <n> --output <scratch>/<n>.html` for 5–10 (the script refuses to overwrite an existing `--output`, so delete first). `git diff --no-index --ignore-all-space` vs `expected.html`. Expected (E10–E12): 5 empty; 6 = 7 run links (one repointed to `{{unsubscribeUrl}}`); 7 = Unsubscribe repointed + 3 formatter-glue lines; 8 = wrapped "unsubscribe" + 2 run links; 9, 10 = one wrapped anchor each; case 8's trailing-space lines are known whitespace churn.
  2. `scripts/snapshot-capture.py <n> --overwrite` for 6–10; `git checkout --` any whitespace-only case. Never `make snapshot-capture`.
  3. `make snapshot-test`, `make converter-data-regression` (ladder unchanged).
  4. `make fidelity-gate` (E13: passes without re-stamp). A re-stamp is only allowed for the four footer sections with `REASON="CE-2: unsubscribe and design text links restored in footers"`; any other section moving beyond the margin stops for the user.
  5. A3 after; before/after table.
  6. 600px side-by-side of the mammut and Starbucks footers against `email-templates/training_HTML/for_converter_engine/<design>/manual_component_build.html`.
  7. Fill the allow-list from the CLI; full test file green.
  8. `git diff --stat origin/main...HEAD`; commit `feat(design-sync): content checks, unsubscribe and text-link fixes (CE-2)`.
- **SATISFIES**: AC #6, #10.

### Task 11: Full gate

- `make check-full`; re-read `git diff` (lint rewrites); restore `app/ai/agents/*/skill-versions.yaml` dates if touched. Amend nothing; new commit if lint changed files.
- **SATISFIES**: AC #10.

### Task 12: Ledger entry (deferred-items skill)

- `ce-2-tree-path-drops-footer-text`: severity `known-bug`, code_refs `app/design_sync/tree_bridge.py:165-168 (_fill_to_slot_value)` and `converter_service.py` tree branch; summary: with the tree bridge on, Lego's tree output carries no footer text (E7), so no unsubscribe phrase to link; closes_when: case 7 tree output contains the footer text. `introduced_commit: pending`.
- **VALIDATE**: `python3 -c "import json;json.load(open('.agents/deferred-items.json'))"`.
- **SATISFIES**: AC #12.

### Task 13: Report and draft PR

- Report `.claude/reports/ce-2-content-checks.md`: RED outputs, CLI table, snapshot audit, gate, A3, side-by-sides; every figure tagged. `piv-create-pr` (draft) with the CLI table in the body, plus the user-ratified decisions U1–U5.

---

## TESTING STRATEGY

### Unit Tests

`test_content_checks.py`, `test_unsubscribe_links.py`, additions to `test_column_text_styling.py` and `test_html_formatter.py`. All read tracked inputs only and run in `make test` and the CI Test step.

### Integration Tests

None new; snapshot, ladder and fidelity gate cover the full conversion.

### Edge Cases

| Edge case | Verified in |
|---|---|
| Phrase inside an existing design link (Lego, Starbucks) | `test_unsubscribe_links.py` case 7 repoint; snapshot 6/7 |
| `{{preferencesUrl}}` anchor | `test_unsubscribe_links.py` case 5 unchanged |
| Phrase inside MSO conditional | `test_unsubscribe_links.py` |
| No enclosing colour | unit test → `color:inherit` |
| "adopt outdoor", "Subscribe" | regex literal table + minimal tree (b) |
| Non-English footer | minimal tree (c) "Hier abmelden" |
| Text node without `text_color`, with link run | `test_column_text_styling.py` addition |
| Link followed by punctuation | `test_html_formatter.py` addition; snapshot 6, 7 |
| VML-doubled CTA | MSO duplicate mutation test |
| Quoted / `!important` fonts | reader mutation tests |
| Allow-list entry that now passes | `evaluate` rule 3 |
| Invisible design nodes | `iter_visible_nodes` test on a real subtree with `visible` forced False |
| MJML and tree outputs | Task 9 tests |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

- `uv run ruff format --check app/design_sync` · `uv run ruff check --no-fix app/design_sync`
- `uv run mypy app/` · `uv run pyright app/` (`make types`)

### Level 2: Unit Tests

- `uv run pytest app/design_sync/tests/test_content_checks.py app/design_sync/tests/test_unsubscribe_links.py app/design_sync/tests/test_column_text_styling.py app/design_sync/tests/test_html_formatter.py -q`
- `make test`

### Level 3: Converter gates

- `make snapshot-test` · `make converter-data-regression` · `make fidelity-gate` · `uv run python scripts/score-fidelity-cases.py --cases 5 6 7 8 9 10` · `make check-full`

### Level 4: Manual Validation

1. `uv run python -m app.design_sync.tests.content_checks` → all rows pass or allow-listed; paste into the PR.
2. Open captured case 6 and 10 HTML at 600px: "Unsubscribe" underlined in the footer colour, no space before the following ".".
3. Delete the `#425` case-10 row → `pytest test_content_checks.py` fails "new failure"; restore.

---

## ACCEPTANCE CRITERIA

- [ ] AC #1 Unsubscribe check: fails when design text has a phrase and output has no unsubscribe `<a>` whose href is an ESP merge tag (`{{…}}`; tightened from "a real href" in PR #450 review L1); n/a without a phrase.
- [ ] AC #2 Font check: every `font-family` (attrs, `<style>`, `face`, MSO) ends in a generic family.
- [ ] AC #3 Blue check: `#0066cc`/`#06c` absent unless a `structure.json` colour field has it.
- [ ] AC #4 CTA check: non-MSO output CTAs ≥ design CTAs from `structure.json`.
- [ ] AC #5 Allow-list strict: new, changed, retired-but-listed and stale entries all fail.
- [ ] AC #6 Allow-list at merge: fonts ×6 → #425, blue ×3 → #438, slate CTA → #428 (CLI-derived).
- [ ] AC #7 Every case whose design has the phrase ships ≥ 1 `{{unsubscribeUrl}}` link on the default path; the MJML and tree tests show the same; minimal trees prove the rule is design-agnostic and multi-language.
- [ ] AC #8 Design-linked unsubscribe phrases point at `{{unsubscribeUrl}}`; `{{preferencesUrl}}` untouched.
- [ ] AC #9 Column text keeps its design links, colour and line breaks; touching inline content stays on one line.
- [ ] AC #10 Case 5 byte-identical; 6–10 differ only as listed in Task 10.1; ladder unchanged; fidelity gate green; A3 reported; `make check-full` green.
- [ ] AC #11 RED proof recorded: `--empty-allowlist` fails on mammut and Starbucks; unsubscribe check fails on 6/8/9/10 before Phase 2.
- [ ] AC #12 Deferred entry for the tree-path footer loss added.

---

## COMPLETION CHECKLIST

- [ ] Tasks done in order, each VALIDATE run
- [ ] `make check-full` green; `git diff` re-read after lint
- [ ] Report with tagged figures; draft PR with CLI table

---

## OPEN QUESTIONS / ASSUMPTIONS

None open. Former risks and how each was closed:

| Risk | Closed by |
|---|---|
| R1 fidelity gate re-stamp | E4/E13: measured on the spike |
| R2 MJML and tree paths not covered | U2 + Task 9; E6/E7 measured (real sidecar) |
| R3 design text links dropped | U4 + Task 7; E10 measured |
| R4 English-only phrases | multi-language `UNSUBSCRIBE_RE`. English measured (E8, 0 false positives in 208 files); non-English phrases checked only against literal strings, false-positive rate **unmeasured** (no non-English corpus). Residual: step 1 repoints any link whose text is a phrase, so a Dutch "Afmelden" used as log-out or a German "abbestellen" for an order would be repointed to `{{unsubscribeUrl}}`. Accepted; CE-5 #423 held-out files are the first non-English evidence |
| Formatter "link ." space | Task 8; E3/E11 measured. Not one of U1–U5: required because U4 would otherwise ship "Unsubscribe ." on Starbucks; it also changes Lego (non-target, 3 lines, a pre-existing defect fixed). Flagged to the user for veto |
| Design link to a mock-up URL | U5 + Task 6 step 1 |

## NOTES (open canvas)

- Rejected O2 (route footers to `email-footer`): only helps designs classified as footers.
- Rejected wrapping inside `_column_text_row`/`_safe_text`: several call sites, nesting risk inside CTA labels, text-block and hero paths uncovered.
- Rejected design CTA count from `layout.sections[].buttons`: moves with CE-9/CE-10.
- Wrapping every unlinked occurrence (only when no unsubscribe link exists) was chosen over first-only: each occurrence in the corpus is a single footer line (E8).

## AMENDMENTS

- 2026-10-01 — Risks R1–R4 closed by a measured spike at the user's request ("address all risks"); scope extended by U4/U5 (text links in column text, href repoint) and the formatter glue the spike exposed. Confidence 8 → 10.

## Amendment: PR #450 review round 1 (2026-10-01)

| Finding | Change | Supersedes |
|---|---|---|
| M1 | `UNSUBSCRIBE_RE`'s English opt-out excludes privacy opt-outs ("opt-out of sale/sharing/cookies/targeted ads…", "cookie opt-out"); they are not repointed, not wrapped, not counted | Task 6 regex `opt[\s-]?out` |
| L1 | `output_unsubscribe_links` counts only `{{…}}` hrefs | AC #1 "real href" |
| L2 | `format_email_html` strips and glues ASCII whitespace only, so U+00A0 at token edges survives; snapshots 6, 7, 8 regenerated | Task 8 glue `isspace()`; Task 10.1 list for 6/7/8 |
| L3 | VML twin never filled (label + href) → ledger `ce-2-cta-button-vml-twin-unfilled` | none |

Detail and evidence: `.claude/reports/pr-450-review-fixes.md`.
