---
name: piv-create-pr
description: Push the current feature branch and open a pull request as a draft; CI's `ready` job flips it to ready for review when every ci.yml job and `codeql` are green on that head. Use after a ticket's implementation is committed on its own branch — it detects the base branch, pushes, opens the PR with a clear body (summary · what changed · validation status), and returns the URL to hand to a reviewer.
argument-hint: "[--base <branch>] (default: auto-detected)"
---

# Create PR: Open the Pull Request, Hand Off for Review

This is the **ship** step of the PIV loop: the implementation is committed on a feature branch; now open the PR
so it can be reviewed (by the `piv-review-pr` agentic gate, then a human).

## Phase 0 — Detect the base branch

Don't hardcode `main`. Resolve it:
1. If `$ARGUMENTS` contains `--base <branch>`, use that.
2. Else: `git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'`
3. Fallback: `git remote show origin 2>/dev/null | grep 'HEAD branch' | awk '{print $NF}'`
4. Last resort: `main`. Store as `{base}`.

**Dead-base check (stacked PR).** If `{base}` is not `main`, ask GitHub whether the base branch has already
landed: `gh pr list --head {base} --state merged --json number,headRefOid`. Use this live query, not local
branch state or `git merge-base --is-ancestor`. A squash merge leaves the base branch's tip off `main`, so
ancestry reports "unmerged" for a base that merged hours ago. Any row → STOP: the PR would merge into a dead
branch and never reach `main` (#358 → re-landed as #359, #361 → re-landed as #362). Rebase onto `main` with
`git rebase --onto origin/main <headRefOid>` (a plain `git rebase origin/main` replays the base's commits that
`main` already holds as one squash; `git fetch origin pull/<number>/head` first if that sha is not local), then
set `{base}` = `main`.

## Phase 1 — Validate git state

```bash
git branch --show-current
git status --short
git log origin/{base}..HEAD --oneline
```

| State | Action |
|-------|--------|
| On `{base}` | STOP: "Create a feature branch first (the ticket should be on its own branch)." |
| Uncommitted changes | STOP: "Commit (or stash) before opening the PR." |
| No commits ahead of `{base}` | STOP: "Nothing to PR." |
| Existing PR for this branch (`gh pr list --head $(git branch --show-current) --json url`) | STOP and print the URL. |
| Clean, commits ahead, no PR | PROCEED |

## Phase 2 — Gather context for the body

- **Project conventions:** if `.claude/references/conventions.md` exists, read its `## pr` section — its rules
  win over the default template below (sections, tone, what must be stated). That file is where a project's
  specifics live; this skill stays general.
- Commits: `git log origin/{base}..HEAD --pretty=format:"- %s"`
- Files: `git diff --stat origin/{base}..HEAD`
- **Every size, count or per-path figure in the body must be produced by a command you run NOW, against the
  final commit, with the command shown beside the figure.** Never transcribe one from the plan, the
  implementation report, a review, or an earlier draft of this body — those are the four places it has been
  wrong before. If a figure is a decomposition, print every bucket and its sum so the arithmetic is checkable
  (`477 + 62 + 94 + 485 = 1,118`), and make sure each bucket's label matches what it actually contains.
  A tag like `observed` says where a number came from; it does **not** say the number is right — correctly
  tagged figures have shipped wrong, and a *correction* to one has been wrong twice more before it was right.
- **Implementation report** (if `piv-implement` wrote one — `.claude/reports/<…>-report.md`): pull the summary,
  validation results, and **documented deviations** (these belong in the PR body — they tell the reviewer what
  was intentional).
- Linked issue: look for `#123`, `Closes #…`, `Fixes #…` in the commits/branch name. The body links it as
  `Closes #N` — GitHub closes the issue on merge only for a closing keyword; `Implements #N` leaves it open.
- PR template: if `.github/PULL_REQUEST_TEMPLATE.md` exists, fill it; else use the default below.

## Phase 2.5 — Generate the validation block, then find the inherited figures (blocking)

Two scripts live beside this skill. **They are referenced here so that deleting them shows up in a
diff** — a script that only prose mentions, and no executable path calls, gets deleted in a cleanup and
leaves only the prose about it behind.

```bash
.claude/skills/piv-create-pr/scripts/record-gate.sh                    # make check-full
.claude/skills/piv-create-pr/scripts/record-gate.sh -- make ci-fe      # when cms/ changed
.claude/skills/piv-create-pr/scripts/inherited-figures.sh <draft-body.md> <report.md> [--pr {N}]
```

**`record-gate.sh` runs the gate and prints the Validation block. Paste it; do not retype it.** It
exits with the gate's own code (3 for a short gate), so a red gate cannot produce a green-looking
record. It writes `.claude/last-gate.json` (gitignored); each `record-gate.sh` run overwrites it, so
when both backend and frontend gates apply, check each record straight after its own run. **STOP and
fix before opening the PR if** the file is missing, its `head` is not the current `HEAD` (the record
describes a different tree — most often after a rebase), `dirty` is true (the run covered uncommitted
work), `exit_code` is non-zero, `make_errors` is non-empty, or `short_gate` is true. Read
`short_reasons` whenever `short_gate` is true: a pytest count under the floor, a missing vitest
summary, a `|| true`-masked step that failed (`check-fe`'s lint and format:check), a target that never
ran, or a tree that changed during the run (`make lint` rewrote files) are each a green-looking exit
that checked less than it claims. `pytest_passed` is the `make test` run's count, not the smaller
`golden-conformance` run that prints after it.

**`inherited-figures.sh` prints every measurement it can bind to a unit word or a duration that this
body shares with the implementation report or with the PR's own previous body** — not every shared
figure: its duration matcher drops a minute prefix, so `1m22.325s` and a bare `22.325s` reduce to one
key. Each hit is *unaudited*, not necessarily wrong: re-derive it at this
head, or say why it is head-independent. Pass `--pr {N}` when updating an existing PR — the published
body is the most-read surface and the only one no working-tree grep can reach. No implementation report
(a docs-only PR) is an ordinary case: it prints a note and exits 0, which is not a pass.

**What neither script can catch — these stay by-eye checks:**

- **A right number under a wrong label.** The figure can be correct while the label is the defect.
- **A claim with no numeral at all.** "GitHub retargets the base branch automatically" has shipped in a
  PR body — no digit for a numeric check to bind to, and false.
- **Retire the claim's subject, not its digits.** A retired claim survives as a verb ("the cache this
  script *measures*") long after its number is gone. Grep the noun — `quantiz`, `grid`, the issue
  number — and read every hit, including the PR body.

## Phase 3 — Push and open the PR

```bash
git push -u origin HEAD
```

```bash
gh pr create --draft --base "{base}" --title "{type}({scope}): {concise description}" --body "$(cat <<'EOF'
## Summary
{1-2 sentences: what this ticket delivers}

## What changed
{commit summaries}

## Validation
{the Validation block record-gate.sh printed, pasted verbatim; one per gate run}
- Manual check: {what was exercised, or "pending review"}

## Notes for the reviewer
{documented deviations from the plan — intentional decisions — or "none"}

## Linked
Closes #{N}   <!-- or "none" -->

_Opened as a draft; CI's `ready` job flips it when every ci.yml job (`backend`, `frontend`, `sdk-check`, `trivy`, `migrations`, `integration`, `migration-lint`, `commit-lint`, `e2e-smoke`) and `codeql` are green on this head. A red job leaves it here with the failing check on the PR._
EOF
)"
```

(`{type}` = feat/fix/refactor/… from the work; `{scope}` = the feature slice, e.g. `design-sync`; the
conventions file's `## pr` section has the full title shape.) Never run `gh pr ready`; the hook refuses it and CI owns the
flip. If the PR stays a draft, the failing check is the next finding.

## Output

```bash
gh pr view --json number,url,title,baseRefName,headRefName
```

Report the PR number + URL, the base ← head branches, and **"Draft. CI flips it ready when every ci.yml job and
`codeql` are green; then run `piv-review-pr <number>`, then the user merges."** No CI duration is quoted here: none
has been measured for the `ready` flip yet (`expected`). A self-authored PR cannot be formally approved (author ==
`gh` user), so `piv-review-pr` posts its verdict with `gh pr review --comment`. This is the handoff point: the
agent's loop ends at an open PR; review and merge are the gates.

**Stacked PR (`{base}` is not `main`):** the Phase 0 check cannot see a base that merges *after* this PR opens.
Also tell the user: "Merge this only after the base PR has merged; then
`git rebase --onto origin/main <base headRefOid>`, retarget it to `main`, and merge. After merge, confirm it landed:
`git fetch origin && git merge-base --is-ancestor $(gh pr view {N} --json mergeCommit -q .mergeCommit.oid) origin/main`
(non-zero exit → it merged somewhere other than `main`; check that base's PR and re-land on `main` if it is dead)."
CI runs only on PRs whose base is `main` (`.github/workflows/ci.yml:6-7`), so a stacked PR gets no CI run and
no `ready` flip until it is retargeted to `main`.

## Notes

- Tool-agnostic in spirit: this skill uses GitHub (`gh`); the same motion is "open a merge request" on GitLab,
  or "mark ready for review" wherever your team works. There is no commit-on-`{base}` shortcut here: the
  `no-commit-to-branch` pre-commit hook (`.pre-commit-config.yaml`) refuses commits on `main`, so every change
  goes through a branch and a PR.
- The `ready` and `codeql` jobs are `expected`: they arrive with the CI PR that adds them (PR B of the AI-layer
  import). Until that merges, no job flips the draft; the user marks it ready after reading the checks.
- Sets up parallel work: one branch per ticket → one PR per ticket is exactly what makes worktree parallelism
  (running independent tickets at once) clean.
