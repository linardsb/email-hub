# AI layer implementation job (email-hub)

Status: **APPROVED 2026-09-27** (sequence + D1–D10, with D3/D4 reversed and D10 added). Not started. No `.claude/`, `CLAUDE.md` or app file touched yet.
Source layer: `~/Desktop/taxi/.claude/` at commit `f2cc6c4`.
Other sources: handoff `~/Desktop/claude-code-second-brain/Fredis/Memory/builds/email-hub/2026-09-27_converter-handoff.md`; course `~/Desktop/cloned_repos/agentic-coding-course`; Archon `~/Desktop/cloned_repos/archon`; prior port `~/Desktop/study-tutor/.claude/PORTED-FROM-TAXI.md`.
Evidence: 5 read-only subagent audits, 2026-09-27. Key findings are inlined below with file:line so they need not be re-run.

## 0. Goal and definition of done

Goal: email-hub gets an AI layer derived for email-hub (not a taxi copy): rules derived from the code, PIV skill chain wired to email-hub gates, email-hub-specific skills, safety hooks, taxi-equivalent PR workflow, improvement loop.

Done = every row of §1 verified (observed), import PR merged by the user, first real ticket (handoff T1) run through the loop.

## 1. Course completion checklist (C-codes) → job step

Course defines the AI layer as rules, on-demand references, skills, subagents, MCP, LSP, hooks, checked into source (`knowledge-base/concepts/the-ai-layer.md:13`, `the-six-components.md:15-20`). No "complete" label exists; Phases 3–4 unreleased (`README.md:93-106`).

| # | Item | Step | Proof |
|---|---|---|---|
| C1 | Lean CLAUDE.md: map, ground rules (traceable to files), commands, working principles (elicited from user) | S3 | `rules-check-drift` clean; user approved diff |
| C2 | `.claude/references/` + pointers from CLAUDE.md | S5 | zero dangling `references/` links |
| C3 | `rules-check-drift` runnable, run pre-merge | S5, S9 | run output |
| C4 | PIV chain customised; `piv-validate` wraps real gates per surface | S5, S6 | S9 loop |
| C5 | ≥1 tuned subagent, `file:line` output, wired into loop | S6 (`code-reviewer`) | used by `piv-review-pr` in S9 |
| C6 | ≥1 MCP committed at project scope (`.mcp.json`) | S6 (D7) | committed or deviation recorded |
| C7 | ≥1 hook in committed settings, proven to fire | S2, S6 | probes S9 |
| C8 | Loop artefacts; work ends in reviewed PR | S8, S9 | artefacts exist |
| C9 | Improvement loop (execution report → evolution review → AI-layer PR) | S5 | S9 produces one each |
| C10 | Layer committed, owned | S8 | PR merged |
| C11 | Optional: Archon / GH Actions agents | D6 → follow-up | — |

Not closable by this job: working principles need the user (S3 interview); LSP (Phase 4); Archon (follow-up).

## 2. Approved decisions

| ID | Decision (approved) |
|---|---|
| D1 | Stop hook = fast subset on changed files: `uv run --no-sync ruff check --no-fix <f>` + `ruff format --check <f>` + `mypy <f>` + `pyright <f>` + nearest `app/<feature>/tests/test_<module>.py -q -x -m "not integration and not benchmark and not visual_regression and not collab"`; `cms/` changes → `pnpm --dir cms type-check`. ~15s/module per the 2026-09-27 audit (`expected` for this repo until S6 measures it). Full gate only in `piv-validate` |
| D2 | Trigger = files changed since session start (snapshot on first hook call into `.claude/state/`), not whole dirty tree |
| D3 | **Keep taxi draft flow**: agent opens draft PR; CI `ready` job flips to ready only when all checks pass on that head |
| D4 | **Keep merge block**: hook refuses `gh pr merge`, `gh pr ready`, non-draft `gh pr create`. Only the user merges |
| D5 | Keep old `.claude/commands/`; do not copy taxi `plan-architecture` (use global `~/.claude/skills/plan-architecture`, it differs); CLAUDE.md names PIV skills as default path |
| D6 | Archon out of scope (follow-up list §6) |
| D7 | `.mcp.json` committed with jdocmunch only if it installs from PyPI; else record deviation (jcodemunch runs from machine-local rebuilt wheel) |
| D8 | Worktree off `origin/main`, branch `chore/ai-layer`; G12 files untouched |
| D9 | Import `piv-next` + `piv-slice-epic` (no `epic` label yet → "no open epic") |
| D10 | GitHub protection on `main`: PR required, admins included (no direct push), 0 approvals (author can't self-approve; keeps Dependabot auto-merge), required checks = ci.yml jobs + `CodeQL (analyze + gate)` (renamed at S8) + `Semgrep SAST` (lockfile-only-PR risk: architecture doc §Open questions). User runs the exact `gh api` call; the hook blocks the agent from it |
| D11 | **CodeQL = taxi full check** (user, 2026-09-27): `codeql` job in ci.yml (python, javascript-typescript, actions; `build-mode: none`; `security-extended`; `upload: always`), taxi `.github/scripts/codeql-gate.sh` (fails on NEW high/critical/error alerts vs base; unanalysed = red; stacked-PR fallback to main), `ready` needs it, default setup switched off by the user. Ships in PR B. Hook blocks `lgtm[…]`/`codeql[…]` suppressions |

## 3. Safety envelope (applies to every step)

- Diff scope for the import PR: `.claude/`, `CLAUDE.md`, `.gitignore`, `.agents/plans/ai-layer-import.md`, `PORTED-FROM-TAXI.md`, optional `.mcp.json`. CI change (`ready` job) is a **separate PR**. Check with `git diff --stat origin/main...HEAD`.
- No `app/`, `alembic/`, `.env`, DB, migration change. Gate runs unit tests only.
- New DB guards in `pre_tool_use.py`: block `alembic downgrade`, `make db-squash`, `dropdb`, `TRUNCATE`, `docker compose down/rm -v`, `docker volume rm|prune`, `docker system prune --volumes`. Also gate-settings writes (`gh api` to branch protection, rulesets, code-scanning default setup). `DROP` already blocked by `.claude/hooks/block-dangerous.sh`.
- Secrets guard (taxi guard 1): block reads of `.env`, keys; allow only `cp <main>/.env <worktree>/.env`.
- `settings.json` permissions merged, never widened beyond current.
- Rollback: delete the branch/worktree.
- Existing risk found (not caused by this job): `gh api repos/linardsb/email-hub/branches/main/protection` → 404 "Branch not protected" (observed). Only local `no-commit-to-branch` pre-commit hook guards `main`. D10 closes it.

## 4. Steps

Checkpoints marked ⏸ = stop, show user, wait for OK.

### S0 — preflight
- `git fetch`; worktree `../email-hub-ai-layer` on `chore/ai-layer` off `origin/main` (global `worktree-create` skill or `git worktree add`). Copy `.env` from main checkout (local spin-up recipe in memory `reference_local_dev_spinup_topology`). Do NOT `make db`.
- Grep `.agents/deferred-items.json` for `.claude/|CLAUDE.md|hook|skill` → expected 0 (observed 0 on 2026-09-27).
- Time `make check-full` once in the worktree (needed for S6 hook/gate timeouts). Record wall time as observed.
- Look up Claude Code default hook timeout in docs (claude-code-guide agent), don't assume.

### S1 — scaffold copy-as-is
From `taxi/.claude/skills/`: `piv-commit`, `piv-slice-epic`, `piv-review-changes`, `plan-create-prd`, `rules-check-drift`, `skills-create`, `hooks-create`, `opportunity-scan`, `system-execution-report`, `piv-next` (+`next.sh`).
Create `.claude/execution-reports/`, `.claude/system-reviews/REMEDY-LEDGER.md` (empty seed). Gitignore `.claude/last-gate.json`.
→ verify `diff -r` vs taxi = intended files only.

### S2 — safety hooks first
Adapt `taxi/.claude/hooks/pre_tool_use.py` (321 lines):
| Guard | Action |
|---|---|
| 1 secrets (`:42-51`) | keep; carve out worktree `.env` copy; drop `os.environ` from `ENV_DUMP` (:51, false-positives on code greps) |
| 2 `rm -rf` (:187-196) | drop, `block-dangerous.sh` covers it with protected-path list |
| 3 anketa fence `(^|/taxi/)(app|backend)/` (:57,:199-205) | **delete** — matches every relative `app/` path = whole backend |
| 4 PR moves (:63-84) | keep (D3/D4) |
| 5 CodeQL (:100-109) | retarget to `# nosemgrep` / semgrep dismissal; add `.py` to `SOURCE_SUFFIXES` (:109) |
| 6 fence `.github/workflows/`, `.github/scripts/`, `.claude/hooks/`, `.claude/settings.json` (:115) | keep. Blocks its own later edits → edit hook files via Bash heredoc once live |
| new | DB guards (§3) |
Wire into `.claude/settings.json` PreToolUse **alongside** existing `block-dangerous.sh` + `pre-commit-security.sh` (matcher `Read|Edit|MultiEdit|Write|NotebookEdit|Bash|Monitor|Grep|Glob`), keep PostToolUse + SessionStart entries. ~~Run via `uv run`~~ → superseded by V1: plain `python3` (a failing uv exits 2 = blocks every tool, `observed`).
→ verify probes: Write `app/x.py` → 0; `cat .env` → 2; Write `.claude/settings.json` → 2; `gh pr merge 1` → 2; `alembic downgrade -1` → 2.

### S3 — global rules ⏸
- `prime-codebase` (adapted: probe `pyproject.toml`, `uv.lock`, `Makefile`, `cms/package.json` instead of turbo/pnpm-workspace/.expo, taxi :36,:48).
- Global `rules-create-global` (brownfield, no arg): back up `CLAUDE.md` → feed it in; keep "what is" rules each traceable to a file; working-principles interview with the user.
- Must add: claims rule (numbers/guarantees tagged observed/derived/expected — taxi skills depend on it: piv-create-pr :43-49, piv-plan-implementation :176-178, piv-fix-review-findings :121); PIV workflow section + artefact paths; on-demand context table; PR flow (draft → CI ready → user merges).
- Must keep: Definition of Done, HTML email rules, deferred-items guardrail, linter safety, parallel-work awareness, `.agents/plans/` 700-line cap.
- Must fix: `sanitize_web_tags_for_email()` lives in `app/design_sync/sanitizers.py` (CLAUDE.md says `converter.py`, gone); jCodeMunch repo id in `.claude/rules/doc-and-code-research.md` (`local/email-hub-0ddab3c4` stale → `linardsb/email-hub`).
- Must NOT port taxi CLAUDE.md :68 (`.claude/` never `.agent/`) — contradicts `.agents/plans/`.
⏸ user reviews CLAUDE.md diff.

### S4 — architecture ⏸
Output: [ai-layer-architecture.md](./ai-layer-architecture.md) (written 2026-09-27; decisions: ready job needs ci.yml only + Semgrep via protection, non-Dependabot PRs only, protection = checks + 0 approvals + admins included, doc in `.agents/plans/`).
Global `plan-architecture` on this doc: records D1–D10, the email-hub skill set (S7), PR flow, safety envelope. Output `docs/architecture/ai-layer.md` (or `.agents/plans/ai-layer-architecture.md`), linked both ways with this plan. Converter O1 architecture is a separate later run.
⏸ user approves.

### S5 — adapt light + references
| File | Edit |
|---|---|
| piv-run-full-loop | `.claude/plans/` → `.agents/plans/` (:37,:63,:68) |
| piv-investigate-issue | missing agents `codebase-analyst`/`research-agent` (:38,:40) → `Explore` |
| piv-fix-review-findings | deferrals → `.agents/deferred-items.json` schema (`.claude/rules/deferred-items.md`); §1.5 CodeQL/#165 (:63-88) → semgrep; plans path (:129) |
| piv-review-pr | keep draft guard (D3); replace line cites `piv-plan-implementation:353-354` (:73-74) with section names; self-authored PR → `gh pr review --comment` |
| system-evolution-review | plans path (:38), ledger (:49,:229), record-gate mention (:238) |
| piv-implement-issue | `allowed-tools: Bash(pnpm:*)` (:5) → `Bash(make:*), Bash(uv run:*)`; pytest sample (:94) |
| vertical-slice-audit | `pnpm check` (:91) → `make check`; `packages/shared`/`@taxi/shared` (:112) → `app/shared`, `app/core`; test rule `app/{feature}/tests/` (:151) |
Skip `prime-app` (email-hub has `be-prime`/`fe-prime`).
New references (email-hub-sourced):
- `.claude/references/conventions.md` — keep §commit/§pr/§review headings (read by piv-commit :12, piv-create-pr :38). Content: `.claude/commands/commit.md`, `.pre-commit-config.yaml` (conventional-commit, `no-commit-to-branch`), PR title shape from #352–#365 (`feat(scope): … (Track G · Gn)`), squash-merge by user, `Closes #N` body.
- `.claude/references/logging-standard.md` — from `.claude/rules/backend.md` (referenced by code-reviewer :52).

### S6 — adapt heavy
| File | Change |
|---|---|
| piv-validate | Rewrite. Backend `make check-full`. Frontend `make ci-fe` (Makefile:195) — NOT `check-fe`, whose lint/format end in `\|\| true` (Makefile:137-142). Eval gates `make eval-check` / `eval-golden` when diff touches `app/ai/agents/` or judges (3pp tolerance). `make lint` rewrites files (Makefile:129-131) → fail if tree changed after it |
| piv-create-pr/scripts/record-gate.sh | Rewrite parser. Keep `head, head_short, branch, dirty, command, exit_code, started, finished`. Replace turbo fields (:92,:121,:152-189,:237) with pytest `N passed` + vitest summary + per-target exit list. `short_gate` true if a target skipped or pytest count < 8000 (expected floor; audit counted 8609 collected). Else a green make run exits 3 "GATE SHORT". `inherited-figures.sh` as-is |
| piv-create-pr | keep draft (D3); body `Closes #N` (study-tutor fix: `Implements` left issues open); conventions ref; reads `last-gate.json` (:69-73) |
| piv-implement | taxi compose/`db/migrations/*.sql` (:26-31) → alembic awareness + worktree recipe; report `.claude/reports/<slug>-report.md` |
| piv-plan-implementation | `.agents/plans/` (:235,:514,:519), 700-line cap, `file:line` not code blocks (overrides taxi :270), mandatory deferred-items grep; pytest/mypy/pyright; drop turbo/tsconfig/eslint/Drizzle/ride lines (:62,:86,:98,:106-108,:170-172,:179,:385,:428-430) |
| agents/code-reviewer.md | rewrite from `.claude/rules/{backend,frontend,security,testing}.md` + HTML email rules; `file:line` output to `.claude/code-reviews/` |
| stop_check.py | prefixes `app/ cms/ services/ alembic/ pyproject.toml uv.lock cms/package.json`; D1/D2 gate; `shutil.which` → stderr note + exit 1 (study-tutor fix, taxi has the bug); timeout → stderr note, never silent pass; explicit hook `timeout` in settings |
| settings.json | add Stop entry; allow `Bash(uv run:*)`, `Bash(gh pr view:*)`, `Bash(gh issue view:*)` |
| `.mcp.json` | D7 |

### S7 — email-hub skills
`opportunity-scan` over recent PRs (#352–#365), memory, `.claude/commands/`. Expected 3–5 skills, then wire into `piv-plan-implementation` + `piv-validate`:
- `converter-fix` — Track B/G fix cycle: seed loading, baseline regen, A3 scorer (per-section jitter = artefact; trust non-target flatness + composites), snapshot gate, ws churn (memory: `reference_converter_trackb_playbook`, `reference_a3_scorer_section_instability`, `reference_local_converter_tests_red`).
- `eval-gate` — which of `eval-check` / `eval-calibration-gate` / `eval-golden` when; 3pp `AGENT_REGRESSION_TOLERANCE`; can't measure live loops (memory `reference_eval_gate_cant_measure_live_loops`).
- `deferred-items` — consult / add / close per `.claude/rules/deferred-items.md` (closure-field drift: `closed_commit`, `closed_date`, `closed_at`, … normalise on `closed_commit`).
- `email-html-check` — table/td-only, no `<p>`/`<h*>`, sanitizer location.
Use `skills-create`. ⏸ user picks final list.

### S8 — ship (two PRs)
- PR A `chore(ai-layer): …` via the new `piv-create-pr` (dogfood). Add `PORTED-FROM-TAXI.md` (source commit + adaptation table).
- PR B `ci: add codeql job + codeql-gate + ready job` — port taxi `.github/workflows/ci.yml` `codeql` job (:89-125) + `.github/scripts/codeql-gate.sh` + `ready` job (:127-190); `needs` = 9 ci.yml jobs + `codeql`; skip Dependabot PRs; token: taxi uses `secrets.PR_READY_TOKEN` (:164) — settle when writing; fail closed. Refresh stale header of `dependabot-auto-merge.yml`. Write it BEFORE the hook is live in the writing session (guard fence).
- D11/D10: user switches CodeQL default setup off, then applies branch protection (exact `gh api` calls shown by the agent, run by the user via `!`), after PR B.
- User merges both.

### S9 — proof
| Check | Expected |
|---|---|
| `grep -rnE 'taxi\|Sakta\|anketa\|pnpm check\|turbo\|apps/\|packages/\|\.claude/plans\|codeql\|audit-diff\|drizzle\|zod\|expo\|#165\|\bride\|wip:' .claude --exclude-dir=worktrees --exclude-dir=state` (widened per cite-check #13; `-i` for codeql/drizzle) | 0 unjustified hits (exclude orphan `.claude/worktrees/phase-51.3-tool-call-cap`; `codeql` is legitimate once PR B exists, `chore(wip):` contains `wip:`, `cms/apps/web` contains `apps/`) |
| dangling `references/` links | 0 |
| hook probes (S2 list + stop_check: red → block, tool off PATH → note exit 1, clean → 0) | as listed |
| `record-gate.sh -- make check-full` | `exit_code 0`, `short_gate false`, pytest count present |
| `rules-check-drift` | clean |
| end-to-end loop on handoff T1 (footer legal text loss, `layout_analyzer.py:980`) | plan, report, commit, draft PR, CI ready flip, `pr-N-review.md`, execution report, evolution review |

## 5. Gotchas (from audits)
- `.claude/commands/handoff.md` is silently gitignored (`.gitignore:96 HANDOFF.md`, case-insensitive match).
- `.claude/worktrees/phase-51.3-tool-call-cap` is orphaned (points at deleted `merkle-email-hub`), doubles `.claude/**` globs.
- Pre-push hook runs `make check` only when GitHub Actions looks unavailable (`scripts/ci-local-fallback.sh`).
- Ruff pre-commit pinned v0.14.2 vs uv 0.15.22; TC rules not selected (pyproject:127-150).
- `.claude/reports`, `code-reviews` not gitignored; three untracked G12 `.claude/` files on the G12 checkout must not enter PR A (worktree avoids this).
- No `piv-*` skill installed globally (archived to `~/.claude/_skills-archive-2026-08-28/`); memory note saying `/piv-review-pr` is global is stale.
- Guard 6 blocks Edit/Write on hooks + settings once active → heredoc.

## 6. Archon follow-up (D6, not this job)
`.archon/workflows/fix-github-issue-emailhub.yaml` (523 lines, inline prompts, `denied_tools: [Bash]`, gate `make lint/types/test`) is untracked (`.gitignore:166`). Needs: track `.archon/` except runtime; `config.yaml` (`worktree.baseBranch: main`, `copyFiles: [.env, data/debug/]`); rename merkle refs (:8-9,:110); re-register workspace (still `linardsb/merkle-email-hub` in `~/.archon/archon.db`); `archon validate`. Port PIV as `.archon/commands/*.md` per `archon/workshops/piv-loop-system-evolution/README.md:26-73`, not by calling skills.

## 7. Progress log

### 2026-09-27 — S0, S1, S2 done (uncommitted, worktree `../email-hub-ai-layer`, base 7e7536e3 / #375)
- S0: deferred grep 6 hits, all substring noise (0 relevant). Hook facts (docs): `timeout` in seconds, default 600; timeout or launch failure = non-blocking (tool proceeds); exit 2 blocks.
- S0 gate timing (observed, worktree without `data/debug/`): backend part of `make check-full` 362s, pytest 8492 passed / 115 skipped; `check-fe` 57s once `cms/node_modules` installed (derived total ≈ 420s). `make test` rewrites `app/ai/agents/{dark_mode,scaffolder}/skill-versions.yaml` `date:` → gate has side effects on `app/` (reverted). `check-full` includes `lint` (rewrites files) and lax `check-fe` (Makefile:182) → piv-validate's "tree changed" check must wrap `check-full` too.
- S1: 10 skills copied; piv-commit (scoped staging, skill-versions restore, `wip:` → `chore(wip):` because commit-msg hook rejects `wip:`, taxi issue refs dropped), hooks-create (fence + heredoc note, quoted argument-hint), skills-create (YAML-invalid description folded) adapted. **S6 piv-implement must use `chore(wip):` to match.** piv-slice-epic needs `prime-codebase` → install the S3-adapted copy. `next.sh:31` row format ≠ piv-slice-epic template (latent, also in taxi) → fix in S5.
- S2: `pre_tool_use.py` wired (matcher adds `Monitor`; command falls back to `python3` when uv is off PATH; missing script → exit 1 notice, not a session-wide block). 132-probe adversarial suite: 25 bypasses + 8 false positives found, all fixed except 10 accepted text-only limits (glob/quote tricks, `export -p`, Bash writes into fenced files = deliberate heredoc route, `cp .env.example .env.test`). Additions beyond plan: `.semgrepignore` + `settings.local.json` fenced; `nosem`/`nosemgrep` counted, not matched.
- Cite check: 0 wrong line cites. Correction: `vertical-slice-audit:151` → drop the 500-line parenthetical, don't add a test rule. 13 missed couplings (piv-create-pr CI job names + `tasks_not_in_graph`, piv-review-pr codeql feed/#165, piv-fix-review-findings audit-diff/expo, piv-plan-implementation .ts/Drizzle/zod/ride, vertical-slice-audit index.ts, piv-investigate-issue file.ts, record-gate.sh:50 pnpm default + `node -e` + apps/dispatch) → S5/S6. S9 grep widened: `codeql|audit-diff|drizzle|zod|expo|#165|\bride|wip:`.
- S7 scan recommends: keep `converter-fix` (9/9 converter PRs #352–#365 follow one cycle; stale memory lines "don't run make check" / "fixture tests skip in CI" must not be copied), keep `deferred-items` re-scoped to add/close/SHA-stamp (26 `pending` placeholders on main), fold `eval-gate` into piv-validate, drop `email-html-check` (rules → code-reviewer agent). New: base-branch check in piv-create-pr/piv-review-pr (#358/#361 re-landed). Final list = user ⏸.
- `block-dangerous.sh` false-positives on any command text containing a recursive-force delete + protected path (e.g. a heredoc) → run such edits from a file.

### 2026-09-27 — S3 applied, awaiting user review of CLAUDE.md diff
- User approved deviations V1–V7 (called 'D1–D7' in chat; renamed to avoid colliding with §2): V1 hook on plain python3, V2 Monitor matcher, V3 fence .semgrepignore + settings.local.json, V4 `chore(wip):`, V5 S7 pick deferred to S7 ⏸, V6 C7 proof in S9 from a worktree session, V7 rules `globs:` → `paths:` — docs: only `paths:` scopes loading, `globs:` files loaded unconditionally).
- Interview: all 10 recommended answers → `## Working principles` in CLAUDE.md (110 lines).
- Also: jCodeMunch id fixed in `.claude/rules/doc-and-code-research.md`; `prime-codebase` (email-hub-adapted) installed.

### 2026-09-27 — S4 written, fact-checked, awaiting user approval
- `ai-layer-architecture.md` written; user calls: ready needs ci.yml jobs (+codeql), Semgrep via protection; ready skips Dependabot; protection = checks + 0 approvals + admins; doc in `.agents/plans/`. D11 added (CodeQL = taxi full check).
- Cold fact-check: 34 claims verified; fixed 3 wrong (hook allowed `gh api` writes to branch protection + `enablePullRequestAutoMerge` → both now blocked, `observed`; python3 interpreter is PATH-dependent: 3.12 shim / 3.9.6 system, both block), 5 retags, 5 plan contradictions (this file's S2/D1/D10/§3 rows updated).

### 2026-09-27 — S4 APPROVED by user; session handed over
- Verification artefacts (hook probe suite `verify-hook/probe.py`, S1/wiring/cite/opportunity reports, S3 prep, gate logs) copied to gitignored `.claude/state/ai-layer/`.
- Next: S5 + S6 (see HANDOFF.md).

### 2026-09-27 — S5 + S6 applied (uncommitted), awaiting cold verification, then S7 ⏸
- Method: 6 parallel subagents (references, S5a review/fix/evolution, S5b loop/investigate/audit/next, S6a validate/create-pr/record-gate, S6b plan/implement, S6c code-reviewer) + 1 research agent, on one shared contract (fixed names, `last-gate.json` fields, GOTCHA cite by section). Lead wrote `stop_check.py`, settings, CLAUDE.md edits.
- Imported + adapted: piv-run-full-loop, piv-investigate-issue, piv-fix-review-findings, piv-review-pr, system-evolution-review, piv-implement-issue, vertical-slice-audit, piv-validate, piv-create-pr (+ `record-gate.sh` rewrite, `inherited-figures.sh`), piv-implement, piv-plan-implementation (632 lines vs taxi 571), `agents/code-reviewer.md`. New `.claude/references/conventions.md` (§commit/§pr/§review) + `logging-standard.md`. Cite-check #1–#12 closed; #13 → §S9 grep row widened.
- **Gate (observed):** `record-gate.sh -- make check-full` exit 0, 313 s recorded window (316 s shell wall-clock incl. wrapper), pytest 8492 passed / 0 failed / 115 skipped, vitest 780 passed, `short_gate false`, skill-versions.yaml restored (tree unchanged after run). `ci-fe` not run (no `cms/` change).
- **Found by the first gate run (observed):** `make lint` / CI `ruff check .` + `ruff format --check .` (ci.yml backend job) cover `.claude/hooks/*.py` → 24 ruff errors (T201/S603/S607/RUF005/PTH/ANN201/B904/S324) + 2 files reformatted; PR A would have failed CI. Fixed in code (`sys.stderr.write`, unpacking, pathlib, `usedforsecurity=False`, `from err`); file-level `# ruff: noqa: S603, S607` in `stop_check.py` only (fixed argv, no shell). Probe suite rerun: exactly 10 FAILs (observed; `probe.py` launches the settings command, so it runs PATH `python3` = 3.12 both times). 3.9 checked directly: `/usr/bin/python3 -m py_compile` both hooks OK; piped `dropdb`, `cat .env`, `gh pr merge 1` → 2, `ls app` → 0 (observed).
- `stop_check.py` (D1/D2): baseline snapshot at SessionStart `startup|resume|clear` (not first Stop, so turn-1 edits are checked) incl. start HEAD (catches `chore(wip):` commits); repo root from stdin `cwd` (docs: `CLAUDE_PROJECT_DIR` does not follow a worktree switch); mypy/pyright on `app/` only (Makefile `types`); own 240 s budget < settings `timeout` 300; `stop_hook_active`, missing uv/pnpm, no baseline, budget, internal error → stderr note exit 1 (never silent). Additions beyond D1: `uv lock --check` when `pyproject.toml`/`uv.lock` change. Probes (scratch clone, observed): red → 2 (3.12 + 3.9), green → 0, clean → 0, active → 1, no uv → 1, no baseline → 2 on red.
- **Stop-hook cost (observed):** warm 9.3–11.3 s per module (3 modules, research agent) and 9 s in the clone probe; cold mypy up to 75 s (`component_matcher.py`); `pnpm --dir cms type-check` 9.7 s. Replaces the ~15 s `expected` figure; within the 60 s narrowing threshold warm.
- Settings: Stop entry + SessionStart snapshot entry; allow `Bash(uv run:*)`, `Bash(gh pr view:*)`, `Bash(gh issue view:*)`.
- **D7 (observed):** `jdocmunch-mcp` 1.145.0 and `jcodemunch-mcp` 1.108.319 both on PyPI (memory "deleted from PyPI" is stale). `.mcp.json` NOT committed: `.gitignore:58` ignores it with comment "contains API tokens" → user call at S7/S8.
- Also fixed: CLAUDE.md pointer row for `.claude/references/` (C2) and dropped the stale "jCodeMunch id is stale" remark (rules-check-drift); `.claude/rules/testing.md` `paths:` comma string → YAML list; code-reviewer severity scale Major/Minor → Critical/High/Medium/Low to match piv-review-pr (latent taxi mismatch).
- Deviations to ratify: (a) REMEDY-LEDGER convention invented (`PR`=`open` = unapplied, row order = rank, `(recurred …)` suffix); (b) deferred entries use `introduced_commit: "pending"` then squash SHA; (c) Critical findings not deferrable without the user; (d) vertical-slice-audit accepts `exceptions.py` (no `errors.py` in email-hub); (e) piv-slice-epic template changed to match `next.sh` (+ `epic` label) rather than next.sh; (f) record-gate counts "tree changed" and missing targets as short; piv-validate restores `traces/analysis.json` after `eval-check`; (g) conventions tag `Closes #N` `expected` (0 of last 100 merged PRs use `Closes`; 4 use `Fixes #N`: #303/#310/#312/#329, observed by the verifier); (h) logging standard keeps 2-part for new events; 440/1296 existing events are 3-part (derived, regex); code-reviewer flags 3-part on new/changed lines only.
- **Cold verification** (`.claude/state/ai-layer/verify-s5s6.md`): §7 claims 21 checked (18 OK, 2 WRONG, 1 unverifiable), 74 email-hub cites opened (71 OK, 1 WRONG), cross-file 8/8, hygiene 7/7, no taxi coupling left. Fixed: 316→313 s window, `Closes`→`Fixes` count, `pyproject.toml:125`→`:126`, `vertical-slice-audit:34` `errors.{py,ts}`→`errors.py`, code-reviewer vs logging-standard conflict. Unverifiable "9 s clone probe" = lead's own run (observed in session, no log kept).
- **Stop-hook gap found by verifier, fixed:** nearest-test lookup only checked `app/<feature>/tests/` → 158/708 `app/` modules got a test; now walks up from the module dir → 271/708 (observed, same glob). Ruff now runs on every changed `.py` (was `app/ services/ alembic/` only; CI lints repo-wide, and the 24 hook errors lived outside those prefixes). Ruff calls use `--force-exclude` so pyproject `exclude` paths (`pyproject.toml:113-124`) stay unlinted as in CI: probe on `email-templates/_x.py` → 0 (plain ruff on it → 1) (observed). Re-probed: `scripts/` lint error → 2 (3.9 and 3.12); nested `app/ai/agents/evals/calibration.py` green → 0 in 8 s (observed).
- Open for the user: (Q1) `Bash(uv run:*)` allow (S6 row) widens permissions against §3, and `uv run python -c 'print(os.environ)'` is an accepted hook bypass → keep or drop; (Q2) commit `.mcp.json` (un-ignore `.gitignore:58`) or record the C6 deviation; `pre_tool_use.py:4` names `PORTED-FROM-TAXI.md`, created at S8. Gate coverage of post-gate edits: `record-gate` ran before the verifier fixes; those touch only `.claude/` text + `stop_check.py`, covered by repo-wide `ruff check --no-fix .` + `ruff format --check .` green (observed); mypy/pyright scan `app/` only and pytest reads no `.claude/` file (derived, Makefile:133-135, pyproject testpaths). Multi-summary pytest rule exercised for real: 8492 picked with `golden-conformance` in the log (observed). Known limits kept: record-gate cannot tell whether `migration-lint`/`check-env-drift` ran; pytest exit 5 counts as pass.

### 2026-09-27 — user decisions at the S7 ⏸ (AskUserQuestion)
- **S7 skills picked:** `converter-fix`, `deferred-items` (add/close/SHA-stamp only), base-branch check in `piv-create-pr` + `piv-review-pr`. Not picked: separate `eval-gate` / `email-html-check` skills (already covered by piv-validate eval branch + code-reviewer).
- **Q1:** `Bash(uv run:*)` allow DROPPED from `.claude/settings.json` (§3 wins over the S6 row). Applied.
- **Q2:** `.mcp.json` COMMITTED (uvx jcodemunch-mcp + jdocmunch-mcp); `.gitignore` line replaced with `.mcp.local.json` for any future secrets. Applied. Closes C6 at S8.
- **V8–V15 ratified** (= §7 S5/S6 deviations (a)–(h)).
- Next: S7 execution via `skills-create` (3 items above), wire into `piv-plan-implementation` + `piv-validate`, cold-verify, then S8.

### 2026-09-27 — S7 applied (uncommitted), cold-verified; stopped at the S8 ⏸
- Method: 3 parallel subagents via `skills-create` (converter-fix Create, deferred-items Create, base-branch Adapt), lead wiring, then 1 cold verifier. No `make` run, no `gh` write, no commit.
- **`converter-fix`** (new): `SKILL.md` 160 lines + `references/baselines-and-gates.md` 105 + `references/a3-scoring.md` 89 (`observed` wc after the verifier fixes). Stale memory lines not copied. Findings: converter case inputs 5–10 (`structure.json`, `tokens.json`, `expected.html`, `rendered_w600.png`) are tracked (`.gitignore:138-146`), so converter tests run in CI (`observed` CI run 29764095476: snapshot 34 passed / 10 skipped / 1 xfail, data-regression 73 / 48 / 1); 2 snapshot skips (`test_reference_bgcolors[6]`/`[10]`, `test_snapshot_regression.py:431-433`) fire in every checkout (reference HTML absent). A3 composite puts the reference on the LEFT (`scripts/score-fidelity-cases.py:78`; memory says the opposite). The "Redis cache poisoned A3 in #359" claim is unsupported: the section cache is only read with a `connection_id` (`converter_service.py:373/:522/:833`), which the scorer never passes; skill keeps the env-var guard and marks the mechanism unverified. `make snapshot-capture` hardcodes `--overwrite` (Makefile:160-161) → skill uses the script with `--output`. Ladder numbers not hardcoded: "unchanged from base" = empty diff on `data/debug/ladder_snapshot.json` + `test_ladder_no_drift` (`test_converter_data_regression.py:266`).
- **`deferred-items`** (new, add/close/SHA-stamp only; normalisation and `closed_pr` out of scope by user choice): `SKILL.md` 102 lines + `scripts/stamp_ledger.py` 121 lines (stdlib, line-based edit, `--dry-run`, stamps only placeholders the merged PR wrote, found by diffing the ledger at the squash commit against its parent). Placeholders on origin/main (`observed`): `introduced_commit` `pending` ×11 + `pending commit` ×5, `closed_commit` `pending` ×4 + `pending commit` ×6 = 26. Scratch replay of #355 (`81dafce4^` ledger, `--sha f9671753`) → byte-identical to `81dafce4` (`observed` by builder and verifier). Ruff + format + `mypy --strict` clean on the script (`observed` by builder).
- **Base-branch check** (piv-create-pr Phase 0 + handoff, piv-review-pr Phase 1 guard + `origin/$BASE` diff + handoff). Replay (`observed` gh timestamps): #358 opened 11:41Z, 2h03m (`derived`) after its base PR #357 merged; #361 opened 13h52m (`derived`) after base PR #360 merged → both caught at create time; #361 also at review time. Squash-merged base tips are not ancestors of main (`observed`), so the test is the PR-state query, and `--is-ancestor` is used only on the merged PR's `mergeCommit` after merge. Added: stacked PRs get no CI (`ci.yml:6-7` `pull_request: branches: [main]`), so no `ready` flip until retargeted.
- **Wiring:** piv-validate surface table gets a converter row (check-full + converter-fix evidence, A3 advisory); piv-validate §4 "lower pytest count" bullet corrected (it claimed converter data is gitignored and skips in a worktree, which was wrong) and the S0 parenthetical "worktree without `data/debug/`" → "in the AI-layer worktree"; piv-plan-implementation step 7 gets a converter bullet, step 8 "close" points to `deferred-items` Close (632 → 635 lines).
- **Cold verification:** ~95 claims, 58 cites opened; 1 WRONG (all snapshot skips called expectation-conditional), 3 DRIFT (`:205-208`→`:200-208`, `:201-203`→`:201-206`, `:67`→`:65`), 5 minor (#357 tree-path shape, #354/#365 count attribution, ladder field list, review-pr query lacked `headRefOid`, 2 untagged figures). All fixed.
- **Gate:** not re-run; S8 step 1 re-runs it at PR A's head (the last record predates S7). S7 changes only `.claude/skills/**` (text + one `.py`). `make security-check` scans `app/` only (Makefile:503), but `semgrep ci` (semgrep.yml:45) scans the whole repo minus `.semgrepignore`, which does not exclude `.claude/` → `stamp_ledger.py`'s `subprocess` calls may raise a Semgrep alert on PR A (`expected`; the hook blocks `nosemgrep`, so a real alert gets a code fix or a human dismissal). Repo-wide `ruff check --no-fix .` "All checks passed!" and `ruff format --check .` 1539 files formatted (`observed` after the wiring edits); mypy/pyright scan `app/` only and pytest reads no `.claude/` file (`derived`, Makefile:133-135, same derivation as S5/S6). `app/`, `data/`, `.agents/deferred-items.json` untouched (`observed` git status).
- Not done (outside the user's list, for the user): `piv-fix-review-findings:51-65` repeats the ledger fields the new skill owns (pointer candidate) and its id example `phase-53g-g4-…` does not fit the rule's `phase-<N>.<sub>-<slug>`; memory `reference_local_converter_tests_red` is stale on CI skips; `delete_branch_on_merge` is false (`observed` by builder), which kept merged branches open as merge targets. `skills-create` Gates 6–7 (independent review, fresh-session trigger test) not run.

### 2026-09-27 — user decisions at the S8 ⏸ (AskUserQuestion)
- Q1: PR A includes `.agents/plans/ai-layer-architecture.md` (§3 widened by that one file).
- Q2: `ready` job uses a classic `repo`-scope PAT in secret `PR_READY_TOKEN` (user creates it); missing secret fails closed.
- Q3: CodeQL default setup switched off by the user BEFORE PR B's first run (accepted gap: no CodeQL scan on main until PR B merges).
- Q4: PR B merges first; PR A then dogfoods the `ready` flip.

### 2026-09-27 — S8 run: PR A committed + gated, PR B written, both cold-verified; stopped before push
- Method: main-checkout session (the worktree hook fences `.github/`); 2 cold subagents (A2 reviewer, PR B + PORTED verifier) + advisor. No push, no `gh pr create`, no settings write.
- **PR A** (`chore/ai-layer`): A2 review of `PORTED-FROM-TAXI.md` → 1 wrong (settings "permissions not widened": `gh pr view`/`gh issue view` read-only allows were added, `observed` diff), 1 drift (references "new" → "rewritten"), 4 omissions (inherited-figures.sh, REMEDY-LEDGER, execution-reports, a table of email-hub files changed not from taxi), 4 minor; all fixed. Second verifier: `execution-reports/` "as-is" → "reset" (taxi tracks 12 files there, `observed`), 4 taxi-domain references added to "Not taken"; fixed. **Note for the user:** §3 says permissions "never widened"; the two read-only `gh` allows are a widening (kept; revert if unwanted). `detect-secrets` hook flagged `code-reviewer.md:61` ("bcrypt for passwords; `HTTPBearer(auto_error=False)`") → reworded, no pragma. Commit via piv-commit, 56 files, all inside §3 + `ai-layer-architecture.md` (A3 `observed`: `git diff --name-only origin/main...HEAD` minus the scope regex = 0 lines).
- **A1** `record-gate.sh` → `make check-full` exit 0 at `015e519f`, dirty false, short_gate false, pytest 8492 passed / 0 failed / 115 skipped, vitest 780 passed (`observed`, window 18:50:06Z→18:54:37Z). The commit was then amended (this entry + the 2 PORTED fixes, docs only), so the record's head is stale: re-run A1 after the post-PR-B rebase, which changes the head anyway.
- **PR B** (worktree `../email-hub-ci`, `ci/codeql-ready` off origin/main 7e7536e3, 1 commit): `codeql` job named `CodeQL (analyze + gate)` (python, javascript-typescript, actions in one job so the gate runs after all uploads; build-mode none; security-extended; upload always; paths-ignore = build outputs only, taxi's `app`/`backend` fence dropped because `app/` is email-hub's backend); `.github/scripts/codeql-gate.sh` (mode 100755); `ready` job (needs the 9 jobs + codeql; skips `dependabot[bot]` by PR author; head-SHA recheck kept; explicit empty-token fail-closed check added); refreshed `dependabot-auto-merge.yml` header. Pins match semgrep.yml (`checkout@v7`, `codeql-action@v4.37.3`). actionlint clean (`observed`).
- **Adaptation found by inspection:** Semgrep OSS uploads to the same code-scanning API (main: 44 open alerts all Semgrep, 0 CodeQL; `refs/pull/375/merge` has 1 Semgrep analysis, 0 CodeQL — `observed`). Taxi's gate counts all tools → a Semgrep-only ref would pass the "was it analysed?" check. Added `tool_name=CodeQL` to both API calls; live `--pr 375` now exits 1 "no CodeQL analysis" (`observed`); offline fixtures: carried 0, new 1, clean 0, usage 2 (`observed`).
- **Job-name collision:** GitHub's own code-scanning check is also named `CodeQL` (app `github-advanced-security` 57789, `observed` on #375 head) → job renamed; protection must pin Actions checks to app_id 15368 (`observed` app id of ci.yml jobs).
- Verifier (PR B): 3 behaviour notes documented in the gate header, not changed in code: V1 = R3 (main has actions-only CodeQL analyses, so the fallback never fires and PR B's gate is expected red on the python/JS backlog); V2 stacked PRs get no CI (`ci.yml:6-7`), fallback dormant; V3 ci.yml concurrency cancels superseded main pushes → transient false red until the next main analysis. Wrong claims (Semgrep "covered by protection"; hook citation before PR A lands; "close that window") and a long line fixed.
- **R4 by proxy:** Dependabot PR #375's Semgrep run (workflow-level `security-events: write`, run 30621083217, 2026-07-31T09:45:15Z) produced a Semgrep analysis on `refs/pull/375/merge` at 09:45:44Z (`observed`) → Dependabot runs honour an explicit `security-events: write`; the `codeql` job should upload on Dependabot PRs (`expected`). PR B is not a Dependabot PR, so its own run cannot observe R4; check the first Dependabot run after PR B merges.
- **R1:** Semgrep's step is `continue-on-error: true` (`semgrep.yml:44`) → advisory; after Q4 the gating scanner for PR A's `.py` is CodeQL.
- Next (user): create `PR_READY_TOKEN`, switch default setup off, then approve push + draft PR B.

### 2026-09-27 — S8 push: settings, deps fix, PR B, merges (S8 closed)
- Method: main-checkout session (the worktree hook fences `.github/`) + 1 A3 agent. The user ran the settings writes, and both PRs were pushed as drafts on the user's OK.
- **User decisions (AskUserQuestion):**
  - O1: Semgrep SAST is NOT required. `semgrep.yml` skips lockfile-only PRs via `paths-ignore`, so a required check would stall them; CodeQL is the gating scanner.
  - O2: neither `Semgrep OSS` nor `Ready for review` is required.
  - O3: the read-only allows `Bash(gh pr view:*)` and `Bash(gh issue view:*)` are KEPT. **This is a logged exception to §3 "never widened".**
  - Protection required checks (derived from O1/O2): the 9 ci.yml job names plus `CodeQL (analyze + gate)`, pinned to `app_id: 15368`.
  - D1: fix the deps first, in a separate PR, before PR B.
  - D2: suppress the 7 gosu CVEs inside that deps PR.
- **Settings (observed):**
  - The user PATCHed CodeQL default setup to `not-configured` (Q3).
  - `PR_READY_TOKEN` (a classic PAT, `repo` scope) was set at 2026-09-27T19:17:28Z from the user's own terminal. An earlier token pasted into chat was revoked and rotated.
- **A1 before push (observed):** `record-gate.sh` → `make check-full` exit 0 at `f66f8056`, with:
  - pytest 8492 passed / 0 failed / 115 skipped, vitest 780 passed;
  - dirty false, short_gate false;
  - window 18:58:18Z→19:02:46Z.
- **PR B first run 36343909130 at `8f715fc3` (observed):**
  - `CodeQL (analyze + gate)` was **green**, not the `expected` red of the S8-run entry. There was one combined upload (category `.github/workflows/ci.yml:codeql`), 176 rules, 0 results.
  - Gate: "0 open on the PR, 0 at the gate's severity, 0 open on the base".
  - `Ready for review` ran `gh pr ready --undo` and concluded `failure`: the token authenticates, and the PR stays draft while `needs` is red.
- **Correction to R3/V1 (observed, A3 agent):** main was NOT actions-only. It had python 257 / JS 259 CodeQL analyses up to 2026-05-22, with alerts 0 open / 31 dismissed / 61 fixed. The gate header in `.github/scripts/codeql-gate.sh` still says actions-only (wording only).
- **Main CI red since at least 2026-09-11 (observed):** 8 ci.yml runs in a row failed, including Dependabot's.
  - Backend pip-audit: 20 vulns in 7 packages.
  - Trivy app image: aiohttp CVE-2026-69244, anyio CVE-2026-63374 (CRITICAL) and cryptography CVE-2026-69247.
- **#406 deps PR (observed):**
  - `83e7e675`: a `uv.lock`-only bump pinned to the exact fix versions: aiohttp 3.14.3, anyio 4.14.2, cryptography 50.0.0, soupsieve 2.9.0, pip 26.2, httpcore2 2.12.0 (forced by httpx2 2.12.0). A plain `--upgrade-package` pulled in extra drift.
  - Once the app image was clean, the Trivy db step ran for the first time since 2026-08-31. It flagged 7 HIGH go-stdlib CVEs in `/usr/local/bin/gosu` from the digest-pinned `pgvector/pgvector:pg16`.
  - `9ce95000` (D2) adds those 7 to `.trivyignore` and `docs/dependency-debt.md`, with review date 2026-12-31.
  - CI run 36346664610 at `9ce95000`: `success`. Merged 20:11:35Z as `505e16cc`.
- **PR B #405 (observed):**
  - Rebased onto #406 to `31335ba7`. It was a rebase, not `gh run rerun`, because rerun replays the stale merge SHA.
  - Run 36347143671: `success`, all 11 jobs green. **CI flipped #405 to ready (`isDraft:false`)**, the first end-to-end ready flip.
  - Merged 20:21:03Z as `ae489171`.
- **PR A #404 (observed), R5:**
  - Its only CI run, 36343619380 at `f66f8056`, was `failure` (the pre-existing pip-audit/Trivy red).
  - The user marked it ready at 20:22:28Z and merged it at 20:22:46Z as `f26ee233`, before any rebase or A1 re-run. So PR A's own ready flip was never exercised; #405's was.
  - The planned post-PR-B rebase + A1 did not happen (`rebase-pr-a.sh` was killed before it changed anything).
- **R6 (observed):** ci.yml concurrency made #404's push run 36347811190 cancel #405's push run 36347701649. That cancelled run left a CodeQL analysis on `ae489171` with error "unsuccessful execution" (id 1848019348). This is the V3 window.
- Carried: the `.trivyignore` `# expires:` comment is never parsed; Trivy reads only `exp:YYYY-MM-DD` (`pkg/result/ignore.go:308`, v0.70.0), so the go-stdlib entries never lapse. Candidate follow-up.

### 2026-09-27 — S9 session: main baseline (step 1)
- Method: session run from the main checkout against worktree `~/Desktop/email-hub-s9` (`chore/ai-layer-s9`, off `f26ee233`) by absolute path, so the repo's own skills and hooks were **not** loaded in this session. PIV skills were followed by reading their `SKILL.md`. That leaves V6's hook-firing proof (C7) to a worktree session. There were 3 read-only subagents (R4, S9 checks, T1 prep).
- **Main baseline (observed):** run 36347811190 at `f26ee233` `success` (updated 20:29:15Z). All required-candidate jobs were green, except `Migration safety (squawk)` and `Commit message lint`, which are `skipped` on push (they are PR-only). `Ready for review` was skipped. CodeQL analysis 1848024960 exists on `refs/heads/main`, with `results_count` 46.
- **Main's first full CodeQL baseline has 18 open alerts** (observed, all created 20:25:22Z by that analysis):
  - 1 critical `py/partial-ssrf` at `app/connectors/http_resilience.py:46`;
  - 1 high `py/redos` at `.claude/hooks/pre_tool_use.py:77` (entered with PR A, whose run predated the codeql job);
  - 13 medium `actions/unpinned-tag` in `.github/workflows`;
  - 3 medium JS file/http access in `cms/apps/web/e2e/global-{setup,teardown}.ts`.
  - The gate fails only on NEW alerts vs base, so these do not block PRs (derived, gate design D11). They are open for triage by the user.
- T1 prep (observed, subagent): `layout_analyzer.py:980` is the `social` early return in `_classify_mj_section` (def :946). It fires before the text-only→FOOTER rule (:1003-1005), and `_classify_by_content`'s legal→FOOTER rule (:1092-1098) is never reached on the MJML path (derived). Matching ledger entry: `phase-53g-g11-social-section-drops-column-content` (deferred, known-bug), whose `closes_when` names G12 re-segmentation.
