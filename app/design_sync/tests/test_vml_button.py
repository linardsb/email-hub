"""CE-11: unit tests for the VML rounded-button builder (``vml_button.py``)."""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from app.design_sync.vml_button import VmlButton, arcsize_pct, render_vml_button
from app.qa_engine.mso_parser import validate_mso_conditionals

_NS_OPEN = (
    '<html xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:o="urn:schemas-microsoft-com:office:office">'
)
_TWIN = '<a href="https://example.com/x" style="color:#ffffff;">Go</a>'


def _spec(**kw: object) -> VmlButton:
    base = VmlButton(
        href="https://example.com/x",
        label="Go",
        width_px=220,
        height_px=48,
        radius_px=5.0,
        fill="#0066cc",
        text_color="#ffffff",
        stroke_color=None,
        stroke_weight_px=None,
        font_family="Arial, sans-serif",
        font_size_px=16,
        font_weight="bold",
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def _roundrect_tag(out: str) -> str:
    m = re.search(r"<v:roundrect\b[^>]*>", out)
    assert m is not None
    return m.group(0)


# Golden variants from email-templates/components/golden-references/vml-rounded-button-variants.html
_GOLDEN = [
    # (width, height, radius, fill, stroke, weight, text color, size, label, arcsize)
    (220, 48, 5.0, "#0066cc", "#0066cc", 1, "#ffffff", 16, "Get Started", 10),
    (200, 44, 22.0, "#ffffff", "#0066cc", 2, "#0066cc", 14, "Learn More", 50),
    (140, 36, 3.0, "#333333", "#333333", 1, "#ffffff", 13, "View Details", 8),
]


class TestGoldenParity:
    @pytest.mark.parametrize(
        ("w", "h", "r", "fill", "stroke", "weight", "color", "size", "label", "arc"), _GOLDEN
    )
    def test_matches_golden_variant(
        self,
        w: int,
        h: int,
        r: float,
        fill: str,
        stroke: str,
        weight: int,
        color: str,
        size: int,
        label: str,
        arc: int,
    ) -> None:
        out = render_vml_button(
            _spec(
                label=label,
                width_px=w,
                height_px=h,
                radius_px=r,
                fill=fill,
                stroke_color=stroke,
                stroke_weight_px=weight,
                text_color=color,
                font_size_px=size,
            ),
            _TWIN,
        )
        tag = _roundrect_tag(out)
        assert f'arcsize="{arc}%"' in tag
        assert f'style="height:{h}px;v-text-anchor:middle;width:{w}px;"' in tag
        assert f'fillcolor="{fill}"' in tag
        assert f'strokecolor="{stroke}"' in tag
        assert "<w:anchorlock/>" in out
        center = re.search(r"<center style=\"([^\"]*)\">([^<]*)</center>", out)
        assert center is not None
        assert f"color:{color};" in center.group(1)
        assert f"font-size:{size}px;" in center.group(1)
        assert center.group(2) == label


class TestShape:
    def test_wraps_twin_verbatim_in_conditionals(self) -> None:
        out = render_vml_button(_spec(), _TWIN)
        assert out.startswith("<!--[if mso]><v:roundrect ")
        assert out.count("<v:roundrect ") == 1
        assert "</v:roundrect><![endif]--><!--[if !mso]><!-->" in out
        assert out.endswith(f"<!--[if !mso]><!-->{_TWIN}<!--<![endif]-->")

    def test_namespaces_on_roundrect(self) -> None:
        tag = _roundrect_tag(render_vml_button(_spec(), _TWIN))
        assert 'xmlns:v="urn:schemas-microsoft-com:vml"' in tag
        assert 'xmlns:w="urn:schemas-microsoft-com:office:word"' in tag

    def test_mso_conditionals_valid(self) -> None:
        out = render_vml_button(_spec(stroke_color="#000000", stroke_weight_px=2), _TWIN)
        result = validate_mso_conditionals(f"{_NS_OPEN}<body>{out}</body></html>")
        assert result.is_valid, result.issues


class TestFillAndStroke:
    def test_no_fill_is_transparent(self) -> None:
        tag = _roundrect_tag(render_vml_button(_spec(fill=None), _TWIN))
        assert 'fill="f"' in tag
        assert "fillcolor" not in tag

    def test_no_stroke(self) -> None:
        tag = _roundrect_tag(render_vml_button(_spec(), _TWIN))
        assert 'stroke="f"' in tag
        assert "strokecolor" not in tag
        assert "strokeweight" not in tag

    def test_stroke(self) -> None:
        tag = _roundrect_tag(
            render_vml_button(_spec(stroke_color="#FE5219", stroke_weight_px=2), _TWIN)
        )
        assert 'strokecolor="#FE5219"' in tag
        assert 'strokeweight="2px"' in tag
        assert 'stroke="f"' not in tag


class TestArcsize:
    def test_clamped_to_50(self) -> None:
        assert arcsize_pct(40, 200, 44) == 50

    def test_zero_radius(self) -> None:
        assert arcsize_pct(0, 200, 44) == 0

    def test_uses_shorter_side(self) -> None:
        assert arcsize_pct(15, 30, 48) == 50

    def test_classic_outlook_measurement(self) -> None:
        # dextinity #6296: classic Outlook drew 50 px at 19% on 536x268 (50/268 = 18.7%).
        assert arcsize_pct(50, 536, 268) == 18

    def test_degenerate_box(self) -> None:
        assert arcsize_pct(10, 0, 48) == 0


class TestEscaping:
    def test_label_href_and_font_escaped(self) -> None:
        out = render_vml_button(
            _spec(
                label="Shop & <Save>",
                href='https://example.com/?q="x"&a=1',
                font_family="'Helvetica Neue', Arial",
            ),
            _TWIN,
        )
        assert ">Shop &amp; &lt;Save&gt;</center>" in out
        assert 'href="https://example.com/?q=&quot;x&quot;&amp;a=1"' in out
        assert "font-family:&#x27;Helvetica Neue&#x27;, Arial;" in out
