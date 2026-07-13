# Frontend Prime — Load Full Frontend Context

Assumes MCP indexes are ready (run `/session-init` if not).

## Step 1: Discover Structure (jCodeMunch — zero file reads)

Using jCodeMunch (repo from `list_repos`):
1. `get_file_tree({ "path_prefix": "cms/apps/web/src/app" })` — map all routes/pages
2. `get_file_tree({ "path_prefix": "cms/apps/web/src/components" })` — map component tree
3. `get_file_tree({ "path_prefix": "cms/apps/web/src/hooks" })` — list all hooks
4. `get_file_outline` on `cms/apps/web/src/app/layout.tsx`, `cms/apps/web/auth.ts`, `cms/apps/web/src/lib/auth-fetch.ts` — understand patterns without reading full files
5. `search_symbols({ "query": "authFetch", "kind": "function" })` — find API fetch pattern

## Step 2: Load Core Patterns (targeted reads only)

Only read files you'll need as reference for implementation:
1. Read `/cms/apps/web/src/app/layout.tsx` — provider hierarchy
2. Read `/cms/apps/web/auth.ts` — authentication setup
3. Read `/cms/apps/web/src/lib/auth-fetch.ts` — API fetching patterns

Use jCodeMunch `get_symbol` for anything else — don't read full files just for reference.

## Step 3: Load Documentation (jDocMunch — section reads only)

Using jDocMunch (repo: `local/email-hub`):
1. `search_sections({ "query": "project overview", "doc_path": "CLAUDE.md", "max_results": 3 })` → `get_section` on matches
2. `search_sections({ "query": "frontend", "doc_path": "CLAUDE.md", "max_results": 3 })` → `get_section` on matches
3. `search_sections({ "query": "architecture", "doc_path": "CLAUDE.md", "max_results": 3 })` → `get_section` on matches

For TODO.md — search only for frontend-relevant phases:
4. `search_sections({ "query": "upcoming phases", "doc_path": "TODO.md", "max_results": 5 })` → `get_section` on relevant matches

## Step 4: Assess Current State

Use jCodeMunch to verify what's implemented:
1. `get_file_tree({ "path_prefix": "cms/apps/web/src/app/(dashboard)" })` — count dashboard pages
2. `search_symbols({ "query": "use", "kind": "function", "file_pattern": "*/hooks/*.ts" })` — count custom hooks
3. `get_file_tree({ "path_prefix": "cms/apps/web/src/components" })` — check component coverage

Summarize: pages implemented, component coverage, hook count, and readiness for frontend work.
