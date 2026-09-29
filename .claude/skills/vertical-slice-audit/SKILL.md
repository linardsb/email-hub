---
name: vertical-slice-audit
description: Audit a feature folder against the 10-row Vertical Slice Architecture checklist, score and classify it, and produce a migration playbook if it scores below 9/10. Use when checking whether a feature or module's code organization fits the vertical-slice pattern.
argument-hint: "[feature_path]"
---

# Vertical Slice Audit — Score a Feature, Produce a Migration Plan

You are auditing a single feature/folder for adherence to Vertical Slice Architecture (VSA). VSA is the codebase-level optimization that lets a coding agent load one slice end-to-end and ship — instead of chasing cross-folder context across layered architecture.

**Target path**: `$ARGUMENTS` (the feature folder to audit). If `$ARGUMENTS` is empty, ask the user which feature to audit before proceeding.

## What you will do

1. Read the target folder at `$ARGUMENTS`
2. Walk the 10-row checklist below, scoring each row
3. Classify the slice based on the total score
4. If the slice fails (score < 9/10), produce a step-by-step migration plan
5. Report results to the user

---

## The 10-row checklist

For the feature at `$ARGUMENTS`, score each row PASS or FAIL:

| # | Check | PASS | FAIL |
|---|---|---|---|
| 1 | Feature has its own folder | All its code lives under one top-level folder | Code is spread across `controllers/`, `services/`, `models/`, `repositories/` |
| 2 | Models are local to the feature | `<feature>/models.{py,ts}` exists | Models live in a top-level `models/` folder shared with other features |
| 3 | Schemas are local to the feature | `<feature>/schemas.{py,ts}` exists | Schemas live in a top-level `schemas/` folder |
| 4 | Routes are local to the feature | `<feature>/routes.{py,ts}` (or routes registered from here) | Routes live in a top-level `routes/` or `controllers/` folder |
| 5 | Business logic is local | `<feature>/service.{py,ts}` exists and contains the substance | Logic is spread across helpers, utils, lib folders |
| 6 | Errors are local | `<feature>/errors.py` or `<feature>/exceptions.py` (email-hub: `AppError` subclasses, `app/core/exceptions.py:16`) defines feature-specific exceptions | All errors are generic `HTTPException` or shared `errors.py` |
| 7 | Tests are colocated | `<feature>/tests/` exists next to the source | Tests live in a top-level `tests/` folder mirroring the source tree |
| 8 | Public API is explicit | Feature has an `index.{py,ts}` (or `__init__.py`) that controls exports | Anything can be imported from anywhere inside the feature |
| 9 | Internal helpers stay internal | Private functions / classes are not exposed via the public API | Everything is exported (or there is no public API) |
| 10 | Cross-feature dependencies are minimal | Feature imports from `<3 other features (excluding shared utils) | Feature imports from many other features; ripple effects on change |

For each row: cite the actual file path that justifies the PASS or FAIL.

---

## Scoring tiers

- **9-10 PASS** → AI-friendly. This slice is the reference shape. Recommend other features in the codebase be migrated toward it.
- **6-8 PASS** → Partially migrated. Usually missing colocated tests, explicit public API, or local errors. Quick wins available — see migration plan below.
- **≤5 PASS** → Horizontally organized. Migration is meaningful but not catastrophic. Most of the work is moving files, not rewriting.

---

## Why each check matters (cite this when explaining results)

| Check | Why agents care |
|---|---|
| 1. Own folder | One `cd` or one `Read` round-trip loads everything. Agent context stays clean. |
| 2-5. Local code | A focused prime command can load the whole slice in one prompt — agent has the full picture without exploration. |
| 6. Local errors | When the agent sees an error, it's near the code that raises it. Faster reasoning, fewer cross-references. |
| 7. Colocated tests | When the agent modifies the feature, it sees the tests immediately — no separate exploration step. Closes the validation loop fast. |
| 8-9. Explicit public API | The agent knows what's importable and what's internal. Prevents leaky abstractions. |
| 10. Low cross-feature coupling | Changes don't ripple. Agent can plan + implement + validate inside the slice with high confidence. |

---

## Migration plan (only produce this if score < 9/10)

If the slice fails the audit, produce a migration plan tailored to this codebase. Use this structure:

```markdown
# VSA Migration Plan — <feature-path>

## Current state
- Score: X/10
- Tier: <AI-friendly / Partially migrated / Horizontally organized>
- Failed rows: <list row numbers + one-line summary>

## Step-by-step migration

### Step 1 — Create the slice folder
<bash commands to mkdir + touch the files this feature is missing>

### Step 2 — Move code into the slice, one layer at a time
Order (least risky → most risky):
1. Models — usually move cleanly; just update imports.
2. Schemas / validation — same.
3. Errors — define feature-local exception classes; replace generic exceptions.
4. Service — move business logic in. May require splitting if old code mixed business logic with HTTP plumbing.
5. Routes — move handlers in; register them from the slice instead of from a top-level routes file.
6. Tests — move tests last. They validate the migration didn't break anything.

After each step, run the codebase's validation (`make check`) and commit. If something breaks, the bisect is trivial.

### Step 3 — Define the public API
Edit `<feature>/__init__.py` to export only what the rest of the system needs. Internal helpers stay internal.

### Step 4 — Update imports across the codebase
Find every import that referenced the old paths. Update to import from the new public API. This is the "blast radius" step — it's mechanical but you need to be thorough.

### Step 5 — Update the AI Layer
Edit `CLAUDE.md` to reference the new slice as the canonical shape. If the feature has non-obvious conventions, write a per-feature `<feature>/CLAUDE.md`.

## Estimated effort
- Lines moved: ~<count from the audit>
- Files touched: ~<count>
- Risk: <Low / Medium / High based on cross-feature dependencies>

## What NOT to migrate
- Truly cross-cutting concerns (auth middleware, logging, request correlation) — stay shared.
- Database connections / session management — stay shared.
- The HTTP framework setup itself — stays shared.
- Utility libraries with no business domain (date helpers, string utils) — stay in `shared/` or `core/`.
- Cross-cutting infrastructure and shared primitives (config, database, logging, `AppError`, shared models/schemas/utils) — those live in `app/core` and `app/shared`; a slice importing from `app/core` or `app/shared` does not count against row 10.
```

---

## Output format

Return the audit result to the user in this format:

```markdown
# VSA Audit Result — <feature-path>

## Score: X/10 — <tier name>

## Checklist results

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Own folder | PASS / FAIL | `<file path or 'no such folder'>` |
| 2 | Models local | PASS / FAIL | ... |
| ... | ... | ... | ... |

## Verdict
<one-paragraph: what's working, what's not>

## Migration plan
<only if score < 9/10 — embed the plan from above>

## Recommended next steps
<2-3 concrete actions>
```

---

## Critical principles

1. **Score honestly.** A PASS means the file/convention actually exists, not that it could exist.
2. **Cite real paths.** Every row's evidence column should reference a file or note its absence.
3. **Don't editorialize.** Describe the codebase as it stands. The score tells the user where they stand; the migration plan tells them what to do next.
4. **Coupling beats LOC.** A 2,000-line `service.py` is fine if it's cohesive. A 200-line file pulling from 14 other features fails row 10.
5. **Migration is incremental.** The migration plan should never recommend "refactor everything." Start with the next greenfield slice; let brownfield decay around it.

---

## Telling the user when to migrate

When you propose VSA migration, the framing that lands:

> *"Layered architecture was great when humans were the only readers. Agents read code differently — they load context for one feature at a time, and they pay a token cost for every folder hop. Reorganizing by feature instead of by layer cuts that cost dramatically. We don't need to refactor everything; we start with the next greenfield slice and let the rest migrate as we touch it."*

Avoid: "this is the best architecture." Architecture is contextual. The honest framing is "this is better for AI-coding throughput, and the migration is incremental, and here's the reference slice to point at."

---

## What this skill does NOT do

- Refactor code on its own. The skill produces a plan; execution is a separate session.
- Audit the entire codebase at once. Audit one feature at a time. To audit multiple, invoke the skill once per feature.
- Score architecture other than VSA. If the codebase uses a different organizational pattern (hexagonal, clean architecture, etc.) by design, this skill's checks may not be the right metric.
