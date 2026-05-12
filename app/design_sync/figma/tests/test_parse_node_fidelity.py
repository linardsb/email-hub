"""Tests for _parse_node data fidelity fixes (38.1).

Covers: opacity falsy trap, visible null handling, COMPONENT/INSTANCE auto-layout,
fill extraction order-dependence, and radial/angular gradient support.
"""

from typing import Any, cast

import pytest

from app.design_sync.figma.raw_types import RawFigmaNode
from app.design_sync.figma.service import FigmaDesignSyncService
from app.design_sync.protocol import DesignNodeType


class TestOpacityFidelity:
    """Bug 1: opacity=0.0 must NOT be replaced by 1.0 (falsy trap)."""

    @pytest.fixture
    def svc(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    def _make_node(self, **overrides: Any) -> RawFigmaNode:
        base: dict[str, Any] = {
            "id": "1:1",
            "type": "FRAME",
            "name": "Test",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 50},
            "children": [],
        }
        base.update(overrides)
        return cast(RawFigmaNode, base)

    def test_opacity_zero_preserved(self, svc: FigmaDesignSyncService) -> None:
        node = svc._parse_node(self._make_node(opacity=0.0), current_depth=0, max_depth=2)
        assert node.opacity == 0.0

    def test_opacity_half_preserved(self, svc: FigmaDesignSyncService) -> None:
        node = svc._parse_node(self._make_node(opacity=0.5), current_depth=0, max_depth=2)
        assert node.opacity == 0.5

    def test_opacity_missing_defaults_to_one(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_node()
        data.pop("opacity", None)
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.opacity == 1.0

    def test_opacity_one_preserved(self, svc: FigmaDesignSyncService) -> None:
        node = svc._parse_node(self._make_node(opacity=1.0), current_depth=0, max_depth=2)
        assert node.opacity == 1.0


class TestVisibleFidelity:
    """Bug 5: visible=null from API should be treated as visible."""

    @pytest.fixture
    def svc(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    def _make_node(self, **overrides: Any) -> RawFigmaNode:
        base: dict[str, Any] = {
            "id": "2:1",
            "type": "RECTANGLE",
            "name": "Box",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 50, "height": 50},
            "children": [],
        }
        base.update(overrides)
        return cast(RawFigmaNode, base)

    def test_visible_null_treated_as_visible(self, svc: FigmaDesignSyncService) -> None:
        node = svc._parse_node(self._make_node(visible=None), current_depth=0, max_depth=2)
        assert node.visible is True

    def test_visible_false_treated_as_hidden(self, svc: FigmaDesignSyncService) -> None:
        node = svc._parse_node(self._make_node(visible=False), current_depth=0, max_depth=2)
        assert node.visible is False

    def test_visible_missing_treated_as_visible(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_node()
        data.pop("visible", None)
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.visible is True


class TestAutoLayoutFidelity:
    """Bug 2: COMPONENT/COMPONENT_SET/INSTANCE nodes must extract auto-layout."""

    @pytest.fixture
    def svc(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    def _make_autolayout_node(self, raw_type: str) -> RawFigmaNode:
        return cast(
            RawFigmaNode,
            {
                "id": "3:1",
                "type": raw_type,
                "name": "AutoLayout",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 300, "height": 200},
                "layoutMode": "VERTICAL",
                "paddingTop": 16,
                "paddingRight": 24,
                "paddingBottom": 16,
                "paddingLeft": 24,
                "itemSpacing": 12,
                "counterAxisSpacing": 8,
                "children": [],
            },
        )

    def test_component_autolayout_extracted(self, svc: FigmaDesignSyncService) -> None:
        node = svc._parse_node(
            self._make_autolayout_node("COMPONENT"), current_depth=0, max_depth=2
        )
        assert node.layout_mode == "VERTICAL"
        assert node.padding_top == 16.0
        assert node.padding_right == 24.0
        assert node.padding_bottom == 16.0
        assert node.padding_left == 24.0
        assert node.item_spacing == 12.0
        assert node.counter_axis_spacing == 8.0

    def test_instance_autolayout_extracted(self, svc: FigmaDesignSyncService) -> None:
        node = svc._parse_node(self._make_autolayout_node("INSTANCE"), current_depth=0, max_depth=2)
        assert node.layout_mode == "VERTICAL"
        assert node.item_spacing == 12.0
        assert node.padding_top == 16.0

    def test_component_set_autolayout_extracted(self, svc: FigmaDesignSyncService) -> None:
        node = svc._parse_node(
            self._make_autolayout_node("COMPONENT_SET"), current_depth=0, max_depth=2
        )
        assert node.layout_mode == "VERTICAL"
        assert node.item_spacing == 12.0

    def test_frame_autolayout_still_works(self, svc: FigmaDesignSyncService) -> None:
        """Regression: FRAME auto-layout must not break."""
        node = svc._parse_node(self._make_autolayout_node("FRAME"), current_depth=0, max_depth=2)
        assert node.layout_mode == "VERTICAL"
        assert node.item_spacing == 12.0


class TestFillExtractionFidelity:
    """Bug 3: Stacked fills (IMAGE + SOLID) must extract both regardless of order."""

    @pytest.fixture
    def svc(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    def _solid_fill(self, r: float, g: float, b: float, a: float = 1.0) -> dict[str, Any]:
        return {"type": "SOLID", "color": {"r": r, "g": g, "b": b, "a": a}}

    def _image_fill(self, ref: str = "img_abc123") -> dict[str, Any]:
        return {"type": "IMAGE", "imageRef": ref}

    def test_vector_image_over_solid_extracts_both(self, svc: FigmaDesignSyncService) -> None:
        """VECTOR with [SOLID(bottom), IMAGE(top)] — should get IMAGE type AND fill_color."""
        data: RawFigmaNode = cast(
            RawFigmaNode,
            {
                "id": "4:1",
                "type": "RECTANGLE",
                "name": "Icon",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 24, "height": 24},
                "fills": [self._solid_fill(1.0, 0.0, 0.0), self._image_fill()],
                "children": [],
            },
        )
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.type == DesignNodeType.IMAGE
        assert node.fill_color is not None
        assert node.fill_color == "#FF0000"

    def test_vector_solid_over_image_solid_wins(self, svc: FigmaDesignSyncService) -> None:
        """VECTOR with [IMAGE(bottom), SOLID(top)] — topmost SOLID wins, type stays VECTOR."""
        data: RawFigmaNode = cast(
            RawFigmaNode,
            {
                "id": "4:2",
                "type": "VECTOR",
                "name": "Shape",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 24, "height": 24},
                "fills": [self._image_fill(), self._solid_fill(0.0, 0.0, 1.0)],
                "children": [],
            },
        )
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        # Reversed iteration finds SOLID first (topmost) and breaks — correct
        assert node.type == DesignNodeType.VECTOR
        assert node.fill_color == "#0000FF"

    def test_frame_image_fill_extracts_ref(self, svc: FigmaDesignSyncService) -> None:
        """FRAME with IMAGE fill should populate image_ref."""
        data: RawFigmaNode = cast(
            RawFigmaNode,
            {
                "id": "4:3",
                "type": "FRAME",
                "name": "Hero",
                "absoluteBoundingBox": {"x": 0, "y": 0, "width": 600, "height": 400},
                "fills": [self._image_fill("hero_bg_ref")],
                "children": [],
            },
        )
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.image_ref == "hero_bg_ref"


class TestGradientFidelity:
    """Bug 4: Radial/angular gradients must be extracted, not silently dropped."""

    @pytest.fixture
    def svc(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    def _gradient_fill(self, gradient_type: str) -> dict[str, Any]:
        return {
            "type": gradient_type,
            "gradientStops": [
                {"color": {"r": 1, "g": 0, "b": 0, "a": 1}, "position": 0.0},
                {"color": {"r": 0, "g": 0, "b": 1, "a": 1}, "position": 1.0},
            ],
            "gradientHandlePositions": [{"x": 0.5, "y": 0}, {"x": 0.5, "y": 1}],
        }

    def _make_file_data(self, fills: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "document": {
                "children": [
                    {
                        "type": "FRAME",
                        "name": "GradientNode",
                        "fills": fills,
                        "children": [],
                    }
                ]
            }
        }

    def test_gradient_radial_extracted(self, svc: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data([self._gradient_fill("GRADIENT_RADIAL")])
        colors, _, gradients = svc._parse_colors(file_data, {})
        midpoints = [c for c in colors if "(gradient midpoint)" in c.name]
        assert len(midpoints) == 1
        assert midpoints[0].hex == "#800080"
        assert len(gradients) == 1
        assert gradients[0].type == "radial"
        assert gradients[0].angle == 0.0

    def test_gradient_angular_midpoint(self, svc: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data([self._gradient_fill("GRADIENT_ANGULAR")])
        colors, _, gradients = svc._parse_colors(file_data, {})
        midpoints = [c for c in colors if "(gradient midpoint)" in c.name]
        assert len(midpoints) == 1
        assert midpoints[0].hex == "#800080"
        assert len(gradients) == 1
        assert gradients[0].type == "radial"

    def test_gradient_diamond_extracted(self, svc: FigmaDesignSyncService) -> None:
        file_data = self._make_file_data([self._gradient_fill("GRADIENT_DIAMOND")])
        _colors, _, gradients = svc._parse_colors(file_data, {})
        assert len(gradients) == 1
        assert gradients[0].type == "radial"

    def test_gradient_linear_still_works(self, svc: FigmaDesignSyncService) -> None:
        """Regression: GRADIENT_LINEAR must still produce type='linear' with angle."""
        file_data = self._make_file_data([self._gradient_fill("GRADIENT_LINEAR")])
        _colors, _, gradients = svc._parse_colors(file_data, {})
        assert len(gradients) == 1
        assert gradients[0].type == "linear"
        assert gradients[0].angle == 180.0  # top-to-bottom


class TestFieldEnrichment:
    """39.1: New field extraction — hyperlinks, corner radius, alignment, strokes, style runs."""

    @pytest.fixture
    def svc(self) -> FigmaDesignSyncService:
        return FigmaDesignSyncService()

    def _make_node(self, **overrides: Any) -> RawFigmaNode:
        base: dict[str, Any] = {
            "id": "39:1",
            "type": "FRAME",
            "name": "Enriched",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 200, "height": 48},
            "children": [],
        }
        base.update(overrides)
        return cast(RawFigmaNode, base)

    def _make_text_node(self, **overrides: Any) -> RawFigmaNode:
        base: dict[str, Any] = {
            "id": "39:2",
            "type": "TEXT",
            "name": "Label",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 20},
            "characters": "Hello World",
            "style": {"fontFamily": "Inter", "fontSize": 16, "fontWeight": 400},
            "fills": [{"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0, "a": 1}}],
            "children": [],
        }
        base.update(overrides)
        return cast(RawFigmaNode, base)

    # ── Hyperlink tests ──

    def test_hyperlink_dict_url_extracted(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node(hyperlink={"type": "URL", "url": "https://example.com"})
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.hyperlink == "https://example.com"

    def test_hyperlink_string_url_extracted(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node(hyperlink="https://example.com/page")
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.hyperlink == "https://example.com/page"

    def test_hyperlink_javascript_rejected(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node(hyperlink={"type": "URL", "url": "javascript:alert(1)"})
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.hyperlink is None

    def test_hyperlink_data_uri_rejected(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node(hyperlink="data:text/html,<script>alert(1)</script>")
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.hyperlink is None

    def test_hyperlink_mailto_allowed(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node(hyperlink={"type": "URL", "url": "mailto:user@example.com"})
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.hyperlink == "mailto:user@example.com"

    def test_hyperlink_missing_is_none(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node()
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.hyperlink is None

    # ── Corner radius tests ──

    def test_corner_radius_extracted(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_node(cornerRadius=8)
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.corner_radius == 8.0

    def test_rectangle_corner_radii_extracted(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_node(rectangleCornerRadii=[4, 4, 0, 0])
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.corner_radii == (4.0, 4.0, 0.0, 0.0)

    # ── Text alignment tests ──

    def test_text_align_center(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node(
            style={
                "textAlignHorizontal": "CENTER",
                "fontFamily": "Inter",
                "fontSize": 16,
                "fontWeight": 400,
            }
        )
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.text_align == "center"

    def test_text_align_right(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node(
            style={
                "textAlignHorizontal": "RIGHT",
                "fontFamily": "Inter",
                "fontSize": 16,
                "fontWeight": 400,
            }
        )
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.text_align == "right"

    # ── Axis alignment tests ──

    def test_primary_axis_align_center(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_node(primaryAxisAlignItems="CENTER")
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.primary_axis_align == "center"

    def test_counter_axis_align_end(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_node(counterAxisAlignItems="MAX")
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.counter_axis_align == "end"

    # ── Stroke tests ──

    def test_stroke_solid_extracted(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_node(
            strokes=[{"type": "SOLID", "color": {"r": 0.878, "g": 0.878, "b": 0.878, "a": 1.0}}],
            strokeWeight=1,
        )
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.stroke_weight == 1.0
        assert node.stroke_color is not None
        assert node.stroke_color.startswith("#")

    def test_stroke_gradient_ignored(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_node(
            strokes=[{"type": "GRADIENT_LINEAR", "gradientStops": []}],
            strokeWeight=2,
        )
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.stroke_color is None

    # ── Style runs tests ──

    def test_style_runs_bold_italic(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node(
            characters="Hello Bold",
            characterStyleOverrides=[0, 0, 0, 0, 0, 0, 1, 1, 1, 1],
            styleOverrideTable={
                "1": {"fontWeight": 700, "fontPostScriptName": "Inter-BoldItalic", "italic": True}
            },
        )
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert len(node.style_runs) == 1
        assert node.style_runs[0].bold is True
        assert node.style_runs[0].italic is True
        assert node.style_runs[0].start == 6
        assert node.style_runs[0].end == 10

    def test_style_runs_mixed_color(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node(
            characters="Red text here",
            characterStyleOverrides=[1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            styleOverrideTable={
                "1": {"fills": [{"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0}}]}
            },
        )
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert len(node.style_runs) == 1
        assert node.style_runs[0].color_hex == "#FF0000"

    def test_style_runs_empty_when_no_overrides(self, svc: FigmaDesignSyncService) -> None:
        data = self._make_text_node()
        node = svc._parse_node(data, current_depth=0, max_depth=2)
        assert node.style_runs == ()
