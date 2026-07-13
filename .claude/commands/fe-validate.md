# Frontend Validate — Run All Frontend Quality Checks

## Level 1: Lint + Format
```bash
cd cms && pnpm --filter web lint
cd cms && pnpm --filter web format:check
```
ESLint (security, a11y, React hooks, import hygiene) + Prettier (formatting, Tailwind class sorting).
If lint fails, auto-fix with `cd cms && pnpm --filter web lint:fix && pnpm --filter web format`.

## Level 2: TypeScript
```bash
cd cms && pnpm --filter @email-hub/web exec tsc --noEmit
```

## Level 3: Build
```bash
cd cms && pnpm build
```
This runs turbo build across all packages (SDK + web). Catches TypeScript errors, import issues, and SSR problems.

## Level 4: Design System (via jCodeMunch — no full grep scans)

Use jCodeMunch to find design system violations efficiently:
1. `search_text({ "query": "text-gray-", "file_pattern": "*.tsx" })` — primitive color usage
2. `search_text({ "query": "bg-blue-", "file_pattern": "*.tsx" })` — primitive color usage
3. `search_text({ "query": "bg-slate-", "file_pattern": "*.tsx" })` — primitive color usage
4. `search_text({ "query": "border-zinc-", "file_pattern": "*.tsx" })` — primitive color usage

Should use semantic tokens (`text-foreground`, `bg-card`, `border-border`, etc.)

Fallback: Grep for `(text|bg|border|ring)-(gray|slate|zinc|red|blue|green)-\d` in `cms/apps/web/src/**/*.tsx`

## Level 5: Security

Use jCodeMunch to locate violations without reading full files:
1. `search_text({ "query": "as any", "file_pattern": "*.ts" })` — flag new instances (currently 0 in codebase — this is a guard rail)
2. `search_text({ "query": "dangerouslySetInnerHTML", "file_pattern": "*.tsx" })` — only flag if DOMPurify is NOT used alongside it
3. `search_text({ "query": "fetch(", "file_pattern": "*.tsx" })` — verify client components use `authFetch`. **Exclude** these files (legitimate raw fetch): `app/api/` (server route handlers), `lib/auth-fetch.ts` (wrapper itself), `lib/sdk.ts` (SDK internals)
4. `find_references({ "symbol_name": "sessionStorage" })` — verify runtime type validation
5. `find_references({ "symbol_name": "localStorage" })` — verify runtime type validation

Only `Read` files when you need to fix a violation found above.

## Level 6: Unit Tests
```bash
cd cms && pnpm --filter web test
```
Vitest runs the frontend unit suite. CI runs this via `make check-fe`; skipping it locally is the single biggest source of red builds.

## Level 7: CI Parity Gates (conditional on diff scope)

CI runs `make check-fe`, which bundles Levels 1, 2, 6 plus a polling-literal scan. Run only the gates whose trigger files appear in the diff:

| Gate | Command | Run when diff touches |
|------|---------|------------------------|
| Polling literals | `make lint-polling` | `cms/apps/web/src/hooks/**` (any file adding/changing SWR refresh intervals) |
| OpenAPI SDK drift | `cd cms && pnpm --filter web exec openapi-ts-check` *(if present)* | `app/**/routes.py` or `app/**/schemas/**.py` (backend route/schema changes that should regenerate the SDK) |
| Tailwind class sort | `cd cms && pnpm --filter web format:check` | already covered by Level 1 — re-mention if formatter was bypassed |
| `.env.example` drift | `make check-env-drift` | only if frontend change pulled in a backend `Settings` field |

If unsure or the diff spans many areas, run **`make check-fe`** (≈60s) — it bundles every frontend gate above plus Levels 1–2, 6 in one shot and matches CI exactly. For mixed backend+frontend changes, `make check` (or `make ci`) covers both sides.

When a CI gate fails on push, the fix is almost always a regenerated artifact (SDK regen via `cd cms && pnpm --filter web codegen`, snapshot regen, etc.) — note which gate failed and add the regenerate step to the same commit, never as a separate "fix CI" follow-up.

## Notes
- ESLint config: `cms/apps/web/eslint.config.mjs` — Prettier config: `cms/.prettierrc.json`
- Report results for each level. Do NOT auto-fix convention violations — use `/fe-code-review-fix` for targeted fixes
