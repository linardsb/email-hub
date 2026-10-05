"""Tests for structure-aware column detection and ColumnGroup preservation."""

from __future__ import annotations

import dataclasses

from app.design_sync.figma.layout_analyzer import (
    ColumnGroup,
    ColumnLayout,
    _build_column_groups,
    _detect_column_layout_with_groups,
    _detect_mj_columns,
    analyze_layout,
)
from app.design_sync.protocol import DesignFileStructure, DesignNode, DesignNodeType


def _node(
    name: str,
    *,
    ntype: DesignNodeType = DesignNodeType.FRAME,
    children: list[DesignNode] | None = None,
    width: float | None = 600,
    height: float | None = 200,
    x: float | None = 0,
    y: float | None = 0,
    text_content: str | None = None,
    fill_color: str | None = None,
    font_size: float | None = None,
    layout_mode: str | None = None,
    image_ref: str | None = None,
) -> DesignNode:
    return DesignNode(
        id=f"id-{name}",
        name=name,
        type=ntype,
        children=children or [],
        width=width,
        height=height,
        x=x,
        y=y,
        text_content=text_content,
        fill_color=fill_color,
        font_size=font_size,
        layout_mode=layout_mode,
        image_ref=image_ref,
    )


def _text_node(name: str, text: str, *, font_size: float = 16) -> DesignNode:
    return _node(
        name,
        ntype=DesignNodeType.TEXT,
        text_content=text,
        width=200,
        height=font_size * 1.5,
        font_size=font_size,
    )


def _image_node(name: str, *, width: float = 300, height: float = 200) -> DesignNode:
    return _node(name, ntype=DesignNodeType.IMAGE, width=width, height=height)


def _make_structure(sections: list[DesignNode]) -> DesignFileStructure:
    page = _node("Page 1", ntype=DesignNodeType.PAGE, children=sections, height=None)
    return DesignFileStructure(file_name="test.fig", pages=[page])


# ── MJML Column Detection ──


class TestDetectMjColumns:
    def test_finds_mj_column_children(self) -> None:
        node = _node(
            "mj-section",
            children=[
                _node(
                    "mj-column",
                    children=[
                        _text_node("mj-text", "Column 1 text"),
                        _image_node("mj-image"),
                    ],
                    width=280,
                ),
                _node(
                    "mj-column",
                    children=[
                        _text_node("mj-text", "Column 2 text"),
                    ],
                    width=280,
                ),
            ],
        )
        columns = _detect_mj_columns(node)
        assert len(columns) == 2
        assert columns[0].column_idx == 1
        assert columns[1].column_idx == 2
        assert len(columns[0].texts) == 1
        assert len(columns[0].images) == 1
        assert len(columns[1].texts) == 1
        assert len(columns[1].images) == 0

    def test_unwraps_nested_mj_section(self) -> None:
        node = _node(
            "mj-wrapper",
            children=[
                _node(
                    "mj-section",
                    children=[
                        _node("mj-column", children=[_text_node("t1", "A")], width=200),
                        _node("mj-column", children=[_text_node("t2", "B")], width=200),
                    ],
                ),
            ],
        )
        columns = _detect_mj_columns(node)
        assert len(columns) == 2

    def test_no_mj_columns_returns_empty(self) -> None:
        node = _node("mj-section", children=[_text_node("t1", "Just text")])
        columns = _detect_mj_columns(node)
        assert columns == []


# ── Auto-Layout Column Detection ──


class TestAutoLayoutColumns:
    def test_horizontal_layout_detects_columns(self) -> None:
        node = _node(
            "Section",
            layout_mode="HORIZONTAL",
            children=[
                _node("Col 1", width=280, height=200, x=0, y=0),
                _node("Col 2", width=280, height=200, x=300, y=0),
            ],
        )
        layout, count, groups = _detect_column_layout_with_groups(node)
        assert layout == ColumnLayout.TWO_COLUMN
        assert count == 2
        assert len(groups) == 2

    def test_horizontal_with_single_wide_child_is_single(self) -> None:
        """Only one child total (no narrow children) → single column."""
        node = _node(
            "Section",
            layout_mode="HORIZONTAL",
            children=[
                _node("Col 1", width=280, height=200, x=0, y=0),
            ],
        )
        layout, _count, _groups = _detect_column_layout_with_groups(node)
        assert layout == ColumnLayout.SINGLE


# ── Position-Based Column Detection ──


class TestPositionColumns:
    def test_y_position_grouping(self) -> None:
        node = _node(
            "Section",
            children=[
                _node("Left", x=0, y=100, width=280, height=200),
                _node("Right", x=300, y=100, width=280, height=200),
            ],
        )
        layout, count, groups = _detect_column_layout_with_groups(node)
        assert layout == ColumnLayout.TWO_COLUMN
        assert count == 2
        assert groups[0].node_name == "Left"
        assert groups[1].node_name == "Right"

    def test_three_columns(self) -> None:
        node = _node(
            "Section",
            children=[
                _node("Col A", x=0, y=100, width=180, height=200),
                _node("Col B", x=200, y=100, width=180, height=200),
                _node("Col C", x=400, y=100, width=180, height=200),
            ],
        )
        layout, count, _groups = _detect_column_layout_with_groups(node)
        assert layout == ColumnLayout.THREE_COLUMN
        assert count == 3

    def test_single_child_no_columns(self) -> None:
        node = _node("Section", children=[_node("Only", x=0, y=0, width=600)])
        layout, count, groups = _detect_column_layout_with_groups(node)
        assert layout == ColumnLayout.SINGLE
        assert count == 1
        assert groups == []


# ── ColumnGroup Content Preservation ──


class TestColumnGroupContentPreservation:
    def test_column_groups_preserve_per_column_content(self) -> None:
        """Key test: image in column 1 stays in column 1, not round-robin shuffled."""
        col1 = _node(
            "Col 1",
            width=280,
            height=200,
            x=0,
            y=0,
            children=[
                _image_node("product-img"),
                _text_node("caption", "Product A"),
            ],
        )
        col2 = _node(
            "Col 2",
            width=280,
            height=200,
            x=300,
            y=0,
            children=[
                _text_node("desc", "Description text"),
            ],
        )
        groups = _build_column_groups([col1, col2])

        assert len(groups) == 2
        # Column 1: has image + text
        assert len(groups[0].images) == 1
        assert groups[0].images[0].node_name == "product-img"
        assert len(groups[0].texts) == 1
        assert groups[0].texts[0].content == "Product A"
        # Column 2: only text
        assert len(groups[1].images) == 0
        assert len(groups[1].texts) == 1
        assert groups[1].texts[0].content == "Description text"


class TestColumnGroupSizing:
    def test_groups_carry_source_horizontal_sizing(self) -> None:
        """CE-6: each column keeps its frame's layoutSizingHorizontal for CE-16."""
        cols = [
            dataclasses.replace(
                _node(name, width=180, x=x, children=[_text_node(f"t-{name}", name)]),
                layout_sizing_horizontal=sizing,
            )
            for name, x, sizing in (("A", 0, "FILL"), ("B", 200, "FILL"), ("C", 400, "FIXED"))
        ]
        groups = _build_column_groups(cols)
        assert [g.sizing_horizontal for g in groups] == ["FILL", "FILL", "FIXED"]

    def test_section_carries_source_horizontal_sizing(self) -> None:
        sections = [
            _node("Header", y=0, height=80),
            dataclasses.replace(
                _node("Body", y=80, height=200, children=[_text_node("t", "Body copy")]),
                layout_sizing_horizontal="FILL",
            ),
        ]
        layout = analyze_layout(_make_structure(sections))
        assert layout.sections[1].sizing_horizontal == "FILL"


# ── Full Pipeline Column Groups ──


class TestAnalyzeLayoutColumnGroups:
    def test_mjml_two_column_produces_groups(self) -> None:
        # Multiple sections to prevent wrapper unwrapping
        sections = [
            _node(
                "mj-section",
                y=0,
                height=200,
                children=[
                    _node(
                        "mj-column",
                        width=280,
                        children=[
                            _image_node("img-left"),
                            _text_node("t1", "Left text"),
                        ],
                    ),
                    _node(
                        "mj-column",
                        width=280,
                        children=[
                            _text_node("t2", "Right text"),
                        ],
                    ),
                ],
            ),
            _node(
                "mj-section",
                y=200,
                height=100,
                children=[
                    _node("mj-column", children=[_text_node("t3", "Footer")]),
                ],
            ),
        ]
        structure = _make_structure(sections)
        layout = analyze_layout(structure, naming_convention="mjml")

        assert len(layout.sections) >= 2
        section = layout.sections[0]
        assert section.column_layout == ColumnLayout.TWO_COLUMN
        assert section.column_count == 2
        assert len(section.column_groups) == 2
        assert len(section.column_groups[0].images) == 1
        assert len(section.column_groups[1].images) == 0

    def test_auto_layout_horizontal_produces_groups(self) -> None:
        # Need multiple top-level sections to avoid wrapper unwrapping
        sections = [
            _node("Header", y=0, height=80),
            _node(
                "Content",
                y=80,
                height=200,
                layout_mode="HORIZONTAL",
                children=[
                    _node(
                        "Left",
                        width=280,
                        height=200,
                        children=[
                            _text_node("t1", "A"),
                        ],
                    ),
                    _node(
                        "Right",
                        width=280,
                        height=200,
                        children=[
                            _text_node("t2", "B"),
                        ],
                    ),
                ],
            ),
        ]
        structure = _make_structure(sections)
        layout = analyze_layout(structure)

        # Second section is the horizontal one
        section = layout.sections[1]
        assert section.column_count == 2
        assert len(section.column_groups) == 2


# ── Component Matcher with Column Groups ──


class TestComponentMatcherColumnGroups:
    def test_column_fills_from_groups(self) -> None:
        from app.design_sync.component_matcher import _build_column_fills_from_groups
        from app.design_sync.figma.layout_analyzer import (
            ButtonElement,
            ImagePlaceholder,
            TextBlock,
        )

        groups = [
            ColumnGroup(
                column_idx=1,
                node_id="col1",
                node_name="Col 1",
                texts=[TextBlock(node_id="t1", content="Hello")],
                images=[ImagePlaceholder(node_id="img1", node_name="Logo")],
                buttons=[],
                width=280,
            ),
            ColumnGroup(
                column_idx=2,
                node_id="col2",
                node_name="Col 2",
                texts=[TextBlock(node_id="t2", content="World")],
                images=[],
                buttons=[ButtonElement(node_id="b1", text="Click")],
                width=280,
            ),
        ]
        fills = _build_column_fills_from_groups(groups)
        assert len(fills) == 2
        assert fills[0].slot_id == "col_1"
        assert "img1" in fills[0].value
        assert "Hello" in fills[0].value
        assert fills[1].slot_id == "col_2"
        assert "World" in fills[1].value
        assert "Click" in fills[1].value


# ── Image Ref on Frames ──


class TestImageRefDetection:
    def test_frame_with_image_ref_detected_as_background(self) -> None:
        frame = _node(
            "Hero Banner",
            image_ref="abc123",
            width=600,
            height=400,
            children=[
                _text_node("headline", "Welcome", font_size=36),
            ],
        )
        sections = [frame]
        structure = _make_structure(sections)
        layout = analyze_layout(structure)

        section = layout.sections[0]
        bg_images = [img for img in section.images if img.is_background]
        assert len(bg_images) == 1
        assert bg_images[0].node_name == "Hero Banner"
