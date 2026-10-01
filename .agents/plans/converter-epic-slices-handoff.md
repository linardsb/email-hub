# Handoff: create the converter epic issues (fresh context)

Paste into a new session: `Read .agents/plans/converter-epic-slices-handoff.md and follow it.`

## State (2026-09-30)

- Slicing is done. Every ticket, the dependency graph, the ledger table and the epic task list are in `.agents/plans/converter-epic-slices.md` (358 lines, 20 tickets CE-1..CE-20 plus the epic CE-0). That file is self-contained; the source brief lives outside the repo and is not needed.
- Branch `plan/converter-epic-slices`, created from origin/main `da8dbd86`. Both plan files are untracked; nothing is committed and nothing is on GitHub.
- Leave alone: `app/ai/agents/dark_mode/skill-versions.yaml`, `app/ai/agents/scaffolder/skill-versions.yaml` (dirty, not this task), `email-hub-deploy/public/`, and the untracked `.claude/{code-reviews,reports}/pr-413-*` files.

## Step 1: orient

1. `git fetch`; confirm origin/main is still `da8dbd86` or only moved forward. If it moved, grep the symbols named in the slices file and fix any line refs that shifted.
2. Read `.agents/plans/converter-epic-slices.md` in full.

## Step 2: get the open answers (one AskUserQuestion call, recommended option first)

| Code | Question | Recommended | Edit if answered otherwise |
|---|---|---|---|
| Q1 | O3 sample size: at n = 20 the #413 rule (Wilson lower bound ≥ 0.80) passes only at 20/20 | Pre-register a larger O3 sample | CE-15 "O3 at n = 20" bullet |
| Q2 | Keep CE-16 (FIXED/FILL column widths + gutter columns, closes R6) | Keep | Drop CE-16 from tickets, graph, task list |
| Q3 | Pull CE-17 (template 600px width, R9) forward from T8 | Pull forward | Fold CE-17 into CE-20 |
| Q6 | Held-out corpus size for CE-5 (non-Email-Love files) | Three or more | CE-5 scope + input table |
| Q7 | CE-19 spike designs | maap + one held-out design | CE-19 scope back to maap only |

Q4 (Figma token), Q5 (Outlook source: Litmus Instant API vs manual) and D1 (authorisation to build) do not block issue creation; they stay recorded as "needs input" on CE-3, CE-4 and CE-1.

Write the answers into the slices file: remove the "pending user OK" tags on CE-16/CE-17, and update the tables.

## Step 3: STOP and show the ticket list. Create only after the user says "create".

## Step 4: create (after "create")

1. Commit both plan files on `plan/converter-epic-slices` (conventional message, e.g. `docs(plans): slice converter fidelity epic into tickets`; show `git diff --stat origin/main...HEAD` first; stage only these two files). Pushing / PR only if the user asks.
2. `gh label create epic` if missing (`gh label list | grep -w epic`).
3. Create CE-1..CE-20 in dependency order so each `depends on` can use real numbers. Each issue body = that ticket's section from the slices file plus the "Conventions every ticket carries" table (or a link to it on the branch). Title = ticket title without the `CE-n:` prefix.
4. Create CE-0 last, labelled `epic`: epic summary, conventions, then the task list with `CE-n` replaced by issue numbers. Row shape must match `.claude/skills/piv-next/next.sh` exactly:
   `- [ ] #<n> — <title> (depends on #<m>, #<k> · <note>)` or `(depends on none)`. Notes go inside the parentheses after ` · `. Never write a bare `#0066cc`-style hex in titles or rows (it reads as an issue ref); write "default blue 0066cc".
5. Edit each ticket body to link back to the epic (`Part of #<epic>`).
6. Run `.claude/skills/piv-next/next.sh`; it should list CE-1, CE-2, CE-4 (and CE-15) as unblocked.
7. Record the issue numbers in the slices file (a `CE-n → #N` table) and commit.

## Public-repo rules for issue bodies

- The repo is public. Cite P/R/T codes only: no vault paths, no forum contributor names, no private business context (D1's reason).
- Figures copied from the plan stay tagged "brief, not re-run" / derived / observed as they are in the file.
- Never run `gh pr merge` or `gh pr ready`.
