# Working Tree Cleanup

**Source:** Audit of dirty working tree on `refactor/tech-debt-04-connector-abcs` after `/be-ship` (50 modified/untracked files, none belonging to PR #42).
**Goal:** Empty `git status` on every branch checkout — every file either tracked, deliberately gitignored, or deleted.
**Effort:** ~1.5 hours. **Five small PRs**, each independent and revertible.

## Summary

| PR | Theme | Files | Risk |
|----|-------|-------|------|
| 1 | Gitignore tooling caches | `.gitignore` only | None |
| 2 | Accept regenerated `.secrets.baseline` + retain pragmas | 1 baseline + 0 new | Low (verified safe) |
| 3 | Commit pending tech-debt plans + audit doc | 16 plan files + `TECH_DEBT_AUDIT.md` | None |
| 4 | Drop oversized debug binaries from working tree | 2 large files | Low (regenerable) |
| 5 | Triage long tail | ~15 files (templates, traces, debug, misc) | Per-file judgment |

After all 5 land: `git status` returns nothing on a fresh checkout of `main`.

## Inventory (current state)

```
 M .agents/plans/tech-debt-01-quick-wins.md          [WIP — landed-status edits]
 M .agents/plans/tech-debt-03-multi-tenant-isolation.md
 M .secrets.baseline                                 [-5929 lines, regenerated 2026-04-26]
 M app/ai/agents/dark_mode/skill-versions.yaml       [date bump only]
 M app/ai/agents/scaffolder/skill-versions.yaml
?? .agents/plans/{14 tech-debt + planning .md files}
?? .claude-merkle/                                   [MCP cache]
?? .claude/projects/                                 [Claude Code session state]
?? .claude/worktrees/                                [Claude Code worktrees]
?? .claude/docs/architecture-quick-reference.md
?? .hypothesis/                                      [Hypothesis cache, ~2k entries]
?? TECH_DEBT_AUDIT.md                                [WIP audit doc + my edits]
?? agentis_security.txt                              [stray essay; appears mis-saved]
?? cms/apps/web/scripts/{generate-icons,rewrite-icon-imports}.mjs
?? data/debug/{converter-gap-analysis*.md,reframe/}
?? docs/{10 HTML/PNG/JSON/MD files, ~10.5 MB total}
?? email-templates/{Icons/,game_recap/,reframe-2025.html,reframe-assets/,training_HTML/, …}
?? traces/pre_{file_based,golden,real_components}/   [eval verdict baselines, 9 jsonl each]
?? workflows/{converter-training-guide.html, design-import-pipeline.md, …}
```

---

## PR 1 — Gitignore tooling caches

**Files:** `.gitignore` only
**Effort:** 5 min

Add to `.gitignore`:

```
# Claude Code session state + MCP caches (machine-local, never commit)
.claude-merkle/
.claude/projects/
.claude/worktrees/

# Hypothesis property-based testing cache (auto-generated, OS-specific)
.hypothesis/
```

After this lands, those 4 directories disappear from `git status` everywhere. No file content removed — just stops tracking the dirs that were never tracked anyway.

**Done when:** PR titled `chore(gitignore): exclude Claude Code state + Hypothesis cache`. `git status` no longer shows the 4 dirs.

**Note on `.claude/`:** keep tracking `.claude/rules/`, `.claude/commands/`, `.claude/docs/` — those are intentionally checked-in AI context. The `.claude/projects/` and `.claude/worktrees/` subdirs are runtime state.

---

## PR 2 — Accept regenerated `.secrets.baseline`

**Files:** `.secrets.baseline` (committed regeneration)
**Effort:** 10 min

**What happened:** the baseline was regenerated on 2026-04-26 09:25 UTC, dropping 5927 stale "results" entries from old plan files (hex hashes in design docs flagged as `Hex High Entropy String`). Generated-at timestamp updated. Header policy unchanged (`detect-secrets` 1.5.0, same plugin set).

**Why this is safe:**
- 100% of removed entries were `is_verified: false` — none were ever confirmed real secrets
- All entries pointed to `.agents/plans/*.md` files containing example hex strings in design docs, never live credentials
- The new baseline (137 lines, `results: {}`) is the modern, lean shape detect-secrets recommends — fixture allowlisting moves to inline `# pragma: allowlist secret` comments (already done on `test_pool_rotation.py`, `test_export_with_creds.py`, `test_braze_service.py` in PR #42)

**Steps:**
1. `uv run detect-secrets-hook --baseline .secrets.baseline $(git ls-files '*.py' '*.md' '*.yaml' '*.json')` — confirm zero new findings
2. If clean, stage and commit `.secrets.baseline` alone
3. PR title: `chore(security): accept regenerated detect-secrets baseline`

**If step 1 reports new findings** that aren't covered by inline pragmas: add pragmas where the value is a fixture, otherwise rotate the secret. **Do not** re-add deleted hash entries — the inline-pragma approach is cleaner and survives file moves.

---

## PR 3 — Commit pending tech-debt plans + audit doc

**Files:** 16 plan files + `TECH_DEBT_AUDIT.md` + 1 architecture-quick-reference.md
**Effort:** 15 min

Two modified plan files (`tech-debt-01-quick-wins.md` got "LANDED" status; `tech-debt-03-multi-tenant-isolation.md` got 4 lines of refinement) and 14 new ones drafted across recent sessions, plus the audit doc with my F020-F024+F069 RESOLVED markers. All of these are real WIP and belong in the repo.

**Stage explicitly** (no `git add .`):
```bash
git add \
  TECH_DEBT_AUDIT.md \
  .agents/plans/tech-debt-01-quick-wins.md \
  .agents/plans/tech-debt-03-multi-tenant-isolation.md \
  .agents/plans/tech-debt-02-public-api-security.md \
  .agents/plans/tech-debt-04-connector-dedup.md \
  .agents/plans/tech-debt-05-phase-48-decision.md \
  .agents/plans/tech-debt-06-custom-checks-split.md \
  .agents/plans/tech-debt-07-engine-god-functions.md \
  .agents/plans/tech-debt-08-converter-god-functions.md \
  .agents/plans/tech-debt-09-frontend-cleanup.md \
  .agents/plans/tech-debt-10-config-and-observability.md \
  .agents/plans/48.10-synthetic-adversarial-generator.md \
  .agents/plans/48.12-proactive-qa-pipeline.md \
  .agents/plans/49.7-cta-fidelity.md \
  .agents/plans/agent-execution-hooks.md \
  .agents/plans/audit-implementation.md \
  .agents/plans/mcp-response-caching.md \
  .agents/plans/qa-meta-eval.md \
  .agents/plans/typed-artifact-protocol.md \
  .agents/plans/working-tree-cleanup.md \
  .claude/docs/architecture-quick-reference.md
```

Skim each new plan once before committing — drop any that are obviously stale or accidentally created. Most should land as-is; `.agents/plans/` is the project's planning artifact directory.

**PR title:** `docs(plans): commit pending tech-debt plans + audit progress`
**Body:** Reference the corresponding TECH_DEBT_AUDIT.md findings each plan addresses.

---

## PR 4 — Drop oversized debug binaries

**Files:** Delete from working tree (do NOT commit):
- `docs/EmailLove2.png` — 6.4 MB design reference screenshot
- `docs/eval-review-data.json` — 4.1 MB eval review data dump

**Effort:** 5 min

These are debug/review artifacts ~10.5 MB combined. Even if you wanted them in git, they'd bloat the pack file forever. If keeping is required:
- PNG → S3 with a markdown reference, or `email-templates/reference/` if it's a canonical design artifact
- JSON → regenerate via `make eval-refresh` whenever needed

**Steps:**
```bash
rm docs/EmailLove2.png docs/eval-review-data.json
# Add a guard so these don't sneak back in:
# (append to .gitignore)
docs/*.png
docs/eval-review-data.json
```

Tracked PNGs in `docs/` (e.g. architecture diagrams) need either a more specific gitignore pattern or `git add -f` exception. Audit current tracked images first:
```bash
git ls-files docs/ | grep -iE '\.(png|jpg|jpeg|gif)$'
```

If the result is empty, `docs/*.png` is safe; if not, scope the ignore tighter (e.g. `docs/EmailLove2.png` exact path, or a `docs/screenshots/` subdir convention).

**PR title:** `chore(docs): drop oversized debug artifacts; gitignore future ones`

---

## PR 5 — Long-tail triage

**Files:** ~15 files needing per-file judgment
**Effort:** 30-45 min

Each file falls into one of three actions: **commit**, **gitignore**, or **delete**. Decision matrix below — flip a coin only if you've never touched the file; otherwise the right call is usually obvious.

| File / dir | Likely action | Rationale |
|------------|---------------|-----------|
| `app/ai/agents/{dark_mode,scaffolder}/skill-versions.yaml` | **Commit** | 1-line `date:` bumps from skill-version auto-tracking. Either commit the bumps as `chore(skills)` or revert if not meaningful (`git checkout -- <file>`). Auto-touched but small. |
| `agentis_security.txt` | **Move or delete** | A 130-line essay on "agentic security architecture." Looks mis-saved — either it belongs in `docs/agentic-security-design.md` (rename + commit) or it was a chat-paste accident (delete). Read first 10 lines: it's an architectural note. Recommend rename to `docs/architecture/agentic-security-fail-safes.md` and commit. |
| `cms/apps/web/scripts/generate-icons.mjs` | **Commit** | Frontend tooling script. Likely supports `make lint-fe` or icon pipeline. Verify by reading it — if it's a real build script, commit; if it was a one-off, delete. |
| `cms/apps/web/scripts/rewrite-icon-imports.mjs` | **Commit or delete** | One-off codemod from an earlier icon refactor. Probably done its job. If grep shows no `package.json` script references it, delete. |
| `data/debug/converter-gap-analysis*.md` | **Delete** | Design-sync investigation notes from converter sessions. Already-known content per `TECH_DEBT_AUDIT.md` F010-F015. If you want them archived, move to `.agents/plans/` or `docs/research/`; otherwise delete. |
| `data/debug/reframe/` | **Gitignore** | Design-sync intermediate output. Add `data/debug/` to `.gitignore` — debug data is by definition transient. |
| `docs/components_in_shell.html` | **Delete** | Design-sync rendered output. Regenerable via `make e2e-report` or converter manual run. |
| `docs/design-to-email-pipeline.html` | **Delete** | Same as above. |
| `docs/design-to-html-pipeline-audit.md` | **Commit or move** | If it's user-authored audit content, commit to `docs/` or move to `.agents/plans/`. If it's machine-generated, delete. Read first to decide. |
| `docs/DESIGN_END_TO_END_PIPELINE.md` | **Commit** | All-caps name suggests user-authored design doc. Likely belongs in `docs/architecture/`. |
| `docs/eval-review-tool.html` | **Decision** | 64KB HTML eval review tool. If it's a working developer tool, commit to `tools/` or `cms/apps/eval-review/`. If it's a generated artifact, delete + regenerate. Check `docs/eval-review-data.json` (PR 4) for sibling. |
| `docs/html_converted_from_figma.html`, `shell_few_components.html` | **Delete** | Snake_case + descriptive names indicate one-off manual exports. Regenerable. |
| `docs/email-hub-audit.md` | **Likely delete** | Possibly an older audit superseded by `TECH_DEBT_AUDIT.md`. Diff and decide. |
| `email-templates/Icons/` | **Commit** | Subfolders `editable-stroke/`, `Merkle Brand/`, `Small Icons/` — design assets. Track these. |
| `email-templates/game_recap/` | **Commit or branch-local** | Sample template + Figma export + 3 jpgs. If it's a canonical demo, commit. If it's a one-off design exploration, gitignore via per-folder rule. |
| `email-templates/reframe-2025.html` + `reframe-assets/` | **Commit** | 15-asset email template (hero, CTAs, social icons). Tracking is how the rest of `email-templates/` works. |
| `email-templates/SUBLIME-SNIPPETS-GUIDE.html` | **Decision** | Sublime Text snippet documentation. Either belongs in `docs/email-authoring-guide.html` (move + commit) or is reference material that doesn't ship (delete). |
| `email-templates/demo-assembled-email.html` | **Delete** | Generated assembly output. Regenerable. |
| `email-templates/training_HTML/` | **Commit or gitignore** | Training fixtures. Read `data/debug/manifest.yaml` for context — if it's pinned to specific eval cases, commit; if transient, ignore. |
| `traces/pre_{file_based,golden,real_components}/` | **Gitignore** | These are eval verdict baselines from prior phase comparisons. The convention in this repo is that `traces/` outputs are transient — `traces/` is already in many gitignores. Add `traces/pre_*/` if not already ignored, or accept that these are intentional historical baselines and commit them once. |
| `workflows/converter-training-guide.html` + `*.md files` | **Commit** | Workflow runbooks. Should land in `docs/runbooks/` or `workflows/` (already exists at top level). Looks like the right home — commit. |

**PR title:** `chore(repo): triage and commit/ignore long-tail files`

If a file is genuinely "I don't know what this is": move to `tmp/` (gitignored) for a week, then delete. Don't let it sit in `git status` indefinitely.

---

## After all 5 land

```bash
git checkout main
git pull
git status
# expect:  nothing to commit, working tree clean
```

**Cross-check:** `find . -type f -not -path '*/\.git/*' -not -path '*/node_modules/*' -not -path '*/\.venv/*' | wc -l` before and after — total files should not have grown by debris.

## Order

PR 1 first (gitignore is independent and removes noise from subsequent statuses). PR 2 next (the regenerated baseline is in everyone's diff and will keep appearing until landed). PR 3 third (commits real WIP — biggest signal-to-noise win). PR 4-5 in parallel.

## Risk

- **PR 2** (`.secrets.baseline`) is the only one with non-trivial security implication. Re-run `detect-secrets-hook` against the full repo on the PR branch before merging.
- **PR 5** triage decisions are reversible (deleted files are recoverable from `git stash` or from the file's last `git log` entry if it was ever tracked).

## Done when

- [ ] PR 1 (gitignore) merged.
- [ ] PR 2 (secrets baseline) merged after full-repo re-scan passes.
- [ ] PR 3 (plans + audit) merged.
- [ ] PR 4 (oversized binaries) merged.
- [ ] PR 5 (long tail) merged.
- [ ] `git status` on a clean `main` checkout returns nothing.
- [ ] `make check` still passes (no behavioural change in any of the 5 PRs).
