# pyright: reportPrivateUsage=false
"""Tests for RGBA opacity compositing (Phase 33.11 — Step 2)."""

from __future__ import annotations

from typing import cast

from app.design_sync.figma.raw_types import RawFigmaGradientHandle, RawFigmaGradientStop
from app.design_sync.figma.service import (
    _compute_gradient_angle,
    _gradient_midpoint_hex,
    _parse_gradient_stops,
    _rgba_to_hex,
    _rgba_to_hex_with_opacity,
)


class TestOpacityCompositing:
    """Tests for _rgba_to_hex_with_opacity alpha compositing on white background."""

    def test_fill_alpha_half(self) -> None:
        """Pure blue at 50% fill alpha → composited against white."""
        result = _rgba_to_hex_with_opacity(0.0, 0.0, 1.0, fill_alpha=0.5, node_opacity=1.0)
        # Blue channel: 0*0.5 + 1.0*0.5 = 0.5 → 128; R/G: 0*0.5 + 1.0*0.5 = 0.5 → 128
        assert result == "#8080FF"

    def test_node_opacity_half(self) -> None:
        """Pure blue at 100% fill alpha + 50% node opacity → same as 50% fill alpha."""
        result = _rgba_to_hex_with_opacity(0.0, 0.0, 1.0, fill_alpha=1.0, node_opacity=0.5)
        assert result == "#8080FF"

    def test_combined_opacity(self) -> None:
        """50% fill * 50% node = 25% effective → lighter compositing."""
        result = _rgba_to_hex_with_opacity(0.0, 0.0, 1.0, fill_alpha=0.5, node_opacity=0.5)
        # eff_alpha = 0.25; R/G: 0*0.25 + 1.0*0.75 = 0.75 → 191; B: 1.0*0.25 + 1.0*0.75 = 1.0 → 255
        assert result == "#BFBFFF"

    def test_fully_opaque_fast_path(self) -> None:
        """Fully opaque → fast path identical to _rgba_to_hex()."""
        result_with = _rgba_to_hex_with_opacity(1.0, 0.0, 0.0, fill_alpha=1.0, node_opacity=1.0)
        result_plain = _rgba_to_hex(1.0, 0.0, 0.0)
        assert result_with == result_plain
        assert result_with == "#FF0000"

    def test_custom_background(self) -> None:
        """Compositing against a non-white background."""
        result = _rgba_to_hex_with_opacity(
            0.0, 0.0, 0.0, fill_alpha=0.5, node_opacity=1.0, bg_hex="#FF0000"
        )
        # R: 0*0.5 + 1.0*0.5 = 0.5 → 128; G/B: 0*0.5 + 0*0.5 = 0 → 0
        assert result == "#800000"

    def test_zero_opacity_returns_background(self) -> None:
        """Zero effective opacity → returns background color."""
        result = _rgba_to_hex_with_opacity(1.0, 0.0, 0.0, fill_alpha=0.0, node_opacity=1.0)
        assert result == "#FFFFFF"  # white background


class TestGradientHelpers:
    """Tests for gradient utility functions."""

    def test_gradient_midpoint_two_stops(self) -> None:
        """Average of red and blue → purple midpoint."""
        stops: list[RawFigmaGradientStop] = [
            cast(RawFigmaGradientStop, {"color": {"r": 1.0, "g": 0.0, "b": 0.0}}),
            cast(RawFigmaGradientStop, {"color": {"r": 0.0, "g": 0.0, "b": 1.0}}),
        ]
        result = _gradient_midpoint_hex(stops)
        assert result == "#800080"

    def test_gradient_midpoint_single_stop(self) -> None:
        """< 2 stops → None."""
        result = _gradient_midpoint_hex(
            [cast(RawFigmaGradientStop, {"color": {"r": 1.0, "g": 0.0, "b": 0.0}})]
        )
        assert result is None

    def test_compute_gradient_angle_top_to_bottom(self) -> None:
        """Handles from top (0,0) to bottom (0,1) → 180 degrees."""
        handles: list[RawFigmaGradientHandle] = [
            cast(RawFigmaGradientHandle, {"x": 0, "y": 0}),
            cast(RawFigmaGradientHandle, {"x": 0, "y": 1}),
        ]
        angle = _compute_gradient_angle(handles)
        assert angle == 180.0

    def test_compute_gradient_angle_left_to_right(self) -> None:
        """Handles from left (0,0) to right (1,0) → 90 degrees."""
        handles: list[RawFigmaGradientHandle] = [
            cast(RawFigmaGradientHandle, {"x": 0, "y": 0}),
            cast(RawFigmaGradientHandle, {"x": 1, "y": 0}),
        ]
        angle = _compute_gradient_angle(handles)
        assert angle == 90.0

    def test_compute_gradient_angle_default(self) -> None:
        """< 2 handles → default 180."""
        assert _compute_gradient_angle([]) == 180.0
        assert _compute_gradient_angle([cast(RawFigmaGradientHandle, {"x": 0, "y": 0})]) == 180.0

    def test_parse_gradient_stops(self) -> None:
        """Gradient stops parsed into (hex, position) tuples."""
        stops_raw = [
            {"color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}, "position": 0.0},
            {"color": {"r": 0.0, "g": 0.0, "b": 1.0, "a": 1.0}, "position": 1.0},
        ]
        result = _parse_gradient_stops(stops_raw)
        assert len(result) == 2
        assert result[0] == ("#FF0000", 0.0)
        assert result[1] == ("#0000FF", 1.0)

    def test_parse_gradient_stops_with_alpha(self) -> None:
        """Gradient stop with 50% alpha → composited hex."""
        stops_raw = [
            {"color": {"r": 0.0, "g": 0.0, "b": 1.0, "a": 0.5}, "position": 0.0},
        ]
        result = _parse_gradient_stops(stops_raw)
        assert len(result) == 1
        assert result[0][0] == "#8080FF"
