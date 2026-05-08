# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false
"""Tests for section-level conversion cache (Phase 35.10)."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.rate_limit import limiter
from app.design_sync.converter_service import DesignConverterService
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExtractedColor,
    ExtractedTokens,
    ExtractedTypography,
)
from app.design_sync.section_cache import (
    SectionCache,
    SectionCacheEntry,
    clear_section_cache,
    compute_section_hash,
    get_section_cache,
)
from app.main import app

# ── Factories ──


def _make_section(
    section_type: EmailSectionType = EmailSectionType.CONTENT,
    *,
    node_id: str = "frame_1",
    node_name: str = "Section",
    texts: list[TextBlock] | None = None,
    images: list[ImagePlaceholder] | None = None,
    buttons: list[ButtonElement] | None = None,
    bg_color: str | None = None,
    height: float | None = 200.0,
    width: float | None = 600.0,
) -> EmailSection:
    return EmailSection(
        section_type=section_type,
        node_id=node_id,
        node_name=node_name,
        texts=texts or [],
        images=images or [],
        buttons=buttons or [],
        column_layout=ColumnLayout.SINGLE,
        column_count=1,
        height=height,
        width=width,
        bg_color=bg_color,
    )


def _make_tokens() -> ExtractedTokens:
    return ExtractedTokens(
        colors=[
            ExtractedColor(name="Primary", hex="#333333"),
            ExtractedColor(name="Background", hex="#ffffff"),
            ExtractedColor(name="Text", hex="#000000"),
        ],
        typography=[
            ExtractedTypography(
                name="Heading", family="Inter", weight="700", size=24.0, line_height=32.0
            ),
            ExtractedTypography(
                name="Body", family="Inter", weight="400", size=16.0, line_height=24.0
            ),
        ],
    )


def _make_entry(html: str = "<table><tr><td>cached</td></tr></table>") -> SectionCacheEntry:
    return SectionCacheEntry(html=html, images=(), generated_at="2026-03-27T12:00:00+00:00")


def _make_user(role: str = "admin") -> User:
    user = User(email="test@example.com", hashed_password="x", role=role)
    user.id = 1
    return user


def _make_structure() -> DesignFileStructure:
    return DesignFileStructure(
        file_name="Test",
        pages=[
            DesignNode(
                id="page1",
                name="Page",
                type=DesignNodeType.PAGE,
                children=[
                    DesignNode(
                        id="frame1",
                        name="Content",
                        type=DesignNodeType.FRAME,
                        width=600.0,
                        height=400.0,
                        children=[
                            DesignNode(
                                id="text1",
                                name="Body Text",
                                type=DesignNodeType.TEXT,
                                text_content="Hello",
                                width=560.0,
                                height=24.0,
                                x=20.0,
                                y=20.0,
                            )
                        ],
                    )
                ],
            )
        ],
    )


# ── Hash Computation ──


class TestComputeSectionHash:
    def test_deterministic(self) -> None:
        """Same inputs produce same hash."""
        section = _make_section()
        tokens = _make_tokens()
        h1 = compute_section_hash(section, tokens, container_width=600)
        h2 = compute_section_hash(section, tokens, container_width=600)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_different_text_content(self) -> None:
        """Different text content produces different hash."""
        tokens = _make_tokens()
        s1 = _make_section(texts=[TextBlock(node_id="t1", content="Hello")])
        s2 = _make_section(texts=[TextBlock(node_id="t1", content="World")])
        h1 = compute_section_hash(s1, tokens, container_width=600)
        h2 = compute_section_hash(s2, tokens, container_width=600)
        assert h1 != h2

    def test_different_bg_color(self) -> None:
        """Different background color produces different hash."""
        tokens = _make_tokens()
        s1 = _make_section(bg_color="#ffffff")
        s2 = _make_section(bg_color="#000000")
        assert compute_section_hash(s1, tokens, container_width=600) != compute_section_hash(
            s2, tokens, container_width=600
        )

    def test_different_container_width(self) -> None:
        """Different container width produces different hash."""
        section = _make_section()
        tokens = _make_tokens()
        h1 = compute_section_hash(section, tokens, container_width=600)
        h2 = compute_section_hash(section, tokens, container_width=700)
        assert h1 != h2

    def test_different_target_clients(self) -> None:
        """Different target clients produce different hash."""
        section = _make_section()
        tokens = _make_tokens()
        h1 = compute_section_hash(section, tokens, container_width=600, target_clients=["gmail"])
        h2 = compute_section_hash(section, tokens, container_width=600, target_clients=["outlook"])
        assert h1 != h2

    def test_float_rounding(self) -> None:
        """Floats differing only beyond 2dp produce same hash."""
        tokens = _make_tokens()
        s1 = _make_section(height=200.001)
        s2 = _make_section(height=200.002)
        assert compute_section_hash(s1, tokens, container_width=600) == compute_section_hash(
            s2, tokens, container_width=600
        )

    def test_target_clients_order_irrelevant(self) -> None:
        """Target clients are sorted, so order doesn't matter."""
        section = _make_section()
        tokens = _make_tokens()
        h1 = compute_section_hash(
            section, tokens, container_width=600, target_clients=["gmail", "outlook"]
        )
        h2 = compute_section_hash(
            section, tokens, container_width=600, target_clients=["outlook", "gmail"]
        )
        assert h1 == h2


# ── SectionCacheEntry Serialization ──


class TestSectionCacheEntry:
    def test_roundtrip_json(self) -> None:
        """to_json/from_json roundtrip preserves data."""
        entry = SectionCacheEntry(
            html="<table><tr><td>Hi</td></tr></table>",
            images=({"node_id": "img1", "url": "https://example.com/img.png"},),
            generated_at="2026-03-27T10:00:00+00:00",
        )
        restored = SectionCacheEntry.from_json(entry.to_json())
        assert restored.html == entry.html
        assert restored.images == entry.images
        assert restored.generated_at == entry.generated_at

    def test_from_json_malformed_raises_value_error(self) -> None:
        """from_json raises ValueError on missing keys or invalid JSON."""
        with pytest.raises(ValueError, match="Malformed cache entry"):
            SectionCacheEntry.from_json('{"bad": true}')

    def test_from_json_invalid_json_raises_value_error(self) -> None:
        """from_json raises ValueError on non-JSON input."""
        with pytest.raises(ValueError, match="Malformed cache entry"):
            SectionCacheEntry.from_json("not json at all")


# ── Memory Cache ──


class TestSectionCacheMemory:
    def test_set_and_get(self) -> None:
        """set_sync + get_sync roundtrip."""
        cache = SectionCache(max_memory=10, redis_ttl=60)
        entry = _make_entry()
        cache.set_sync("conn1", "hash_abc", entry)
        result = cache.get_sync("conn1", "hash_abc")
        assert result is not None
        assert result.html == entry.html

    def test_miss_returns_none(self) -> None:
        """get_sync for unknown key returns None."""
        cache = SectionCache(max_memory=10, redis_ttl=60)
        assert cache.get_sync("conn1", "nonexistent") is None

    def test_lru_eviction(self) -> None:
        """Oldest entry is evicted when cache is full."""
        cache = SectionCache(max_memory=3, redis_ttl=60)
        cache.set_sync("c", "h1", _make_entry("a"))
        cache.set_sync("c", "h2", _make_entry("b"))
        cache.set_sync("c", "h3", _make_entry("c"))
        # At capacity — adding h4 should evict h1
        cache.set_sync("c", "h4", _make_entry("d"))
        assert cache.get_sync("c", "h1") is None
        assert cache.get_sync("c", "h4") is not None

    def test_clear_memory(self) -> None:
        """clear_memory empties the cache."""
        cache = SectionCache(max_memory=10, redis_ttl=60)
        cache.set_sync("c", "h1", _make_entry())
        cache.clear_memory()
        assert cache.get_sync("c", "h1") is None

    @pytest.mark.asyncio
    async def test_invalidate_connection_memory(self) -> None:
        """invalidate_connection removes only matching connection entries."""
        cache = SectionCache(max_memory=10, redis_ttl=60)
        cache.set_sync("conn1", "h1", _make_entry("a"))
        cache.set_sync("conn1", "h2", _make_entry("b"))
        cache.set_sync("conn2", "h3", _make_entry("c"))

        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [])

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            cleared = await cache.invalidate_connection("conn1")

        assert cleared >= 2  # At least 2 memory entries
        assert cache.get_sync("conn1", "h1") is None
        assert cache.get_sync("conn1", "h2") is None
        assert cache.get_sync("conn2", "h3") is not None


# ── Async Cache (Redis mocked) ──


class TestSectionCacheAsync:
    @pytest.mark.asyncio
    async def test_set_writes_to_redis(self) -> None:
        """Async set stores in memory AND calls redis.set with TTL."""
        cache = SectionCache(max_memory=10, redis_ttl=3600)
        entry = _make_entry()
        mock_redis = AsyncMock()

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            await cache.set("conn1", "hash_abc", entry)

        # Memory populated
        assert cache.get_sync("conn1", "hash_abc") is not None
        # Redis called
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "section_cache:conn1:hash_abc"
        assert call_args[1]["ex"] == 3600

    @pytest.mark.asyncio
    async def test_get_from_redis_on_memory_miss(self) -> None:
        """Async get falls back to Redis when memory misses, back-fills memory."""
        cache = SectionCache(max_memory=10, redis_ttl=3600)
        entry = _make_entry("<table>from redis</table>")
        mock_redis = AsyncMock()
        mock_redis.get.return_value = entry.to_json()

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            result = await cache.get("conn1", "hash_xyz")

        assert result is not None
        assert result.html == "<table>from redis</table>"
        # Back-filled into memory
        assert cache.get_sync("conn1", "hash_xyz") is not None

    @pytest.mark.asyncio
    async def test_redis_failure_graceful(self) -> None:
        """Redis error doesn't raise — falls back to memory-only."""
        from redis.exceptions import ConnectionError as RedisConnectionError

        cache = SectionCache(max_memory=10, redis_ttl=3600)
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = RedisConnectionError("connection refused")

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            result = await cache.get("conn1", "hash_xyz")

        assert result is None  # Graceful fallback

    @pytest.mark.asyncio
    async def test_get_many_batch(self) -> None:
        """get_many returns cached entries from memory + Redis."""
        cache = SectionCache(max_memory=10, redis_ttl=3600)
        # Pre-populate one in memory
        entry_mem = _make_entry("<table>mem</table>")
        cache.set_sync("conn1", "hash_a", entry_mem)

        entry_redis = _make_entry("<table>redis</table>")
        mock_redis = AsyncMock()
        mock_redis.mget.return_value = [entry_redis.to_json()]

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            results = await cache.get_many(
                "conn1",
                {"node_a": "hash_a", "node_b": "hash_b"},
            )

        assert "node_a" in results
        assert results["node_a"].html == "<table>mem</table>"
        assert "node_b" in results
        assert results["node_b"].html == "<table>redis</table>"

    @pytest.mark.asyncio
    async def test_invalidate_connection_redis(self) -> None:
        """invalidate_connection scans + deletes Redis keys."""
        cache = SectionCache(max_memory=10, redis_ttl=3600)
        cache.set_sync("conn1", "h1", _make_entry())

        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, ["section_cache:conn1:h1", "section_cache:conn1:h2"])
        mock_redis.delete.return_value = 2

        with patch("app.core.redis.get_redis", return_value=mock_redis):
            cleared = await cache.invalidate_connection("conn1")

        assert cleared >= 3  # 1 memory + 2 redis
        mock_redis.delete.assert_called_once()


# ── Singleton ──


class TestSectionCacheSingleton:
    def test_get_section_cache_singleton(self) -> None:
        """get_section_cache returns same instance on repeated calls."""
        clear_section_cache()
        c1 = get_section_cache()
        c2 = get_section_cache()
        assert c1 is c2
        clear_section_cache()

    def test_clear_section_cache_resets(self) -> None:
        """clear_section_cache resets the singleton."""
        clear_section_cache()
        c1 = get_section_cache()
        clear_section_cache()
        c2 = get_section_cache()
        assert c1 is not c2
        clear_section_cache()


# ── Converter Integration ──


class TestConverterCacheIntegration:
    def test_convert_with_cache_populates(self) -> None:
        """convert() with connection_id populates the memory cache."""
        clear_section_cache()
        service = DesignConverterService()
        structure = _make_structure()
        tokens = _make_tokens()

        document = EmailDesignDocument.from_legacy(structure, tokens)
        result = service.convert_document(
            document,
            use_components=True,
            connection_id="conn_test",
        )

        assert result.sections_count >= 1
        assert result.html != ""
        # Cache should have been populated — second call should hit
        result2 = service.convert_document(
            document,
            use_components=True,
            connection_id="conn_test",
        )
        assert result2.cache_hit_rate is not None
        assert result2.cache_hit_rate > 0.0
        clear_section_cache()

    def test_convert_without_connection_id_no_cache(self) -> None:
        """convert() without connection_id skips caching."""
        clear_section_cache()
        service = DesignConverterService()
        structure = _make_structure()
        tokens = _make_tokens()

        document = EmailDesignDocument.from_legacy(structure, tokens)
        result = service.convert_document(document, use_components=True)
        assert result.cache_hit_rate is None
        clear_section_cache()

    def test_convert_cache_disabled(self) -> None:
        """convert() with cache disabled skips caching even with connection_id."""
        clear_section_cache()
        service = DesignConverterService()
        structure = _make_structure()
        tokens = _make_tokens()

        with patch("app.design_sync.converter_service.get_settings") as mock_settings:
            mock_cfg = mock_settings.return_value
            mock_cfg.design_sync.section_cache_enabled = False
            mock_cfg.design_sync.section_cache_memory_max = 500
            mock_cfg.design_sync.section_cache_redis_ttl = 3600
            mock_cfg.design_sync.sibling_detection_enabled = False
            mock_cfg.design_sync.custom_component_enabled = False
            mock_cfg.design_sync.custom_component_max_per_email = 0

            document = EmailDesignDocument.from_legacy(structure, tokens)
            result = service.convert_document(
                document,
                use_components=True,
                connection_id="conn_test",
            )

        assert result.cache_hit_rate is None
        clear_section_cache()

    def test_convert_changed_section_partial_hit(self) -> None:
        """Changing one section's content causes a cache miss for that section."""
        clear_section_cache()
        service = DesignConverterService()
        tokens = _make_tokens()

        # Structure with 2 frames
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="page1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="frame1",
                            name="Header",
                            type=DesignNodeType.FRAME,
                            width=600.0,
                            height=100.0,
                            y=0.0,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="Logo",
                                    type=DesignNodeType.TEXT,
                                    text_content="Brand",
                                    width=200.0,
                                    height=24.0,
                                    x=20.0,
                                    y=20.0,
                                ),
                                DesignNode(
                                    id="img1",
                                    name="Logo Image",
                                    type=DesignNodeType.IMAGE,
                                    width=120.0,
                                    height=40.0,
                                    x=200.0,
                                    y=10.0,
                                ),
                            ],
                        ),
                        DesignNode(
                            id="frame2",
                            name="Content",
                            type=DesignNodeType.FRAME,
                            width=600.0,
                            height=300.0,
                            y=100.0,
                            children=[
                                DesignNode(
                                    id="t2",
                                    name="Body",
                                    type=DesignNodeType.TEXT,
                                    text_content="Original body",
                                    width=560.0,
                                    height=24.0,
                                    x=20.0,
                                    y=20.0,
                                )
                            ],
                        ),
                    ],
                )
            ],
        )

        document = EmailDesignDocument.from_legacy(structure, tokens)
        # First conversion — all misses
        r1 = service.convert_document(document, use_components=True, connection_id="conn_partial")
        assert r1.sections_count >= 2
        assert r1.cache_hit_rate == 0.0

        # Second conversion — same input — all hits
        r2 = service.convert_document(document, use_components=True, connection_id="conn_partial")
        assert r2.cache_hit_rate == 1.0

        # Modify text in frame2
        structure_modified = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="page1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        structure.pages[0].children[0],  # Same header
                        DesignNode(
                            id="frame2",
                            name="Content",
                            type=DesignNodeType.FRAME,
                            width=600.0,
                            height=300.0,
                            y=100.0,
                            children=[
                                DesignNode(
                                    id="t2",
                                    name="Body",
                                    type=DesignNodeType.TEXT,
                                    text_content="Modified body",
                                    width=560.0,
                                    height=24.0,
                                    x=20.0,
                                    y=20.0,
                                )
                            ],
                        ),
                    ],
                )
            ],
        )

        # Third conversion — partial hit (header cached, content re-rendered)
        document_modified = EmailDesignDocument.from_legacy(structure_modified, tokens)
        r3 = service.convert_document(
            document_modified, use_components=True, connection_id="conn_partial"
        )
        assert r3.cache_hit_rate is not None
        assert 0.0 < r3.cache_hit_rate < 1.0
        clear_section_cache()

    def test_convert_different_target_clients_full_miss(self) -> None:
        """Changing target_clients causes all cache misses (different hashes)."""
        clear_section_cache()
        service = DesignConverterService()
        structure = _make_structure()
        tokens = _make_tokens()

        document = EmailDesignDocument.from_legacy(structure, tokens)
        r1 = service.convert_document(
            document,
            use_components=True,
            connection_id="conn_tc",
            target_clients=["gmail"],
        )
        assert r1.cache_hit_rate == 0.0

        # Same structure, different target_clients
        r2 = service.convert_document(
            document,
            use_components=True,
            connection_id="conn_tc",
            target_clients=["outlook"],
        )
        assert r2.cache_hit_rate == 0.0  # Full miss
        clear_section_cache()


# ── Admin Endpoint ──

BASE = "/api/v1/design-sync"


@pytest.fixture(autouse=True)
def _disable_rate_limit() -> Generator[None]:
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture
def _auth_admin() -> Generator[None]:
    user = _make_user("admin")
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def _auth_viewer() -> Generator[None]:
    user = _make_user("viewer")
    app.dependency_overrides[get_current_user] = lambda: user
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.usefixtures("_auth_admin")
def test_clear_cache_endpoint(client: TestClient) -> None:
    """DELETE /connections/{id}/cache clears entries and returns count."""
    clear_section_cache()
    cache = get_section_cache()
    cache.set_sync("42", "h1", _make_entry())
    cache.set_sync("42", "h2", _make_entry())

    with patch("app.core.redis.get_redis", new_callable=AsyncMock) as mock_get:
        mock_redis = AsyncMock()
        mock_redis.scan.return_value = (0, [])
        mock_get.return_value = mock_redis

        resp = client.delete(f"{BASE}/connections/42/cache")

    assert resp.status_code == 200
    body = resp.json()
    assert body["cleared_entries"] >= 2
    clear_section_cache()


@pytest.mark.usefixtures("_auth_viewer")
def test_clear_cache_viewer_forbidden(client: TestClient) -> None:
    """Viewer role gets 403 on cache clear (requires admin)."""
    resp = client.delete(f"{BASE}/connections/1/cache")
    assert resp.status_code == 403


def test_clear_cache_unauthenticated(client: TestClient) -> None:
    """Unauthenticated request returns 401."""
    app.dependency_overrides.clear()
    resp = client.delete(f"{BASE}/connections/1/cache")
    assert resp.status_code == 401


# ── Phase 38.4 Tests ──


class TestHashIncludesTextStyling:
    """Bug 25: Cache hash must include text styling fields."""

    def test_different_font_size_different_hash(self) -> None:
        tokens = _make_tokens()
        s1 = _make_section(texts=[TextBlock(node_id="t1", content="Hi", font_size=16.0)])
        s2 = _make_section(texts=[TextBlock(node_id="t1", content="Hi", font_size=24.0)])
        h1 = compute_section_hash(s1, tokens, container_width=600)
        h2 = compute_section_hash(s2, tokens, container_width=600)
        assert h1 != h2

    def test_different_font_weight_different_hash(self) -> None:
        tokens = _make_tokens()
        s1 = _make_section(texts=[TextBlock(node_id="t1", content="Hi", font_weight=400)])
        s2 = _make_section(texts=[TextBlock(node_id="t1", content="Hi", font_weight=700)])
        h1 = compute_section_hash(s1, tokens, container_width=600)
        h2 = compute_section_hash(s2, tokens, container_width=600)
        assert h1 != h2

    def test_different_font_family_different_hash(self) -> None:
        tokens = _make_tokens()
        s1 = _make_section(texts=[TextBlock(node_id="t1", content="Hi", font_family="Arial")])
        s2 = _make_section(texts=[TextBlock(node_id="t1", content="Hi", font_family="Georgia")])
        h1 = compute_section_hash(s1, tokens, container_width=600)
        h2 = compute_section_hash(s2, tokens, container_width=600)
        assert h1 != h2

    def test_different_is_heading_different_hash(self) -> None:
        tokens = _make_tokens()
        s1 = _make_section(texts=[TextBlock(node_id="t1", content="Hi", is_heading=False)])
        s2 = _make_section(texts=[TextBlock(node_id="t1", content="Hi", is_heading=True)])
        h1 = compute_section_hash(s1, tokens, container_width=600)
        h2 = compute_section_hash(s2, tokens, container_width=600)
        assert h1 != h2

    def test_same_styling_same_hash(self) -> None:
        tokens = _make_tokens()
        s1 = _make_section(
            texts=[TextBlock(node_id="t1", content="Hi", font_size=16.0, font_weight=400)]
        )
        s2 = _make_section(
            texts=[TextBlock(node_id="t1", content="Hi", font_size=16.0, font_weight=400)]
        )
        h1 = compute_section_hash(s1, tokens, container_width=600)
        h2 = compute_section_hash(s2, tokens, container_width=600)
        assert h1 == h2
