# Conventions — how email-hub ships work

> Ship-step conventions live here. `piv-commit` reads `## commit`, `piv-create-pr` reads `## pr`, and PR
> reviews follow `## review`. The rules below win over those skills' generic defaults.

## commit

**Mechanical (hook- and CI-enforced):**
- Subject is `type(scope): description`. Allowed types (11): `feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert`,
  enforced by the `commit-msg` hook (`.pre-commit-config.yaml:81-97`, conventional-pre-commit) and again by
  CI `commit-lint` (`.github/workflows/ci.yml:286-314`, regex at `:300`, also accepts `!` for breaking).
  CI checks every non-merge commit in `origin/<base>..HEAD`. `.claude/commands/commit.md:78` lists only 8 of
  the 11; the hook is the source of truth.
- End-of-day snapshots use `chore(wip):`, never `wip:` (the hook rejects the bare tag).
- Never commit on `main`: `no-commit-to-branch` (`.pre-commit-config.yaml:29-31`) refuses it. Branch first.
- A failed hook means fix the cause and make a NEW commit. Never `--no-verify`.
- Stage by path; never `git add -A` / `git add .` (`commit.md:62`). STOP if `.env`, `*.pem`, `*.key`,
  `credentials.*` or `secrets.*` is in the change set (`commit.md:33`).
- Subject under 72 chars, imperative mood; body says WHY (`commit.md:83-85`). No gate enforces the length.
- Trailers: use the attribution lines from the session's system-reminder (the model name in `commit.md:75`
  is stale).
- If the commit touches AI-context files (`.claude/commands|rules|docs/*.md`, `CLAUDE.md`), add a `Context:`
  block after the body (`commit.md:87-103`).

**Scope:** the feature slice or area touched: `design-sync` (hyphen, not `design_sync`), `agents`,
`qa-engine`, `blueprints`, `knowledge`, `connectors`, `components`, `auth`, `core`, `shared`, `cms`
(`commit.md:80`), plus `deps`, `ci`, `flags`, `security`, `deferred-items`, `tech-debt`. `observed`: the
last 300 non-merge subjects on `origin/main` (`git log origin/main --no-merges --format=%s -300`) are led
by `chore(deps)` 98, `chore(deps-dev)` 42, `fix(design-sync)` 25, `feat(design-sync)` 14.

**Judgment:** <!-- #commit-quality -->
- The message describes THIS diff; a reader of the message alone predicts roughly which files changed.
- One atomic concern per commit. Gate side effects (`skill-versions.yaml` `date:` churn) are not staged.

## pr

**Mechanical:**
- Base `main`. The agent opens a **draft** PR only; CI's `ready` job flips it to ready when every check is
  green on that head (`expected`: the `ready` job does not exist yet). **Only the user merges** (squash), so
  the PR title becomes the subject on `main` and gets ` (#N)` appended. The agent never runs `gh pr merge`
  or `gh pr ready`.
- Title uses the commit shape. Track work appends the track tag: `feat(design-sync): <what> (Track G · G11)`,
  `fix(design-sync): <what> (Track G · G6 / 51.2)` (`observed`: #352-#365, `gh pr list --state merged
  --limit 25 --json number,title`). Titles run long; no gate checks title length.
- Branch `<prefix>/<kebab-slug>`. `observed` over the last 100 merged PRs (`gh pr list --state merged --limit
  100 --json headRefName`): `dependabot` 43, `fix` 25, `chore` 17, `investigate` 3, `feat` 3, `archon` 3,
  `feature` 2, `docs` 2. Prefixes do not reliably mirror the title's type (`fix/phase-53g7-...` shipped as
  `feat(...)` in #358), so none is enforced.
- Body sections, in order: `## Summary`, `## What changed`, `## Validation`, then `## Notes for the reviewer`
  (documented deviations) and `## Linked` or `## Ledger` (`observed`: #354, #360, #364, #365).
- Link the work: `Closes #N` when a GitHub issue exists (`expected`: new rule with the draft-PR flow). Today
  0 of the last 100 merged bodies use `Closes`; 4 use `Fixes #N` (#303, #310, #312, #329) (`observed`,
  `gh pr list --state merged --limit 100 --json body`); either keyword closes the issue on merge;
  Track PRs link the plan and the `.agents/deferred-items.json` entry they close instead.
- Footer: the PR attribution line from the session's system-reminder.

**Judgment:** <!-- #pr-quality -->
- Summary says WHY the change exists. Validation lists what actually ran on this head (`make check-full`,
  `make ci-fe`, eval/A3 gates), each figure tagged `observed`/`derived`/`expected`.
- Deviations from the plan (from `.claude/reports/<slug>-report.md`) appear in the body.

## review

**Mechanical:**
- Output file `.claude/code-reviews/pr-<N>-review.md`.
- Starts with a verdict line: **APPROVE** / **REQUEST CHANGES** / **COMMENT**, and how it was reviewed.
- `## Validation`: the gates run on the PR head, with results.
- `## Findings by severity`: Critical / High / Medium / Low (tracked example `.claude/code-reviews/pr-354-review.md:26-35`). Every finding carries
  `file:line`, what is wrong, and a concrete fix. An empty tier says "none".
- `## Recommendation`: one paragraph. Never approve over an unresolved Critical.
- Self-authored PRs cannot be `--approve`d (author == gh user). Post the report with
  `gh pr review <N> --comment --body-file .claude/code-reviews/pr-<N>-review.md`.

**Judgment:** <!-- #review-routing -->
- Review against `origin/main...HEAD`, not a stale local `main`.
- Weight load-bearing code: email HTML shape (table-only, no `<p>`/`<h*>`), `TemplateAssembler` as the single
  HTML writer, per-agent sanitization, auth/BOLA checks, migrations, and converter A3 deltas on non-target cases.
