# Frontend Parallel Plan — Concurrent Research + Planning

Replaces the sequential `/fe-prime` → `/fe-planning` flow with parallel agent execution.
Three agents run simultaneously, then results merge into a single implementation plan.

## Input

The user provides:
- **Feature description** — what to build
- **Plan filename** — where to save (default: `.agents/plans/{feature-slug}.md`)

## Execution

Launch **three agents in parallel** using the Agent tool:

### Agent 1: Researcher (subagent_type: Explore)
```
Research the frontend codebase for implementing: {feature description}

Using jCodeMunch (repo from list_repos):
1. get_file_tree({ "path_prefix": "cms/apps/web/src/app" }) — map all routes/pages
2. get_file_tree({ "path_prefix": "cms/apps/web/src/components" }) — map component tree
3. search_symbols for components/hooks related to: {feature keywords}
4. get_file_outline on the most relevant files found
5. find_references for key components/hooks that will need modification
6. get_file_outline on cms/apps/web/src/app/layout.tsx, cms/apps/web/auth.ts, cms/apps/web/src/lib/auth-fetch.ts

Using jDocMunch (repo: local/email-hub):
1. search_sections({ "query": "{feature keywords}", "doc_path": "CLAUDE.md" }) — architecture context
2. search_sections({ "query": "frontend", "doc_path": "CLAUDE.md" }) — frontend conventions
3. search_sections({ "query": "{feature keywords}", "doc_path": "TODO.md" }) — task context

Write a structured research summary including:
- Relevant files and their roles
- Key components/hooks to modify or extend
- Existing patterns to follow (authFetch, SWR hooks, Dialog vs Sheet)
- Tailwind token conventions observed
- Dependencies and imports needed
```

### Agent 2: Test Scout (subagent_type: Explore)
```
Find all test files and patterns related to: {feature description}

1. Glob for test files in related directories: cms/apps/web/src/**/__tests__/*.test.{ts,tsx}
2. Read test setup files for existing fixtures and render helpers
3. Search for test patterns using Grep:
   - Existing mock patterns (mockReturnValue, mockResolvedValue)
   - Render helpers and test utilities
   - MSW handlers if API mocking is used
4. Check cms/apps/web/src/types/ for existing TypeScript types relevant to this feature
5. Check for existing Storybook stories in the component area

Write a structured summary including:
- Related test files found
- Existing test utilities and helpers available
- Mock patterns used in this area
- TypeScript types that can be reused
- Test conventions specific to this feature area
```

### Agent 3: TypeScript Baseline (subagent_type: general-purpose)
```
Run TypeScript baseline on the frontend:

1. Run: cd cms && pnpm --filter web tsc --noEmit 2>&1 | tail -20
2. Count current errors
3. Also run: cd cms && pnpm --filter web lint 2>&1 | tail -20
4. Report the baseline error counts
```

## After All Agents Complete

Combine all three agent results and write the implementation plan following the `/fe-planning` format:

```markdown
# Plan: {Feature Name}

## Context
{Why this change is needed — from user's feature description}

## Research Summary
{From Agent 1 — relevant files, patterns, dependencies}

## Test Landscape
{From Agent 2 — existing tests, fixtures, mock patterns}

## Type Check Baseline
{From Agent 3 — current tsc/eslint error counts}

## Files to Create/Modify
- `cms/apps/web/src/...` — {what changes}

## Implementation Steps
1. {Step with exact code or clear instructions}
2. ...

## Preflight Warnings
{Any hardcoded assertions, snapshot tests, or fragile patterns found by Agent 2 in existing tests}

## Security Checklist
- [ ] No `(x as any)` casts
- [ ] API calls use `authFetch`
- [ ] No `dangerouslySetInnerHTML` without DOMPurify
- [ ] Preview iframes use `sandbox` attribute

## Verification
- [ ] `make check-fe` passes
- [ ] No ESLint errors
- [ ] No TypeScript errors
- [ ] Semantic Tailwind tokens only
- [ ] TypeScript errors ≤ baseline ({N} errors before)
```

Save to `.agents/plans/{feature-slug}.md`.

## Rules

- All three agents MUST run in parallel — do not wait for one before starting another
- The plan file must not exceed 700 lines (use compact descriptions, tables, `file:line` refs)
- Use semantic Tailwind tokens — NEVER primitive colors
- Use `authFetch` for API calls, SWR hooks for data fetching
- React 19: No setState in useEffect, no component defs inside components
- Follow all conventions from @_shared/frontend-security.md

@_shared/tailwind-token-map.md
@_shared/frontend-security.md
