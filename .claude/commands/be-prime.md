# Backend Prime — Load Full Backend Context

Assumes MCP indexes are ready (run `/session-init` if not).

## Step 1: Discover Structure (jCodeMunch — zero file reads)

Using jCodeMunch (repo from `list_repos`):
1. `get_file_tree({ "path_prefix": "app/" })` — map all backend features
2. `get_file_outline` on `app/core/config.py`, `app/core/exceptions.py`, `app/shared/schemas.py`, `app/shared/models.py` — understand patterns without reading full files
3. `search_symbols({ "query": "AppError", "kind": "class" })` — discover error hierarchy
4. `search_symbols({ "query": "get_current_user", "kind": "function" })` — find auth pattern
5. `search_symbols({ "query": "router", "kind": "variable", "file_pattern": "*/routes.py" })` — list all route modules

## Step 2: Load Core Patterns (targeted reads only)

Only read files you'll need as reference for implementation:
1. Read `/app/core/config.py` — configuration structure
2. Read `/app/core/database.py` — database patterns
3. Read `/app/core/exceptions.py` — error hierarchy

Use jCodeMunch `get_symbol` for anything else — don't read full files just for reference.

## Step 3: Load Documentation (jDocMunch — section reads only)

Using jDocMunch (repo: `local/email-hub`):
1. `search_sections({ "query": "project overview", "doc_path": "CLAUDE.md", "max_results": 3 })` → `get_section` on matches
2. `search_sections({ "query": "development guidelines", "doc_path": "CLAUDE.md", "max_results": 3 })` → `get_section` on matches
3. `search_sections({ "query": "architecture", "doc_path": "CLAUDE.md", "max_results": 3 })` → `get_section` on matches

For TODO.md — search only for backend-relevant phases:
4. `search_sections({ "query": "upcoming phases", "doc_path": "TODO.md", "max_results": 5 })` → `get_section` on relevant matches

## Step 4: Assess Current State

Use jCodeMunch to verify what's implemented:
1. `search_symbols({ "query": "router", "file_pattern": "*/routes.py" })` — count API modules
2. `get_file_tree({ "path_prefix": "alembic/versions" })` — count migrations
3. `get_file_tree({ "path_prefix": "app/ai/agents" })` — check agent coverage

Summarize: modules implemented, API coverage, test coverage, and readiness for backend work.
