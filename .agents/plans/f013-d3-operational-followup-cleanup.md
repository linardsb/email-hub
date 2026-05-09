# F013-D3 — Operational Follow-Up Cleanup (DONE-already)

**Cluster:** F (bookkeeping; no code work).
**Closes:** the `Operational follow-ups` block in `TODO.md` and the matching
ledger entry — both reference the 2026-05-11 readiness check that has already
been satisfied.
**Branch:** any branch that touches `TODO.md` (typically the next PR — fold
this in rather than spinning a session).
**Estimated effort:** 5 min.

## Why this exists

The 2026-05-11 readiness check in `TODO.md` says:

> If the count is **zero**, proceed to D3 and delete the shims.

`d9132c7c` (commit dated 2026-05-08) already retired the legacy shims:
`grep -rn "convert\b|convert_mjml|_convert_recursive" app/design_sync/` returns
only the new `convert_document` / `convert_document_mjml` symbols. The shims
are gone and no telemetry hits exist (`grep -c "design_sync.converter.shim_called"
traces/*.jsonl` returns 0 across all trace files as of today).

So the operational follow-up is **stale**. It survives because the entry was
written before D3 shipped early.

## Files

| File | Change |
|---|---|
| `TODO.md` | Remove or strike the `Operational follow-ups` section dated `2026-05-11 — F013 D3 readiness check`. Replace with a one-line closing note pointing at `d9132c7c`. |
| `docs/TODO-completed.md` | If F013-D3 isn't already logged, add a one-line entry under the relevant phase note. |
| `.agents/plans/tech-debt-08-converter-god-functions-followup.md` | Mark Part D3 done in the "Done When" checklist (the plan body still says "Part D3 stays unchecked — calendar-blocked by D2's 14-day window"; that line is now historical). |
| `.agents/deferred-items.json` | If a `tooling_followups[]` entry tracks the readiness check, mark it `closed: 2026-05-08` with `closed_commit: "d9132c7c"`. (Verified: the existing `tooling_followups[]` is for a different concern; no edit needed unless one was added later.) |

## Steps

### 1. Confirm shim deletion

```bash
rg -n "design_sync.converter.shim_called" app/ services/ traces/
# → no hits
git log --oneline --all --grep="F013\|shim" | head -5
# → expect d9132c7c "retire legacy converter shims" + 8b996b4c "instrument..."
rg -n "^def convert\b|^    def convert\b|def convert_mjml|def _convert_recursive" \
   app/design_sync/converter*.py
# → only convert_document / convert_document_mjml should remain
```

If any of those checks surface unexpected hits, **stop** — the cleanup
assumption is wrong and the actual shim state needs investigation. Otherwise
proceed.

### 2. Edit `TODO.md`

Locate the `Operational follow-ups` block (search for
`2026-05-11 — F013 D3 readiness check`). Replace the multi-line block with:

```markdown
## Operational follow-ups

> **2026-05-08 — F013 D3 closed early.** Telemetry was at zero; legacy shims
> deleted in commit `d9132c7c` (3 days ahead of the 14-day window).
> See `.agents/plans/tech-debt-08-converter-god-functions-followup.md` Part D3.
```

(Keep the section header so future operational items have a home.)

### 3. Edit the followup plan

`.agents/plans/tech-debt-08-converter-god-functions-followup.md` — find the
"Done When" checklist (or end-of-Part-D section). Mark D3 done. If the body
still says "Part D3 stays unchecked — calendar-blocked by D2's 14-day window"
(seen in `d9132c7c`'s commit message but the file body may have been updated
in the same commit), leave that historical comment alone — it's accurate at
commit time.

### 4. PR checklist

- [ ] No new code changes.
- [ ] `make check-full` green (it would be regardless; this is doc-only).
- [ ] `.agents/plans/deferred-items-tracker.md` — strike Cluster F (the row
      already references `d9132c7c`).
- [ ] If folding into another PR (e.g. Cluster A's PR also touches `TODO.md`),
      mention this cleanup in the PR description.

## Risk

None — doc-only edits. The only failure mode is the §1 verification surfacing
that the shims aren't actually gone, in which case this plan doesn't apply and
the original 2026-05-11 readiness check stands.
