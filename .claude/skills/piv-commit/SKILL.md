---
name: piv-commit
description: Creates a new git commit for this task's uncommitted changes with an atomic, conventionally-tagged message. Use when work is complete and ready to be committed.
---

# Commit: Create a New Commit

Create a new commit for this task's uncommitted changes. Never `git add -A` / `git add .`: stage by path.

## Process

0. **Read this project's conventions.** If `.claude/references/conventions.md` exists, read its `## commit`
   section and follow it — those rules win over the defaults below. That file is where a project's specifics
   live; this skill stays general.
1. Run `git status && git diff HEAD && git status --porcelain` to see what files are uncommitted.
   Then run `git log --format='%h %s' origin/main..HEAD`; if one or more consecutive top commits start with
   `chore(wip):`, run `git reset --soft <first non-wip ancestor>` before staging (for a branch whose every
   commit is WIP, `git reset --soft $(git merge-base HEAD origin/main)`). Fold every one, not just the top:
   they are `piv-implement` end-of-day snapshots, not real commits, and after one the other three commands
   print nothing at all. This commit changes the tree, so the gate runs after it (`piv-validate` on the
   committed head), never before.
   **Gate side effects:** `make test` / `make check-full` rewrite the `date:` line of
   `app/ai/agents/*/skill-versions.yaml`. If that is the only change in such a file and the task did
   not touch agent skills, `git checkout -- <file>` it. Any other file outside the plan's
   "Files to Create/Modify" list (or parallel work, per CLAUDE.md § Parallel Work Awareness): leave it
   unstaged and name it in the output.
2. **Plan-staleness check**, then stage the task's untracked and changed files by path. Run `ls .claude/reports/`; if this
   branch's plan has a report there, read both its `## Deviations from the plan` **and** its
   `## Tasks completed`, and edit every divergence — including a task whose shipped files or queries
   differ from the plan's IMPLEMENT line (the report names one function, the plan still names the one it
   replaced) — into the plan's `## STEP-BY-STEP TASKS`, or date it under `## AMENDMENTS` as superseded.
   Staged here, not later: a stale plan on `main` misleads the next ticket.
3. Write an atomic commit message with an appropriate, descriptive summary.
4. Add a tag such as `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, etc. that reflects our work.
   The `commit-msg` hook (`.pre-commit-config.yaml`, conventional-pre-commit) accepts only
   feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert, and `no-commit-to-branch` refuses
   commits on `main`. If a hook fails, fix the cause and make a NEW commit; never `--no-verify`.

## Output

A single commit containing this task's changes, with a conventional-commit-style message
(`<tag>: <atomic description>`) that accurately reflects the work done.

After the commit succeeds, print two clearly labelled summaries:

### What Changed
One short paragraph (3–6 sentences) describing the feature/fix/refactor that was committed — what problem it solves and what files were the key touch points. Write for a developer skimming the git log.

### AI Layer Changes
Only include this section if any files under `.claude/` were modified or added (CLAUDE.md, `.claude/references/`, `.claude/skills/`, `.claude/agents/`, etc.).

List each changed AI-layer file with a one-line note on what evolved and why. If nothing in `.claude/` changed, omit this section entirely.
