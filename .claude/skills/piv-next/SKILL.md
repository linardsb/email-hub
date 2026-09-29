---
name: piv-next
description: Read the open epics' task lists back from GitHub and say which epic ticket is unblocked next, and which loose open tickets should fold into an epic ticket instead of being worked on their own. Read-only. Use at session start, before picking a ticket, or when the backlog feels like it grows faster than the epic moves.
argument-hint: "(no arguments)"
---

# /piv-next — what the epic says is next

`piv-slice-epic` writes the epic's task list; nothing read it back, so the loop picked whatever ticket was open and
smallest. This reads it back.

Run:

```bash
bash .claude/skills/piv-next/next.sh
```

It prints, per open epic, each task-list row as **UNBLOCKED** (every `depends on` ticket is closed) or **blocked**
(with the open dependencies named), then every open ticket that has no epic row, with the open epic ticket its own
body names as the place to fold it.

## Reading the output

- **Next work is the lowest-numbered UNBLOCKED row in the oldest epic.** State it in one line and start there.
- **A loose ticket with a fold target is a checklist line, not a slice.** Append it to that epic ticket's body
  (`gh issue edit <n> --body-file`) and close it with a comment naming where it went. `piv-fix-review-findings` §1
  already routes new deferrals this way; this catches the ones filed before that rule.
- **A loose ticket with no fold target** is either a real reader-visible bug (work it) or process upkeep (park it
  until the epic has no unblocked row). Say which, don't guess.

The script writes nothing. Every decision above is the owner's; the skill only makes the queue visible.
