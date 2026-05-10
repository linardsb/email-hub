# Tech-Debt 12 — `/bootstrap` Hardening (F030)

**Cluster:** Auth/Token (Session 11). **Closes:** F030 in `TECH_DEBT_AUDIT.md`.
**Branch:** `sec/tech-debt-12-bootstrap-hardening`. **Effort:** 1 session.

## Problem (F030)

`POST /api/v1/auth/bootstrap` creates the first admin and returns JWT tokens
with **no auth required**. Today's only gates are:

1. `settings.environment == "development"` (`app/auth/service.py:358`)
2. `await self.repo.count() == 0` (`app/auth/service.py:361`)

Both can be true on a misconfigured staging or preview deploy that gets
shipped before the operator seeds a user. First HTTP hit gets admin.
The audit prescribes (`TECH_DEBT_AUDIT.md:72`):

> Additionally require loopback origin or an env-bound bootstrap secret.

## Approach

Add a **third independent factor** — combined with the existing two via AND.
The third factor is satisfied if **either** sub-condition holds:

- **(a) loopback origin** — `request.client.host in {"127.0.0.1", "::1"}`
- **(b) shared secret** — request header `X-Bootstrap-Secret` matches
  `settings.auth.bootstrap_secret` via `secrets.compare_digest`, and the
  configured secret is non-empty.

Final policy: `dev` AND `zero-users` AND `(loopback OR valid-secret)`.

Rationale for OR-combining (a) and (b):

- (a) covers the operator running `curl` on the box itself. No env required.
- (b) covers automation (CI seed scripts, devcontainer/Docker setups where
  `request.client.host` is the bridge IP, not loopback).
- Production deploys with no `AUTH__BOOTSTRAP_SECRET` set and no loopback
  reachability cannot bootstrap — which is the goal.

`secrets.compare_digest` is constant-time. Empty configured secret means (b)
is unavailable (we never compare against `""`), so a missing config never
lets a request through.

A failed third-factor check raises `ForbiddenError` → 403 (separate handler
exists at `app/core/exceptions.py:125`). The existing
`InvalidCredentialsError` → 401 path is left alone for the env / zero-user
gates — those are not F030 scope and changing them would leak into
unrelated code.

## Files to Modify

| File | Change |
|---|---|
| `app/core/config/auth.py` | Add `bootstrap_secret: SecretStr = SecretStr("")` field bound to `AUTH__BOOTSTRAP_SECRET`. |
| `app/auth/service.py` | `bootstrap_demo(...)` accepts `client_host: str \| None` and `provided_secret: str \| None` kwargs. Adds the third-factor check, raises `ForbiddenError` on failure. Logs `auth.bootstrap_denied` with `reason` + `client_host` (no secret value). |
| `app/auth/routes.py` | `bootstrap()` reads `request.client.host` and `request.headers.get("x-bootstrap-secret")` and passes both to the service. Update docstring. |
| `app/auth/tests/test_bootstrap.py` | **NEW** — regression tests for the matrix below. |
| `.env.example` | Auto-regenerated via `make .env.example` (picks up the new `AUTH__BOOTSTRAP_SECRET` field). Verify the diff is exactly one line added. |
| `TECH_DEBT_AUDIT.md` | Mark F030 as RESOLVED with commit SHA + closure note (post-merge). |

No deferred-items entries match this scope (grepped `.agents/deferred-items.json`
for `bootstrap` / `auth/service` / `auth/routes` — no hits).

## Implementation Steps

### Step 1 — Config

In `app/core/config/auth.py`, import `SecretStr` from `pydantic` and add:

```python
bootstrap_secret: SecretStr = Field(
    default=SecretStr(""),
    description=(
        "Optional shared secret required by /api/v1/auth/bootstrap when the "
        "request is not from a loopback address. Empty disables non-loopback "
        "bootstrapping. Combined with ENVIRONMENT=development + zero-users "
        "gates as a third independent factor (F030)."
    ),
)
```

`SecretStr` keeps the value out of `repr()` / log lines. Service callers
pull the cleartext via `.get_secret_value()` only at the comparison site.

### Step 2 — Service

`app/auth/service.py:342` — change signature:

```python
async def bootstrap_demo(
    self,
    *,
    client_host: str | None,
    provided_secret: str | None,
) -> LoginResponse:
```

After the existing `environment != "development"` check (line 358) and
`count > 0` check (line 361), but **before** creating the admin user, add:

```python
import secrets as _secrets
from app.core.exceptions import ForbiddenError

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})
loopback_ok = client_host in LOOPBACK_HOSTS

configured_secret = settings.auth.bootstrap_secret.get_secret_value()
secret_ok = bool(configured_secret) and provided_secret is not None and (
    _secrets.compare_digest(configured_secret, provided_secret)
)

if not (loopback_ok or secret_ok):
    logger.warning(
        "auth.bootstrap_denied",
        reason="third_factor_failed",
        client_host=client_host,
        loopback_ok=loopback_ok,
        secret_provided=provided_secret is not None,
    )
    raise ForbiddenError("Bootstrap requires loopback origin or a valid bootstrap secret")
```

`bool(configured_secret)` short-circuits comparison when the operator hasn't
set `AUTH__BOOTSTRAP_SECRET` — we never `compare_digest` against `""`.
Imports go to module top (don't inline `import secrets`); rename to
`_secrets` to avoid shadowing the existing module-level identifier if any.
Quick `grep -n "^import secrets\|^from secrets" app/auth/service.py` to
confirm; rename only if there's a conflict.

Do NOT log the `provided_secret` value (only its presence). The `client_host`
field is already logged by middleware (`app/core/middleware.py:85`); echoing
it here is intentional — operators triaging a denied bootstrap need to know
which host attempted.

### Step 3 — Route

`app/auth/routes.py:48` — pass the new kwargs through:

```python
@router.post("/bootstrap", response_model=LoginResponse)
@limiter.limit("5/minute")
async def bootstrap(
    request: Request,
    service: AuthService = Depends(get_service),
) -> LoginResponse:
    """Bootstrap first admin user (dev + zero-users + loopback-or-secret).

    Creates the initial admin account and returns JWT tokens. All three of
    the following must hold:
      1. ENVIRONMENT=development
      2. No users exist yet
      3. Request originates from 127.0.0.1/::1 OR carries a valid
         X-Bootstrap-Secret header matching AUTH__BOOTSTRAP_SECRET.
    """
    client_host = request.client.host if request.client else None
    provided_secret = request.headers.get("x-bootstrap-secret")
    return await service.bootstrap_demo(
        client_host=client_host,
        provided_secret=provided_secret,
    )
```

Header lookup is case-insensitive in Starlette's `Headers` (verified at
starlette.datastructures.Headers); `"x-bootstrap-secret"` matches both
casings.

### Step 4 — Regression Tests (`app/auth/tests/test_bootstrap.py`)

New file. Use AsyncMock pattern from `app/projects/tests/test_bola.py:18-33`
for the rate-limiter-disable fixture; mirror the `MagicMock` request
factory style.

Six test cases — the truth table for the third factor plus the existing
gates:

| # | env | user count | client_host | x-bootstrap-secret | configured secret | expected |
|---|---|---|---|---|---|---|
| 1 | development | 0 | `127.0.0.1` | absent | empty | **200** (loopback) |
| 2 | development | 0 | `::1` | absent | empty | **200** (loopback IPv6) |
| 3 | development | 0 | `192.0.2.1` | absent | empty | **403** ForbiddenError |
| 4 | development | 0 | `192.0.2.1` | `"correct-horse"` | `"correct-horse"` | **200** (secret) |
| 5 | development | 0 | `192.0.2.1` | `"wrong"` | `"correct-horse"` | **403** ForbiddenError |
| 6 | production | 0 | `127.0.0.1` | absent | empty | **401** InvalidCredentialsError (existing gate) |
| 7 | development | 1 | `127.0.0.1` | absent | empty | **401** InvalidCredentialsError (existing gate) |

Test #3 is the **mandatory regression assertion** the task spec calls for
("non-loopback origins are 403'd in development").

Test pattern (sketch — adapt counts, do not copy verbatim):

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.auth.service import AuthService
from app.auth.exceptions import InvalidCredentialsError
from app.core.exceptions import ForbiddenError


@pytest.fixture
def service():
    svc = AuthService(AsyncMock())
    svc.repo = AsyncMock()
    svc.repo.count = AsyncMock(return_value=0)
    svc.repo.create = AsyncMock(side_effect=lambda u: (setattr(u, "id", 1), u)[1])
    return svc


@pytest.mark.asyncio
async def test_non_loopback_dev_no_secret_is_forbidden(service):
    with pytest.raises(ForbiddenError):
        await service.bootstrap_demo(
            client_host="192.0.2.1",
            provided_secret=None,
        )
```

For tests 4/5 use `monkeypatch.setenv("AUTH__BOOTSTRAP_SECRET", "correct-horse")`
plus `get_settings.cache_clear()` (it's `@lru_cache`d) so the new value is
picked up. Confirm the cache-clear pattern by reading
`app/core/tests/test_config_security.py` — it already does this.

For test 6 monkeypatch `AUTH__JWT_SECRET_KEY` (must be ≥32 chars and
non-default) and `AUTH__DEMO_USER_PASSWORD` (must not be `"admin"`) so the
production validator at `app/core/config/__init__.py:213` doesn't trip.

The test file gets the standard `# pyright: reportUnknownMemberType=false, ...`
header used in the other auth tests — see `app/auth/tests/test_token.py`.

### Step 5 — Manual smoke check

After running the suite, also smoke the wiring with the dev server:

```bash
# Start the backend (zero users in DB).
make dev &
# Loopback path (should 200 then return tokens):
curl -X POST http://127.0.0.1:8891/api/v1/auth/bootstrap
# Drop the user with `make db-migrate down ...` or DB shell, restart, then:
# Non-loopback simulation via Host-bridge IP — easiest is to set
# AUTH__BOOTSTRAP_SECRET=test123 and hit it from a remote shell:
curl -X POST http://<lan-ip>:8891/api/v1/auth/bootstrap   # → 403
curl -X POST http://<lan-ip>:8891/api/v1/auth/bootstrap \
  -H 'X-Bootstrap-Secret: test123'                        # → 200
```

Document the result in the PR body under "Manual verification".

### Step 6 — `.env.example` regeneration

Run `make .env.example` after the config change. The CI step
`make check-env-drift` (referenced at `TECH_DEBT_AUDIT.md:75`) will fail the
build if this is forgotten.

## Security Checklist

- [x] **Auth required:** Endpoint is intentionally pre-auth (chicken-and-egg)
  — the three-factor gate is the substitute. New 403 path raises
  `ForbiddenError` (mapped by handler at `app/core/exceptions.py:189`).
- [x] **Rate limiting:** Existing `@limiter.limit("5/minute")` retained.
- [x] **Constant-time comparison:** `secrets.compare_digest` for the secret.
  Never `==` or `is`.
- [x] **No secret leakage in logs:** `auth.bootstrap_denied` logs only
  `secret_provided` (bool) — never the value. `SecretStr` keeps it out of
  config dumps and Pydantic `.model_dump()`.
- [x] **No internal-type leakage in error response:** `ForbiddenError`
  flows through `app_exception_handler` → `error_sanitizer.get_safe_error_message`
  (see `app/core/exceptions.py:134`). User sees the literal message we pass.
- [x] **Defense-in-depth retained:** Production environment still
  hard-blocks via the existing `environment != "development"` check.
  Operator must override both `ENVIRONMENT` AND set a secret AND have zero
  users to bootstrap from anywhere.
- [x] **No new SQL / shell / template execution paths.** Service does not
  pass `client_host` or `provided_secret` to the DB.
- [x] **Header injection:** `request.headers.get("x-bootstrap-secret")`
  returns the raw header value as a `str`. Starlette already strips CR/LF
  per RFC 9110 — no manual sanitization needed before `compare_digest`.

## Verification

- [ ] `make check-full` passes (lint + types + tests + security + golden +
  flag audit + migration lint + env-drift).
- [ ] New `app/auth/tests/test_bootstrap.py` — all 7 cases pass.
- [ ] Test #3 specifically asserts non-loopback in development → 403.
- [ ] Manual smoke (Step 5) recorded in PR.
- [ ] `.env.example` diff is exactly the new `AUTH__BOOTSTRAP_SECRET=` line.
- [ ] `TECH_DEBT_AUDIT.md:72` (F030 row) updated to **RESOLVED** with
  commit SHA in the closure note.
- [ ] No changes to `app/auth/dependencies.py`, `app/auth/repository.py`,
  `app/auth/token.py`, or `app/auth/schemas.py` — keep the diff surgical.

## Out of Scope

- Repointing the existing `environment != "development"` →
  `InvalidCredentialsError` (401) to `ForbiddenError` (403). Semantically
  cleaner but unrelated to F030 and breaks any caller that catches the
  former.
- Replacing `/bootstrap` with a CLI / Alembic seed step. Discussed in the
  audit but out of scope for this surgical fix.
- Deprecating `/auth/seed` (admin-only, env-gated) — separate audit row.
