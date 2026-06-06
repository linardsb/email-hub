# Converter Structural-Fidelity Audit (audit_3)

> Scope: **STRUCTURE / LAYOUT** fidelity of the design_sync converter (Figma → email HTML).
> Date: 2026-06-01 · Branch: `tech-debt/phase-52-converter-foundation`
> Companion docs: `HANDOFF.md`, `.agents/plans/52-converter-foundation.md` (Phase 53), `docs/fidelity-gap-audit-findings.md`.

---

## 1. Title + TL;DR

**The engine cannot render the design properly because it groups the design into the wrong number of sections *before any HTML seed is chosen*, and that error is bidirectional.** Live, current-code section counts vs. design target:

| fixture | converter | target | direction |
|---------|-----------|--------|-----------|
| Starbucks (6) | **5** | 9 | under |
| maap (5) | **11** | 13 | under (with internal over) |
| mammut (10) | **14** | 18 | under |
| LEGO (7) | **17** | 8 | **over (+9)** |
| slate (9) | **10** | 8 | over |
| performance (8) | 11 | 10 | on-target (within tolerance 1) |

This is **not** a property-plumbing problem. Phase 52 already fixed the serializer bridge that was nulling text color, dropping `text_align`, CTA `url`/`border_radius`, and the Phase-50 section layer (RC-A/RC-B, commits `d6d1854d`/`d6d1854d`; design_sync = 2077 tests green). Colors, fonts, alignment, and CTA radius now reach the HTML. This audit is about the layer above that: **how Figma nodes get partitioned into sections (segmentation), which seed each section matches (seed-match), and what the fixed-seed renderer can express (RC-C).**

On the **current fixed-seed engine**, the headline defect — wrong section count — originates **upstream of the renderer**, in `layout_analyzer.analyze_layout`, before `component_matcher.match_all` (which is a strict 1:1 map and cannot change the count). The single mechanism responsible for **both** directions is the wrapper-unwrap pass (`_get_section_candidates` + `_expand_container_wrappers`) behaving asymmetrically: it leaves single-child wrappers merged (under-count) and explodes multi-child card wrappers (over-count). A one-way "splitter" — the only structural fix prior plans proposed — would make LEGO/slate worse.

> **Important cross-fork qualifier (reconciled with `docs/converter_audit_2.md`):** "upstream of the renderer" is true *for the fixed-seed engine only*. The deleted recursive-renderer fork (b) does **not** call `analyze_layout` at all — it walks the Figma `DesignNode` tree directly — so the broken segmentation stage does not exist on that path. audit_2's **live spike** of that renderer produced the **correct 8 LEGO bands**. See §6 Part B; this is corrected from an earlier draft of this audit that reasoned (without running fork-b) that it could not fix the count.

---

## 2. Methodology

**Three-way ground truth.** For each fixture we compared:

1. `email-templates/training_HTML/for_converter_engine/<dir>/manual_component_build.html` — the **hand-authored correct email assembled from the same component library**. This is the primary "what proper output looks like" reference. (For LEGO the converter baseline is `hub_converter_phase49_baseline.html`; its `manual_component_build.html` is ground truth.)
2. `data/debug/<case>/expected.html` — the **converter's actual current output** (verified: `actual.html == expected.html`; reproduced live via `run_case_conversion`).
3. `<dir>/visual_design.png` — the rendered design image, read directly.

**Why this sidesteps the blockers.** The fidelity pixel-metric (RC-F) is blind: it is color-blind, blurred, off-by-default, never runs in production, and is dimensionally invalid — and it is additionally inert because 22 node-id image URLs have **no on-disk asset map** (the 52.1-finish gate). So we do **not** report any ΔE / SSIM / fidelity-percentage numbers. Instead we use **HTML topology** (section markers, seed slugs, slot fills) plus the per-stage **count ladder** produced by re-running the live pipeline. Broken images do not affect section structure, so the structural conclusions hold regardless of the asset gate.

**Stage-localization framing.** Every defect is attributed to exactly one stage with `file:line` evidence:

```
ingest  →  segmentation  →  seed-match  →  render  →  assemble
```

- **ingest** = `figma/service.py` + `tree_normalizer.py` (Figma JSON → recursive `DesignNode` tree).
- **segmentation** = `layout_analyzer.analyze_layout` (recursive tree → flat `EmailSection[]`; **this sets the section count**).
- **seed-match** = `component_matcher.match_all` / `match_section` (each `EmailSection` → one seed slug; strict 1:1).
- **render** = `component_renderer.render_section` (copy seed HTML verbatim + inject content + closed override set = RC-C).
- **assemble** = `converter_service._assemble_phase` (flat vertical string-join into the shell).

**Honest caveat on ground truth.** Case 8 (performance_reimagined) has **no** `manual_component_build.html` — only `hub_converter_build.html` + PNG — so its ground truth is two-way (PNG + manifest target), not three-way. Its by-count result (11 vs 10) is within manifest tolerance; its defects are within-section/render quality, not a count error. **Case 9 (slate)**'s design PNG was not directly band-counted in this pass, so its target (8) and its "over" direction (10 vs 8) rest on the manifest authors' judgment rather than our own band count — treat slate's direction as **medium-confidence**.

---

## 3. Empirical per-fixture findings

### 3a. The count ladder (the headline artifact — no prior audit produced this)

Produced by re-running the live pipeline against each `data/debug/<case>/structure.json`. Columns: target (manifest) → `len(_get_section_candidates)` (pre-unwrap) → `len(analyze_layout().sections)` (post-segmentation) → rendered `sections_count`. Naming convention was **MJML for all six** (`_detect_naming_convention`), so the wrapper-unwrap gate at `layout_analyzer.py:561` is **open for every fixture**.

| fixture | target | candidates | after analyze | rendered | container-wrappers (fill+≥2 children) | net direction |
|---------|--------|-----------|---------------|----------|----------------------------------------|---------------|
| Starbucks (6) | 9 | 5 | 5 | **5** | 0 | strong under |
| maap (5) | 13 | 9 | 11 | **11** | 1 | net under, internal over |
| mammut (10) | 18 | 12 | 17 | **14** | 2 | under |
| LEGO (7) | 8 | 8 | **21** | **17** | 3 | strong over (+9) |
| slate (9) | 8 | 8 | 11 | **10** | 1 | over |
| performance (8) | 10 | 10 | 11 | 11 | 1 | on-target (tol 1) |

Two stages move the count: **`analyze_layout` (wrapper-unwrap)** raises it (8→21 for LEGO; 12→17 for mammut), and **sibling-collapse in `_match_phase`** lowers it but **incompletely** (LEGO 21→17, not →8; mammut 17→14). Per-section element bags (texts/images/buttons) confirm the mechanism — e.g. maap section_1 = `3t/0i/1b` (the merged hero), LEGO has six `*t/*i/1b` card sections where the manual has them inside one band.

### 3b. Per-fixture defect summary

| fixture | conv. | GT | direction | top defects (stage) |
|---------|-------|----|-----------|--------------------|
| maap (5) | 11 | 13 | mixed | hero 4-elem band → 1 text-block (**segmentation**); single "Stores" band over-split to label + col-3 + col-4 (**segmentation/seed-match**); navbar matched to horizontal seed carrying `class="hide"` → invisible on mobile (**seed-match/render**); `Section Heading` + footer boilerplate leaks (**render**) |
| Starbucks (6) | 5 | 9 | under | 9 design bands (logo/hero/heading/body/CTA/2-col countdown/CTA/4-col nav/social/footer) collapse to 5; each single-child mj-wrapper holds multiple blocks flattened to one text-block (**segmentation + ingest**) |
| LEGO (7) | 17 | 8 | over (+9) | three lime `#AFCA01`/`#F4F4F4` card wrappers unwrap each repeated card into its own section (8→21) (**segmentation**); sibling-collapse fires (repeat_count 4, 2) but legacy path re-flattens → stays 17, not 8 (**seed-match**); all-`text-block`/`full-width-image` alternation = each card's image split from its text (**segmentation**) |
| performance (8) | 11 | 10 | on-target | by-count fine; within-section render quality only (no count defect) |
| slate (9) | 10 | 8 | over | dual-hero + image-grid wrapper children promoted to separate sections (**segmentation**); `col-icon` sections render 0/4 slots filled — content dropped (**render**, log: `low_slot_fill_rate 0/4`) |
| mammut (10) | 14 | 18 | under | multi-hero / editorial / product-grid bands flattened; `article-card` fills 2/5 slots — 3 design elements dropped (**render**, log: `low_slot_fill_rate 2/5`) |

---

## 4. Stage-localized root-cause map (the heart)

Grouped by stage. Every code claim is `file:line` against **current code** on this branch. Adversarial-verification verdicts are marked; **refuted claims are flagged so they are NOT re-chased.**

### INGEST — `figma/service.py`, `tree_normalizer.py`
**Not the structural-loss point.** `_parse_node` (`figma/service.py:1525-1590`) preserves the full recursive tree with geometry; `tree_normalizer` keeps it recursive. This is consistent with Phase 52 being green — the bits arrive. The ingest-stage loss that *does* matter is the **never-parsed / never-emitted** class (effects, gradients, opacity composited vs hard `#FFFFFF` at `figma/service.py:265-291`, column width ratios), which is RC-E and is a Phase-53 render concern, not a count concern. **(Confirmed; not a count cause.)**

### SEGMENTATION — `figma/layout_analyzer.py` (owns the section count)

| # | mechanism | file:line | severity | fixtures | verdict |
|---|-----------|-----------|----------|----------|---------|
| S1 | **Single-depth candidate pick.** `_get_section_candidates` takes depth-1 frame children; descends one level only if exactly one top frame has ≥2 frame children. The count is whatever node depth the export exposes. | `layout_analyzer.py:520-537` | structural | all | **Confirmed** |
| S2 | **Under-count via single-section-child wrappers.** `_is_container_wrapper` requires fill **AND ≥2 section children** (`:579-584`). Starbucks/maap wrappers each have **exactly 1** section child holding multiple visual blocks (verified: case 6 all 5 candidates `children=1`, `is_wrap=False`). They do **not** unwrap, so heading+body+CTA collapse to one section. | `layout_analyzer.py:579-584`, `:587-598` | structural | 6, 5, 10 | **Confirmed** |
| S3 | **Over-count via multi-child card wrappers.** When a wrapper *does* have ≥2 section children (LEGO's `#AFCA01` wrapper has **8**, verified), `_expand_container_wrappers` promotes **each child to its own EmailSection** — exploding repeated cards (case 7: 8 candidates → **21** sections). | `layout_analyzer.py:540-576` | structural | 7, 9, 10 | **Confirmed** |
| S4 | **Loose `_is_section_child` fallback** promotes any frame-with-children to a section child, amplifying S3 when scaffolding frames qualify. | `layout_analyzer.py:587-598` | structural | 7, 9 | **Confirmed (contributory to S3)** |
| S5 | **Flat-text / flat-image ingest** — `_walk_for_texts` / `_walk_for_images` flatten all descendant text/image nodes of a section into flat lists with no per-element x/y; `TextBlock` carries no geometry. Once S2 under-merges, the matcher sees one blob and the merge is **irreversible**. | `layout_analyzer.py:1073-1147`, `:67-128` | structural | 5, 6, 10 | **Confirmed** |
| S6 | **Column ratios bucketed to a 4-value enum** (`_layout_from_count`); `ColumnGroup.width` exists but is dropped at the bridge, so asymmetric splits (70/30) cannot be reconstructed. | `layout_analyzer.py:926-965`; `email_design_document.py:967-968` | high | 5 | **Confirmed (feeds RC-C)** |

> **REFUTED — do NOT re-chase:** the prior digest's strand *"descriptive/generic naming → identity wrapper-unwrap pass → under-segmentation (Starbucks/Mammut shape)"* is **false for these fixtures.** All six are MJML-named (`data-component-name="mj-wrapper"/"mj-section"` in every `expected.html`; `_detect_naming_convention` returns MJML for all six), so the `naming != MJML` gate at `:561` is **open everywhere.** The under-count is **not** caused by naming routing or the gate being closed — it is caused by **S2 (the `≥2 section children` requirement leaving single-child wrappers merged)** plus **S5 (flat ingest).** Any fix targeting the naming detector or the MJML gate is misdirected.

### SEED-MATCH — `component_matcher.py` (strict 1:1; cannot change count)

| # | mechanism | file:line | severity | fixtures | verdict |
|---|-----------|-----------|----------|----------|---------|
| M0 | `match_all` is a **pure 1:1 list comprehension** — one `ComponentMatch` per input section, no merge/split. The count is frozen upstream. | `component_matcher.py:96-113` | (structural fact) | all | **Confirmed** |
| M1 | **Sibling-collapse computed then discarded.** `detect_repeating_groups` correctly merges repeated cards (LEGO logs `repeat_count=4`, `=2`), but the legacy render path **re-flattens** the group before `match_all`, so the merge does **not** reduce rendered count (LEGO stays 17, not 8). | `converter_service.py:611-633`; `sibling_detector.py:62` | high | 7, 9, 10 | **Confirmed** |
| M2 | **No-good-seed floor coerces to text-block.** `_score_candidates` emits `text-block` only when `has_texts AND NOT has_images`; there is no "no match" escape — unmatched bands silently become text-block, hiding structural mismatch. | `component_matcher.py:279-364`, `:350-351` | high | all | **Confirmed** |
| M3 | **Phantom slug bug.** `_score_extended_candidates` can emit `faq-accordion` (`:474`), which **does not exist** in `component_manifest.yaml` (only `faq-item`, `faq-list`). Renderer then falls to `_fallback_render` → generic text-block. | `component_matcher.py:474`; manifest | medium | latent | **Confirmed (genuine bug)** |
| M4 | **Equal-width column seeds.** `_match_column_layout` keys only off the `ColumnLayout` enum → `column-layout-2/3/4` with baked 50/50, thirds, quarters. Asymmetric splits cannot be expressed. | `component_matcher.py:183-190` | high | 5 | **Confirmed (feeds RC-C)** |

### RENDER — `component_renderer.py` (RC-C, the fixed-seed ceiling)

| # | mechanism | file:line | severity | fixtures | verdict |
|---|-----------|-----------|----------|----------|---------|
| R1 | **Topology is always a shipped seed tree.** `render_section` copies `seed['html_source']` verbatim and string-rewrites content + a closed override set. Cannot synthesize a tag-tree no seed provides (no z-order, overlap, free 2D geometry). | `component_renderer.py:373-382`, `:397`, `:699-781` | structural | all | **Confirmed (hard cap)** |
| R2 | **No per-column-width override target.** Even with perfect upstream ratios, the renderer emits the seed's baked equal splits. **Soft cap** — parameterizable without abandoning fixed-seed. | `component_renderer.py:699-781`, `:973-978` | high | 5 | **Confirmed (soft cap)** |
| R3 | **Closed typography vocabulary.** Only `_HEADING_SLOTS`/`_BODY_SLOTS` + 13 named classes receive design typography; out-of-vocab slots (quote, price, stat_*, faq_*, etc.) silently keep seed defaults. **Soft cap.** | `component_renderer.py:81-103`, `:788-912` | high | testimonial/pricing/FAQ/stats | **Confirmed (soft cap)** |
| R4 | **Seed-default leakage.** Unmatched slots keep the seed default: maap leaks `Section Heading` (`expected.html:249`) and fabricated footer `123 Business Street…` + `{{unsubscribeUrl}}`/`{{preferencesUrl}}` (`:442-449`). Confirmed live via `placeholder_in_output` warning. | `component_renderer.py:601-634` | medium | 5 (and others) | **Confirmed** |
| R5 | **Dropped slot fills.** Fills with no matching `data-slot` are silently dropped (slate `col-icon` 0/4; mammut `article-card` 2/5 — confirmed live via `low_slot_fill_rate`). | `component_renderer.py:601-634`, `:345-362` | medium | 9, 10 | **Confirmed** |
| R6 | **No compose/wrapper primitive.** The LEGO manual nests seeds inside a rounded white card-shell on a colored band; the renderer can only inject into one flat seed. The "COMPOSE" half of select-vs-compose. | `component_renderer.py:384`; `Lego/manual_component_build.html:292,1192` | high | 7 | **Confirmed (RC-C latent)** |
| R7 | **Invalid column nesting.** `_column_text_row` serializes column text as a raw `<tr><td>…</td></tr>` fragment injected into the `col_N` `<td>` with no wrapping inner `<table>` → invalid nesting (maap `expected.html:142-147`). | `component_matcher.py:693-759`; `component_renderer.py:538-599` | medium | 5 | **Confirmed (HTML-validity bug)** |

### ASSEMBLE — `converter_service.py`
Flat vertical string-join of independently-rendered fragments into the shell (`converter_service.py:862`, `:879`). No cross-section structural reasoning — cannot reflow two adjacent sections into one shared multi-column table. **(Confirmed; downstream consequence of segmentation, not a count cause.)**

### VLM verify→correct loop (RC-G) — **dead on every default path**
- Wired only into `convert_document_mjml` (`converter_service.py:375`); the default `convert_document` discards screenshots (`:286 _ = design_screenshots`).
- `vlm_verify_enabled` defaults False (`config/design_sync.py:58`); production callers never pass `design_screenshots` → short-circuit at `:396` always fires.
- Even if revived, `correction_applicator` is **property-only**: `_LAYOUT_SIMPLE_PROPS` = {width, max-width, min-width, text-align, vertical-align} (`:35-37`); complex layout returns None (`:158`); it splices into a fixed marker byte-range (`:327`) and **cannot add/remove/reorder/merge sections.** **(Confirmed; cannot fix count even if revived.)**

### Stage-attribution verdict
**On the current fixed-seed engine, wrong section COUNT is a SEGMENTATION defect (S1–S5), upstream of and orthogonal to RC-C.** `match_all` and `render_all` are strictly 1:1; RC-C is the per-section *content/geometry* ceiling, a separate axis. **Do not default-blame RC-C for count errors.** The hypothesis "wrong count originates upstream of the renderer" is **confirmed** by the count ladder: the count is fully determined by `analyze_layout` before any seed is chosen.

> **Cross-fork caveat:** this attribution is scoped to the *fixed-seed pipeline*. The recursive-renderer fork (b) does not invoke `analyze_layout`/`match_all` (it imports only the `EmailSection` type, `converter.py:27`, then recurses `node.children` directly) — so on that path the segmentation stage, and its count error, **do not exist**. audit_2's live spike confirms fork-(b) produced the correct 8 LEGO bands. See §6 Part B.

---

## 5. What is NEW vs prior audits

**audit_3 adds:**

1. **The per-stage count ladder across all 6 live fixtures** (§3a) — target → candidates → analyze → rendered, with per-section element bags. No prior audit (CONVERGENCE-PLAN V1/V2, fidelity-gap, pipeline-audit) produced this; they had only endpoints or prose.
2. **Corrects the direction of the problem.** Every prior doc diagnosed **under-count only** and prescribed a one-way splitter (V2 Fix E). The live manifest + ladder prove the error is **bidirectional**: 6/5/10 under, 7/9 over. A one-way splitter would regress 7/9.
3. **Identifies the single asymmetric mechanism.** Both directions come from the **same** wrapper-unwrap pass: the `≥2 section children` requirement (`:581-584`) leaves single-child wrappers merged (under), while the same pass explodes multi-child card wrappers (over). This is sharper than the prior "two separate bugs on the same gate" framing and **replaces** the (refuted) naming-convention story.

**Prior claims corrected:**
- **REFUTED:** under-count is caused by descriptive naming / the MJML gate being closed. All six fixtures are MJML; the gate is open everywhere. Under-count is the `≥2-children` requirement + flat ingest.
- **Clarified:** LEGO "8 vs 20" is a granularity trap — manifest target (8) and `phase49_baseline` (8) count **top-level bands**; the manual's "20 numbered sections" counts **nested component instances** (the depth-2 membership cards, cf. deferred `phase-50.8`). Throughout this audit "sections" = top-level bands; LEGO over-segments bands (17 vs 8), it does not under-count vs 20.
- **Clarified:** case 8 (11 vs 10) is **within tolerance** and is not an over-segmentation exemplar; do not group it with LEGO's +9.

**Confirmed-still-open structural bugs (current code, do not re-propose as "new"):**
- V2 Fix E **section splitter** never implemented — no `DESIGN_SYNC__SECTION_SPLITTER_ENABLED`, no `_split_card_grid` (grep empty). Only the MJML-gated `_expand_container_wrappers` exists.
- V2 Fix A (images in text-block) **not landed** — `_fills_text_block` never reads `section.images`.
- V2 Fix B (all buttons) **not landed** — `component_matcher.py:1002` still `section.buttons[0]`; multi-CTA collapse persists.
- `<br><br>`.join collapses N body texts to one slot (`:978`, `:987`, `:998`) — blocks per-node typography.

**Dead-ends NOT to repeat:**
- "Recursive renderer just needs wiring" — over-simplified: it was deleted in `d9132c7c` and needs ingest re-plumbed to persist the `DesignNode` tree. (It **does** fix the section count by construction — audit_2 live spike → 8 LEGO bands — but is middle-tier: no effects/pixel. So this is a real fork option, not just a dead end. See §6 Part B.)
- Enabling Phase 47-49 flags on the snapshot pipeline — proven bit-identical no-op.
- Forcing `output_format='tree'` (TreeCompiler) — dead-on-arrival, falls back to legacy.
- Regenerating snapshot baselines to go green — bakes in wrong output; `expected.html` *is* the converter's output, so regression-green ≠ fidelity.
- Trusting the "97%→99% fidelity ladder" — computed by the blind RC-F metric; aspirational, not operative.
- Per-run typography via `style_runs` / removing the first-heading `break` — overrides collide on shared CSS classes; needs per-node `<td>` anchors.

---

## 6. Fix plan

### Part A — Interim fixes to the current (fixed-seed) engine

> **Correction (reconciled with `docs/converter_audit_2.md`'s live fork-b spike):** an earlier draft labelled these "fork-independent." That is wrong. They all live in the current fixed-seed pipeline (segmentation → matcher → seed renderer). If fork **(b)** is later chosen, that pipeline is replaced wholesale and these are **not preserved** — so they are *fork-a improvements with interim value*, not fork-independent. Split them by throwaway risk:
> - **Ship now regardless (cheap, ≤1d each, fix real defects in *today's* shipped output):** **A4, A5, A6, A7.** A5 in particular stops fabricated footer addresses + `Section Heading` leaking into live emails.
> - **Fork-sensitive — high throwaway risk if fork-(b) wins (it fixes count *and* proportional columns by construction):** **A1, A2, A3, A8.** Do these only as a deliberate interim fork-a investment, or **after** the 53.1 fork decision. Sinking the ~5–8d A1 rework before deciding is precisely the throwaway risk the Phase-53 plan exists to avoid.

| # | fix | stage | file:line | 53.x slot | effort | risk | sequencing |
|---|-----|-------|-----------|-----------|--------|------|------------|
| A1 | **Bidirectional grouping pass.** Make `analyze_layout` group by the design's intended bands, not raw wrapper depth: (a) **split** single-section-child wrappers whose child holds heading+body+CTA-type siblings (fixes under-count 5/6/10); (b) **merge** repeated sibling cards into one band by *consuming* the already-computed `RepeatingGroup` in the render path instead of re-flattening it (fixes over-count 7/9). | segmentation | `layout_analyzer.py:520-576`, `:579-598`; `converter_service.py:611-633` | 53.2 (fork-a; or post-53.1) | L (5-8d) | high — changes count for all fixtures; **subsumed if fork-(b) is chosen** | **gate on 53.1** |
| A2 | **Stop re-flattening detected sibling groups** in the legacy render path (subset of A1, shippable alone): render `RepeatingGroup` membership as one band. Directly fixes LEGO 17→ closer to 8. | seed-match | `converter_service.py:611-633` | 53.2 | M (2-3d) | medium | can land before A1 |
| A3 | **Bind image+text per card before matching** — `_fills_text_block` / segmentation must keep each card's image with its text (V2 Fix A). Kills the `text-block`/`full-width-image` alternation fingerprint. | segmentation/seed-match | `component_matcher.py:963-1020` (add `section.images`); `layout_analyzer.py:1117-1147` | 53.2 | M (2-3d) | medium | with A1 |
| A4 | **Fix phantom slug** — map `faq-accordion` → real `faq-item`/`faq-list`, or stop emitting it. | seed-match | `component_matcher.py:474` | 53.6 | S (<1d) | low | anytime |
| A5 | **Blank unmatched seed defaults** — `_fill_text_slot` should clear a slot's default text on no-match instead of leaking `Section Heading` / fabricated footer boilerplate. | render | `component_renderer.py:601-634` | 53.6 | S (1d) | low — verify footer-required fields aren't blanked | anytime |
| A6 | **Wrap column-text fragments in an inner `<table>`** to fix invalid `<tr>`-in-`<td>` nesting. | render | `component_matcher.py:693-759`; `component_renderer.py:538-599` | 53.6 | S (1d) | low | anytime |
| A7 | **Multi-CTA support** — emit all `section.buttons`, not `buttons[0]` (V2 Fix B). | seed-match | `component_matcher.py:1002` | 53.6 | S (1d) | low | anytime |
| A8 | **Per-column-width override target** + plumb `ColumnGroup.width` to the matcher so asymmetric splits aren't forced to equal seeds. | render + seed-match | `component_renderer.py:699-781`; `component_matcher.py:183-190`; `layout_analyzer.py:926-965` | 53.6 | M (2-3d) | medium | after A1 |

**Recommended immediate order:** ship **A4/A5/A6/A7 now** (cheap, low-risk, fix real defects in today's output, survive any fork). **Gate A1/A2/A3/A8 on the 53.1 fork decision** — if fork-(b) is chosen they are subsumed (it fixes count + proportional columns by construction), so pursue them now only as an explicit interim fork-a investment. Every count-affecting change must be validated against the **count ladder per fixture** (§3a), not the snapshot gate (which is byte-stability, not fidelity).

### Part B — The engine-fork decision (do NOT decide here)

This audit deliberately does **not** pick a winner. The choice is a **user decision gate (53.1)** that **requires the wired pixel metric**, which is blind until asset resolution (52.1-finish). Characterizations from the evidence:

| fork | what it is | structural reach | does it fix the count? | cost / dependency |
|------|-----------|------------------|------------------------|-------------------|
| **a — keep fixed-seed** (+ Part A) | current engine, with segmentation + matcher + slot fixes | per-section content/typography ceiling stays (RC-C: no z-order/overlap/free geometry; R2/R3/R6 soft caps) | **Yes** — A1/A2/A3 fix count at segmentation, where the defect lives | lowest; Part A only |
| **b — restore recursive renderer** (`d9132c7c^`, 1625 LOC) | walks the Figma tree, emits HTML structurally (per-node typography, Auto-Layout rows/cols, gradients) | higher **within-section** geometry/column fidelity; **never pixel-faithful**; no effects/rotation/overlap | **Yes — by construction.** It does **not** call `analyze_layout`/`match_all` (imports only the `EmailSection` type, `converter.py:27`); it recurses the `DesignNode` tree directly (`node.children`, `_group_into_rows`, proportional column widths from child widths). audit_2's **live spike** ran it on LEGO → **8 correct bands**. Band granularity = the Figma tree's frame structure (matched the design for LEGO; only LEGO was spiked, so not yet verified for the other 5). | high; needs ingest re-plumbed to persist the full `DesignNode` tree (`from_legacy` discards it, `converter_service.py:315 _frames=[]`); ~2.5–4 eng-weeks; shares the same blank-image asset gate |
| **c — rasterize** non-reproducible subtrees | export frames as images where email cannot express the design | pixel-faithful for rasterized regions; loses live text/links there | orthogonal to count | per-subtree; needs asset resolution + a reproducibility classifier |

**Decisive cross-fork fact (corrected against audit_2's live spike):** fork-(a) and fork-(b) fix the count by *different means* — fork-(a) needs the ~5–8d A1 bidirectional-grouping rework inside `analyze_layout`; fork-(b) gets the correct count **for free** by bypassing `analyze_layout` and walking the tree (LEGO → 8 bands, spiked live). So the count fix is **not** fork-independent: choosing fork-(b) makes A1/A2/A3/A8 throwaway. The real trade is fork-(b)'s correct-count-by-construction + higher within-section fidelity **vs** its cost (ingest re-plumbing to persist the `DesignNode` tree; ~2.5–4 eng-weeks) and its middle-tier ceiling (no effects/pixel). This is a genuine, consequential choice — **gate it on the wired metric (53.1); do not decide it on prose, and do not sink a week into fork-(a) segmentation rework before deciding.**

---

## 7. Honest ceiling & dependencies

**What "fixed" can mean.** Email HTML is `table`/`td` + inline CSS + MSO ghost tables. Hard, fork-independent caps:

| design feature | reproducible in email? |
|----------------|------------------------|
| stacked bands, columns (equal or, with A8, asymmetric), typography, solid fills, links, CTAs | yes |
| Outlook rendering | ~95% floor regardless of engine (table + VML) |
| drop/inner shadows, blur, blend modes | no — flat fallback only |
| gradients | partial — linear-gradient CSS + VML fallback; not all clients |
| rotation, free 2D geometry, z-order / overlapping elements | no — not expressible in flow layout |
| SVG / decorative vectors | rasterize or inline PNG (fork-c) |

So even a perfect engine cannot exceed the email box-model. "Fidelity" should be measured against **what email can express**, not against the pixel-exact design.

**Hard dependency chain (must land in order):**

```
asset resolution (52.1-finish: node-id → on-disk image map)
        ↓
wired, color-aware fidelity metric (RC-F corrected: CIEDE2000 LAB, MIN-agg, runs in pipeline)
        ↓
engine-fork decision (53.1 — user gate, evidence-driven)
```

Part A is **fork-independent and ships before the metric is wired** (validated by the count ladder + three-way topology diff). Part B **must wait** for the wired metric — choosing an engine against the blind metric repeats the months-long churn the Phase 53 plan explicitly warns against (`52-converter-foundation.md:149`).

---

## 8. Appendix

**Dropped / low-severity singleton claims:**
- maap store-pill rows lose the left-aligned 2-row grid (R2 soft cap; low severity, subsumed by A8).
- `tree_normalizer._remove_invisible` edge-case undercount (narrow; not observed in the 6 fixtures).
- ContentGroup carries no geometry (`layout_analyzer.py:143-156`) — feeds RC-C, not count.

**Cross-references:**
- `HANDOFF.md` — Phase 52 property-plumbing fixes (RC-A/RC-B), dead-end list, asset-gate (22 node-id URLs unmapped).
- `.agents/plans/52-converter-foundation.md` — Phase 53 fork gate (53.1), ingest render (53.3), VLM revive/retire (53.4), honest ceiling doc (53.7). Part-A items map to 53.2/53.6.
- `.agents/deferred-items.json` → `phase-50.8-nested-physical-cards` (**closed/superseded**): documents that LEGO's membership card is nested at depth-2 inside `section[7]`'s mj-wrapper and that `analyze_layout` needs subtree-walking for physical-card surfaces — directly relevant to fix A1 (the bidirectional grouping pass must descend into nested card surfaces, not just unwrap top-level wrappers).

> All section counts, the count ladder, naming-convention detection, the maap hero merge / navbar-hide / seed-default leaks, the slot-fill-rate drops, and the unlanded-fix claims were verified by re-running the live pipeline and reading current code on `tech-debt/phase-52-converter-foundation` (2026-06-01). No fidelity percentages are asserted; the pixel metric is blind until asset resolution lands.
