# Frontend Planning — Create Implementation Plan

Research the codebase and create a self-contained frontend implementation plan.

## Process

1. **Understand the task** — Read the user's requirements carefully
2. **Check memory** — Read relevant memory files for domain patterns, past feedback, and conventions before writing any code or plans.

3. **Research existing code** — Read files you will modify AND discover related data assets.

   **jCodeMunch** (repo from `list_repos`):
   - `search_symbols(query, kind, file_pattern)` — find related components/hooks
   - `get_file_outline(file_path)` — understand exports without reading
   - `get_symbol(symbol_name)` — read specific component/function code
   - `find_references(symbol_name)` — trace where components/hooks are used
   - `get_file_tree(path_prefix)` — discover layout (e.g. `cms/apps/web/src/...`)

   **jDocMunch** (repo: `local/email-hub`):
   - `search_sections(query, doc_path)` → `get_section(section_id)` for CLAUDE.md architecture context and TODO.md task context
   - `get_document_outline(doc_path)` for smaller docs (<50 sections) when you need full structure

4. **Discover existing data assets** — Before writing test fixtures, mock data, or example code, check what already exists:
   - `app/ai/templates/library/*.html` — 15 golden email templates (real production HTML)
   - `app/components/data/seeds.py` — 21 seeded components (`COMPONENT_SEEDS`) with production HTML
   - `cms/apps/web/src/types/` — existing TypeScript types and interfaces
   - Existing test files in the feature area — reuse patterns, factories, fixtures
   - **Read actual data** to verify structure and counts — never assume

5. **Identify files to create/modify** — List every file that needs changes
6. **Write the plan** — Step-by-step instructions that another agent can follow. All code examples must follow patterns found in existing codebase

## Plan Format

Save the plan to `.agents/plans/{feature-name}.md` with this structure:

```markdown
# Plan: {Feature Name}

## Context
{Why this change is needed}

## Files to Create/Modify
- `cms/apps/web/src/app/(dashboard)/{route}/page.tsx` — {what changes}
- `cms/apps/web/src/hooks/use-{domain}.ts` — {what changes}
- ...

## Implementation Steps
1. {Step with exact code or clear instructions}
2. ...

## Security Checklist
For files in this plan only:
- [ ] No `(x as any)` type casts — use proper type augmentation
- [ ] API calls use `authFetch` (never raw `fetch` for authenticated endpoints)
- [ ] No `dangerouslySetInnerHTML` without DOMPurify sanitization
- [ ] Token handling uses JWT `exp` claim (not hardcoded expiry)
- [ ] SessionStorage/localStorage data validated with runtime type guards before use
- [ ] Preview iframes use `sandbox` attribute
Full codebase security sweep is `/fe-validate`.

## Verification
- [ ] `make check-fe` passes (ESLint + Prettier + TypeScript + tests)
- [ ] No ESLint errors (`pnpm --filter web lint`)
- [ ] No TypeScript errors
- [ ] Semantic Tailwind tokens only (no primitive colors)
- [ ] Auth/RBAC works correctly
- [ ] No `as any` casts in changed files
```

## Rules
- Use semantic Tailwind tokens — NEVER primitive colors (`text-gray-500`, `bg-blue-600`)
- Use `authFetch` for API calls, SWR hooks for data fetching
- React 19: No setState in useEffect, no component defs inside components
- Dialog for detail views (not Sheet). Widths: detail=28rem, forms=32rem
- Named container sizes collapse in Tailwind v4 — use explicit rem values
- Route protection via middleware.ts ROLE_PERMISSIONS map
- Preview iframes must use sandbox attribute (no allow-scripts)

@_shared/tailwind-token-map.md
@_shared/frontend-security.md
