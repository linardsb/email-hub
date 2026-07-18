# PR #354 Review — composite-slot infrastructure + own-row CTA (Track G · G4 / 51.1)

**Verdict: ✅ APPROVE** — recorded here as a comment (GitHub blocks a formal self-approval from the PR author).

## Recommendation

Approve and merge. No critical or high-severity issues. `make check-full` is green, the change matches its stated intent, the five documented deviations are intentional and sound, and both the rendered output and the ledger close-out check out. The one **Medium** finding is a dead test assertion (the test still catches its target bug via other assertions) — worth tidying but not merge-blocking. The **Low** items are correctly deferred to 51.2 or are hygiene nits.

## Validation

| Gate | Result |
|---|---|
| `make check-full` | **GREEN (exit 0)** |
| Backend tests | 8414 passed · 115 skipped · 2 xfailed |
| Frontend tests | 780 passed (79 files) |
| Golden conformance | 26 passed |
| lint · mypy · pyright · security · flag-audit · migration-lint | clean |
| Snapshot `data/debug/` | **+24 / −0**, c9 byte-identical |

One pre-existing local test failure — `test_tree_bridge.py::TestRoundtripTreeToHtml::test_tree_compiles_to_valid_html` (missing `cssselect` in the local env) — exists on `origin/main`, is unrelated to this diff, and passes inside the `make` gate.

## Fresh-eyes method

Reviewed against **`origin/main`** — local `main` was stale, so a naive `main...HEAD` diff showed 124 contaminated (already-merged #352/#353) files; the real PR is exactly **14 files**. Two independent cold-context reviewers (correctness; standards/tests) plus a manual pass. Findings were triaged against the five documented deviations — documented = intentional decision, only *undocumented* divergences are flagged as issues.

## Findings by severity

### Medium

1. **Dead assertion in the nested-table regression guard** — `app/design_sync/tests/test_composite_slot.py:116`.
   `body_cell = out.split('data-slot="body"')[1].split("CTA")[0]` is by construction the text *before* the first `"CTA"`, so `assert 'align="center">CTA' not in body_cell` can never fail — vacuous.
   *Not a coverage hole:* the surrounding assertions — `out.index("para2") < out.index("CTA")` (line 113) and `out.endswith('...<tr><td align="center">CTA</td></tr></table>')` (line 118) — both genuinely fail under a naive `find("</tr>")` splice, so the guard still has teeth.
   **Fix:** drop the dead line, or extract the true body-cell extent (body `<td>` → its matching outer `</td>`) and assert the anchor is absent from *that*.

### Low

2. **Depth-≥2 composite emits malformed HTML** — `app/design_sync/component_matcher.py:952-960` (`render_composite`).
   A `composite`-typed child returns a full `<tr>…</tr>`, which the parent embeds inside its own `<td>` → `<td><tr>…</tr></td>` (a `<tr>` with no intervening `<table>`; email clients foster-parent it out of the cell). **Latent only** — 51.1's sole consumer (own-row CTA) is strictly depth-1 with terminal anchor children, which is well-formed. This is a trap for whoever lands 51.2 (general sub-template recursion), already ledgered as `phase-53g-g4-general-sub-template-recursion`.
   **Fix at 51.2:** wrap a recursive child in an inner `<table role="presentation">` before embedding, or have the recursive call return cell *contents* rather than a full row.

3. **Depth-2 test locks in that malformed shape** — `test_composite_slot.py::test_depth2_composite_child_recurses` asserts only `count("<tr>")==2` + `"INNER" in html`; it green-lights the invalid nesting and will need revising when 51.2 fixes the wrap. Add a comment that the shape is knowingly provisional.

4. **Two new `_fills_text_block` branches are untested** — the `anchor_slot=="heading"` splice (body absent, heading present) and the `anchor_slot is None` inline fallback. Every `TestOwnRowCTAComposite` case carries both heading + body, so only the body path runs. Low risk; a content section with buttons but no body/heading text would reach the fallback.

5. **Ledger commit SHAs left `"pending"`** — `.agents/deferred-items.json` ships with `introduced_commit`/`closed_commit` = `"pending"` in the committed PR (HEAD `89eaf6f0`); the implementation report's own close-out note said to fill the real SHA at commit time. Hygiene only — amend or follow-up to stamp `89eaf6f0`.

## Documented deviations — reviewed, all sound (not issues)

- **Blast radius {5,6,7,8,10}, not the plan's {6,7,10}** — verified zero collateral (0 lines removed; `_column_cta_row` untouched); c5/c8 legitimately carry text-block-*family* CTAs. Correct not to contort the code to force a wrong "c5/c8 byte-identical" AC.
- **`cell_style` = `padding:0 24px 24px`** — the body cell's own 24px bottom padding is the above-CTA gap; top=0 avoids doubling it. Confirmed against the snapshots.
- **Tree-bridge SKIPS the composite (returns `None`)** — emitting an undefined `cta_row` slot would fail `validate_tree_against_manifest` → `CompilationError` → poison the entire tree compile and force a legacy fallback for every text-block-with-CTA email. **Verified latent, not a live regression:** the tree path is doubly gated off (`tree_bridge_enabled` defaults `False`; `output_format` is never `"tree"` — the public route schema only accepts `html`/`mjml`). Honestly ledgered `phase-53g-g4-tree-html-slot-row-shape` (known-bug, deferred to 51.2); AC box left unchecked. The severity label is accurate.
- **c5 section_median −0.024** — pre-existing color-extraction miss (`#0066cc` `_safe_color` fallback, not MAAP's palette); own-row just makes an already-miscolored button more prominent. Out of scope.
- **`component_renderer` imports only `render_composite`** — `CompositeSlot` is unreferenced there; importing it would be an unused-import lint error. Correct.

## What's genuinely well done

- Depth-counted `_find_matching_close` reused for the after-slot splice — correctly handles the c8/c10 nested `_per_node_body_html` table (a naive `find("</tr>")` would splice the CTA *inside* the body cell), with a dedicated regression test.
- `anchor_slot` ladder (body → heading → inline fallback) guarantees the CTA is never silently dropped on the live renderer path.
- `test_undefined_slot_breaks_compile` proves *why* the tree-bridge must skip — a high-value test, not a formality.
- The +24/−0 snapshot delta exactly matches the code's claim; anchors are moved, not duplicated; all five files stay tag-balanced; c9 byte-identical.
- Type-safe; conforms to the email-HTML rules (table/tr/td, no div/p/h); no new untrusted interpolation (`align`/`cell_style` hardcoded, anchor children pre-escaped upstream).

---

🤖 Fresh-eyes review via `/piv-review-pr` — two independent cold-context reviewer passes (correctness + standards/tests) plus a manual pass and a full `make check-full` run. Verdict recorded as a comment because GitHub does not allow a formal review state (approve/request-changes) from the PR's own author.
