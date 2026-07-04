# Converter Audit #4 — Why design-sync output still doesn't match the design (2026-07-03)

> **Question answered:** Phases 52–53 fixed the serializer bridge, section counts, and property
> plumbing — yet conversions still look visibly wrong. Why?
>
> **Answer:** the section-count war is won (ladder 5-of-6 exact), but **in-section render
> fidelity** is broken by seven verified mechanisms in the seed-fill layer
> (`component_matcher.py` / `component_renderer.py`) — none of them segmentation, none of them
> the bridge. The committed `expected.html` baselines contain every one of these defects, so
> the snapshot regression has been passing-while-wrong the entire time.
>
> **Fix plan:** `.agents/plans/53-f-render-fidelity.md` (Track F of the operative Phase-53 plan).

## 1. Method

- Fresh conversion of all 6 fixtures (`data/debug/{5..10}`, local assets present since §A4).
- Playwright render at 600px (`render_case_png`) → CIEDE2000 pixel scoring
  (`score_case_fidelity`) against the reference design PNGs
  (`email-templates/training_HTML/for_converter_engine/*/visual_design.png`).
- Side-by-side visual audit of every case (reference vs render, chunked).
- Four independent code traces, each verified at file:line against fixture input
  (`structure.json`) and output (`actual.html`).

## 2. Measured state (first multi-case pixel numbers)

| Case | Fixture | full_image | section_min | section_median | Ladder (rendered/target) |
|---|---|---|---|---|---|
| 5 | maap | **0.879** | 0.634 | 0.896 | 13/13 |
| 6 | starbucks | 0.801 | 0.480 | 0.682 | 9/9 |
| 7 | LEGO | **0.624** | 0.300 | 0.683 | 8/8 |
| 8 | performance | 0.702 | 0.302 | 0.683 | 10/10 |
| 9 | slate | **0.640** | 0.357 | 0.696 | 8/8 |
| 10 | mammut | 0.679 | **0.087** | 0.777 | 12/18 (known residual) |

Counts are right; pixels are not. `make converter-data-regression` is green — because
`expected.html` **is** the converter's own output (audit-1's lesson, still true).

## 3. Root-cause inventory (all verified at file:line)

### RC-F1 — Multi-image sections collapse to `images[0]` (heroes vanish, icons stretch)
Every single-image fill builder takes `section.images[0]` and silently discards the rest:
`_fills_full_width_image` (~`component_matcher.py:1505`), `_fills_hero` (~`:984`),
`_fills_logo_header` (~`:955`), `_fills_image_block` (~`:1266`), `_fills_article_card` (~`:1216`).
- Case 7 hero section `2833:1875` = [600×67 strip, **600×400 hero**] → hero dropped.
- Case 8 hero section `2833:2258` = [**64×64 icon**, 600×480 hero] → hero dropped AND the
  64px icon stretched to 600px ("giant logo tile").
- Both hero node IDs are absent from `expected.html` too — baseline passes-while-wrong.
- **Overturned hypothesis:** this is NOT an ingest gap; both heroes are fully parsed in
  `structure.json` (imageRef, bbox, scaleMode all present).

### RC-F2 — Image seeds have no background surface; `_outer` override can only replace
`section.bg_color` is parsed correctly (dark fills `#181818`/`#2B2B2B` present in fixtures;
captured at `layout_analyzer.py:467`, emitted as `_outer` override at
`component_matcher.py:1822-1830`). But `full-width-image`/`image-block`/`image-grid` seeds
carry **no** `background-color` and no `_outer` class, and the renderer fallback
(`component_renderer.py:933-944` → `_replace_first_css_prop`) only *replaces* an existing
declaration — it never *inserts* one. Every image-only section on a dark band flips to white
(Ferrari, slate, mammut footer). **Overturned hypothesis:** NOT the 53.3 `child_bg` ingest
limit — these are plain SOLID fills, lost render-side.

### RC-F3 — Image width dropped at fill-build time (giant pixelated icons/arrows)
Width IS captured (`ImagePlaceholder.width`, `layout_analyzer.py:1280`) and then ignored:
- Column path: `_column_image_row` (`component_matcher.py:826-840`) hardcodes
  `style="…width:100%…"`, never reads `img.width` → slate pins/thermometers, mammut nav
  arrows fill the column.
- Single-image path: only `_fills_logo_header` (`:966-969`) and `_fills_full_width_image`
  (`:1037-1040`) thread `overrides["width"]`; `_fills_image_block`/`_fills_hero`/
  `_fills_image_grid`/`_fills_product_grid` don't → seed's `width="600"`/`max-width:600px` wins.
- No decorative flag exists for plain IMAGE nodes: `is_background` is set only for
  FRAME-with-image-fill (`layout_analyzer.py:1287-1295`), so background decorations (LEGO
  brick outlines) enter the normal flow.

### RC-F4 — Unfilled seed slots leak seed-default content and styling
`_blank_unfilled_text_slots` (`component_renderer.py:784-820`) reaches **`<td>` slots only**
(`_TEXT_SLOT_OPEN_RE` at `:28`); `<span>`/`<a>`/`<img>` seed defaults survive by construction.
`_strip_placeholder_urls` (`:1507-1513`) knows 3 hosts — `fakeimg.pl` is not one of them.
Verified leaks:
- `cta-button.html`: `<span data-slot="cta_text">Shop Now</span>` + hardcoded `#0066cc` +
  VML `fillcolor` → Starbucks nav renders 3 blue "Shop Now"; the design-color override is
  gated on `if section.buttons:` (`component_matcher.py:1948-1962`) so an empty `buttons`
  list leaves seed blue. `_fills_cta` returns `[]` when no buttons (`:1396`).
- `col-icon`: routed to `_fills_text_block` which emits `heading`/`body`, but the seed
  declares `heading_1/heading_2/icon_1_url/icon_2_url` — **slot-id mismatch, 0/4 fill by
  construction** → slate's 2×2 broken "Feature icon" grid (`fakeimg.pl` ×8 in actual.html).
- `event-card.html`: 📅/📌 emoji are static text *outside* the slot spans → un-blankable.
- `hero-block/hero-split/zigzag-*/event-card-minimal/article-card`: bare
  `<span data-slot="cta_text">Learn More|Read More</span>` → spurious CTAs (maap, mammut).
- **Five extended slugs have no fill builder at all** — `countdown-timer`, `testimonial`,
  `pricing-table`, `video-placeholder`, `zigzag-alternating` score in
  `_score_extended_candidates` (`:389`) but are missing from the builders dict
  (`:506-578`) → they can only ever render seed placeholder text.
- The `low_slot_fill_rate` warning (`component_renderer.py:436-453`) reports; nothing repairs.

### RC-F5 — Footer legal/unsubscribe content destroyed in both branches
`_fills_footer` (`component_matcher.py:1407-1425`) builds ONE `footer_content` fill that
replaces the **entire** cell — wiping the seed's unsubscribe/preferences/legal rows whenever
Figma footer text exists. With no Figma text, the preserved seed leaks raw
`{{unsubscribeUrl}}` merge tags (confirmed in case-5 output). The comment at
`component_renderer.py:30-35` claiming BrandRepair fixes this downstream is **false**:
`RepairPipeline` is never invoked from any design-sync path (`converter_service.py`,
`import_service.py`, `routes.py` — zero repair imports), and `BrandRepair._repair_footer`
(`qa_engine/repair/brand.py:141-172`) early-returns on the seed's surviving `footer-bg`
class and never injects unsub links anyway.

### RC-F6 — Eyebrow/heading order systematically swapped
`_detect_content_hierarchy` (`layout_analyzer.py:1580`) buckets texts by font-size
(`is_heading` = ≥1.3× median); builders partition by that flag
(`_fills_text_block:1137`/`_body_slot_texts:1146`); seeds hardcode heading-slot-above-body
(`text-block.html:7/12`, `hero-block.html:12/17`). A small eyebrow ABOVE the headline is
classed as body → renders BELOW. Confirmed in `data/debug/8/actual.html:313-325`
("DESIGNED TO EXCEED LIMITS" above the red "FERRARI 849 TESTAROSSA" eyebrow). Y-order is
discarded the moment texts are bucketed. Affects maap + Ferrari (both editorial sections).

### RC-F7 — Intra-section geometry discard (the structural fixed-seed ceiling)
`TextBlock`/`ImagePlaceholder`/`ButtonElement` carry **no x/y** (`layout_analyzer.py:67-131`);
sections flatten to `(texts[], images[], buttons[])` in tree order. Consequences:
- 2-col detection requires frame-wrapped children (`_FRAME_TYPES` = FRAME/GROUP/COMPONENT,
  `:284`; Strategy 2 needs `layout_mode=="HORIZONTAL"`, `:1073-1081`) → bare IMAGE+TEXT
  side-by-side sections stay SINGLE and stack. Peel requires literal `"mj-wrapper"` naming
  (`sibling_detector.py` `_peelable_grandkids`) — non-MJML files never peel.
- Child-frame cards are invisible: `_detect_inner_bg` (`layout_analyzer.py:1665-1703`) never
  walks child frames and gates on an existing `container_bg` → LEGO's white cards vanish.
  Conversely seeds bake their own surfaces (`text-block`/`article-card`/`col2-bg` `#ffffff`).
- No vertical-nav seed; `_fills_nav` hardcodes `color:#333333` 14px (`:1611,1621`).
- Pill/tag radius: `ButtonElement.corner_radius_spec` captured but never emitted
  (`component_matcher.py:1844-1856` — "no tag/pill slot yet"); column CTA fallback radius
  `"4"` (`:853`) → maap ovals render as near-rectangles.
This is the class the ratification-pending **composite-slot chain (51.1–51.6,
`.agents/plans/deferred/TRIAGE-2026-06-12.md`)** exists to lift.

### Latent (not causal today)
- `figma/service.py:607-612`: RECTANGLE with IMAGE fill is reclassified to IMAGE but
  `imageRef` is never captured (`image_ref=null` corpus-wide). Assets resolve by node-id, so
  harmless today — bites the FRAME-background-image gate (`layout_analyzer.py:1287`) and any
  future imageRef dedup.

## 4. De-ranked / environmental findings
- **Brand-font loss (mammut mono, Starbucks serif) is mostly environmental**: emitted HTML
  carries `font-family:Geist Mono,sans-serif` correctly; the render harness (and most email
  clients) lack the font. Real residual: consider `@font-face` injection for supporting
  clients — separate, low priority.
- **Starbucks "invented white card" reconciliation**: the maroon Holiday-Countdown section
  currently routes to `column-layout-2` with correct `#AA1733` bg and side-by-side layout in
  `actual.html`. The seed-baked-surface mechanism (RC-F7) is real, but that named instance
  renders columned — the visual audit likely mis-localized an adjacent single-column section.
- Segmentation is NOT re-opened: ladder 5-of-6 exact; mammut 12/18 stays the deferred
  below-candidate residual (`phase-53-d3-mammut-below-candidate-undercount`).

## 5. Why months of gates never caught this
1. `expected.html` = converter's own output → snapshot regression can't see wrong-but-stable.
2. The A2 gate counts sections, not content — counts are now correct.
3. The A3 pixel metric only ran on case 5 in CI (assets gitignored), and only full-image /
   min / median aggregates — nobody looked at the renders.
4. `low_slot_fill_rate` warns in logs nobody reads; nothing repairs or fails.

## 6. Disposition
Fix plan: `.agents/plans/53-f-render-fidelity.md` (Track F). Expected headline movement:
RC-F1+F2+F3 dominate the pixel gap on cases 7/8/9/10; RC-F4+F5 are correctness/compliance
must-fixes regardless of pixels.
