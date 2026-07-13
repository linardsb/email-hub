# Frontend Code Review Fix — Diagnose and Fix Issues

Find, diagnose, and fix frontend bugs, code review findings, or quality issues.

## Trigger

Use when: bug report, failing test, code review comment, type error, UI regression, broken layout, or any issue that needs fixing rather than new feature development.

## Process

### 1. Understand the Issue

Read the user's description. Classify:
- **Bug**: unexpected behaviour, runtime error, wrong render, broken interaction
- **Code review finding**: style, architecture, security, performance, accessibility issue
- **Test failure**: failing Vitest test that needs code or test fix
- **Type error**: TypeScript compilation error
- **Design system violation**: primitive colors, wrong tokens

### 2. Reproduce / Locate

**jCodeMunch** (repo from `list_repos`) for cross-file tracing:
- `search_symbols(query, kind)` — find related components/hooks
- `find_references(symbol_name)` — trace where a component or hook is used
- `get_file_outline(file_path)` — understand file structure before deciding what to read
- `get_symbol(symbol_name)` — read just the specific component/function you need

Only `Read` the full file when you need to edit it.

**Direct diagnosis:**
- For bugs: find the component or page. Trace page → components → hooks → types.
- For test failures: run `cd cms && pnpm --filter web test` and read output.
- For type errors: run `cd cms && pnpm --filter @email-hub/web exec tsc --noEmit`.
- For design issues: grep for primitive Tailwind colors.

### 3. Root Cause Analysis

- Trace the issue to its root cause — don't patch symptoms.
- Check if the same pattern exists elsewhere (grep for similar code).
- Identify the minimal set of files that need changes.

### 4. Fix

Apply the fix following project conventions. Don't over-engineer — fix the issue, nothing more.

@_shared/tailwind-token-map.md
@_shared/frontend-security.md

**Key rules:**
- Use semantic Tailwind tokens — NEVER primitive colors (`text-gray-500`, `bg-blue-600`)
- Use `authFetch` for API calls in client components, SWR hooks for data fetching
- React 19: No setState in useEffect, no component defs inside components
- Dialog for detail views (not Sheet). Widths: detail=28rem, forms=32rem

### 5. Verify

Run the validation pyramid on affected code:

```bash
# Lint + format (ESLint: security, a11y, React hooks + Prettier with Tailwind class sorting)
cd cms && pnpm --filter web lint:fix
cd cms && pnpm --filter web format

# Type check
cd cms && pnpm --filter @email-hub/web exec tsc --noEmit

# Unit tests
cd cms && pnpm --filter web test

# Build (catches SSR issues, import errors)
cd cms && pnpm build
```

Then grep for design system violations in changed files:
- Primitive colors: `(text|bg|border|ring)-(gray|slate|zinc|red|blue|green|...)-\d`

Fix any issues introduced by the change. Repeat until all checks pass.

### 6. Report

Summarise:
- **Root cause**: what was wrong and why
- **Fix**: what was changed and in which files
- **Verification**: which checks passed
- **Risk**: any side effects or areas to watch

## Rules

- Fix the root cause, not the symptom
- Don't refactor unrelated code while fixing a bug
- Don't add features — only fix the reported issue
- If the fix requires architectural changes, flag it and suggest `/fe-planning` instead
- Run verification on every file you touch — never skip type checks
