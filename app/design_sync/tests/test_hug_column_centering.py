"""Hug-content column-layout centering (Track G · G7, Mechanism 3 / M6).

A ``column-layout`` section whose design columns sum to far less than the
section's own width is an auto-layout HUG row — Figma sizes the frame to its
content. c7's ``Andy | 0`` user-info strip is 4 x 60px columns inside a 440px
section; the equal-split seed renders them as 4 x 138px spread across the
container. ``_apply_hug_column_widths`` pins each ghost ``<td>``/div to its
design px and shrinks the ghost table total, so the seed's own
``text-align:center`` / ghost ``align="center"`` centers the 240px content
strip. Product-card columns that FILL their band (Sum ≈ section width) fall
through byte-identical.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.design_sync.component_matcher import ComponentMatch
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.figma.layout_analyzer import (
    ColumnGroup,
    EmailSection,
    EmailSectionType,
)

_COMPONENT_DIR = Path("email-templates/components")


@pytest.fixture
def renderer() -> ComponentRenderer:
    r = ComponentRenderer(container_width=600)
    r.load()
    return r


def _cols(widths: list[float]) -> list[ColumnGroup]:
    return [
        ColumnGroup(column_idx=i, node_id=f"c{i}", node_name="col", width=w)
        for i, w in enumerate(widths)
    ]


def _match(slug: str, *, width: float, col_widths: list[float]) -> ComponentMatch:
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s",
        node_name="sec",
        width=width,
        column_groups=_cols(col_widths),
    )
    return ComponentMatch(
        section_idx=0,
        section=section,
        component_slug=slug,
        slot_fills=[],
        token_overrides=[],
    )


# ── hug row: 4x60 in a 440 section -> centered 240px strip ─────────────────────


def test_hug_row_renders_at_design_widths(renderer: ComponentRenderer) -> None:
    out = renderer.render_section(
        _match("column-layout-4", width=440.0, col_widths=[60, 60, 60, 60])
    ).html
    assert 'width="60" valign="top"' in out  # ghost td -> design px
    assert "max-width: 60px" in out  # inline-block div -> design px
    assert 'width="240"' in out  # ghost table total = Sum design cols
    assert 'width="600"' not in out  # equal-split total (seed default) gone
    assert 'width="150"' not in out  # equal-split per-col (seed default) gone


# ── fill row: product-card columns (Sum ≈ section) stay byte-identical ──────────


def test_full_width_columns_not_hugged(renderer: ComponentRenderer) -> None:
    baseline = renderer.render_section(
        _match("column-layout-2", width=560.0, col_widths=[])  # no groups -> passthrough
    ).html
    filled = renderer.render_section(
        _match("column-layout-2", width=560.0, col_widths=[250, 250])  # Sum/width=0.89 > 0.7
    ).html
    assert filled == baseline  # not a hug row — seed widths untouched


def test_hug_declines_when_a_width_is_missing(renderer: ComponentRenderer) -> None:
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s",
        node_name="sec",
        width=440.0,
        column_groups=[
            ColumnGroup(column_idx=0, node_id="c0", node_name="c", width=60.0),
            ColumnGroup(column_idx=1, node_id="c1", node_name="c", width=None),
            ColumnGroup(column_idx=2, node_id="c2", node_name="c", width=60.0),
            ColumnGroup(column_idx=3, node_id="c3", node_name="c", width=60.0),
        ],
    )
    match = ComponentMatch(
        section_idx=0,
        section=section,
        component_slug="column-layout-4",
        slot_fills=[],
        token_overrides=[],
    )
    out = renderer.render_section(match).html
    assert 'width="150"' in out  # can't trust the measurement -> equal split kept
