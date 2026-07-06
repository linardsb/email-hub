"""RC-F7 (Track F) — column-layout card surface insert.

``column-layout-{2,3,4}`` seeds carry no ``class="_inner"`` element, so a section
with ``inner_bg`` set (a card floating on a coloured band — LEGO benefit cards)
would lose its surface: the ``_inner`` bg override no-ops and content renders on
the bare band. ``ComponentRenderer._wrap_col_bg_inner_card`` mirrors the RC-F2
insert-on-no-op — when the ``_inner`` bg override finds no target AND the section
rendered through a ``col[234]-bg`` cell, it wraps that cell's whole body in ONE
``<table class="product-card _inner">`` painted with the card colour.

Tests render from the REAL seeds (with the MSO ``[if mso]`` ghost comments) because
``_find_matching_close`` counts ``<td>``/``</td>`` tokens inside comments; it lands
on the true ``col-bg`` ``</td>`` only because the ghost's commented cells balance
(N/N for column-layout-N). A stripped fixture would balance trivially and pass while
the real render mis-nests.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.design_sync.component_matcher import TokenOverride
from app.design_sync.component_renderer import ComponentRenderer

_COMPONENT_DIR = Path("email-templates/components")
_COLUMN_SEEDS = ("column-layout-2", "column-layout-3", "column-layout-4")


def _tag_balanced(html_str: str, tag: str) -> bool:
    """True when every ``<tag>`` (incl. those inside HTML comments) is closed."""
    depth = 0
    for match in re.finditer(rf"<(/?){tag}\b[^>]*?(/?)>", html_str, re.DOTALL):
        if match.group(1):
            depth -= 1
        elif not match.group(2):
            depth += 1
    return depth == 0


@pytest.fixture
def renderer() -> ComponentRenderer:
    r = ComponentRenderer(container_width=600)
    r.load()
    return r


def _inner_bg(color: str = "#FFFFFF") -> list[TokenOverride]:
    return [TokenOverride("background-color", "_inner", color)]


class TestColumnCardSurfaceInsert:
    """RC-F7: an ``_inner`` bg override on a column seed (no ``_inner`` target)
    wraps the ``col[234]-bg`` cell body in a painted card surface."""

    @pytest.mark.parametrize("slug", _COLUMN_SEEDS)
    def test_inner_bg_wraps_card(self, renderer: ComponentRenderer, slug: str) -> None:
        seed = (_COMPONENT_DIR / f"{slug}.html").read_text(encoding="utf-8")
        assert 'class="product-card _inner"' not in seed  # pre-condition
        out = renderer._apply_token_overrides(seed, _inner_bg("#FFFFFF"))
        assert 'class="product-card _inner"' in out
        assert "background-color:#FFFFFF" in out
        assert 'bgcolor="#FFFFFF"' in out

    def test_no_inner_bg_byte_identical(self, renderer: ComponentRenderer) -> None:
        # No _inner override at all → the branch never runs → seed unchanged.
        seed = (_COMPONENT_DIR / "column-layout-2.html").read_text(encoding="utf-8")
        assert renderer._apply_token_overrides(seed, []) == seed

    def test_outer_only_override_adds_no_wrapper(self, renderer: ComponentRenderer) -> None:
        # container_bg → _outer paints the band; it must not add a card surface.
        seed = (_COMPONENT_DIR / "column-layout-2.html").read_text(encoding="utf-8")
        out = renderer._apply_token_overrides(
            seed, [TokenOverride("background-color", "_outer", "#AFCA01")]
        )
        assert 'class="product-card _inner"' not in out

    def test_wrapper_spans_both_columns_uniform(self, renderer: ComponentRenderer) -> None:
        # ONE wrapper (not per-column) around BOTH col slots; well-formed output.
        seed = (_COMPONENT_DIR / "column-layout-2.html").read_text(encoding="utf-8")
        out = renderer._apply_token_overrides(seed, _inner_bg("#FFFFFF"))
        assert out.count('class="product-card _inner"') == 1
        wrap_at = out.index('class="product-card _inner"')
        assert wrap_at < out.index('data-slot="col_1"')
        assert wrap_at < out.index('data-slot="col_2"')
        # the MSO ghost cells balance, so the wrap closes at the true col-bg </td>
        assert _tag_balanced(out, "td")
        assert _tag_balanced(out, "table")

    def test_wrapper_carries_static_dark_class(self, renderer: ComponentRenderer) -> None:
        # product-card is a static dark-mode class (converter_service.py → #2d2d44)
        # so the card flips in dark mode with no dark-CSS change.
        seed = (_COMPONENT_DIR / "column-layout-2.html").read_text(encoding="utf-8")
        out = renderer._apply_token_overrides(seed, _inner_bg("#FFFFFF"))
        assert re.search(r'class="[^"]*\bproduct-card\b[^"]*"', out)

    def test_inner_radius_rounds_wrapper(self, renderer: ComponentRenderer) -> None:
        # inner_bg emitted before inner_radius, so the radius override finds the
        # freshly inserted _inner wrapper and rounds it (per-section, 4 corners).
        seed = (_COMPONENT_DIR / "column-layout-2.html").read_text(encoding="utf-8")
        out = renderer._apply_token_overrides(
            seed,
            [
                TokenOverride("background-color", "_inner", "#FFFFFF"),
                TokenOverride("border-radius", "_inner", "12px"),
            ],
        )
        wrapper = re.search(r'<table[^>]*class="product-card _inner"[^>]*>', out)
        assert wrapper is not None
        tag = wrapper.group(0)
        assert "border-radius:12px" in tag
        assert "border-collapse:separate" in tag
        assert "overflow:hidden" in tag
        # a base border-collapse:collapse would sit later in the value and win,
        # defeating the rounded-corner clipping — guard against that regression.
        assert "border-collapse:collapse" not in tag

    def test_real_inner_seed_not_double_wrapped(self, renderer: ComponentRenderer) -> None:
        # article-card already has class="artcard-bg _inner" → the override paints
        # it and the col-bg fallback must NOT fire (no product-card wrapper added).
        seed = (_COMPONENT_DIR / "article-card.html").read_text(encoding="utf-8")
        out = renderer._apply_token_overrides(seed, _inner_bg("#FFEEAA"))
        assert 'class="product-card _inner"' not in out
        assert "artcard-bg _inner" in out
        assert "background-color:#FFEEAA" in out

    def test_non_column_seed_noop(self, renderer: ComponentRenderer) -> None:
        # inner_bg override on HTML with no col[234]-bg cell and no _inner target
        # → both replace and wrap no-op → byte-identical.
        html_in = '<table role="presentation" width="100%"><tr><td>x</td></tr></table>'
        assert renderer._apply_token_overrides(html_in, _inner_bg("#FFFFFF")) == html_in
