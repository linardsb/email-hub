"""Section-level conversion cache for incremental design-to-email conversion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.design_sync.figma.layout_analyzer import EmailSection
from app.design_sync.protocol import ExtractedTokens

logger = get_logger(__name__)


@dataclass(frozen=True)
class SectionCacheEntry:
    """Cached conversion result for a single section."""

    html: str
    images: tuple[dict[str, str], ...]
    generated_at: str

    def to_json(self) -> str:
        """Serialize to JSON for Redis storage."""
        return json.dumps(
            {
                "html": self.html,
                "images": list(self.images),
                "generated_at": self.generated_at,
            }
        )

    @classmethod
    def from_json(cls, raw: str | bytes) -> SectionCacheEntry:
        """Deserialize from Redis JSON string.

        Raises ValueError on malformed data so callers can handle gracefully.
        """
        try:
            data = json.loads(raw)
            return cls(
                html=data["html"],
                images=tuple(data["images"]),
                generated_at=data["generated_at"],
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"Malformed cache entry: {exc}") from exc


def _round_float(v: float | None, decimals: int = 2) -> float | None:
    """Round float to fixed decimal places for hash stability."""
    if v is None:
        return None
    return round(v, decimals)


def _section_to_canonical(section: EmailSection) -> dict[str, Any]:
    """Build a canonical dict from an EmailSection for hashing."""
    return {
        "node_id": section.node_id,
        "section_type": section.section_type.value,
        "bg_color": section.bg_color,
        "width": _round_float(section.width),
        "height": _round_float(section.height),
        "column_layout": section.column_layout.value,
        "column_count": section.column_count,
        "padding_top": _round_float(section.padding_top),
        "padding_right": _round_float(section.padding_right),
        "padding_bottom": _round_float(section.padding_bottom),
        "padding_left": _round_float(section.padding_left),
        "item_spacing": _round_float(section.item_spacing),
        "texts": [
            {
                "node_id": t.node_id,
                "content": t.content,
                "font_size": _round_float(t.font_size),
                "font_weight": t.font_weight,
                "font_family": t.font_family,
                "is_heading": t.is_heading,
            }
            for t in section.texts
        ],
        "images": [
            {
                "node_id": img.node_id,
                "width": _round_float(img.width),
                "height": _round_float(img.height),
            }
            for img in section.images
        ],
        "buttons": [{"node_id": b.node_id, "text": b.text} for b in section.buttons],
    }


def _tokens_to_canonical(tokens: ExtractedTokens) -> dict[str, Any]:
    """Build a canonical dict from tokens for hashing (only style-affecting fields)."""
    return {
        "colors": sorted([c.hex for c in tokens.colors]),
        "dark_colors": sorted([c.hex for c in tokens.dark_colors]),
        "typography": sorted(
            [
                {"family": t.family, "size": _round_float(t.size), "weight": t.weight}
                for t in tokens.typography
            ],
            key=lambda x: (x["family"], str(x["size"]), x["weight"]),
        ),
        "spacing": sorted(round(s.value, 2) for s in tokens.spacing),
    }


def compute_section_hash(
    section: EmailSection,
    tokens: ExtractedTokens,
    *,
    container_width: int,
    target_clients: list[str] | None = None,
) -> str:
    """Compute a deterministic SHA-256 hash for a section + its conversion context.

    The hash captures all inputs that affect the rendered output:
    section content, design tokens, container width, and target clients.
    """
    canonical: dict[str, Any] = {
        "section": _section_to_canonical(section),
        "tokens": _tokens_to_canonical(tokens),
        "container_width": container_width,
        "target_clients": sorted(target_clients) if target_clients else [],
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


_REDIS_KEY_PREFIX = "section_cache"


class SectionCache:
    """Two-layer section conversion cache (in-memory LRU + Redis).

    The sync methods (get_sync / set_sync) use only the in-memory layer.
    The async methods (get / set / get_many / invalidate_connection) use
    both memory and Redis.
    """

    def __init__(self, *, max_memory: int = 500, redis_ttl: int = 3600) -> None:
        self._max_memory = max_memory
        self._redis_ttl = redis_ttl
        self._memory: dict[str, SectionCacheEntry] = {}

    @staticmethod
    def _mem_key(connection_id: str, section_hash: str) -> str:
        return f"{connection_id}:{section_hash}"

    @staticmethod
    def _redis_key(connection_id: str, section_hash: str) -> str:
        return f"{_REDIS_KEY_PREFIX}:{connection_id}:{section_hash}"

    # ── Sync (memory-only) ──────────────────────────────────────────

    def get_sync(self, connection_id: str, section_hash: str) -> SectionCacheEntry | None:
        """Look up a cached entry in memory only (for sync convert path)."""
        key = self._mem_key(connection_id, section_hash)
        entry = self._memory.get(key)
        if entry is not None:
            # Move to end for LRU freshness (reinsert)
            self._memory.pop(key)
            self._memory[key] = entry
        return entry

    def set_sync(
        self,
        connection_id: str,
        section_hash: str,
        entry: SectionCacheEntry,
    ) -> None:
        """Store an entry in the memory cache (for sync convert path)."""
        key = self._mem_key(connection_id, section_hash)
        # Evict oldest if at capacity
        if key not in self._memory and len(self._memory) >= self._max_memory:
            oldest_key = next(iter(self._memory))
            del self._memory[oldest_key]
        self._memory[key] = entry

    # ── Async (memory + Redis) ──────────────────────────────────────

    async def get(self, connection_id: str, section_hash: str) -> SectionCacheEntry | None:
        """Look up a cached entry — memory first, then Redis."""
        mem_entry = self.get_sync(connection_id, section_hash)
        if mem_entry is not None:
            return mem_entry

        try:
            from app.core.redis import get_redis

            redis = await get_redis()
            raw = await redis.get(self._redis_key(connection_id, section_hash))
            if raw is not None:
                entry = SectionCacheEntry.from_json(raw)
                # Back-fill memory cache
                self.set_sync(connection_id, section_hash, entry)
                return entry
        except (RedisError, OSError, ValueError):
            logger.debug("design_sync.section_cache_redis_read_error", exc_info=True)
        return None

    async def set(
        self,
        connection_id: str,
        section_hash: str,
        entry: SectionCacheEntry,
    ) -> None:
        """Write-through: store in memory and Redis."""
        self.set_sync(connection_id, section_hash, entry)
        try:
            from app.core.redis import get_redis

            redis = await get_redis()
            await redis.set(
                self._redis_key(connection_id, section_hash),
                entry.to_json(),
                ex=self._redis_ttl,
            )
        except (RedisError, OSError):
            logger.debug("design_sync.section_cache_redis_write_error", exc_info=True)

    async def get_many(
        self,
        connection_id: str,
        hashes: dict[str, str],
    ) -> dict[str, SectionCacheEntry]:
        """Batch lookup. *hashes* maps section node_id → section_hash.

        Returns dict of node_id → SectionCacheEntry for cache hits.
        """
        results: dict[str, SectionCacheEntry] = {}
        redis_lookups: list[tuple[str, str]] = []  # (node_id, section_hash)

        for node_id, section_hash in hashes.items():
            mem_entry = self.get_sync(connection_id, section_hash)
            if mem_entry is not None:
                results[node_id] = mem_entry
            else:
                redis_lookups.append((node_id, section_hash))

        if not redis_lookups:
            return results

        try:
            from app.core.redis import get_redis

            redis = await get_redis()
            keys = [self._redis_key(connection_id, sh) for _, sh in redis_lookups]
            values = await redis.mget(keys)
            for (node_id, section_hash), raw in zip(redis_lookups, values, strict=True):
                if raw is not None:
                    entry = SectionCacheEntry.from_json(raw)
                    self.set_sync(connection_id, section_hash, entry)
                    results[node_id] = entry
        except (RedisError, OSError, ValueError):
            logger.debug("design_sync.section_cache_redis_mget_error", exc_info=True)

        return results

    async def invalidate_connection(self, connection_id: str) -> int:
        """Remove all cache entries for a connection. Returns count of entries cleared."""
        # Memory sweep
        prefix = f"{connection_id}:"
        mem_keys = [k for k in self._memory if k.startswith(prefix)]
        for k in mem_keys:
            del self._memory[k]
        cleared = len(mem_keys)

        # Redis SCAN + DEL
        try:
            from app.core.redis import get_redis

            redis = await get_redis()
            pattern = f"{_REDIS_KEY_PREFIX}:{connection_id}:*"
            cursor = 0
            while True:
                scan_result = await redis.scan(cursor=cursor, match=pattern, count=100)  # pyright: ignore[reportUnknownMemberType]
                cursor, keys = scan_result
                if keys:
                    await redis.delete(*keys)
                    cleared += len(keys)
                if cursor == 0:
                    break
        except (RedisError, OSError):
            logger.debug("design_sync.section_cache_redis_invalidate_error", exc_info=True)

        logger.info(
            "design_sync.section_cache_invalidated",
            connection_id=connection_id,
            cleared=cleared,
        )
        return cleared

    def clear_memory(self) -> None:
        """Clear the in-memory cache (for tests)."""
        self._memory.clear()


def get_section_cache() -> SectionCache:
    """Return the module-level section cache singleton, lazily created."""
    global _section_cache
    if _section_cache is None:
        settings = get_settings()
        _section_cache = SectionCache(
            max_memory=settings.design_sync.section_cache_memory_max,
            redis_ttl=settings.design_sync.section_cache_redis_ttl,
        )
    return _section_cache


_section_cache: SectionCache | None = None


def clear_section_cache() -> None:
    """Reset the singleton (for tests)."""
    global _section_cache
    if _section_cache is not None:
        _section_cache.clear_memory()
    _section_cache = None
