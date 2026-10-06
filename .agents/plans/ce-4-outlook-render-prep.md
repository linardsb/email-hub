# Feature: CE-4 part 1 — Outlook render-source inventory, decision doc, per-design HTML export

The following plan should be complete, but validate documentation and codebase patterns and task sanity before you start implementing. Pay attention to the names of existing utils, types and models; import from the right files.

## Feature Description

CE-4 (#422) asks for a decision on where classic-Outlook (Word engine) renders come from, and one render per design. On 2026-10-06 the user deferred the source choice (Litmus, Email on Acid, or an own Windows + classic-Outlook rig) and chose option O1: ship everything that does not depend on that choice. This plan delivers:

1. An inventory of `app/rendering/`, with the result written as observed facts.
2. `docs/outlook-render-source.md`: the options, what each needs, the selection criteria, and the interim position (HD2), with the decision marked **pending**.
3. `scripts/export-outlook-cases.py`: writes each case's current converter HTML plus the images it references into a self-contained bundle. Every render-source option needs this bundle as input.

This PR is **Part of #422**, not "Closes #422". The renders and the button report stay owed.

## User Story

As the converter-epic owner
I want the Outlook render-source options costed and the per-design input bundle ready
So that, once I pick a source, the renders for #422 are one script run plus one upload away, and #437 is unblocked without re-research.

## Problem Statement

Every Outlook finding in the epic (R10, CE-11 AC 9, CE-19 kill test 3) is inferred from markup; nothing in the repo renders through the Word engine. The epic assumed `app/rendering/litmus|eoa` might be reusable. Its slice text says "wiring to the converter not checked". The inventory below shows they are placeholders. The converter's image srcs (`/api/v1/design-sync/assets/<node>.png`) resolve only behind the live API, so no external renderer could load the images even with a working client.

## Solution Statement

Record the inventory and the options in a decision doc. Ship a small export script that turns each case into `<out>/<case>/email.html` plus `<out>/<case>/assets/*.png`, with srcs rewritten to relative paths, or to absolute URLs under `--asset-base-url`. It also writes a `manifest.json` (head sha, HTML sha256, image and `v:roundrect` counts). The script deliberately does **not** call `RenderingProvider` (see NOTES N1).

## Out of Scope / Non-Goals

- Not included: choosing the render source. It stays pending, and the user decides later.
- Not included: any real Litmus or EoA client, API key wiring, own-rig automation (pywin32), or renders. These are owed by #422 after the decision.
- Not included: the button report (CE-4 done-check leg 3). Owed by #422, and it needs renders.
- Not changing: `app/rendering/**` code, including the placeholder providers and the `RenderingConfig.provider="litmus"` default. Logged to the ledger (Task 5), not fixed.
- Not changing: converter output. No diff under `app/design_sync/` except one new test file, so no A3 run, no baseline regen and no ladder impact.
- Not included: the image-hosting setup itself (bucket, CDN). The doc costs it per option; the script only rewrites srcs to a given base URL.

## Feature Metadata

**Feature Type**: New Capability (docs + tooling)
**Estimated Complexity**: Low
**Primary Systems Affected**: `docs/`, `scripts/`, `app/design_sync/tests/` (new test only), `.agents/deferred-items.json`
**Dependencies**: none new (stdlib `hashlib`, `json`, `shutil`, `re`, `argparse`)

## Related Work

**Implements**: #422 (CE-4), part 1 of 2 · **Epic**: #439, slice text `.agents/plans/converter-epic-slices.md:104-111`; DSL spec `docs/architecture/dsl-compiler.md:225` (HD2)

**Back-references**:
- `.agents/plans/converter-epic-slices.md:57` — Q5 "Outlook render source: Litmus Instant API vs manual" is an open user input. This plan adds the own-rig option and keeps Q5 open.
- `docs/architecture/dsl-compiler.md:225` — HD2 default "no spend; markup inspection, marked inferred". Inherited as the interim position, not re-decided.
- `.agents/plans/ce-11-vml-every-button.md:388` — AC 9 (stroke grows the VML box?) owed by #422. Still owed after this PR.
- `docs/fidelity-gate.md` — the CE-1 gate. It renders Chromium only, and its asset-commit rule makes this export CI-testable.

**Forward-references**:
- (to be created after the source decision) CE-4 part 2: provider client or rig script, the renders, the button report. Closes #422.

## Deferred Items Touching This Plan

Grep run 2026-10-06: open entries whose text mentions Word engine / classic Outlook / `app/rendering` / Litmus / EoA / CE-4, plus `code_refs` matching `scripts/score-fidelity-cases.py` and `fidelity_case_scorer.py`.

| id | match (phase / code_ref) | decision | why |
|----|--------------------------|----------|-----|
| `phase-53.7-asset-reexport-prerequisite` | asset availability for renders | carry forward | The export copies only committed node-keyed assets. All 7 cases have every referenced asset committed (observed below), so the export is unaffected. Full-res re-export stays that entry's job. |
| `phase-53f-f7-card-wrapper-outlook-ghost-overflow` | "unverified in the Word engine" | none (closed) | Closed by G9's static ghost-arithmetic gate (`app/design_sync/tests/test_outlook_ghost_arithmetic.py`). Listed so the reader sees it was checked. A real render in part 2 can re-confirm it, but no open entry owns it. |
| `ce-9-peel-row-fixed-width-wrap` | matched `fidelity_case_scorer` text | avoid | Chromium viewport behaviour; unrelated to the export. |

---

## CONTEXT REFERENCES

### Inventory result (observed 2026-10-06, reading the source at HEAD `be80a746`)

| Component | What it is | Usable as a classic-Outlook source? |
|---|---|---|
| `app/rendering/litmus/service.py:1-44` | Docstring "placeholder implementation"; `submit_test` returns `litmus_test_{hash%100000}`, `get_results` returns two hard-coded `https://placeholder.litmus.com/...` URLs | No: no HTTP call, no key read |
| `app/rendering/eoa/service.py:1-40` | Same shape, `placeholder.emailonacid.com` URLs | No |
| `app/rendering/service.py:76-80,93-104` | `SUPPORTED_PROVIDERS` = litmus/eoa/local; `_get_provider` instantiates the class with no args (API keys never passed) | No |
| `app/core/config/rendering.py:33-35` | `provider: str = "litmus"  # litmus, eoa, mock`; comment lists `mock`, registry has `local` | Default routes real callers to the mock (ledger, Task 5) |
| `app/rendering/local/profiles.py:109-116` | `outlook_desktop` profile: `browser="cr"`, comment "Word engine — CSS preprocessing only" | No: Chromium |
| `app/rendering/local/emulators.py:338+` | Word-engine emulator = regex stripping of unsupported CSS, MSO-conditional handling | No: cannot draw VML (`v:roundrect`), fails the ticket's wrong-if line |
| `app/rendering/sandbox/` | Mailpit/Roundcube SMTP sandbox | No: the brief already records "Mailpit renders nothing" (`converter-epic-slices.md:57`, brief, not re-run) |
| `app/rendering/gate.py`, `visual_diff.py` | Pre-send confidence gate over local profiles; odiff wrapper | Consumers of renders, not sources |
| Converter → rendering wiring | `app/design_sync/fidelity_service.py:162-163` and `visual_verify.py:246-247,397` import the **local** Chromium provider, runner, crop and odiff; nothing in `app/design_sync` touches litmus/eoa | Chromium only; no classic-Outlook path exists |

### Per-case export inputs (observed 2026-10-06, `run_case_conversion` over `data/debug/<case>` on HEAD `be80a746`)

| case | HTML bytes | `src=` asset refs | CSS `url('…')` asset refs | `v:roundrect` | `[if mso` | committed assets (`git ls-files`) |
|---|---|---|---|---|---|---|
| 5 | 52690 | 6 | 2 | 16 | 58 | 6 |
| 6 | 31094 | 11 | 0 | 4 | 23 | 11 |
| 7 | 85662 | 23 | 0 | 18 | 57 | 23 |
| 8 | 40911 | 10 | 0 | 4 | 33 | 10 |
| 9 | 38407 | 11 | 0 | 4 | 28 | 13 |
| 10 | 55125 | 17 | 0 | 4 | 43 | 17 |
| reframe | 59009 | 13 | 0 | 6 | 47 | 16 |

Every `src=` node is distinct in every case, and case 5's two `url('…')` refs (`background-image` on band tables) point at nodes that also appear as `src=`. No other reference form occurs (observed: a context scan of every `/api/v1/design-sync/assets/` hit). Each case converts byte-identically twice in one process (observed), so test 4 tests the export, not converter noise. `structure.json` is committed for all 7 cases (`git ls-files 'data/debug/*/structure.json'`). The implementer re-derives them from `manifest.json` in Task 4; any difference means main moved, so record the new figures and don't copy these.

### Relevant Codebase Files — READ BEFORE IMPLEMENTING

- `app/design_sync/tests/regression_runner.py:48-61` — `run_case_conversion(case_dir)`: the default-path conversion every gate uses. Returns `None` when structure/tokens are missing.
- `app/design_sync/fidelity_case_scorer.py:164-187` — `_ASSET_SRC_RE` and `_rewrite_asset_srcs`: the `:`→`_` asset naming to mirror. It matches `src="…"` only; the export needs both forms (Task 3). Don't import the private helper (N3).
- `scripts/prepare-fidelity-fixtures.py:70-97` — owns the asset-commit rule: commits the nodes `_ASSET_SRC_RE` finds in current output (downscaled to ≤600px). Explains why committed sets can exceed current refs (N4).
- `app/design_sync/fidelity_gate.py:434-438` — `gated_cases()`: case ids with a committed `reference_1x.png` (the 7 cases). Use it as the case list.
- `app/design_sync/fidelity_gate.py:449-462` — `current_commit()`: short HEAD sha (honours `FIDELITY_COMMIT`).
- `scripts/score-fidelity-cases.py:1-100` — script shape: module docstring with usage, `REPO` + `sys.path.insert`, `argparse`, `main()`, output under `.tmpscratch/` (gitignored, `.gitignore:311`).
- `app/design_sync/tests/test_jev_shadow.py:463-470` — `_report_script()`: the importlib pattern for testing a hyphen-named script.
- `docs/fidelity-gate.md` — doc register to match: plain sentences, `file:line` refs, headed sections.
- `.claude/skills/deferred-items/SKILL.md` — the Add step for Task 5.

### New Files to Create

- `docs/outlook-render-source.md` — inventory, options, criteria, interim position, pending decision.
- `scripts/export-outlook-cases.py` — the per-case bundle exporter.
- `app/design_sync/tests/test_outlook_export.py` — unit tests over the real committed cases.

### Files to Modify

- `.agents/deferred-items.json` — one new entry (Task 5).

### Relevant Documentation

- Litmus and Email on Acid API docs: find and open the current pages in Task 6, and record every vendor capability as "vendor-documented, not tried".
- Microsoft "Considerations for unattended automation of Office" (Microsoft Learn): cited as the reason an own rig is a dev machine, not CI or a service. Open it before citing (Task 6 gotcha).

### Patterns to Follow

- **Logging**: scripts here `print` (see `scripts/score-fidelity-cases.py:83-90`); no `get_logger` needed.
- **Lint**: `scripts/` is in ruff scope. `subprocess` use would need `# noqa: S607` as at `fidelity_gate.py:455`; avoid it by calling `current_commit()`.
- **Typing**: tests are typed (`-> None`); the importlib loader returns `Any` (`test_jev_shadow.py:463`).

---

## IMPLEMENTATION PLAN

### Phase 0: Branch
Branch `feature/ce-4-outlook-render-prep` from `origin/main`. The current checkout `feature/ce-27-dsl-case-runner` carries unrelated uncommitted files; don't carry them over. This plan and its `.html` brief are untracked on that checkout, so copy both into the new branch's `.agents/plans/` first.

### Phase 1: RED tests
Write `test_outlook_export.py` against the not-yet-existing script; it fails on load.

### Phase 2: Export script
Write the script until the tests pass.

### Phase 3: Docs + ledger
**Independent of:** Phases 1–2, except that the doc's usage section names the script's flags.

---

## STEP-BY-STEP TASKS

### 1. CREATE branch

- **IMPLEMENT**: the main checkout holds the user's uncommitted CE-27 files, so never stash or switch it. Run, in order:
  1. `git fetch origin && git worktree add ../email-hub-ce4 -b feature/ce-4-outlook-render-prep origin/main`
  2. Copy the env file with the one form the PreToolUse hook allows, a bare `cp .env ../email-hub-ce4/.env` as its own command. Then `cp .agents/plans/ce-4-outlook-render-prep.md .agents/plans/ce-4-outlook-render-prep.html ../email-hub-ce4/.agents/plans/`
  3. `cd ../email-hub-ce4 && uv sync --frozen && (cd cms && pnpm install --frozen-lockfile)`; `check-full` runs `check-fe`, which needs `node_modules`.
  4. Don't run `make db` (compose ports collide with main's containers; memory `reference_local_dev_spinup_topology`). This ticket needs no DB.
- **VALIDATE**: `git -C ../email-hub-ce4 log -1 --oneline` equals `git rev-parse --short origin/main`; `git -C ../email-hub-ce4 status --short` lists only the two copied plan files.
- **SATISFIES**: process.

### 2. CREATE `app/design_sync/tests/test_outlook_export.py` (RED)

- **IMPLEMENT**: load the script via `_export_script()` (mirror `test_jev_shadow.py:463-470`, path `scripts/export-outlook-cases.py`). One `scope="module"` fixture `exports` builds, for every case in `gated_cases()`: the converter HTML (`run_case_conversion`), a relative export under `tmp_path_factory.mktemp("rel")`, a base-URL export under `tmp_path_factory.mktemp("abs")`, and both manifest rows. It returns `dict[str, CaseExport]` (a small `NamedTuple` in the test file). Each test takes `@pytest.mark.parametrize("case", gated_cases())` and indexes the dict. Tests:
  1. `test_no_api_asset_ref_survives`: the substring `/api/v1/design-sync/assets/` appears nowhere in `email.html` (covers `src=` and CSS `url('…')`; case 5 is the one with both).
  2. `test_every_relative_src_has_a_copied_file`: default mode; every `src="assets/<f>"` exists under `<case>/assets/`, and the manifest's `missing_assets` is `[]`.
  3. `test_base_url_mode_rewrites_absolute`: `asset_base_url="https://cdn.example.test/ce4/5"`; every rewritten src starts with it and ends `.png`.
  4. `test_markup_unchanged_except_asset_refs`: `re.split(r"/api/v1/design-sync/assets/[^\"')\s]+?\.png", converter_html)` equals `re.split(r"assets/[^\"')\s]+?\.png", exported_html)`. That means the same text between refs and the same number of refs. Sound because `assets/` occurs in converter output only inside the API path (observed 2026-10-06: `html.count("assets/") == html.count("/api/v1/design-sync/assets/")` for all 7 cases). This guards against the script altering what Outlook would render.
  5. `test_manifest_counts_match_file`: `sha256` equals the hash of the written bytes; `roundrect` and `mso_blocks` equal `.count("v:roundrect")` and `.count("<!--[if mso")` of the **written file** (not the converter HTML); `commit` is non-empty.
- **PATTERN**: convert each case once per module (`scope="module"` fixture with `tmp_path_factory`) and export twice (relative and base-URL); about 7 conversions, not 42. Real fixtures only (CLAUDE.md "Evidence"). `structure.json`, `tokens.json` and the referenced assets are committed (`.gitignore:145-160`, `git ls-files` table above), so these run in CI. Add `pytest.skip` if `run_case_conversion` returns `None`, mirroring the converter tests.
- **GOTCHA**: test 4 is the one that catches a script that "fixes" markup (for example by stripping MSO comments). Mutation check: add `html = html.replace("<!--[if mso", "<!--[if x")` just before the write. Expected: test 4 red on all 7 cases; tests 1, 2, 3 and 5 green (5 stays green because its counts are read from the written file). Run the whole file under the mutation, paste the pass/fail line per test into the report, then revert and re-run green.
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_outlook_export.py -q` fails at load (RED, observed).
- **SATISFIES**: AC 3, AC 4.

### 3. CREATE `scripts/export-outlook-cases.py`

- **IMPLEMENT**: module constant `ASSET_REF_RE = re.compile(r"/api/v1/design-sync/assets/([^\"')\s]+?)\.png")`, public function `export_case(case: str, out_dir: Path, *, asset_base_url: str | None = None) -> dict[str, object]`, plus `main()`. Under 120 lines in total (expected).
  - Convert with `run_case_conversion(DEBUG_DIR / case)`; raise `SystemExit` naming the case if `None`.
  - `ASSET_REF_RE` matches the bare path, so `src="…"` and `url('…')` are both rewritten (case 5 needs the second). Replace each match with `assets/<node with : → _>.png`, or `<asset_base_url.rstrip('/')>/<same>.png`. Copy each referenced file that exists from `data/debug/<case>/assets/` into `<out>/<case>/assets/`, and record the rest in `missing_assets`.
  - Write `<out>/<case>/email.html` (utf-8).
  - Return the manifest row: `case`, `commit` (`current_commit()`), `sha256`, `bytes`, `img_srcs`, `roundrect`, `mso_blocks`, `missing_assets`.
  - `main()`: `--cases` (default `gated_cases()`), `--out` (default `.tmpscratch/outlook-export`), `--asset-base-url` (used as given, so pass a per-case base if hosting per case; document this). Write `<out>/manifest.json` and print one line per case.
- **PATTERN**: `scripts/score-fidelity-cases.py:1-45` (docstring/usage, `REPO`, `sys.path.insert`, `# noqa: E402` imports).
- **IMPORTS**: `from app.design_sync.tests.regression_runner import run_case_conversion` (precedent: a script importing it, `scripts/prepare-fidelity-fixtures.py:34`); `from app.design_sync.fidelity_gate import DEBUG_DIR, current_commit, gated_cases`. Lint: `scripts/**` ignores `T201` (print) and `D` (`pyproject.toml:183`). mypy and pyright cover `app/` only (`Makefile:133-135`, `pyproject.toml:335`), so type the script anyway but expect no checker on it.
- **GOTCHA**: don't inline images as `data:` URIs. Classic Outlook is widely reported not to display them (expected, not verified here; part 2 can test it on a real render). Don't import `_rewrite_asset_srcs`: it emits `file://` URIs, which no external renderer can load.
- **GOTCHA**: no `RenderingProvider` call (N1).
- **VALIDATE**: `uv run pytest app/design_sync/tests/test_outlook_export.py -q` green; `uv run python scripts/export-outlook-cases.py` prints 7 rows; then run the Task 2 mutation and record which tests go red.
- **SATISFIES**: AC 3, AC 4.

### 4. RE-DERIVE the per-case table

- **IMPLEMENT**: from `.tmpscratch/outlook-export/manifest.json`, rebuild the "Per-case export inputs" table and paste it into the doc (Task 6) tagged `observed (export-outlook-cases.py at <sha>)`.
- **VALIDATE**: `python3 -c "import json;print(json.load(open('.tmpscratch/outlook-export/manifest.json')))"`.
- **SATISFIES**: AC 2.

### 5. ADD ledger entry `ce-4-rendering-providers-placeholder`

- **IMPLEMENT**: follow `.claude/skills/deferred-items/SKILL.md` Add (steps 1–4; grep for `placeholder` and `litmus` first to rule out a duplicate). The id and phase format follow the latest CE entries (`ce-26-whole-file-documents-exceed-v1-caps`, `phase: "ce-26"`).
  - `id: "ce-4-rendering-providers-placeholder"`, `title: "Litmus and Email on Acid providers are placeholders, and the default provider is Litmus"`, `phase: "ce-4"`, `severity: "known-bug"`, `introduced: "2026-10-06"`, `introduced_commit: "pending"`.
  - `summary`: Litmus/EoA providers return mock IDs and placeholder URLs; `RenderingConfig.provider` defaults to `litmus`, so `POST /api/v1/rendering/tests` (`app/rendering/routes.py:47` prefix, `:54` decorator, 201) "succeeds" on fake screenshots; `_get_provider` passes no API key.
  - `code_refs`: `app/rendering/litmus/service.py:10 (LitmusRenderingService)`, `app/rendering/eoa/service.py:10 (EoARenderingService)`, `app/rendering/service.py:93 (_get_provider)`, `app/core/config/rendering.py:33 (provider)`.
  - `symptom_if_broken`: rendering-test results list `placeholder.*.com` screenshot URLs.
  - `closes_when`: CE-4 part 2 implements the chosen provider for real, or the default becomes a non-mock provider and the placeholders refuse to run.
- **GOTCHA**: append with a JSON-aware edit (load, append, `json.dump(..., indent=2, ensure_ascii=False)` plus a trailing newline) only if it reproduces untouched entries byte for byte. Check with `git diff --stat` (expect only added lines). Otherwise insert the object as text before the closing `]` of `items`.
- **VALIDATE**: `python3 -c "import json;json.load(open('.agents/deferred-items.json'))"`, then `grep -n ce-4-rendering-providers-placeholder .agents/deferred-items.json`.
- **SATISFIES**: AC 5.

### 6. CREATE `docs/outlook-render-source.md`

- **IMPLEMENT** sections:
  1. **Status**: decision pending (user, 2026-10-06). Interim = HD2 (`docs/architecture/dsl-compiler.md:225`): no spend; Outlook findings come from markup inspection and are marked inferred.
  2. **Requirement**: classic Outlook, Word engine. A source that renders only new Outlook or Outlook.com fails (the ticket's wrong-if line). Must show `v:roundrect` buttons (CE-11 AC 9, CE-19 kill test 3).
  3. **What exists**: the inventory table above, condensed, `file:line` cited.
  4. **Options**: a table with one row each for Litmus, Email on Acid, own rig, and manual.
     - Columns: Word engine?, versions/DPI covered, image handling, credentials/spend, repeatability, work to land (files, rough lines, expected).
     - Own rig: Windows 11 ARM VM (Parallels/UTM) + classic Outlook (M365 Apps or Office LTSC) + a pywin32 script: `MailItem.HTMLBody` → `Inspector.WordEditor.ExportAsFixedFormat` PDF → PNG. Mark this route "expected, not tried". Fallback: window screenshot. Limits: one version and one DPI per VM image; Microsoft does not support unattended automation (link), so it is a dev machine, not CI.
     - Vendor rows: every capability "vendor-documented, not tried".
  5. **Images**: srcs must be absolute URLs reachable from the renderer: `--asset-base-url` after uploading `<out>/<case>/assets/`. The own rig and manual options may instead attach images as CID (part 2). `data:` URIs are excluded (Task 3 gotcha).
  6. **Storage of renders**: options are repo (downscaled PNG), `.tmpscratch` with an external link, or an artifact store. Decided in part 2 against measured render sizes. No figure is given now (expected).
  7. **Input bundle**: usage of `scripts/export-outlook-cases.py`, and the Task 4 table.
  8. **What part 2 does once a source is picked**: client or rig script, one render per case from the bundle, the button report (radius, fill, stroke, size, and whether the stroke grows the box — CE-11 D8/AC 9).
- **PATTERN**: `docs/fidelity-gate.md` register.
- **GOTCHA**: no vendor pricing figures (unverified). Every figure is tagged observed/derived/expected (CLAUDE.md "Claims"). Open each external URL (WebFetch) before citing it; cite one that does not resolve by title only. N5 goes in the report, not the doc.
- **VALIDATE**: `grep -c "file:\|\.py:" docs/outlook-render-source.md` > 0; `grep -n "pending" docs/outlook-render-source.md` shows the status line.
- **SATISFIES**: AC 1, AC 2.

### 7. RUN the gate

- **IMPLEMENT**: precheck `docker info >/dev/null && echo up`. The `fidelity-gate` prerequisite runs in the pinned Playwright image (`Makefile:180-181,203`). If Docker is down, run `colima stop --force && colima start` (memory: Colima half-broken state). Then `make check-full`, then `git diff` (lint rewrites files); restore `app/ai/agents/*/skill-versions.yaml` if `make test` re-dated them.
- **VALIDATE**: `make check-full` exits 0 (observed, named in report). `git diff --stat origin/main...HEAD` lists only the 4 files.
- **SATISFIES**: AC 6.

---

## TESTING STRATEGY

### Unit Tests
`app/design_sync/tests/test_outlook_export.py`: 5 tests × 7 cases, real committed fixtures, no browser, runs under `make test` and CI.

### Integration Tests
None. There is no renderer to integrate with in this part. The script run in Task 3 is the end-to-end check for the bundle.

### Edge Cases

| Edge case | Where verified |
|---|---|
| Asset referenced but not committed | `missing_assets` field; test 2 asserts `[]` for all current cases |
| Same node referenced twice | test 2 (file exists once, both srcs resolve) |
| Trailing slash on `--asset-base-url` | test 3 uses no slash; `rstrip('/')` in the implementation; Level 4 step 2 uses a trailing slash |
| Script mutates markup | test 4 + Task 2 mutation check |
| Case without structure.json | `SystemExit` naming the case; Level 4 step 3 |

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style
- `uv run ruff format --check scripts/export-outlook-cases.py app/design_sync/tests/test_outlook_export.py`
- `uv run ruff check --no-fix scripts/export-outlook-cases.py app/design_sync/tests/test_outlook_export.py`
- `uv run mypy app/` and `uv run pyright app/` (`make types`)

### Level 2: Unit Tests
- `uv run pytest app/design_sync/tests/test_outlook_export.py -q`

### Level 3: Full gate
- `make check-full`. No eval gate: no diff under `app/ai/`. No A3: converter output is unchanged (test 4 proves the export copies it verbatim apart from srcs).

### Level 4: Manual Validation
1. `uv run python scripts/export-outlook-cases.py`, then `open .tmpscratch/outlook-export/7/email.html`: images load from the relative `assets/`, buttons render (Chromium, so the non-MSO path).
2. `uv run python scripts/export-outlook-cases.py --cases 5 --asset-base-url https://cdn.example.test/x/`: `grep -o 'https://cdn.example.test/x/[^"'"'"')]*' .tmpscratch/outlook-export/5/email.html | wc -l` = 8 (derived: 6 `src=` + 2 `url()`, table above; re-check against the manifest). `grep -c` would count lines, not hits.
3. `uv run python scripts/export-outlook-cases.py --cases nosuch`: exits non-zero, naming `nosuch`.

---

## ACCEPTANCE CRITERIA

- [ ] AC 1: `docs/outlook-render-source.md` merged with the decision marked pending, HD2 as interim, the four options costed against the Word-engine requirement, and the image strategy stated.
- [ ] AC 2: the inventory of `app/rendering/` is recorded with `file:line` evidence and states that no existing component is a classic-Outlook source; the per-case table is re-derived from the export (observed).
- [ ] AC 3: `scripts/export-outlook-cases.py` writes a bundle per case for all `gated_cases()`, with no API-only asset refs left (`src=` or CSS `url()`) and every referenced asset copied.
- [ ] AC 4: the export does not alter converter markup apart from asset refs (test 4, mutation-checked).
- [ ] AC 5: ledger entry `ce-4-rendering-providers-placeholder` added.
- [ ] AC 6: `make check-full` green on the head.
- [ ] AC 7 (**owed by #422**): one classic-Outlook render per design stored or linked. Blocked on the render-source decision (user, 2026-10-06).
- [ ] AC 8 (**owed by #422**): report on what each render shows about buttons (CE-10 baseline; also CE-11 AC 9).

PR body: "Part of #422" (not Closes), so #422 and its block on #437 stay visible.

---

## COMPLETION CHECKLIST

- [ ] Tasks 1–7 done in order, each VALIDATE run
- [ ] Mutation check recorded (both halves)
- [ ] `make check-full` green, `git diff` re-read after lint
- [ ] Only the 4 planned files in `git diff --stat origin/main...HEAD`
- [ ] Report at `.claude/reports/ce-4-outlook-render-prep-report.md`, figures tagged

---

## RISK REGISTER (all closed at planning time, 2026-10-06)

| R | Risk | Closed by |
|---|---|---|
| R1 | Asset refs in forms other than `src=` stay API-only | Context scan over all 7 outputs: only `src="` and `url('` occur (observed); `ASSET_REF_RE` covers both; test 1 asserts the bare path is gone |
| R2 | Test 4 tests converter noise, not the export | Each case converted twice in one process came out byte-identical (observed); test 4 uses one conversion per case from the module fixture |
| R3 | Test 4's split regex catches unrelated `assets/` text | `count("assets/") == count("/api/v1/design-sync/assets/")` for all 7 (observed) |
| R4 | Tests skip in CI because inputs are gitignored | `git ls-files` lists `structure.json` for all 7 and every referenced asset (observed); CI runs `pytest -m "not integration"` (`.github/workflows/ci.yml:56`) |
| R5 | Mutation check proves only half | Task 2 gotcha names the expected red and green per test and runs the whole file under the mutation |
| R6 | `check-full` fails on environment, not code | Docker precheck in Task 7 (Docker up, observed 2026-10-06); the worktree gets `uv sync`, `pnpm install` and the env file (Task 1) |
| R7 | Ledger edit reformats the file | Task 5 gotcha: the diff must show only added lines |
| R8 | Inventory claim wrong | Corrected after a second grep: `app/design_sync` imports the local Chromium renderer only (cited) |
| R9 | Ledger summary cites a wrong route | `POST /api/v1/rendering/tests`, `routes.py:47,54` (opened) |
| R10 | Vendor or Microsoft links in the doc are stale | Task 6: open before citing, else cite by title |
| R11 | `data:` URI claim wrong | Not load-bearing: it only steers the default away from inlining; the doc marks it expected |
| R12 | Coverage gate drop | `--cov=app` (`ci.yml:56`) excludes `scripts/`; the new test only adds coverage |
| R13 | N5 decision blocks the PR | It doesn't: N5 goes in the report, and the user decides on a ledger entry separately |
| R14 | Worktree env copy blocked by the secrets hook | Task 1 uses the one allowed form, a bare `cp <checkout>/.env <worktree>/.env` (hook message, observed 2026-10-06) |

## OPEN QUESTIONS / ASSUMPTIONS

- **Q1 (changed from what was offered)**: when offering O1 I proposed a wrapper "against the existing `app/rendering/protocol.py` interface". The plan drops it (N1): the providers are mocks, so a protocol-driven script would "succeed" on fake screenshots, and fixing the protocol shape now would pre-decide the source. Say if you want it back.
- **A1**: the case list is `gated_cases()` (7 cases incl. reframe). Held-out cases from CE-5 (#423) join automatically once they carry `reference_1x.png`.
- **A2**: `.tmpscratch/outlook-export/` is the default output; nothing render-related is committed in this part.
- **A3**: the "data: URIs don't display in classic Outlook" claim is expected, not verified. It only steers the default away from inlining.

## NOTES (open canvas)

**N1, why no provider seam.** `RenderingProvider` (`app/rendering/protocol.py`) models an async API returning `screenshot_url`s. Litmus and EoA could fit it; the own rig (synchronous, local PDF) and manual upload fit it badly. Building to it now would bias the decision toward a vendor, and calling it today returns placeholder URLs, which is fabricated evidence. Part 2 picks the seam that fits the chosen source.

**N2, why export at all if no source is picked.** Every option consumes the same thing: the converter HTML from current main with images reachable outside the API. The export also gives part 2 a reproducible input (sha256 per case in the manifest), so renders can be tied to a commit.

**N3, why copy the regex rather than import `_rewrite_asset_srcs`.** That helper emits `file://` URIs for Chromium; the export needs relative or hosted URLs. Sharing only the regex constant would mean making a private name public across modules for one line; duplication is the smaller change. If a third consumer appears, promote `_ASSET_SRC_RE`.

**N4, image counts.** Case 9 commits 2 assets current output no longer references (`2833_2126`, `2833_2143`), and reframe commits 3 (`2833_1506`, `2833_1560`, `2833_1596`) (observed). `prepare-fidelity-fixtures.py` allowlisted the nodes the output referenced when it ran, and later converter changes dropped those refs. They are harmless here: the export copies only referenced files. Pruning the allowlist is out of scope.

**N5, found mid-plan, out of ticket.** The CE-1 gate's `_rewrite_asset_srcs` rewrites `src=` only, and the gate blocks non-`file://` requests. So case 5's two CSS `background-image: url('/api/…')` bands render without their image in the gate (inferred from the regex and `docs/fidelity-gate.md` step 2, not rendered). Report it in the implementation report and ask the user whether it gets a ledger entry. Don't fix it here.

## AMENDMENTS

- 2026-10-06 — pre-execution hardening: R1–R14 closed (risk register). Verified the asset ref forms, determinism, CI inputs, route path and Docker state; corrected the inventory wiring row; fixed the test fixture shape, test 4's method, the mutation's expected outcomes and the worktree setup. Confidence 10/10 for one-pass execution, conditional on origin/main not changing converter output before Task 4 (if it does, Task 4 re-derives the table, so the tests are unaffected).
- 2026-10-06 — post-execution (report `.claude/reports/ce-4-outlook-render-prep-report.md`), superseding parts of Tasks 2, 4 and 7:
  - Task 2 PATTERN "about 7 conversions" superseded: `export_case` converts internally, so the fixture makes 21 (~0.2 s each, observed); test 4 stays sound by R2 determinism.
  - Task 3/4: `img_srcs` counts every asset ref, CSS `url()` included (case 5 = 8). The doc table shows exported-file bytes from `manifest.json`, re-derived at `45d71cea` (main moved from `be80a746`; converter bytes unchanged).
  - Task 7 VALIDATE "only the 4 files" superseded: the branch carries 6 (this plan and its `.html` brief land with the work).
  - Task 6: the Email on Acid row records its move into Mailgun Inspect (from June 2026); Mailgun's migration article returned 403 and is cited by title only.
