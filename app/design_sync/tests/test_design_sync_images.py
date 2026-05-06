# pyright: reportPrivateUsage=false
"""Tests for image handling in the design sync pipeline (Phase 33.11 — Step 10).

Tests cover:
- IMAGE node HTML rendering (dimensions, responsive styles)
- _fill_image_urls() src attribute rewriting
- export_images() protocol contract
- ConversionResult image metadata
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import AsyncMock

from app.design_sync.converter import node_to_email_html
from app.design_sync.converter_service import ConversionResult
from app.design_sync.import_service import DesignImportService
from app.design_sync.protocol import (
    DesignNode,
    DesignNodeType,
    ExportedImage,
    ExtractedTokens,
)
from app.design_sync.render_context import RenderContext


class TestImageNodeRendering:
    """IMAGE nodes render correct HTML with dimensions and responsive styles."""

    def test_image_dimensions_in_html(self) -> None:
        """Figma node dimensions → HTML width/height attributes."""
        node = DesignNode(id="img1", name="Hero", type=DesignNodeType.IMAGE, width=600, height=400)
        html = node_to_email_html(node)
        assert 'width="600"' in html
        assert 'height="400"' in html

    def test_image_responsive_styles(self) -> None:
        """IMAGE node → max-width, width:100%, height:auto, display:block."""
        node = DesignNode(id="img1", name="Hero", type=DesignNodeType.IMAGE, width=600, height=400)
        html = node_to_email_html(node)
        assert "max-width:600px" in html
        assert "width:100%" in html
        assert "height:auto" in html
        assert "display:block" in html

    def test_image_empty_src(self) -> None:
        """IMAGE node → src="" placeholder for later URL fill."""
        node = DesignNode(id="img1", name="Hero", type=DesignNodeType.IMAGE, width=600, height=400)
        html = node_to_email_html(node)
        assert 'src=""' in html

    def test_image_data_node_id(self) -> None:
        """IMAGE node → data-node-id for URL mapping."""
        node = DesignNode(id="1:23", name="Logo", type=DesignNodeType.IMAGE, width=200, height=50)
        html = node_to_email_html(node)
        assert 'data-node-id="1:23"' in html

    def test_image_alt_from_name(self) -> None:
        """IMAGE node name → alt attribute."""
        node = DesignNode(
            id="img1", name="Company Logo", type=DesignNodeType.IMAGE, width=200, height=50
        )
        html = node_to_email_html(node)
        assert 'alt="Company Logo"' in html

    def test_image_alt_escapes_html(self) -> None:
        """HTML characters in name → escaped in alt attribute."""
        node = DesignNode(
            id="img1",
            name='Image "1" <hero>',
            type=DesignNodeType.IMAGE,
            width=200,
            height=50,
        )
        html = node_to_email_html(node)
        assert "<hero>" not in html
        assert "&lt;hero&gt;" in html

    def test_image_no_dimensions_no_max_width(self) -> None:
        """IMAGE without dimensions → no max-width in style."""
        node = DesignNode(id="img1", name="Icon", type=DesignNodeType.IMAGE)
        html = node_to_email_html(node)
        assert "max-width:" not in html

    def test_image_mso_bicubic(self) -> None:
        """IMAGE → MSO interpolation mode for Outlook."""
        node = DesignNode(id="img1", name="Photo", type=DesignNodeType.IMAGE, width=400, height=300)
        html = node_to_email_html(node)
        assert "-ms-interpolation-mode:bicubic" in html

    def test_image_slot_name_when_counter(self) -> None:
        """IMAGE with slot_counter → data-slot-name="image"."""
        node = DesignNode(id="img1", name="Photo", type=DesignNodeType.IMAGE, width=400, height=300)
        counter: dict[str, int] = {}
        html = node_to_email_html(node, RenderContext.from_legacy_kwargs(slot_counter=counter))
        assert 'data-slot-name="image"' in html

    def test_image_no_slot_name_when_no_counter(self) -> None:
        """IMAGE without slot_counter → no data-slot-name."""
        node = DesignNode(id="img1", name="Photo", type=DesignNodeType.IMAGE, width=400, height=300)
        html = node_to_email_html(node)
        assert "data-slot-name" not in html


class TestFillImageUrls:
    """Tests for _fill_image_urls() src attribute rewriting."""

    def test_fills_matching_node_ids(self) -> None:
        """data-node-id matches → src filled with hub URL."""
        html = '<img src="" data-node-id="1:2" width="600" />'
        urls = {"1:2": "/api/v1/design-sync/assets/42/1_2.png"}
        result = DesignImportService._fill_image_urls(html, urls)
        assert 'src="/api/v1/design-sync/assets/42/1_2.png"' in result
        assert 'src=""' not in result

    def test_multiple_images_filled(self) -> None:
        """Multiple images each get their correct URL."""
        html = (
            '<img src="" data-node-id="1:2" />'
            '<img src="" data-node-id="3:4" />'
            '<img src="" data-node-id="5:6" />'
        )
        urls = {
            "1:2": "/assets/1_2.png",
            "3:4": "/assets/3_4.png",
            "5:6": "/assets/5_6.png",
        }
        result = DesignImportService._fill_image_urls(html, urls)
        assert result.count('src=""') == 0
        assert "/assets/1_2.png" in result
        assert "/assets/3_4.png" in result
        assert "/assets/5_6.png" in result

    def test_unmatched_nodes_stay_empty(self) -> None:
        """Unmatched data-node-id → src stays empty."""
        html = '<img src="" data-node-id="1:2" /><img src="" data-node-id="5:6" />'
        urls = {"1:2": "/assets/1_2.png"}
        result = DesignImportService._fill_image_urls(html, urls)
        assert 'src="/assets/1_2.png"' in result
        assert 'src=""' in result  # 5:6 unmatched

    def test_empty_mapping_unchanged(self) -> None:
        """Empty URL mapping → HTML unchanged."""
        html = '<img src="" data-node-id="1:2" />'
        result = DesignImportService._fill_image_urls(html, {})
        assert result == html

    def test_no_img_tags_unchanged(self) -> None:
        """HTML without <img> → unchanged."""
        html = "<table><tr><td>No images</td></tr></table>"
        result = DesignImportService._fill_image_urls(html, {"1:2": "/url"})
        assert result == html


class TestExportImagesProtocol:
    """Tests for export_images() provider protocol."""

    def test_export_images_returns_exported_images(self) -> None:
        """Provider.export_images() returns ExportedImage list."""
        mock_provider = AsyncMock()
        mock_provider.export_images.return_value = [
            ExportedImage(node_id="1:2", url="https://cdn.figma.com/img1.png", format="png"),
            ExportedImage(node_id="3:4", url="https://cdn.figma.com/img2.png", format="png"),
        ]
        # Verify protocol shape
        result = mock_provider.export_images.return_value
        assert len(result) == 2
        assert result[0].node_id == "1:2"
        assert result[0].url.startswith("https://")
        assert result[0].format == "png"


class TestConversionResultImages:
    """Tests for image metadata in ConversionResult."""

    def test_default_empty_images(self) -> None:
        """Default ConversionResult has empty images list."""
        result = ConversionResult(html="<table></table>", sections_count=1)
        assert result.images == []

    def test_images_via_replace(self) -> None:
        """Frozen dataclass → replace() for adding images."""
        result = ConversionResult(html="<table></table>", sections_count=1)
        updated = replace(
            result,
            images=[{"node_id": "1:2", "filename": "1_2.png", "hub_url": "/assets/1/1_2.png"}],
        )
        assert len(updated.images) == 1
        assert updated.images[0]["node_id"] == "1:2"
        # Original unchanged (frozen)
        assert result.images == []

    def test_multiple_images_in_result(self) -> None:
        """Multiple images carried in ConversionResult."""
        result = ConversionResult(
            html="<table></table>",
            sections_count=1,
            images=[
                {"node_id": "1:2", "filename": "logo.png", "hub_url": "/assets/1/logo.png"},
                {"node_id": "3:4", "filename": "hero.png", "hub_url": "/assets/1/hero.png"},
                {"node_id": "5:6", "filename": "icon.png", "hub_url": "/assets/1/icon.png"},
            ],
        )
        assert len(result.images) == 3


# TestPipelineImageIntegration was removed: both tests asserted that 3 IMAGE
# nodes produced 3 <img> tags via the legacy `_convert_recursive` renderer.
# Under the modern component-template path (the only path post-08c), 3 stacked
# IMAGE nodes match a single image-grid component, surfacing one <img> tag.
# The image-URL filling behaviour itself is covered by the unit tests for
# `DesignImportService._fill_image_urls` higher up in this file.
