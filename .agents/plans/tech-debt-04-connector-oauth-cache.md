# Tech-Debt 04 — SFMC + Adobe Sync Provider OAuth Cache Hardening

**Cluster:** A (highest severity — known-bug).
**Closes:** `tech-debt-04-sync-provider-duplication`.
**Branch:** `tech-debt/04-connector-oauth-cache`.
**Estimated effort:** 1 session.

## Problem

`app/connectors/sfmc/sync_provider.py:29` and `app/connectors/adobe/sync_provider.py:29`
both carry the F020/F024/F069 anti-patterns that Plan 04 collapsed in `service.py`:

1. `_token_cache: ClassVar[dict[str, tuple[str, float]]]` — process-wide, no eviction,
   grows unbounded under high-tenant-count workloads.
2. `_cache_key()` returns `hashlib.sha256(client_id)[:16]` — **64-bit truncation.**
   Two tenants whose `client_id` SHA-256 collides on the first 16 hex chars get
   each other's bearer tokens for the lifetime of the cache entry. Birthday-bound
   means a real collision needs ~2^32 tenants, but the per-pair collision
   probability is non-zero in any real workload and the consequence
   (cross-tenant token reuse) is severe enough to warrant fixing regardless.
3. No vendor prefix — if a future provider reuses the same `_token_cache` shape,
   keys can collide across vendors.

The clean code path (`OAuthConnectorService` at `app/connectors/_base/oauth.py:27`)
already solves this:
- per-instance `LruWithTtl[str, str]` (line 44–47, `maxsize=64`),
- vendor-prefixed key `f"{self.service_name}:{credentials['client_id']}"` (line 100–101),
- TTL parsed from `expires_in` minus a 60s grace.

The two `sync_provider.py` files predate that work and were not migrated.

## Decision: surgical bandaid, not full unification

`OAuthConnectorService.export()` is shaped for one-shot HTML push (single
`_post_asset` + 401-retry). The `sync_provider.py` surface is bidirectional
CRUD (`list_templates / get_template / create_template / update_template /
delete_template / validate_credentials`). Migrating `sync_provider.py` to inherit
`OAuthConnectorService` would require splitting `export()` into a generic
`_authenticated_request()` mixin and reshaping the resilient-request flow. That's
a connector-architecture refactor, not a tech-debt fix.

**This plan does Option (b) from `deferred-items.json`:** replace the
`ClassVar` cache with `LruWithTtl(maxsize=64)` and drop the SHA-256[:16]
truncation in favour of `f"{vendor}:{client_id}"`. Both files become structurally
identical to the `OAuthConnectorService` cache plumbing, which makes the
follow-up unification (when scheduled) a mechanical AST move.

## Files

| File | Change |
|---|---|
| `app/connectors/sfmc/sync_provider.py` | Replace `_token_cache` (line 29) + `_cache_key` (line 35–37) + `_get_access_token` (line 39–62) cache plumbing |
| `app/connectors/adobe/sync_provider.py` | Same changes, mirror SFMC |
| `app/connectors/sfmc/tests/test_sync_provider.py` | New (or extend) — cross-tenant test asserting two providers with colliding-prefix `client_id` SHA-256 do **not** share tokens |
| `app/connectors/adobe/tests/test_sync_provider.py` | Same |

## Steps

### 1. Pre-flight

```bash
git checkout -b tech-debt/04-connector-oauth-cache
make check
rg -n "_token_cache|_cache_key" app/connectors/{sfmc,adobe}/sync_provider.py
```

Confirm only the two files matched. If `test_sync_provider.py` exists, read it
first — the surgical fix changes the cache key, so any test that pokes the cache
directly via `SFMCSyncProvider._token_cache[...]` needs an update.

### 2. SFMC sync provider rewrite

`app/connectors/sfmc/sync_provider.py` — three edits:

**Edit 1 (lines 1–18, imports + class header).** Drop `hashlib`, add
`LruWithTtl`. Drop `ClassVar`-keyed `_token_cache` declaration. Initialize
per-instance cache in `__init__`:

```python
from app.core.cache import LruWithTtl

_TOKEN_CACHE_MAXSIZE = 64
_TOKEN_REFRESH_GRACE = 60.0
_DEFAULT_TOKEN_TTL = 3600.0


class SFMCSyncProvider:
    """..."""

    _base_url: str

    def __init__(self, settings: Settings | None = None) -> None:
        _settings = settings or get_settings()
        self._base_url = _settings.esp_sync.sfmc_base_url
        self._token_cache: LruWithTtl[str, str] = LruWithTtl(
            maxsize=_TOKEN_CACHE_MAXSIZE,
            default_ttl=_DEFAULT_TOKEN_TTL,
        )
```

**Edit 2 (lines 35–37, `_cache_key`).** Replace SHA-256[:16] with vendor-prefixed
key. The SHA-256 wrapper is unnecessary: `client_id` is already a stable opaque
identifier and the cache is bounded by `maxsize`.

```python
@staticmethod
def _cache_key(credentials: dict[str, str]) -> str:
    return f"sfmc:{credentials['client_id']}"
```

**Edit 3 (lines 39–62, `_get_access_token`).** Switch to `LruWithTtl.get()` /
`put(ttl=...)`. The post-response `time.time() + expires_in` arithmetic is gone
(LruWithTtl handles TTL internally via `monotonic`):

```python
async def _get_access_token(self, credentials: dict[str, str]) -> str:
    key = self._cache_key(credentials)
    cached = self._token_cache.get(key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{self._base_url}/v2/token",
            json={
                "client_id": credentials["client_id"],
                "client_secret": credentials["client_secret"],
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = str(data["access_token"])
        expires_in = float(data.get("expires_in", _DEFAULT_TOKEN_TTL))
        ttl = max(expires_in - _TOKEN_REFRESH_GRACE, 1.0)
        self._token_cache.put(key, token, ttl=ttl)
        return token
```

**Edit 4 (line 86, 401 eviction in `_call_with_auth`).** `LruWithTtl.pop()`
replaces `self._token_cache.pop(key, None)`:

```python
self._token_cache.pop(self._cache_key(credentials))
```

(`LruWithTtl.pop()` is no-op on miss, so the `, None` arg is gone.)

**Drop dead imports.** Both `import hashlib` (was used only by the truncated
SHA-256 cache key) and `import time` (was used only for the manual
`time.time() + expires_in` arithmetic) are no longer referenced. Remove both
from the imports block at the top of `sfmc/sync_provider.py`. `make types` will
catch any straggler reference if you miss one.

### 3. Adobe sync provider rewrite

`app/connectors/adobe/sync_provider.py` — apply the same 4 edits with these
deltas vs. SFMC:

- `_base_url` from `_settings.esp_sync.adobe_base_url`.
- Token endpoint: `/ims/token/v3` (not `/v2/token`).
- Token request uses `data=` (form-encoded) per Adobe IMS, not `json=`.
- Default TTL is 86399s, not 3600s — keep that as the `_DEFAULT_TOKEN_TTL`
  inside `adobe/sync_provider.py` (do **not** share a constant across the two
  files; vendor-specific defaults belong in their vendor module).
- Cache key: `f"adobe:{credentials['client_id']}"`.

### 4. Cross-tenant regression test

Either create `app/connectors/sfmc/tests/test_sync_provider.py` if absent, or
extend an existing test file. The test must prove: two providers with
`client_id` values that share the same SHA-256[:16] prefix do **not** share a
cached token. Pre-image collision is intractable to construct; instead, test
that the cache key is no longer truncated by asserting on the key itself:

```python
def test_cache_key_not_truncated() -> None:
    p = SFMCSyncProvider()
    key_a = p._cache_key({"client_id": "tenant-a-with-long-suffix-XYZ"})
    key_b = p._cache_key({"client_id": "tenant-b-with-long-suffix-ABC"})
    assert key_a != key_b
    assert "tenant-a-with-long-suffix-XYZ" in key_a
    assert key_a.startswith("sfmc:")


def test_token_cache_is_per_instance() -> None:
    """Regression: previous ClassVar dict shared state across instances."""
    p1 = SFMCSyncProvider()
    p2 = SFMCSyncProvider()
    p1._token_cache.put("sfmc:tenant-a", "token-a", ttl=600)
    assert p2._token_cache.get("sfmc:tenant-a") is None
```

Mirror both tests for Adobe.

### 5. Verify

```bash
make types
make lint
make test app/connectors/sfmc app/connectors/adobe
make check-full
```

**Manual probe:** `rg -n "_token_cache" app/connectors/{sfmc,adobe}/` should now
match only constructor lines and test files. No `ClassVar[dict]`, no `hashlib`
import in either `sync_provider.py`.

### 6. PR checklist

- [ ] `.agents/deferred-items.json` — set `tech-debt-04-sync-provider-duplication`
      `status: "closed"`, add `closed_commit` + `closed` (`2026-05-XX`), add
      `closure_note` capturing that this is the surgical fix and a follow-up
      unification ABC remains as future work.
- [ ] `.agents/plans/deferred-items-tracker.md` — strike out Cluster A row, link
      the PR number.
- [ ] `make check-full` green.
- [ ] No diff in `app/connectors/{sfmc,adobe}/service.py` — those already use
      `OAuthConnectorService` and are not in scope for this plan.

## Out of scope (deferred to a follow-up)

- Migrating `sync_provider.py` to inherit a hypothetical `OAuthSyncProviderBase`
  ABC. Leave a `# TODO(tech-debt): ` line at the top of each file pointing back
  to this plan and the closed deferred-items entry, so the next sweep knows the
  bandaid is intentional.
