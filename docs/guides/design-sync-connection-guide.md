# Design Sync Connection Guide

Step-by-step guide for connecting design files (Figma, Sketch, Canva, Penpot) to the Merkle Email Hub. Covers setup, common errors, and rate limit avoidance.

## Before You Start

### 1. Generate a Personal Access Token (PAT)

| Provider | Where to generate | Scopes needed |
|----------|-------------------|---------------|
| Figma | [figma.com/developers/api#access-tokens](https://www.figma.com/developers/api#access-tokens) | File read access |
| Penpot | Account Settings > Access Tokens | Read |

- Tokens are encrypted at rest in the database (Fernet + PBKDF2)
- Only the last 4 characters are visible in the UI
- Never share tokens in chat, Slack, or commit them to source control
- If a token is exposed, revoke it immediately and generate a new one

### 2. Verify File Access

Before connecting through the Hub, confirm your PAT can access the file:

```bash
# Figma: test your PAT
curl -s https://api.figma.com/v1/me \
  -H "X-Figma-Token: YOUR_PAT" | jq .handle

# Figma: test file access (extract file key from URL)
# URL: https://www.figma.com/design/sV1UnG6Tv6SvaJCHVaLGtc/My-Design
# File key: sV1UnG6Tv6SvaJCHVaLGtc
curl -s "https://api.figma.com/v1/files/YOUR_FILE_KEY?depth=1" \
  -H "X-Figma-Token: YOUR_PAT" | jq .name
```

If you get `"status": 403`, your PAT doesn't have access to the file. Ask the file owner to share it with your Figma account.

### 3. Check the File URL Format

The Hub expects standard design file URLs:

| Provider | Valid URL format |
|----------|----------------|
| Figma | `https://www.figma.com/design/<file_key>/<name>` or `https://www.figma.com/file/<file_key>/<name>` |
| Penpot | `https://design.penpot.app/#/workspace/<project>/<file>` |

Query parameters (`?node-id=...`, `?t=...`) are ignored — only the file key is extracted.

## Connection Flow

1. Go to **Design Sync** in the sidebar
2. Click **Connect Design File**
3. **Step 1 — Authenticate:** Select provider, paste your PAT, click "Browse Files"
4. **Step 2 — Select file:** Pick from the file list, or enter a URL manually if browsing returns empty
5. **Step 3 — Configure:** Name the connection, optionally link to a project, click "Connect"

## Avoiding Figma Rate Limits (429 Errors)

Figma enforces API rate limits **per account** (not per IP or token). Generating a new PAT does not reset the limit.

| Plan | Approx. limit | Retry-After | Scope |
|------|---------------|-------------|-------|
| Starter/Free | ~3-5 calls/min | Up to 4+ days | Per Figma account |
| Professional | Higher | Minutes to hours | Per account |

The Hub makes API calls during:
- **Browse Files** — 1 call
- **Connect** — 1 call (validates PAT + file access)
- **Sync Now** — 3-4 calls (file data + styles + structure + thumbnail export)
- **File Structure (page load)** — 0 calls (served from DB cache)
- **Thumbnails (page load)** — 0 calls (served from DB cache, populated during sync)
- **Layout Analysis** — reuses cached file data

### How to Avoid 429 Errors

| Do | Don't |
|----|-------|
| Wait 1-2 minutes between connection attempts if one fails | Rapidly retry failed connections |
| Connect one file at a time | Open multiple browser tabs connecting different files simultaneously |
| Use "Sync Now" sparingly (once after connecting, then as needed) | Click "Sync Now" repeatedly |
| Select only the frames you need for import | Select all frames in a large file |
| Use the Mock provider for testing the UI flow | Use a real PAT for UI testing |
| Use a different Figma account if rate-limited | Generate new PATs on the same account (doesn't help) |

### If You Hit a 429

1. **Don't retry repeatedly** — each retry consumes quota and extends the lockout
2. Check the error message for `Retry-After` duration
3. **Options to unblock**: wait for the timer, use a **different Figma account** (share the file with it), or upgrade to Professional
4. Your connection and encrypted token are saved — nothing is lost

## Common Errors and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| "Figma access denied. Check your Personal Access Token." | Invalid or revoked PAT | Generate a new PAT in Figma settings |
| "Figma file not found. Check the file URL." | File deleted, or PAT doesn't have access | Verify the URL in your browser; ask owner to share |
| "Figma API returned status 429" | Rate limited | Wait 60 seconds and retry |
| "Invalid Figma URL" | URL doesn't match expected format | Use `figma.com/design/<key>/...` or `figma.com/file/<key>/...` |
| "Failed to browse files" | PAT valid but no recent files | Use manual URL entry (Step 2 fallback) |
| "Failed to connect design file" (generic) | Network error or server issue | Check browser console (F12) for details; verify backend is running |

## After Connecting

Once connected, you can:

1. **Browse file structure** — Expand the tree to see pages, frames, and components. Thumbnails for the top 100 frames are cached during sync and load instantly (zero Figma API calls)
2. **Extract design tokens** — Click "Sync Now" to pull colors, typography, and spacing tokens. Colors and typography are extracted from both published styles and direct node properties (fills, text styles)
3. **Import frames** — Select frames (click the thumbnail or checkbox) and click "Import Selected Frames" to generate email HTML via the Scaffolder AI agent
4. **Extract components** — Pull individual Figma components into the Hub's component library

## Token Management

- Tokens are stored encrypted (Fernet + PBKDF2) — the Hub never displays or logs the full token
- To rotate a PAT: use the **Refresh Token** button on the connection card (no need to delete and re-create)
- Each connection stores its own token — multiple connections can use different PATs
- If a team member leaves, revoke their PAT in Figma and refresh affected connections with a new PAT

## For Developers

### Testing Without Figma API Calls

Use the **Mock** provider (available in development mode) to test the UI without hitting any external APIs:

1. Select "Mock (Demo)" as the design tool
2. Enter any value as the access token
3. The mock provider returns realistic file structures and tokens

### Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `DESIGN_SYNC__FIGMA_PAT` | Default Figma PAT (optional — users provide their own per connection) | No |
| `DESIGN_SYNC__ENCRYPTION_KEY` | Custom encryption key for token storage (falls back to JWT secret) | No |
| `DESIGN_SYNC__PENPOT_ENABLED` | Enable Penpot provider | No (default: false) |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/design-sync/browse-files` | Browse files with PAT (pre-connection) |
| `POST` | `/api/v1/design-sync/connections` | Create a new connection |
| `GET` | `/api/v1/design-sync/connections` | List all connections |
| `GET` | `/api/v1/design-sync/connections/{id}/file-structure` | Browse file tree |
| `GET` | `/api/v1/design-sync/connections/{id}/tokens` | Get extracted tokens |
| `POST` | `/api/v1/design-sync/connections/sync` | Re-sync tokens |
| `POST` | `/api/v1/design-sync/connections/export-images` | Export node images |
| `POST` | `/api/v1/design-sync/connections/delete` | Delete a connection |
