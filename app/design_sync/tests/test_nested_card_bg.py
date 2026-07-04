"""Phase 50.4 — nested-card background detection + ``_outer``/``_inner`` rendering.

Covers:
* ``_detect_inner_bg`` (explicit fill + PNG centroid sampling)
* ``_resolve_corner_radius`` (corner / per-corner radii)
* ``_build_token_overrides`` emission for ``_inner`` bg + radius and the
  ``bg_color`` → ``_outer`` Phase 49 fallback when no nested card detected.
* ``ComponentRenderer`` ``_inner`` dispatch — class-targeted bg + radius
  application, plus ``no-op`` behaviour when ``inner_bg`` is unset.
* Component HTML files carry ``class="_inner"`` / ``class="_outer"`` markers.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.design_sync.component_matcher import (
    TokenOverride,
    _build_token_overrides,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import (
    EmailSection,
    EmailSectionType,
    _detect_inner_bg,
    _resolve_corner_radius,
)
from app.design_sync.protocol import DesignNode, DesignNodeType

_COMPONENT_DIR = Path("email-templates/components")
_TARGET_COMPONENTS = (
    "article-card",
    "zigzag-image-left",
    "zigzag-image-right",
    "editorial-2",
    "event-card",
    "pricing-table",
)


def _frame(
    node_id: str,
    *,
    fill: str | None = None,
    radius: float | None = None,
    radii: tuple[float, ...] | None = None,
    x: float = 0,
    y: float = 0,
    width: float = 600,
    height: float = 400,
) -> DesignNode:
    return DesignNode(
        id=node_id,
        name=node_id,
        type=DesignNodeType.FRAME,
        x=x,
        y=y,
        width=width,
        height=height,
        fill_color=fill,
        corner_radius=radius,
        corner_radii=radii,
    )


def _solid_png(color: tuple[int, int, int], *, size: tuple[int, int] = (600, 400)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _two_band_png(
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
    *,
    size: tuple[int, int] = (600, 400),
    band_y: int = 100,
) -> bytes:
    """Top band painted with ``top_color``, bottom band with ``bottom_color``."""
    img = Image.new("RGB", size, top_color)
    pixels = img.load()
    assert pixels is not None
    for y in range(band_y, size[1]):
        for x in range(size[0]):
            pixels[x, y] = bottom_color
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _section(
    *,
    bg_color: str | None = None,
    container_bg: str | None = None,
    inner_bg: str | None = None,
    inner_radius: float | None = None,
) -> EmailSection:
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s1",
        node_name="Section",
        bg_color=bg_color,
        container_bg=container_bg,
        inner_bg=inner_bg,
        inner_radius=inner_radius,
    )


# ── _detect_inner_bg ──


class TestDetectInnerBg:
    def test_explicit_fill_distinct_from_container(self) -> None:
        node = _frame("card", fill="#FFFFFF", radius=24)
        bg, radius = _detect_inner_bg(
            node,
            container_bg="#A4D33B",
            global_design_image=None,
        )
        assert bg == "#FFFFFF"
        assert radius == 24

    def test_no_inner_bg_when_fill_matches_container(self) -> None:
        node = _frame("card", fill="#A4D33B")
        bg, radius = _detect_inner_bg(
            node,
            container_bg="#A4D33B",
            global_design_image=None,
        )
        assert bg is None
        assert radius is None

    def test_inner_bg_from_png_sampling(self) -> None:
        # White card centred on a lime container — geometric centre is white.
        node = _frame("card", x=100, y=100, width=200, height=100)
        png = _two_band_png(
            top_color=(0xA4, 0xD3, 0x3B),  # lime — outside the card
            bottom_color=(0xFF, 0xFF, 0xFF),  # white — covers the card
            band_y=80,
        )
        bg, _ = _detect_inner_bg(
            node,
            container_bg="#A4D33B",
            global_design_image=png,
        )
        assert bg == "#FFFFFF"

    def test_no_inner_bg_when_png_close_to_container(self) -> None:
        # Centre pixel within Δ=30 of container — not a card surface.
        node = _frame("card", x=100, y=100, width=200, height=100)
        png = _solid_png((0xA4, 0xD3, 0x3B))  # entirely lime
        bg, _ = _detect_inner_bg(
            node,
            container_bg="#A4D33B",
            global_design_image=png,
        )
        assert bg is None

    def test_explicit_fill_returns_none_radius_when_no_radius(self) -> None:
        node = _frame("card", fill="#FFFFFF")
        _, radius = _detect_inner_bg(
            node,
            container_bg="#A4D33B",
            global_design_image=None,
        )
        assert radius is None


class TestResolveCornerRadius:
    def test_scalar_corner_radius(self) -> None:
        node = _frame("card", radius=12.0)
        assert _resolve_corner_radius(node) == 12.0

    def test_per_corner_radii_returns_max(self) -> None:
        node = _frame("card", radii=(8.0, 24.0, 16.0, 12.0))
        assert _resolve_corner_radius(node) == 24.0

    def test_no_radius(self) -> None:
        node = _frame("card")
        assert _resolve_corner_radius(node) is None


# ── _build_token_overrides ──


class TestTokenOverrideEmission:
    def test_emits_inner_bg_when_set(self) -> None:
        section = _section(container_bg="#A4D33B", inner_bg="#FFFFFF")
        overrides = _build_token_overrides(section)
        bg = [
            o
            for o in overrides
            if o.css_property == "background-color" and o.target_class == "_inner"
        ]
        assert len(bg) == 1
        assert bg[0].value == "#FFFFFF"

    def test_emits_inner_radius_when_set(self) -> None:
        section = _section(container_bg="#A4D33B", inner_bg="#FFFFFF", inner_radius=24)
        overrides = _build_token_overrides(section)
        radius = [
            o for o in overrides if o.css_property == "border-radius" and o.target_class == "_inner"
        ]
        assert len(radius) == 1
        assert radius[0].value == "24px"

    def test_falls_back_to_outer_bg_color_without_inner(self) -> None:
        # Phase 49 contract: when no nested card is detected and only
        # ``bg_color`` is set, the override targets ``_outer``.
        section = _section(bg_color="#f5f0e8")
        overrides = _build_token_overrides(section)
        bg = [o for o in overrides if o.css_property == "background-color"]
        assert len(bg) == 1
        assert bg[0].target_class == "_outer"
        assert bg[0].value == "#f5f0e8"

    def test_container_bg_alone_targets_outer(self) -> None:
        section = _section(container_bg="#A4D33B")
        overrides = _build_token_overrides(section)
        targets = {(o.css_property, o.target_class, o.value) for o in overrides}
        assert ("background-color", "_outer", "#A4D33B") in targets


# ── Renderer: _inner dispatch ──


@pytest.fixture
def renderer() -> ComponentRenderer:
    r = ComponentRenderer(container_width=600)
    r.load()
    return r


class TestRendererInnerDispatch:
    def test_replaces_existing_inner_bg(self, renderer: ComponentRenderer) -> None:
        html_in = (
            '<table class="_inner" style="background-color: #ffffff;"><tr><td>x</td></tr></table>'
        )
        out = renderer._apply_token_overrides(
            html_in,
            [TokenOverride("background-color", "_inner", "#FFEEAA")],
        )
        assert "background-color:#FFEEAA" in out
        assert "#ffffff" not in out
        assert 'bgcolor="#FFEEAA"' in out

    def test_injects_inner_bg_when_missing(self, renderer: ComponentRenderer) -> None:
        html_in = (
            '<table class="_inner" style="border-collapse: separate;"><tr><td>x</td></tr></table>'
        )
        out = renderer._apply_token_overrides(
            html_in,
            [TokenOverride("background-color", "_inner", "#FFEEAA")],
        )
        assert "background-color:#FFEEAA" in out
        assert 'bgcolor="#FFEEAA"' in out

    def test_inner_radius_replace_and_inject(self, renderer: ComponentRenderer) -> None:
        html_in = (
            '<table class="_inner" style="border-collapse: separate;"><tr><td>x</td></tr></table>'
        )
        out = renderer._apply_token_overrides(
            html_in,
            [TokenOverride("border-radius", "_inner", "16px")],
        )
        assert "border-radius:16px" in out
        assert "border-collapse:separate" in out
        assert "overflow:hidden" in out


# ── Renderer: _outer bg insert on bg-less seeds (Track F / RC-F2) ──


class TestOuterBgInsertOnBgLessSeed:
    """RC-F2: an ``_outer`` background-color override on a bg-less image seed
    (no ``_outer`` class, no ``background-color`` to replace) inserts the surface
    into the first visible presentation table instead of no-oping, so dark
    section bands don't flip white. Uses the real component seeds."""

    def test_inserts_bg_into_full_width_image_seed(self, renderer: ComponentRenderer) -> None:
        # full-width-image's visible table has a style attr → bg is injected
        # into it; the fixed-width MSO ghost must stay uncolored.
        seed = (_COMPONENT_DIR / "full-width-image.html").read_text(encoding="utf-8")
        out = renderer._apply_token_overrides(
            seed,
            [TokenOverride("background-color", "_outer", "#181818")],
        )
        assert "background-color:#181818" in out
        assert 'bgcolor="#181818"' in out
        # the leading MSO ghost (width="600") is not the target
        ghost = out.split("<![endif]-->")[0]
        assert 'width="600"' in ghost
        assert "background-color:#181818" not in ghost
        assert 'bgcolor="#181818"' not in ghost

    def test_adds_style_attr_to_image_block_seed(self, renderer: ComponentRenderer) -> None:
        # image-block's visible table carries no style attr → one is added.
        seed = (_COMPONENT_DIR / "image-block.html").read_text(encoding="utf-8")
        out = renderer._apply_token_overrides(
            seed,
            [TokenOverride("background-color", "_outer", "#2B2B2B")],
        )
        assert 'style="background-color:#2B2B2B;"' in out
        assert 'bgcolor="#2B2B2B"' in out

    def test_existing_bg_is_replaced_not_inserted(self, renderer: ComponentRenderer) -> None:
        # Gate: a legacy table WITH a background-color goes through replace; the
        # insert path must not fire (replaced != result) or double-apply.
        html_in = (
            '<table role="presentation" width="100%" '
            'style="background-color:#ffffff;padding:0;"><tr><td>x</td></tr></table>'
        )
        out = renderer._apply_token_overrides(
            html_in,
            [TokenOverride("background-color", "_outer", "#181818")],
        )
        assert "background-color:#181818" in out
        assert "#ffffff" not in out
        assert out.count("background-color:#181818") == 1


# ── Component HTML files carry the markers ──


class TestComponentMarkup:
    @pytest.mark.parametrize("slug", _TARGET_COMPONENTS)
    def test_inner_class_present(self, slug: str) -> None:
        html = (_COMPONENT_DIR / f"{slug}.html").read_text(encoding="utf-8")
        assert 'class="' in html
        assert "_inner" in html, f"{slug}.html missing _inner class marker"

    @pytest.mark.parametrize("slug", _TARGET_COMPONENTS)
    def test_outer_class_present(self, slug: str) -> None:
        html = (_COMPONENT_DIR / f"{slug}.html").read_text(encoding="utf-8")
        assert "_outer" in html, f"{slug}.html missing _outer class marker"
