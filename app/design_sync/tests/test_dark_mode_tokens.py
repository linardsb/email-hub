"""Tests for dark mode token extraction, gradient parsing, and CSS generation."""

from __future__ import annotations

from app.design_sync.converter_service import dark_mode_meta_tags, dark_mode_style_block
from app.design_sync.dark_mode_gradient import _gradient_to_css
from app.design_sync.protocol import ExtractedColor, ExtractedGradient, ExtractedTokens
from app.design_sync.token_transforms import (
    TokenWarning,
    _apply_magic_colors,
    _validate_dark_mode_contrast,
    _validate_gradient,
    validate_and_transform,
)

# ── Dark Mode Variable Extraction ──


class TestDarkModeVariableExtraction:
    def test_dark_mode_detected_from_modes(self) -> None:
        """Collection with 'Light'/'Dark' modes → dark_colors populated."""
        tokens = ExtractedTokens(
            colors=[ExtractedColor(name="Background", hex="#FFFFFF")],
            dark_colors=[ExtractedColor(name="Background", hex="#1A1A2E")],
        )
        assert len(tokens.dark_colors) == 1
        assert tokens.dark_colors[0].hex == "#1A1A2E"

    def test_no_dark_mode_no_dark_colors(self) -> None:
        """No dark mode in collection → dark_colors empty."""
        tokens = ExtractedTokens(
            colors=[ExtractedColor(name="Background", hex="#FFFFFF")],
        )
        assert tokens.dark_colors == []

    def test_dark_colors_matched_by_name(self) -> None:
        """Dark_colors[i].name matches colors[i].name for pairing."""
        tokens = ExtractedTokens(
            colors=[
                ExtractedColor(name="Background", hex="#FFFFFF"),
                ExtractedColor(name="Text", hex="#000000"),
            ],
            dark_colors=[
                ExtractedColor(name="Background", hex="#1A1A2E"),
                ExtractedColor(name="Text", hex="#E0E0E0"),
            ],
        )
        assert tokens.dark_colors[0].name == tokens.colors[0].name
        assert tokens.dark_colors[1].name == tokens.colors[1].name


# ── Magic Color Replacement ──


class TestMagicColorReplacement:
    def test_pure_black_replaced(self) -> None:
        """#000000 → #010101."""
        color = ExtractedColor(name="bg", hex="#000000")
        result = _apply_magic_colors(color)
        assert result.hex == "#010101"

    def test_pure_white_replaced(self) -> None:
        """#FFFFFF → #FEFEFE."""
        color = ExtractedColor(name="bg", hex="#FFFFFF")
        result = _apply_magic_colors(color)
        assert result.hex == "#FEFEFE"

    def test_non_magic_unchanged(self) -> None:
        """#333333 stays #333333."""
        color = ExtractedColor(name="bg", hex="#333333")
        result = _apply_magic_colors(color)
        assert result.hex == "#333333"

    def test_magic_colors_applied_in_validate_and_transform(self) -> None:
        """Full pipeline applies magic colors to dark tokens."""
        tokens = ExtractedTokens(
            colors=[ExtractedColor(name="bg", hex="#FFFFFF")],
            dark_colors=[
                ExtractedColor(name="bg", hex="#000000"),
                ExtractedColor(name="text", hex="#FFFFFF"),
            ],
        )
        validated, _ = validate_and_transform(tokens)
        dark_hexes = {c.hex for c in validated.dark_colors}
        assert "#010101" in dark_hexes
        assert "#FEFEFE" in dark_hexes
        assert "#000000" not in dark_hexes
        assert "#FFFFFF" not in dark_hexes


# ── Dark Mode Contrast ──


class TestDarkModeContrast:
    def test_low_contrast_warns(self) -> None:
        """Dark bg #1A1A2E + dark text #2A2A3E → warning."""
        dark_colors = [
            ExtractedColor(name="background", hex="#1A1A2E"),
            ExtractedColor(name="text", hex="#2A2A3E"),
        ]
        warnings: list[TokenWarning] = []
        _validate_dark_mode_contrast(dark_colors, warnings)
        assert any("contrast ratio" in w.message.lower() for w in warnings)

    def test_adequate_contrast_no_warning(self) -> None:
        """Dark bg #1A1A2E + light text #FFFFFF → no warning."""
        dark_colors = [
            ExtractedColor(name="background", hex="#1A1A2E"),
            ExtractedColor(name="text", hex="#FFFFFF"),
        ]
        warnings: list[TokenWarning] = []
        _validate_dark_mode_contrast(dark_colors, warnings)
        assert not any("contrast ratio" in w.message.lower() for w in warnings)


# ── Gradient Extraction ──


class TestGradientExtraction:
    def test_linear_gradient_parsed(self) -> None:
        """2-stop gradient → ExtractedGradient with angle + stops."""
        grad = ExtractedGradient(
            name="hero-bg",
            type="linear",
            angle=180.0,
            stops=(("#FF0000", 0.0), ("#0000FF", 1.0)),
            fallback_hex="#800080",
        )
        assert grad.type == "linear"
        assert grad.angle == 180.0
        assert len(grad.stops) == 2

    def test_gradient_3_stops(self) -> None:
        """3 stops all present."""
        grad = ExtractedGradient(
            name="triple",
            type="linear",
            angle=90.0,
            stops=(("#FF0000", 0.0), ("#00FF00", 0.5), ("#0000FF", 1.0)),
            fallback_hex="#808080",
        )
        assert len(grad.stops) == 3
        assert grad.stops[1] == ("#00FF00", 0.5)

    def test_gradient_fallback_is_midpoint(self) -> None:
        """fallback_hex matches midpoint."""
        grad = ExtractedGradient(
            name="bg",
            type="linear",
            angle=180.0,
            stops=(("#FF0000", 0.0), ("#0000FF", 1.0)),
            fallback_hex="#800080",
        )
        assert grad.fallback_hex == "#800080"


# ── Gradient CSS ──


class TestGradientCSS:
    def test_gradient_to_css(self) -> None:
        """Renders correct linear-gradient() syntax."""
        grad = ExtractedGradient(
            name="bg",
            type="linear",
            angle=180.0,
            stops=(("#FF0000", 0.0), ("#0000FF", 1.0)),
            fallback_hex="#800080",
        )
        css = _gradient_to_css(grad)
        assert css == "linear-gradient(180.0deg, #FF0000 0.0%, #0000FF 100.0%)"

    def test_unparseable_stop_color_warns(self) -> None:
        """Unparseable gradient stop color emits error-level warning."""
        grad = ExtractedGradient(
            name="bad",
            type="linear",
            angle=180.0,
            stops=(("not-a-color", 0.0), ("#0000FF", 1.0)),
            fallback_hex="#808080",
        )
        warnings: list[TokenWarning] = []
        validated = _validate_gradient(grad, warnings)
        assert any(w.level == "error" and "Unparseable" in w.message for w in warnings)
        # Original value preserved when unparseable
        assert validated.stops[0][0] == "not-a-color"

    def test_gradient_angle_clamped(self) -> None:
        """Angle > 360 → clamped to 0-360."""
        grad = ExtractedGradient(
            name="bg",
            type="linear",
            angle=450.0,
            stops=(("#FF0000", 0.0), ("#0000FF", 1.0)),
            fallback_hex="#800080",
        )
        warnings: list[TokenWarning] = []
        validated = _validate_gradient(grad, warnings)
        assert validated.angle == 90.0
        assert any("clamped" in w.message.lower() for w in warnings)


# ── Dark Mode Style Block ──


class TestDarkModeStyleBlock:
    def _make_pairs(
        self,
    ) -> tuple[list[ExtractedColor], list[ExtractedColor]]:
        light = [
            ExtractedColor(name="Background", hex="#FFFFFF"),
            ExtractedColor(name="Text Color", hex="#000000"),
        ]
        dark = [
            ExtractedColor(name="Background", hex="#1A1A2E"),
            ExtractedColor(name="Text Color", hex="#E0E0E0"),
        ]
        return light, dark

    def test_generates_media_query(self) -> None:
        """@media (prefers-color-scheme: dark) present."""
        light, dark = self._make_pairs()
        css = dark_mode_style_block(light, dark)
        assert "@media (prefers-color-scheme: dark)" in css

    def test_generates_outlook_selectors(self) -> None:
        """[data-ogsc] and [data-ogsb] present."""
        light, dark = self._make_pairs()
        css = dark_mode_style_block(light, dark)
        assert "[data-ogsb]" in css
        assert "[data-ogsc]" in css

    def test_important_on_all_overrides(self) -> None:
        """All rules have !important."""
        light, dark = self._make_pairs()
        css = dark_mode_style_block(light, dark)
        # Every line with a CSS property should have !important
        for line in css.splitlines():
            if "background-color:" in line or "color:" in line:
                assert "!important" in line

    def test_empty_dark_colors_no_output(self) -> None:
        """No dark colors → empty string."""
        css = dark_mode_style_block(
            [ExtractedColor(name="bg", hex="#FFFFFF")],
            [],
        )
        assert css == ""

    def test_meta_tags_generated(self) -> None:
        """Includes color-scheme meta."""
        meta = dark_mode_meta_tags()
        assert 'name="color-scheme"' in meta
        assert 'name="supported-color-schemes"' in meta

    def test_no_dark_mode_no_meta_tags_in_skeleton(self) -> None:
        """No dark tokens → no meta tags in style block."""
        from app.design_sync.converter_service import DesignConverterService
        from app.design_sync.protocol import DesignFileStructure, DesignNode, DesignNodeType

        structure = DesignFileStructure(
            file_name="test",
            pages=[
                DesignNode(
                    id="page1",
                    name="Page 1",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="frame1",
                            name="Frame 1",
                            type=DesignNodeType.FRAME,
                            width=600,
                            height=400,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="Text",
                                    type=DesignNodeType.TEXT,
                                    text_content="Hello",
                                    y=0,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        tokens = ExtractedTokens(
            colors=[ExtractedColor(name="bg", hex="#FFFFFF")],
            dark_colors=[],
        )
        from app.design_sync.email_design_document import EmailDesignDocument

        document = EmailDesignDocument.from_legacy(structure, tokens)
        result = DesignConverterService().convert_document(document)
        assert 'name="color-scheme"' not in result.html

    def test_dark_mode_meta_tags_in_skeleton(self) -> None:
        """Dark tokens → meta tags appear in output HTML."""
        from app.design_sync.converter_service import DesignConverterService
        from app.design_sync.protocol import DesignFileStructure, DesignNode, DesignNodeType

        structure = DesignFileStructure(
            file_name="test",
            pages=[
                DesignNode(
                    id="page1",
                    name="Page 1",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="frame1",
                            name="Frame 1",
                            type=DesignNodeType.FRAME,
                            width=600,
                            height=400,
                            children=[
                                DesignNode(
                                    id="t2",
                                    name="Text",
                                    type=DesignNodeType.TEXT,
                                    text_content="Hello",
                                    y=0,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        tokens = ExtractedTokens(
            colors=[ExtractedColor(name="Background", hex="#FFFFFF")],
            dark_colors=[ExtractedColor(name="Background", hex="#1A1A2E")],
        )
        from app.design_sync.email_design_document import EmailDesignDocument

        document = EmailDesignDocument.from_legacy(structure, tokens)
        result = DesignConverterService().convert_document(document)
        assert 'name="color-scheme"' in result.html
        assert "@media (prefers-color-scheme: dark)" in result.html


# ── Gradient Validation Pipeline ──


class TestGradientValidationPipeline:
    def test_gradients_preserved_through_validation(self) -> None:
        """Gradients pass through validate_and_transform intact."""
        tokens = ExtractedTokens(
            colors=[ExtractedColor(name="bg", hex="#FFFFFF")],
            gradients=[
                ExtractedGradient(
                    name="hero",
                    type="linear",
                    angle=180.0,
                    stops=(("#FF0000", 0.0), ("#0000FF", 1.0)),
                    fallback_hex="#800080",
                ),
            ],
        )
        validated, _warnings = validate_and_transform(tokens)
        assert len(validated.gradients) == 1
        assert validated.gradients[0].name == "hero"
        assert len(validated.gradients[0].stops) == 2
