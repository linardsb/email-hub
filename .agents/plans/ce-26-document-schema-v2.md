# Feature: CE-26 document schema v2 (`body` tree beside `sections`, version dispatch)

The following plan should be complete, but validate documentation and codebase patterns and task sanity
before you start implementing. Pay special attention to the names of existing types and import paths.

Base: `origin/main` `b9cccdf8` (observed: `git fetch` 2026-10-05). Line refs are at that SHA. Branch from
`origin/main`, not from the current `fix/ce-7-review-f1` checkout.

## Feature Description

`EmailDesignDocument` (the converter's single JSON contract) gets a second version. `"2.0"` adds a `body`
field: a typed tree of nine DSL node types (`wrapper`, `section`, `column`, `text`, `image`, `button`,
`divider`, `spacer`, `raw`) next to the unchanged flat `sections`. The loader (`from_json`) and the
validator (`validate`) dispatch on `version`. Nothing produces a v2 document yet; the tree builder, the
MJML compiler and the feature flag are later tickets (CE-19 #437, CE-20 #438).

## User Story

As the converter team building the DSL compiler spike (CE-19 #437)
I want a persisted, schema-validated document format that can carry a typed layout tree
So that the spike's tree builder and compiler plug into an existing contract instead of inventing one, and
persisted v1 documents keep loading unchanged.

## Problem Statement

Observed 2026-10-02 (issue #466) and re-read at `b9cccdf8`:

- `EmailDesignDocument.from_json` (`app/design_sync/email_design_document.py:1456`) never reads `version`
  beyond copying it, so a `body` key would be silently dropped.
- `_load_schema` / `_get_validator` (`:54-61`) are single-entry `lru_cache`s pinned to
  `data/schemas/email-design-document-v1.json`, whose root has `additionalProperties: false` and
  `version: {"const": "1.0"}`. A v2 document cannot validate.

Found while planning (observed: `from_legacy` → `to_json` → `validate` on all 7 committed cases,
2026-10-05, scratch probe run on checkout `94e84b95`. Its `email_design_document.py` is identical to
`b9cccdf8`; it lacks CE-6's sizing-field reads in `protocol.py`/`diagnose/report.py`/`figma/`, which add
no tokens and no dividers, so the figures below should hold on `b9cccdf8` (derived, not re-run there)):

- **Every real converter document fails v1 validation today.** `tokens.typography` has 234 entries on all
  7 cases (cases 5–10 and reframe share one token library) against `maxItems: 200`. Deduplication does not
  help: 232 distinct entries ignoring `name`.
- `DocumentColumn.dividers` (added in #365, `:878-909`) is emitted by `to_json` but never declared in the
  v1 `column` def, so 4 cases also fail with `'dividers' was unexpected`: case 5 (sections 5, 7), 8 (10),
  9 (7, 9), 10 (12, 14). A field-by-field sweep of every `Document*` dataclass against its `$defs`
  entry finds `dividers` as the only drift.
- Round-trip is already sound: `json.dumps(from_json(d).to_json()) == json.dumps(d)` on all 7 (observed,
  same probe).

Prototyped: the v1 schema with only the two Task 1 edits applied validates all 7 case documents with 0 errors (observed 2026-10-05, in-memory edit of the base schema, jsonschema 4.26.0).

User decision 2026-10-05: **relax v1 and v2 together.** Raise the typography cap and declare `dividers` in
both files. A relaxation (larger `maxItems`, one new optional property) cannot make a valid v1 document
invalid, so the ticket's "Wrong if" line holds. v2 is then exactly "v1 plus `body`".

## Solution Statement

1. Relax `email-design-document-v1.json`: `tokens.typography.maxItems` 200 → 1000; declare `dividers` on
   `$defs/column`.
2. Add `data/schemas/email-design-document-v2.json`: a full copy of v1 with `$id`/`title` changed,
   `version.const` = `"2.0"`, `body` added to `properties` and `required`, and new `node_*` +
   `container_style` `$defs`. A parity test keeps the shared `$defs` identical to v1.
3. Add `app/design_sync/dsl/nodes.py`: frozen dataclasses for the nine nodes with `to_json`/`from_json`.
   The text, image and button leaves wrap `DocumentText`/`DocumentImage`/`DocumentButton` verbatim.
4. `EmailDesignDocument` gains `body: tuple[BodyNode, ...] = ()`. `from_json` dispatches on `version`
   (`"1.0"` → `body=()`, `"2.0"` → parse `body`, else `ValueError`). `validate` picks the validator by
   `version`. `to_json` writes `body` only for `"2.0"`.
5. Close ledger entry `phase-53.7-typography-maxitems-cap` with a test that validates all 7 real cases.

## Out of Scope / Non-Goals

- Not included: the tree builder (FR1–FR6), the compiler, `compile_tree`, the `dsl_compiler_enabled` flag
  (CE-19 #437 / DSL-1). `from_legacy` keeps writing `version="1.0"`.
- Not included: a `/schema/v2` endpoint (no consumer yet; DSL-1). `GET /schema/v1`'s docstring
  (`routes.py:869`) stays true and is not edited. `POST /validate-document` starts accepting v2 bodies
  through `validate()` dispatch, so its docstring (`routes.py:887`) is updated in Task 11 and the SDK
  regenerated, since that text is copied into `cms/packages/sdk/openapi.json:6706` and
  `cms/packages/sdk/src/client/sdk.gen.ts:1798` (observed: `git grep` at base).
- Not included: `sizing_horizontal` on `DocumentColumn`/`DocumentSection` (ledger
  `ce-6-sizing-horizontal-dropped-at-document-bridge`, carried to CE-16). DSL nodes carry their own
  `sizing` field, so the DSL path does not need that bridge.
- Not changing: `EmailDesignDocument.schema()` and `GET /schema/v1` keep serving the v1 file (its content
  changes by the two relaxations only).
- Not changing: converter output. Every case renders byte-identical HTML.

## Feature Metadata

**Feature Type**: New Capability (data contract) plus a schema-drift fix
**Estimated Complexity**: Medium (no runtime behaviour change, but a public JSON contract)
**Primary Systems Affected**: `app/design_sync/email_design_document.py`, `data/schemas/`, new `app/design_sync/dsl/`
**Dependencies**: none new. `jsonschema` 4.26.0 (observed: `uv pip show jsonschema`), `Draft202012Validator`.

## Related Work

**Implements**: #466 (CE-26) · **Epic**: #439; spec `docs/architecture/dsl-compiler.md` S1 + M2; slices
`.agents/plans/dsl-epic-slices.md:39-44`.

**Back-references**:

- `.agents/plans/36.1-email-design-document-schema.md` — Why: original v1 schema/dataclass design this extends.
- `.agents/plans/ce-6-sizing-fields.md` — Why: source of the `Sizing` vocabulary (`FIXED|HUG|FILL`,
  `app/design_sync/protocol.py:172-174`).

**Forward-references**: CE-19 (#437) tree builder writes v2; DSL-1 adds `/schema/v2` + route docstrings.

## Deferred Items Touching This Plan

Grep run 2026-10-05 against `origin/main:.agents/deferred-items.json` for phase `ce-26`/`53.7` and every
file below.

| id | match (phase / code_ref) | decision | why |
|----|--------------------------|----------|-----|
| `phase-53.7-typography-maxitems-cap` | `data/schemas/email-design-document-v1.json`, `email_design_document.py` `validate()` | **close** | Task 1 raises the cap; Task 7 validates all 7 real cases (its `closes_when`). Its "LEGO only" wording is stale: all 7 cases emit 234 (observed). Close via `.claude/skills/deferred-items/SKILL.md` Close step, `closed_commit: pending` until squash. |
| `ce-6-sizing-horizontal-dropped-at-document-bridge` | `email_design_document.py:936/951/1279` | **carry forward** | Its `closes_when` names CE-16 or CE-26. Adding the field changes v1 sections that nothing reads yet; CE-16 is the first reader. Append a `notes` line saying CE-26 deliberately left it. |
| `ce-10-unnamed-button-icon-not-exported` | `import_service.py:598` | **avoid** | This plan does not edit `import_service.py`; it only relies on `:239`'s existing `except ValueError`. |

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `app/design_sync/email_design_document.py:46-61` — schema path + two `lru_cache(maxsize=1)` loaders to make per-version.
- `app/design_sync/email_design_document.py:488-858` — `DocumentCornerRadiusSpec`, `DocumentText`, `DocumentImage`, `DocumentButton`: the `to_json` (omit-when-default) / `from_json` (`data.get`) style to mirror, and the three leaf payloads the nodes wrap.
- `app/design_sync/email_design_document.py:860-935` — `DocumentColumn.dividers` serialisation (keys `node_id`, `stroke_color`, `stroke_weight`) that the schema must declare.
- `app/design_sync/email_design_document.py:1424-1492` — `EmailDesignDocument` fields, `to_json`, `from_json` (KeyError/TypeError → `ValueError`), `validate`, `schema`.
- `app/design_sync/email_design_document.py:1518-1619` — `from_legacy`: unchanged, still writes `"1.0"` (`:1559`, `:1610`); shows the function-level-import pattern (`:1532-1534`).
- `app/design_sync/import_service.py:236-245` — persisted-document load: catches `(ValueError, KeyError)` and falls back to the legacy re-fetch. An unsupported version must raise `ValueError` to land here.
- `app/design_sync/routes.py:870-911` — `GET /schema/v1` (`schema()`) and `POST /validate-document` (`validate()` on arbitrary client JSON; `version` may be any JSON type).
- `data/schemas/email-design-document-v1.json` — 521 lines; root `additionalProperties: false`; `$defs` keys: `source tokens color typography spacing gradient gradient_stop variable section content_group padding style_run corner_radius_spec text image button column layout compatibility_hint token_warning`. Note `text`, `image`, `button`, `section`, `column` are taken: node defs need a `node_` prefix.
- `app/design_sync/font_stacks.py:26-31` — `FontCategory` StrEnum (`sans-serif`/`serif`/`monospace`): the generic that must end a text node's `font_stack` (spec S3).
- `app/design_sync/figma/layout_analyzer.py:38` — `EmailSectionType(StrEnum)`: the enum style to mirror.
- `app/design_sync/tests/test_email_design_document.py:45-56` (`_make_document`), `:173-322` (`TestSchemaValidation`), `:207-215` (`test_wrong_version` uses `"2.0"`, must change), `:324-403` (`TestRoundtrip`).
- `app/design_sync/tests/regression_runner.py:31-61` — `discover_cases`, `run_case_conversion` (`load_structure_from_json` → `from_legacy` → `convert_document`): the real-fixture oracle.
- `app/design_sync/tests/test_golden_roundtrip.py:69-88` — `TestGoldenSchemaValidation.test_schema_valid`: golden components through `HtmlImportAdapter`.

### New Files to Create

- `data/schemas/email-design-document-v2.json` — v1 copy + `body` + `node_*`/`container_style` `$defs`.
- `app/design_sync/dsl/__init__.py` — package docstring only.
- `app/design_sync/dsl/nodes.py` — enums, `ContainerStyle`, nine node dataclasses, `body_from_json`.
- `app/design_sync/dsl/tests/__init__.py` — empty (sibling `tests/` packages have one, e.g. `app/design_sync/tests/__init__.py`).
- `app/design_sync/dsl/tests/test_nodes.py` — node round-trip, enum/schema parity, illegal-child and guard tests.
- `app/design_sync/tests/test_document_v2.py` — version dispatch, v1/v2 schema parity, real-case corpus checks.

### Relevant Documentation

- `docs/architecture/dsl-compiler.md` § S1 (node schema, loader rule), § S2 (DSL nesting table), § S3 (value contracts) — the decided shapes; do not re-decide.
- [JSON Schema 2020-12 `contains`](https://json-schema.org/understanding-json-schema/reference/array#contains) — "at least one section in a wrapper" while `raw` siblings stay allowed.
- [`if`/`then` conditional](https://json-schema.org/understanding-json-schema/reference/conditionals) — child unions dispatch on the `type` tag, so an error reports at the failing field (`body.0.children.0.children.0.children.0.type`). *(Amended after PR #475 F2: the original `oneOf` reported every nested failure at `body.0`, with the whole subtree's repr as the message.)*

### Patterns to Follow

**Dataclasses**: `@dataclass(frozen=True)`, hand-written `to_json` that omits `None`/default fields and `from_json` classmethods using `data["required"]` / `data.get("optional")` (`email_design_document.py:541-589`). Sequences inside nodes are `tuple[...]` (spec S1), not `list`.
**Enums**: `class X(StrEnum)` (`layout_analyzer.py:38`); serialise with `.value`, parse with `X(value)` (raises `ValueError` on unknown, which is the desired loader error).
**Errors**: loader errors are `ValueError` with a `Malformed EmailDesignDocument: …` style message (`:1475`). No new exception class; nothing new is logged (pure data module, no logger in the file today).
**Imports**: `dsl/nodes.py` imports `DocumentText`, `DocumentImage`, `DocumentButton` from `app.design_sync.email_design_document` at module level. `email_design_document.py` imports `dsl.nodes` **only inside `from_json`** and under `TYPE_CHECKING` for the `BodyNode` annotation, to avoid a circular import (pattern: `from_legacy`'s function-level imports, `:1532-1534`; `TYPE_CHECKING` block at `:42-44`).
**Lint**: no rule flags the function-level import (ruff `PLC0415` is not selected; the file already does it at `:1532`). Ruff `TC` rules are not selected (CLAUDE.md "Linter safety"), so do not move runtime imports under `TYPE_CHECKING` beyond the annotation-only `BodyNode`.

---

## IMPLEMENTATION PLAN

### Phase 1: Schemas (v1 relaxation + v2 file)
Tasks 1–2. Pure JSON; RED tests for them land in Phase 4 but are written first (Task 0).

### Phase 2: DSL node dataclasses
**Independent of:** Phase 1 at the code level (the parity test in Task 8 joins them).
Task 3.

### Phase 3: Version dispatch in `EmailDesignDocument`
**Depends on:** Phases 1 and 2.
Tasks 4–5.

### Phase 4: Tests, ledger, gates
Tasks 6–12 (Task 11 touches `cms/packages/sdk/`).

---

## STEP-BY-STEP TASKS

### Task 0: RECORD the base and capture converter output before any edit

- **IMPLEMENT**: `git rev-parse origin/main` into the report. Dump every case's HTML at the base:
  `uv run python -c "from pathlib import Path; from app.design_sync.tests.regression_runner import discover_cases, run_case_conversion; out=Path('$SCRATCH/before'); out.mkdir(parents=True, exist_ok=True); [ (out/f'{c.name}.html').write_text(r.html) for c in discover_cases() if (r:=run_case_conversion(c)) ]"`
  (`$SCRATCH` = the session scratchpad). Expect 7 files (5–10, reframe).
- **GOTCHA**: run with `DESIGN_SYNC__SECTION_CACHE_ENABLED=false` so a warm cache cannot mask a change.
- **VALIDATE**: `ls $SCRATCH/before | wc -l` → 7.
- **SATISFIES**: AC 5.

### Task 1: UPDATE `data/schemas/email-design-document-v1.json`

- **IMPLEMENT**: (a) `$defs.tokens.properties.typography.maxItems` 200 → 1000. (b) add to `$defs.column.properties`:
  `"dividers": {"type": "array", "maxItems": 50, "default": [], "items": {"type": "object", "required": ["node_id", "stroke_color"], "additionalProperties": false, "properties": {"node_id": {"type": "string", "maxLength": 200}, "stroke_color": {"type": "string", "maxLength": 20}, "stroke_weight": {"type": ["number", "null"], "default": null}}}}`.
  Nothing else in the file changes.
- **PATTERN**: sibling arrays in the same def (`texts`, `images`: `maxItems` + `default: []`).
- **GOTCHA**: 1000 is a chosen ceiling (expected), not a measured need: observed max is 234. The cap exists to bound
  `POST /validate-document` work; the route's 5 MB body limit (`routes.py:863`) still bounds it.
  `stroke_color` is required because `DocumentColumn.from_json` reads `dv["stroke_color"]` (`:928`); a
  document without it would validate but fail to load.
- **VALIDATE**: `uv run python -c "import json; json.load(open('data/schemas/email-design-document-v1.json'))"` and Task 7's corpus test.
- **SATISFIES**: AC 6, ledger close.

### Task 2: CREATE `data/schemas/email-design-document-v2.json`

- **IMPLEMENT**: copy the Task-1 v1 file, then change only:
  - `$id` → `email-design-document/v2`; `title` → `Email Design Document v2`; `description` names the `body` tree.
  - `properties.version` → `{"const": "2.0", …}`.
  - `properties.body` → `{"type": "array", "maxItems": 100, "items": <dispatch over wrapper, section, raw>}`; add `"body"` to root `required`. A dispatch is `{"type": "object", "required": ["type"], "properties": {"type": {"enum": [...]}}, "allOf": [{"if": {"type": "object", "required": ["type"], "properties": {"type": {"const": "<t>"}}}, "then": {"$ref": "#/$defs/node_<t>"}}, …]}` (amended after PR #475 F2).
  - New `$defs` (all `"type": "object"`, `"additionalProperties": false`, `required` includes `type`, `id`, `name`; `id`/`name` are `string` `maxLength: 200`; `type` is `{"const": "<node>"}`):

| def | extra properties (required in **bold**) |
|---|---|
| `container_style` | `background_color` (`#/$defs/hex6`), `radius` (`oneOf`: integer ≥0, or array of exactly 4 integers ≥0), `padding` (array of exactly 4 integers ≥0: top, right, bottom, left), `vertical_align` (enum `top middle bottom`), `sizing` (`#/$defs/sizing`), `full_width` (boolean, default false), `background_image` (`#/$defs/image`) |
| `node_wrapper` | `style` (`container_style`), **`children`**: array, `minItems: 1`, `maxItems: 50`, items dispatch [`node_section`, `node_raw`], `contains: {"properties": {"type": {"const": "section"}}}` |
| `node_section` | `style`, **`children`**: same shape, items dispatch [`node_column`, `node_raw`], `contains` type `column` |
| `node_column` | `style`, **`children`**: array `maxItems: 100`, items dispatch [`node_text`, `node_image`, `node_button`, `node_divider`, `node_spacer`, `node_raw`] |
| `node_text` | **`text`** (`#/$defs/text`), **`role`** (enum `heading body label cta`), **`font_stack`** (array of strings `maxLength: 200`, `minItems: 1`, `maxItems: 20`) |
| `node_image` | **`image`** (`#/$defs/image`), **`alt`** (string `maxLength: 2000`), `href` (string `maxLength: 2000`), `sizing` |
| `node_button` | **`button`** (`#/$defs/button`), `align` (enum `left center right`), `sizing` |
| `node_divider` | **`thickness`** (integer ≥0), **`color`** (`hex6`), **`style`** (enum `solid dashed dotted`), `width` (integer ≥0) |
| `node_spacer` | **`height`** (integer ≥0), `background_color` (`hex6`) |
| `node_raw` | **`html`** (string `maxLength: 100000`), **`reason`** (string `pattern: ^[a-z][a-z0-9_.]*$`, `maxLength: 64`) |
| `hex6` | `{"type": "string", "pattern": "^#[0-9a-f]{6}$"}` (S3: lowercase six-digit) |
| `sizing` | `{"enum": ["FIXED", "FILL", "HUG"]}` (raw upper-case, as `protocol.py:173`) |

- **PATTERN**: v1 `$defs` style (`additionalProperties: false`, `maxLength` on strings).
- **GOTCHA**: `text`, `image`, `button`, `section`, `column` are existing v1 `$defs`; node defs **must** be prefixed `node_` or they overwrite them. `node_divider.style` and the containers' `style` share a key name with different meaning (enum vs object); this is per-def and legal.
- **GOTCHA**: JSON Schema cannot constrain the last array item, so S3's "font_stack ends in a generic" is enforced in the dataclass (Task 3), not here. Say so in the def's `description`.
- **GOTCHA**: `raw.html` is stored, not sanitised, here. The spec's "sanitised table-only payload" is the builder's job (`sanitize_web_tags_for_email()` before construction, CE-19). Put that in the def's `description`.
- **VALIDATE**: `uv run python -c "import json; from jsonschema import Draft202012Validator as V; V.check_schema(json.load(open('data/schemas/email-design-document-v2.json')))"`.
- **SATISFIES**: AC 2, AC 3.

### Task 3: CREATE `app/design_sync/dsl/__init__.py`, `app/design_sync/dsl/nodes.py`

- **IMPLEMENT** (`nodes.py`):
  - Enums (`StrEnum`): `NodeType` (9 members, values = schema `const`s), `Sizing` (`FIXED FILL HUG`), `TextRole` (`heading body label cta`), `HorizontalAlign` (`left center right`), `VerticalAlign` (`top middle bottom`), `DividerStyle` (`solid dashed dotted`).
  - `Padding = tuple[int, int, int, int]`; `Radius = int | tuple[int, int, int, int]`.
  - `ContainerStyle` (all optional: `background_color: str | None`, `radius: Radius | None`, `padding: Padding | None`, `vertical_align: VerticalAlign | None`, `sizing: Sizing | None`, `full_width: bool = False`, `background_image: DocumentImage | None`), `to_json`/`from_json`, omit-when-default.
  - Leaves: `TextNode(id, name, text: DocumentText, role: TextRole, font_stack: tuple[str, ...])`, `ImageNode(id, name, image: DocumentImage, alt: str, href: str | None = None, sizing: Sizing | None = None)`, `ButtonNode(id, name, button: DocumentButton, align: HorizontalAlign | None = None, sizing: Sizing | None = None)`, `DividerNode(id, name, thickness: int, color: str, style: DividerStyle, width: int | None = None)`, `SpacerNode(id, name, height: int, background_color: str | None = None)`, `RawNode(id, name, html: str, reason: str)`.
  - Containers: `ColumnNode(id, name, children: tuple[ColumnChild, ...], style: ContainerStyle | None = None)`, `SectionNode(… children: tuple[ColumnNode | RawNode, ...] …)`, `WrapperNode(… children: tuple[SectionNode | RawNode, ...] …)`.
  - Each node: class-level `type: ClassVar[NodeType]`; `to_json` writes `"type": self.type.value` first, then `id`, `name`, then fields; payload leaves call `self.text.to_json()` etc.
  - Aliases: `ColumnChild = TextNode | ImageNode | ButtonNode | DividerNode | SpacerNode | RawNode`; `BodyNode = WrapperNode | SectionNode | RawNode`.
  - `NODE_CLASSES: dict[NodeType, type[...]]` mapping every member to its class.
  - Allowed children follow S2's "DSL allows" column. One private `_node_from_json(data)` reads `NodeType(data["type"])` and dispatches via `NODE_CLASSES`; per-container helpers narrow the result (see the strict-pyright GOTCHA) and raise `ValueError(f"node type {t!r} not allowed here")`.
  - `body_from_json(items: list[dict[str, Any]]) -> tuple[BodyNode, ...]` (public; used by `EmailDesignDocument.from_json`).
  - `TextNode.__post_init__`: `font_stack` non-empty and `font_stack[-1] in {c.value for c in FontCategory}`, else `ValueError` (S3).
- **PATTERN**: `DocumentButton.to_json`/`from_json` (`email_design_document.py:740-805`); `FontCategory` from `app/design_sync/font_stacks.py:26`.
- **IMPORTS**: `from app.design_sync.email_design_document import DocumentButton, DocumentImage, DocumentText`; `from app.design_sync.font_stacks import FontCategory`.
- **GOTCHA**: radius/padding JSON is a list; `from_json` converts to `tuple` (and 4-length check) so round-trip equality and hashing hold; a scalar radius stays `int`. Every int length (radius, padding, `thickness`, `width`, `height`) goes through `_px`: a whole float loads as `int`, a bool or fraction raises (amended after PR #475 F1).
- **GOTCHA**: `from_json` must not use `data.get("type")` defaults; a missing `type` is `KeyError`, which `EmailDesignDocument.from_json` already converts to `ValueError`.
- **GOTCHA (strict pyright, prototyped)**: the shared parser returns the node union, which strict pyright will not assign to `tuple[ColumnNode | RawNode, ...]`. Use this shape (prototyped 2026-10-05 on a 4-node cut: `pyright` 0 errors, `mypy` clean, `ruff check` clean, observed):
  - `_node_from_json(data, allowed: frozenset[NodeType], parent: str) -> AnyNode`: `NodeType(data["type"])` first, then `if node_type not in allowed: raise ValueError(f"node type {node_type.value!r} not allowed in a {parent}")`, **then** `NODE_CLASSES[node_type].from_json(data)`.
  - Per-container helpers `_body_child`, `_wrapper_child`, `_section_child`, `_column_child` call it with `_BODY_CHILDREN` / `_WRAPPER_CHILDREN` / `_SECTION_CHILDREN` / `_COLUMN_CHILDREN`, then narrow with `if not isinstance(node, ColumnNode | RawNode): raise ValueError(...)` (unreachable after the set check; it exists for the type checker). No `cast`, no `assert`.
  - Check the tag **before** parsing. The prototype's first cut parsed first and narrowed after; an illegal `section` under a `column` then failed inside the wrong parser with `KeyError: 'children'` instead of the "not allowed" `ValueError` (observed).
  - Unknown tags fail in `NodeType(...)` with `ValueError: 'carousel' is not a valid NodeType` (observed).
  - `NODE_CLASSES: dict[NodeType, type[AnyNode]]` typechecks with `.from_json` called on the union of classes (observed).
- **GOTCHA (lint)**: fields named `type` and `id` shadow builtins; ruff's `A` family is not selected (`pyproject.toml` `[tool.ruff.lint] select` = E W F I B C4 UP ANN S DTZ RUF ARG PTH SIM PERF T20 PIE PGH RET FURB FBT D, observed 2026-10-05), so no rule flags them. `FBT` targets function parameters, not dataclass fields, so `full_width: bool = False` is clean.
- **GOTCHA**: `ClassVar` fields are not dataclass fields, so `type` is excluded from `__init__`; that is intended (a `TextNode` cannot claim to be a `spacer`).
- **GOTCHA**: S2 minimums (a wrapper needs ≥1 section, a section ≥1 column) are enforced by the schema only, not by `from_json`. Loading does not validate; callers that need validity call `validate()` (the existing contract: `import_service.py:239` loads without validating).
- **VALIDATE**: `uv run mypy app/design_sync/dsl && uv run pyright app/design_sync/dsl && uv run ruff check --no-fix app/design_sync/dsl && uv run ruff format --check app/design_sync/dsl`.
- **SATISFIES**: AC 2, AC 3.

### Task 4: UPDATE `app/design_sync/email_design_document.py` (validator dispatch)

- **IMPLEMENT**:
  - Replace `_SCHEMA_PATH` (`:46-48`) with `_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "data" / "schemas"` and `_SCHEMA_FILES: dict[str, str] = {"1.0": "email-design-document-v1.json", "2.0": "email-design-document-v2.json"}`.
  - `_load_schema(version: str = "1.0")` and `_get_validator(version: str = "1.0")` with `@lru_cache(maxsize=len(_SCHEMA_FILES))`.
  - `validate(data)`: `v = data.get("version")`; `key = v if isinstance(v, str) and v in _SCHEMA_FILES else "1.0"`; iterate `_get_validator(key)`. An unknown or missing version therefore reports the v1 `const`/`required` error exactly as today.
  - `schema()` unchanged (returns `_load_schema()` = v1).
  - Module docstring (`:1-6`): name both schema files.
- **GOTCHA**: `version` in `POST /validate-document` bodies is arbitrary JSON; a list is unhashable and `v in dict` would raise `TypeError` (500). The `isinstance(v, str)` guard is required. Add a test (Task 6).
- **GOTCHA**: keep a default argument so `schema()` and any external `_load_schema()` caller keep v1 behaviour (only internal callers exist: `:1480`, `:1492`).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_email_design_document.py -q` (expect only `test_wrong_version` red until Task 6).
- **SATISFIES**: AC 3, AC 4.

### Task 5: UPDATE `EmailDesignDocument` fields, `to_json`, `from_json`

- **IMPLEMENT**:
  - Add `body: tuple[BodyNode, ...] = ()` as the last field (`:1438`), with `BodyNode` imported under the existing `TYPE_CHECKING` block (`:42-44`) from `app.design_sync.dsl.nodes`.
  - `__post_init__`: `if self.version != "2.0" and self.body: raise ValueError("body requires version 2.0")`. This is the "never silently drop `body`" guard on the Python side.
  - `to_json`: after `"layout"`, `if self.version == "2.0": d["body"] = [n.to_json() for n in self.body]` (always written for v2, even empty, because v2 requires it).
  - `from_json`: read `version = data["version"]` first. `"1.0"`: if `"body" in data` raise `ValueError("Malformed EmailDesignDocument: body is not allowed in version 1.0")`; `body = ()`. `"2.0"`: function-level `from app.design_sync.dsl.nodes import body_from_json`; `body = body_from_json(data["body"])`. Anything else: `raise ValueError(f"Unsupported EmailDesignDocument version: {version!r}")`. Keep the existing `except (KeyError, TypeError)` wrapper around the whole construction.
- **GOTCHA**: `to_json` must not emit `body` for `"1.0"`. Emitting `"body": []` would break v1 byte identity and fail v1's root `additionalProperties: false`.
- **GOTCHA**: test helpers construct `EmailDesignDocument` by keyword (`_make_document`, `test_email_design_document.py:45`); a new last field with a default breaks none of them (grep `EmailDesignDocument(` positional calls: none found in `git grep` at base; re-check).
- **GOTCHA**: `import_service.py:239` catches `ValueError`; an unsupported version or a v1-with-body document therefore falls back to the legacy re-fetch (spec N2 path) instead of 500-ing. Do not add a new exception type.
- **GOTCHA**: read `data["version"]` **inside** the existing `try`. `test_import_service.py:686` and `:747` give the import service a snapshot `{"schema": "email-design-document-v1"}` with no `version`; today that `KeyError` becomes `ValueError` and the import falls back to the legacy path. Reading `version` before the `try` turns it into an uncaught `KeyError`.
- **GOTCHA**: `version != "2.0"` (not `== "1.0"`) in `__post_init__`, so an unknown version string cannot carry a body either.
- **VALIDATE**: `uv run mypy app/design_sync/email_design_document.py app/design_sync/dsl && uv run pyright app/design_sync/email_design_document.py app/design_sync/dsl`.
- **SATISFIES**: AC 1, AC 2, AC 4.

### Task 6: UPDATE `app/design_sync/tests/test_email_design_document.py`

- **IMPLEMENT**:
  - `test_wrong_version` (`:207`): change `"2.0"` → `"3.0"` (2.0 is now valid-shaped and fails on missing `body` instead). Keep the assertion.
  - ADD `test_non_string_version_reports_error`: `version: ["1.0"]` → `validate` returns a non-empty list, no exception.
  - ADD `test_v1_with_body_key_fails_validation_and_load`: `validate` error path `(root)` mentions `body`; `from_json` raises `ValueError`.
  - ADD `test_unsupported_version_from_json_raises_value_error` (`"3.0"`).
  - ADD `test_v1_constructor_rejects_body`: `EmailDesignDocument(version="1.0", …, body=(<RawNode>,))` raises `ValueError`.
  - ADD `test_v1_to_json_has_no_body_key` on `_make_full_document()`.
- **PATTERN**: `TestSchemaValidation` (`:173`), `TestRoundtrip.test_malformed_raises_value_error` (`:391`).
- **GOTCHA (RED-first)**: write these before Tasks 4–5 and record the failing run; `test_v1_with_body_key…`'s `from_json` half and `test_v1_constructor_rejects_body` are red on the base.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_email_design_document.py -q`.
- **SATISFIES**: AC 1, AC 4.

### Task 7: CREATE `app/design_sync/tests/test_document_v2.py`

- **IMPLEMENT**:
  - `_all_nine_body()` helper: one `WrapperNode` → `SectionNode` → `ColumnNode` holding one each of text (`font_stack=("Inter", "Helvetica", "sans-serif")`), image, button, divider, spacer, raw; plus a top-level `RawNode` and a top-level `SectionNode`. Leaf payloads (`DocumentText`, `DocumentImage`, `DocumentButton`) are **taken from case 5's `from_legacy` sections** (first text/image/button found), so the v2 fixture carries real payloads, not invented ones.
  - `test_v2_all_nine_round_trip_and_validate`: `doc = replace(case5_doc, version="2.0", body=_all_nine_body())`; `j = doc.to_json()`; `validate(j) == []`; `json.dumps(EmailDesignDocument.from_json(json.loads(json.dumps(j))).to_json()) == json.dumps(j)`; and `{n.type for n in walk(doc.body)} == set(NodeType)`.
  - `test_v2_unknown_node_type_fails_validation`: copy `j`, set the column's first child `type` to `"carousel"`; assert the only error path is `body.0.children.0.children.0.children.0.type` and the message names `'carousel'` (control: the unmutated `j` validated clean above). *(Amended after PR #475 F2: this bullet first pinned every path to `body.0`, which was the `oneOf` behaviour. That instruction is reversed.)* `test_v2_errors_point_at_the_bad_field` pins the other three prototyped shapes at their deep paths: unknown top-level type → `body.0.type`, upper-case hex → `…children.3.color`, section with only `raw` children → `body.0.children.0.children`. Also `from_json` raises `ValueError`.
  - `test_v2_illegal_nesting_fails`: a `node_text` directly under `body` → error path `body.<index>.type` (`enum`); `from_json` raises `ValueError`.
  - `test_v2_missing_body_fails_validation`.
  - Corpus (parametrized over `discover_cases()` that have `structure.json` and `tokens.json`; `pytest.skip` otherwise, as `test_converter_data_regression.py:132`): `test_case_v1_round_trip_byte_identical` (`json.dumps` equality after `from_json`) and `test_case_v1_document_validates` (`validate(doc.to_json()) == []`). This is the ledger's `closes_when` test.
  - `TestSchemaParity`: v2 `$defs[k] == v1 $defs[k]` for every v1 key; v2 `properties` minus `body`/`version` equals v1's; `set(v2.required) == set(v1.required) | {"body"}`; new defs == `{f"node_{t.value}" for t in NodeType} | {"container_style", "hex6", "sizing"}`.
  - Enum parity (checked mapping rule): `set(NODE_CLASSES) == set(NodeType)`; schema `sizing.enum` == `{s.value for s in Sizing}`; `node_text.role.enum` == `TextRole`; `node_divider.style.enum` == `DividerStyle`; `node_button.align.enum` == `HorizontalAlign`; `container_style.vertical_align.enum` == `VerticalAlign`.
- **PATTERN**: `regression_runner.run_case_conversion` steps (`regression_runner.py:48-61`) for building the case document.
- **GOTCHA**: build the v2 fixture from a case document only **after** Task 1 (before it, the case document itself fails v1/v2 validation, and "unknown type fails" would prove nothing).
- **GOTCHA (mutation check, all halves)**: (M1) revert Task 1's `maxItems` change in the **v1 file only** → `test_case_v1_document_validates` goes red on all 7, `TestSchemaParity` goes red (shared `$defs` differ), and `test_v2_all_nine_round_trip_and_validate` stays **green** (it validates against the v2 file, which still has 1000). (M2) drop `"body"` from v2 `required` → `test_v2_missing_body_fails_validation` goes red and the round-trip test stays green. Run both mutations, record all five results.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_document_v2.py -q`.
- **SATISFIES**: AC 1, AC 2, AC 3, AC 6.

### Task 8: CREATE `app/design_sync/dsl/tests/__init__.py`, `app/design_sync/dsl/tests/test_nodes.py`

- **IMPLEMENT**: per node type, `X.from_json(x.to_json()) == x` with every optional field set, and once with all optionals absent (asserting omitted keys). `ContainerStyle` with scalar radius and 4-tuple radius. The per-container helpers reject a `column` under `body` and a `text` under `section` with `ValueError`. `TextNode` rejects `font_stack=()` and `("Inter",)`. Unknown `type` string → `ValueError`.
- **VALIDATE**: `uv run pytest app/design_sync/dsl/tests -q`.
- **SATISFIES**: AC 2, AC 3.

### Task 9: UPDATE `app/design_sync/tests/test_golden_roundtrip.py`

- **IMPLEMENT**: in `test_schema_valid` (`:83-87`) add one assertion: `json.dumps(EmailDesignDocument.from_json(doc.to_json()).to_json()) == json.dumps(doc.to_json())` (import `json`). Golden components through `HtmlImportAdapter` are the second "committed v1 document" source.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_golden_roundtrip.py -q`.
- **SATISFIES**: AC 1.

### Task 10: UPDATE `.agents/deferred-items.json`

- **IMPLEMENT**: close `phase-53.7-typography-maxitems-cap` per `.claude/skills/deferred-items/SKILL.md` Close step (`status: closed`, `closed_commit: "pending"`, a `notes` line: all 7 cases emit 234, cap raised to 1000 in v1+v2, guarded by `test_case_v1_document_validates`). Append a `notes` line to `ce-6-sizing-horizontal-dropped-at-document-bridge`: CE-26 left it for CE-16. **Add** a new `speculative` entry `ce-26-whole-file-documents-exceed-v1-caps` (phase `ce-26`): the 2 local persisted rows are a whole design-system file ("The Ultimate Email Design System (Community)": 397 sections vs cap 100, section texts 103 vs 50, `element_gaps` 106 vs 100, content-group texts 73 vs 50; observed 2026-10-05). They load and round-trip, but `validate()` rejects them; latent because no load path validates. `closes_when`: either the caps are sized for whole-file imports or whole-file snapshots stop being persisted as one document. Not fixed here: raising those caps is outside the user's 2026-10-05 decision (typography + `dividers` only).
- **VALIDATE**: `uv run python -c "import json; json.load(open('.agents/deferred-items.json'))"`.
- **SATISFIES**: ledger.

### Task 11: UPDATE `app/design_sync/routes.py:887` docstring and regenerate the SDK

- **IMPLEMENT**: `validate_document` docstring → `"Validate a JSON body against the EmailDesignDocument schema for its version (1.0, 2.0)."` (amended: `or 2.0` trips the `falsy-numeric-trap` hook). Then `make sdk-snapshot && make sdk-local` (no running backend needed, `Makefile:262-266`).
- **GOTCHA**: only `cms/packages/sdk/openapi.json` and `cms/packages/sdk/src/client/sdk.gen.ts` should change, one description line each. Any other SDK churn means the snapshot picked up unrelated drift: stop and report it rather than committing it.
- **GOTCHA**: `get_document_schema`'s docstring (`:869`) still says v1 and is still true; leave it.
- **VALIDATE**: `make sdk-check` (exits 0) and `git diff --stat cms/` shows exactly the two files. Then `make ci-fe` (the diff now touches `cms/`; CLAUDE.md Definition of Done).
- **SATISFIES**: AC 8.

### Task 12: ADD endpoint test for the relaxed v1 schema; write the PR-body note

- **IMPLEMENT**: in `TestDocumentEndpoints` (`test_email_design_document.py:541`), extend `test_get_schema_v1` (`:567`): served `$defs.tokens.properties.typography.maxItems == 1000` and `"dividers" in $defs.column.properties`. Add `test_validate_document_accepts_v2` posting the Task 7 v2 JSON → `valid is True`.
- **IMPLEMENT (PR body, for `piv-create-pr`)**: a "Schema contract change" section stating (1) v1 was relaxed, not reshaped, against the issue's "unchanged v1 file" wording, by user decision 2026-10-05, because every committed case failed v1 validation; (2) a relaxation cannot invalidate a valid v1 document (derived: only a `maxItems` bound rises and one optional property is added); (3) `GET /schema/v1` is served with `Cache-Control: public, max-age=86400` (`routes.py:875-878`), so a client may hold the old, stricter copy for up to 24 h; the old copy rejects more, never accepts something the new one rejects (derived), so a stale cache cannot let an invalid document through. Put this text in the implementation report so the PR step copies it.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_email_design_document.py -q -k "schema_v1 or accepts_v2"`.
- **SATISFIES**: AC 6, AC 8.

---

## TESTING STRATEGY

### Unit Tests
`app/design_sync/dsl/tests/test_nodes.py` (node shapes and guards) and the additions to
`test_email_design_document.py` (dispatch, guards). Pure, no I/O.

### Integration Tests
No DB, network or WebSocket surface. The real-data checks are the corpus tests in `test_document_v2.py`
(7 committed cases via `from_legacy`) and the golden-component round trip (Task 9).

### Edge Cases

| Edge case | Verified in |
|---|---|
| v1 document with a stray `body` key | `test_v1_with_body_key_fails_validation_and_load` |
| `version` missing / unknown / non-string | `test_missing_version` (existing), `test_wrong_version`, `test_non_string_version_reports_error` |
| v2 with `body: []` | `test_v2_*`: empty body validates (no `minItems` on root `body`) — add one assertion in Task 7 |
| v2 without `body` | `test_v2_missing_body_fails_validation` |
| unknown node type / illegal nesting | Task 7 + Task 8 tests |
| scalar vs per-corner radius | Task 8 |
| `font_stack` without a trailing generic | Task 8 |
| persisted v1 rows in a real DB | Level 4 step 2 |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
- `uv run ruff format --check app/design_sync && uv run ruff check --no-fix app/design_sync`
- `uv run mypy app/ && uv run pyright app/`

### Level 2: Unit Tests
- `uv run pytest app/design_sync/dsl/tests app/design_sync/tests/test_document_v2.py app/design_sync/tests/test_email_design_document.py app/design_sync/tests/test_golden_roundtrip.py -q`
- `uv run pytest app/design_sync -q -m "not integration and not benchmark and not visual_regression and not collab"` (includes `test_converter_data_regression.py` ladder `test_ladder_no_drift`, `:266`).
- `make test` rewrites `date:` in `app/ai/agents/*/skill-versions.yaml`; restore before committing.

### Level 3: Full gate
- `make check-full` (includes `fidelity-gate`, `flag-audit`, `check-env-drift`; no flag or setting is added, so the last two are unaffected). Then `git diff` again: `make lint` inside it rewrites files.
- `make ci-fe` and `make sdk-check` (Task 11 touches `cms/packages/sdk/`).
- No eval gate: the diff touches nothing under `app/ai/`.

### Level 4: Manual Validation
1. **Converter byte identity.** Re-run Task 0's dump into `$SCRATCH/after`; `diff -r $SCRATCH/before $SCRATCH/after` prints nothing. Record "7/7 byte-identical (observed)".
2. **Persisted rows.** The local dev DB holds 2 `design_token_snapshots.document_json` rows, both `"1.0"` (observed 2026-10-05). Run:
   `psql -h localhost -U Berzins -d merkle_email_hub -At -c "select document_json from design_token_snapshots where document_json is not null" > $SCRATCH/db_docs.jsonl`, then
   `uv run python -c "import json; from app.design_sync.email_design_document import EmailDesignDocument as E; rows=[json.loads(l) for l in open('$SCRATCH/db_docs.jsonl')]; print([json.dumps(E.from_json(d).to_json(), sort_keys=True)==json.dumps(d, sort_keys=True) for d in rows])"`
   → `[True, True]`. (`sort_keys` because JSONB does not keep key order.) Baseline at `b9cccdf8`-equivalent code: `[True, True]` (observed 2026-10-05). `validate()` on these rows reports the whole-file cap errors logged in Task 10; after the change the typography error is gone and the others remain (expected).
3. **API.** With `make dev` up: `curl -s localhost:8891/api/v1/design-sync/schema/v1 | jq '.["$defs"].tokens.properties.typography.maxItems'` → 1000 (router prefix `/api/v1/design-sync`, `routes.py:70`). `POST /validate-document` with the Task 7 v2 JSON → `{"valid": true}`.
4. **A3.** HTML is byte-identical (step 1), so A3 before = after by construction (derived: identical HTML → identical render input). Record that line instead of a scoring run; run `scripts/score-fidelity-cases.py` only if step 1 shows any diff, which is itself a stop.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1 — Every committed v1 document round-trips byte-identically: 7/7 `data/debug` cases (Task 7) and the golden components (Task 9).
- [ ] AC 2 — A v2 document using all nine node types validates and round-trips byte-identically (Task 7).
- [ ] AC 3 — A v2 document with an unknown node `type` fails validation with one error at that node's `type` path, and fails to load with `ValueError`. *(Amended after PR #475 F2: was "errors at `body.0` only".)*
- [ ] AC 4 — `"1.0"` loads with `body=()` against the v1 file; a v1 document with `body` is rejected by both `validate` and `from_json`; unknown versions raise `ValueError`.
- [ ] AC 5 — Converter output byte-identical on all 7 cases (Level 4 step 1); ladder unchanged.
- [ ] AC 6 — `validate()` returns `[]` for every case's `from_legacy` document (closes `phase-53.7-typography-maxitems-cap`).
- [ ] AC 7 — `make check-full` and `make ci-fe` green on the head (observed, named in the report).
- [ ] AC 8 — `/validate-document` accepts v2 and says so in its docstring; SDK regenerated and `make sdk-check` passes; `/schema/v1` serves the relaxed caps; the PR body carries the schema-contract note.

---

## COMPLETION CHECKLIST

- [ ] Tasks 0–12 done in order, each VALIDATE run
- [ ] RED runs recorded for Task 6/7 tests before the code change
- [ ] Both mutation checks in Task 7 run, five results recorded
- [ ] `make check-full` green; `git diff` re-read after it; skill-versions yaml dates restored
- [ ] Level 4 steps 1–3 run, results tagged observed
- [ ] Ledger edited; report at `.claude/reports/ce-26-document-schema-v2-report.md`

---

## OPEN QUESTIONS / ASSUMPTIONS

- **Decided (user, 2026-10-05):** relax v1 and v2 together (typography cap + `dividers`). This departs from the issue's "unchanged v1 file"; the PR body states it and why (every real document failed v1 validation).
- A1 — Typography ceiling 1000 is a chosen bound (expected), 4.3× the observed 234 (derived: 1000/234). Change it in Task 1 if the reviewer prefers another bound; nothing else depends on the number.
- A2 — `raw.reason` is a free string matching `^[a-z][a-z0-9_.]*$`, not an enum: the reason codes are the builder's (FR6) and do not exist yet. CE-19 may tighten it to an enum; that is a v2 change before any v2 document is persisted (re-plan trigger T-F).
- A3 — `ContainerStyle` is shared by wrapper, section and column, so a field meaningless on one container (e.g. `full_width` on a column) is representable. The compiler (CE-19) ignores or rejects it. Splitting per container adds three near-identical defs for no reader today.
- A4 — Persisted-row check is local-only (2 rows, both load and round-trip, observed). Production rows, if any, are not reachable from here; the relaxation argument (no valid v1 document can become invalid; `from_json` for `"1.0"` is unchanged apart from the `body` key check) covers them (derived).

## NOTES

- **Why copy v1 into v2 instead of `$ref`-ing it.** A cross-file `$ref` needs a `referencing.Registry`, and the public `GET /schema/*` consumers would receive a schema that does not resolve on its own. A self-contained copy plus `TestSchemaParity` gives the same single-source guarantee with no resolver.
- **Why `validate` falls back to v1 for unknown versions** rather than returning a custom error: it keeps today's error text for `"3.0"`/missing versions, so the API's existing behaviour and tests stay the same apart from `"2.0"`.
- **Why `from_json` does not enforce S2 minimums.** The loader has never validated (persisted documents load without `validate`); adding validation to the loader would change the v1 path. The schema owns structure; the dataclass owns type tags and the parent-child type table.
- **Corpus facts (observed 2026-10-05 probe on `94e84b95`):** sections per case 5:15, 6:9, 7:21, 8:11, 9:11, 10:17, reframe:16; typography 234 on all 7.

## AMENDMENTS

- 2026-10-05 — Risks R1–R3 from the planning report closed before execution. R1: Task 12 adds an endpoint test and the PR-body schema-contract note (stale-cache argument). R2: typing pattern prototyped and pinned in Task 3 (check-before-parse found by the prototype). R3: Task 11 brings the validate-route docstring and SDK regen into scope. Also: `version` read inside the `try` (versionless snapshot tests), error-path assertions pinned to `body.0`, persisted-row probe run and a new deferred entry for whole-file cap breaches.
- 2026-10-05 (execution, report `.claude/reports/ce-26-document-schema-v2-report.md` D1–D10):
  - Task 11 docstring reads `(1.0, 2.0)`. The `falsy-numeric-trap` hook flags `1.0 or 2.0`.
  - Task 2: v2 was generated from the post-Task-1 v1 with `json.dumps(indent=2)` instead of being hand-copied. Each container's `contains` also requires `type: object` and `type`.
  - Task 7/8: the v2 tests and node tests could not be RED-first, because they need `dsl.nodes`. M1 and M2 stand in for that. M2 also turns `test_root_properties_v1_plus_body` red.
  - Extra tests:
    - `test_v2_empty_body_validates`
    - `test_node_type_consts`
    - `test_column_rejects_section_child`
    - `test_container_style_rejects_wrong_length`
    - `test_missing_type_raises_key_error`
  - Task 4: `schema()` calls `_load_schema("1.0")` so it shares the validator's cache key.
  - Unknown node types raise `NodeType`'s own `ValueError`, without the `Malformed` prefix.
  - Level 4 step 3: `POST /validate-document` was not run live (it needs auth). The TestClient test covers it.
- 2026-10-05 (PR #475 review fixes, `.claude/reports/pr-475-review-fixes.md`):
  - F1: `nodes._px` coerces every int length field. A whole float loads as `int`; a bool or fraction raises `TypeError` → `ValueError`. The loader and `validate()` now accept the same lengths.
  - F2: the four child unions dispatch on `type` with `if`/`then` instead of `oneOf`, so errors report at the failing field. AC 3, the Task 7 bullets and the line-149 reference are amended. The schema accepts the same documents (18 shapes probed against both schemas, 0 disagreements). `validate()` keeps the first and last 120 characters of a longer message.
  - F3: `from_json` also turns `AttributeError` into `ValueError`.
