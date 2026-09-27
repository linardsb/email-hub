---
name: deferred-items
description: Adds, closes and SHA-stamps entries in the deferred-items ledger `.agents/deferred-items.json`. Use when the user says "add a deferred item", "log this as deferred", "defer this to the ledger", "close ledger entry X", "retire this deferred item", "stamp the merge SHA", "stamp the ledger", when a PR that edited the ledger has just been squash-merged (its `pending` placeholders need the squash SHA), when a plan ships with a soft acceptance criterion, or on /deferred-items. Do NOT use to look up or cross-reference existing entries before planning; that is `/preflight-check` Step 2.
argument-hint: "add <what> | close <id> | stamp <PR number>"
---

# Deferred Items

Write to the open-gap ledger `.agents/deferred-items.json` (entries under `items`) in three ways: **add** an
entry, **close** one, and **stamp** the squash-merge SHA over the `pending` placeholders a merged PR left.
The schema and the add/close rules are owned by `.claude/rules/deferred-items.md`; open it before any write.
Looking entries up is not this skill: `/preflight-check` Step 2 (`.claude/commands/preflight-check.md`) does it.

Route on `$ARGUMENTS`: `add …` → Add, `close <id>` → Close, `stamp <N>` or "the PR merged" → Stamp. Ask only
when the operation is genuinely unclear.

## Add

1. **Gate on load-bearing.** Add only what the rule file's "When to add an entry" list names: a soft acceptance
   criterion, a speculative gap found by inspection, or a code-shape concession. Refuse anything on its
   "Don't add" list (a bug fixable now, a task with a home in `docs/TODO-completed.md` / `.agents/plans/` / an
   issue, a subjective preference). State the refusal and the reason; write nothing.
2. **Check for a duplicate.** Grep the ledger for the file and the symptom. A match gets a `notes` line on the
   existing entry, not a second entry.
3. **Append one object** to `items` with every required field from the rule file's Schema section:
   - `id` = `phase-<N>.<sub>-<short-slug>`, unique across `items`; `phase` = `<N>.<sub>`.
   - `status: "deferred"`; `severity` ∈ `soft` | `speculative` | `known-bug` (ledger severity, not review
     severity: confirmed defect → `known-bug`, plausible by inspection → `speculative`, needs data or a fixture
     that does not exist yet → `soft`).
   - `introduced` = today (`YYYY-MM-DD`); `introduced_commit: "pending"`.
   - `summary`, `code_refs` (`file:line (symbol)`, each one opened), `symptom_if_broken`, `closes_when` (a
     concrete, checkable condition).
   - Optional fields only from the rule file's optional list.
4. Validate (below).

## Close

1. **Prove `closes_when` is met**, not merely addressed: name the test, commit or observation showing the
   `symptom_if_broken` can no longer occur, and put that evidence in the PR description or the run's report.
   If it is only partly met, add a `notes` line and leave it `deferred`.
2. Set `status: "closed"` and add `closed_commit: "pending"`. Leave every other field as it is.
3. **Never delete an entry**, closed or not.
4. Validate (below).

**Why `"pending"` and never a SHA before merge:** the user squash-merges, so a branch-head SHA never lands on
`main`. PR #365 wrote pre-merge SHAs (`405f17d0`) that `git merge-base --is-ancestor` shows are not on `main` (`observed`).
`"pending"` is the placeholder the Stamp step replaces.

## Stamp (after the user squash-merges PR N)

`main` blocks direct commits (`no-commit-to-branch` in `.pre-commit-config.yaml`), so the stamp lands via its
own branch and PR.

```bash
git status --porcelain -- .agents/deferred-items.json   # must print nothing; else stop (or use a clean worktree)
git fetch origin
gh pr view N --json state,mergeCommit -q '.state + " " + (.mergeCommit.oid // "")'   # must be "MERGED <oid>"
SHA=<oid from the line above>
git switch -c chore/stamp-ledger-prN origin/main
python3 .claude/skills/deferred-items/scripts/stamp_ledger.py --sha "$SHA" --dry-run
python3 .claude/skills/deferred-items/scripts/stamp_ledger.py --sha "$SHA"
```

1. Read the dry-run list and confirm every line is an entry PR N added or closed. The script scopes itself to
   placeholders PR N wrote (the ledger at `SHA` vs `SHA^`), so older unstamped placeholders stay untouched.
2. Exit `1` ("nothing to stamp") means PR N left no placeholders; report that and stop, with no branch to ship.
   Exit `2` is an error (unknown SHA, unreadable ledger, a field it could not locate); do not hand-edit around it.
3. Check the diff holds only the stamps: `git diff --numstat -- .agents/deferred-items.json` must read `K K`,
   where K is the field count the script printed.
4. Validate (below), then commit and open the PR with `piv-commit` and `piv-create-pr`, staging only
   `.agents/deferred-items.json`. Title it `chore: stamp PR #N merge SHA into deferred-items ledger`.

## Validate (after every write)

```bash
python3 -m json.tool .agents/deferred-items.json >/dev/null
pre-commit run check-json --files .agents/deferred-items.json
git diff -- .agents/deferred-items.json
```

- **Add / Close:** the diff shows `"pending"` on each new `introduced_commit` / `closed_commit`, and no SHA.
- **Stamp:** this must print nothing:
  `git diff -- .agents/deferred-items.json | grep -E '^\+.*"(introduced|closed)_commit": "pending'`.
  A bare `grep pending` is useless here: prose fields (`title`, `summary`, `notes`) contain the word too.

## Gotchas

- Both placeholder spellings exist on `main`: `"pending"` and `"pending commit"`. Write `"pending"`; the script
  matches both.
- Stamp with the short SHA: 8 characters is the ledger's convention (observed on `main`: 8 characters in 39 of
  42 non-placeholder `introduced_commit` values). The script shortens `gh`'s full oid to 8 by default.
- Do not rewrite the file with `json.dump`: its default `ensure_ascii=True` escapes every raw `—`, and past
  revisions mixed raw and `\u`-escaped text, so a round trip churns unrelated lines. Edit the entries in place
  (the script edits line by line and checks the parsed result before writing).
- `end-of-file-fixer` also runs on this file: keep the single trailing newline.

## Resources

- `scripts/stamp_ledger.py`: stamps PR N's placeholders with its squash SHA. Run it, don't read it:
  `--sha <sha> [--dry-run] [--file PATH] [--length 8]`; exit 0 stamped, 1 nothing to stamp, 2 error.
- `.claude/rules/deferred-items.md`: the schema and the add / retire rules (authority).
- `.claude/commands/preflight-check.md` Step 2: consulting the ledger before a plan (not this skill).
