# Implementation Report — Jev shadow classifier (O1/O2/O3)

**Plan**: `.agents/plans/jev-shadow-classifier.md`   **Branch**: `feat/jev-shadow-classifier` (off `origin/main` `4f704bcd`)   **Status**: COMPLETE (T1–T12; T13 not applicable under D1(a))

## Summary
Built the shadow classifier code path end to end, T1–T9a. It covers the default-off flag, the API key setting, an async REST client, the section→state serializer, the O1/O2/O3 question builders and slot resolver, and the post-hoc `run_jev_shadow` pass that writes to its own JSONL. It also covers the offline runner script and the committed reframe `structure.json`. No converter logic file changed (D1(a)).

T10–T12 were first blocked on the API key (see Issues) and completed on 2026-09-29 (see Addendum):
- T10: the runner wrote 293 records from 92 requests to `traces/jev_shadow.jsonl` (0 errors, 251,644 input tokens; observed).
- T11: `data/debug/jev_shadow_labels.yaml`, labelled blind against `data/debug/jev_shadow_labeling_rules.md` and cross-checked by 4 independent blind labellers.
- T12: `docs/jev-shadow-report.md`. The pre-registered rule gives "don't wire it in" for O1 type, O1 template and O3, and "insufficient evidence" for O2 (n = 5).

## Tasks completed
- T1 → `app/core/config/design_sync.py` (UPDATE): `jev_shadow_enabled`, `jev_api_key: SecretStr`
- T2 → `feature-flags.yaml`, `.env.example` (UPDATE)
- T3 → `app/design_sync/jev_shadow/client.py` (CREATE)
- T4 → `app/design_sync/jev_shadow/state.py` (CREATE)
- T5 → `app/design_sync/tests/test_jev_shadow_state.py` (CREATE)
- T6 → `app/design_sync/jev_shadow/questions.py` (CREATE), with 63 slug descriptions
- T7 → `app/design_sync/jev_shadow/shadow.py`, `__init__.py` (CREATE)
- T8 → `app/design_sync/tests/test_jev_shadow.py` (CREATE)
- T9 → `scripts/jev_shadow_report.py` (CREATE)
- T9a → `data/debug/reframe/structure.json` (CREATE, 272,832 bytes after nulling `image_ref`, observed; see Deviation 12)
- Shared helper → `app/design_sync/tests/jev_shadow_capture.py` (CREATE; see Deviations)
- Gate fix → `app/core/tests/test_config_design_sync.py` (UPDATE; see Deviations)
- T10 → `traces/jev_shadow.jsonl` (gitignored run output)
- T11 → `data/debug/jev_shadow_labels.yaml`, `data/debug/jev_shadow_labeling_rules.md` (CREATE)
- T12 → `docs/jev-shadow-report.md` (CREATE)

## Tests added
`test_jev_shadow_state.py`, 11 tests:
- R1: case 6 `2833:1475` keeps the `mj-social` name and the `Ref: 26-6-NWSL-…` text.
- R2: case 9 `2833:2126` has `inside_button: true` and `icon-sized`.
- R3: case 5 `2833:1643` and `2833:1650` keep the Sub-Headline and bucket the image.
- No hex and no px, plus a counts check, on each of cases 5–10.
- Truncation at a cap lowered to 20.

`test_jev_shadow.py`, 14 tests:
- Enum and slug mappings (ast-derived, 60 + 3).
- Resolver: a shared-node case and a none/exhausted case.
- Client: documented body, 401, malformed body.
- Flag off, and no key.
- Errors: 529 plus `ReadTimeout`.
- R1 disagreement at conf 0.91.
- O3 displaced slot carries its resolved option's probability. Red on the pre-fix code, green after (observed).
- O3 container fills skipped.
- All-agree run with a no-mutation `deepcopy` check.

Result: `uv run pytest app/design_sync/tests/test_jev_shadow_state.py app/design_sync/tests/test_jev_shadow.py -q` gives **25 passed** (observed). After the PR #413 review fixes the same command gives 30 passed (observed; see `.claude/reports/pr-413-review-fixes.md`).

## Validation results
All observed on this branch, 2026-09-28.
- Level 1:
  - `ruff format --check` and `ruff check --no-fix` on the new paths: clean.
  - `mypy`: clean on `scripts/jev_shadow_report.py` plus the package and tests (9 files).
  - pyright: 0 errors.
- Level 2:
  - The 25 tests pass.
  - `make snapshot-test`: 34 passed, 10 skipped, 1 xfailed. That equals the pre-change baseline.
- Level 3: `make check-full` exits 0 on `ddfe6762`, the PR #413 head, re-run in the PR #413 review. The earlier run predated the Addendum files. The run after the review fixes is in `.claude/reports/pr-413-review-fixes.md`.
  - Backend: 8538 passed, 115 skipped, 2 xfailed.
  - mypy: 1384 files clean. pyright: 0 errors.
  - Frontend: 780 vitest tests passed.
  - Flag audit: 0 errors. Env drift: none.
  - `make lint` rewrote nothing. `skill-versions.yaml` dates were restored.
- Scope: `git diff --stat origin/main...ddfe6762` lists 19 files (observed, PR #413 fixes round). Code: `app/design_sync/jev_shadow/`, its tests and capture helper under `app/design_sync/tests/`, `scripts/jev_shadow_report.py`, plus the flag in `app/core/config/design_sync.py`, its test, `.env.example` and `feature-flags.yaml`. Data: `data/debug/reframe/structure.json`, `data/debug/jev_shadow_labels.yaml` and `data/debug/jev_shadow_labeling_rules.md`. Docs: `docs/jev-shadow-report.md`, this report and the plan. No converter logic file appears.
- F2 checks across all 7 cases: section node ids are unique per case, so the record and label keys can't collapse. No section has two asked O3 slots with the same heuristic source, so no disagreement is forced by the resolver.
- T1: the settings one-liner prints `False False`.
- T9a: `make snapshot-test` and the `test_converter_data_regression.py` + `test_bridge_roundtrip.py` run give the same counts before and after the file was added. Snapshot is 34p/10s/1xf; data-regression plus roundtrip is 92p/48s/1xf.
- T9 dry run: `--cases 5,6,7,8,9,10,reframe --dry-run` builds 92 requests with 248 questions and sends nothing. Per case: 15+9+16+11+10+15 on 5–10, plus 16 on reframe.
- AC5 byte-identity: under the `match_all` capture, `_normalize_html(html) == _normalize_html(expected.html)` holds for all six of cases 5–10.
- Plan counts reproduced:
  - Column slugs: 18 of the 76 matches on 5–10.
  - O3 fills on 5–10: 157 total, 72 ineligible, 85 eligible. Of the eligible, 53 are single-source, 2 are `multi_node` and 30 are `unmapped`.
  - O2 candidates: 5. Two on slate (`2833:2126`, `2833:2143`) and three on reframe (`2833:1506`, `1560`, `1596`).
- Request size:
  - Observed: mean 6,962 JSON characters per request, max 8,990.
  - Derived tokens: about 2k per request, assuming about 3.5 characters per token. That is below the plan's 5k-token assumption, so T10's cost estimate of about $0.02 is an upper bound. Expected, not yet run.

## Deviations from the plan
1. **New shared helper `app/design_sync/tests/jev_shadow_capture.py`** (not in the plan's file list). It holds the `match_all` capture, which binds the real function before patching so the side effect can't recurse. The runner and both test files use it, so they see the same shipped matches. It sits beside `regression_runner.py`, and the script imports it the same way it imports `_normalize_html`.
2. **`plan_section()` / `SectionPlan` in `shadow.py`.** The runner's `--dry-run` calls the same builder that `run_jev_shadow` uses, not a parallel copy.
3. **`o1_questions()` takes no `state` argument.** The questions don't depend on the state.
4. **`ShadowRecord.input_tokens`** is set on each section's `o1_type` record only. T10 can then sum token usage from the records without double counting. `run_done` also logs the total.
5. **Client details.**
   - `JevError` subclasses `ServiceUnavailableError`, per the backend rule on the AppError hierarchy. Its signature is `(message, *, status, request_id)`.
   - `SystemOneResponse` carries `request_id` from the `x-typesafe-request-id` header.
   - The API shape was checked against the live `docs.typesafe.ai/api.md` (2026-09-28): answers carry `type`, criteria allow `null`, and `usage.input_tokens` exists.
6. **State details the plan left open.**
   - The section `width` bucket is `narrow` / `partial` / `full`, relative to a 600-wide email.
   - `_scrub` replaces any hex or px in names and text with `[colour]` / `[size]`. No corpus name or text contains either (observed), so fixture state is unaffected. The guard is there for other designs.
7. **T5 R2 assertion.** `mj-button` `2833:2123` is itself `inside_button: true`, because its wrapper `mj-button-Frame` `2833:2122` (height 56, 1 text) matches the name rule. The test now asserts the sibling `mj-text` `2833:2121` is `false` instead.
8. **T8 O3 eligibility.** The test checks `footer_editorial`, `footer_legal` and `nav_links` on case 5. Case 5's `col_N` fills each hold one node, so they are single-source and get asked. The `col_N` → `unmapped` pattern happens on cases 7, 8 and 10 (observed).
9. **Field-count ceiling raised, 58 → 60** (`app/core/tests/test_config_design_sync.py`). The plan accepted +2 fields as carried-forward debt (tech-debt-19). It missed this guard, and its "62 → 64" figure is stale: the real count is 58 → 60 (observed via `len(DesignSyncConfig.model_fields)`). The comment follows the file's existing "+1 (58)" precedent. **This needs the user's ratification.** The alternative is to fold the key into an existing field, and nothing clean fits.
10. **`--summary` prints a mechanical "Rule result" line** per decision point, applying T12's pre-registered rule, so the verdict in T12 is read off the output and not judged by hand.
11. **Divergence from the source prompt, as the plan planned:** records go to `traces/jev_shadow.jsonl`, not `converter_traces.jsonl`.
12. **Reframe `structure.json` is committed with every `image_ref` set to `null`.**
    - Why: the `detect-secrets` pre-commit hook flagged the 14 Figma image-fill hashes (40-hex) as "Hex High Entropy String".
    - Precedent: cases 5–10 already commit `image_ref: null` everywhere (0 non-null, observed).
    - Effect: none. Nulling left reframe's sections, slugs and normalised HTML identical to the unnulled parse (observed, `capture_case` comparison).
    - Consequence: the plan's "273,439 bytes" figure no longer applies; the committed file is 272,832.
    - Checks after the change, observed: `make snapshot-test` still gives 34p/10s/1xf. Data-regression + roundtrip + the 24 Jev tests give 116p/48s/1xf, which is 92 + 24 passed. A reframe dry run still builds 16 requests.
    - Why not the alternatives: allowlisting in `.secrets.baseline` or excluding the path in the hook would both widen the secrets gate.
13. **O3 `jev_confidence` is the probability of the option the resolver picked, not Jev's raw `confidence`.**
    - The plan copies Jev's `confidence`.
    - Why that is wrong here: when two slots top-rank the same node, the loser is resolved to its next option. With the raw figure, that slot would carry the confidence of the node it lost.
    - Effect on the report: `--summary` would then count displaced slots as high-confidence breaks, which skews the O3 threshold sweep.
    - This keeps the O3 sweep on one scale.
    - O1 still uses Jev's `confidence`. O2 uses `max(noul, 1 - noul)`, as planned.

## Issues encountered
- **T10 blocked.** `--check-key` printed `DESIGN_SYNC__JEV_API_KEY is empty.` (observed). The user must add `DESIGN_SYNC__JEV_API_KEY=<key>` to `.env`, then run:
  1. `uv run python scripts/jev_shadow_report.py --check-key`. Expect status 200 and model `jev-1.13.0`.
  2. `DESIGN_SYNC__JEV_SHADOW_ENABLED=true uv run python scripts/jev_shadow_report.py`
  3. `uv run python scripts/jev_shadow_report.py --emit-label-template`, which writes `data/debug/jev_shadow_labels.yaml`.
  4. Fill in `label` and `source` (T11). No labels were filled by the agent.
  5. `uv run python scripts/jev_shadow_report.py --summary`, then write `docs/jev-shadow-report.md` (T12).
- AC6, AC7 and part of AC8 stay open until those steps run. AC1–AC5 are met.
- `make check-full` first failed on `test_design_sync_field_count_bounded` (see Deviation 9). It then failed on `lint-numeric` over `input_tokens or 0` in `shadow.py`, which was rewritten as an explicit `None` filter. The third run was green.
- No migration. Not applicable.
- AC8's "nothing committed without the user's ask" was read as satisfied by the piv-implement skill, which instructs a local `chore(wip):` commit. Nothing was pushed.

## Addendum (2026-09-29): T10–T12
- **Labelling.** The agent wrote the labels under a blind protocol: the `heuristic`, `jev` and `jev_confidence` fields were not read until labelling was finished. The labels follow content-based rules the user ratified. The note in Issues step 4, "No labels were filled by the agent", predates this.
- **Cross-check.** 4 independent blind labeller subagents labelled the same worksheet, and every majority decision was applied. With the final labels counted as a 5th vote, no row has another label with more votes (observed).
- **Scratchpad loss.** The labelling scratchpad under `/private/tmp` was cleaned between sessions. It was recovered from the 12:00 Time Machine local snapshot, plus a replay of the session transcripts for edits made after the snapshot. Every file present in both sources was byte-identical. Merging the recovered labels onto the recovered pre-label copy reproduces the committed YAML byte for byte (observed).
- **Checks before `--summary`** (observed):
  - The YAML equals the pre-label copy once `label` and `source` are removed.
  - `diff -U0` changes 836 lines, all of them `label` or `source`.
  - There are 0 null O1 and O2 labels. The 39 null O3 labels are all heuristic/Jev agreements, checked after the labels were frozen.
  - Every O1 value is valid against `questions.py`.
  - The labels' sha256 (`a0f40fcb…c216c`) was recorded before `--summary` ran.
- **Latency** is not recorded in the trace records, so the T12 report makes no latency claim.
