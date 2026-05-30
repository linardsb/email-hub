# Phase 50–53: Design-to-HTML Converter Fidelity Master Plan

> **⚠️ SUPERSEDED NUMBERING (2026-05-30).** The "Phase 50–53" labels in this plan are **stale** — they predate TODO.md reassigning 50→Tech Debt and 51→Agentic Security. They never entered the operative backlog. The converter-fidelity roadmap now lives in `TODO.md` as **Phase 52 (Foundation)** + **Phase 53 (Engine)**; full plan in `.agents/plans/52-converter-foundation.md`.
>
> **⚠️ PREMISE INVALIDATED by re-audit (`wf_fa48d17b-6ea`).** This plan's Rules 1–11 + composite-slot work is **neutered before it can fire**: the `EmailDesignDocument.to_email_section` reader bridge nulls `text_color`/`text_align`/`corner_radius_spec`/CTA-stroke (the inputs these rules consume) on every production path, so Phase 50 is *built + enabled-by-default + inert*. The "Current State ✅" rows below (CTA fidelity, Rule-10 per-corner radii, token overrides) **do not affect shipped output** until the bridge is repaired (Phase 52.2/52.3). The **85→99% Success-Metrics ladder is an unfalsifiable projection** — it is computed by the grayscale/blurred/gmail-only/off-by-default SSIM that the re-audit proves cannot see color, gradient, shadow, or sub-pixel spacing. Promote any rule from here **only via Phase 53.6**, after the bridge is fixed (52) and the metric is real (52.1).

## Source

`docs/architecture/opus-figma-to-html-process.md` — direct-Opus conversion of LEGO Insiders Halloween (Figma `2833:1869`) vs. the email-hub `design_sync` converter. Documents 12 gaps, 11 detection rules, and a 5-stage repair loop.

**Artifact triplet** (in `email-templates/training_HTML/for_converter_engine/Lego/`):
- `viaual_design.png` — source Figma design screenshot
- `hub_converter_phase49_baseline.html` (350 lines) — **frozen** Phase 49 baseline; "before" anchor with known gaps. Never regenerate
- `manual_component_build.html` (1309 lines) — target output (Opus manual build using hub components, all 11 rules `[Rule N]`-tagged)

Used as the canonical before/after diff pair for Phase 50 acceptance.

## Goal

Close the converter's structural fidelity gap from ~85% (today) → ~99% (Phase 53) on real-world designs by:

1. Threading the **full-design PNG** through classification (Gap 9 — single biggest leverage point).
2. Two-stage layout: **wrapper unwrap → section classify** (Gap 1 — unblocks Gaps 4, 6, 9, 10).
3. **Composite slot type** so cards can contain tag-pills + spec-lists + CTAs (Part 4 §3 — collapses Gaps 2, 3, 4).
4. **Universal repair loop** with the 11 detection rules codified as a deterministic dispatch table (Part 8).

The fidelity ladder is additive — each phase ships ~5pp of fidelity gain, all measured against the existing snapshot regression suite (`make converter-data-regression`).

## Current State (Phase 49 complete)

| Capability | File | Status |
|---|---|---|
| Sibling detection | `sibling_detector.py:62` | ✅ Detects N consecutive similar sections |
| Repeating-group renderer | `component_renderer.py:render_repeating_group()` | ✅ Wraps in container `<table>` + MSO ghost |
| Section/component classifier | `component_matcher.py:_score_candidates` | ✅ 122 tests passing, extended scoring 49.3 |
| Token override (text + bg + cta) | `component_matcher.py:1401` | ✅ 14 properties on `_outer/_inner/_heading/_body/_cta` |
| Slot content extraction | `layout_analyzer.py:_extract_content_groups` | ✅ Per-FRAME children with role hints |
| Per-email token scoping | `figma/service.py:sync_tokens_and_structure` | ✅ Subtree-scoped via `target_node_id` |
| CTA fidelity | `component_matcher.py:_walk_for_buttons` | ✅ Stroke + icon + radius + per-button |
| EmailTree bridge | `tree_bridge.py:build_email_tree` | ✅ ComponentMatch[] → EmailTree |
| Data-driven regression | `tests/regression_runner.py` | ✅ 4 cases, 62 parametrized tests |
| **Bgcolor propagator** | `bgcolor_propagator.py` | ⚠️ Single-direction; needs promotion to boundary classifier (Phase 50.2) |
| **Full-design PNG** | `figma/service.py:522` | ❌ Fetched + written to disk; **discarded before classification** (Gap 9) |
| **Wrapper unwrap** | `layout_analyzer.py:_get_section_candidates` | ⚠️ Only top-level frame; doesn't unwrap inner `mj-section` children of tall `mj-wrapper` (Gap 1) |
| **Composite slots** | n/a | ❌ Slots take strings only — no `composite_slot` type (Part 4 §3) |
| **Repair loop** | `visual_verify.py:run_verification_loop` | ⚠️ Per-section design diff only; no rendered-HTML diff, single viewport, no rule dispatch (Part 8) |

## Phases

| # | Theme | Subtasks | Fidelity ceiling | Blocks |
|---|---|---|---|---|
| 50 | Foundation: global PNG + wrapper unwrap + cheap FRAME-tree rules | 7 | ~93% | Phase 51, 52 |
| 51 | Composite slot infrastructure + Rule 1 + missing slot patterns | 6 | ~96% | Phase 52 |
| 52 | Universal repair loop + multi-viewport + remaining rules | 10 | ~98% | — |
| 53 | Optimizations + extension hardening | 7 | ~99% | — |

## Dependency Graph

```
50.1 (full PNG threading) ──┬─→ 50.4 (nested-card bg)
                            ├─→ 52.8 (Rule 4: visible divider absent)
                            ├─→ 52.9 (Rule 5: asset name vs content)
                            └─→ low-confidence VLM fallback (50.5+)

50.2 (bgcolor boundary)  ──┬─→ 50.3 (wrapper unwrap)
                           └─→ 53.4 (transition band)

50.3 (wrapper unwrap)    ──┬─→ 50.4 (inner sections need wrapper bg)
                           ├─→ 51.2 (Rule 1 needs sub-section unwrap)
                           └─→ 51.6 (composite footer)

50.4 (nested-card bg)    ──┬─→ 50.5 (Rule 11 reads inner card width)
                           └─→ 52.7 (Rule 9 nested dark mode)

50.7 (physical-card)     ──→ 52.7 (Rule 9 identity exception)

51.1 (composite slot)    ──┬─→ 51.2 (Rule 1 emits composite container)
                           ├─→ 51.3 (tag/pill slot)
                           ├─→ 51.4 (spec list slot)
                           └─→ 51.6 (composite footer rewrite)

52.3 (structural correction applicator) ──→ 52.4–52.7 (rules needing wrap_in / add_class)
```

---

## Phase 50 — Foundation (global PNG + wrapper unwrap + cheap rules)

**Theme.** Capture the global visual context the converter is currently throwing away, separate wrapper from section, and ship the FRAME-tree rules that need no PNG. Per Part 8 §5: "Rules 7–11 are pure FRAME-tree reads — cheapest to ship, biggest silent-misread reduction."

### 50.1 — Full-design PNG threading (Gap 9)

**One-line.** Fetch full-frame PNG once at conversion start; thread `design_image: bytes | None` through `DesignFileStructure → analyze_layout → match_section → visual_verify`.

**Why first.** Gap 9 is the converter's structural ceiling — without the global PNG, every classification decision is local to one section, and ~5 of 12 gaps cannot be detected. Doc TL;DR: "without this, the converter is structurally limited to ~85% fidelity."

**Touches.** `figma/service.py:522` (export endpoint exists, just needs production-flow wiring), `protocol.py:DesignFileStructure:160` (new field), `layout_analyzer.py:222` (new param), `component_matcher.py:56` (new param threaded through), `visual_verify.py` (low-confidence path). See `.agents/plans/50.1-full-design-png-threading.md`.

### 50.2 — Bgcolor → section-boundary classifier (Part 4 §1)

**One-line.** Promote `bgcolor_propagator.py` from single-direction propagator to boundary classifier: emits `continuous_with_above | continuous_with_below | hard_break` per section.

**Why second.** Shared computation for Gaps 1, 6, 8 — pixel sampling already exists, just needs API reshape and bidirectional sweep. Output is consumed by 50.3 (wrapper unwrap) and 53.4 (transition band).

**Touches.** `bgcolor_propagator.py` (rewrite as `BoundaryClassifier`), new `EmailSection.boundary_above / boundary_below: Literal["continuous","hard_break"] | None`, wired before `analyze_layout()` returns. See `.agents/plans/50.2-bgcolor-boundary-classifier.md`.

### 50.3 — Wrapper unwrap pre-pass (Gap 1)

**One-line.** When a candidate `mj-wrapper` has a fill color **and** ≥2 inner `mj-section` children, return the children with `wrapper_bg_color` propagated.

**Why third.** Two-stage layout (wrapper detection → inner-section classification) unblocks Gaps 1, 4, 6 simultaneously. Cost is O(N) over wrappers. The `mj-wrapper` MJML idiom is the canonical signal.

**Touches.** `figma/layout_analyzer.py:385-410` (`_get_section_candidates` second unwrap pass), `figma/layout_analyzer.py:135-165` (`EmailSection.wrapper_bg_color` field — distinct from existing `bg_color`), new `_is_container_wrapper()` predicate. See `.agents/plans/50.3-wrapper-unwrap-prepass.md`.

### 50.4 — Nested-card bg (`container_bg` / `inner_bg`) (Gap 10)

**One-line.** Add `container_bg`, `inner_bg`, `inner_radius` fields on `EmailSection`; emit two-target overrides `(_outer, container_bg)` + `(_inner, inner_bg)` + `(_inner, border-radius)`; component HTMLs gain inner-table layer `<td class="_outer"><table class="_inner">…</table></td>`.

**Why fourth.** Closes the white-card-on-coloured-wrapper pattern (LEGO membership cards, product rows). Depends on 50.1 (PNG sampling for inner_bg detection when FRAME has empty fill) and 50.3 (wrapper unwrap so inner sections exist).

**Touches.** `figma/layout_analyzer.py:135-165` (3 new fields), `component_matcher.py:1401-1467` (override emission), ~6 component HTML files (`article-card`, `zigzag-image-{left,right}`, `editorial-2`, `event-card`, `pricing-table`). See `.agents/plans/50.4-nested-card-bg.md`.

### 50.5 — Pure FRAME-tree rules: 7, 8, 10, 11

**One-line.** Codify Rules 7 (pill alignment from bbox.x), 8 (corner radius from `cornerRadius`), 10 (image per-corner radii from `rectangleCornerRadii`), 11 (inner card width matches dominant child image width).

**Why bundled.** All four read FRAME-tree fields directly — no PNG needed. Doc §8.5: "should ship first because they have the highest hit rate per minute of engineering investment." Rule 11 lands here because 50.4 already emitted nested-card structure.

**Touches.** New `app/design_sync/frame_rules.py` (4 rule predicates + dispatch), `component_matcher.py:1401` (token-override emission for align/radius/per-corner), `component_renderer.py:_replace_*` (per-corner CSS longhand), `_build_token_overrides` consumes rule outputs. See `.agents/plans/50.5-frame-tree-rules.md`.

### 50.6 — Heading text-align from text-node attribute (Gap 11)

**One-line.** In `_build_token_overrides`, emit `(text-align, _heading, text.text_align.lower())` for the first heading and same for `_body`.

**Why ninth.** One-liner per role — but the highest-frequency silent misread (centered-by-default heading components misalign LEFT/RIGHT designs).

**Touches.** `component_matcher.py:1411-1428` (new override emission); renderer already accepts arbitrary CSS-property overrides (Phase 49.4). See `.agents/plans/50.6-heading-text-align.md`.

### 50.7 — Physical-card identity-exception signals (Rule 9 prep)

**One-line.** Add `EmailSection.is_physical_card_surface: bool` derived from FRAME signals (aspect ratio matches ID-1 / loyalty-card / boarding-pass + barcode/QR asset present + logo on white field + `cornerRadius` distinct from siblings).

**Why now.** Rule 9 (Phase 52.7) needs these signals to opt physical-card surfaces OUT of the auto-dark flip. Detection is a cheap FRAME-tree read but barcode/QR recognition needs an aspect-ratio + dimension heuristic now (deferring to Phase 52 risks Rule 9 misfiring on membership cards).

**Touches.** `figma/layout_analyzer.py` (new helper `_detect_physical_card()` + new `EmailSection` field), unit tests covering 1.586:1 / 2:1 / 4:3 aspect ratios + barcode-strip aspect ≥ 1:4. See `.agents/plans/50.7-physical-card-signals.md`.

---

## Phase 51 — Composite slots + Rule 1 + missing slot patterns

**Theme.** Add the slot-type infrastructure that lets cards contain tag-pills + CTAs, zigzag rows contain spec-lists, footers contain logo + barcode + social-row. This is the single biggest leverage point in Part 4: "Gaps 2, 3, 4 collapse to 'add a composite slot'."

### 51.1 — Composite slot type infrastructure (Part 4 §3)

`SlotFill` extended with a discriminated union: `string | composite[ComponentMatch]`. New sub-renderer recurses into composite slot values. Component HTMLs gain `data-slot-composite="<slot_name>"` markup. Builder/renderer consume the recursive form.

### 51.2 — Rule 1 pre-pass: card-with-N-children (advisor flag #1 + Gap 4)

`FRAME` with `fills[0]` non-default + `cornerRadius > 0` + ≥2 child frames → wraps children in one rounded outer table. Tag children with `parent_card_id`. Renderer groups consecutive sections sharing a `parent_card_id`. Reuses primitive `sibling_detector.py` already produces (49.1 / 49.2). Emits a composite slot containing the heterogeneous children.

### 51.3 — Tag/pill slot + role detection (Gap 2)

`_extract_content_groups` marks any text whose parent FRAME is a small fill+padding leaf (`layoutMode=HORIZONTAL`, `paddingLeft/Right ≥ 8`, single TEXT child) as `role_hint="tag"`. **Detection does NOT gate on `cornerRadius`** (per Rule 8 — pills can be square). Tag slot template emits alignment from Rule 7 + radius from Rule 8 (both 50.5).

### 51.4 — Spec mini-table slot (Gap 3)

New `_score_extended_candidates` trigger: ≥2 images ≤30px wide, each sibling-paired with a text < 40 chars. Confidence 0.92 with 2+ pairs. Spec-list emitted as composite slot containing N `(icon_url, label)` tuples — one cell pair per item. Used as a *child* component nested inside zigzag rows.

### 51.5 — Multi-line text splitter (Gap 12)

`_extract_texts` detects `\n` in TEXT node content and splits into structurally-paired children: first half `role_hint="value"` + second half `role_hint="label"`, plus `font_weight_diff` flag. `_safe_text` replaces `\n` with `<br>` after HTML-escape (fallback for un-split nodes).

### 51.6 — Composite footer cleanup (Gap 4 cleanup)

Rename `_fills_footer` → `_fills_footer_legal`. Card structure delegated to Rule 1 (51.2) + composite slot (51.1). Per advisor flag: avoids re-implementing footer twice.

---

## Phase 52 — Universal repair loop + multi-viewport + remaining rules

**Theme.** Codify the 5-stage repair loop (CAPTURE → DIFF → CATEGORIZE → APPLY → RE-RENDER + LOOP) from Part 8 §1, render at both desktop + mobile, dispatch corrections by rule_id, ship the rules that need PNG or structural mutation.

### 52.1 — Multi-viewport rendering (Part 8 §1 stage 1)

`run_verification_loop()` extended with `viewports: tuple[int, ...] = (600, 480)`. Renders HTML at both, compares both before applying corrections. Doc: "single-viewport rendering is the most common cause of 'fixed in one place, broken in another' loops."

### 52.2 — Categorized correction schema (Part 8 §1 stage 3)

VLM output schema constrained to `rule_id: Literal["rule_1", ..., "rule_11", "content_error"]`. `CorrectionApplicator` dispatches per rule. Rule mismatches surface as low-confidence telemetry rather than ad-hoc fixes.

### 52.3 — Structural correction applicator (advisor flag — HARD PREREQ for 52.4–52.7)

`CorrectionResult` extended with `wrap_in: dict | None` (parent tag + style) and `add_class: list[str]` per target element. Applicator can wrap existing elements and add classes, not just mutate styles/content/images on existing elements.

### 52.4 — Rule 2: responsive image overflow on stacked columns

When `class="column"` triggers `display:block;width:100%`, emit `class="bannerimg"` on every child image. Class sets `width:100%!important; max-width:100%!important; height:auto!important` at `max-width: 599px`.

### 52.5 — Rule 3: image padding inside non-bleed container + asymmetric padding

(advisor flag — moved up from 53.) Image's `absoluteBoundingBox` strictly inside parent FRAME's bbox + parent has non-default fill → emit `padding: <top> <right> <bottom> <left>` on wrapping `<td>` measured from design (4-tuple per side, NOT single value). Pair with `class="img-pad"` for mobile override.

### 52.6 — Rule 6: mobile DOM order via `dir="rtl"` flip pattern

Image-right desktop layout where mobile expects image-on-top → DOM order `[image][content]` + `direction: rtl` on parent at desktop only (mobile media query restores `ltr`). Per-side padding flipped to match. MSO conditional path `<table dir="rtl">` for Outlook. Verified working markup: `email-templates/training_HTML/for_converter_engine/Lego/manual_component_build.html` sections #10 and #12.

### 52.7 — Rule 9: dark-mode contrast on nested cards + identity exception

Every nested coloured surface gets its own `class="card-bg-N"` + matching `@media (prefers-color-scheme: dark) { .card-bg-N { background-color: <darkColor> !important } }`. Light→dark mapping from `design_system.py:dark_palette` (fallback: shift L by –40, hue preserved). **Identity exception**: physical-card surfaces (50.7's `is_physical_card_surface`) opt OUT — stay white in dark mode. User-info row text on dark-flipped bg gets `class="footer-strong"` + `!important` color overrides.

**Pre-flight:** check `.agents/deferred-items.json` for any open `phase-50.7-*` entries — Rule 9's correctness depends on `is_physical_card_surface` returning True on real cards, which is currently validated only against synthetic fixtures.

### 52.8 — Rule 4: visible divider absent from FRAME tree (needs PNG)

PNG diff: ≥2 sibling columns visibly separated by uniform 1-2px line, no LINE/RECTANGLE/TEXT node containing `|`/`·`/`–` between them in FRAME tree → emit `<td>` containing literal `|` + `color: #c8c8c8; padding: 0 14px;` (most robust across mail clients).

### 52.9 — Rule 5: asset name vs content mismatch (needs PNG)

When emitting `data-slot` candidates, base assignment on (1) aspect ratio (≥ 1:4 → barcode/strip), (2) sibling order (top → header logo, middle → content, bottom → decoration), (3) image-fill perceptual hash. `name` field used only as tie-breaker.

### 52.10 — Rule telemetry

Emit `log.info("conversion.correction_applied", rule_id=..., section_id=..., viewport=600|480|"dark", iteration=loop_iter, diff_severity="major"|"minor")` per applied correction. After 100+ conversions, histogram tells team which rules pay back the most engineering effort.

---

## Phase 53 — Optimizations + extension hardening

### 53.1 — Verification reuse for repeating groups (Gap 5)

When section is a `RepeatingGroup` member and member 1 has verified, cache corrections from member 1 + apply by default to members 2..N. VLM only as second-pass. Cuts VLM calls 4× on product grids.

### 53.2 — Hero-text-only + hero-image pairing (Gap 6)

Pair-detection: section A has 600px-wide image bottom-aligned; section B has texts + ≤1 button on non-white bg; A.bottom_color ≈ B.top_color (50.2 boundary classifier supplies). Merge into single `hero-block` component or tag both with `hero_pair_id`.

### 53.3 — Per-frame export as default (Gap 7)

`image_resolution_mode: "imageRef" | "frame_export"` toggle on `DesignSyncConfig`. Default `frame_export` for any frame whose node has children other than the imageRef-bearing rectangle (composited); `imageRef` for leaf rectangle. One extra batched `/v1/images` call per email.

### 53.4 — Transition band detection (Gap 8)

Single image with `width ≥ 95% of container_width` + bottom edge color matches next section's top edge color (50.2 supplies) + dimensions < 70px tall → `transition_band` type, zero padding on outer cell.

### 53.5 — Component selection: golden-reference confidence boost

`+0.05` confidence boost for components appearing in `email-templates/golden-references/` YAMLs. Doc Step 4 §3: "no concept of 'renderer track record' (golden references it knows handle this case correctly)."

### 53.6 — Reference set: `[Rule N]`-tagged transactional + newsletter

Add 2 new reference designs to `email-templates/`:
1. **Transactional** (e.g. order confirmation) anchoring rules 4, 6, 7, 8 in data-table-dominant layouts.
2. **Newsletter** (multi-section, multi-CTA) anchoring rules 1, 2, 3 across editorial content.

Tag both with `[Rule N]` markup matching LEGO. Wire into the regression suite (Phase 49.9) so the 11 rules are validated across heterogeneous designs.

**Closes:** `phase-50.7-ac-4` (LEGO regression promotion) and `phase-50-stranded-templates` (performance_reimagined + slate). See `.agents/deferred-items.json` — also promote those three existing `email-templates/training_HTML/for_converter_engine/` templates into `data/debug/`, not only the 2 new transactional/newsletter designs.

### 53.7 — Conversion quality checklist as automated gate (Appendix)

Convert the 14-item appendix checklist into deterministic post-render checks (HTML parse + style inspect):
- [ ] No `<div>`/`<p>` for layout (table-only)
- [ ] Every text `<td>` has `font-family/font-size/color/line-height/mso-line-height-rule:exactly`
- [ ] Every image has non-empty `alt` (or `alt=""+role="presentation"` for decorative)
- [ ] CTAs have VML round-rect for Outlook + table button for everyone else
- [ ] Dark-mode override classes on every coloured surface — including nested
- [ ] Pill align matches bbox.x relative to parent column (Rule 7)
- [ ] Pill border-radius matches `cornerRadius` (Rule 8)
- [ ] Image per-corner radii match `rectangleCornerRadii` (Rule 10)
- [ ] Inner cards with fixed-width image children have `width="<NATIVE_PX>" + align="center" + class="wf"` (Rule 11)
- [ ] Total HTML size < 100 KB after Maizzle inlining
- [ ] Adjacent section bgcolor continuity (50.2)
- [ ] Render at light + dark color-schemes (Playwright `color_scheme='dark'`)
- [ ] Footer legal text fits in ≤ 600px viewport
- [ ] Repeating rows alternate consistently or visibly stack uniformly

Wired as a gate in `make converter-data-regression`.

---

## Files Affected (Phases 50–53)

| File | Phases touching | Notes |
|---|---|---|
| `figma/service.py:522,1191` | 50.1, 53.3 | Full PNG export, per-frame mode toggle |
| `figma/layout_analyzer.py:135-165, 222, 385` | 50.1, 50.3, 50.4, 50.7, 51.5 | EmailSection fields, wrapper unwrap, multi-line splitter |
| `bgcolor_propagator.py` | 50.2, 53.4 | Promotion to boundary classifier, transition band |
| `component_matcher.py:56, 273, 380, 1087, 1401` | 50.1, 50.4, 50.5, 50.6, 51.2-51.6, 52.5, 52.9, 53.5 | Threading PNG, overrides, slot fills, golden boost |
| `component_renderer.py` | 50.4, 50.5, 51.1, 51.2, 52.4, 52.6, 52.7 | Inner-table layer, composite sub-renderer, dir=rtl, dark classes |
| `email-templates/components/*.html` | 50.4, 51.1-51.4, 52.4 | Inner-table, composite slots, tag/spec/footer markup, bannerimg class |
| `sibling_detector.py:62` | 51.2 | Reused primitive for non-repeating heterogeneous siblings |
| `visual_verify.py:92, 181` | 50.1, 52.1, 52.2, 53.1 | Multi-viewport, low-confidence VLM, repeating-group reuse |
| `correction_applicator.py:41` | 52.3 | wrap_in + add_class structural mutations |
| New `frame_rules.py` | 50.5 | Rules 7, 8, 10, 11 dispatch |
| New `repair_loop.py` | 52.1, 52.2, 52.10 | 5-stage loop orchestration + telemetry |
| `app/core/config.py:DesignSyncConfig` | 50.1, 50.5, 50.7, 52.1, 52.7, 53.3 | Feature flags per phase |
| `email-templates/golden-references/` | 53.5, 53.6 | Confidence boost wiring + 2 new tagged references |
| `app/design_sync/tests/regression_runner.py` | 53.7 | Automated 14-item checklist |

## Success Metrics

| Metric | Today (Phase 49) | Phase 50 | Phase 51 | Phase 52 | Phase 53 |
|---|---|---|---|---|---|
| Snapshot regression pass | 38/62 | 48/62 | 56/62 | 60/62 | 62/62 |
| LEGO conversion `[Rule N]` coverage | 0/11 | 4/11 (7,8,10,11) | 5/11 (+1) | 11/11 | 11/11 |
| Avg structural fidelity (ODiff) | ~85% | ~93% | ~96% | ~98% | ~99% |
| VLM calls per email | ~N (1 per section) | ~N | ~N | ~N | ~N/4 (53.1 reuse) |
| Reference designs `[Rule N]`-tagged | 1 (LEGO) | 1 | 1 | 1 | 3 |

## Phase Subtask Plans

Phase 50 subtask plans (in this directory):

- `.agents/plans/50.1-full-design-png-threading.md`
- `.agents/plans/50.2-bgcolor-boundary-classifier.md`
- `.agents/plans/50.3-wrapper-unwrap-prepass.md`
- `.agents/plans/50.4-nested-card-bg.md`
- `.agents/plans/50.5-frame-tree-rules.md`
- `.agents/plans/50.6-heading-text-align.md`
- `.agents/plans/50.7-physical-card-signals.md`

Phase 51, 52, 53 subtask **stubs** live in `.agents/plans/deferred/` (23 files: 51.1–51.6, 52.1–52.10, 53.1–53.7). Each stub captures the one-paragraph summary, approximate files, dependencies, and open questions to resolve at promotion time. Detailed plans are deferred per advisor recommendation — Phase 50 will surface decisions (composite-slot internal API shape, where Rule 1's pre-pass lives, EmailSection field naming) that reshape downstream phases. Promote a stub to a detailed plan when its phase work begins.

## Out of Scope

- AI custom component generation (`custom_component_generator.py`, Phase 47.8) — works as fallback today; not a fidelity blocker.
- VLM section classifier (`vlm_classifier.py`, Phase 41.7) — fires on UNKNOWN sections; bgcolor + wrapper unwrap (50.2 + 50.3) shrink the UNKNOWN set rather than replace it.
- New AI agents — converter improvements stay in the deterministic-engine layer; AI involvement remains via VLM verification only.
- New connectors / connectors changes — orthogonal.
- Email-tree compiler refactor — Phase 48.8's `TreeCompiler` is consumed via Phase 49.8's `tree_bridge.py`; converter changes flow through the bridge unchanged.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Wrapper-unwrap (50.3) breaks existing single-wrapper conversions | Behind `DESIGN_SYNC__WRAPPER_UNWRAP_ENABLED=true` flag; off by default for one release; existing 4 regression cases must still pass |
| Composite slot (51.1) breaks existing string-only slot consumers | New slot type is additive; existing components untouched until they declare `data-slot-composite` |
| Multi-viewport rendering (52.1) doubles Playwright time | Run mobile only when desktop fidelity ≥ 0.85 (cheap heuristic to skip mobile when desktop is already broken) |
| Rule 9 dark-mode misfiring on identity-card surfaces | 50.7 ships physical-card detection BEFORE 52.7 ships the auto-flip |
| Rule 1 (51.2) emits wrong wrapping on already-flat sections | Rule fires only when ≥2 children + non-default fill + `cornerRadius > 0` (3 conditions); single-child frames fall through |
| Token-override expansion (50.5, 50.6) fights existing 49.4 expansion | All new overrides reuse Phase 49.4's two-pass data-slot→class-fallback machinery; no new dispatch path |
| **Snapshot baselines diverge in Phase 50 even when no overrides fire** | 50.4 adds `<table class="_inner">` markup, 50.5 adds `data-node-id` to `<img>`, 50.6 emits new `text-align` overrides — all three change rendered bytes unconditionally. Reframe Phase 50 acceptance as "baselines regenerated; structural diff reviewed and approved" rather than "baselines unchanged." Run `make rendering-baselines` + manual review at end of 50.4, 50.5, 50.6 |
| **Positional construction of frozen dataclasses breaks when fields are added** | 4 of 7 Phase 50 subtasks add fields to `EmailSection` / `TextBlock` / `ImagePlaceholder` / `ButtonElement`. Per-subtask checklist: run `grep -rn "EmailSection(" app/` (and same for the other 3 dataclasses) before the first edit; convert any positional construction to keyword args |

## Out-of-band Decisions Surfaced by Phase 50

These are decisions Phase 50 work will make, which Phase 51+ inherits — list them in master so the team sees them coming:

1. **`wrapper_bg_color` vs `container_bg` vs `inner_bg`.** Phase 50.3 introduces `wrapper_bg_color`; Phase 50.4 introduces `container_bg` + `inner_bg`. Open question: are wrapper_bg_color and container_bg the same field with two names, or are they two distinct concepts (wrapper = MJML wrapper bg propagated; container = parent FRAME of nested card)? Resolve in 50.3/50.4 — likely collapse to `container_bg` with `inner_bg` distinct.
2. **Where does Rule 1's pre-pass live?** Two options: (a) `layout_analyzer.py` (tags `parent_card_id` during section construction); (b) new `frame_rules.py` (rule predicate + post-pass tagger). Phase 50.5 establishes `frame_rules.py` for Rules 7/8/10/11 — natural home for Rule 1 too in 51.2.
3. **Composite slot value type.** `string | composite[ComponentMatch]` vs `string | composite[list[SlotFill]]`. Latter is recursive (composite slots can hold composite slots). Decide in 51.1 based on Phase 50 EmailSection traversal patterns.
4. **Multi-viewport in regression suite.** 52.1 ships dual-viewport in conversion. Open: do we add mobile snapshot baselines to all 4 existing regression cases (cost: regenerate all baselines) or run mobile only as a secondary check? Resolve in 52.1.
