# Tech Debt 02 — Public-API Security

**Source:** `TECH_DEBT_AUDIT.md`
**Scope (remaining):** Auth-token strictness — JWT decode requires `exp`/`iat`/`type`/`jti`, refresh TTL flows from `AuthConfig`, Redis fail-open on the revocation check is observable.
**Estimated effort:** ¼ day, single PR.
**Prerequisites:**
- ✅ Plan 01 landed (`eddcd1ac` / PR #40).
- ✅ Parts A (F004) and B (F005) landed via `d38be734` / PR #41 — see "Already shipped" below.

## Findings addressed (this PR)

F027 (JWT `decode_token` does not require `exp`/`iat`/`type`/`jti`) — High
F028 (`REFRESH_TOKEN_TTL_SECONDS` hardcoded, decoupled from `AuthConfig`) — High
F029 (token revocation Redis fail-open silent) — High

## Already shipped — do NOT re-execute

- **Part A — F004 (prompt-injection guard on structured path).** Shipped `d38be734`. `_secure_user_message` was split into `_scan_request` / `_wrap_user_message` / `_apply_sanitized_input` on `BaseAgentService`; the scan now runs once at the top of `_process_impl` so structured mode is covered. Regression test: `app/ai/agents/tests/test_injection_guard_coverage.py` (parametrized over the 7 agents × `html`/`structured`).
- **Part B — F005 (MCP per-user scope enforcement).** Shipped `d38be734`. `require_scope` decorator in `app/mcp/auth.py`; all 27 `@mcp.tool` decorators annotated (26 in `app/mcp/tools/*.py` + `mcp_batch_execute` in `app/mcp/server.py`); startup check in `_register_schemas` fails closed if any tool lacks `_mcp_required_scope`. Regression test: `app/mcp/tests/test_scope_enforcement.py`.

If `/be-execute` finds itself touching `app/ai/agents/base.py`, `app/mcp/auth.py`, `app/mcp/server.py`, or any `app/mcp/tools/*.py`, **stop** — that is shipped work and should not be re-derived.

## Pre-flight

```bash
git checkout -b sec/tech-debt-02-auth-strictness
make check  # baseline green
```

## Part C — Auth token strictness

These three items are Quick Wins per `TECH_DEBT_AUDIT.md` line 170 but were dropped from Plan 01. Originally bundled with Parts A+B because all touch `app/auth/`; A+B have since shipped (PR #41), so this is the only remaining work.

### C1. F027 — Strict required claims in `decode_token`

`app/auth/token.py:127-152`. Currently `jwt.decode(...)` does not pass `options={"require": [...]}`, and `payload.get("jti", "")` lets JTI-less tokens through `is_token_revoked("")` → False.

**Order matters:** the require list will include `iat`, but neither `create_access_token` (`:31-53`) nor `create_refresh_token` (`:56-77`) currently emit it (`rg '"iat"' app/auth/` returns zero matches). Decode strictness must land in the *same change* as `iat` emission, otherwise every freshly issued token is rejected on first use.

#### C1a. Emit `iat` in both token creators

```python
# app/auth/token.py — create_access_token
now = datetime.datetime.now(datetime.UTC)
expire = now + datetime.timedelta(minutes=settings.auth.access_token_expire_minutes)
payload: dict[str, Any] = {
    "sub": str(user_id),
    "role": role,
    "iat": now,        # NEW — required by decode_token after C1b
    "exp": expire,
    "type": "access",
    "jti": uuid.uuid4().hex,
}
```

Apply the same `iat = now` pattern to `create_refresh_token`. Reuse one `now` per call so `iat` and `exp` agree on the same instant (avoids the off-by-microsecond skew that bites token-age telemetry).

#### C1b. Strictness in `decode_token`

```python
# app/auth/token.py — decode_token
payload = jwt.decode(
    token,
    settings.auth.jwt_secret_key,
    algorithms=[_JWT_ALGORITHM],
    options={"require": ["exp", "iat", "type", "jti"]},
)
jti = payload["jti"]  # required, no .get() with empty default
if not jti:
    raise InvalidTokenError("missing jti")
```

Drop the permissive defaults at `:145-148` (`payload.get("role", "")`, `payload.get("type", "access")`, `payload.get("jti", "")`) — `type` and `jti` are now in the require list, and `role` stays optional only for refresh tokens (which carry `"role": ""`).

#### C1c. Update existing JWT test fixtures

`app/tests/test_jwt_algorithm.py:37` and `:52` hand-craft tokens missing `iat`. After C1b, these tokens are rejected on the require check *before* the algorithm logic runs, so the tests still pass but no longer exercise what they claim to. Add `"iat": 1` to both payloads to keep the algorithm-rejection assertion meaningful.

#### C1d. New tests

Add to `app/auth/tests/test_token.py` (create file if absent):
- `test_decode_rejects_token_without_jti`
- `test_decode_rejects_token_without_exp`
- `test_decode_rejects_token_without_iat` — hand-rolled token with `{sub, exp, type, jti}` but no `iat`; expect `decode_token` returns `None`.
- `test_create_access_token_emits_iat` — decode (skip-verify) the freshly minted token and assert `iat` is present and within ±2 s of `datetime.now(UTC)`.
- `test_create_refresh_token_emits_iat` — same shape for refresh.

### C2. F028 — Refresh TTL computed from config

`app/auth/routes.py:33`. Replace the hardcoded `REFRESH_TOKEN_TTL_SECONDS = 604800` with:

```python
def _refresh_ttl_seconds() -> int:
    return get_settings().auth.refresh_token_expire_days * 86400
```

Update the **single** callsite at `app/auth/routes.py:91` (`revoke_token(payload.jti, ttl_seconds=REFRESH_TOKEN_TTL_SECONDS)`). Verify nothing else imports the old constant: `rg "REFRESH_TOKEN_TTL_SECONDS" /Users/Berzins/Desktop/email-hub` — preflight already confirmed only this one match.

### C3. F029 — Enrich existing Redis fail-open log

`app/auth/token.py:118-124`. The `is_token_revoked` exception handler already emits `logger.warning("auth.token.revocation_check_degraded", jti=jti, detail=...)` and returns `False`. The remaining gaps from the audit are: (a) the captured exception isn't logged, (b) there's no follow-up note about the in-memory denylist alternative.

**Pin the existing log key** — `auth.token.revocation_check_degraded` is the deployed event name; renaming to `auth.token_revocation_check_unavailable` (the prior draft of this plan) would silently break any operator dashboard or alert that watches it. Enrich in place instead:

```python
except Exception as exc:  # bare except stays — the import inside try can also raise ImportError
    logger.warning(
        "auth.token.revocation_check_degraded",
        jti=jti,
        error=str(exc),
        error_type=type(exc).__name__,
        detail="Redis unavailable - token revocation check skipped (fail-open)",
    )
    # TODO follow-up: consider in-memory short-window denylist as fallback for sustained Redis outages
    return False  # fail-open for availability
```

Skip the Prometheus counter — `app/core/metrics.py` does not exist (`rg "metrics" app/core/` returns no module); structured-log enrichment is sufficient.

### C4. Tests for C2 and C3

Add to `app/auth/tests/test_token.py` (alongside the C1d tests):
- `test_refresh_ttl_follows_config` (parametrize over `refresh_token_expire_days = 1, 7, 30`)
- `test_revocation_check_fails_open_emits_warning` (mock Redis, assert log captured)

## Verification

```bash
make check
make test
# Manual JWT probe — hand-craft token missing iat (or jti, or type, or exp); expect 401:
python -c "import jwt; print(jwt.encode({'sub':'1','exp':9999999999,'type':'access','jti':'x'}, 'CHANGE-ME-IN-PRODUCTION-this-is-not-a-real-secret', algorithm='HS256'))" \
  | xargs -I{} curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer {}" http://localhost:8891/api/v1/projects
# Expect: 401. Repeat after dropping jti / type / exp from the payload — all 401.
# Then issue a real token via /api/v1/auth/login and confirm 200 — sanity-check that iat emission lands.
```

## Rollback

Each of C1 / C2 / C3 is an independent single-file revert (`app/auth/token.py` for C1+C3, `app/auth/routes.py` for C2). C1's `iat` emission and decode strictness should revert together — leaving emission without strictness is harmless, but reverting strictness without removing emission means newly issued tokens carry an unused `iat`. Acceptable, but cleaner to revert as a pair.

## Risk notes

- **C1 ordering — emission must precede strictness in the same commit.** If decode strictness lands first, every previously issued (still-valid) access/refresh token in users' clients fails on its next request because they were minted without `iat`. C1a + C1b in the same change is non-negotiable.
- **C1 — short-window token churn during deploy.** Even with C1a+C1b co-deployed, tokens minted by an old replica during a rolling deploy lack `iat` and fail decode against a new replica. Mitigate by accepting brief 401s during the rollout window, or by adding a transitional `iat` fallback (issue token with `iat=now()` if missing) — recommend the former; it's a single-deploy bump, not ongoing breakage.
- **C2 — only one callsite.** Plan-text drafts implied two; `rg` confirms one. Don't grep-and-replace beyond `app/auth/routes.py:91`.
- **C3 — keep the existing log key.** `auth.token.revocation_check_degraded` is already the deployed event name. Operator dashboards may key off it. Enrich the payload (`error`, `error_type`); do not rename.

## Done when

- [ ] `create_access_token` and `create_refresh_token` emit `iat` (verified by C1d's `test_create_*_token_emits_iat`).
- [ ] `decode_token` rejects tokens missing any of `exp` / `iat` / `type` / `jti` — three new C1d tests green.
- [ ] `app/tests/test_jwt_algorithm.py` updated so its hand-crafted tokens carry `iat` and continue to exercise algorithm rejection.
- [ ] Refresh TTL follows `AuthConfig.refresh_token_expire_days` — `test_refresh_ttl_follows_config` green; `rg "REFRESH_TOKEN_TTL_SECONDS" /Users/Berzins/Desktop/email-hub` returns no matches after the rename.
- [ ] Revocation Redis fail-open emits enriched warning under the existing `auth.token.revocation_check_degraded` key — `test_revocation_check_fails_open_emits_warning` green.
- [ ] `make check-full` green; pyright still 0 errors on `app/auth/token.py` + `app/auth/routes.py` + new `app/auth/tests/test_token.py` (preflight baseline was 0).
- [ ] Manual JWT probe (Verification block) returns 401 for tokens missing any required claim; 200 for a real `/auth/login` token.
- [ ] PR titled `sec(auth): JWT decode strictness + refresh TTL from config + revocation log enrichment (F027 F028 F029)`.
- [ ] Mark F027, F028, F029 as **RESOLVED** in `TECH_DEBT_AUDIT.md`. (F004, F005 were resolved by PR #41 / `d38be734` — verify they're already marked there; if not, this PR can flip those flags too.)
