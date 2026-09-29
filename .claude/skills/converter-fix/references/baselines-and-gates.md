# Baselines and gates

Detail for `converter-fix` steps 1, 3 and 4. Line numbers were opened at base `7e7536e3`; re-check them
if the file has moved.

## What the corpus inputs are

Each case `data/debug/<n>/` holds the converter **inputs** `structure.json` + `tokens.json` and the
**baseline** `expected.html`. `.gitignore:138` ignores `data/debug/*/*`, then `.gitignore:139-146`
allowlists `expected.html`, `manifest.yaml`, `vlm_classifications.json`, `actual-tree-with-fixes.html`,
`actual-with-fixes.html`, `structure.json`, `tokens.json` and `rendered_w600.png`; `.gitignore:149-156`
allowlist case 5's six assets. Local-only (never in a clean checkout): `raw_figma.json`, `design.png`,
`report.json`, `actual.html`, and `assets/` for cases 6 to 10.

Converter seeds are files: editing `email-templates/components/*.html` reaches converter output directly,
so a seed edit is a converter change and runs this whole cycle.

## What runs in CI (and in a fresh worktree)

Every converter fixture test runs in CI for the six corpus cases, because their inputs are tracked. The
fixture-absence skips are defensive and do not fire in a clean checkout. `observed` in the last `ci.yml`
run on main (run 29764095476, head `60c98bc6`, 2026-07-20): `test_snapshot_matches`,
`test_ladder_no_drift` and `test_rendered_matches_target` PASSED for all six cases (case 10's target gate
XFAIL by design); `test_snapshot_regression.py` 34 passed / 10 skipped / 1 xfail and
`test_converter_data_regression.py` 73 passed / 48 skipped / 1 xfail, matching #354's snapshot 34/10/1
and #365's 34 and 73 passed from local runs. Of the 10 snapshot skips, 8 are expectation-conditional (no
expectations for that case). The other 2, `test_reference_bgcolors[6]` and `[10]`, skip because their
reference HTML (`mammut-duvet-day.html`, `starbucks-pumpkin-spice.html`) exists in no checkout
(`test_snapshot_regression.py:431-433`). All 48 converter-data skips are expectation-conditional. The log
carries no `-rs` reasons, so that attribution is `derived` from the skip guards below.

| Test | Skip guard | Fires in CI? |
|---|---|---|
| `test_snapshot_regression.py` (snapshot match, sanity, section count, bgcolor) | `_require_fixtures`, :200-208 (guard :207-208) | no: `structure.json`/`tokens.json` tracked |
| `test_reference_bgcolors` | :431-433 | yes, in every checkout: the reference HTML for cases 6 and 10 is absent |
| `test_converter_data_regression.py` (incl. `TestSectionLadder`, :242-283) | :97, :105, :124, :138, :269, :305 | no. `reframe` is not skipped either: `_converter_case_ids` (:80) and `discover_ladder_case_ids` (`ladder_harness.py:228`) leave it out, and the all-case checks assert on its tracked `expected.html` |
| `test_cta_fidelity.py` corpus pill guard | :1006 | no |
| `test_bridge_roundtrip.py` fixture cases | `skipif(not _FIXTURE_CASES)`, :505 | no |
| `test_layout_analyzer.py` LEGO fixture | :1853 | no |
| `test_fidelity_case_scorer.py` (case 5 A3 metric) | `skipif`, :53-62 | no: case-5 inputs, `rendered_w600.png` and `maap/visual_design.png` are tracked; it scores the committed PNG, no Playwright |
| `test_snapshot_visual.py` | `visual_regression` marker | collects zero cases: every manifest case has `design_image: false` |

What stays out of CI: `scripts/score-fidelity-cases.py` (live Playwright render + gitignored reference
PNGs and assets for cases 6 to 10; see `a3-scoring.md`). The remaining pytest skips are
manifest-conditional ("No X expectations in manifest"), except the two `test_reference_bgcolors` skips above.

Consequence: any change to converter output for cases 5 to 10 fails `test_snapshot_matches` in CI until
`expected.html` is regenerated. A new case becomes CI-gated the moment its inputs and `expected.html` are
committed, so settle its output first.

Stale comments to ignore (report-only, not this skill's job to edit): the docstring at
`test_snapshot_regression.py:201-206` ("They aren't committed", :204-205) and the skip reason at
`test_bridge_roundtrip.py:505` ("gitignored").

## Regen-and-audit recipe (step 3)

`scripts/snapshot-capture.py` takes `case_id`, `--overwrite` and `--output <path>` (script lines 34-40);
without `--overwrite` it refuses to replace an existing file. `make snapshot-capture CASE=<n>`
(Makefile:160-161) hardcodes `--overwrite`, and the `data/debug/manifest.yaml` header recommends it: do
not use it for a fix.

1. Capture every corpus case, not only the targets, to a scratch path:
   `uv run python scripts/snapshot-capture.py <n> --output <scratch>/<n>.html` for n in 5 to 10.
2. Diff each against the baseline: `git diff --no-index --ignore-all-space data/debug/<n>/expected.html
   <scratch>/<n>.html`.
3. Audit line by line: every changed line must trace to the fix. Structural drift (a moved `</table>`, a
   lost row, a changed alt, any `<p>`/`<h*>`) is a bug, not a baseline update. Record per case
   `+N/-M` and what moved.
4. Only for the audited target cases: `uv run python scripts/snapshot-capture.py <n> --overwrite`.
5. Open each moved `expected.html` in a browser, or check the A3 composite (step 5), before committing.

A failing `test_snapshot_matches` writes `data/debug/<n>/actual.html` and prints
`cp {actual_path} {expected_path}` (`test_snapshot_regression.py:262`). That shortcut skips the audit;
use the recipe above.

## The c8 whitespace churn

The converter emits trailing whitespace; the `trailing-whitespace` pre-commit hook
(`.pre-commit-config.yaml:13`) strips it at commit; `_normalize_html` in the snapshot test
(`test_snapshot_regression.py:65`) strips per-line whitespace before comparing. So a regen on unchanged
code can dirty `data/debug/8/expected.html` with whitespace only (#354, #356). Audit with
`--ignore-all-space`, and `git checkout --` a case whose only diff is whitespace.

## The ladder

Committed in `data/debug/ladder_snapshot.json` (per case: `name`, `target`, `candidates`, `analyzed`,
`rendered`, `bands`, `band_desc`, `bags`). `test_ladder_no_drift` (`test_converter_data_regression.py:266`) compares
the live ladder with it; `test_rendered_matches_target` (:301) is the design-target gate, xfail only for
`SEMANTIC_UNDERCOUNT_CASES` (`ladder_harness.py:62`). Print the live ladder with
`python -m app.design_sync.tests.ladder_harness`; `--write` (`ladder_harness.py:293`) rewrites the
snapshot, only after an intended segmentation change, and the snapshot is then committed with the fix.

"Unchanged" means: `git diff origin/main -- data/debug/ladder_snapshot.json` is empty and
`test_ladder_no_drift` passes. The `sections:` values in `data/debug/manifest.yaml` are stale (`observed` at base
`7e7536e3`: case 5 says 9 where the ladder's `rendered` says 13) and are not the ladder.

## Gate map for a converter diff

| When | Command | Notes |
|---|---|---|
| iterating | `uv run ruff check --no-fix <changed files>` | never `ruff --fix` wholesale while iterating |
| iterating | `uv run pytest app/design_sync/tests/ app/components/tests/` | seeds feed both suites |
| iterating | `make snapshot-test`, `make converter-data-regression [CASE=<n>]` | both inside `make test` |
| iterating | `make golden-conformance`, `make lint-numeric` | be-validate Level 7 rows for `app/design_sync/**` |
| ship | `piv-validate` (`make check-full`) | the only gate that counts for Done |
