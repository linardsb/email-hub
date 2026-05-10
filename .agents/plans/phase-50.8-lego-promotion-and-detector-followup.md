# Phase 50.8 — LEGO Promotion + Physical-Card Detector Follow-Up

**Cluster:** D (4 deferred items, all soft / speculative).
**Closes:**
- `phase-50-stranded-templates` (LEGO + performance_reimagined + slate)
- `phase-50.7-ac-4` (LEGO real-fixture validation of `is_physical_card_surface`)
- `phase-50.7-gap-2` (`_has_logo_on_white_field` walks at most 2 levels)
- `phase-50.7-gap-3` (detection gated on `inner_bg` being set)

**Branch:** `phase/50.8-lego-promotion`.
**Depends on:** Cluster C (tenant-isolation harness) ideally landed first so
fixture promotion gets the integration regression net for free; not strictly
required.
**Estimated effort:** 1–2 sessions (one for LEGO promotion + AC #4 closure;
gap-2/gap-3 fixes either fold into the same PR or split into a follow-up
depending on whether AC #4 surfaces them).

## Problem

Phase 50.7 shipped the `is_physical_card_surface` detector
(`app/design_sync/figma/physical_card_detector.py`) gated by
`AI__DESIGN_SYNC__PHYSICAL_CARD_DETECTION_ENABLED` (or equivalent), wired into
`app/design_sync/figma/layout_analyzer.py:397-414`. The detector is
LEGO-Insiders-shaped — designed to identify physical-card surfaces (membership
cards, credit cards, gift cards) so Phase 52.7's Rule 9 dark-mode flip can skip
them without inverting the visual.

But:

1. **AC #4** is open: detector validation against a real LEGO Figma extraction
   never happened, because LEGO has no `data/debug/<N>/structure.json` —
   `email-templates/training_HTML/for_converter_engine/Lego/` carries
   `figma_link.txt` (node `2833-1869`) and `manual_component_build.html` only.
2. **Gap-2 and Gap-3** are speculative: `_has_logo_on_white_field`
   (`physical_card_detector.py:122-141`) walks one level via `_iter_self_and_children`
   (line 188–189), and the detector is gated on `inner_bg is not None`
   (`layout_analyzer.py:403`) — both can cause `is_physical=False` on cards
   that visually qualify, which means Phase 52.7's dark-flip will mis-invert
   them.
3. **Two more stranded templates** — `performance_reimagined` (no
   `manual_component_build.html` either) and `slate` (has manual build but no
   `structure.json`). They live in
   `email-templates/training_HTML/for_converter_engine/` but never ride the
   `make converter-data-regression` suite, so any Phase 51A or 52.x rule whose
   canonical example lives in one of those templates ships uncaught.

The current regression baseline (per `phase_50_summary.regression_baseline` in
`deferred-items.json`): **38 passed, 24 skipped, 0 failed (4 cases: MAAP,
Starbucks, Mammut, REFRAME).**

## Approach

Two phases, in order:

**Phase α — promotion (closes 2 of 4 entries, surfaces evidence for the other 2).**

1. Extract `structure.json` + `tokens.json` from connection ID hosting LEGO node
   `2833-1869` via `python -m app.design_sync.diagnose.extract`.
2. Add `data/debug/<N_LEGO>/` with the standard fixture set
   (`structure.json`, `tokens.json`, `expected.html`, `manifest.yaml`,
   `raw_figma.json`, `report.json`, `vlm_classifications.json`).
3. Append a manifest row to `data/debug/manifest.yaml` with
   `expectations.sections[16].is_physical_card_surface: true` (the membership
   card section).
4. Repeat for `performance_reimagined` and `slate` (2 more `data/debug/<N>/`
   dirs, with manifest rows). Their `is_physical_card_surface` expectations
   stay at the default `false` — those templates exist for layout coverage,
   not physical-card coverage.
5. Run `make converter-data-regression`. Expected outcome:
   - LEGO section #16 manifest expectation either matches (closes AC #4 + Gap-2
     + Gap-3) or fails (we have empirical evidence the detector is wrong on real
     data — proceed to Phase β).

**Phase β — detector fixes (only if Phase α LEGO regression fails).**

6. **Gap-3 (gating fix):** in `layout_analyzer.py:403`, relax the gate. Either:
   - (a) fire on any section with `corner_radius >= 16` AND a barcode/QR
     descendant, dropping the `inner_bg is not None` precondition; or
   - (b) extend `_detect_inner_bg` to populate `inner_bg` for top-level cards
     (where the section IS the card, no wrapping container). Pick (b) if the
     LEGO node's section IS the card (most likely); pick (a) otherwise.
7. **Gap-2 (walk depth fix):** in `physical_card_detector.py:122-141`, replace
   `_iter_self_and_children` (single-level walk, line 188–189) with a
   bounded recursive walker mirroring `_walk_image_descendants` (line 176–185),
   capped at 4 levels.
8. Re-run `make converter-data-regression` — LEGO must now pass with
   `is_physical=True` on section #16.

## Files

| File | Phase | Change |
|---|---|---|
| `data/debug/<N_LEGO>/...` | α | New fixture set (7 files) |
| `data/debug/<N_PERFORMANCE>/...` | α | New fixture set (7 files) |
| `data/debug/<N_SLATE>/...` | α | New fixture set (7 files) |
| `data/debug/manifest.yaml` | α | 3 new case rows |
| `app/design_sync/figma/physical_card_detector.py:122-141` | β | Recursive walker for `_has_logo_on_white_field` (gap-2) |
| `app/design_sync/figma/physical_card_detector.py:176-185` | β | Bounded recursive walker (`_walk_logo_candidates`) |
| `app/design_sync/figma/layout_analyzer.py:403` | β | Relax gate (gap-3) — pick (a) or (b) per §6 |
| `app/design_sync/tests/test_physical_card_detector.py` | β | Replace synthetic `test_lego_membership_card_pattern` with a real-fixture-driven test |

## Steps

### Phase α — promotion

#### α.1 Locate the LEGO connection

```bash
rg -n "2833-1869" .
cat email-templates/training_HTML/for_converter_engine/Lego/figma_link.txt
```

Find the connection ID that hosts this node (the design_sync tooling assigns
incremental IDs; existing fixtures use IDs 5/6/10). If no live connection
serves this node, the extract step needs a Figma API key — flag this in the PR
description if blocked.

#### α.2 Run the diagnostic extract

```bash
# For each of LEGO, performance_reimagined, slate — pick next free IDs
# (data/debug/ already has 5, 6, 10).
python -m app.design_sync.diagnose.extract --connection-id <LEGO_CONN_ID>
make snapshot-capture CASE=<NEW_ID>
```

This produces `structure.json`, `tokens.json`, and an initial `actual.html`.
Visually verify `actual.html` against `manual_component_build.html` (LEGO has
one) — copy `actual.html` → `expected.html` only after visual confirmation.

For `performance_reimagined` (no `manual_component_build.html`), use
`viaual_design.png` (the Figma export image, present in LEGO too at
`viaual_design.png`) as the visual ground truth — note in the manifest that
the `expected.html` is best-effort approximation.

#### α.3 Add manifest rows

Append to `data/debug/manifest.yaml`:

```yaml
  - id: "<N_LEGO>"
    name: "LEGO Insiders Halloween — physical-card membership pattern"
    source: "Lego/figma_link.txt"
    figma_node: "2833-1869"
    sections: <count>
    target_sections: <count>
    status: active
    design_image: true
    visual_threshold: 0.95
    expectations:
      sections:
        16:                         # zero-indexed; check the actual structure
          is_physical_card_surface: true
          physical_card_signals:
            contains:                # at least these signals must fire
              - "barcode_aspect"
              - "logo_on_white_field"
              - "distinct_corner_radius"
```

**Locate the manifest validator first** — its path is not yet confirmed:

```bash
find data/debug app/design_sync/tests -name "manifest_validator*" -o -name "regression_runner*"
rg -n "manifest.yaml" app/design_sync/tests/ data/debug/
```

The existing `app/design_sync/tests/regression_runner.py` is the most likely
consumer of the manifest. If it parses `manifest.yaml` directly via PyYAML and
hands rows to test cases, the new `expectations` field needs to be threaded
through that runner. If the manifest is parsed only for `id` / `name` /
`figma_node` / `visual_threshold` today, the `expectations` field is a
breaking-change to the runner contract — extend the runner in this PR.

If the runner rejects the `expectations` field (e.g. strict pydantic schema),
fall back to a sidecar `<N_LEGO>/expectations.json` file consumed by a new
detector-specific test that imports the JSON directly — keeps the runner
contract clean while still real-fixture-validating the detector.

Mirror for `performance_reimagined` and `slate` (no `is_physical` expectations
— they're for layout coverage).

#### α.4 Regression baseline shift

```bash
make converter-data-regression
```

Expected: 38 → **41 passed** (3 new cases). If LEGO section #16 manifest
expectation fails, that **closes Gap-2 / Gap-3 from "speculative" to
"confirmed-bug"** — this is the win condition for Phase β. Document the failure
mode in the PR description verbatim.

If LEGO passes (the detector handled the real fixture correctly): Gap-2 and
Gap-3 close as **"speculation refuted"** — close those entries with a
`closure_note` saying "LEGO real-fixture regression passed; detector handled
the case despite the speculative gaps". Keep the gaps' debugging trail for
future readers.

### Phase β — detector fixes (conditional on α failure)

#### β.1 Recursive walker (gap-2)

`physical_card_detector.py` — add a new helper near line 176:

```python
_LOGO_WALK_MAX_DEPTH = 4


def _walk_logo_candidates(node: DesignNode) -> Iterator[DesignNode]:
    """Yield every descendant up to MAX_DEPTH levels, mirroring _walk_image_descendants
    but bounded — physical-card logos sit at most a few levels under the white field.
    """
    stack: list[tuple[DesignNode, int]] = [(node, 0)]
    while stack:
        current, depth = stack.pop()
        yield current
        if depth < _LOGO_WALK_MAX_DEPTH:
            for child in current.children:
                stack.append((child, depth + 1))
```

Then replace `_iter_self_and_children(child)` in `_has_logo_on_white_field`
(line 133) with `_walk_logo_candidates(child)`. Skip yielded nodes that are
`child` itself (preserves existing behaviour).

#### β.2 Gate relaxation (gap-3) — pick option

Read `layout_analyzer.py:1457-1502` (`_detect_inner_bg`) and the LEGO
`structure.json` from Phase α. Decide:

- **Option (a) — drop the precondition.** Replace the `if inner_bg is not None
  …` gate (line 403) with:
  ```python
  if ds_cfg.physical_card_detection_enabled and (
      inner_bg is not None or _looks_like_top_level_card(node)
  ):
  ```
  where `_looks_like_top_level_card(node)` returns True iff `node` has
  `corner_radius >= _CARD_MIN_RADIUS` AND any descendant returns True from
  `_has_barcode_or_qr_descendant`.
- **Option (b) — extend `_detect_inner_bg` to populate for top-level cards.**
  In `layout_analyzer.py:1457-1502`, if `container_bg is None` and `node`
  itself has `corner_radius >= _CARD_MIN_RADIUS` and a fill, return
  `(node.fill, node.corner_radius)` instead of None. This is more invasive but
  keeps the detector's signal logic untouched.

Pick whichever is shorter against the actual LEGO `structure.json` — the
diagnostic runner output from Phase α will show which path produces correct
classification.

#### β.3 Real-fixture detector test

Replace `test_lego_membership_card_pattern` (synthetic) in
`app/design_sync/tests/test_physical_card_detector.py` with:

```python
def test_lego_section_16_classified_as_physical(
    lego_structure: DesignFileStructure,  # fixture loaded from data/debug/<N_LEGO>/
) -> None:
    section = lego_structure.sections[16]
    detection = detect_physical_card_surface(
        section, sibling_radii=None, container_bg=None
    )
    assert detection.is_physical is True
    assert "barcode_aspect" in detection.signals
    assert "logo_on_white_field" in detection.signals
```

Add the `lego_structure` fixture to a shared `conftest.py` under
`app/design_sync/tests/` so other tests can reuse it.

#### β.4 Verify

```bash
make types
make lint
make test app/design_sync/figma/
make converter-data-regression           # 41 passing, LEGO §16 = is_physical
make golden-conformance
```

### Phase α/β shared — PR checklist

- [ ] `.agents/deferred-items.json` — close all 4 entries:
      - `phase-50.7-ac-4` → `closed`, `closure_note: "LEGO promoted to data/debug/<N>; manifest expectation green"`.
      - `phase-50-stranded-templates` → `closed`, `closure_note: "All 3 promoted to data/debug/<N>"`.
      - `phase-50.7-gap-2` → either `closed` (refuted by α) or `closed`
        (fixed by β); pick `closure_note` accordingly.
      - `phase-50.7-gap-3` → same shape as gap-2.
- [ ] Update `phase_50_summary.regression_baseline` in `deferred-items.json`
      to reflect the new `41 passed` count.
- [ ] `.agents/plans/deferred-items-tracker.md` — strike Cluster D.
- [ ] `make check-full` green; `make converter-data-regression` shows 3 new
      passing cases.
- [ ] PR description copies the visual diff for LEGO `actual.html` vs.
      `expected.html` (or links to the reviewer screenshots).

## Risk

- **LEGO node access.** If no live Figma connection serves node `2833-1869`,
  `diagnose.extract` fails. Resolution: either re-import LEGO via the design_sync
  pipeline (creates a connection), or hand-curate `structure.json` from the
  `manual_component_build.html`. Hand-curation is acceptable but loses the
  "real-fixture" property — note explicitly in the PR.
- **Manifest schema changes.** §α.3 may need to extend the manifest validator
  for the `expectations` field. If that change ripples into the `make
  golden-conformance` gate, scope it as a separate PR landing first.
- **Phase α LEGO passes.** Reduces this to a 3-template promotion plus AC #4
  closure — half the work. If that happens, mark gap-2/gap-3 as
  "speculation refuted" and don't touch detector code.

## Out of scope

- Phase 51A composite-slot work (LEGO's footer membership card). Those entries
  in the deferred ledger anticipate it but it's a separate phase.
- Phase 52.7 dark-mode flip (Rule 9). The closure note for gap-2/gap-3 should
  mention that the detector is now real-fixture-validated, so 52.7 can rely on
  it. The actual Rule 9 wiring is its own phase.
