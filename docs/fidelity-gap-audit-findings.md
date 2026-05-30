# Fidelity-Gap Audit — Why Figma→Email Is Not ~99% Close to Design

**Date:** 2026-05-30
**Method:** 5-stage parallel audit (Figma sync · conversion · assembly · build · fidelity-measurement) with adversarial per-finding verification. 29 agents, ~1.93M tokens. The synthesis agent crashed on a structured-output error; this report is reconstructed from the 4 completed stage-audits + 21 verified verdicts (14 confirmed in-production root causes). Findings below were each re-checked against code at the cited `file:line`.

> **⚠️ RE-AUDIT UPDATE (2026-05-30, workflow `wf_fa48d17b-6ea`, 23 agents).** A second forensic pass verified every root cause below at `file:line` and found **two this audit missed** plus **two it got wrong**. See the **"Re-audit verification & corrections"** appendix at the end. Headline: the single highest-ROI defect is **not** listed below — a serializer bridge (`email_design_document.py:695/743`) does `getattr(t,"text_color",None)` against a field named `color`, so **every text color is nulled before the converter runs**, and the same reader drops `text_align`/`url`/`border_radius`/`corner_radius_spec`/stroke on every path. That bridge — not "lossy ingest" — is why the shipped Phase 49/50 fidelity logic is **built, enabled-by-default, and inert**. The fix is sequenced as **Phase 52 (foundation) + Phase 53 (engine)** in `TODO.md`; full plan in `.agents/plans/52-converter-foundation.md`.

---

## Executive answer

The "~97% → ~99% fidelity ladder" in the docs is **aspirational, not operative**. Two independent facts make it so:

1. **The corrective machinery that the docs credit for the lift never runs on the default production path.** The VLM verify→correct loop is triple-disabled; the high-fidelity recursive renderer is never invoked; the design-system/assembler corrections are off-path.
2. **The path that *does* ship is a fixed component-seed converter** that slots content into ~150 pre-authored table templates and patches only a tiny allowlist of CSS properties — structurally unable to reproduce arbitrary Figma geometry, color, type, or effects.

And the number that's supposed to *prove* 97/99% is a **color-blind grayscale SSIM that is off by default**, non-fatal, stored-only, and never fed back into correction. So the system both **can't produce** ~99% on the default path and **can't measure** whether it did.

Net: the realistic ceiling of the shipping path is well below the claimed figure, and the gap to the design is dominated by (a) lossy Figma ingest and (b) the fixed-seed converter — not by the build/assembly stages, which are off-path.

---

## The production path (verified ground truth)

```
Figma → repo snapshot.document_json → EmailDesignDocument (LOSSY flatten)
      → converter.convert_document   [default output_format="html"]   ← SHIPS THIS
      → import_service passthrough (import_service.py:356-385) wraps it as
        ScaffolderResponse(model="design-converter")  ← Scaffolder/assembler BYPASSED
      → _inject_asset_urls / _fix_orphaned_footer / _sanitize_email_html
      → stored as Template html_source  ← export serves this verbatim to the ESP
```

- Default `output_format = "html"` (`schemas.py:634-635`) → `convert_document` (component path), **not** `convert_document_mjml`.
- `convert_document` explicitly discards design screenshots: `_ = design_screenshots` (`converter_service.py:284-286`).
- Scored artifact == shipped artifact at the template layer (`import_service.py:457-460`), but scoring is off by default (below).
- The high-fidelity recursive `DesignNode` renderer (`_build_props_map_from_nodes`, `converter_service.py:1088`) receives `_frames=[]` on the document path (`:315`) and **never runs in production**.

---

## Ranked root causes (confirmed, in production path)

### 1 — Fixed component-seed converter is the shipping engine *(leverage: high; structural)*
`component-snap-fixed-seed-model`, `gradients-shadows-dropped`
The default path is a vertical stack of ~150 pre-built table templates. The matcher picks *which* seed per section; slots inject **text/image content only** (`component_renderer.py:521` preserves the seed's opening tag + style). The seed's structure, paddings, line-heights, font-weight, and column proportions are authored once and cannot represent arbitrary Figma geometry. This is a hard ceiling independent of any flag.

### 2 — Token overrides are a tiny allowlist, read first-element-only *(leverage: high)*
`first-text-only-token-override`, `no-fontweight-lineheight-letterspacing-override`, `column-layout-hardcodes-arial-bold`
`_build_token_overrides` loops `for text in section.texts` and **`break`s after the first heading and first body** for font-family (`component_matcher.py:1485-1493`), font-size (`:1496-1504`), color (`:1507-1515`), text-align (`:1474/1480`). Only **bg-color, text color, font-family, font-size, padding, text-align, CTA color/radius** are ever patched. **font-weight, line-height, letter-spacing, gradients, shadows, opacity, per-element padding are never emitted** → they always equal seed defaults. Multi-style sections collapse to one style; surplus content beyond a seed's slots is dropped. Column layouts hardcode Arial/bold (`_build_column_fills`).

### 3 — The ~97% VLM verify→correct loop is triple-dead in production *(leverage: high)*
`vlm-verify-loop-off-and-not-on-this-path`, `vlm-verify-loop-doubly-disabled-on-default-path`
Three independent, each-sufficient blocks:
- `vlm_verify_enabled = False` default (`config/design_sync.py:58`).
- Loop is only wired into `_apply_verification`, called solely from `convert_document_mjml` — the **non-default** path.
- `convert_document` discards `design_screenshots`; even the MJML path is never passed per-section screenshots by `import_service` (`:220-225, 282-288`), so `_apply_verification` short-circuits on `not design_screenshots` (`converter_service.py:396`).

→ Zero automatic corrections ever reach shipped HTML. The documented "render→compare→correct until fidelity ≥ 0.97" never executes.

### 4 — Figma ingest is lossy *before conversion runs* (dominant upstream ceiling) *(leverage: high; structural)*
`EmailDesignDocument` is a flattened section model (`DocumentSection/Text/Image/Button`) that **every** path serializes to and reloads from the snapshot. It has **no fields** for effects/shadows, blend modes, per-node gradients, per-corner radii, opacity, `text_transform`/`text_decoration`/`style_runs`/hyperlink, or constraints — unrecoverable downstream regardless of converter quality. Specific destructive losses:
- **Effects never read from the API:** `node.effects` (drop/inner shadow, layer/background blur) and `blendMode` are never parsed (`_parse_visual_props`, `figma/service.py:554-629`). Elevation and overlay-blend looks can never be reproduced. (`effects-shadows-blur-never-extracted`)
- **Opacity composited against hard-coded `#FFFFFF`:** `_rgba_to_hex_with_opacity` (`figma/service.py:265-291`) folds alpha into a solid hex against white — any translucent layer over a non-white backdrop is the wrong color before conversion. (`node-opacity-composited-against-white`)
- **Gradients dropped / un-reattachable:** `_parse_visual_props` `continue`s on any non-SOLID top fill (`figma/service.py:600`); gradients survive only as **global, node-less** tokens (`ExtractedGradient` has no `node_id`), and `DocumentSection` stores a single `background_color` string — so a gradient can't be put back on its section. (`per-node-gradient-fill-dropped`)
- **Per-corner radii discarded**, **text-transform/decoration/style-runs dropped at write**, **decorative VECTOR nodes silently dropped** (inline icons, dividers, vector logomarks vanish). (`per-corner-radius-discarded`, `text-transform-decoration-styleruns-dropped-at-write`, `vector-decorative-content-dropped`)
- **`text_align` lost on read** — two independent breaks in the chain, so even a stored value doesn't reach output. (`text-align-not-passed-on-read`)

### 5 — The fidelity metric can't see the failures, and is off by default *(leverage: high for trust; it gates nothing)*
`fidelity-metric-color-blind`
`visual_scorer.score_fidelity` loads both images via `.convert("L")` (`:54`) and applies Gaussian blur σ=1.0 (`:142-143`) before SSIM:
- **Color-blind:** a wrong brand color at matching luminance scores ~1.0. The single most common Figma→email divergence is invisible.
- **Blur** smooths away the exact sub-pixel/few-px spacing & alignment errors the converter is known to introduce.
- **Off by default:** requires both `fidelity_enabled=True` (`config/design_sync.py`, default False) **and** request `score_fidelity=True` (`schemas.py:638`, default False).
- **Non-fatal, stored-only, no feedback**, and **per-section mean (not min)** so one badly-diverged section is masked.

→ The "97%/99%" figures are not computed on the shipped artifact in default config, and even when computed cannot detect color/gradient/shadow/spacing divergence — the very things that dominate the gap.

---

## Suspicions investigated and **debunked** (not the cause)

- **TemplateAssembler / scaffolder / golden-template snapping** — OFF the default path; runs only when the converter is disabled or returns 0 sections (rare for real multi-section designs). Not a default-path contributor.
- **Euclidean nearest-RGB "brand sweep" corrupting intentional colors** — real, but gated to `source=='design_system'` (`assembler.py:119`); never fires on the Figma-import path (`source=='llm_generated'`). Only affects the separate brand-identity flow.
- **Maizzle / PostCSS / Lightning-CSS / Juice build stripping design CSS** — that pipeline does **not** run on the default import→export path (only `output_format=='mjml'`); export serves stored HTML verbatim (`connectors/sync_service.py:319-332/422-436`). Zero effect on the default shipped bytes.
- **Sanitizer (`margin→padding`, `<br><br>` unwrap, div→table)** shifts designed spacing — confirmed but low impact.

---

## Measurement-trust verdict

**Do not trust any reported "97%/99%."** In default config no fidelity number is produced for the shipped template; when produced it is grayscale+blur SSIM that structurally cannot measure color, gradient, opacity, shadow, or sub-pixel spacing — and it gates nothing (no ship-blocking on low score). There is also **no metric anywhere** that compares the captured `EmailDesignDocument` against the raw Figma tree, so the ingest-stage capture loss (the biggest ceiling) is entirely unmeasured by the system itself.

---

## What it would actually take (qualitative — no invented percentages)

Ordered by leverage on the **default** path:

1. **Make the corrective loop real on the shipping path:** pass per-section `design_screenshots` into `convert_document`, enable `vlm_verify_enabled`, and wire `_apply_verification` into the `output_format="html"` path — or stop crediting it in the docs.
2. **Replace color-blind SSIM with a color-aware perceptual metric** (e.g. ΔE/LAB or a VLM judge), score on the post-export artifact, take per-section **min** not mean, and make it gate shipping. Until then the fidelity number is decorative.
3. **Widen the converter override surface** beyond the first-element allowlist: emit font-weight, line-height, letter-spacing, per-element padding; read all text runs, not just the first heading/body.
4. **Stop the destructive ingest losses:** read `node.effects`/`blendMode`, preserve rgba/opacity instead of compositing against white, attach gradients to their node, keep per-corner radii and decorative vectors. These are upstream of everything; nothing downstream can recover them.
5. **Accept the structural floor honestly:** Outlook/Word tops out ~95%; drop shadows, gradients, SVG, blend modes are not reproducible in email. A true ~99% is only realistic for modern clients on designs that avoid those — and only after 1–4.

---

## Provenance / re-run

- Workflow run id: `wf_2a91f121-c6f` (resumable; completed agents are cached).
- Raw salvaged payloads: `/tmp/fidelity_salvage.json` (4 audits + 21 verdicts).
- The 5th finder (dedicated fidelity-measurement) crashed before emitting structured output; its mandate is fully covered by the measurement findings in the other four audits above.

---

## Re-audit verification & corrections (2026-05-30, `wf_fa48d17b-6ea`)

An 11-finder + adversarial-verifier + synthesis workflow re-checked every claim above against code. Result: the spine is correct, but the **location/mechanism** of the dominant loss was wrong, and the two highest-ROI defects were absent.

### Two root causes this audit missed

- **RC-A — `text_color` is *always* `None` (1-line bug, two sites).** `DocumentText` stores color as `color` (`email_design_document.py:414`) and it round-trips JSON perfectly, but the reader bridge rebuilds `TextBlock` with `text_color=getattr(t,"text_color",None)` (`:695`, `:743`). `DocumentText` has no `text_color` attribute, so the default fires every time — and the override builder *does* emit a color override (`component_matcher.py:1507-1515`), so the reader nulls a field the converter actively consumes. Fix: `→ t.color`.
- **RC-B — the reader bridge `to_email_section` strips fidelity fields on *every* production path** (`email_design_document.py:685-718`, `733-766`). `text_align` is written (`:816`) but never read back; button `url`/`border_radius` round-trip JSON (`:492-493`) but are dropped at `:709-718`; `corner_radius_spec`, button stroke, `text_transform`/`decoration`, `style_runs`, `layout_align`, and the entire Phase-50 section layer have no carry-back. **This is the true reason Phase 50 is shipped + default-True + inert** — its overrides read fields that are always `None`.

### Corrections to claims above (do not re-litigate)

1. **The high-fidelity recursive renderer does not "just need wiring" — it was deleted.** Commit `d9132c7c` removed `app/design_sync/converter.py` (`_convert_recursive`, `node_to_email_html`). The `_build_props_map_from_nodes`/`_frames` remnants (`converter_service.py:1088`) are orphaned scaffolding with zero callers. Recover via `git show d9132c7c^:app/design_sync/converter.py` (1625 LOC) — but even restored it was the **middle** tier (Auto-Layout/typography/gradient), never effects/geometry/pixel-faithful.
2. **Root cause #4's "lossy ingest" framing mislocates several losses.** `text_align`, per-corner radii, `text_transform`/`decoration`, `style_runs` are **correctly parsed** and reach the in-memory `TextBlock`/`ButtonElement` — then dropped at the **serializer boundary** (RC-B), not at the Figma read. Fixing the parser would be wasted effort. Use this three-way taxonomy: **never-parsed** (effects, blendMode, scaleMode/imageTransform, rotation, AUTO/% line-height, z-order/overlap, non-button strokes) / **parsed-then-dropped-at-bridge** (text_color, text_align, url, border_radius, button stroke, corner_radius_spec, Phase-50 section layer) / **captured-but-never-emitted-as-CSS** (font-weight, line-height, letter-spacing, text-transform, text-decoration).
3. **State-of-system: not "frozen Phase-49".** Phase 50 has **shipped and is enabled-by-default** (`config/design_sync.py:92,97,102,109,116` all `True`) — it is *built + enabled + inert* because of RC-B, not unbuilt.
4. **The metric is *dimensionally invalid* by default, not merely lenient.** Beyond color-blind/blur/mean: Figma exports at 2× (`fidelity_figma_scale=2.0`) while the HTML screenshot renders at DPR 1; `_pad_to_match` white-pads instead of resampling; `_capture_figma_composite` stitches sections gap-free while `_compute_design_height` spans gaps (cumulative y-drift); and only `gmail_web` is ever rendered (`fidelity_service.py:33,168`) — the Outlook floor is never scored. And it **never runs** (fixtures gitignored, `fidelity_enabled=False`).
5. **Narrow one categorical claim.** "convert_document discards design_screenshots / never receives the global PNG" is overstated by one path: the legacy fallback (`import_service.py:290-296`) *does* pass `global_design_image`. The conclusion (the verify→correct loop never runs) still holds.
6. **"65 passed" proves byte-stability, not fidelity.** `compute_quality_score` measures the matcher's own self-reported confidence (decoupled from design); the richest color fixture (`reframe`) is `reference_only`; real fixtures are gitignored so CI asserts vacuous substrings.

### Debunked finder claims (kept so they are not re-raised)

- Tiny sub-window sections scoring a perfect 1.0 SSIM that inflates the mean — **unreachable** (the <8px guard at `visual_scorer.py:161` drops them first). The *silent-drop* gap is real and separate.
- `converter-data-regression`/`snapshot-test` as orphan Makefile targets — **refuted on cause**: the test files run under `make test`; the real cause of vacuous coverage is gitignored fixtures.
- "DocumentText lacks line-height/letter-spacing" — **strawman**: those fields exist and round-trip (`:411-415`); the defect is never-emitted-as-CSS, not absent fields.

### New gaps beyond the original audit (verified)

Image crop/fit (`scaleMode`/`imageTransform`) never read; node rotation dropped; z-order/overlap flattened; AUTO/% line-height collapses to `None`; non-button strokes lost at the section write; decorative standalone VECTOR nodes dropped with no model class; `_fix_text_contrast` mis-scopes recolors over nested tables (forces light cells to invisible white) on every shipped artifact; `email-design-document-v1.json` `additionalProperties:false` already forbids fields `to_json` emits; per-section composite scale drifts when inter-section gaps exist; the metric renders gmail-only so the Outlook floor is unscored.

### Reconciliation vs `.agents/plans/50-converter-fidelity-master.md`

Promoting Rules 1–11 + composite slots **decorates** the confirmed ceiling rather than removing it, and is itself **neutered by RC-B** (the bridge nulls the inputs those rules consume). No phase in the master plan addresses RC-B, RC-E (ingest effects/gradient/opacity), or RC-F (the broken metric), and its 85→99% Success-Metrics ladder is computed by the very metric this audit invalidates — treat it as an unfalsifiable projection. The operative roadmap is now **Phase 52 (foundation) + Phase 53 (engine)** in `TODO.md`; the master plan's 50–53 labels are superseded.
