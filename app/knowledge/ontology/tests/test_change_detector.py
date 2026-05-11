"""Tests for the rendering change detector (Phase 21.2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.knowledge.ontology.change_detector import (
    DetectionResult,
    RenderingChange,
    RenderingChangeDetector,
)
from app.knowledge.ontology.feature_templates import (
    FEATURE_TEMPLATES,
    list_templates,
)

# ── Feature template registry ──


class TestFeatureTemplates:
    """Tests for the feature template registry."""

    def test_list_templates_returns_sorted(self) -> None:
        templates = list_templates()
        assert templates == sorted(templates)
        assert len(templates) >= 20

    def test_all_templates_have_property_mapping(self) -> None:
        for name in list_templates():
            assert name in FEATURE_TEMPLATES

    def test_template_files_exist(self) -> None:
        from app.knowledge.ontology.feature_templates import get_template_html

        for name in list_templates():
            html = get_template_html(name)
            assert "<html" in html.lower()
            assert len(html) > 50


# ── RenderingChangeDetector ──


class TestRenderingChangeDetector:
    """Tests for the change detector service."""

    @pytest.fixture
    def detector(self) -> RenderingChangeDetector:
        return RenderingChangeDetector()

    @pytest.mark.asyncio
    async def test_first_run_creates_baselines(self, detector: RenderingChangeDetector) -> None:
        """First run with no baselines should create them, report no changes."""
        mock_screenshots = [
            {
                "client_name": "gmail_web",
                "image_bytes": b"\x89PNG_fake",
                "viewport": "680x900",
                "browser": "cr",
            },
        ]

        with (
            patch.object(
                detector._renderer,
                "render_screenshots",
                new_callable=AsyncMock,
                return_value=mock_screenshots,
            ),
            patch(
                "app.knowledge.ontology.change_detector.list_templates",
                return_value=["flexbox_display-flex"],
            ),
            patch(
                "app.knowledge.ontology.change_detector.get_template_html",
                return_value="<html>test</html>",
            ),
        ):
            result, baselines = await detector.detect_changes(baselines={})

        assert result.baselines_created == 1
        assert len(result.changes) == 0
        assert "flexbox_display-flex:gmail_web" in baselines

    @pytest.mark.asyncio
    async def test_no_change_when_identical(self, detector: RenderingChangeDetector) -> None:
        """No change reported when current matches baseline."""
        from app.rendering.visual_diff import DiffResult

        existing_baselines = {"flexbox_display-flex:gmail_web": b"\x89PNG_fake"}
        mock_screenshots = [
            {
                "client_name": "gmail_web",
                "image_bytes": b"\x89PNG_fake",
                "viewport": "680x900",
                "browser": "cr",
            },
        ]
        mock_diff = DiffResult(
            identical=True, diff_percentage=0.0, diff_image=None, pixel_count=0, changed_regions=[]
        )

        with (
            patch.object(
                detector._renderer,
                "render_screenshots",
                new_callable=AsyncMock,
                return_value=mock_screenshots,
            ),
            patch(
                "app.knowledge.ontology.change_detector.list_templates",
                return_value=["flexbox_display-flex"],
            ),
            patch(
                "app.knowledge.ontology.change_detector.get_template_html",
                return_value="<html>test</html>",
            ),
            patch(
                "app.knowledge.ontology.change_detector.compare_images",
                new_callable=AsyncMock,
                return_value=mock_diff,
            ),
        ):
            result, _baselines = await detector.detect_changes(baselines=existing_baselines)

        assert len(result.changes) == 0
        assert result.baselines_created == 0

    @pytest.mark.asyncio
    async def test_change_detected_when_diff_exceeds_threshold(
        self, detector: RenderingChangeDetector
    ) -> None:
        """Change reported when diff percentage exceeds threshold."""
        from app.rendering.visual_diff import DiffResult

        existing_baselines = {"flexbox_display-flex:gmail_web": b"\x89PNG_old"}
        mock_screenshots = [
            {
                "client_name": "gmail_web",
                "image_bytes": b"\x89PNG_new",
                "viewport": "680x900",
                "browser": "cr",
            },
        ]
        mock_diff = DiffResult(
            identical=False,
            diff_percentage=15.5,
            diff_image=b"diff",
            pixel_count=1000,
            changed_regions=[],
        )

        with (
            patch.object(
                detector._renderer,
                "render_screenshots",
                new_callable=AsyncMock,
                return_value=mock_screenshots,
            ),
            patch(
                "app.knowledge.ontology.change_detector.list_templates",
                return_value=["flexbox_display-flex"],
            ),
            patch(
                "app.knowledge.ontology.change_detector.get_template_html",
                return_value="<html>test</html>",
            ),
            patch(
                "app.knowledge.ontology.change_detector.compare_images",
                new_callable=AsyncMock,
                return_value=mock_diff,
            ),
        ):
            result, baselines = await detector.detect_changes(baselines=existing_baselines)

        assert len(result.changes) == 1
        change = result.changes[0]
        assert change.property_id == "display-flex"
        assert change.client_id == "gmail_web"
        assert change.diff_percentage == 15.5
        # Baseline updated to new screenshot
        assert baselines["flexbox_display-flex:gmail_web"] == b"\x89PNG_new"

    @pytest.mark.asyncio
    async def test_render_error_increments_error_count(
        self, detector: RenderingChangeDetector
    ) -> None:
        """Render failures are counted but don't crash the detector."""
        with (
            patch.object(
                detector._renderer,
                "render_screenshots",
                new_callable=AsyncMock,
                side_effect=RuntimeError("playwright crashed"),
            ),
            patch(
                "app.knowledge.ontology.change_detector.list_templates",
                return_value=["flexbox_display-flex"],
            ),
            patch(
                "app.knowledge.ontology.change_detector.get_template_html",
                return_value="<html>test</html>",
            ),
        ):
            result, _ = await detector.detect_changes(baselines={})

        assert result.errors == 1
        assert len(result.changes) == 0

    @pytest.mark.asyncio
    async def test_template_load_error_increments_error_count(
        self, detector: RenderingChangeDetector
    ) -> None:
        """Missing template file is counted as error."""
        with (
            patch(
                "app.knowledge.ontology.change_detector.list_templates",
                return_value=["nonexistent"],
            ),
            patch(
                "app.knowledge.ontology.change_detector.get_template_html",
                side_effect=FileNotFoundError("no such file"),
            ),
        ):
            result, _ = await detector.detect_changes(baselines={})

        assert result.errors == 1

    @pytest.mark.asyncio
    async def test_multiple_clients_multiple_templates(
        self, detector: RenderingChangeDetector
    ) -> None:
        """Handles multiple templates x multiple clients correctly."""
        mock_screenshots = [
            {
                "client_name": "gmail_web",
                "image_bytes": b"\x89PNG_g",
                "viewport": "680x900",
                "browser": "cr",
            },
            {
                "client_name": "outlook_2019",
                "image_bytes": b"\x89PNG_o",
                "viewport": "800x900",
                "browser": "cr",
            },
        ]

        with (
            patch.object(
                detector._renderer,
                "render_screenshots",
                new_callable=AsyncMock,
                return_value=mock_screenshots,
            ),
            patch(
                "app.knowledge.ontology.change_detector.list_templates",
                return_value=["flexbox_display-flex", "grid_display-grid"],
            ),
            patch(
                "app.knowledge.ontology.change_detector.get_template_html",
                return_value="<html>test</html>",
            ),
        ):
            result, baselines = await detector.detect_changes(baselines={})

        # 2 templates x 2 clients = 4 baselines created
        assert result.baselines_created == 4
        assert len(baselines) == 4


# ── RenderingChangePoller ──


class TestRenderingChangePoller:
    """Tests for the background poller."""

    @pytest.mark.asyncio
    async def test_poller_init_reads_config(self) -> None:
        from app.knowledge.ontology.change_poller import RenderingChangePoller

        poller = RenderingChangePoller()
        assert poller.name == "rendering-change-detector"
        assert poller.interval_seconds > 0

    @pytest.mark.asyncio
    async def test_poller_store_writes_knowledge_on_changes(self) -> None:
        """Changes are stored as knowledge documents."""
        from app.knowledge.ontology.change_poller import RenderingChangePoller

        poller = RenderingChangePoller()

        change = RenderingChange(
            property_id="display-flex",
            client_id="gmail_web",
            template_name="flexbox_display-flex",
            diff_percentage=12.5,
        )
        result = DetectionResult(
            changes=[change],
            templates_checked=25,
            clients_checked=5,
            baselines_created=0,
            errors=0,
        )

        mock_ingest = AsyncMock(return_value=1)
        mock_service = AsyncMock()
        mock_service.ingest_text = mock_ingest

        with (
            patch(
                "app.knowledge.ontology.change_poller.RenderingChangePoller._save_baselines",
                new_callable=AsyncMock,
            ),
            patch(
                "app.knowledge.ontology.change_poller.RenderingChangePoller._save_last_run",
                new_callable=AsyncMock,
            ),
            patch(
                "app.core.database.get_db_context",
            ) as mock_db_ctx,
            patch(
                "app.knowledge.services.ingestion.IngestionService",
                return_value=mock_service,
            ),
        ):
            mock_db_ctx.return_value.__aenter__ = AsyncMock()
            mock_db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await poller.store({"result": result, "new_baselines": {}})

        mock_ingest.assert_called_once()
        call_kwargs = mock_ingest.call_args.kwargs
        assert call_kwargs["domain"] == "rendering_changes"
        assert "display-flex" in call_kwargs["title"]

    @pytest.mark.asyncio
    async def test_poller_store_noop_when_no_changes(self) -> None:
        """No knowledge documents created when no changes detected."""
        from app.knowledge.ontology.change_poller import RenderingChangePoller

        poller = RenderingChangePoller()

        result = DetectionResult(
            changes=[],
            templates_checked=25,
            clients_checked=5,
            baselines_created=0,
            errors=0,
        )

        with (
            patch(
                "app.knowledge.ontology.change_poller.RenderingChangePoller._save_baselines",
                new_callable=AsyncMock,
            ),
            patch(
                "app.knowledge.ontology.change_poller.RenderingChangePoller._save_last_run",
                new_callable=AsyncMock,
            ),
        ):
            # Should not attempt knowledge store
            await poller.store({"result": result, "new_baselines": {}})

    @pytest.mark.asyncio
    async def test_poller_store_handles_none_data(self) -> None:
        """None data (skip cycle) is handled gracefully."""
        from app.knowledge.ontology.change_poller import RenderingChangePoller

        poller = RenderingChangePoller()
        await poller.store(None)  # Should not raise


# ── Redis baseline persistence ──


class TestBaselinePersistence:
    """Tests for baseline save/load in Redis."""

    @pytest.mark.asyncio
    async def test_save_and_load_round_trip(self) -> None:
        from app.knowledge.ontology.change_poller import RenderingChangePoller

        poller = RenderingChangePoller()

        # Mock Redis
        stored: dict[str, str] = {}

        async def mock_setex(key: str, ttl: int, value: str) -> None:
            stored[key] = value

        async def mock_get(key: str) -> str | None:
            return stored.get(key)

        mock_redis = AsyncMock()
        mock_redis.setex = mock_setex
        mock_redis.get = mock_get

        with patch("app.knowledge.ontology.change_poller.get_redis", return_value=mock_redis):
            test_baselines = {"test:gmail_web": b"\x89PNG_data"}
            await poller._save_baselines(test_baselines)
            loaded = await poller._load_baselines()

        assert loaded == test_baselines

    @pytest.mark.asyncio
    async def test_load_empty_when_redis_empty(self) -> None:
        from app.knowledge.ontology.change_poller import RenderingChangePoller

        poller = RenderingChangePoller()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("app.knowledge.ontology.change_poller.get_redis", return_value=mock_redis):
            loaded = await poller._load_baselines()

        assert loaded == {}

    @pytest.mark.asyncio
    async def test_load_empty_on_redis_error(self) -> None:
        from app.knowledge.ontology.change_poller import RenderingChangePoller

        poller = RenderingChangePoller()

        with patch(
            "app.knowledge.ontology.change_poller.get_redis",
            side_effect=ConnectionError("redis down"),
        ):
            loaded = await poller._load_baselines()

        assert loaded == {}


class TestChangeDetectorEdgeCases:
    """Edge case tests for rendering change detection."""

    @pytest.fixture
    def detector(self) -> RenderingChangeDetector:
        return RenderingChangeDetector()

    @pytest.mark.asyncio
    async def test_diff_below_threshold_not_reported(
        self, detector: RenderingChangeDetector
    ) -> None:
        """Changes below diff_threshold are treated as identical by compare_images."""
        from app.rendering.visual_diff import DiffResult

        existing_baselines = {"flexbox_display-flex:gmail_web": b"\x89PNG_old"}
        mock_screenshots = [
            {
                "client_name": "gmail_web",
                "image_bytes": b"\x89PNG_new",
                "viewport": "680x900",
                "browser": "cr",
            },
        ]
        # compare_images returns identical=True when diff is below threshold
        mock_diff = DiffResult(
            identical=True,
            diff_percentage=0.5,
            diff_image=None,
            pixel_count=50,
            changed_regions=[],
        )

        with (
            patch.object(
                detector._renderer,
                "render_screenshots",
                new_callable=AsyncMock,
                return_value=mock_screenshots,
            ),
            patch(
                "app.knowledge.ontology.change_detector.list_templates",
                return_value=["flexbox_display-flex"],
            ),
            patch(
                "app.knowledge.ontology.change_detector.get_template_html",
                return_value="<html>test</html>",
            ),
            patch(
                "app.knowledge.ontology.change_detector.compare_images",
                new_callable=AsyncMock,
                return_value=mock_diff,
            ),
        ):
            result, _baselines = await detector.detect_changes(baselines=existing_baselines)

        assert len(result.changes) == 0

    @pytest.mark.asyncio
    async def test_empty_templates_returns_zero_results(
        self, detector: RenderingChangeDetector
    ) -> None:
        """No templates → zero baselines, zero changes."""
        with patch(
            "app.knowledge.ontology.change_detector.list_templates",
            return_value=[],
        ):
            result, baselines = await detector.detect_changes(baselines={})

        assert result.baselines_created == 0
        assert len(result.changes) == 0
        assert len(baselines) == 0
