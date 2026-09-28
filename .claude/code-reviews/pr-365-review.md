# PR #365 Review — G11 residual ingest classes sweep (Track G)

**Verdict: APPROVE** · 2 independent cold reviewers (correctness/standards + logic deep-dive), fresh context.

## Validation

| Gate | Result |
|---|---|
| `make check-full` | GREEN (backend + frontend 780 + golden conformance 26 + flag audit 87 + migration lint); re-run green on push |
| `uv run pyright` (6 changed src files) | 0 errors (2 pre-existing `reportUnusedFunction` warnings at layout_analyzer:1193,1742 — not from this PR) |
| `uv run ruff --no-fix` | clean |
| unit (item 3 / 2 / 1) | 3 / 22 / 71 GREEN, each RED-proven first |
| `make converter-data-regression` (A2 ladder) | 73 passed, section counts UNCHANGED, c10 xfail preserved |
| `make snapshot-test` | 34 passed, moved baselines diff-audited to intended change only |

## Issues by severity

**Critical / High / Medium: none.**

**Low / informational (non-blocking, corpus-clean, no worse than baseline):**

- **LOW-1** — `layout_analyzer.py` `is_small_decoration` gates on `image_ref/fill_color/effects_summary is None` but not `stroke_color`. A ≤64px child in an unstyled-but-bordered frame would child-export and re-apply the frame border at child size. Did not manifest (c8's `2833:2262` has `border:0`); a stroke isn't baked into a child PNG anyway, so re-adding it at child size is defensible for an icon. Speculative.
- **LOW-2** — item-2 shrink can cross the `_SPEC_ICON_MAX_WIDTH = 30` fold threshold (`component_matcher.py:1114`): an image whose frame was >30 but child ≤30 (c7 60→30, c9 34→24) becomes spec-icon-eligible, which *could* alter `_group_spec_pairs` folding in a future fixture. Did NOT on this corpus (snapshot green; c7 `<tr>` count unchanged 117=117, no new spec-mini-tables). Latent coupling — G12 re-audits all fixtures.
- **LOW-3** — a single-member band `[content, divider]` captures a `BandRule` but is skipped by `len(members) < 2`, dropping the rule. Acceptable: no member pair to draw a rule between; no worse than baseline.

None warrant a code change or block merge.

## What's good

- **Types & standards clean**: all new/changed signatures fully annotated; widened `… | ColumnDivider` unions + TypeGuards type-check; emitted rule rows (`_column_divider_row`, `_band_internal_rule_row`) are `<table>/<tr>/<td>`-only, no `<p>`/`<h*>`/layout-div, hex-gated + sub-pixel weight floored to 1px (never a `0px solid` invisible rule) — matches the case-9 divider + spec-mini-table empty-cell precedent.
- **Serialization symmetric**: `DocumentColumn.dividers` handled in all four methods; empty-list round-trips; proven end-to-end by `TestColumnChildDivider` (from_column_group→to_json→from_json→to_column_group).
- **`group_by_wrapper` restructure is a faithful rewrite**: `members` identical to the prior comprehension for both `absorb_spacers` branches; `absorbed=` logging + member count unchanged; rule capture is purely additive and correctly gated (DIVIDER + truthy stroke + non-empty members → leading divider dropped).
- **Band-rule index math provably correct**: `after_member_index=len(members)-1` aligns with the `enumerate(rendered_items)` injection index because production builds sections from `item.sections` (absorbed dividers already removed) and `group_matches` filtering is order-preserving → a rule can be *dropped* by the equal-length guard but never *misplaced*. c10 rendering both rules empirically exercises the `matches[i]↔members[i]` invariant.
- **Deviations sound & non-circular**: the c8-non-render evidence is that its baseline was NOT regenerated, so passing snapshot proves the category does not fire on c8, while `TestColumnChildDivider` proves it renders when a section reaches column render. Item-2 correctness rests on geometry (a 28/64px child baked into a wide frame `<img>` is a ~10× upscale) + the c8 A3 lift, not the (circular) regenerated c7/c9/c10 baselines. Both correctly ledgered.

## Recommendation

**APPROVE.** No correctness, type-safety, security, or standards issues survive review; the three LOW notes are latent couplings that are corpus-clean and no worse than baseline; the four documented deviations are legitimate and correctly ledgered. Ready for a human to merge.

_(Posted as a comment: PR author == reviewer gh identity, so a formal GitHub `--approve` is not available; this is the agentic-gate verdict for the human approver.)_
