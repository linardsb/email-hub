# Figma Rate Limits & API Budget

Figma's REST API has aggressive rate limits on free/starter plans. This document covers how the Hub minimizes API calls and what to do when rate-limited.

## Figma Rate Limit Behaviour

| Plan | Limit | Retry-After | Scope |
|------|-------|-------------|-------|
| Starter/Free | Very low (~3-5 calls/min) | Up to 4+ days | Per Figma **account** (not IP, not token) |
| Professional | Higher | Minutes to hours | Per account |

- Rate limits are **per Figma account**, not per IP or per token
- Generating a new PAT or switching networks does **not** reset the limit
- The only workaround is using a different Figma account or waiting

## API Calls Per Hub Action

| Hub Action | Figma API Calls | Endpoint(s) |
|------------|----------------|-------------|
| Connect (Browse Files) | 1 | `GET /v1/me/files/recents` |
| Connect (Validate) | 1 | `GET /v1/files/{key}?depth=1` |
| Sync Now | 3-4 | `GET /v1/files/{key}` + `GET /v1/files/{key}/styles` + file structure cache + thumbnail export (top 100 frames) |
| File Structure | 0 (cached) | Served from snapshot after sync |
| Thumbnails (page load) | 0 (cached) | Served from snapshot — cached during sync |
| List Components | 1 | `GET /v1/files/{key}/components` |
| Extract Components | 1 | `GET /v1/images/{key}` (batch export) |

**Total for a full connect + sync + browse**: ~5-6 API calls. On starter plans, this can exhaust the budget in one session. Subsequent page loads use **zero** Figma API calls — both file structure and thumbnails are served from the DB cache.

## How the Hub Minimizes API Calls

1. **File structure caching** — During "Sync Now", the file structure is cached in the token snapshot. Subsequent file browser loads serve from cache (0 API calls)
2. **Thumbnail caching** — During "Sync Now", thumbnails for the top 100 priority-ranked frames are exported and cached in the snapshot. The file browser reads thumbnails directly from the file-structure response — no separate API call needed on page load
3. **Cache-first export** — The `export-images` endpoint checks the cached thumbnail URLs before calling Figma. Only uncached node IDs trigger a live API call
4. **Rate limit passthrough on validation** — If Figma returns 429 during `validate_connection`, the connection is still created (token is valid, just rate-limited)
5. **Browse fallback** — If file browsing is rate-limited, the wizard falls through to manual URL entry instead of blocking

## Import Design vs Extract Components

These are two separate features in the Import dialog:

| Feature | What it does | Input | Output |
|---------|-------------|-------|--------|
| **Import Design** | Takes the full design layout (or selected frames), analyzes structure, generates a campaign brief, runs through the AI Scaffolder pipeline | Design frames from file browser | Complete HTML email template |
| **Extract Components** | Fetches **published Figma components** and uses AI to convert each into a reusable HTML component | Published components (must be explicitly published in Figma's Assets panel) | Individual HTML components in the Hub's component library |

**Key distinction**: "Extract Components" only works with components that are **published** in Figma (via the Assets panel > Publish). Regular frames, groups, and component instances are not included — only the master component definitions.

## When You Hit a Rate Limit

1. **Don't panic** — Your connection and encrypted token are saved. Nothing is lost.
2. **Don't retry repeatedly** — Each retry consumes quota and extends the lockout
3. **Use "Refresh Token" button** — If you need to update your PAT later, use the Refresh Token button on the connection card instead of deleting and re-creating
4. **Options to unblock**:
   - Wait for `Retry-After` to expire (check the error message for the duration)
   - Use a **different Figma account** (free accounts are fine — the design file just needs to be shared with or duplicated to that account)
   - For production/team use, upgrade to Figma Professional for higher rate limits

## Stable Encryption Key

To prevent "Token sync failed" errors after server restarts, set a stable encryption key in your `.env`:

```bash
DESIGN_SYNC__ENCRYPTION_KEY=your-stable-secret-key-here
```

If this is empty (default), the JWT secret is used — which means changing `AUTH__JWT_SECRET_KEY` will make all stored design tokens undecryptable. Set a dedicated key for production.
