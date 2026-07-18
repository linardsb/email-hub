# Implementation Report — Composite-slot infrastructure (51.1) + own-row CTA (Track G · G4 / M8)

**Plan**: `.agents/plans/53-g4-composite-slot-infrastructure.md`
**Branch**: `feature/53-g4-composite-slot-infrastructure` (off `origin/main` @ `9d66eae5`)
**Status**: COMPLETE — `make check-full` GREEN. **Two per-case A3 trades await Linards's ratification before merge** (c7 full_image −0.009, c5 section_median −0.024; see Deviations).

## Summary
Built the render-time-only 51.1 composite-slot seam — a `composite` variant on `SlotFill` + a `CompositeSlot` frozen dataclass + a depth-≤3 `render_composite` sub-renderer + a `_splice_rows_after_slot` injection primitive — and proved it with its first consumer: own-row CTA emission in `_fills_text_block`. The text-block CTA now renders centered on its own `<tr>` below the body (matching the design) instead of folded into the body `<td>` where it hugged the left padding. Infrastructure lands byte-identical with zero consumers (Checkpoint A); wiring the consumer moves only the CTA-carrying baselines (Checkpoint B).

## Tasks completed
- **Types + sub-renderer** → `app/design_sync/component_matcher.py` (UPDATE): `SlotFill.slot_type` gains `"composite"` + trailing `composite: CompositeSlot | None = None`; `CompositeSlot` dataclass; module-level `render_composite` (depth-≤3 loop, inherent recursion, `child.composite is None` degrade-to-value).
- **Renderer plumbing** → `app/design_sync/component_renderer.py` (UPDATE): `_splice_rows_after_slot` (mirrors `_splice_rows_before_slot`; anchors on the row-open + depth-counted `_find_matching_close` so a nested-table body — c8/c10 — isn't truncated at its inner `</tr>`); `_fill_composite_slot`; `composite` dispatch branch (before the `else → _fill_text_slot`); import of `render_composite`.
- **Tree plumbing** → `app/design_sync/tree_bridge.py` (UPDATE): `composite` branch in `_fill_to_slot_value` that **skips** the fill (returns `None`) — see Deviation 3.
- **Consumer** → `component_matcher.py:_fills_text_block` (UPDATE): CTA fold replaced by a `composite` `cta_row` fill (`after_slot` body/heading ladder, `cell_style="padding:0 24px 24px"`, `child_separator="\n"`; inline-fallback kept for the no-text-anchor case not hit by the corpus).
- **Baselines** → `data/debug/{5,6,7,8,10}/expected.html` (regenerated, NOT hand-patched; c9 untouched).
- **Close-out** → `.agents/deferred-items.json` (+3 entries), `.agents/plans/deferred/TRIAGE-2026-06-12.md` (51.1 PROMOTED), `TODO.md` Track G (G4 Result + intro status + G5 floor patch — TODO.md is gitignored, so local-only). Frozen snapshot `53-g-production-readiness-prompt-sequence.md` **untouched**.

## Tests added
- **`app/design_sync/tests/test_composite_slot.py`** (NEW, 8 cases): `render_composite` depth-1 concat+center-wrap, align/style, depth-2 recursion, mislabeled-composite degrade-to-value, depth-4 cap truncation; `_splice_rows_after_slot` splice-after / no-op-when-absent / **nested-table regression guard** (the c10 `_per_node_body_html` shape a naive `find("</tr>")` would break).
- **`test_cta_fidelity.py::TestOwnRowCTAComposite`** (4 cases): builder emits `composite` `cta_row` (after_slot=body, anchor in children); body fill no longer carries `<a>`; renderer places the anchor in an `align="center"` row after the body row; multi-button → one centered row.
- **`test_tree_bridge.py::TestCompositeSlotConversion`** (3 cases): composite skipped at bridge (`cta_row` absent from result, no `unknown_slot_type`); body converts to a clean `TextSlot`; `test_undefined_slot_breaks_compile` proves *why* the bridge must skip (an undefined slot fails manifest validation → `CompilationError`).
- **`test_component_matcher.py::TestButtonInTextBlock`** (2 cases, UPDATED): the pre-existing B8/F11 guards now assert the anchor lives in the `cta_row` composite children (F11 white-fallback + B8 multi-button/outlined-color intent preserved), not in `body.value`.

## Validation results
- **`make check-full`**: **GREEN (exit 0)** — lint, mypy/pyright (0 errors), full test suite (8414+ passed), security (bandit/`-S`), golden conformance (26), flag audit (87), migration lint. Ruff `--no-fix` + `ruff format --check` clean on all touched files.
- **Checkpoint A** (infra, no consumer): snapshot regression **34 passed / 10 skipped / 1 xfailed**, `git diff data/debug/` empty → corpus byte-identical.
- **Checkpoint B** (consumer wired): `git diff data/debug/` = **24 insertions / 0 deletions**, only composite CTA rows; c9 byte-identical; snapshot gate green with regenerated baselines. **Method note (not hand-patching the content):** baselines were regenerated via `scripts/snapshot-capture.py --overwrite`, then I applied a trailing-whitespace strip (`sed -i '' 's/[[:space:]]*$//'`) to the 5 regenerated files. The raw converter output carries trailing whitespace (notably c8's heading lines) that the repo's **pre-commit hook strips anyway** and the **snapshot gate normalizes** — this is the same c8 ws mechanism recorded in the F7/F11 ledger entries. Stripping it here matches the eventual committed bytes and keeps the reviewable diff to only the composite CTA rows; the CTA-row content itself is 100% converter-generated, not hand-authored.
- **A3 fidelity** (gmail_web, full_image · section_min · section_median), baseline → after:

| case | full_image | section_min | section_median | verdict |
|---|---|---|---|---|
| 5 maap | 0.838 → 0.838 | 0.400 → 0.415 | 0.838 → **0.814** | median −0.024 (pre-existing color miss — see D5) |
| 6 starbucks | 0.816 → **0.820** | 0.477 → 0.477 | 0.699 → 0.698 | up |
| 7 LEGO | 0.803 → **0.794** | 0.389 → 0.389 | 0.790 → 0.792 | full −0.009 trade (median +0.002; own-row design-correct) |
| 8 Ferrari | 0.784 → **0.785** | 0.677 → 0.676 | 0.784 → **0.786** | up |
| 9 slate | 0.680 → 0.680 | flat | flat | untouched |
| 10 mammut | 0.748 → **0.754** | 0.067 → 0.067 | 0.852 → **0.857** | up |

Ladder 13/9/8/10/8/12 held (mammut xfail only).

## Deviations from the plan
1. **Blast radius is {5,6,7,8,10}, not the plan's {6,7,10}.** The plan's Task-0.5 coverage map grepped only the `textblock-body` class (and a non-greedy `.*?</td>` that stops at nested-body inner cells), but `_fills_text_block` serves ~10 slugs — so c5 and c8 also carry text-block-*family* CTAs that legitimately move. **Verified zero collateral**: 0 lines removed anywhere, `_column_cta_row` (c5's 8 pills, c8's column CTAs) untouched. The plan AC "c5/c8/c9 byte-identical" is corrected to **"c9 byte-identical; c5/c6/c7/c8/c10 move (CTA rows only)"** — I did NOT contort the code to force the wrong AC (that would mean arbitrarily scoping to the `text-block` slug).
2. **`cell_style` tuned to `padding:0 24px 24px` (from the plan's starting `8px 24px 24px`).** The body cell already contributes its 24px bottom padding as the above-CTA gap (matching the design), so the extra 8px top was doubling it. Confirmed against the design composite. One targeted pass, re-scored; the two values are within ±0.004 — `0 24px 24px` is marginally better net + cleaner rationale.
3. **Tree-path AC NOT met — `tree_bridge` SKIPS the composite (returns `None`), it does NOT emit an `HtmlSlot`.** The plan's Task 5 said to emit `HtmlSlot(render_composite(...))`, but `validate_tree_against_manifest` **rejects an undefined slot** (`cta_row` not defined for `text-block`) with a `CompilationError` — which would poison the entire tree compile and force a legacy-renderer fallback for *every* text-block-with-CTA email. Skipping keeps the tree compile valid (kills the `unknown_slot_type` warning too) but the CTA is absent in the tree path (pre-G4 its label survived as tag-stripped body text). The enabling mechanism (`data-slot-composite` slot) is explicitly 51.2 territory. **User chose "defer honestly."** Ledgered as `phase-53g-g4-tree-html-slot-row-shape` (deferred, known-bug); AC box left unchecked.
4. **`component_renderer` imports only `render_composite`, not `CompositeSlot`.** The plan said add both, but `CompositeSlot` is never referenced there (would be an unused-import lint error).
5. **c5 section_median −0.024 is out of scope.** c5's CTA renders `background-color:#0066cc` — the `_safe_color` fallback, i.e. no design color was extracted (MAAP's palette is grey/lilac/green, not blue). Own-row just makes an already-miscolored button more prominent. This is a pre-existing color-extraction miss (cf. `phase-53-b8-text-block-solid-cta-text-color`), not a placement problem G4 should fix.

## Issues encountered / awaiting ratification
- **c7 full_image −0.009 and c5 median −0.024 are ratifiable trades (mirror the G2/G3 pattern).** The design composite **confirms** own-row centered-with-gap is correct for c7; the full_image dip is a structural floor (own-row adds the body's unavoidable 24px gap that the coarse pixel-diff penalizes on downstream vertical alignment) while c7's *section* median rises. I did not rescue the "c7 flat-or-up" AC by cherry-picking section_median — presenting the honest per-metric trade for your ratification before merge.
- Pre-existing uncommitted `skill-versions.yaml` stamps were `git restore`d (per the Track-G invariant; not my changes). `TODO.md` edits are local-only (file is gitignored).
- **Stale-by-design tree artifacts:** the committed `data/debug/{5,6,10}/actual-tree-with-fixes.html` still show the pre-G4 tree output (CTA label folded in body). They are NOT gate-enforced (the snapshot test compares only `expected.html`) and were left unregenerated on purpose — regenerating them would just make the deferred tree-path drop concrete. Tracked by `phase-53g-g4-tree-html-slot-row-shape`; not an oversight.
- **At commit time (`piv-commit`):** fill the real SHA into the three `"pending"` ledger fields (`introduced_commit` ×3, `closed_commit` on the infra entry) and the TODO.md/TRIAGE references.
- Ready for `piv-commit` → `piv-create-pr` once the c7/c5 trade is ratified. Suggested: repoint the branch upstream off `origin/main` before pushing (plan OQ4).
