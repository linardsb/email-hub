"""Tests for layout analyzer and brief generator — pure unit tests, no DB/IO."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.design_sync.brief_generator import generate_brief
from app.design_sync.diagnose.report import load_structure_from_json
from app.design_sync.figma.layout_analyzer import (
    ColumnLayout,
    DesignLayoutDescription,
    EmailSectionType,
    TextBlock,
    _classify_by_name,
    _detect_content_hierarchy,
    _has_large_image_child,
    analyze_layout,
)
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExtractedColor,
    ExtractedSpacing,
    ExtractedTokens,
    ExtractedTypography,
)

# ── Fixtures ──


def make_email_structure() -> DesignFileStructure:
    """Create a realistic email design structure for testing."""
    return DesignFileStructure(
        file_name="Campaign Email",
        pages=[
            DesignNode(
                id="page1",
                name="Email",
                type=DesignNodeType.PAGE,
                children=[
                    DesignNode(
                        id="f1",
                        name="Header",
                        type=DesignNodeType.FRAME,
                        x=0,
                        y=0,
                        width=600,
                        height=80,
                        children=[
                            DesignNode(
                                id="img0",
                                name="Logo",
                                type=DesignNodeType.IMAGE,
                                x=20,
                                y=20,
                                width=120,
                                height=40,
                            ),
                        ],
                    ),
                    DesignNode(
                        id="f2",
                        name="Hero",
                        type=DesignNodeType.FRAME,
                        x=0,
                        y=80,
                        width=600,
                        height=300,
                        children=[
                            DesignNode(
                                id="img1",
                                name="hero-image",
                                type=DesignNodeType.IMAGE,
                                x=0,
                                y=80,
                                width=600,
                                height=200,
                            ),
                            DesignNode(
                                id="t2",
                                name="headline",
                                type=DesignNodeType.TEXT,
                                x=20,
                                y=290,
                                width=560,
                                height=40,
                                text_content="Summer Sale is Here!",
                            ),
                            DesignNode(
                                id="t3",
                                name="subhead",
                                type=DesignNodeType.TEXT,
                                x=20,
                                y=330,
                                width=560,
                                height=20,
                                text_content="Get 50% off everything",
                            ),
                        ],
                    ),
                    DesignNode(
                        id="f3",
                        name="Content Section",
                        type=DesignNodeType.FRAME,
                        x=0,
                        y=400,
                        width=600,
                        height=200,
                        children=[
                            DesignNode(
                                id="t4",
                                name="body",
                                type=DesignNodeType.TEXT,
                                x=20,
                                y=410,
                                width=560,
                                height=16,
                                text_content="Check out our latest collection.",
                            ),
                        ],
                    ),
                    DesignNode(
                        id="f4",
                        name="CTA Section",
                        type=DesignNodeType.FRAME,
                        x=0,
                        y=620,
                        width=600,
                        height=60,
                        children=[
                            DesignNode(
                                id="btn1",
                                name="button-cta",
                                type=DesignNodeType.FRAME,
                                x=200,
                                y=630,
                                width=200,
                                height=48,
                                children=[
                                    DesignNode(
                                        id="btn1-text",
                                        name="button-label",
                                        type=DesignNodeType.TEXT,
                                        x=220,
                                        y=640,
                                        width=160,
                                        height=20,
                                        text_content="Shop Now",
                                    ),
                                ],
                            ),
                        ],
                    ),
                    DesignNode(
                        id="f5",
                        name="Footer",
                        type=DesignNodeType.FRAME,
                        x=0,
                        y=700,
                        width=600,
                        height=100,
                        children=[
                            DesignNode(
                                id="t5",
                                name="legal",
                                type=DesignNodeType.TEXT,
                                x=20,
                                y=710,
                                width=560,
                                height=14,
                                text_content="Unsubscribe | Privacy Policy",
                            ),
                        ],
                    ),
                ],
            )
        ],
    )


# ── LayoutAnalyzer tests ──


class TestNameBasedDetection:
    def test_header_detected(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        assert layout.sections[0].section_type == EmailSectionType.HEADER

    def test_hero_detected(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        assert layout.sections[1].section_type == EmailSectionType.HERO

    def test_content_detected(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        assert layout.sections[2].section_type == EmailSectionType.CONTENT

    def test_cta_detected(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        assert layout.sections[3].section_type == EmailSectionType.CTA

    def test_footer_detected(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        assert layout.sections[4].section_type == EmailSectionType.FOOTER


class TestPositionBasedFallback:
    def test_first_frame_is_header(self) -> None:
        """Unnamed frames: first -> HEADER."""
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="a",
                            name="Section A",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=80,
                        ),
                        DesignNode(
                            id="b",
                            name="Section B",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=100,
                            width=600,
                            height=80,
                        ),
                        DesignNode(
                            id="c",
                            name="Section C",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=200,
                            width=600,
                            height=80,
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        assert layout.sections[0].section_type == EmailSectionType.HEADER

    def test_last_frame_is_footer(self) -> None:
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="a",
                            name="Section A",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=80,
                        ),
                        DesignNode(
                            id="b",
                            name="Section B",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=100,
                            width=600,
                            height=80,
                        ),
                        DesignNode(
                            id="c",
                            name="Section C",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=200,
                            width=600,
                            height=80,
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        assert layout.sections[-1].section_type == EmailSectionType.FOOTER

    def test_middle_with_large_image_is_hero(self) -> None:
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="a",
                            name="Section A",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=80,
                        ),
                        DesignNode(
                            id="b",
                            name="Section B",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=100,
                            width=600,
                            height=300,
                            children=[
                                DesignNode(
                                    id="img",
                                    name="big-img",
                                    type=DesignNodeType.IMAGE,
                                    x=0,
                                    y=100,
                                    width=500,
                                    height=280,
                                ),
                            ],
                        ),
                        DesignNode(
                            id="c",
                            name="Section C",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=400,
                            width=600,
                            height=80,
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        assert layout.sections[1].section_type == EmailSectionType.HERO


class TestColumnDetection:
    def test_two_column(self) -> None:
        """Two sibling frames at same y -> TWO_COLUMN.

        Uses two top-level frames so the wrapper-unwrap heuristic doesn't
        collapse the structure (single wrapper with >=2 inner frames gets
        unwrapped into separate sections).
        """
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="header",
                            name="Header",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=80,
                        ),
                        DesignNode(
                            id="row",
                            name="Content Row",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=80,
                            width=600,
                            height=200,
                            children=[
                                DesignNode(
                                    id="col1",
                                    name="Left",
                                    type=DesignNodeType.FRAME,
                                    x=0,
                                    y=0,
                                    width=290,
                                    height=200,
                                ),
                                DesignNode(
                                    id="col2",
                                    name="Right",
                                    type=DesignNodeType.FRAME,
                                    x=310,
                                    y=0,
                                    width=290,
                                    height=200,
                                ),
                            ],
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        # Second section (Content Row) should detect 2-column layout
        assert layout.sections[1].column_layout == ColumnLayout.TWO_COLUMN
        assert layout.sections[1].column_count == 2

    def test_three_column(self) -> None:
        """Three sibling frames at same y -> THREE_COLUMN.

        Uses two top-level frames to prevent single-wrapper unwrapping.
        """
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="header",
                            name="Header",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=80,
                        ),
                        DesignNode(
                            id="row",
                            name="Content Row",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=80,
                            width=600,
                            height=200,
                            children=[
                                DesignNode(
                                    id="c1",
                                    name="Col1",
                                    type=DesignNodeType.FRAME,
                                    x=0,
                                    y=0,
                                    width=190,
                                    height=200,
                                ),
                                DesignNode(
                                    id="c2",
                                    name="Col2",
                                    type=DesignNodeType.FRAME,
                                    x=200,
                                    y=0,
                                    width=190,
                                    height=200,
                                ),
                                DesignNode(
                                    id="c3",
                                    name="Col3",
                                    type=DesignNodeType.FRAME,
                                    x=400,
                                    y=0,
                                    width=190,
                                    height=200,
                                ),
                            ],
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        assert layout.sections[1].column_layout == ColumnLayout.THREE_COLUMN

    def test_single_column_vertical_stack(self) -> None:
        """Children stacked vertically -> SINGLE."""
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="stack",
                            name="Content Stack",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=400,
                            children=[
                                DesignNode(
                                    id="r1",
                                    name="Row1",
                                    type=DesignNodeType.FRAME,
                                    x=0,
                                    y=0,
                                    width=600,
                                    height=100,
                                ),
                                DesignNode(
                                    id="r2",
                                    name="Row2",
                                    type=DesignNodeType.FRAME,
                                    x=0,
                                    y=120,
                                    width=600,
                                    height=100,
                                ),
                            ],
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        assert layout.sections[0].column_layout == ColumnLayout.SINGLE


class TestTextExtraction:
    def test_text_nodes_yield_blocks(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        # Hero section should have text blocks
        hero = layout.sections[1]
        assert len(hero.texts) >= 2
        texts = [t.content for t in hero.texts]
        assert "Summer Sale is Here!" in texts

    def test_content_hierarchy(self) -> None:
        """Largest font size text marked as heading."""
        structure = make_email_structure()
        layout = analyze_layout(structure)
        hero = layout.sections[1]
        headings = [t for t in hero.texts if t.is_heading]
        assert len(headings) >= 1
        assert headings[0].content == "Summer Sale is Here!"


class TestImageDetection:
    def test_image_node_detected(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        hero = layout.sections[1]
        assert len(hero.images) >= 1
        assert hero.images[0].node_name == "hero-image"

    def test_frame_wrapping_image(self) -> None:
        """FRAME with single IMAGE child -> also detected."""
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="f1",
                            name="Image Wrapper",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=300,
                            children=[
                                DesignNode(
                                    id="wrapper",
                                    name="wrapper-frame",
                                    type=DesignNodeType.FRAME,
                                    x=0,
                                    y=0,
                                    width=600,
                                    height=300,
                                    children=[
                                        DesignNode(
                                            id="img",
                                            name="photo",
                                            type=DesignNodeType.IMAGE,
                                            x=0,
                                            y=0,
                                            width=600,
                                            height=300,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        assert len(layout.sections[0].images) >= 1


class TestButtonDetection:
    def test_button_detected(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        cta = layout.sections[3]
        assert len(cta.buttons) >= 1
        assert cta.buttons[0].text == "Shop Now"


class TestSectionSpacing:
    def test_spacing_calculated(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        # Header (y=0, h=80) -> Hero (y=80) => spacing = 0
        assert layout.sections[0].spacing_after == 0.0


class TestPreheaderDetection:
    def test_preheader_by_name(self) -> None:
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="ph",
                            name="Preheader",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=20,
                            children=[
                                DesignNode(
                                    id="pt",
                                    name="preview-text",
                                    type=DesignNodeType.TEXT,
                                    x=0,
                                    y=0,
                                    width=600,
                                    height=12,
                                    text_content="Preview text goes here",
                                ),
                            ],
                        ),
                        DesignNode(
                            id="f2",
                            name="Main",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=30,
                            width=600,
                            height=400,
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        assert layout.sections[0].section_type == EmailSectionType.PREHEADER


class TestEmptyStructure:
    def test_no_pages(self) -> None:
        structure = DesignFileStructure(file_name="Empty")
        layout = analyze_layout(structure)
        assert layout.sections == []
        assert layout.total_text_blocks == 0
        assert layout.total_images == 0


class TestDeepNesting:
    def test_text_in_nested_frames(self) -> None:
        """Text 3+ levels deep still extracted."""
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="f1",
                            name="Content",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=400,
                            children=[
                                DesignNode(
                                    id="g1",
                                    name="Group",
                                    type=DesignNodeType.GROUP,
                                    x=0,
                                    y=0,
                                    width=600,
                                    height=400,
                                    children=[
                                        DesignNode(
                                            id="g2",
                                            name="Inner",
                                            type=DesignNodeType.GROUP,
                                            x=0,
                                            y=0,
                                            width=600,
                                            height=400,
                                            children=[
                                                DesignNode(
                                                    id="t1",
                                                    name="deep-text",
                                                    type=DesignNodeType.TEXT,
                                                    x=20,
                                                    y=20,
                                                    width=560,
                                                    height=20,
                                                    text_content="Deep nested text",
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        assert layout.total_text_blocks == 1
        assert layout.sections[0].texts[0].content == "Deep nested text"


# ── BriefGenerator tests ──


class TestBriefGeneratorFull:
    def test_full_brief(self) -> None:
        """Layout with all sections -> valid markdown."""
        structure = make_email_structure()
        layout = analyze_layout(structure)
        brief = generate_brief(layout)
        assert "# Campaign Email Brief" in brief
        assert "## Sections" in brief
        assert "Header" in brief
        assert "Hero" in brief
        assert "Footer" in brief

    def test_with_tokens(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        tokens = ExtractedTokens(
            colors=[ExtractedColor(name="Primary", hex="#FF5733")],
            typography=[
                ExtractedTypography(
                    name="Body", family="Inter", weight="400", size=16, line_height=24
                )
            ],
            spacing=[ExtractedSpacing(name="s-16", value=16)],
        )
        brief = generate_brief(layout, tokens=tokens)
        assert "## Design Tokens" in brief
        assert "#FF5733" in brief
        assert "Inter" in brief

    def test_with_asset_urls(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        brief = generate_brief(layout, asset_url_prefix="/api/v1/design-sync/assets/5")
        # Verify proper Markdown link format: [name](url)
        assert "(/api/v1/design-sync/assets/5/" in brief

    def test_truncation(self) -> None:
        """Brief exceeding 4000 chars is truncated."""
        # Create a structure with many text-heavy sections
        children: list[DesignNode] = []
        for i in range(30):
            children.append(
                DesignNode(
                    id=f"f{i}",
                    name=f"Content {i}",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=i * 200,
                    width=600,
                    height=180,
                    children=[
                        DesignNode(
                            id=f"t{i}",
                            name=f"text-{i}",
                            type=DesignNodeType.TEXT,
                            x=20,
                            y=i * 200 + 10,
                            width=560,
                            height=20,
                            text_content=f"This is a very long text block number {i} with lots of content "
                            * 5,
                        ),
                    ],
                )
            )
        structure = DesignFileStructure(
            file_name="Long",
            pages=[DesignNode(id="p1", name="Page", type=DesignNodeType.PAGE, children=children)],
        )
        layout = analyze_layout(structure)
        brief = generate_brief(layout)
        assert len(brief) <= 4000
        assert "# Campaign Email Brief" in brief

    def test_two_column_brief(self) -> None:
        """2-column section -> '2-column' in brief.

        Uses two top-level frames to prevent single-wrapper unwrapping.
        """
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="header",
                            name="Header",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=80,
                        ),
                        DesignNode(
                            id="row",
                            name="Content Row",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=80,
                            width=600,
                            height=200,
                            children=[
                                DesignNode(
                                    id="c1",
                                    name="Left",
                                    type=DesignNodeType.FRAME,
                                    x=0,
                                    y=0,
                                    width=290,
                                    height=200,
                                ),
                                DesignNode(
                                    id="c2",
                                    name="Right",
                                    type=DesignNodeType.FRAME,
                                    x=310,
                                    y=0,
                                    width=290,
                                    height=200,
                                ),
                            ],
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        brief = generate_brief(layout)
        assert "2-column" in brief

    def test_empty_layout(self) -> None:
        """No sections -> minimal valid brief."""
        layout = DesignLayoutDescription(file_name="Empty")
        brief = generate_brief(layout)
        assert "# Campaign Email Brief" in brief
        assert "no sections" in brief


class TestFilterStructure:
    def test_matching_node_returned(self) -> None:
        from app.design_sync.service import _filter_structure

        structure = make_email_structure()
        filtered = _filter_structure(structure, ["f2"])  # Hero frame
        # Page should be preserved, only f2 child kept
        assert len(filtered.pages) == 1
        assert len(filtered.pages[0].children) == 1
        assert filtered.pages[0].children[0].id == "f2"

    def test_no_match_returns_empty(self) -> None:
        from app.design_sync.service import _filter_structure

        structure = make_email_structure()
        filtered = _filter_structure(structure, ["nonexistent"])
        assert filtered.pages == []

    def test_multiple_matches(self) -> None:
        from app.design_sync.service import _filter_structure

        structure = make_email_structure()
        filtered = _filter_structure(structure, ["f1", "f5"])
        assert len(filtered.pages) == 1
        children_ids = [c.id for c in filtered.pages[0].children]
        assert "f1" in children_ids
        assert "f5" in children_ids


class TestLayoutOverallWidth:
    def test_width_from_widest_frame(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        assert layout.overall_width == 600.0


class TestTypographyFromDesignNode:
    def test_actual_font_size_used(self) -> None:
        """TextBlock uses DesignNode.font_size (actual), not bounding box height."""
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="f1",
                            name="Content",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=200,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="text",
                                    type=DesignNodeType.TEXT,
                                    x=20,
                                    y=20,
                                    width=560,
                                    height=50,  # bounding box
                                    text_content="Hello World",
                                    font_size=32.0,  # actual font size
                                    font_family="Inter",
                                    font_weight=700,
                                    line_height_px=40.0,
                                    letter_spacing_px=0.5,
                                ),
                            ],
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        text = layout.sections[0].texts[0]
        assert text.font_size == 32.0  # actual, not 50 (height)
        assert text.font_family == "Inter"
        assert text.font_weight == 700
        assert text.line_height == 40.0
        assert text.letter_spacing == 0.5

    def test_fallback_to_height_without_font_size(self) -> None:
        """TextBlock falls back to bounding box height when font_size is None."""
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="f1",
                            name="Content",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=200,
                            children=[
                                DesignNode(
                                    id="t1",
                                    name="text",
                                    type=DesignNodeType.TEXT,
                                    x=20,
                                    y=20,
                                    width=560,
                                    height=20,
                                    text_content="Legacy text",
                                ),
                            ],
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        text = layout.sections[0].texts[0]
        assert text.font_size == 20.0  # falls back to height


class TestSectionSpacingFromDesignNode:
    def test_padding_captured(self) -> None:
        """EmailSection captures padding from DesignNode auto-layout."""
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="f1",
                            name="Content",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=200,
                            padding_top=32.0,
                            padding_right=24.0,
                            padding_bottom=32.0,
                            padding_left=24.0,
                            item_spacing=16.0,
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        section = layout.sections[0]
        assert section.padding_top == 32.0
        assert section.padding_right == 24.0
        assert section.item_spacing == 16.0


class TestGenerateSpacingMap:
    def test_spacing_map_generated(self) -> None:
        """generate_spacing_map produces per-section dict."""
        structure = DesignFileStructure(
            file_name="Test",
            pages=[
                DesignNode(
                    id="p1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="f1",
                            name="Content",
                            type=DesignNodeType.FRAME,
                            x=0,
                            y=0,
                            width=600,
                            height=200,
                            padding_top=32.0,
                            item_spacing=16.0,
                        ),
                    ],
                )
            ],
        )
        layout = analyze_layout(structure)
        assert "f1" in layout.spacing_map
        assert layout.spacing_map["f1"]["padding_top"] == 32.0
        assert layout.spacing_map["f1"]["item_spacing"] == 16.0


class TestSortByYPosition:
    def test_sections_sorted_top_to_bottom(self) -> None:
        structure = make_email_structure()
        layout = analyze_layout(structure)
        y_positions = [s.y_position for s in layout.sections if s.y_position is not None]
        assert y_positions == sorted(y_positions)


# ── 38.3 Bug Fix Tests ──


def _make_text_node(
    node_id: str,
    text: str,
    font_size: float = 16.0,
    **kw: object,
) -> DesignNode:
    return DesignNode(
        id=node_id,
        name=f"text-{node_id}",
        type=DesignNodeType.TEXT,
        text_content=text,
        font_size=font_size,
        **kw,  # type: ignore[arg-type]
    )


def _make_button_frame(
    node_id: str,
    text: str,
    *,
    fill_color: str | None = "#FF0000",
    width: float = 200,
    height: float = 50,
) -> DesignNode:
    text_child = _make_text_node(f"{node_id}-text", text)
    return DesignNode(
        id=node_id,
        name="button",
        type=DesignNodeType.FRAME,
        children=[text_child],
        fill_color=fill_color,
        width=width,
        height=height,
    )


def _make_section_structure(
    sections: list[DesignNode],
) -> DesignFileStructure:
    return DesignFileStructure(
        file_name="test",
        pages=[
            DesignNode(
                id="page1",
                name="Email",
                type=DesignNodeType.PAGE,
                children=sections,
            )
        ],
    )


class TestHeadingDetectionFixes:
    """Bug 11-12: heading threshold uses 1.3x median, uniform sizes → no headings."""

    def test_uniform_sizes_no_headings(self) -> None:
        texts = [
            TextBlock(node_id="a", content="One", font_size=16.0),
            TextBlock(node_id="b", content="Two", font_size=16.0),
            TextBlock(node_id="c", content="Three", font_size=16.0),
        ]
        result = _detect_content_hierarchy(texts)
        assert all(not t.is_heading for t in result)

    def test_small_ratio_not_heading(self) -> None:
        """18px vs 16px body = 1.125x median — NOT heading (< 1.3x)."""
        texts = [
            TextBlock(node_id="a", content="Body text", font_size=16.0),
            TextBlock(node_id="b", content="Slightly larger", font_size=18.0),
        ]
        result = _detect_content_hierarchy(texts)
        assert not any(t.is_heading for t in result)

    def test_large_ratio_is_heading(self) -> None:
        """32px vs 16px body → median=16, threshold=20.8 → IS heading."""
        texts = [
            TextBlock(node_id="a", content="Body text", font_size=16.0),
            TextBlock(node_id="b", content="More body", font_size=16.0),
            TextBlock(node_id="c", content="Title", font_size=32.0),
        ]
        result = _detect_content_hierarchy(texts)
        headings = [t for t in result if t.is_heading]
        assert len(headings) == 1
        assert headings[0].content == "Title"

    def test_median_based_threshold(self) -> None:
        """[12, 14, 16, 16, 32] → median=16, threshold=20.8 → only 32 is heading."""
        texts = [
            TextBlock(node_id="a", content="Small", font_size=12.0),
            TextBlock(node_id="b", content="Medium", font_size=14.0),
            TextBlock(node_id="c", content="Body", font_size=16.0),
            TextBlock(node_id="d", content="Body2", font_size=16.0),
            TextBlock(node_id="e", content="Heading", font_size=32.0),
        ]
        result = _detect_content_hierarchy(texts)
        headings = [t for t in result if t.is_heading]
        assert len(headings) == 1
        assert headings[0].content == "Heading"


class TestFooterClassificationFixes:
    """Bug 13: footer requires position near bottom AND legal text."""

    def test_legal_text_mid_email_not_footer(self) -> None:
        """© text at index 1 of 5 → should NOT be FOOTER."""
        structure = _make_section_structure(
            [
                DesignNode(
                    id="s0",
                    name="Frame 0",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=80,
                ),
                DesignNode(
                    id="s1",
                    name="Frame 1",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=100,
                    width=600,
                    height=200,
                    children=[_make_text_node("t1", "© 2024 Company. All rights reserved.")],
                ),
                DesignNode(
                    id="s2",
                    name="Frame 2",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=300,
                    width=600,
                    height=200,
                ),
                DesignNode(
                    id="s3",
                    name="Frame 3",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=500,
                    width=600,
                    height=200,
                ),
                DesignNode(
                    id="s4",
                    name="Frame 4",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=700,
                    width=600,
                    height=100,
                ),
            ]
        )
        layout = analyze_layout(structure)
        section_1 = next(s for s in layout.sections if s.node_id == "s1")
        assert section_1.section_type != EmailSectionType.FOOTER

    def test_legal_text_bottom_is_footer(self) -> None:
        """© text at last position → FOOTER."""
        structure = _make_section_structure(
            [
                DesignNode(
                    id="s0",
                    name="Frame 0",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=80,
                ),
                DesignNode(
                    id="s1",
                    name="Frame 1",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=100,
                    width=600,
                    height=200,
                ),
                DesignNode(
                    id="s2",
                    name="Frame 2",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=300,
                    width=600,
                    height=100,
                    children=[_make_text_node("t1", "© 2024 Company. Unsubscribe")],
                ),
            ]
        )
        layout = analyze_layout(structure)
        section_2 = next(s for s in layout.sections if s.node_id == "s2")
        assert section_2.section_type == EmailSectionType.FOOTER

    def test_unsubscribe_mid_not_footer(self) -> None:
        """'unsubscribe' at index 2 of 6 → not FOOTER."""
        sections = [
            DesignNode(
                id=f"s{i}",
                name=f"Frame {i}",
                type=DesignNodeType.FRAME,
                x=0,
                y=i * 100,
                width=600,
                height=80,
            )
            for i in range(6)
        ]
        # Add unsubscribe text to section at index 2
        sections[2] = DesignNode(
            id="s2",
            name="Frame 2",
            type=DesignNodeType.FRAME,
            x=0,
            y=200,
            width=600,
            height=80,
            children=[_make_text_node("t1", "Click here to unsubscribe from updates")],
        )
        structure = _make_section_structure(sections)
        layout = analyze_layout(structure)
        section_2 = next(s for s in layout.sections if s.node_id == "s2")
        assert section_2.section_type != EmailSectionType.FOOTER


class TestPatternMatchingFixes:
    """Bug 14: word-boundary matching prevents false substring matches."""

    def test_text_not_matches_context(self) -> None:
        """'context-block' should NOT match pattern 'text'."""
        result, _conf = _classify_by_name("context-block")
        assert result != EmailSectionType.CONTENT

    def test_exact_word_matches(self) -> None:
        """'content-block' should match pattern 'content'."""
        result, _conf = _classify_by_name("content-block")
        assert result == EmailSectionType.CONTENT


class TestImageChildDetectionFixes:
    """Bug 15: _has_large_image_child recurses 2 levels deep."""

    def test_nested_image_detected(self) -> None:
        """IMAGE 2 levels deep should be detected."""
        inner_frame = DesignNode(
            id="inner",
            name="inner-frame",
            type=DesignNodeType.FRAME,
            width=500,
            height=300,
            children=[
                DesignNode(
                    id="img",
                    name="hero-img",
                    type=DesignNodeType.IMAGE,
                    width=500,
                    height=300,
                ),
            ],
        )
        outer = DesignNode(
            id="outer",
            name="outer-frame",
            type=DesignNodeType.FRAME,
            width=600,
            height=400,
            children=[inner_frame],
        )
        assert _has_large_image_child(outer)

    def test_shallow_image_still_works(self) -> None:
        """Direct child IMAGE should still be detected."""
        node = DesignNode(
            id="frame",
            name="hero",
            type=DesignNodeType.FRAME,
            width=600,
            height=300,
            children=[
                DesignNode(
                    id="img",
                    name="hero-img",
                    type=DesignNodeType.IMAGE,
                    width=500,
                    height=300,
                ),
            ],
        )
        assert _has_large_image_child(node)

    def test_multiple_images_still_detected(self) -> None:
        """Multiple IMAGE children — largest still triggers detection."""
        node = DesignNode(
            id="frame",
            name="gallery",
            type=DesignNodeType.FRAME,
            width=600,
            height=300,
            children=[
                DesignNode(
                    id="img1",
                    name="large-img",
                    type=DesignNodeType.IMAGE,
                    width=400,
                    height=200,
                ),
                DesignNode(
                    id="img2",
                    name="small-img",
                    type=DesignNodeType.IMAGE,
                    width=100,
                    height=100,
                ),
            ],
        )
        assert _has_large_image_child(node)


class TestColumnGroupingFixes:
    """Bug 16: deterministic column grouping regardless of input order."""

    def test_deterministic_2x2_grid(self) -> None:
        """2x2 grid → same result regardless of input order."""
        children = [
            DesignNode(
                id="a",
                name="A",
                type=DesignNodeType.FRAME,
                x=0,
                y=0,
                width=280,
                height=200,
                children=[_make_text_node("ta", "Col A")],
            ),
            DesignNode(
                id="b",
                name="B",
                type=DesignNodeType.FRAME,
                x=300,
                y=0,
                width=280,
                height=200,
                children=[_make_text_node("tb", "Col B")],
            ),
            DesignNode(
                id="c",
                name="C",
                type=DesignNodeType.FRAME,
                x=0,
                y=220,
                width=280,
                height=200,
                children=[_make_text_node("tc", "Col C")],
            ),
            DesignNode(
                id="d",
                name="D",
                type=DesignNodeType.FRAME,
                x=300,
                y=220,
                width=280,
                height=200,
                children=[_make_text_node("td", "Col D")],
            ),
        ]
        # Forward order
        s1 = _make_section_structure(
            [
                DesignNode(
                    id="row",
                    name="grid",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=440,
                    children=children,
                ),
            ]
        )
        l1 = analyze_layout(s1)

        # Reversed order
        s2 = _make_section_structure(
            [
                DesignNode(
                    id="row",
                    name="grid",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=440,
                    children=list(reversed(children)),
                ),
            ]
        )
        l2 = analyze_layout(s2)

        # Column groups should be identical
        g1 = l1.sections[0].column_groups
        g2 = l2.sections[0].column_groups
        assert len(g1) == len(g2)
        for a, b in zip(g1, g2, strict=True):
            assert a.node_id == b.node_id

    def test_sorted_by_x_within_row(self) -> None:
        """Columns should be sorted left-to-right by x position."""
        children = [
            DesignNode(
                id="right",
                name="Right",
                type=DesignNodeType.FRAME,
                x=300,
                y=0,
                width=280,
                height=200,
            ),
            DesignNode(
                id="left", name="Left", type=DesignNodeType.FRAME, x=0, y=0, width=280, height=200
            ),
        ]
        structure = _make_section_structure(
            [
                DesignNode(
                    id="row",
                    name="row",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=200,
                    children=children,
                ),
                DesignNode(
                    id="footer",
                    name="Footer",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=200,
                    width=600,
                    height=80,
                ),
            ]
        )
        layout = analyze_layout(structure)
        row_section = next(s for s in layout.sections if s.node_id == "row")
        groups = row_section.column_groups
        assert len(groups) >= 2
        assert groups[0].node_id == "left"
        assert groups[1].node_id == "right"


class TestButtonTextExclusionFixes:
    """CRITICAL: button text should NOT appear in section.texts."""

    def test_button_text_not_in_section_texts(self) -> None:
        """'SHOP NOW' in buttons, NOT in texts."""
        structure = _make_section_structure(
            [
                DesignNode(
                    id="s1",
                    name="CTA Section",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=150,
                    children=[
                        _make_text_node("t1", "Check out our deals", font_size=16.0),
                        _make_button_frame("btn1", "SHOP NOW"),
                    ],
                ),
            ]
        )
        layout = analyze_layout(structure)
        section = layout.sections[0]
        text_contents = [t.content for t in section.texts]
        button_texts = [b.text for b in section.buttons]
        assert "SHOP NOW" in button_texts
        assert "SHOP NOW" not in text_contents
        assert "Check out our deals" in text_contents

    def test_body_text_preserved(self) -> None:
        """Non-button text should still be extracted."""
        structure = _make_section_structure(
            [
                DesignNode(
                    id="s1",
                    name="Content",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=300,
                    children=[
                        _make_text_node("t1", "Hello world"),
                        _make_text_node("t2", "Another paragraph"),
                        _make_button_frame("btn1", "Click me"),
                    ],
                ),
            ]
        )
        layout = analyze_layout(structure)
        section = layout.sections[0]
        text_contents = [t.content for t in section.texts]
        assert "Hello world" in text_contents
        assert "Another paragraph" in text_contents
        assert "Click me" not in text_contents

    def test_multiple_buttons_excluded(self) -> None:
        """Multiple buttons excluded, body text kept."""
        structure = _make_section_structure(
            [
                DesignNode(
                    id="s1",
                    name="Section",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=300,
                    children=[
                        _make_text_node("t1", "Body text here"),
                        _make_button_frame("btn1", "BUY NOW"),
                        _make_button_frame("btn2", "LEARN MORE"),
                    ],
                ),
                DesignNode(
                    id="s2",
                    name="Footer",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=300,
                    width=600,
                    height=80,
                ),
            ]
        )
        layout = analyze_layout(structure)
        section = next(s for s in layout.sections if s.node_id == "s1")
        text_contents = [t.content for t in section.texts]
        assert "Body text here" in text_contents
        assert "BUY NOW" not in text_contents
        assert "LEARN MORE" not in text_contents
        assert len(section.buttons) == 2


class TestGhostButtonFixes:
    """Bug 19: ghost/outline buttons detected by name even without fill."""

    def test_outline_button_by_name(self) -> None:
        """Frame 'cta-button' with no fill → detected as button."""
        structure = _make_section_structure(
            [
                DesignNode(
                    id="s1",
                    name="Section",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=200,
                    children=[
                        DesignNode(
                            id="ghost-btn",
                            name="cta-button",
                            type=DesignNodeType.FRAME,
                            width=200,
                            height=48,
                            fill_color=None,
                            children=[_make_text_node("gt", "Learn More")],
                        ),
                    ],
                ),
            ]
        )
        layout = analyze_layout(structure)
        section = layout.sections[0]
        assert len(section.buttons) == 1
        assert section.buttons[0].text == "Learn More"


class TestCTAClassificationFixes:
    """Bug 18: CTA classification requires button-like content."""

    def test_tall_frame_without_buttons_not_cta(self) -> None:
        """Frame 60-150px height with only text → NOT CTA via position fallback."""
        structure = _make_section_structure(
            [
                DesignNode(
                    id="s0",
                    name="Frame 0",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=0,
                    width=600,
                    height=80,
                ),
                DesignNode(
                    id="s1",
                    name="Frame 1",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=100,
                    width=600,
                    height=120,
                    children=[_make_text_node("t1", "Just a text paragraph with no button")],
                ),
                DesignNode(
                    id="s2",
                    name="Frame 2",
                    type=DesignNodeType.FRAME,
                    x=0,
                    y=300,
                    width=600,
                    height=100,
                ),
            ]
        )
        layout = analyze_layout(structure)
        section_1 = next(s for s in layout.sections if s.node_id == "s1")
        assert section_1.section_type != EmailSectionType.CTA


_LEGO_FIXTURE = Path(__file__).resolve().parents[3] / "data" / "debug" / "7" / "structure.json"


class TestNestedPhysicalCardDetection:
    """Phase 50.8 — analyze_layout surfaces nested cards via subtree fallback.

    When ``_detect_inner_bg`` cannot reach the card (LEGO's mj-wrapper →
    mj-section → mj-section chain), the fallback walker in
    ``find_physical_card_in_subtree`` runs and flips
    ``is_physical_card_surface`` on the enclosing top-level section.
    """

    def test_lego_membership_card_surfaced_on_section_seven(self) -> None:
        if not _LEGO_FIXTURE.exists():
            pytest.skip(f"LEGO fixture missing: {_LEGO_FIXTURE}")

        structure = load_structure_from_json(_LEGO_FIXTURE)
        layout = analyze_layout(structure)

        flagged = [s for s in layout.sections if s.is_physical_card_surface]
        assert len(flagged) == 1, (
            f"expected exactly one physical-card section, got "
            f"{[(layout.sections.index(s), s.physical_card_signals) for s in flagged]}"
        )

        card_section = flagged[0]
        assert layout.sections.index(card_section) == 19
        assert "barcode_child" in card_section.physical_card_signals
        assert "distinct_corner_radius" in card_section.physical_card_signals
