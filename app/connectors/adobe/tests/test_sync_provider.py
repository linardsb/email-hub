# pyright: reportPrivateUsage=false
"""Regression tests for Adobe Campaign sync provider OAuth cache hardening.

Closes deferred-items entry `tech-debt-04-sync-provider-duplication`:
  - cache key must NOT be SHA-256[:16] truncated (cross-tenant collision risk),
  - `_token_cache` must be per-instance (the previous `ClassVar[dict]` shared
    state across every provider in the process).
"""

from __future__ import annotations

from app.connectors.adobe.sync_provider import AdobeSyncProvider


class TestCacheKey:
    """Cache key is vendor-prefixed and not truncated."""

    def test_cache_key_includes_full_client_id(self) -> None:
        p = AdobeSyncProvider()
        key = p._cache_key({"client_id": "tenant-a-with-long-suffix-XYZ"})
        assert "tenant-a-with-long-suffix-XYZ" in key
        assert key.startswith("adobe:")

    def test_cache_key_distinguishes_distinct_client_ids(self) -> None:
        p = AdobeSyncProvider()
        key_a = p._cache_key({"client_id": "tenant-a-with-long-suffix-XYZ"})
        key_b = p._cache_key({"client_id": "tenant-b-with-long-suffix-ABC"})
        assert key_a != key_b


class TestPerInstanceCache:
    """Cache is per-instance — no shared `ClassVar[dict]` state."""

    def test_token_cache_is_per_instance(self) -> None:
        p1 = AdobeSyncProvider()
        p2 = AdobeSyncProvider()
        p1._token_cache.put("adobe:tenant-a", "token-a", ttl=600)
        assert p2._token_cache.get("adobe:tenant-a") is None

    def test_token_cache_isolates_writes(self) -> None:
        p1 = AdobeSyncProvider()
        p2 = AdobeSyncProvider()
        p1._token_cache.put("adobe:shared-key", "token-from-p1", ttl=600)
        p2._token_cache.put("adobe:shared-key", "token-from-p2", ttl=600)
        assert p1._token_cache.get("adobe:shared-key") == "token-from-p1"
        assert p2._token_cache.get("adobe:shared-key") == "token-from-p2"
