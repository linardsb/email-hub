---
description: Security rules for all code
paths: "**/*.{py,ts,tsx}"
---

# Security Rules

- NEVER hardcode secrets, API keys, or passwords in source code
- NEVER commit .env files or credentials
- Use `escape_like()` for SQL LIKE/ILIKE patterns
- Use bcrypt for password hashing (never MD5/SHA)
- HTTPBearer with auto_error=False for auth dependencies
- Generic error messages for auth failures ("Invalid email or password")
- Rate limit all public endpoints
- Validate and sanitize all user input

# Semgrep Triage Rules for Agent Development

All agents follow the same pattern: prompt → LLM → generated HTML → `sanitize_html_xss()` → user. When Semgrep flags a finding, apply this decision tree:

1. **Does user input reach this code path?** No → false positive
2. **Is the "dangerous" pattern the intended functionality?** Yes → false positive
3. **Is the code exposed to the network or external clients?** No → lower priority

## Known false positives (suppressed via `.semgrepignore`)
- `sa.text()` in `alembic/` migrations — admin-only, no user input
- Template vars in `href` in `email-templates/` — dynamic URLs are intended
- `render(source)` in `services/maizzle-builder/` — internal sidecar, source from backend API

## Patterns that ARE real issues — always fix
- `dangerouslySetInnerHTML` in frontend preview components → add DOMPurify
- `$host` header forwarding in nginx → use explicit server name
- Any agent code passing user input directly to `sa.text()`, `subprocess`, `eval`, or external APIs without sanitization
- WebSocket upgrade headers not restricted to `websocket` value only
