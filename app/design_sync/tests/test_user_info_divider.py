"""User-info column border-left divider (Track G · G7, Mechanism 4 / M6).

c7's ``Andy | 0`` count group carries a per-column Figma stroke (#D9D9D9, 1px)
that reads as a vertical divider between the name group and the count group.
``ColumnGroup`` gains the uniform stroke (captured from the source
``mj-column`` node) and the renderer emits it as ``border-left`` on that
column's content cell — NOT a full box (which would read as a rectangle). Only
the uniform stroke is captured; true per-side ``individualStrokeWeights`` are
ledgered (phase-53g-g7-per-side-stroke-capture).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.design_sync.component_matcher import ComponentMatch
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.email_design_document import DocumentColumn
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


def _cols(stroke_on: int | None) -> list[ColumnGroup]:
    out: list[ColumnGroup] = []
    for i in range(4):
        sc = "#D9D9D9" if i == stroke_on else None
        sw = 1.0 if i == stroke_on else None
        out.append(
            ColumnGroup(
                column_idx=i,
                node_id=f"c{i}",
                node_name="col",
                width=60.0,
                stroke_color=sc,
                stroke_weight=sw,
            )
        )
    return out


def _match(stroke_on: int | None) -> ComponentMatch:
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s",
        node_name="sec",
        width=440.0,
        column_groups=_cols(stroke_on),
    )
    return ComponentMatch(
        section_idx=0,
        section=section,
        component_slug="column-layout-4",
        slot_fills=[],
        token_overrides=[],
    )


# ── render: border-left on the stroked column's content cell ──────────────────


def test_stroked_column_emits_border_left(renderer: ComponentRenderer) -> None:
    # Exercise the method on the real seed markup — an empty-fill render blanks
    # the col_N cells (dropping data-slot), while the live pipeline fills them.
    seed = renderer._templates["column-layout-4"]
    out = renderer._apply_column_dividers(seed, _match(stroke_on=2))  # col_3
    assert 'data-slot="col_3" style="border-left:1px solid #D9D9D9;' in out
    # border-LEFT only — never a full box
    assert "border:1px" not in out


def test_no_stroke_no_border(renderer: ComponentRenderer) -> None:
    out = renderer.render_section(_match(stroke_on=None)).html
    assert "border-left" not in out


def test_non_hug_stroked_column_has_no_divider(renderer: ComponentRenderer) -> None:
    # A full-width 2-column layout with a stroke (c9's Place|Temperature shape,
    # Sum≈section width) is NOT a hug row — the divider must not fire (a left
    # border on the first column would be wrong; box-vs-divider needs per-side
    # strokes, ledgered).
    seed = renderer._templates["column-layout-2"]
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s",
        node_name="sec",
        width=560.0,
        column_groups=[
            ColumnGroup(
                column_idx=0,
                node_id="c0",
                node_name="c",
                width=270.0,
                stroke_color="#545454",
                stroke_weight=1.0,
            ),
            ColumnGroup(
                column_idx=1,
                node_id="c1",
                node_name="c",
                width=270.0,
                stroke_color="#545454",
                stroke_weight=1.0,
            ),
        ],
    )
    match = ComponentMatch(
        section_idx=0,
        section=section,
        component_slug="column-layout-2",
        slot_fills=[],
        token_overrides=[],
    )
    assert "border-left" not in renderer._apply_column_dividers(seed, match)


def test_non_hex_stroke_is_dropped(renderer: ComponentRenderer) -> None:
    section = EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id="s",
        node_name="sec",
        width=440.0,
        column_groups=[
            ColumnGroup(column_idx=0, node_id="c0", node_name="c", width=60.0),
            ColumnGroup(
                column_idx=1,
                node_id="c1",
                node_name="c",
                width=60.0,
                stroke_color="url(javascript:alert(1))",
                stroke_weight=1.0,
            ),
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
    assert "border-left" not in out  # malformed color dropped


# ── #327 round-trip: stroke survives DocumentColumn serialization ─────────────


def test_column_stroke_survives_json_round_trip() -> None:
    cg = ColumnGroup(
        column_idx=2,
        node_id="c2",
        node_name="mj-column",
        width=60.0,
        stroke_color="#D9D9D9",
        stroke_weight=1.0,
    )
    restored = DocumentColumn.from_json(
        DocumentColumn.from_column_group(cg).to_json()
    ).to_column_group()
    assert restored.stroke_color == "#D9D9D9"
    assert restored.stroke_weight == 1.0
