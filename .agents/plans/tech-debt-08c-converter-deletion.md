# Tech Debt 08c — Delete Legacy Converter Path (`converter.py` Wholesale Removal)

**Source:** Continuation of `.agents/plans/tech-debt-08-converter-god-functions-followup.md` §D3. The original D3 understated test-migration scope — this plan replaces it.
**Scope:** Delete `convert`, `convert_mjml`, `_convert_recursive`, `node_to_email_html`, all per-node renderers, and `app/design_sync/converter.py` itself. Extract 12 reusable helpers to new homes first. Migrate ~30 shim-test callsites to the modern `convert_document` path. Delete or migrate ~50+ `node_to_email_html` test callsites depending on which behavior is still load-bearing.
**Estimated effort:** **One full session (~3-4 hours).** Plus one short follow-up session if any extracted helper produces import cycles.
**Prerequisite:** Tech Debt 08 + 08-followup Parts A/B/C/D1 all merged (already on `main`). Static check confirmed zero non-test, non-self callers of the shims (this session, 2026-05-06).

## Why this plan replaces D3

The original D3 step assumed extraction work was limited to `_relative_luminance` + `_contrast_ratio`. A static check on 2026-05-06 found:

- **8 production modules** import helpers from `app/design_sync/converter.py` (not just 2 — see "Helper extraction targets" below).
- **~30 test callsites** of `service.convert(...)` and `service.convert_mjml(...)` — these were missed because the original grep filtered qualified-name patterns only.
- **~50+ test callsites** of `node_to_email_html` — these test the legacy node renderer that has **zero production callers** post-Part-A/B.

D2's 14-day calendar window does not detect any of this — it only detects unknown *production* callers, not test or helper coupling. Static analysis already proves no production caller exists; this plan deals with the test/helper coupling D3 didn't anticipate.

## Findings addressed

- **F013** — legacy converter shims still wired (Critical). After this plan: `app/design_sync/converter.py` deleted; `_convert_recursive` deleted; both shim methods deleted. Mark RESOLVED in `TECH_DEBT_AUDIT.md`.

## Static-analysis snapshot (do not re-derive — captured 2026-05-06)

### Production helpers imported from `app/design_sync/converter.py`

| Helper | Importer | Notes |
|---|---|---|
| `_relative_luminance` | `app/design_sync/import_service.py:841` | |
| `_relative_luminance`, `_contrast_ratio` | `app/design_sync/quality_contracts.py:18` | |
| `_relative_luminance`, `_contrast_ratio` | `app/design_sync/token_transforms.py:591` | |
| `_relative_luminance` | `app/design_sync/bgcolor_propagator.py:20` | |
| `_relative_luminance`, `convert_colors_to_palette` | `app/design_sync/brief_generator.py:5` | |
| `_relative_luminance` | `app/ai/agents/scaffolder/prompt.py:177` | |
| `convert_colors_to_palette` | `app/ai/agents/scaffolder/prompt.py:156` | |
| `convert_spacing` | `app/design_sync/import_service.py:599` | |
| `sanitize_web_tags_for_email` | `app/design_sync/import_service.py:817` | |
| `sanitize_web_tags_for_email` | `app/design_sync/diagnose/runner.py:13` | |
| Multi-import tuple | `app/design_sync/converter_service.py:18-25` | `_has_visible_content`, `_NodeProps`, `_sanitize_css_value`, `convert_colors_to_palette`, `convert_typography`, `node_to_email_html` |
| Multi-import tuple | `app/design_sync/mjml_template_engine.py:18` | (verify with `grep -A 6 "from app.design_sync.converter import" app/design_sync/mjml_template_engine.py`) |
| Multi-import tuple (inside function) | `app/design_sync/diagnose/runner.py:239` | |
| `_NodeProps` (TYPE_CHECKING) | `app/design_sync/render_context.py:15` | |

### Test imports from `app/design_sync/converter`

| Helper | Test file(s) |
|---|---|
| `node_to_email_html` | `test_builder_annotations`, `test_converter_fixes`, `test_spacing_pipeline`, `test_spacing_layout`, `test_image_pipeline`, `test_penpot_converter`, `test_semantic_html`, `test_multi_column`, `test_dark_mode_gradients`, `test_design_sync_images`, `test_typography_pipeline` |
| `_next_slot_name` | `test_builder_annotations` |
| `_meaningful_alt` | `test_image_pipeline` |
| `_render_style_runs` | `test_converter_fixes` |
| `_gradient_to_css` | `test_dark_mode_tokens`, `test_dark_mode_gradients` |
| `_font_stack` | `test_typography_pipeline` |
| `convert_typography`, `convert_spacing`, `sanitize_web_tags_for_email`, `convert_colors_to_palette` | various |

### Shim callsites in tests

`DesignConverterService.convert(...)` — **22 callsites in 9 files:**

```
test_section_cache.py:           410, 420, 437, 457, 537, 542, 581, 595, 605
test_penpot_converter.py:        682, 973, 1086, 1127, 1167, 1289
test_builder_annotations.py:     161, 180, 199, 232
test_dark_mode_gradients.py:     68, 116
test_dark_mode_tokens.py:        293, 333
test_design_sync_images.py:      236, 268
test_e2e_pipeline.py:            344, 352
test_html_formatter.py:          475, 530
test_converter_fixes.py:         80, 116
test_snapshot_visual.py:         121
```

`DesignConverterService.convert_mjml(...)` — **8 callsites in 2 files:**
```
test_mjml_convert.py:            103, 120, 136, 150, 168, 182, 196
test_e2e_mjml_pipeline.py:       519
```

## Pre-flight

```bash
git checkout -b refactor/tech-debt-08c-converter-deletion
make check                                  # baseline must be green
make snapshot-test                          # establish snapshot baselines
make snapshot-visual                        # establish pixel baselines
cp -r data/snapshot/baseline data/snapshot/baseline.before
make eval-golden                            # secondary safety net
```

If any baseline fails on `main`, fix that *first* on a separate branch — don't proceed until green.

---

## Part 1 — Extract production helpers (independent commit)

This part lands first as its own commit so it can revert cleanly if any importer breaks.

### 1.1 New module: `app/shared/color.py`

Extract:
- `_relative_luminance(hex_color: str) -> float` → rename to `relative_luminance` (drop underscore — public)
- `_contrast_ratio(c1: str, c2: str) -> float` → rename to `contrast_ratio`

Re-export the legacy private names from `app/design_sync/converter.py` as deprecated aliases for one PR cycle:

```python
# app/design_sync/converter.py — kept until Part 5
from app.shared.color import contrast_ratio as _contrast_ratio
from app.shared.color import relative_luminance as _relative_luminance
```

Migrate all 6 production importers to `from app.shared.color import relative_luminance, contrast_ratio` (drop the underscore prefix on import). Run `rg "_relative_luminance|_contrast_ratio" app/` after migration — the only remaining hits should be the deprecated aliases in converter.py.

### 1.2 Helper consolidation in `app/design_sync/`

The remaining production helpers are domain-specific to design_sync, not general-purpose color math. Move them to existing siblings:

| Helper | New home | Rationale |
|---|---|---|
| `convert_colors_to_palette` | `app/design_sync/token_transforms.py` (already imports from here) | All callers go through token_transforms |
| `convert_typography` | `app/design_sync/token_transforms.py` | Same module category |
| `convert_spacing` | `app/design_sync/token_transforms.py` | Same module category |
| `sanitize_web_tags_for_email` | `app/design_sync/sanitizers.py` (new file, ~40 LOC) | Single-responsibility utility, used by import_service + diagnose/runner |
| `_has_visible_content`, `_sanitize_css_value` | `app/design_sync/sanitizers.py` (private, prefix preserved) | Used only by converter_service after Part 5 |
| `_NodeProps` | `app/design_sync/protocol.py` (already exports DesignNode etc.) | Type lives near related types |

Update all importers. **Do not delete the originals from `converter.py` yet** — keep deprecated re-exports to prevent multi-file PR coupling. Drop them in Part 5.

### 1.3 Verify Part 1

```bash
uv run ruff format app/design_sync/ app/shared/color.py app/ai/agents/scaffolder/prompt.py
uv run ruff check --fix app/design_sync/ app/shared/color.py app/ai/agents/scaffolder/prompt.py
make types
make test app/design_sync/ app/shared/ app/ai/agents/scaffolder/ -v
make snapshot-visual          # zero pixel diff vs baseline.before
```

**Commit:** `refactor(design_sync): extract color helpers + sanitizers from converter.py (08c part 1)`

---

## Part 2 — Migrate shim-callsite tests to `convert_document` (independent commit)

Goal: every test that calls `service.convert(structure, tokens, ...)` or `service.convert_mjml(...)` must be rewritten to call `service.convert_document(EmailDesignDocument.from_legacy(structure, tokens, ...), ...)` — the same transformation the shim performs internally. After this part, the shims have zero callers anywhere.

### 2.1 Migration template

Before:
```python
result = service.convert(structure, tokens, use_components=True, connection_id="conn1")
```

After:
```python
from app.design_sync.email_design_document import EmailDesignDocument

document = EmailDesignDocument.from_legacy(structure, tokens)
result = service.convert_document(document, use_components=True, connection_id="conn1")
```

For `use_components=False` callsites (legacy recursive path):
- These tests are exercising `_convert_recursive` → `node_to_email_html`. That path is being deleted in Part 4.
- **Decide per file:** if the test asserts something the modern path also covers (component output), migrate; if it asserts node-renderer-specific HTML structure that no longer applies, **delete** the test in the same commit.

### 2.2 Per-file plan

| File | Action | Why |
|---|---|---|
| `test_section_cache.py` (9 calls) | **Migrate** | Tests the cache feature, which lives on the modern path. |
| `test_penpot_converter.py` (6 calls) | **Migrate 4, delete 2** | The 4 mid-file calls test penpot adapter integration (still alive). The 2 trailing calls assert specific node-renderer HTML — delete with the file's other `node_to_email_html` callsites in Part 4. |
| `test_builder_annotations.py` (4 calls) | **Migrate or delete entire file** | All 4 use `use_components=False`. This entire file tests the legacy renderer's slot-counter behavior — **delete the file** in Part 4 along with the `node_to_email_html` callsites. |
| `test_dark_mode_gradients.py` (2 calls) | **Delete** | `use_components=False` — legacy-only behavior. Move any still-useful gradient-token assertions to `test_dark_mode_tokens.py` (which tests `_gradient_to_css` directly). |
| `test_dark_mode_tokens.py` (2 calls) | **Migrate** | Tests dark-mode token extraction (still alive in modern path). |
| `test_design_sync_images.py` (2 calls) | **Migrate** | Tests image-handling integration. |
| `test_e2e_pipeline.py` (2 calls) | **Migrate** | E2E pipeline still uses convert_document. |
| `test_html_formatter.py` (2 calls) | **Migrate** | Tests `format_email_html` integration — formatter runs on modern path output too. |
| `test_converter_fixes.py` (2 calls) | **Migrate** | Tests bug-fix regressions for modern-path-relevant behavior. |
| `test_snapshot_visual.py` (1 call) | **Migrate (critical)** | Snapshot-test safety net — must continue working. |
| `test_mjml_convert.py` (7 calls) | **Migrate to `convert_document_mjml`** | Tests MJML compile path, still alive. |
| `test_e2e_mjml_pipeline.py` (1 call) | **Migrate to `convert_document_mjml`** | Same. |

### 2.3 Verify Part 2

```bash
rg -n "\.convert\(structure|\.convert_mjml\(" app/design_sync/tests/ app/connectors/tests/
# Must return zero hits.

make test app/design_sync/ app/connectors/ -v
make snapshot-visual          # zero pixel diff
```

**Commit:** `test(design_sync): migrate shim callsites to convert_document (08c part 2)`

---

## Part 3 — Delete the shims (independent commit)

`app/design_sync/converter_service.py:446-606` — delete:
- The `# ── Legacy entry points (shim to document path) ──` comment header
- `def convert(...)` (446-529) including all telemetry/deprecation plumbing
- `async def convert_mjml(...)` (531-606) including all telemetry/deprecation plumbing

Drop now-unused imports — re-grep:
```bash
grep -nE "^(import|from)" app/design_sync/converter_service.py
# Then verify each is still referenced:
grep "normalize_tree" app/design_sync/converter_service.py   # only in deleted methods → drop
```

Expected drops after Part 3:
- `from app.design_sync.figma.tree_normalizer import normalize_tree` (only used by the two shims)

Keep:
- `inspect`, `_stdlib_warnings as warnings` — still used by `_convert_recursive`'s telemetry block (deleted in Part 4, not yet)
- `MjmlCompileError` — still raised by `convert_document_mjml` path

### 3.1 Verify Part 3

```bash
uv run ruff format app/design_sync/converter_service.py
uv run ruff check --fix app/design_sync/converter_service.py
make types
make test app/design_sync/ -v
make snapshot-visual
```

**Commit:** `refactor(design_sync): delete legacy convert/convert_mjml shims (08c part 3 / F013)`

---

## Part 4 — Delete `_convert_recursive`, `node_to_email_html`, and `converter.py`

### 4.1 Delete `_convert_recursive`

`app/design_sync/converter_service.py:1144-end-of-method` — delete the entire method, including its 3-line telemetry block. After this, `inspect` and `_stdlib_warnings` imports become unused — drop them.

Verify no callers remain:
```bash
rg "_convert_recursive" app/
# Only hit should be the line in the conversion_phases.py docstring referring to history — fine to leave or update.
```

### 4.2 Delete the legacy node-renderer test files

These files test `node_to_email_html` and its per-node renderers, all dead post-Part-A/B. Delete entirely:

```
app/design_sync/tests/test_builder_annotations.py
app/design_sync/tests/test_image_pipeline.py
app/design_sync/tests/test_spacing_pipeline.py
app/design_sync/tests/test_spacing_layout.py
app/design_sync/tests/test_multi_column.py
app/design_sync/tests/test_semantic_html.py
```

For files that test node behavior *and* still-useful helpers, surgically delete the relevant test classes/functions but keep the helper tests:

| File | Surgery |
|---|---|
| `test_converter_fixes.py` | Delete all `node_to_email_html(...)` test methods + the `_render_style_runs` test class. Keep helper tests if any remain. |
| `test_typography_pipeline.py` | Delete `node_to_email_html` test methods. Keep `_font_stack` and `convert_typography` tests (move them to `test_token_transforms.py` if appropriate). |
| `test_dark_mode_tokens.py` | Already migrated by Part 2. Keep `_gradient_to_css` tests — extract `_gradient_to_css` to `app/design_sync/dark_mode.py` (or wherever dark-mode helpers live) before deletion. |
| `test_dark_mode_gradients.py` | Deleted in Part 2. Confirm. |
| `test_design_sync_images.py` | Migrated in Part 2. Verify no `node_to_email_html` calls remain (some are in standalone test methods, not via service). Delete those methods. |
| `test_penpot_converter.py` | Delete the ~70 `node_to_email_html` test methods. Keep penpot-adapter integration tests migrated in Part 2. |

After surgery, `rg "node_to_email_html|_next_slot_name|_meaningful_alt|_render_style_runs" app/` should show zero hits in `app/design_sync/tests/`.

### 4.3 Extract or delete remaining test-only helpers

| Helper | Decision | New home or fate |
|---|---|---|
| `_gradient_to_css` | **Extract** | `app/design_sync/dark_mode_gradient.py` (new, ~30 LOC) — kept because dark-mode token tests still cover real behavior |
| `_font_stack` | **Extract** | `app/design_sync/token_transforms.py` — shares concerns with `convert_typography` |
| `_meaningful_alt`, `_render_style_runs`, `_next_slot_name` | **Delete** | Test-only, tests for them deleted in 4.2 |

### 4.4 Delete `app/design_sync/converter.py`

After 4.1–4.3, the file's only contents should be:
- The deprecated re-export aliases for `_relative_luminance`/`_contrast_ratio` from Part 1
- `node_to_email_html` and per-node renderers (`_render_text_node`, `_render_image_node`, `_render_image_only_frame_node`, `_render_frame_node`)
- `_NodeProps` (already moved to protocol.py in Part 1, so this is a deprecated re-export too)

Final grep before deletion:
```bash
rg "from app.design_sync.converter import|from app\.design_sync import converter" app/ --type py
# Expected output: empty (or only test files we haven't deleted yet — fix those)
```

Then `git rm app/design_sync/converter.py`.

### 4.5 Verify Part 4

```bash
uv run ruff format app/design_sync/
uv run ruff check --fix app/design_sync/
make types
make check                    # full suite
make snapshot-test
make snapshot-visual          # MUST be zero pixel diff
make eval-golden
```

**Commit:** `refactor(design_sync): delete converter.py and legacy renderer tests (08c part 4 / F013)`

---

## Part 5 — Cleanup deprecated re-exports & ledger updates

### 5.1 Drop the Part 1 deprecated aliases

The aliases in `converter.py` are gone with the file in Part 4. Confirm no caller still imports `_relative_luminance` / `_contrast_ratio` (private names) anywhere — `rg "_relative_luminance|_contrast_ratio" app/` must return zero hits.

### 5.2 Update plan ledgers

- `.agents/plans/tech-debt-08-converter-god-functions-followup.md` — check off **Part D3** in the Done When list; reference this plan as the executor.
- `.agents/deferred-items.json` — close any entry whose `closes_when` matches "F013 shims removed" (re-grep with `python3 -c "import json; print([i for i in json.load(open('.agents/deferred-items.json')) if 'F013' in str(i)])"`); if none exist, no-op.
- `TECH_DEBT_AUDIT.md` — mark **F013** as RESOLVED with this PR's commit SHA.
- `TODO.md` Operational follow-ups — delete the `2026-05-11 — F013 D3 readiness check` row (D3 is done; the readiness check is moot).

**Commit:** `chore(design_sync): close F013 ledger entries (08c part 5)`

---

## Verification (final)

```bash
make check
make test app/ -v
make snapshot-test
make snapshot-visual          # zero pixel diff vs baseline.before
make eval-golden
make converter-data-regression
```

Then `rm -rf data/snapshot/baseline.before` once you're satisfied.

## Rollback

Each Part (1/2/3/4/5) is an independent commit and an independent revert. The riskiest is Part 4 because it's a large file deletion — `git revert` will restore everything in one commit. Part 1 is the safest revert.

If `_relative_luminance` extraction (Part 1) creates an import cycle, fold it back into `app/design_sync/converter.py` and pick a different shared module — `app/shared/color.py` should have no imports from `app.design_sync.*`, but if any helper accidentally pulls in design_sync types, the cycle surfaces immediately and is fixable in the same commit.

## Risk notes

- **Snapshot tests are the only signal that Part 4 is non-destructive.** If they go red, revert immediately and investigate before re-trying.
- **`mjml_template_engine.py:18` import-tuple** wasn't fully expanded in the static check. Re-grep before Part 1 to confirm what it imports — if it pulls a helper not listed in Part 1, add it to the extraction set.
- **`diagnose/runner.py:239`** has an inline (function-scoped) import that may be hidden from grep without `rg --multiline`. Re-verify before Part 4.
- **Part 2 test surgery is the longest manual step.** Don't try to script it — each file's tests were written for different reasons; the `migrate vs delete` call requires reading what the test asserts. Budget half the session for Part 2 alone.

## Done when

- [ ] **Part 1** — `app/shared/color.py` exists with `relative_luminance` + `contrast_ratio`; 6 production importers updated; 5 design_sync helpers moved to `token_transforms.py`/`sanitizers.py`/`protocol.py`; `make snapshot-visual` zero diff.
- [ ] **Part 2** — `rg "\.convert\(structure|\.convert_mjml\(" app/design_sync/tests/ app/connectors/tests/` returns zero hits; all migrated tests pass.
- [ ] **Part 3** — `convert` and `convert_mjml` deleted from `converter_service.py`; `normalize_tree` import dropped; `make snapshot-visual` zero diff.
- [ ] **Part 4** — `_convert_recursive` deleted; legacy node-renderer test files deleted or surgically trimmed; `_gradient_to_css` + `_font_stack` extracted; `app/design_sync/converter.py` deleted; `rg "from app.design_sync.converter" app/` returns zero hits.
- [ ] **Part 5** — Plan ledgers updated; F013 marked RESOLVED in `TECH_DEBT_AUDIT.md`; `2026-05-11` readiness-check row removed from `TODO.md`.
- [ ] **Final verification** — `make check`, `make snapshot-test`, `make snapshot-visual` (zero diff), `make eval-golden`, `make converter-data-regression` all green.
- [ ] **PRs** (5 sequential commits, can be a single PR or split):
  - `refactor(design_sync): extract color helpers + sanitizers from converter.py (08c part 1)`
  - `test(design_sync): migrate shim callsites to convert_document (08c part 2)`
  - `refactor(design_sync): delete legacy convert/convert_mjml shims (08c part 3 / F013)`
  - `refactor(design_sync): delete converter.py and legacy renderer tests (08c part 4 / F013)`
  - `chore(design_sync): close F013 ledger entries (08c part 5)`
