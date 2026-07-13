# Update Documentation

Synchronise all project documentation to reflect the current implementation state. Update these files in order:

## 1. Read Current State

### 1a. Documentation (via jDocMunch — section-level reads, no full-file scans)

Use jDocMunch (repo: `local/email-hub`) to read only the sections that matter.

**TODO.md** — search for relevant phases:
- `search_sections({ "query": "upcoming phases", "max_results": 5 })` → `get_section` on matches
- `search_sections({ "query": "completed", "doc_path": "TODO.md", "max_results": 5 })` → `get_section` on matches

**CLAUDE.md** — only the roadmap/architecture sections:
- `search_sections({ "query": "roadmap", "doc_path": "CLAUDE.md" })` → `get_section`
- `search_sections({ "query": "architecture", "doc_path": "CLAUDE.md" })` → `get_section`

**PRD.md** — only Section 0 (Implementation Status):
- `search_sections({ "query": "implementation status", "doc_path": "PRD.md", "max_results": 3 })` → `get_section`
- Do NOT read sections 1-12 (requirements — never modified by this command)

### 1b. Codebase Evidence (via jCodeMunch — no file reads)

Use jCodeMunch (repo from `list_repos`) to scan for implementation evidence:
- `get_file_tree({ "path_prefix": "cms/apps/web/src/hooks" })` — frontend hooks
- `get_file_tree({ "path_prefix": "cms/apps/web/src/app" })` — dashboard/route pages
- `search_symbols({ "query": "router", "kind": "variable", "file_pattern": "*/routes.py" })` — backend API coverage
- `get_file_tree({ "path_prefix": "alembic/versions" })` — migration files
- `get_file_tree({ "path_prefix": "app/" })` — backend feature modules

### 1c. Fallback

If jDocMunch/jCodeMunch indexes are stale or unavailable, fall back to direct `Read` + `Glob`.

## 2. Update TODO.md

- Mark any newly completed tasks with `~~strikethrough~~` and `DONE` suffix
- Ensure completion markers match actual implementation (don't mark incomplete work as done)
- Keep security requirements and verification criteria intact

## 3. Update CLAUDE.md

- Sync the `Implementation Roadmap` checklist with TODO.md completion state
- Update `[x]` / `[ ]` markers to match
- If new modules, commands, or patterns were introduced, add them to the relevant architecture sections
- Keep compact — CLAUDE.md is loaded into every conversation context

## 4. Update PRD.md

- Update the `Implementation Status` section (Section 0):
  - Move newly completed tasks to the "Completed" table with key deliverables
  - Update "In Progress" to reflect current sprint focus
  - Update "Infrastructure Built" if new cross-cutting capabilities were added
- Bump version number if significant changes
- Update the date to today

## 5. Verify Consistency

Cross-check that all three docs agree on:
- Which tasks are complete vs in-progress
- Phase numbering and task descriptions
- Architecture descriptions match actual code structure

## 6. Report Changes

Summarise what was updated in each file. If nothing changed, say so — don't make changes for the sake of it.

## Rules

- Do NOT add features or tasks that don't exist in the codebase
- Do NOT remove security requirements or verification criteria from TODO.md
- Do NOT expand CLAUDE.md beyond what's needed (it's context-window-sensitive)
- Do NOT modify the PRD requirements sections (1-12) — only update Section 0 (Implementation Status)
- Keep all changes factual and verifiable against the codebase
