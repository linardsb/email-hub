# pyright: reportPrivateUsage=false
"""Tests for Figma Variables API extraction (Phase 33.11 — Step 1)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from app.design_sync.figma.raw_types import RawVariablesResponse
from app.design_sync.figma.service import FigmaDesignSyncService


def _make_variables_response(
    *,
    colors: dict[str, dict[str, Any]] | None = None,
    collections: dict[str, dict[str, Any]] | None = None,
) -> RawVariablesResponse:
    """Build a minimal Figma Variables API response structure."""
    if collections is None:
        collections = {
            "coll1": {
                "name": "Brand Colors",
                "modes": [{"modeId": "mode_light", "name": "Light"}],
            },
        }
    if colors is None:
        colors = {}
    return cast(
        RawVariablesResponse,
        {
            "local": {
                "meta": {
                    "variableCollections": collections,
                    "variables": colors,
                },
            },
            "published": {},
        },
    )


def _make_color_variable(
    *,
    name: str,
    r: float,
    g: float,
    b: float,
    a: float = 1.0,
    mode_id: str = "mode_light",
    collection_id: str = "coll1",
) -> dict[str, Any]:
    """Build a COLOR variable entry."""
    return {
        "name": name,
        "resolvedType": "COLOR",
        "variableCollectionId": collection_id,
        "valuesByMode": {mode_id: {"r": r, "g": g, "b": b, "a": a}},
    }


def _make_float_variable(
    *,
    name: str,
    value: float,
    mode_id: str = "mode_light",
    collection_id: str = "coll1",
) -> dict[str, Any]:
    """Build a FLOAT variable entry."""
    return {
        "name": name,
        "resolvedType": "FLOAT",
        "variableCollectionId": collection_id,
        "valuesByMode": {mode_id: value},
    }


def _make_string_variable(
    *,
    name: str,
    value: str,
    mode_id: str = "mode_light",
    collection_id: str = "coll1",
) -> dict[str, Any]:
    """Build a STRING variable entry."""
    return {
        "name": name,
        "resolvedType": "STRING",
        "variableCollectionId": collection_id,
        "valuesByMode": {mode_id: value},
    }


class TestVariablesAPIExtraction:
    """Tests for _parse_variables on Figma Variables API responses."""

    def test_color_float_string_variables(self) -> None:
        """COLOR/FLOAT/STRING variables parsed into ExtractedTokens."""
        svc = FigmaDesignSyncService()
        raw = _make_variables_response(
            colors={
                "v1": _make_color_variable(name="color/Primary", r=0.2, g=0.4, b=0.9),
                "v2": _make_float_variable(name="spacing/md", value=16.0),
                "v3": _make_string_variable(name="font/body", value="Inter"),
            },
        )
        colors, _typo, variables, modes, _dark = svc._parse_variables(raw)
        assert len(colors) == 1  # 1 COLOR variable → 1 extracted color
        assert colors[0].name == "Primary"  # "color/" prefix stripped
        assert len(variables) == 3
        var_types = {v.type for v in variables}
        assert "COLOR" in var_types
        assert "FLOAT" in var_types
        assert "STRING" in var_types
        assert "Light" in modes

    def test_alias_resolution(self) -> None:
        """Variable with alias → resolved to literal hex."""
        svc = FigmaDesignSyncService()
        raw = _make_variables_response(
            colors={
                "v_target": _make_color_variable(name="color/brand.primary", r=1.0, g=0.0, b=0.0),
                "v_alias": {
                    "name": "color/alias.primary",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "mode_light": {"type": "VARIABLE_ALIAS", "id": "v_target"},
                    },
                },
            },
        )
        colors, _typo, variables, _modes, _dark = svc._parse_variables(raw)
        # Alias should resolve to the same hex as the target
        alias_var = next(v for v in variables if "alias" in v.name)
        assert alias_var.is_alias is True
        assert alias_var.alias_path == "color/brand.primary"
        # Colors should contain the resolved hex
        assert len(colors) >= 1

    def test_circular_alias_does_not_crash(self) -> None:
        """A→B→A circular alias resolves to None (depth guard)."""
        svc = FigmaDesignSyncService()
        raw = _make_variables_response(
            colors={
                "v_a": {
                    "name": "color/A",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "mode_light": {"type": "VARIABLE_ALIAS", "id": "v_b"},
                    },
                },
                "v_b": {
                    "name": "color/B",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "mode_light": {"type": "VARIABLE_ALIAS", "id": "v_a"},
                    },
                },
            },
        )
        # Should not raise — depth guard returns None
        _colors, _typo, variables, _modes, _dark = svc._parse_variables(raw)
        # Circular aliases won't produce valid colors (resolved value is None)
        assert isinstance(variables, list)

    def test_light_dark_modes(self) -> None:
        """Collection with 'Light'+'Dark' modes → separate colors + dark_colors."""
        svc = FigmaDesignSyncService()
        collections = {
            "coll1": {
                "name": "Theme",
                "modes": [
                    {"modeId": "mode_light", "name": "Light"},
                    {"modeId": "mode_dark", "name": "Dark"},
                ],
            },
        }
        raw = _make_variables_response(
            collections=collections,
            colors={
                "v1": {
                    "name": "color/bg",
                    "resolvedType": "COLOR",
                    "variableCollectionId": "coll1",
                    "valuesByMode": {
                        "mode_light": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0},
                        "mode_dark": {"r": 0.1, "g": 0.1, "b": 0.18, "a": 1.0},
                    },
                },
            },
        )
        colors, _typo, _vars, modes, dark_colors = svc._parse_variables(raw)
        assert len(colors) == 1  # 1 COLOR variable → 1 light color
        assert len(dark_colors) == 1  # same variable → 1 dark color
        assert "Dark" in modes
        assert "Light" in modes

    @pytest.mark.anyio
    async def test_403_fallback_to_styles(self) -> None:
        """403 from Variables API → returns None, sync_tokens_and_structure falls back."""
        svc = FigmaDesignSyncService()
        mock_response_403 = AsyncMock()
        mock_response_403.status_code = 403
        mock_response_pub = AsyncMock()
        mock_response_pub.status_code = 200
        mock_response_pub.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response_403)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.design_sync.figma.service.httpx.AsyncClient", return_value=mock_client):
            result = await svc._fetch_variables("file_key", "token")

        assert result is None

    def test_existing_styles_regression(self) -> None:
        """Standard Styles API response (no Variables) → extraction works unchanged."""
        svc = FigmaDesignSyncService()
        # When _parse_variables receives empty variables, it returns empty lists
        raw = _make_variables_response(colors={})
        colors, _typo, variables, _modes, dark_colors = svc._parse_variables(raw)
        assert colors == []
        assert variables == []
        assert dark_colors == []
