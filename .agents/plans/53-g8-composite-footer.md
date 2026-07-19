# Feature: Composite-footer cleanup — per-node rows, style-run links, legal-compliance owner (Track G · G8 / 51.6)

The plan below is complete but the executor MUST validate every `file:line` and symbol against the tree before editing — refs are pinned to **HEAD `e4f4d587`** (research pass 2026-07-19), symbols are the anchor. Pay special attention to importing `DesignSystem`/`FooterConfig` from the right module and to the `StyleRun.start/end`-vs-stripped-`content` offset caveat.

## Feature Description

`_fills_footer` (`app/design_sync/component_matcher.py:2123`) currently joins every Figma footer text node with `<br><br>` into the single `footer_editorial` slot and never emits `footer_legal`. Three defects flow from that:

1. **Run-on lines** — hard line breaks *inside* a node (`\n`, ` `) collapse to whitespace (`_safe_text` only escapes), so c7's `*For full Terms & Conditions, click here␊⁨…This email was sent to: …` renders as one run-on line.
2. **Dead style-run links** — c7's footer nodes carry per-run `link_url` (the `Unsubscribe | Privacy | Cookies | Preferences` bar → campaign URL; the T&C run underlined; the `email@brand.emaillove.com` run `#0080C6`+underline). `_fills_footer` never reads `style_runs`, so all links die.
3. **Boilerplate leakage** — `footer_legal` is left verbatim (`_PRESERVE_UNFILLED_SLOTS`), so the seed's fake `© 2026 Company Name` / `123 Business Street, London` renders under every converted email.

G8 makes `_fills_footer` the footer's **content + compliance owner**: per-node editorial rows with style-run links, and a footer_legal block that is deterministically rebuilt (FooterConfig substitution when present; a reconstructed `{{unsubscribeUrl}}` compliance row with the fake literals dropped when absent). This retires `phase-53f-brandrepair-footer-gaps` (BrandRepair stays unwired/dead for the converter path).

## User Story

As a **brand operator importing a Figma email**,
I want the **converted footer to preserve my designed links and legal copy while guaranteeing a working unsubscribe**,
So that **the email is visually faithful and legally compliant without leaking placeholder "Company Name / Business Street" boilerplate**.

## Problem Statement

The converter footer is neither faithful (drops links + run-on lines) nor compliant (leaks fake legal literals, and only accidentally keeps `{{unsubscribeUrl}}` via slot-preservation). The one-string `<br><br>` join cannot express per-node typography, per-run links, or a substitutable legal block.

## Solution Statement

Rewrite `_fills_footer` to emit **two** SlotFills:
- **`footer_editorial`** = a nested `<table>` inside the editorial cell, one `<tr><td>` per design text node, each rendered with its design typography and its style-run `<a>` links (multi-line via `_multiline_to_br`).
- **`footer_legal`** = a rebuilt compliance block. The `{{unsubscribeUrl}}` unsub row is an **invariant** (always emitted). When a project `DesignSystem.footer` (`FooterConfig`) is present, its `company_name`/`legal_text`/`address` populate the legal lines; when absent, the fake ©/address rows are dropped and only the reconstructed unsub row remains.

`design_system` is threaded (default `None`) from `import_service.run_conversion` down to the builder dispatch so `_fills_footer` can read `FooterConfig`.

## Out of Scope / Non-Goals

- **Not changing** the seed file `email-templates/components/email-footer.html` (structure stays; slots are filled at runtime). Consequently golden-conformance is untouched.
- **Not editing** `_PRESERVE_UNFILLED_SLOTS` (component_renderer.py:45) — footer_legal is now always *filled*, so preservation is moot; leaving the frozenset is the surgical choice.
- **Not touching** the MJML output path (`convert_document_mjml` → `mjml_template_engine.py`, which builds context from `ExtractedTokens`, not `DesignSystem`). The corpus + acceptance exercise the component path (`convert_document`). MJML-path footer compliance is a separate concern → carry-forward note, not this ticket.
- **Not** surgically stripping/merging the design's own decorative unsub/prefs tokens (ratified "Coexist" policy — see Dedupe table). No token-level href rewriting.
- **Not** synthesizing `mailto:` links — the email address run's href is its Figma `link_url` (campaign URL), emitted as-is.
- **Not** re-segmenting the footer or changing section counts (ladder snapshot unaffected).

## Feature Metadata

**Feature Type**: Enhancement + Bug Fix (fidelity + compliance)
**Estimated Complexity**: Medium-High (6-hop threading + fixture regeneration + compliance policy)
**Primary Systems Affected**: `app/design_sync/component_matcher.py` (`_fills_footer`), the converter match chain, `app/design_sync/import_service.py`, corpus fixtures `data/debug/{5,7}`
**Dependencies**: `FooterConfig`/`DesignSystem` (`app/projects/design_system.py`), `ProjectService.get_design_system`

## Related Work

**Implements**: Track G · G8 / roadmap 51.6 (composite-footer cleanup). Depends on 51.1 (composite-slot infra, shipped #354) + 51.2 (composite render, shipped #357).

**Back-references**:
- `.agents/plans/53-g4-composite-slot-infrastructure.md` — SlotFill/CompositeSlot infra + nested-row rendering this reuses.
- Track F / **RC-F5** (`_fills_footer` docstring `component_matcher.py:2128-2136`) — the "preserve footer_legal verbatim" decision G8 **supersedes**. This plan makes the builder actively emit footer_legal.
- Deferred ledger `phase-53f-brandrepair-footer-gaps` (`.agents/deferred-items.json`) — retired by this work.

**Forward-references**: (none yet)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `app/design_sync/component_matcher.py:2123-2146` (`_fills_footer`) — the function to rewrite; today reads only `section.texts`, joins `<br><br>`.
- `app/design_sync/component_matcher.py:722-788` (`_column_text_row`) — **the per-node `<tr><td>` typography builder to mirror/extend**. Emits font-family/size/weight/color/line-height/align/letter-spacing/transform/decoration + `mso-line-height-rule:exactly` + `_multiline_to_br(text.content)`. Hardcodes `padding:0 0 8px`.
- `app/design_sync/component_matcher.py:636-646` (`_multiline_to_br`) + `:633` (`_LINE_SEP_RE`) — hard-break → `<br />` (handles `\n`,`\r\n`,` `,` `). Reuse; do NOT split on `"\n"` alone.
- `app/design_sync/component_matcher.py:625` (`_safe_text`), `:700` (`_safe_color`), `:709` (`_safe_url`) — escaping/validation helpers. `_safe_url` allows `http/https/mailto/tel//`.
- `app/design_sync/component_matcher.py:28-52` (`SlotFill`) — `slot_id/value/slot_type`; `slot_type="body"` text fills go through `_fill_text_slot`.
- `app/design_sync/component_matcher.py:97-155` (`match_section`, `match_all`) + `:505-589` (`_build_slot_fills` + dispatch at `:589`) + `:158-212` (VLM path) — the threading chain; dispatch passes only `image_urls=`,`slug=` today.
- `app/design_sync/figma/layout_analyzer.py:73-91` (`TextBlock`) — `content`, `style_runs`, `text_color`, `text_align`, `font_*`, `line_height`, `letter_spacing`, `text_transform`, `text_decoration`, `role_hint`. **No y-field — order is tree order.**
- `app/design_sync/figma/layout_analyzer.py:179-258` (`EmailSection`) — `.texts`, `.element_gaps` (`:204`), `.bg_color`.
- `app/design_sync/protocol.py:82-93` (`StyleRun`) — `start`,`end`,`bold`,`italic`,`underline`,`strikethrough`,`color_hex`,`font_size`,`link_url`. Offsets are into RAW chars; `content` is `raw.strip()` → **clamp/guard offsets**.
- `app/projects/design_system.py:87-95` (`FooterConfig`) — `company_name`(req), `legal_text`(""), `address`(""), `unsubscribe_text`("Unsubscribe"). **No year, no unsub_url field.** `:133-166` (`DesignSystem`, `.footer: FooterConfig | None`). `:169-176` (`load_design_system`).
- `app/projects/service.py:156-158` (`ProjectService.get_design_system`) — parse `Project.design_system` JSON. Load point for threading.
- `app/design_sync/import_service.py:86` + `~:101-133` + `:231/237,293/300` — `run_conversion`; scoped db + `project_id` in scope; calls `convert_document`/`convert_document_mjml`.
- `app/design_sync/converter_service.py:306-317` (`convert_document`), `~:380` (`_convert_with_components`), `:663-671`/`:707-713` (`_match_phase`→`match_all`) — threading hops.
- `app/design_sync/component_renderer.py:45-53` (`_PRESERVE_UNFILLED_SLOTS`), `:918-994` (`_fill_slots`), `:1125-1163` (`_fill_text_slot`), `:228-248` (`_find_matching_close` — depth-aware; nested table inside a `<td>` is NOT truncated). **Leave unchanged; understand for correctness.**
- `email-templates/components/email-footer.html` — the seed (below). Confirms nested-table-in-cell is the idiom.
- `app/design_sync/tests/test_converter_data_regression.py` — universal + manifest + ladder assertions; `content_cov` compares actual vs `expected.html`. `manifest_schema.py:62-63` (`required_content`/`forbidden_content` — both **empty** for c5/c7).

### Ground-truth data (verified this session, HEAD e4f4d587)

**Seed `email-footer.html`** — `footer_editorial` = empty `<td>` (above); `footer_legal` = `<td>` wrapping a nested `<table>` of 3 `<tr>`: `© 2026 Company Name…`, `123 Business Street, London, EC1A 1BB`, and one links cell `Unsubscribe→{{unsubscribeUrl}}` `|` `Manage Preferences→{{preferencesUrl}}` `|` `Privacy Policy→https://example.com/privacy` (all `color:#0066cc;text-decoration:underline`, `class="footer-link"`).

**c7 (LEGO, `data/debug/7`)** footer section `texts` (order = tree order):
- Node A: `Unsubscribe␠␠ | ␠␠Privacy Policy␠␠ | ␠␠Cookies Policy␠␠ | ␠␠Preferences` — `#000000`, center, 12px, wt 500. style_runs: 4 links (0-11,18-32,39-53,60-71) all `link_url=https://emaillove.com/…#`, no underline, no run color.
- Node B: `*For full Terms & Conditions, click here␊⁨␠This email was sent to: email@brand.emaillove.com. LEGO Aastvej 1, Billund, 7190, Denmark` — `#000000`, center, 11px, wt 500. style_runs: `0-41` link+**underline** (T&C); `67-92` (`email@brand.emaillove.com`) link+**`#0080C6`**+**underline**; interior non-link runs. Contains a `\n ` hard break (the run-on bug).
- No project DesignSystem → **FooterConfig absent**. c7 is itself a **dedupe case** (design already has an Unsubscribe/Preferences bar).

**c5 (MAAP, `data/debug/5`)** footer section `texts`:
- Node 1: `Contact Us … Instagram … Facebook … Strava` — `#FFFFFF`, 14px, wt 400, **no style_runs** (plain text).
- Node 2: `No longer want to receive these emails? You can unsubscribe here.` — `#FFFFFF`, 12px, wt 400, **no style_runs** → its "unsubscribe here" is **dead plain text**. FooterConfig absent. Footer bg `#000000`.
- **Proves the invariant**: suppressing the seed unsub row here would ship c5 with no working unsubscribe.

**Gate facts**: c5/c7 manifests have empty `required_content`/`forbidden_content` + `patterns: []` → no hard footer-literal assertions. Ladder tracks section counts (footer stays 1 section). `content_cov` metric = actual-vs-expected diff → **expected.html must be regenerated to byte-match new output**. `{{unsubscribeUrl}}`/`{{preferencesUrl}}` alone → `liquid_syntax` valid + `personalisation_syntax` detects UNKNOWN platform → both PASS.

### Patterns to Follow

- **Per-node row = nested `<table>` inside the `footer_editorial` `<td>`** (mirror `footer_legal` in the seed). Fill value is a self-contained `<table>…</table>` string; `_find_matching_close` handles depth. No `stacked_*`/`composite` splice needed.
- **Typography** per row from `_column_text_row` (font-family escaped `quote=True` + web-safe fallback; size `int`; weight raw; `_safe_color`; line-height `round(px)`; align allowlist; letter-spacing skip `0.0`; transform/decoration allowlist; `mso-line-height-rule:exactly`). Footer default size 12px, color inherits node `text_color`.
- **Style-run links**: reconstruct the cell text by walking runs in `start` order, emitting `content[cursor:run.start]` plain and `content[run.start:run.end]` wrapped in `<a href="{_safe_url(link_url)}" style="color:{_safe_color(run.color_hex, node_text_color)};text-decoration:{underline?}">…</a>` when `link_url` set. Escape every segment with `_multiline_to_br`. Clamp `start/end` to `len(content)`; skip overlapping/backward runs.
- **Merge tags are constants, not user input** — emit `{{unsubscribeUrl}}`/`{{preferencesUrl}}` as literal strings (never through `_safe_text`; they contain no `&<>` and must pass through for Liquid).
- **Threading**: single optional kwarg `design_system: DesignSystem | None = None` at every hop; `_fills_footer` already swallows `**_kw`, so the ~30 other builders are untouched.

---

## IMPLEMENTATION PLAN

### Phase 1: Thread `design_system` to the builder — Foundation
**Independent of** Phases 2/3 (they don't need the value to compile; only the footer_legal *present* branch consumes it).

Add `design_system: DesignSystem | None = None` through the component-path chain and load it in `import_service`. Default `None` keeps every existing caller/test green.

### Phase 2: Style-run link renderer
**Independent of** Phase 1. Pure helper: `TextBlock` → HTML string with `<a>` links from `style_runs`. RED-testable in isolation.

### Phase 3: Per-node editorial rows
**Depends on:** Phase 2 (rows embed the link renderer). Build the nested-table `footer_editorial` value from `section.texts`.

### Phase 4: `footer_legal` compliance policy (the core)
**Depends on:** Phase 1 (FooterConfig access). Emit the always-present compliance block; substitute vs fallback per the matrices below.

### Phase 5: Fixtures, gates, ledger, anti-drift close-out
**Depends on:** Phases 1-4. Regenerate + hand-verify c5/c7; run `make check-full`; close the ledger entry; patch TODO.md + later G-prompts.

---

## LEGAL / DEDUPE POLICY (compliance-sensitive — user-visible, ratified "Coexist")

**Invariant (never conditional):** `footer_legal` ALWAYS emits the functional `{{unsubscribeUrl}}` unsub row. Rationale: c5 shows a design's own unsub can be dead plain text; the compliance row is the only guarantee.

### Table A — What each slot emits (by FooterConfig × design footer content)

| FooterConfig | Design footer | `footer_editorial` | `footer_legal` |
|---|---|---|---|
| **absent** | own unsub/prefs links (c7) | design nodes verbatim as per-node rows + style-run links | reconstructed unsub row only (`{{unsubscribeUrl}}` \| `{{preferencesUrl}}` \| privacy). Fake ©/address **dropped**. Coexists with design's decorative unsub → 2 visible unsub links, **1 functional** |
| **absent** | dead unsub text / none (c5) | design nodes verbatim | same reconstructed unsub row = the **only** working unsubscribe |
| **absent** | no footer texts at all | (empty editorial) | same reconstructed unsub row (empty-texts early-return removed) |
| **present** | any | design nodes verbatim | `© {company_name}` (or `{legal_text}`) + `{address}` (if set) + unsub row (`{unsubscribe_text}`→`{{unsubscribeUrl}}` \| Manage Preferences→`{{preferencesUrl}}` \| Privacy Policy→privacy). **No fake literals.** |

"Dedupe" = exactly **one compliance row** (never duplicated); the design's decorative unsub/prefs stays untouched (no token rewriting).

### Table B — FooterConfig-absent fallback matrix (the compliance-critical branch: footer_legal cell content)

| Seed legal row | FooterConfig present | FooterConfig **absent** (fallback) |
|---|---|---|
| © line | `© {company_name}. All rights reserved.` — or `{legal_text}` verbatim if non-empty | **DROPPED** (was fake `© 2026 Company Name`) |
| address line | `{address}` if non-empty, else omitted | **DROPPED** (was fake `123 Business Street…`) |
| unsub row | `{unsubscribe_text}`→`{{unsubscribeUrl}}` \| Manage Preferences→`{{preferencesUrl}}` \| Privacy Policy→`https://example.com/privacy` | **ALWAYS emitted** verbatim: `Unsubscribe`→`{{unsubscribeUrl}}` \| `Manage Preferences`→`{{preferencesUrl}}` \| `Privacy Policy`→`https://example.com/privacy` (same `color:#0066cc;text-decoration:underline;class="footer-link"` styling as seed) |

Notes: `FooterConfig` has no year field and `Date.now` is unavailable in this context — the © line carries **no fabricated year** (use `legal_text` when the brand wants a year). `company_name`/`legal_text`/`address` are project data → escape via `_safe_text`. `unsubscribe_text` is the visible **label** only; href is always the `{{unsubscribeUrl}}` merge tag.

---

## STEP-BY-STEP TASKS

Execute top-to-bottom. Each `VALIDATE` is non-interactive.

### Phase 1 — Threading

#### UPDATE `app/design_sync/component_matcher.py` — dispatch + match chain
- **IMPLEMENT**: add `design_system: DesignSystem | None = None` param to `_build_slot_fills` (`:505`), `match_section` (`:97`), `match_all` (`:136`), and `match_section_with_vlm_fallback` (`:158`). Pass `design_system=design_system` at both `_build_slot_fills` call sites (`:122`, `:212`) and at the `builder(...)` dispatch (`:589`).
- **IMPORTS**: under `TYPE_CHECKING`, `from app.projects.design_system import DesignSystem`.
- **GOTCHA**: `_fills_footer` swallows `**_kw` — do NOT add the kwarg to the other builders. Keep the dispatch call passing `design_system=` to all (harmless for `**_kw` builders).
- **VALIDATE**: `uv run pyright app/design_sync/component_matcher.py`

#### UPDATE `app/design_sync/converter_service.py` — thread through convert path
- **IMPLEMENT**: add `design_system: DesignSystem | None = None` to `convert_document` (`:306`), `_convert_with_components`, `_match_phase` (`:663`); pass to `match_all` (`:707`).
- **PATTERN**: mirror how `image_urls`/`gradients` are threaded through the same functions.
- **VALIDATE**: `uv run pyright app/design_sync/converter_service.py`

#### UPDATE `app/design_sync/import_service.py` — load DesignSystem
- **IMPLEMENT**: in `run_conversion`, load `design_system = await ProjectService(...).get_design_system(project_id)` (guard: `None` when the project has no design_system) inside the existing scoped-db block; pass `design_system=design_system` into `convert_document(...)` (`:237`/`:300`). Leave `convert_document_mjml` unchanged (out of scope).
- **GOTCHA**: verify `get_design_system` returns `DesignSystem | None` and takes the project id already in scope; do not open a second session.
- **VALIDATE**: `uv run pyright app/design_sync/import_service.py`

### Phase 2 — Style-run link renderer

#### ADD `_render_text_runs(text: TextBlock) -> str` to `component_matcher.py`
- **IMPLEMENT**: if `not text.style_runs` → return `_multiline_to_br(text.content)`. Else walk runs sorted by `start`, `cursor=0`, `n=len(content)`; for each run clamp `s,e` to `[0,n]`, skip if `s<cursor` or `e<=s`; emit `_multiline_to_br(content[cursor:s])` then the run segment. For `run.link_url`: wrap in `<a href="{_safe_url(run.link_url)}" style="color:{_safe_color(run.color_hex, _safe_color(text.text_color, '#0066cc'))};text-decoration:{'underline' if run.underline else 'none'};">{_multiline_to_br(seg)}</a>`. Non-link segment → `_multiline_to_br(seg)`. Trailing `content[cursor:]` appended.
- **GOTCHA**: `start/end` index RAW chars but `content` is stripped — clamping + `s<cursor` guard prevents index errors and overlap; a leading-whitespace node may shift offsets (accept minor drift; c5/c7 nodes have no leading WS).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_component_matcher_footer.py -k run -q` (new file, Phase 5)

### Phase 3 — Per-node editorial rows

#### ADD `_footer_editorial_rows(section) -> str` + `_footer_row(text, pad_bottom) -> str`
- **IMPLEMENT**: `_footer_row` mirrors `_column_text_row` typography (family/size(default 12)/weight/`_safe_color(text.text_color)`/line-height/align(center default)/letter-spacing/transform/decoration/`mso-line-height-rule:exactly`) but inner content = `_render_text_runs(text)` and `padding:0 0 {pad_bottom}px 0`. `_footer_editorial_rows` wraps one `<tr>` per `section.texts` in a `<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">`; `pad_bottom` = `int(section.element_gaps[i])` when available else 12, last row 0.
- **PATTERN**: `_column_text_row` (`:722-788`) for the declaration order.
- **GOTCHA**: keep `role="presentation"` on the table (accessibility check + universal assertions). No `<div>`/`<p>` (email-structure rule).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_component_matcher_footer.py -k editorial -q`

### Phase 4 — footer_legal compliance owner + `_fills_footer` rewrite

#### ADD `_footer_legal_html(design_system) -> str`
- **IMPLEMENT**: build the nested legal `<table>`. Unsub row (ALWAYS) = the seed's row-3 literal (`{{unsubscribeUrl}}`/`{{preferencesUrl}}`/`https://example.com/privacy`, `#0066cc` underline, `class="footer-link"`), with the visible unsub label = `_safe_text(fc.unsubscribe_text)` when FooterConfig present else `Unsubscribe`. When `design_system and design_system.footer` (`fc`): prepend `© {_safe_text(fc.company_name)}. All rights reserved.` (or `_safe_text(fc.legal_text)` if `fc.legal_text`) row and, if `fc.address`, an `{_safe_text(fc.address)}` row (12px `#666666` center, `mso-line-height-rule:exactly`, matching seed styling). When absent: unsub row only.
- **GOTCHA**: emit merge tags as raw literals (no `_safe_text`). Preserve seed styling so visual regression stays tight.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_component_matcher_footer.py -k legal -q`

#### UPDATE `_fills_footer(section, _cw, *, design_system=None, **_kw)` (`:2123`)
- **IMPLEMENT**: replace body. Remove the `if not section.texts: return []` early-return. Compute `editorial = _footer_editorial_rows(section)` (empty string if no texts); `legal = _footer_legal_html(design_system)`. Return `[SlotFill("footer_editorial", editorial), SlotFill("footer_legal", legal)]` (omit the editorial fill when `not section.texts` so the empty cell blanks cleanly, but always emit footer_legal).
- **PATTERN/REPLACE**: update the RC-F5 docstring (`:2128-2136`) to state G8 supersedes "preserve verbatim" — the builder now owns footer_legal.
- **GOTCHA**: `footer_editorial` fill is `slot_type="body"` (default "text" is fine → `_fill_text_slot`). Nested `<table>` value is fine (`_find_matching_close` is depth-aware).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_component_matcher_footer.py -q`

### Phase 5 — Fixtures, gates, ledger, anti-drift

#### CREATE `app/design_sync/tests/test_component_matcher_footer.py`
- **IMPLEMENT** (RED-first): unit tests building `EmailSection`/`TextBlock`/`StyleRun` fixtures for: (a) style-run link emission (href, underline, `#0080C6`), (b) multi-line `\n ` → `<br />`, (c) per-node rows (one `<tr>` per node), (d) footer_legal absent = unsub row only, no `Company Name`/`Business Street`, `{{unsubscribeUrl}}` present, (e) footer_legal present = FooterConfig `company_name`/`address` substituted, (f) empty-texts section still emits footer_legal, (g) c7 coexistence (design Unsubscribe + compliance `{{unsubscribeUrl}}` both present).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_component_matcher_footer.py -v`

#### UPDATE corpus fixtures `data/debug/5` and `data/debug/7`
- **IMPLEMENT**: `make converter-data-regression CASE=5` then `CASE=7` (or `make snapshot-capture CASE=5/7`) to regenerate `actual.html`; hand-verify each new footer against Table A/B; copy the intended footer region into `expected.html` (byte-match). Re-run to confirm `actual==expected` for the footer region.
- **GOTCHA**: `content_cov` silently drops if `expected.html` ≠ output — diff the footer region explicitly. Confirm no fake `Company Name`/`Business Street` remains; confirm `{{unsubscribeUrl}}` present in both.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k "case_5 or case_7" -v` + `uv run python -m app.design_sync.tests.regression_runner --report`

#### VERIFY snapshot + ladder
- **IMPLEMENT**: `make snapshot-test`; regen snapshots only if an *intended* footer diff trips them (`make snapshot-capture CASE=…`). Ladder should be unchanged (section counts constant) — do NOT regen unless it drifts.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_snapshot_regression.py -v`

#### CLOSE ledger `phase-53f-brandrepair-footer-gaps`
- **IMPLEMENT**: set `status: "closed"`, add `closed_commit`. Note (precise): "G8 makes `_fills_footer` the converter footer's compliance owner — it now always emits the `{{unsubscribeUrl}}` compliance row and rebuilds footer_legal (supersedes RC-F5 preserve-verbatim). BrandRepair stays unwired/dead for the converter path. The scaffolder-pipeline decorative-footer symptom is a DIFFERENT (non-converter) path not exercised here; this closure covers the converter (the entry's `code_refs` home)."
- **VALIDATE**: `python3 -c "import json; json.load(open('.agents/deferred-items.json'))"`

#### ANTI-DRIFT: TODO.md + later G-prompts
- **IMPLEMENT**: refresh TODO.md Track G intro/status row if c5/c7 scores moved; patch any LATER G-prompt (`.agents/plans/53-g9-*`, `53-g-production-readiness-*`) whose `file:line` refs, scores, or mechanism claims about `_fills_footer`/footer this change invalidated (symbols are the anchor; refs there pinned to `a660262c`). Do NOT edit frozen plan-file snapshots.
- **VALIDATE**: `git diff --stat`

#### GATE
- **VALIDATE**: `make check-full`

---

## TESTING STRATEGY

### Unit Tests (RED-first, `app/design_sync/tests/test_component_matcher_footer.py`)
Fixture-built `EmailSection`/`TextBlock`/`StyleRun` — cover the 7 cases above. AsyncMock not needed (pure functions). Assert on emitted HTML substrings (href, `text-decoration:underline`, `#0080C6`, `<br />`, one `<tr>` per node, `{{unsubscribeUrl}}` present, `Company Name`/`Business Street` absent, FooterConfig substitution).

### Integration / corpus
`test_converter_data_regression.py` cases 5 & 7 (actual vs regenerated expected; universal balanced-table/MSO/no-div assertions). `test_snapshot_regression.py`. `regression_runner --report` (overall_score must not regress: c5 ~0.889, c7 1.0).

### Edge Cases
- Node with `style_runs=()` → plain `_multiline_to_br`.
- Overlapping/backward run offsets → guarded (skip).
- Run offset > `len(content)` (leading-strip drift) → clamped.
- Empty `section.texts` → editorial omitted, footer_legal still emitted.
- FooterConfig with empty `address`/`legal_text` → those rows omitted, unsub row still present.
- Multiple consecutive separators `\n ` → decide single vs double `<br />` (default: reuse `_multiline_to_br` as-is = one `<br />` per separator; hand-verify c7 reads cleanly, collapse only if it looks wrong).

---

## VALIDATION COMMANDS

### Level 1 — Syntax & types
`uv run ruff check app/design_sync/ --no-fix` · `uv run pyright app/design_sync/component_matcher.py app/design_sync/converter_service.py app/design_sync/import_service.py`

### Level 2 — Unit
`uv run pytest app/design_sync/tests/test_component_matcher_footer.py -v`

### Level 3 — Corpus/integration
`uv run pytest app/design_sync/tests/test_converter_data_regression.py -k "case_5 or case_7" -v` · `make snapshot-test` · `uv run python -m app.design_sync.tests.regression_runner --report`

### Level 4 — Manual
Inspect `data/debug/7/actual.html` footer: bar links present, T&C underlined, email `#0080C6`, no run-on, no `Company Name`/`Business Street`, one `{{unsubscribeUrl}}` compliance row. `data/debug/5/actual.html`: social + unsub-text rows, `{{unsubscribeUrl}}` present, no fake literals.

### Level 5 — Full gate
`make check-full`

---

## ACCEPTANCE CRITERIA (user-visible)

- [ ] **c7 legal** = three centered editorial lines with working links — the `Unsubscribe|Privacy|Cookies|Preferences` bar (campaign hrefs), the underlined `*For full Terms & Conditions, click here`, and the `email@brand.emaillove.com` `#0080C6` underlined link — the `\n ` run-on split to separate lines; a **bold-weight (500) address** line; plus **ONE** compliance unsub row (`{{unsubscribeUrl}}`).
- [ ] **Zero `Company Name` / `Business Street` leakage** in c5 & c7 output while FooterConfig absent.
- [ ] **`{{unsubscribeUrl}}` guaranteed** in every footer (invariant), including empty-texts and dead-design-unsub (c5).
- [ ] **c5 footer re-verified** — social + unsub-text rows preserved, fake literals gone, `{{unsubscribeUrl}}` present; overall_score not regressed.
- [ ] **FooterConfig present** substitutes `company_name`/`legal_text`/`address` (unit-tested; no corpus fixture).
- [ ] `liquid_syntax` + `personalisation_syntax` PASS on the footer merge tags.
- [ ] Ledger `phase-53f-brandrepair-footer-gaps` closed with the precise note.
- [ ] `make check-full` green.

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order; each `VALIDATE` passed
- [ ] Unit + corpus + snapshot green; overall_score c5/c7 not regressed
- [ ] `expected.html` c5/c7 byte-match new output
- [ ] `make check-full` green
- [ ] Ledger closed; TODO.md + later G-prompts patched (frozen snapshots untouched)
- [ ] `git diff` isolated to G8 (no parallel-branch leakage)

---

## OPEN QUESTIONS / ASSUMPTIONS

- **Prompt-vs-fixture reconciliation (resolved):** the brief said "mailto:email@brand.emaillove.com #0080c6". The fixture shows the email run is `#0080C6`+underline but its `link_url` is the **campaign URL**, not `mailto:`. Ratified: emit the run's `link_url` as-is (no synthesized mailto). `#0080C6` is real.
- **Dedupe (ratified "Coexist"):** the compliance unsub row is always emitted; c7's own decorative unsub/prefs bar coexists (2 visible unsub links, 1 functional). "ONE unsub row" = one compliance row. No token rewriting.
- **FooterConfig-present branch has no corpus fixture** — validated by unit tests only; production wiring loads it in `import_service`.
- **Ledger scaffolder nuance:** the entry's `symptom_if_broken` is the *scaffolder* (non-converter) path; this fix is converter-only. Closure covers the converter path (the entry's `code_refs` home); the scaffolder decorative-footer edge is not exercised here (noted, not claimed fixed).
- **MJML output path** (`convert_document_mjml`) is out of scope; its footer uses a different engine. Assumption: production converter output for the acceptance uses the component path (matches the corpus harness).
- **`©` year:** `FooterConfig` has no year and time functions are unavailable → no fabricated year in the © line (brands wanting a year use `legal_text`).

## NOTES (open canvas)

- **Why nested-table-in-cell, not the splice path:** `footer_editorial` is a single `<td>`; the seed itself nests a `<table>` in `footer_legal`. Filling the editorial cell with a self-contained `<table>` reuses `_fill_text_slot` + the depth-aware `_find_matching_close` with zero renderer changes — simpler than `stacked_before`/`composite` splicing (which target `<tr>` siblings, not a cell's interior).
- **Threading cost:** 6 signatures + dispatch + VLM path + the import_service load. All get `design_system: DesignSystem | None = None` (default None) so existing callers/tests are byte-unaffected; only `_fills_footer` reads it. This is the plan's main mechanical cost and its main risk surface — run pyright per hop.
- **Supersession of RC-F5:** RC-F5 deliberately kept `_fills_footer` from emitting footer_legal (preserve-verbatim compliance). G8 inverts that: active emission is now the compliance mechanism. `_PRESERVE_UNFILLED_SLOTS` still lists `footer_legal` but the slot is always filled → preservation never triggers for the converter; left in place (surgical, and other seeds may rely on the frozenset).
- **Multi-line default:** reuse `_multiline_to_br` verbatim (one `<br />` per separator). c7 Node B's `\n ` → two `<br />` (a blank line between T&C and "sent to"). If hand-verification of `actual.html` reads poorly, add a footer-local collapse of consecutive separators → one `<br />` (small, contained) rather than changing the shared helper.

## AMENDMENTS

(none — created 2026-07-19)
