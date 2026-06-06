# Decision Note — B5 alt derivation vs the G3-neg conformance gate

> Scope: a **decision note**, not a full plan. Closes the open question in deferred-items
> `phase-53-b5-decorative-empty-alt-vs-g3neg`. Companion to `.agents/plans/53-converter-engine-fix.md` §Track B (B5).
> Every claim below is empirically traced on branch `tech-debt/phase-52-converter-foundation` (2026-06-06), not inferred.

## The question

B5 (alt derivation) must stop the Figma **layer-name leak** into `alt` (Mode E-alt:
`component_matcher.py:795,1455` emit `alt="{html.escape(img.node_name)}"`). The plan's B5 line prescribes
"real alt … / `alt=""` for decorative." But the golden-conformance gate **G3-neg**
(`test_golden_conformance.py:71-76`, `should_match=False`) forbids `alt` that is empty *or* a single generic
token (`image|photo|picture|img|mj-image|mj-text|frame|banner`) — empty is the first regex alternative. Does
`alt=""`-for-decorative re-trip G3-neg, and if so, how is it reconciled?

## Decisive finding (settles it)

A one-off trace running each image seed through `import → convert_document` (the exact G3-neg harness):

| Seed | Reaches `_build_column_fill_html` (B5's path)? | Output `alt` | G3-neg |
|---|---|---|---|
| image-grid | **yes** | `Grid image 1/2` | pass |
| article-card / product-card | **yes** | `Article image` | pass |
| hero-block / column-layout-2 / reverse-column | **yes** | (no surviving `<img>`) | pass |
| full-width-image | no (slot-fill path) | `Full width image`, `Company Logo` | pass |

Two facts fall out, both load-bearing:

1. **B5's column-builder path *is* on the G3-neg gate.** (The earlier hypothesis that the gate only touches the
   slot-fill `_fill_image_slot` path is refuted by the trace.) So an `alt=""` emitted there *would* fail
   `make golden-conformance` / `make check` the moment a gated seed image takes that branch. The deferred entry's
   worry is real.
2. **The leak does not occur on the seed/conformance path.** There `img.node_name` is sourced from the seed's own
   descriptive `alt` (`"Grid image 1"`, `"Article image"` — multi-word ⟹ passes G3-neg). The leak is the *Figma-fixture*
   provenance of the **same field**: `node_name = node.name` = the raw layer name (`layout_analyzer.py:438,1002,…`),
   which the data/debug snapshot corpus exercises — and that corpus enforces **no** alt check
   (`test_converter_data_regression.py` has none). So the layer-name leak is currently *unmeasured*, and `alt=""`
   would be *measured* and *red*.

Third fact closing the "decorative" half: `is_background` images render as MJML **`background-url` / CSS background,
not `<img>`** (`hero.mjml.j2:2`, gated `:16 {% if not img.is_background %}`) → a genuinely decorative image produces
**no `<img>`, no `alt` surface**. On the column path it would render as `<img>`, but every column-path image in the
6 fixtures is **content** (LEGO/maap product + hero photos), for which `alt=""` is a11y-*wrong* regardless of the gate.

## Decision

**Conservative reconciliation. B5 = leak-fix only; never emit `alt=""` on the column path; do not touch G3-neg.**

> **Execution correction (2026-06-06, commit `65a8b703`).** The leak is **broader than the two column-path sites this
> note and the deferred entry originally cited** — it spans **8 image-alt emission sites**, and the slot-fill path is
> *not* exonerated after all: the matcher *feeds* raw `node_name` into it. Running the real converter on the fixtures
> showed `mj-image, (mjml:mj-image), (type: logo)` surviving in cases 6/8/9/10 after the column-path fix alone. Full
> site list (all routed through the new `_derive_image_alt` / `_is_descriptive_alt` helpers): the 2 column f-strings
> (`_build_column_fill_html`, `_build_column_fills`); the 4 `SlotFill("image_alt", …)` feeders
> (`_fills_full_width_image`, `_fills_article_card`, `_fills_image_block`, `_fills_event_card`); the 1
> `SlotFill("logo_alt", …)` (`_fills_logo_header`); and the social-icon fallback (`_fills_social`). A separate,
> pre-existing defect — linked icons with literal `alt=""` in `col-icon.html` (`<a><img alt="">`, unlabeled link) — was
> fixed in the same commit to `alt="Feature icon"`. Result: 0 empty/generic/leak alts across all 6 fixtures;
> golden-conformance green. The conservative **decision** below stands unchanged; only its *scope* was wider.

1. **Stop the leak (the actual B5 bug), unconditionally** across the 8 sites above (originally cited as just
   `component_matcher.py:795` and `:1455`): do not route a raw layer-name into `alt`.
2. **Derive `alt` (column path), never empty, never a lone generic token:**
   - **Meaningful `node_name`** — multi-word, not a node-id pattern (no `:`, not all-digits/separators), not a single
     generic token → use it (`html.escape`d). This is already what the seed path emits and what passes G3-neg.
   - **Otherwise** → a **descriptive multi-word placeholder** (e.g. role-derived, mirroring B1's seed precedent
     `"Article image"` / `"Full width image"` — both multi-word ⟹ G3-neg-clean). Never a lone generic word, never `""`.
3. **Do NOT emit `alt=""`-for-decorative in B5, and do NOT amend G3-neg.** The plan's `alt=""` prescription has **no
   live, safe case** on the column path today (decorative → no `<img>`; column images → content). The user-authored
   ledger note "do not loosen it" stands; the trace shows the gate is correctly covering the real surface.

### Why not the gate-amendment alternative (the `closes_when` "option 2")

A `role="presentation"` exemption would let the code-under-test opt *itself* out of the gate via an attribute it
emits — inverting the gate's purpose (G1 checks *for* `role="presentation"` presence; an empty-alt *exemption* keyed on
it is the hole). It also buys nothing now: there is no decorative `<img>` on this path to exempt. Rejected for B5.

### What is genuinely deferred (not B5)

True per-image **semantic** alt and a real **decorative** signal are an **ingest-level (RC-E)** concern, not a renderer
patch: Figma carries no alt/caption, and `node.name` is an unreliable proxy. If RC-E later lands a `role="presentation"`/
decorative flag *upstream*, the renderer can then emit `alt="" role="presentation"` and G3-neg can be made role-aware in
the **same** change (gate-amendment justified only when a real decorative `<img>` exists to gate). Until then: leak-fix +
descriptive placeholder is the whole of B5.

## Ledger reconciliation (`phase-53-b5-decorative-empty-alt-vs-g3neg`)

The entry's `closes_when` ("B5 lands real *derived* … alt") over-scopes B5. Re-scoped to two tiers (edit applied to
`.agents/deferred-items.json` alongside this note):
- **Tier 1 — leak closed by B5 (this decision):** column path no longer emits raw `node_name`; emits a meaningful name
  or a descriptive non-generic placeholder; golden-conformance stays green; no `alt=""` on the column path.
- **Tier 2 — semantic per-image derivation + true decorative `alt=""`:** deferred to RC-E (ingest signal). Only then is
  a role-aware G3-neg amendment on the table.

## Verification (for the B5 executor)

- [ ] `make golden-conformance` green after the edit (column-builder seeds keep descriptive, non-empty, non-generic alt).
- [ ] No `alt=""` and no lone-generic-token `alt` emitted by `_build_column_fill_html` / `_build_column_fills`
      (grep the converter output for the 6 data/debug fixtures + the conformance seeds).
- [ ] Layer-name leak gone on the Figma-fixture corpus (data/debug snapshot output no longer carries `node.name` as alt);
      regen + `snapshot_diff_audit` manual intended-vs-structural review per the Track-B playbook.
- [ ] `make types` clean. Do **not** run repo-wide `ruff --fix` / `make check` (parallel uncommitted work) — scope to
      changed files.
