"""Regression tests for the Rule 10 per-corner image radius applicator.

``_apply_image_corner_radius`` merges per-corner ``border-*-radius`` longhands
into the matching ``<img data-node-id="X">``'s own ``style`` attribute. The
applicator must work regardless of whether ``style=`` precedes or follows
``data-node-id`` — the original form assumed ``data-node-id`` came first and,
when ``style`` came first, silently appended a SECOND ``style=`` attribute
(invalid HTML; browsers ignore the duplicate, so the radius never rendered).
This surfaced once Phase 52.3 un-inerted ``corner_radius_spec`` on the bridge.
"""

from __future__ import annotations

import pytest

from app.design_sync.component_renderer import ComponentRenderer

_RADII = (
    ("border-top-left-radius", "6px"),
    ("border-top-right-radius", "0px"),
    ("border-bottom-right-radius", "0px"),
    ("border-bottom-left-radius", "6px"),
)


@pytest.fixture
def renderer() -> ComponentRenderer:
    return ComponentRenderer(container_width=600)


def _apply_all(renderer: ComponentRenderer, html: str, node_id: str) -> str:
    out = html
    for prop, val in _RADII:
        out = renderer._apply_image_corner_radius(out, node_id, prop, val)
    return out


def test_style_before_data_node_id_merges_single_attr(renderer: ComponentRenderer) -> None:
    """The bug case: ``style`` precedes ``data-node-id`` — must merge, not duplicate."""
    html = (
        '<td style="padding:4px;">'
        '<img data-slot="image_1" style="display:block;width:100%;border:0;" '
        'data-node-id="2833:2060" /></td>'
    )
    out = _apply_all(renderer, html, "2833:2060")
    assert out.count('style="') == 2, "expected exactly one img style + one td style, no duplicate"
    img = out[out.index("<img") :]
    assert img.count('style="') == 1, "img must carry a single style attribute"
    for prop, val in _RADII:
        assert f"{prop}:{val}" in img
    assert "display:block" in img, "pre-existing style declarations must be preserved"


def test_data_node_id_before_style_also_merges(renderer: ComponentRenderer) -> None:
    """The other attribute order must behave identically."""
    html = '<img data-node-id="2833:2060" data-slot="image_1" style="display:block;border:0;" />'
    out = _apply_all(renderer, html, "2833:2060")
    assert out.count('style="') == 1
    for prop, val in _RADII:
        assert f"{prop}:{val}" in out
    assert "display:block" in out


def test_img_without_style_attr_gets_one(renderer: ComponentRenderer) -> None:
    html = '<img data-node-id="2833:2060" data-slot="image_1" />'
    out = renderer._apply_image_corner_radius(html, "2833:2060", "border-top-left-radius", "6px")
    assert out.count('style="') == 1
    assert "border-top-left-radius:6px" in out


def test_reapply_replaces_not_duplicates(renderer: ComponentRenderer) -> None:
    """Applying the same corner twice must not duplicate the declaration."""
    html = '<img style="display:block;" data-node-id="2833:2060" />'
    once = renderer._apply_image_corner_radius(html, "2833:2060", "border-top-left-radius", "6px")
    twice = renderer._apply_image_corner_radius(once, "2833:2060", "border-top-left-radius", "8px")
    assert twice.count("border-top-left-radius") == 1
    assert "border-top-left-radius:8px" in twice
    assert twice.count('style="') == 1


def test_overflow_hidden_stamped_on_parent_td(renderer: ComponentRenderer) -> None:
    html = '<td style="padding:4px;"><img style="display:block;" data-node-id="2833:2060" /></td>'
    out = renderer._apply_image_corner_radius(html, "2833:2060", "border-top-left-radius", "6px")
    assert "overflow:hidden" in out
