"""Item 1 (phase-53.5-nested-divider-render-gap): nested mj-divider rules render.

53.5 recovers a divider stroke only when the mj-divider frame IS a section
(case 9). Two nested placements lost the rule:

- **case 8 (column-child):** a zero-area LINE inside an mj-column is dropped by
  the image walk; its stroke must render as a border-top row at its design
  y-position within the column fill.
- **case 10 (band-absorbed):** a DIVIDER pseudo-section absorbed by
  ``group_by_wrapper``'s ``absorb_spacers`` must re-inject a border-top rule row
  between the band members it separated (absorption/member-count unchanged).

Both tests drive the REAL pipeline end-to-end (case 8: mj-column ingest →
DocumentColumn round-trip → column render; case 10: group_by_wrapper →
render_repeating_group) so a missing link in the ~10-step chain surfaces here.
"""

from __future__ import annotations

import pytest

from app.design_sync.component_matcher import (
    ComponentMatch,
    SlotFill,
    _build_column_fill_html,
)
from app.design_sync.component_renderer import ComponentRenderer
from app.design_sync.email_design_document import DocumentColumn
from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    TextBlock,
    _detect_mj_columns,
)
from app.design_sync.protocol import DesignNode, DesignNodeType
from app.design_sync.sibling_detector import RepeatingGroup, group_by_wrapper

# ── case 8: in-column divider ────────────────────────────────────────────


def _text_frame(node_id: str, content: str) -> DesignNode:
    text = DesignNode(
        id=f"{node_id}-t",
        name="mj-text",
        type=DesignNodeType.TEXT,
        text_content=content,
        width=520.0,
        height=40.0,
        font_family="Noto Sans",
        font_size=14.0,
        text_color="#000000",
    )
    return DesignNode(
        id=node_id,
        name="mj-text-Frame",
        type=DesignNodeType.FRAME,
        children=[text],
        width=520.0,
        height=40.0,
    )


def _mj_column_with_divider(stroke: str = "#373737") -> DesignNode:
    """c8 shape: mj-column [text, mj-divider-Frame(zero-area LINE), text]."""
    divider_vec = DesignNode(
        id="2833:2365",
        name="mj-divider",
        type=DesignNodeType.VECTOR,
        width=520.0,
        height=0.0,  # zero-area LINE — the image walk drops it
        stroke_color=stroke,
        stroke_weight=1.0,
    )
    divider_frame = DesignNode(
        id="2833:2364",
        name="mj-divider-Frame",
        type=DesignNodeType.FRAME,
        children=[divider_vec],
        width=520.0,
        height=3.0,
    )
    column = DesignNode(
        id="2833:2350",
        name="mj-column",
        type=DesignNodeType.FRAME,
        children=[
            _text_frame("tf-above", "Above divider"),
            divider_frame,
            _text_frame("tf-below", "Below divider"),
        ],
        width=520.0,
        height=90.0,
    )
    section = DesignNode(
        id="sec",
        name="mj-section",
        type=DesignNodeType.FRAME,
        children=[column],
        width=520.0,
        height=90.0,
    )
    return DesignNode(
        id="root",
        name="root",
        type=DesignNodeType.FRAME,
        children=[section],
        width=520.0,
        height=90.0,
    )


class TestColumnChildDivider:
    def test_in_column_divider_renders_border_top_between_texts(self) -> None:
        groups = _detect_mj_columns(_mj_column_with_divider())
        assert len(groups) == 1
        # Round-trip through the DocumentColumn persistence bridge (the corpus
        # render path: from_column_group → to_json → from_json → to_column_group).
        cg = DocumentColumn.from_json(
            DocumentColumn.from_column_group(groups[0]).to_json()
        ).to_column_group()
        html = _build_column_fill_html(cg)
        # the killed defect: the zero-area LINE was dropped, so no rule rendered.
        assert "border-top:1px solid #373737" in html
        # rule lands at the LINE's y-position — between the two texts.
        assert (
            html.index("Above divider")
            < html.index("border-top:1px solid #373737")
            < html.index("Below divider")
        )


# ── case 10: band-absorbed divider ───────────────────────────────────────


def _card(idx: int, wrapper_id: str = "2833:1240") -> EmailSection:
    return EmailSection(
        section_type=EmailSectionType.CONTENT,
        node_id=f"card_{idx}",
        node_name=f"Card {idx}",
        texts=[TextBlock(node_id=f"t_{idx}", content=f"Reason {idx}", is_heading=True)],
        images=[],
        buttons=[],
        column_layout=ColumnLayout.SINGLE,
        column_count=1,
        height=200.0,
        bg_color="#FFFFFF",
        parent_wrapper_id=wrapper_id,
        container_bg="#FFFFFF",
    )


def _band_divider(stroke: str = "#C7CCCF", wrapper_id: str = "2833:1240") -> EmailSection:
    return EmailSection(
        section_type=EmailSectionType.DIVIDER,
        node_id="div_0",
        node_name="Divider",
        stroke_color=stroke,
        stroke_weight=1.0,
        parent_wrapper_id=wrapper_id,
        container_bg="#FFFFFF",
    )


def _group_match(idx: int, section: EmailSection) -> ComponentMatch:
    return ComponentMatch(
        section_idx=idx,
        section=section,
        component_slug="col-icon",
        slot_fills=[SlotFill(slot_id="heading_1", value=f"Reason {idx}")],
        token_overrides=[],
    )


@pytest.fixture
def renderer() -> ComponentRenderer:
    r = ComponentRenderer(container_width=600)
    r.load()
    return r


class TestBandAbsorbedDivider:
    def test_absorbed_divider_reinjects_rule_between_members(
        self, renderer: ComponentRenderer
    ) -> None:
        # [card, DIVIDER(stroke), card] — the divider is absorbed (A2-ratified)
        # but its stroke must re-inject a rule row between the two cards.
        grouped = group_by_wrapper([_card(0), _band_divider(), _card(1)])
        assert len(grouped) == 1
        group = grouped[0]
        assert isinstance(group, RepeatingGroup)
        assert len(group.sections) == 2  # absorption preserved — member count unchanged

        matches = [_group_match(i, s) for i, s in enumerate(group.sections)]
        html = renderer.render_repeating_group(group, matches).html
        # the killed defect: absorb_spacers dropped the divider before render.
        assert "border-top:1px solid #C7CCCF" in html
        assert (
            html.index("Reason 0")
            < html.index("border-top:1px solid #C7CCCF")
            < html.index("Reason 1")
        )
