"""Tests for per-email token scoping (Phase 49.6).

When a Figma file contains multiple email designs, token extraction should
scope to the target frame's subtree when a node_id is provided.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.design_sync.figma.raw_types import RawFigmaNode
from app.design_sync.figma.service import FigmaDesignSyncService, _find_subtree

# ── Test Data Factories ──


def _solid_fill(r: float, g: float, b: float, a: float = 1.0) -> dict[str, Any]:
    return {"type": "SOLID", "color": {"r": r, "g": g, "b": b, "a": a}}


def _text_node(
    family: str, size: float, fill_r: float, fill_g: float, fill_b: float
) -> dict[str, Any]:
    return {
        "type": "TEXT",
        "style": {
            "fontFamily": family,
            "fontWeight": "400",
            "fontSize": size,
            "lineHeightPx": size * 1.5,
        },
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 200, "height": size * 2},
        "fills": [_solid_fill(fill_r, fill_g, fill_b)],
        "children": [],
    }


def _frame_with_padding(
    node_id: str, name: str, children: list[dict[str, Any]], padding: float = 16.0
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": "FRAME",
        "name": name,
        "paddingLeft": padding,
        "paddingRight": padding,
        "paddingTop": padding,
        "paddingBottom": padding,
        "children": children,
    }


def _make_multi_email_file_data() -> dict[str, Any]:
    """Two-frame Figma document: Email A (target) and Email B (noise)."""
    return {
        "document": {
            "id": "0:0",
            "type": "DOCUMENT",
            "children": [
                {
                    "id": "0:1",
                    "type": "CANVAS",
                    "name": "Page 1",
                    "children": [
                        _frame_with_padding(
                            "100:1",
                            "Email A",
                            [_text_node("Helvetica", 16.0, 0.0, 0.5, 0.0)],
                            padding=20.0,
                        ),
                        _frame_with_padding(
                            "200:1",
                            "Email B",
                            [_text_node("Inter", 14.0, 1.0, 0.0, 0.0)],
                            padding=32.0,
                        ),
                    ],
                }
            ],
        },
        "styles": {},
    }


def _make_single_email_file_data() -> dict[str, Any]:
    """Single-frame Figma document."""
    return {
        "document": {
            "id": "0:0",
            "type": "DOCUMENT",
            "children": [
                {
                    "id": "0:1",
                    "type": "CANVAS",
                    "name": "Page 1",
                    "children": [
                        _frame_with_padding(
                            "100:1",
                            "Email A",
                            [_text_node("Helvetica", 16.0, 0.0, 0.5, 0.0)],
                        ),
                    ],
                }
            ],
        },
        "styles": {},
    }


# ── _find_subtree Tests ──


class TestFindSubtree:
    def test_find_root_node(self) -> None:
        doc: RawFigmaNode = cast(
            RawFigmaNode, {"id": "0:0", "children": [{"id": "1:1", "children": []}]}
        )
        result = _find_subtree(doc, "0:0")
        assert result is doc

    def test_find_nested_node(self) -> None:
        target_children: list[dict[str, Any]] = [{"id": "3:1", "children": []}]
        target: dict[str, Any] = {
            "id": "2:1",
            "type": "FRAME",
            "children": target_children,
        }
        doc: RawFigmaNode = cast(
            RawFigmaNode,
            {"id": "0:0", "children": [{"id": "1:1", "children": [target]}]},
        )
        result = _find_subtree(doc, "2:1")
        assert result is target
        # Children intact
        assert len(target_children) == 1

    def test_not_found(self) -> None:
        doc: RawFigmaNode = cast(
            RawFigmaNode, {"id": "0:0", "children": [{"id": "1:1", "children": []}]}
        )
        assert _find_subtree(doc, "999:999") is None

    def test_empty_document(self) -> None:
        assert _find_subtree(cast(RawFigmaNode, {}), "0:0") is None


# ── Scoped Token Extraction Tests ──


class TestScopedTokenExtraction:
    """Integration tests for scoped token extraction via sync_tokens_and_structure."""

    @pytest.fixture
    def figma_service(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    def _mock_http_responses(self, file_data: dict[str, Any]) -> AsyncMock:
        """Build an AsyncClient mock that returns file_data and empty styles."""

        file_resp = MagicMock()
        file_resp.status_code = 200
        file_resp.json.return_value = file_data

        styles_resp = MagicMock()
        styles_resp.status_code = 200
        styles_resp.json.return_value = {}

        client = AsyncMock()
        client.get = AsyncMock(side_effect=[file_resp, styles_resp])
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        return client

    @pytest.mark.asyncio
    async def test_scoped_colors_only_from_target(
        self, figma_service: FigmaDesignSyncService
    ) -> None:
        file_data = _make_multi_email_file_data()
        client = self._mock_http_responses(file_data)

        with patch("app.design_sync.figma.service.httpx.AsyncClient", return_value=client):
            tokens, _structure = await figma_service.sync_tokens_and_structure(
                "test-file", "test-token", target_node_id="100:1"
            )

        # Only Email A's green color, not Email B's red
        hex_values = [c.hex for c in tokens.colors]
        assert any("#008000" in h or "#007F00" in h for h in hex_values), (
            f"Expected green from Email A, got: {hex_values}"
        )
        assert "#FF0000" not in hex_values, "Email B's red should not be present"

    @pytest.mark.asyncio
    async def test_scoped_typography_only_from_target(
        self, figma_service: FigmaDesignSyncService
    ) -> None:
        file_data = _make_multi_email_file_data()
        client = self._mock_http_responses(file_data)

        with patch("app.design_sync.figma.service.httpx.AsyncClient", return_value=client):
            tokens, _ = await figma_service.sync_tokens_and_structure(
                "test-file", "test-token", target_node_id="100:1"
            )

        families = [t.family for t in tokens.typography]
        assert "Helvetica" in families, f"Expected Helvetica, got: {families}"
        assert "Inter" not in families, "Email B's Inter should not be present"

    @pytest.mark.asyncio
    async def test_scoped_spacing_only_from_target(
        self, figma_service: FigmaDesignSyncService
    ) -> None:
        file_data = _make_multi_email_file_data()
        client = self._mock_http_responses(file_data)

        with patch("app.design_sync.figma.service.httpx.AsyncClient", return_value=client):
            tokens, _ = await figma_service.sync_tokens_and_structure(
                "test-file", "test-token", target_node_id="100:1"
            )

        spacing_values = [s.value for s in tokens.spacing]
        assert 20.0 in spacing_values, f"Expected 20px from Email A, got: {spacing_values}"
        assert 32.0 not in spacing_values, "Email B's 32px spacing should not be present"

    @pytest.mark.asyncio
    async def test_scoping_disabled_extracts_all(
        self, figma_service: FigmaDesignSyncService
    ) -> None:
        file_data = _make_multi_email_file_data()
        client = self._mock_http_responses(file_data)

        with (
            patch("app.design_sync.figma.service.httpx.AsyncClient", return_value=client),
            patch("app.design_sync.figma.service.get_settings") as mock_settings,
        ):
            settings = mock_settings.return_value
            settings.design_sync.token_scoping_enabled = False
            settings.design_sync.opacity_composite_bg = "#FFFFFF"
            settings.design_sync.figma_variables_enabled = False

            tokens, _ = await figma_service.sync_tokens_and_structure(
                "test-file", "test-token", target_node_id="100:1"
            )

        families = [t.family for t in tokens.typography]
        assert "Helvetica" in families
        assert "Inter" in families, "Both fonts should be present when scoping is disabled"

    @pytest.mark.asyncio
    async def test_target_not_found_falls_back_to_global(
        self, figma_service: FigmaDesignSyncService
    ) -> None:
        file_data = _make_multi_email_file_data()
        client = self._mock_http_responses(file_data)

        with patch("app.design_sync.figma.service.httpx.AsyncClient", return_value=client):
            tokens, _ = await figma_service.sync_tokens_and_structure(
                "test-file", "test-token", target_node_id="999:999"
            )

        # Should fall back to global extraction — both fonts present
        families = [t.family for t in tokens.typography]
        assert "Helvetica" in families
        assert "Inter" in families, "Fallback should extract all fonts"

    @pytest.mark.asyncio
    async def test_single_frame_file_unchanged(self, figma_service: FigmaDesignSyncService) -> None:
        file_data = _make_single_email_file_data()
        client = self._mock_http_responses(file_data)

        with patch("app.design_sync.figma.service.httpx.AsyncClient", return_value=client):
            scoped_tokens, _ = await figma_service.sync_tokens_and_structure(
                "test-file", "test-token", target_node_id="100:1"
            )

        # Re-create client for unscoped call
        client2 = self._mock_http_responses(file_data)
        with patch("app.design_sync.figma.service.httpx.AsyncClient", return_value=client2):
            global_tokens, _ = await figma_service.sync_tokens_and_structure(
                "test-file", "test-token"
            )

        assert len(scoped_tokens.colors) == len(global_tokens.colors)
        assert len(scoped_tokens.typography) == len(global_tokens.typography)
        assert len(scoped_tokens.spacing) == len(global_tokens.spacing)
