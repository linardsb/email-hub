# Feature: CE-6 read auto-layout sizing fields (+ structure.json re-sync)

The following plan should be complete, but validate documentation and codebase patterns and task sanity before
you start implementing. Pay special attention to naming of existing utils, types and models.

## Feature Description

The Figma parser ignores Figma's auto-layout child sizing (`layoutSizingHorizontal/Vertical`, `layoutGrow`,
`layoutAlign`, `layoutPositioning`, `layoutWrap`, `minWidth/maxWidth`). This ticket declares them on the raw
type, parses them onto `DesignNode`, round-trips them through both node serializers, records horizontal sizing on
the analysed `ColumnGroup`/`EmailSection`, and re-syncs every committed `data/debug/*/structure.json` so the
fields reach CI. Read-and-record only: no converter output changes.

## User Story

As the converter (and the CE-16 / CE-19 work built on it)
I want every design node to carry Figma's FIXED / FILL / HUG sizing
So that column widths and the DSL compiler can follow the designer's intent instead of guessing from pixels.

## Problem Statement

`DesignNode` (`app/design_sync/protocol.py:110`) has no sizing field and `RawFigmaNode`
(`app/design_sync/figma/raw_types.py:88`) declares none, so CE-16 (#434) and the DSL spike CE-19 (#437, spec M1)
have no input. The committed `structure.json` files carry no sizing, so CI cannot see it either. Separately, the
DB-cache serializer (`app/design_sync/services/_serialization.py`) already drops `scale_mode`, `rotation` and
`effects_summary` (observed: no reference to them in that file), and its parity test passes only because its test
node leaves them at default.

## Solution Statement

Extend `_LayoutProps`/`_parse_layout_props` (`figma/service.py:364-449`) with the eight fields, read **outside**
the frame-type / `layoutMode` gates (they are child properties) except `layoutWrap` (container-only, inside the
gate). Add the fields to `DesignNode`, `diagnose/report.py:_node_from_dict` and the cache pair; harden the cache
parity test to set every field non-default, which forces the three missing 53.3 fields in too (user decision
2026-10-05). Add `sizing_horizontal` to `ColumnGroup` and `EmailSection`. Re-sync all seven cases with
`scripts/resync-case-structure.py`, empty `_KNOWN_LAGGING_KEYS`, and pin the result with CI-visible invariants
(every parsed node has sizing; root width == `container_width`).

## Out of Scope / Non-Goals

- Not changing: column widths, `container_width` derivation (`email_design_document.py:1597-1603`), any template.
  Width use is CE-16 (#434) and CE-17 (#435).
- Not included: `DocumentSection` / document JSON fields (CE-26 #466 owns schema v2).
- Not included: Penpot sizing (`penpot/service.py:475`) and mock provider; they keep defaults.
- Not included: `minHeight/maxHeight`, `counterAxisAlignContent` (not in the ticket's list).
- Not closing: `phase-53g-band-item-spacing-defaults-vs-wrapper-padding` (behaviour change, CE-16).
- Not checking the brief's P2 table: it is not in the repo. Counts are re-derived and reported as observed; the one
  in-repo figure (DSL spec `docs/architecture/dsl-compiler.md:118`, case 5 = 72 FILL / 22 FIXED / 28 HUG) is
  cross-checked.

## Feature Metadata

**Feature Type**: Enhancement (ingest) + fixture refresh
**Estimated Complexity**: Medium (small code, wide fixture diff, two hook frictions)
**Primary Systems Affected**: `app/design_sync/figma/`, `protocol.py`, `diagnose/report.py`, `services/_serialization.py`, `figma/layout_analyzer.py`, `data/debug/*/structure.json`, `.secrets.baseline`
**Dependencies**: none new

## Related Work

**Implements**: #424 (CE-6) · **Epic**: #439, `.agents/plans/converter-epic-slices.md:123-131`; DSL spec `docs/architecture/dsl-compiler.md` (M1 `:118`, `:199`; N5 `:238`)

**Back-references**:
- `.agents/plans/ce-3-corpus-refresh.md` - Why: wrote `scripts/resync-case-structure.py`, `TestFixtureFreshness`, and hit the same detect-secrets and large-file frictions (E4/E5, report deviation 3).
- `.agents/plans/dsl-epic-slices.md:13,35` - Why: G0 gate lists "#424 with re-sync" as spike prerequisite.

**Forward-references**: CE-16 (#434) reads `sizing_horizontal`; CE-19 (#437) reads `DesignNode.layout_sizing_horizontal`.

## Deferred Items Touching This Plan

| id | match (phase / code_ref) | decision | why |
|----|--------------------------|----------|-----|
| `ce-3-fixture-schema-lag-6-10` | `test_converter_data_regression.py` `_KNOWN_LAGGING_KEYS`, `resync-case-structure.py` | **close** (Task 11) | Re-sync of 6-10 empties the map; baselines audited byte-identical (observed dry run, below), gate untouched |
| `phase-53g-band-item-spacing-defaults-vs-wrapper-padding` | `item_spacing` (epic table: CE-6/CE-16) | carry forward | Fix changes output; CE-16 owns it |
| `phase-53g-g7-per-side-stroke-capture` | `figma/service.py` | avoid | `individualStrokeWeights` is a separate field; not touched |
| `phase-53-d3-mammut-below-candidate-undercount` | `layout_analyzer.py` | avoid | Segmentation; no candidate logic changes |
| `phase-53f-decorative-image-flag` | `layout_analyzer.py` | avoid | Image classification untouched |
| `phase-53g-g11-contentgroup-column-divider-gap` | `layout_analyzer.py` | avoid | Divider logic untouched |
| `ce-10-cta-icon-not-rendered`, `ce-10-unnamed-button-icon-not-exported`, `ce-10-large-styled-icon-wrapper-exports-bare-glyph` | `layout_analyzer.py` | avoid | Button/icon extraction untouched |
| `phase-53-a2-advisory-section-gate` | `test_converter_data_regression.py` | avoid | Ladder must stay unchanged |
| `phase-53.7-typography-maxitems-cap` | `email_design_document.py` | avoid | File read only, not edited |
| `ce-9-peel-row-fixed-width-wrap` | `container_width` | carry forward | Width behaviour, CE-16/17 |
| `ce-2-tree-path-drops-footer-text` | `structure.json` | avoid | Tree path (flag off) not exercised |

---

## Planning evidence (observed 2026-10-05, tree == `origin/main` 56598f36, scratch outputs under the session scratchpad)

| ID | Check | Result |
|----|-------|--------|
| E1 | `resync-case-structure.py <c> --out <tmp>` vs committed, all 7 cases | case 5 identical; 6-10 lack 4 keys (`rotation`, `line_height_relative`, `effects_summary`, `scale_mode`, all null except `scale_mode`); `image_ref` null → hash on 11/23/10/13/17 nodes (6/7/8/9/10) and 16 (reframe) |
| E2 | Non-null `scale_mode` values after re-sync | all `FILL` (12/11/23/10/13/17/16), so the 53.3c frame-export branch (`layout_analyzer.py:1521`) cannot fire |
| E3 | Convert re-synced structures, `DESIGN_SYNC__SECTION_CACHE_ENABLED=false`, one fresh process per case, vs committed `expected.html` | bytes equal for 5/6/7/9/10/reframe; case 8 equal after `_normalize_html` only, and the same holds for the **unchanged** case-8 structure (pre-existing c8 whitespace churn). Section counts 13/9/8/10/8/12/11 unchanged |
| E4 | Sizing field counts in `raw_figma.json` (table below) | `layoutPositioning`, `minWidth`, `maxWidth` appear 0 times in the corpus |
| E5 | Root frame width vs `container_width` (`EmailDesignDocument.from_legacy`) | 600/640/600/600/640/600/640 for 5/6/7/8/9/10/reframe; equal in every case; root `layoutSizingHorizontal` = FIXED in every case |
| E6 | Committed parser test fixtures `figma/tests/fixtures/*.json` | 0 `layoutSizingHorizontal` occurrences: no free CI invariant there |
| E7 | `fidelity_baseline.json` / `fidelity_gate.py` | no input hash of `structure.json`; gate reads converter output only |
| E8 | Exact re-synced dump size (re-parse + the 8 keys filled from each node's real raw values, `json.dumps(indent=2)`) | case 7 = 525,405 B, over the 512,000 B `--maxkb=500` cap; others 169,809-377,626 B. **The cap does not apply:** `check-added-large-files` without `--enforce-all` filters to `git diff --staged --diff-filter=A` (`pre_commit_hooks/check_added_large_files.py:45-46`, v5.0.0), and these files are modified, not added. Throwaway worktree on `origin/main` with all 7 simulated files staged: hook `Passed` |
| E9 | detect-secrets on the same staged files (throwaway worktree) | hook fails on the new `image_ref` hashes. `detect-secrets scan --baseline .secrets.baseline` (v1.5.0, allowed in `.claude/settings.local.json:70`; `.secrets.baseline` does not match the `pre_tool_use.py:52` secret-path pattern) adds 15/11/16/10/13/14 entries for 10/6/7/8/9/reframe = 79, re-numbers case 5's existing 7, changes `generated_at`, touches no other file's entries. Hook then `Passed`. The Claude-level commit hook `.claude/hooks/pre-commit-security.sh` matches only prefixed credential patterns (AKIA, sk-, ghp_, JWT, ...): 0 matches over all 7 simulated fixtures and the baseline, and it exempts `.secrets.baseline` by name (`:38-40`) |
| E10 | Live path: `serialize_node` → JSON → `_node_from_dict` (the production read, `services/conversion_service.py:72-79`) vs corpus load, per case | only `scale_mode` differs (12/11/23/10/13/17/16 nodes lost); converted HTML equal in all 7 (all values `FILL`). On the **committed** fixtures only cases 5 (12) and reframe (16) differ; 6-10 carry no `scale_mode` key, so both sides are `None`. Consumers of the 3 dropped fields: `scale_mode` → `_crop_export_id` (`layout_analyzer.py:1513`, used ungated at `:1640`, `:1655`, `:1694`); `effects_summary` → `:486`, `:606`, `:1688`, `:1888`, `converter_service.py:359` (ungated); `rotation` → `:1787`, reached only when `frame_export_fallback_enabled` (default `False`, `app/core/config/design_sync.py:133`) |
| E11 | Pattern spike: `raw_h if raw_h in _SIZING_VALUES else None` with `layoutSizingHorizontal: str` and `minWidth: Any` on `RawFigmaNode` | pyright 0 errors, mypy clean (throwaway worktree, discarded) |
| E12 | Existing all-fields sentinel | `test_diagnose_roundtrip.py:40-83` `_sentinel_node()` sets every field today but nothing asserts it stays complete; `test_serialization_roundtrip.py:112` uses a partial node |

**Sizing counts per case (observed, E4; parsed node count excludes the synthetic page node):**

| case | nodes | auto-layout frames | H: FILL/FIXED/HUG | V: HUG/FIXED/FILL | `layoutGrow` 1/0 | `layoutAlign` STRETCH/INHERIT | `layoutWrap` NO_WRAP |
|---|---|---|---|---|---|---|---|
| 5 | 122 | 86 | 72/22/28 | 107/15/0 | 30/91 | 42/79 | 86 |
| 6 | 67 | 45 | 37/21/9 | 56/11/0 | 13/53 | 24/42 | 45 |
| 7 | 204 | 145 | 142/43/19 | 154/34/16 | 55/148 | 103/100 | 145 |
| 8 | 111 | 76 | 85/17/9 | 100/11/0 | 43/67 | 42/68 | 76 |
| 9 | 98 | 71 | 59/28/11 | 75/19/4 | 25/72 | 38/59 | 71 |
| 10 | 157 | 109 | 123/24/10 | 134/23/0 | 58/98 | 65/91 | 109 |
| reframe | 132 | 93 | 90/29/13 | 113/19/0 | 41/90 | 49/82 | 93 |

Derived invariants from this table: H counts sum to node count in every case (e.g. 72+22+28 = 122), V likewise,
and `layoutWrap` count = auto-layout frame count. Case 5's H split matches the DSL spec figure. `layoutGrow` sums
are one short of nodes (root carries none).

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `app/design_sync/figma/raw_types.py:88-139` - `RawFigmaNode`; layout block `:110-118`. Docstring `:89-95` explains `Any` typing for isinstance-guarded fields.
- `app/design_sync/figma/service.py:355-449` - `_LayoutProps` and `_parse_layout_props`; frame gate `:399-415`; `_float_or_none` `:311`.
- `app/design_sync/figma/service.py:1594-1680` - `_parse_node`, `DesignNode(...)` build `:1635-1679`.
- `app/design_sync/protocol.py:110-169` - `DesignNode`; append new fields after `effects_summary` `:169`.
- `app/design_sync/diagnose/report.py:86-141` - `_node_from_dict` explicit field map (the dumper `:65-84` is generic).
- `app/design_sync/services/_serialization.py:26-97` (`serialize_node`, compact: omit None/default) and `:170-212` (`cached_dict_to_node`).
- `app/design_sync/tests/test_serialization_roundtrip.py:20-125` - `_outlined_cta_node`, `_roundtrip`, `test_full_field_parity_with_protocol` `:112`.
- `app/design_sync/figma/layout_analyzer.py:156-178` (`ColumnGroup`), `:201-281` (`EmailSection`), constructors `:461`, `:569` (sections), `:1349`, `:1376` (columns); `overall_width` `:393-397`.
- `app/design_sync/email_design_document.py:1597-1603` - `container_width` derivation (read only).
- `app/design_sync/tests/test_converter_data_regression.py:481-532` - `_LAG_6_10`, `_KNOWN_LAGGING_KEYS`, `_node_key_sets`, `TestFixtureFreshness`; ladder `:264-300`.
- `app/design_sync/figma/tests/test_parse_props.py:20-45` - helper-level unit test pattern (dict literal typed `RawFigmaNode`).
- `scripts/resync-case-structure.py` - offline re-parse of `raw_figma.json` (gitignored; present locally for all 7 cases).
- `.pre-commit-config.yaml:21-22` (large-file cap, added files only, E8) and `:67-71` (detect-secrets with `.secrets.baseline`, E9). Read only; not edited.
- `.agents/deferred-items.json` entry `ce-3-fixture-schema-lag-6-10` (~`:1353`).

### New Files to Create

- `.claude/reports/ce-6-sizing-fields-report.md` - counts table re-derived on the branch head, byte-identity evidence, A3/gate results.

No new source modules. Tests go into existing files.

### Relevant Documentation

- [Figma REST API, Node types → FrameNode / layout properties](https://www.figma.com/developers/api#frame-props) - `layoutSizingHorizontal` (FIXED/HUG/FILL), `layoutGrow` (0/1), `layoutAlign` (INHERIT/STRETCH, legacy MIN/CENTER/MAX), `layoutPositioning` (AUTO/ABSOLUTE), `layoutWrap` (NO_WRAP/WRAP), `minWidth/maxWidth` (number or null). Why: allowed value sets for validation. Fields are omitted when default, which is why E4 shows zero `layoutPositioning`/`minWidth`.
- `docs/architecture/dsl-compiler.md:95-118` - sizing contract the spike will consume.
- `.claude/skills/converter-fix/SKILL.md` steps 0-6 and `references/baselines-and-gates.md` § Regen-and-audit.

### Patterns to Follow

- **String enums from Figma**: `layout_mode` stores the raw upper-case string (`service.py:408`); axis align maps to lower-case (`:421`). Sizing keeps raw upper-case (the DSL spec contract `FIXED | FILL | HUG`), validated against a module-level `frozenset`; unknown value → `None`. No isinstance needed when the TypedDict field is `str`; pyright strict accepts `x if x in _SET else None`.
- **Numbers**: `_float_or_none(node_data.get(...))` (`service.py:311`).
- **Compact cache**: `if node.x is not None: d["x"] = node.x` (`_serialization.py:41-97`).
- **Field comments**: one-line provenance comment per new `DesignNode` field group, like `:156-169` ("CE-6 (#424) — ...").
- **Logging**: none needed (pure parse). **Errors**: none (absent → None).

---

## IMPLEMENTATION PLAN

### Phase 0: Isolated worktree
Work in a new worktree, not the main checkout. The main checkout carries someone's uncommitted
`.claude/skills/*` and `skill-versions.yaml` edits on `fix/ce-7-review-f1`, which must not be stashed, moved
or committed.

### Phase 1: Scaffold + RED tests (Tasks 1b-4)
Parse unit tests, cache parity hardening, fixture invariants. All must fail on the assertion before Phase 2.

### Phase 2: Ingest (Tasks 6-8)
raw type → `_LayoutProps` → `DesignNode` → both serializers → analysed nodes.

### Phase 3: Fixture re-sync (Tasks 9-12)
**Depends on:** Phase 2. Re-sync, hook frictions, freshness map, ledger.

### Phase 4: Gates and report (Tasks 13-15)

---

## STEP-BY-STEP TASKS

### Task 1 — SETUP worktree
- **IMPLEMENT** (from the main checkout, `MAIN=/Users/Berzins/Desktop/email-hub`, `WT=/Users/Berzins/Desktop/eh-ce6`):
  1. `git fetch origin && git worktree add $WT -b feat/ce-6-sizing-fields origin/main`; `git -C $WT rev-parse --short HEAD` → base SHA for every "unchanged" claim.
  2. `cp /Users/Berzins/Desktop/email-hub/.env /Users/Berzins/Desktop/eh-ce6/.env` as its own command (the only form `pre_tool_use.py:67-69` allows).
  3. Gitignored inputs: `for c in 5 6 7 8 9 10 reframe; do cp $MAIN/data/debug/$c/raw_figma.json $WT/data/debug/$c/; done`.
  4. A3 references and assets: run the copy block in `.claude/skills/converter-fix/references/a3-scoring.md:19-31`.
  5. `cd $WT && uv sync`.
- **VALIDATE**: `git -C $WT status --short` empty; `ls $WT/data/debug/*/raw_figma.json | wc -l` = 7; `uv run pytest app/design_sync/tests/test_snapshot_regression.py -q` green in `$WT`.
- **SATISFIES**: hygiene (R4)

### Task 1b — SCAFFOLD inert fields (so every RED fails on an assertion, not an `AttributeError`)
- **IMPLEMENT**:
  - `raw_types.py`, layout block after `counterAxisAlignItems` (`:117`): `layoutSizingHorizontal: str`, `layoutSizingVertical: str`, `layoutGrow: float`, `layoutAlign: str`, `layoutPositioning: str`, `layoutWrap: str`, `minWidth: Any`, `maxWidth: Any` (Figma sends `null` when unset; `_float_or_none` guards), each with a one-line value-set comment like `:111`.
  - `protocol.py`, after `effects_summary` (`:169`): `layout_sizing_horizontal: str | None = None`, `layout_sizing_vertical: str | None = None`, `layout_grow: float | None = None`, `layout_align: str | None = None`, `layout_positioning: str | None = None`, `layout_wrap: str | None = None`, `min_width: float | None = None`, `max_width: float | None = None`, under `# CE-6 (#424) — Figma auto-layout child sizing, raw upper-case values`.
  - `service.py`: add the eight fields to `_LayoutProps` and return `None` for each from `_parse_layout_props`. No reads yet.
- **GOTCHA**: nothing reads the fields yet, so output cannot move. The commit history shows the scaffold, the RED run, then the reads (converter-fix step 1).
- **VALIDATE**: `uv run pytest app/design_sync/ -q -m "not integration" -x` green except `TestFixtureFreshness` (every case now lacks the 8 keys; expected, closes at Task 9); `uv run pyright app/design_sync/figma app/design_sync/protocol.py` clean.
- **SATISFIES**: AC1 (structure)

### Task 2 — ADD parse unit tests `app/design_sync/figma/tests/test_parse_props.py`
- **IMPLEMENT**: tests on `_parse_layout_props` with `RawFigmaNode` dict literals (Figma input, so the real-fixture rule holds):
  1. auto-layout FRAME with all eight fields (incl. `layoutPositioning: "ABSOLUTE"`, `minWidth: 120`, `maxWidth: 480`, `layoutWrap: "WRAP"`) → each lands on the matching `_LayoutProps` attribute.
  2. TEXT node (non-frame) with `layoutSizingHorizontal: "FILL"`, `layoutSizingVertical: "HUG"`, `layoutGrow: 1`, `layoutAlign: "STRETCH"` → all four parsed (proves no frame gate).
  3. FRAME with `layoutMode: "NONE"` and `layoutSizingHorizontal: "FIXED"` → sizing parsed, `layout_wrap` None.
  4. Unknown strings (`"BOGUS"`) and non-numeric `minWidth` → None.
  5. Absent fields → all None (green on the scaffold; a guard, not a RED test).
- **PATTERN**: `test_parse_props.py:20-45`.
- **VALIDATE**: `uv run pytest app/design_sync/figma/tests/test_parse_props.py -q` → tests 1-3 fail on `assert ... ==`; tests 4-5 stay green (the scaffold returns None, so test 4 is a guard); record.
- **SATISFIES**: AC1

### Task 3 — HARDEN both serializer parity tests
- **IMPLEMENT**:
  1. Move `_sentinel_node()` from `app/design_sync/tests/test_diagnose_roundtrip.py:40-83` to `app/design_sync/tests/conftest.py` as `make_full_design_node()`. Add the eight CE-6 fields with non-default values (`"FILL"`, `"HUG"`, `1.0`, `"STRETCH"`, `"ABSOLUTE"`, `"WRAP"`, `120.0`, `480.0`). Update the diagnose test's 3 call sites (4 occurrences incl. the definition).
  2. In `conftest.py` add helper (not a test) `non_default_field_names(node) -> set[str]`: a field counts as set when it has no default at all (`f.default` and `f.default_factory` both `dataclasses.MISSING`: `id`, `name`, `type`) or its value differs from `f.default` / `f.default_factory()`.
  3. `test_diagnose_roundtrip.py`: new `test_sentinel_sets_every_field`: `non_default_field_names(make_full_design_node()) | {"children"} == {f.name for f in fields(DesignNode)}`. Fails whenever `DesignNode` grows a field the sentinel does not set.
  4. `test_serialization_roundtrip.py`: new `test_every_field_round_trips_the_cache`: `_roundtrip(make_full_design_node())` equals the input on every field except `children`.
- **GOTCHA**: keep the existing `test_full_field_parity_with_protocol` tests; the new ones add the completeness half (E12). Sentinel `visible=False` / `opacity=0.5` are already non-default; keep them.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_serialization_roundtrip.py app/design_sync/tests/test_diagnose_roundtrip.py -q` → cache test fails on `scale_mode`, `rotation`, `effects_summary` and the 8 new fields; diagnose parity test fails on the 8 new fields only; `test_sentinel_sets_every_field` green. Record.
- **SATISFIES**: AC2

### Task 4 — ADD fixture invariants `app/design_sync/tests/test_converter_data_regression.py`
- **IMPLEMENT** class `TestSizingCapture` parametrized over `_structure_case_ids()`, loading via `load_structure_from_json` (exercises `_node_from_dict`):
  1. `test_every_parsed_node_has_sizing`: every node except the synthetic page (`type == PAGE`) has `layout_sizing_horizontal` and `layout_sizing_vertical` in `{"FIXED","HUG","FILL"}`. RED until Task 9.
  2. `test_wrap_on_every_auto_layout_frame`: `layout_wrap is not None` iff `layout_mode not in (None, "NONE")` (the parser stores `"NONE"` on non-auto-layout frames). RED until Task 9.
  3. `test_root_frame_is_fixed`: the page's single child has `layout_sizing_horizontal == "FIXED"`. RED until Task 9.
  4. `test_root_width_is_container_width`: `int(root.width) == EmailDesignDocument.from_legacy(structure, tokens).layout.container_width`. **Verification invariant, green on base** (E5); the docstring says so.
  5. `test_live_cache_path_matches_corpus_load`: `live = [_node_from_dict(json.loads(json.dumps(serialize_node(p)))) for p in structure.pages]`; walk both trees in parallel, assert every non-`children` field equal. This is the production read (`conversion_service.py:72-79`, E10), so it ties live conversion to what the snapshot suite proves.
- **GOTCHA** (test 5 RED shape): fails today only on cases **5 and reframe**, on `scale_mode`. Committed 6-10 have no `scale_mode` key, so both sides load `None` and pass. They start exercising the check after Task 9. Green after Task 7 for 5/reframe; stays green through Task 9 for all 7 (after the re-sync the new keys are real values on both sides).
- **GOTCHA**: invariants over every case, never per-design numbers (epic generality rule). The counts table goes in the report. All five read committed `structure.json`, so they run in CI.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k "SizingCapture" -q` → tests 1-3 red ×7 cases, test 4 green ×7, test 5 red ×2 (5, reframe); record.
- **SATISFIES**: AC2, AC3, AC4

### Task 6 — IMPLEMENT reads `app/design_sync/figma/service.py`
- **IMPLEMENT**: module constants `_SIZING_VALUES = frozenset({"FIXED","HUG","FILL"})`, `_LAYOUT_ALIGN_VALUES = frozenset({"INHERIT","STRETCH","MIN","CENTER","MAX"})`, `_LAYOUT_POSITIONING_VALUES = frozenset({"AUTO","ABSOLUTE"})`, `_LAYOUT_WRAP_VALUES = frozenset({"NO_WRAP","WRAP"})`. In `_parse_layout_props`, replace the scaffold `None`s: read sizing/grow/align/positioning/min/max **before** the frame gate (any node type), as `v if v in _SET else None` (E11) and `_float_or_none(...)`; read `layoutWrap` inside the `layoutMode != NONE` branch next to `itemSpacing` (`:409-415`). Pass all eight into `DesignNode(...)` at `:1635`.
- **GOTCHA**: copying the padding block puts sizing behind `raw_type in (FRAME, ...)` and `layoutMode != NONE`. That drops sizing from TEXT/RECTANGLE/IMAGE nodes. E4: case 5 has 122 sizing values but 86 frames.
- **VALIDATE**: `uv run pytest app/design_sync/figma/tests/ -q` (Task 2 green, existing green); `uv run mypy app/design_sync/figma app/design_sync/protocol.py && uv run pyright app/design_sync/figma app/design_sync/protocol.py`
- **SATISFIES**: AC1

### Task 7 — UPDATE serializers `app/design_sync/diagnose/report.py`, `app/design_sync/services/_serialization.py`
- **IMPLEMENT**:
  - `report.py:_node_from_dict`: add the eight `data.get(...)` kwargs.
  - `_serialization.py:serialize_node`: compact `if ... is not None` entries for the eight fields **and** `scale_mode`, `rotation`, `effects_summary`. `cached_dict_to_node`: matching `data.get(...)` kwargs for all eleven.
- **GOTCHA**: fixing the three 53.3 fields is a live behaviour change (user decision 2026-10-05). Today live conversions lose them (E10), so a synced design with a cropped image fill or a drop shadow converts differently from the same design in the corpus harness. After the fix both paths match. `rotation` stays behind the default-off flag. Corpus: zero change (E10, all `FILL`, no effects or rotation). PR body states it in one paragraph with the E10 consumer list.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_serialization_roundtrip.py app/design_sync/tests/test_diagnose_roundtrip.py -q` → Task 3 green; Task 4 test 5 green for 5/reframe (`scale_mode` now survives the cache).
- **SATISFIES**: AC2

### Task 8 — UPDATE `app/design_sync/figma/layout_analyzer.py`
- **IMPLEMENT**: add `sizing_horizontal: str | None = None` to `ColumnGroup` (after `stroke_weight`, `:177`) and `EmailSection` (after `effects_summary`, `:281`), each with a one-line "CE-6 (#424) — source frame's layoutSizingHorizontal; read by CE-16" comment. Set `sizing_horizontal=child.layout_sizing_horizontal` at `:1349` and `:1376`; `sizing_horizontal=node.layout_sizing_horizontal` at `:461` and `:569`.
- **GOTCHA**: do not add to `DocumentSection.from_email_section` (`email_design_document.py:1279`) or the section cache canonical form (`section_cache.py:116-135`). No reader exists yet, so output cannot move. Consequence: the field is dropped at the document bridge (`to_layout_description`), so CE-16 must carry it across first (ledger `ce-6-sizing-horizontal-dropped-at-document-bridge`, PR #474 review F1). Confirm `dataclasses.replace` at `:625` carries it (it does by construction).
- **TEST**: in `app/design_sync/tests/test_column_grouping.py`, one test building a HORIZONTAL frame with two FILL children and one FIXED child (via `DesignNode(..., layout_sizing_horizontal=...)`) through `_build_column_groups` → groups carry FILL/FILL/FIXED; one `analyze_layout` test asserting the section's `sizing_horizontal`. Write these RED first (they fail on `AttributeError` before the field exists; acceptable as the field is the change).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_column_grouping.py app/design_sync/tests/test_layout_analyzer.py -q`
- **SATISFIES**: AC5

### Task 9 — RE-SYNC fixtures `data/debug/{5,6,7,8,9,10,reframe}/structure.json`
- **IMPLEMENT**: `for c in 5 6 7 8 9 10 reframe; do uv run python scripts/resync-case-structure.py $c; done`.
- **AUDIT** (converter-fix step 3, before touching `expected.html`): `for c in 5 6 7 8 9 10 reframe; do DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/snapshot-capture.py $c --output .tmpscratch/ce6/$c.html; cmp .tmpscratch/ce6/$c.html data/debug/$c/expected.html; done` → byte-identical. No `--overwrite`. Case 8 differs only in whitespace (known churn, E3): compare it byte-for-byte to the output of the `origin/main` structure and with `_normalize_html` to `expected.html`.
- **GOTCHA**: classify the structure change by script (walk old and new by node id) for every changed key: expected only the eight new keys, the four lag keys (6-10), and `image_ref` null → hash (6-10, reframe; counts in E1). Anything else is a stop.
- **VALIDATE**: `git diff --stat -- data/debug/` touches only the 7 `structure.json`; `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k "SizingCapture" -q` → all green.
- **SATISFIES**: AC3, AC6

### Task 10 — UPDATE `.secrets.baseline`
- **IMPLEMENT** (in `$WT`, after Task 9, with the fixtures staged): `detect-secrets scan --baseline .secrets.baseline` (E9). Keep the hashes (CE-3 precedent O1; nulling them re-opens the lag).
- **AUDIT**: compare the old and new baseline `results` per file. Expected exactly: +15/+11/+16/+10/+13/+14 for 10/6/7/8/9/reframe (79), case 5 count unchanged at 7 with new line numbers, `generated_at` changed, no other file's entries changed. Any other change is a stop.
- **GOTCHA**: run it in `$WT` only. In the main checkout the scan would also pick up the other branch's tracked changes.
- **GOTCHA**: no `.pre-commit-config.yaml` change. Case 7 is 525,405 B but the large-file hook only checks added files (E8).
- **VALIDATE**: `uv run pre-commit run --files data/debug/*/structure.json .secrets.baseline` → all hooks pass.
- **SATISFIES**: AC6

### Task 11 — UPDATE freshness map + ledger
- **IMPLEMENT**: delete `_LAG_6_10` and make `_KNOWN_LAGGING_KEYS: dict[str, frozenset[str]] = {}` (keep the mechanism and its comment, reworded to "empty since CE-6"). Close `ce-3-fixture-schema-lag-6-10` with the `deferred-items` skill (status `closed`, `closed_commit: "pending"`, resolution citing Task 9 audit).
- **GOTCHA**: `TestFixtureFreshness` "stale" branch fails if the map still lists keys the cases now carry, so this edit is required, not cosmetic.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k "Freshness or known_failures" -q`
- **SATISFIES**: AC7

### Task 12 — LADDER and snapshot hold
- **VALIDATE**: `git diff origin/main -- data/debug/ladder_snapshot.json data/debug/*/expected.html` empty; `uv run pytest app/design_sync/tests/test_converter_data_regression.py -k ladder -q` green; `make snapshot-test` green.
- **SATISFIES**: AC6

### Task 13 — A3 and fidelity gate
- **IMPLEMENT**: A3 per `.claude/skills/converter-fix/references/a3-scoring.md`, before (detached checkout of the base SHA; Tasks 1b-11 are committed, so a stash no longer restores base) and after on the same checkout: `DESIGN_SYNC__SECTION_CACHE_ENABLED=false uv run python scripts/score-fidelity-cases.py`. Expected: identical per-section scores (derived: identical converter HTML in, identical render out; E3). `make fidelity-gate` → pass with no re-stamp (E7).
- **GOTCHA**: a non-zero A3 delta with identical HTML is scorer jitter (`reference_a3_scorer_section_instability`), but identical HTML should give exactly 0; any delta is investigated, not ratified.
- **SATISFIES**: AC8

### Task 14 — REPORT `.claude/reports/ce-6-sizing-fields-report.md`
- **IMPLEMENT**: re-derive the counts table on the branch head from the committed `structure.json` (tag observed, name the command), the E3-style byte-identity table, A3 before/after, gate result, ladder unchanged, the cache behaviour-change note, wrong-if status ("a real client file has no `layoutMode`": unchecked until CE-5 #423 lands; all 7 corpus files have `layoutMode` on 100% of frames, observed).
- **SATISFIES**: AC9

### Task 15 — FULL gate
- **VALIDATE**: `make check-full` green, then `git diff` (lint rewrites) and restore `app/ai/agents/*/skill-versions.yaml` date churn. Stage only this ticket's files; show `git diff --stat origin/main...HEAD` before commit.
- **SATISFIES**: AC10

---

## TESTING STRATEGY

### Unit Tests
Task 2 (parser helper), Task 3 (cache pair completeness), Task 8 (analysed nodes). All build minimal Figma dicts or `DesignNode`s, never email HTML.

### Integration Tests
Task 4 invariants over every committed case through the real loader; snapshot + ladder suites (Task 12) prove zero output change.

### Edge Cases

| Edge case | Where verified |
|---|---|
| Sizing on non-frame nodes (TEXT) | Task 2 test 2; Task 4 test 1 over corpus |
| `layoutMode: NONE` frame keeps sizing, no wrap | Task 2 test 3 |
| Unknown enum strings / null min-max | Task 2 test 4 |
| Fields absent (Penpot, old fixtures, old DB cache rows) | Task 2 test 5; `.get` defaults in both loaders |
| `layoutPositioning`/`minWidth`/`maxWidth` (0 in corpus, E4) | Task 2 test 1 only; stated in report |
| Field added to `DesignNode` later but not to the cache | Task 3 completeness assertion |
| Loader drops a field the dumper writes | Task 4 test 1 (loads through `_node_from_dict`) |

---

## VALIDATION COMMANDS

### Level 1
- `uv run ruff format --check app/design_sync scripts` and `uv run ruff check --no-fix app/design_sync scripts`
- `make types`

### Level 2
- `uv run pytest app/design_sync/ -q -m "not integration"`

### Level 3
- `make snapshot-test`, `make converter-data-regression`, `make fidelity-gate`, then `make check-full`

### Level 4: Manual
1. `uv run python scripts/resync-case-structure.py 7 --out /tmp/c7.json && python3 -c "import json;d=json.load(open('/tmp/c7.json'));print(d['pages'][0]['children'][0]['layout_sizing_horizontal'])"` → `FIXED`.
2. Open `data/debug/9/expected.html` unchanged at 600px beside `email-templates/training_HTML/for_converter_engine/<design>/manual_component_build.html` (epic convention). No visual change is expected; this records that none happened.

---

## ACCEPTANCE CRITERIA

- [ ] AC1: each of the eight fields parses from a Figma node, for frame and non-frame nodes; invalid values → None.
- [ ] AC2: every `DesignNode` field (incl. `scale_mode`, `rotation`, `effects_summary`) round-trips the DB cache; a future field that does not fails a test.
- [ ] AC3: every parsed node in every committed case carries horizontal and vertical sizing; wrap present iff auto-layout.
- [ ] AC4: root frame width == `container_width` for every case (600 or 640), root sizing FIXED.
- [ ] AC5: `ColumnGroup` and `EmailSection` carry the source frame's horizontal sizing.
- [ ] AC6: all corpus outputs byte-identical to `origin/main` modulo the known c8 whitespace churn; ladder unchanged.
- [ ] AC7: `_KNOWN_LAGGING_KEYS` empty; `ce-3-fixture-schema-lag-6-10` closed.
- [ ] AC8: A3 before/after identical on all cases; fidelity gate passes with no re-stamp.
- [ ] AC9: report at `.claude/reports/ce-6-sizing-fields-report.md` with the re-derived counts table (observed).
- [ ] AC10: `make check-full` green on the head.

## COMPLETION CHECKLIST

- [ ] RED recorded for Tasks 2, 3, 4 (tests 1-3, 5), 8 after the Task 1b scaffold, before Tasks 6-8
- [ ] Task 9 audit diffs empty
- [ ] `.secrets.baseline` audit matches Task 10 exactly (79 added, case 5 renumbered, nothing else)
- [ ] Unrelated working-tree edits not committed
- [ ] PR body flags the large fixture diff and the live-path behaviour change (E10)
- [ ] Worktree `$WT` removed after merge (`git worktree remove`)

---

## RISKS (all resolved at planning, 2026-10-05)

| id | risk | resolution | evidence |
|----|------|------------|----------|
| R1 | Case 7 fixture exceeds the 500 KB pre-commit cap | No action: the hook checks only newly added files; these are modified | E8 (hook source + staged run `Passed`) |
| R2 | detect-secrets flags the new `image_ref` hashes; CE-3 needed the user | Agent runs the baseline scan in the worktree and audits the exact delta | E9 (79 entries, hook `Passed`) |
| R3 | Cache fix changes live conversion | Intended (user decision). Live and corpus paths become identical, pinned by Task 4 test 5 on every case; corpus output unchanged; `rotation` stays flag-gated | E10 |
| R4 | Main checkout has another session's uncommitted edits | Work in a dedicated worktree; nothing in the main checkout is touched | Task 1 |
| R5 | Pyright strict rejects the validation pattern | Pattern type-checks clean | E11 |
| R6 | A new field silently missing from a loader | Sentinel completeness test + both parity tests + live-path parity | E12, Tasks 3/3b |

## OPEN QUESTIONS / ASSUMPTIONS

- Decided 2026-10-05 (user): fields on `DesignNode` plus `sizing_horizontal` on `ColumnGroup`/`EmailSection`; not on `DocumentSection`.
- Decided 2026-10-05 (user): fix the three 53.3 fields in the cache pair here.
- Assumption: only horizontal sizing goes on the analysed nodes (CE-16 needs widths only). Vertical stays on `DesignNode`.
- Assumption: re-sync uses the local `raw_figma.json` snapshots (Figma versions as recorded by the script output), not a fresh Figma pull. A fresh pull is out of scope and would move baselines.
- Assumption: `scripts/resync-case-structure.py` output for case 5 already equals committed (E1), so case 5's diff is the eight new keys only.

## NOTES

- Why read sizing in `_parse_layout_props` rather than a fourth helper: same concern (layout), one NamedTuple, no new abstraction.
- Why invariants instead of per-case counts in tests: the epic's generality rule; a per-case count test would pin fixture trivia and break on any Figma re-pull.
- Rejected: a large-file exemption or compact JSON dumps. Neither is needed (E8), and compact dumps would make every future fixture diff unreadable.
- The tracked `actual-with-fixes.html` / `actual-tree-with-fixes.html` files have no producer or test in `app/` or `scripts/` (grep); leave them.

## AMENDMENTS

- 2026-10-05 — risk pass before implementation: R1 dropped (hook checks added files only, E8); R2 agent-run baseline with exact audit (E9, 79 not ~90); R3 pinned by Task 4 test 5 live-path parity (E10); Task 1b scaffold so every RED fails on an assertion; Task 4 root test split into invariant (green) and FIXED (red); commit-time hook checked (E9); R4 worktree setup (Task 1); sentinel completeness tests (E12, Task 3). No `.pre-commit-config.yaml` change.
- 2026-10-05 — implementation (report `.claude/reports/ce-6-sizing-fields-report.md` D1-D7): Task 2 test 4 green on the scaffold by construction; Task 4 test 2 uses `layout_mode not in (None, "NONE")`; Task 8 RED is `AttributeError`; Task 9 audit is `cmp` plus a scripted key classification, with case 8 checked against base-structure output; Task 13 "before" scored at detached `56598f36`; Level 4 manual check 2 superseded by byte-identity of `expected.html`.
- 2026-10-05 — PR #474 review round 1 (`.claude/reports/pr-474-review-fixes.md`, commit `a9bd6391`): F1 logged as ledger `ce-6-sizing-horizontal-dropped-at-document-bridge` and named in both `sizing_horizontal` comments; F2 `raw_types.py` comment corrected (absent = not captured); F3 added `test_every_field_survives_the_production_cache_read` (sentinel through `serialize_node` → JSON → `_node_from_dict`), the corpus parity test narrowed to corpus values; F5 two live-only `effects_summary` effects noted on `phase-53f-decorative-image-flag` and `ce-10-large-styled-icon-wrapper-exports-bare-glyph`; F4 (SHA stamp) after merge.
