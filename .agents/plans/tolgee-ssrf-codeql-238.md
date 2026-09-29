# Tolgee SSRF guard (CodeQL alert 238, py/partial-ssrf)

## Problem

CodeQL alert 238 (critical) flags `app/connectors/http_resilience.py:47` (`client.request`). SARIF from analysis 1860273876 (main, 2026-09-29) traces three sources, all in the Tolgee connector:

| Source | Tainted value | URL position |
|---|---|---|
| `app/connectors/tolgee/routes.py:37` (`POST /connect`) | `TolgeeConnectionRequest.base_url` (any string) | scheme + host; the PAT is sent there |
| `app/connectors/tolgee/routes.py:71` (`POST /pull`) | `locales` | path segment (already `BCP47Locale`, CodeQL cannot see the regex) |
| `app/connectors/tolgee/routes.py:88` (`POST /build-locales`) | `LocaleBuildRequest.locales: list[str]` | path segment, unvalidated (`../` reaches other Tolgee endpoints) |

## Decision

User chose a settings allowlist (2026-09-29). Implemented as exact base-URL match rather than host match: a self-hosted Tolgee is identified by its base URL, and returning the configured string (not the caller's) removes the tainted value from the request path.

## Changes

| File | Change |
|---|---|
| `app/core/config/connectors.py` | `TolgeeConfig.allowed_base_urls: list[str] = []` (`TOLGEE__ALLOWED_BASE_URLS`) |
| `app/connectors/tolgee/exceptions.py` | `TolgeeBaseUrlNotAllowedError(DomainValidationError)` |
| `app/connectors/tolgee/service.py` | `_resolve_base_url()`: default when omitted; else must equal (trailing `/` ignored) the default or an allowlist entry; returns the configured value |
| `app/connectors/tolgee/schemas.py` | `LocaleBuildRequest.locales: list[BCP47Locale]` |
| `app/connectors/tolgee/tests/test_service.py` | reject metadata IP / suffix-host / traversal URLs before any client is built; accept default, trailing-slash default, listed URL; reject non-BCP-47 locales |
| `.env.example` | regenerated (`make .env.example`) |

## Out of scope

- Stored connections created before this change keep their saved `base_url` (`_make_client` reads it from encrypted credentials). Only a developer-role user could have set one; revalidating stored rows would break existing connections without an allowlist entry. Noted in the PR.
- `/pull` locale source (routes.py:71) is already regex-validated; if CodeQL still reports it after this PR, dismissal as false positive is the user's call.

## Validation

1. `uv run pytest app/connectors/tolgee` → green.
2. `make sdk-snapshot && make sdk-local` → no `cms/packages/sdk/` drift.
3. `make check-full` → green; `git diff` after (lint rewrites).
4. PR CodeQL check → alert 238 reported fixed (expected, not yet run).
