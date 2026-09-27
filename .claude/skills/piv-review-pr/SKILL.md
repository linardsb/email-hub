---
name: piv-review-pr
description: Full pull-request review — fetch the PR, run the project's validation, review the diff with fresh eyes (dispatching the code-reviewer agent), categorize issues by severity, post the review to GitHub (`gh pr review --comment` on a self-authored PR, which GitHub cannot approve), and save a report. The agentic gate that runs on an open PR before a human approves. Use after piv-create-pr.
argument-hint: "<pr-number | pr-url | branch> [--approve | --request-changes]"
---

# Review PR: The Agentic Gate Before the Human

**Input**: $ARGUMENTS

The point of this skill is **fresh eyes**: it reviews the PR in a clean context — *not* the context that wrote
the code — and can hand the deep analysis to the **`code-reviewer` agent**, which is the whole reason the review
catches what the author's own context rationalizes away. It posts its verdict on the PR, then a **human** makes
the final call.

## Phase 1 — Fetch the PR

Resolve the input to a PR number (a number, a URL, or a branch via
`gh pr list --head <branch> --json number -q '.[0].number'`). Then:

```bash
gh pr view {N} --json number,title,body,author,headRefName,baseRefName,baseRefOid,mergeStateStatus,state,additions,deletions,changedFiles,files
gh pr diff {N}
gh pr checkout {N}

# The base branch's LIVE tip, which is what Phase 3's guarantees trigger compares.
# `baseRefOid` is the base sha recorded ON THE PR: it moves only when someone
# reconciles the branch, so it cannot answer "has the base moved under this PR?"
# — by the time it changes, the drift is already fixed.
BASE=$(gh pr view {N} --json baseRefName --jq .baseRefName)
# Dead-base guard (stacked PR) first: a deleted base leaves `origin/$BASE` unresolvable below.
# Ask GitHub, not git: a squash-merged base's tip is not an ancestor of main.
[ "$BASE" != main ] && gh pr list --head "$BASE" --state merged --json number,headRefOid,mergedAt --jq '.[]'
git fetch origin && git rev-parse "origin/$BASE"

# The review scope: the PR's own commits against the live base tip (`main` unless the
# PR is stacked). A stale local base ref makes `$BASE...HEAD` show foreign commits.
git diff --stat "origin/$BASE...HEAD" && git diff "origin/$BASE...HEAD"
```

State guard: `MERGED`/`CLOSED` → stop ("nothing to review"); the dead-base guard prints a row → skip Phases 2–5 and
post it via Phase 6 as the only finding, Critical ("base `$BASE` already merged as #M; this PR would merge into a dead
branch and never reach `main` — rebase onto `main` per `piv-create-pr` Phase 0"; #358 and #361 both did); `DRAFT` → every PR opens as one. `gh pr checks {N}`
says why it still is: checks pending → review anyway and say so; a red check → that check is finding #1 (Critical if
it is one of the gate jobs in `.github/workflows/ci.yml` — `backend` / "Backend (lint + types + security + test)" or
`frontend` / "Frontend (lint + format + types + test)", the names `gh pr checks` prints — High otherwise), and the review
does not wait for the flip.

## Phase 2 — Load the context (so you review against the right bar)

- **`CLAUDE.md`** + `.claude/rules/*.md` + any `.claude/references/` — the project's standards are the review rubric.
- **The implementation report** (if `piv-implement` wrote one) + its plan. Branches carry a prefix and report slugs
  a phase number (`feature/g12-generalization-insurance` → `53-g12-generalization-insurance-report.md`), so match on
  the branch's last segment — `ls .claude/reports/*"${BRANCH##*/}"*` — and fall back to a report or plan path named
  in the PR body. Read the
  **documented deviations**. A documented deviation is an *intentional decision*, **not** an issue — only flag
  *undocumented* divergences. (No report? Review normally and note its absence.)
- The PR's own intent (title/body): what problem it claims to solve.

## Phase 3 — Run validation

Run the project's real suite (the **`piv-validate`** skill, or the plan's validation commands) — tests, type-check,
lint, build. Capture pass/fail + counts. A red suite is a finding in itself.

Then read the PR's open code-scanning alerts **every time, not only on a red check**: Semgrep
(`.github/workflows/semgrep.yml`) runs with `continue-on-error: true` and its SARIF upload is
`continue-on-error` too, so its check is green whatever it finds; the `codeql` job in `ci.yml` (expected, not yet
written) reports to the same API. Use the `gh api … code-scanning/alerts?ref=refs/pull/{N}/merge` command in
`piv-fix-review-findings` §1.5 and fold each line in as a finding at GitHub's severity, tagged with the tool that
raised it (`Semgrep`, `CodeQL`). A 403/404 from that endpoint means code scanning is unavailable on the repo — say
so in the report; it is not "zero alerts".

## Phase 4 — Review the diff (dispatch the code-reviewer agent)

Hand the deep pass to the **`code-reviewer` agent** (`.claude/agents/code-reviewer.md`) — it reviews against the
project's standards and reports **high-confidence issues only**. Read every changed file *in full* (not just the
diff) for context. Cover: correctness · type safety · pattern/standards compliance · security · performance ·
tests present · maintainability.

**Categorize every issue by severity:**

| Severity | Meaning |
|----------|---------|
| **Critical** | Blocking — security, data loss, crashes |
| **High** | Should fix before merge — type-safety holes, missing error handling, logic errors |
| **Medium** | Pattern inconsistencies, missing edge cases, *undocumented* deviations |
| **Low** | Suggestions, minor polish |

Acknowledge what's done well, too — review is constructive, not just a defect list.

### The constraint pass — before you recommend a fix

For each proposed fix, grep the plan Phase 2 loaded, then read every hit — ACCEPTANCE CRITERIA and
CONTEXT REFERENCES first, but a task's `GOTCHA` is where the template puts constraints (in
`piv-plan-implementation`, the task template's `**GOTCHA**` bullet) and a GOTCHA is binding (the 'GOTCHA is
binding' sub-bullet): `grep -in "do not modify\|do not edit\|read-only\|no changes to\|frozen" <plan>`.
One review prescribed a log line in a file whose acceptance criterion froze it ("no changes to …"); only the
fix pass's triage caught it. A fix that breaks the PR's own AC gets `gh issue create` and its number in
the report, not an inline recommendation. No plan loaded → skip.

### The numbers pass — do this explicitly, it is not covered by the agent

typecheck, lint, test and build cannot read prose, so **you are the only gate on every figure in the PR
body and the implementation report.** Two consecutive tickets in the project this skill came from shipped a
false number to `main`, and both times the reviewer re-deriving it was the first and only check.

Enumerate every figure and ask of each: **which run produced this?**

- Can it name one → `observed`. Spot-check that the run's own output actually says so.
- It cannot → it is `derived` or `expected`, and must say which. **A derived figure sitting under an
  "Observed" heading is a finding**, at the severity its downstream use warrants — a number that a later
  ticket could de-scope work on is **High**, not Low.
- Correct arithmetic does not make a figure observed. One report's `30 = 6 cells × 5 polls` was sound
  arithmetic, truthfully passed its own "show the arithmetic" AC, and still described a run that never happened.

When a figure credits a mechanism ("proves the cache saves 5×"), ask **what was held constant to isolate
it**. If the experiment cannot distinguish the credited mechanism from something else in the path, the
attribution is the defect even when the count is right.

The same applies to a **failure and its cause**. Real red output plus an inferred cause is still an
unverified claim: ask what in the code *permits* the cause just named, and read that code. One PR saw 8
integration tests fail, named Redis, and wrote it into `CLAUDE.md`, the implementation report, the PR body
and a new GitHub issue — while the test harness overrode the store in question with an in-memory one, so
the mechanism could not fire. **A digit that survives re-observation is not licence to rewrite the sentence
around it.**

Check the claim's **subject**, not just its digits — grep the noun (`quantiz`, `grid`, the issue number)
and read every hit. A retired claim survives as a verb ("the cache this script *measures*") long after its
number is gone, and it survives in the **PR body**, which is the most-read surface and the only one not in
the working tree.

### The guarantees pass — when the base moved under this PR

A rebase onto a merged base sweeps *figures* well, because figures look like figures. It does not sweep
**guarantees**, and a guarantee invalidated by a sibling merge fails silently — the suite stays green
because both sides were re-run, and only the *relationship* between them broke. One PR shipped one to review
in a file whose own comment named the exact condition that would invalidate it.

**The trigger, so it is observable rather than remembered:** compare the base branch's **live tip** — Phase 1's
`git rev-parse origin/<baseRefName>`, after a `git fetch origin` — against the `**Base** … @ <sha>` recorded in
the newest existing `.claude/code-reviews/pr-{N}-review*.md`. Different → the base moved, run this pass. No prior
report → first round, skip it. `baseRefName` alone cannot answer this: a rebase leaves the name identical.

**Not `baseRefOid`**, which is what this trigger once compared. That field is the base sha recorded *on the
PR*; it moves when someone reconciles the branch, which is *after* the drift has been fixed, so the comparison
returns equal for exactly the window in which the pass is needed. In the project this skill came from, between a
sibling PR merging and a later `gh pr update-branch`, `baseRefOid` still read the sha round 1's
report header recorded while `origin/main` had moved on: old comparison equal, pass skipped; live tip different,
pass fires. That was the one PR whose only High finding was a guarantee broken by that base move.
`mergeStateStatus == BEHIND` corroborates it on the same `gh pr view` call, but it is not the comparison: GitHub
computes it lazily and answers `UNKNOWN` until it has.

For every PR whose base changed since the last review round:

- **Re-read the previous round's own rebase notes and close each by re-derivation, not by a green run.** A note
  that says "after this rebase, re-run X and Y" is discharged only when the *relationship* it names has been
  re-derived. One PR's round 1 named the coupling exactly and was closed by re-running two specs;
  they passed, because the divergence was structurally untestable, and the guarantee shipped broken to round 3.
  A passing suite is not evidence about a relationship no fixture can express.
- Grep the diff for **conditional comments** — "if X changes, this needs re-deriving", "as long as",
  "assuming", "the same row set". Each is a tripwire someone set deliberately. Check whether the condition
  fired; if it did, the comment is now a warning about something that has already happened.
- Grep for **absolute claims** in docblocks, the report and the PR body — "returns null when", "always",
  "never", "the same as", "cannot". Re-derive each against the merged base, not the pre-rebase tree they
  were written on.
- Where two surfaces count or compare the same thing, name the case where they **stop** agreeing. A pure
  function whose inputs cannot distinguish that case is a seam problem, not a fixture problem — say so,
  because no test can be added to catch it.

### The fix-mechanism pass — round ≥ 2

A prior round exists (`.claude/code-reviews/pr-{N}-review*.md`) → for **each Critical/High the previous
round raised and the fix pass closed, ask what the fix's mechanism newly permits**, not only whether the
original repro passes. A fix that reroutes delivery through a request can swallow that request's failure;
a chain added for one error can lack a terminal `catch`; a flag can be set before the thing it claims.
Both of one PR's round-2 Highs were round-1 fixes whose repros passed — round 2 found them by asking
this question by instinct; ask it by procedure. Cross-check `.claude/reports/pr-{N}-review-fixes.md` —
its per-finding grep list and closing-command outputs (`piv-fix-review-findings` §2/§4 require both):
a closed finding with neither, or no such file at all, is re-opened, not trusted.

## Phase 5 — Decide

- **Approve** — no critical/high issues, validation passes, matches intent.
- **Request changes** — high issues, or fixable validation failures, or undocumented pattern violations.
- **Block** (request-changes, strongly) — critical security/data issues, or wrong fundamental approach.
- Honor an explicit `--approve` / `--request-changes` flag (this skill's own argument, not `gh`'s — the
  verdict lands in the report body), but never approve over an unresolved critical issue.

## Phase 6 — Post to GitHub + save the report

Write the report to `.claude/code-reviews/pr-{N}-review.md` (summary · issues by severity with `file:line` + fix ·
validation table · what's good · recommendation). **The header must carry `**Head** <sha> · **Base** <ref> @
`<baseRefOid>`** — the base SHA is what makes the next round's guarantees pass triggerable; a base *name* is
unchanged by a rebase and so cannot detect one. Keep recording `baseRefOid`: it is the right thing to *record*
(the base this round actually reviewed against). The next round compares it against the base branch's **live
tip**, never against `baseRefOid` again — the guarantees pass says why. Then post it:

```bash
# GitHub refuses --approve and --request-changes from the PR's own author ("Can not approve your
# own pull request"). Compare the PR author with the authenticated gh user first.
AUTHOR=$(gh pr view {N} --json author -q .author.login); ME=$(gh api user -q .login)
if [ "$AUTHOR" = "$ME" ]; then
  gh pr review {N} --comment --body-file .claude/code-reviews/pr-{N}-review.md   # verdict lives in the body
else
  gh pr review {N} --approve --body-file .claude/code-reviews/pr-{N}-review.md   # or --request-changes, per Phase 5
fi
```

On a self-authored PR the report's first line states the verdict and that it is recorded as a comment because
GitHub blocks a formal self-approval.

## Output + hand off

Print: PR number/URL · issue counts by severity · validation results · the recommendation. Then hand off:
**"Posted on the PR. A human now reviews the code + this review and merges."** If there are issues, the natural
next step is **`piv-fix-review-findings`** on the report, then re-run validation.

Stacked PR (base is not `main`): this review cannot see a base that merges *after* it. Add to the hand-off:
"Merge only after the base PR has merged; then `git rebase --onto origin/main <base headRefOid>`, retarget to
`main`, and merge. After merge, confirm it landed:
`git fetch origin && git merge-base --is-ancestor $(gh pr view {N} --json mergeCommit -q .mergeCommit.oid) origin/main`
(non-zero exit → it merged somewhere other than `main`; check that base's PR and re-land on `main` if it is dead)."

## Notes

- **Fresh eyes is the whole point** — run this in a clean context (or let the `code-reviewer` agent be the clean
  context). Don't review with the session that wrote the code; it rationalizes instead of scrutinizing.
- This is the *agentic* gate; it does not replace the human — it gives the human a validated, triaged PR to
  approve. Going deeper (multiple review agents, tuning the reviewer to your stack, the validation pyramid) is
  the code-review-as-a-component material later in the course.
