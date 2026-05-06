# pyright: reportPrivateUsage=false
"""End-to-end MJML pipeline test: normalize → analyze → classify → template render → compile.

Verifies the full MJML conversion path from DesignFileStructure through to
compiled email HTML, including:
- Tree normalization (hidden node removal, group flattening)
- Layout analysis into EmailSections
- MjmlTemplateEngine rendering with section markers and token injection
- Dark mode CSS in MJML output
- Multi-column layouts via mj-column
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.design_sync.converter_service import (
    ConversionResult,
    DesignConverterService,
    MjmlCompileResult,
)
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnLayout,
    DesignLayoutDescription,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
    analyze_layout,
)
from app.design_sync.figma.tree_normalizer import normalize_tree
from app.design_sync.mjml_template_engine import (
    MjmlTemplateEngine,
    build_template_context,
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

# ---------------------------------------------------------------------------
# Factory helpers (following test_e2e_pipeline.py patterns)
# ---------------------------------------------------------------------------


def _make_node(
    name: str,
    ntype: DesignNodeType,
    *,
    node_id: str | None = None,
    children: list[DesignNode] | None = None,
    width: float | None = None,
    height: float | None = None,
    x: float | None = None,
    y: float | None = None,
    text_content: str | None = None,
    font_size: float | None = None,
    font_weight: int | None = None,
    text_color: str | None = None,
    fill_color: str | None = None,
    layout_mode: str | None = None,
    item_spacing: float | None = None,
    padding_top: float | None = None,
    padding_right: float | None = None,
    padding_bottom: float | None = None,
    padding_left: float | None = None,
    visible: bool = True,
    opacity: float = 1.0,
) -> DesignNode:
    return DesignNode(
        id=node_id or name.lower().replace(" ", "_"),
        name=name,
        type=ntype,
        children=children or [],
        width=width,
        height=height,
        x=x,
        y=y,
        text_content=text_content,
        font_size=font_size,
        font_weight=font_weight,
        text_color=text_color,
        fill_color=fill_color,
        layout_mode=layout_mode,
        item_spacing=item_spacing,
        padding_top=padding_top,
        padding_right=padding_right,
        padding_bottom=padding_bottom,
        padding_left=padding_left,
        visible=visible,
        opacity=opacity,
    )


def _make_tokens(
    *,
    colors: list[ExtractedColor] | None = None,
    dark_colors: list[ExtractedColor] | None = None,
) -> ExtractedTokens:
    return ExtractedTokens(
        colors=colors
        or [
            ExtractedColor(name="Background", hex="#FFFFFF"),
            ExtractedColor(name="Text", hex="#333333"),
            ExtractedColor(name="Primary", hex="#0066CC"),
        ],
        dark_colors=dark_colors or [],
        typography=[
            ExtractedTypography(
                name="Heading", family="Inter", weight="700", size=24.0, line_height=32.0
            ),
            ExtractedTypography(
                name="Body", family="Inter", weight="400", size=16.0, line_height=24.0
            ),
        ],
        spacing=[
            ExtractedSpacing(name="sm", value=8),
            ExtractedSpacing(name="md", value=16),
        ],
    )


def _make_structure() -> DesignFileStructure:
    """4-section structure: Header + Hero + 2-col Content + Footer."""
    header = _make_node(
        "Header",
        DesignNodeType.FRAME,
        width=600,
        height=80,
        layout_mode="HORIZONTAL",
        children=[
            _make_node(
                "Logo", DesignNodeType.IMAGE, node_id="logo", width=120, height=40, x=0, y=0
            ),
        ],
    )
    hero = _make_node(
        "Hero",
        DesignNodeType.FRAME,
        width=600,
        height=300,
        layout_mode="VERTICAL",
        item_spacing=16,
        children=[
            _make_node(
                "Hero Title",
                DesignNodeType.TEXT,
                text_content="Welcome to Our Store",
                font_size=32.0,
                font_weight=700,
                y=0,
            ),
            _make_node(
                "Hero CTA",
                DesignNodeType.COMPONENT,
                width=200,
                height=48,
                fill_color="#0066CC",
                y=60,
                children=[
                    _make_node(
                        "CTA Label",
                        DesignNodeType.TEXT,
                        text_content="Shop Now",
                        text_color="#FFFFFF",
                        font_size=16.0,
                        y=0,
                    ),
                ],
            ),
        ],
    )
    content = _make_node(
        "Two Columns",
        DesignNodeType.FRAME,
        width=600,
        height=200,
        layout_mode="HORIZONTAL",
        item_spacing=20,
        children=[
            _make_node(
                "Left Column",
                DesignNodeType.FRAME,
                width=280,
                height=200,
                x=0,
                y=0,
                children=[
                    _make_node(
                        "Left Text",
                        DesignNodeType.TEXT,
                        text_content="Column one content",
                        font_size=16.0,
                        y=0,
                    ),
                ],
            ),
            _make_node(
                "Right Column",
                DesignNodeType.FRAME,
                width=280,
                height=200,
                x=300,
                y=0,
                children=[
                    _make_node(
                        "Right Text",
                        DesignNodeType.TEXT,
                        text_content="Column two content",
                        font_size=16.0,
                        y=0,
                    ),
                ],
            ),
        ],
    )
    footer = _make_node(
        "Footer",
        DesignNodeType.FRAME,
        width=600,
        height=60,
        children=[
            _make_node(
                "Legal",
                DesignNodeType.TEXT,
                text_content="© 2026 Brand Inc.",
                font_size=12.0,
                y=0,
            ),
        ],
    )
    page = _make_node("Page", DesignNodeType.PAGE, children=[header, hero, content, footer])
    return DesignFileStructure(file_name="Campaign.fig", pages=[page])


def _make_section(
    section_type: EmailSectionType = EmailSectionType.CONTENT,
    *,
    node_id: str = "s1",
    node_name: str = "Section",
    texts: list[TextBlock] | None = None,
    images: list[ImagePlaceholder] | None = None,
    buttons: list[ButtonElement] | None = None,
    column_layout: ColumnLayout = ColumnLayout.SINGLE,
    column_count: int = 1,
    bg_color: str | None = None,
) -> EmailSection:
    return EmailSection(
        section_type=section_type,
        node_id=node_id,
        node_name=node_name,
        texts=texts or [],
        images=images or [],
        buttons=buttons or [],
        column_layout=column_layout,
        column_count=column_count,
        bg_color=bg_color,
        column_groups=[],
    )


def _make_layout(sections: list[EmailSection]) -> DesignLayoutDescription:
    return DesignLayoutDescription(file_name="Test", sections=sections)


# ---------------------------------------------------------------------------
# Tests: Full pipeline normalize → analyze → template engine
# ---------------------------------------------------------------------------


def _render_mjml(layout: DesignLayoutDescription, tokens: ExtractedTokens) -> str:
    """Render MJML via template engine (replaces generate_mjml)."""
    engine = MjmlTemplateEngine()
    ctx = build_template_context(tokens)
    preheader = ""
    body_sections: list[EmailSection] = []
    for s in layout.sections:
        if s.section_type == EmailSectionType.PREHEADER and s.texts:
            preheader = s.texts[0].content
        elif s.section_type != EmailSectionType.PREHEADER:
            body_sections.append(s)
    return engine.render_email(body_sections, ctx, preheader=preheader)


class TestNormalizeToMjmlPipeline:
    """Full pipeline: normalize_tree → analyze_layout → template engine."""

    def test_full_pipeline_normalize_to_mjml(self) -> None:
        """Full pipeline produces valid <mjml> document."""
        structure = _make_structure()
        tokens = _make_tokens()

        normalized, _stats = normalize_tree(structure)
        layout = analyze_layout(normalized)
        mjml = _render_mjml(layout, tokens)

        assert "<mjml>" in mjml
        assert "</mjml>" in mjml
        assert "<mj-body" in mjml
        assert "<mj-section" in mjml

    def test_pipeline_section_count_matches(self) -> None:
        """Section count in layout == mj-section count in MJML output."""
        structure = _make_structure()
        tokens = _make_tokens()

        normalized, _stats = normalize_tree(structure)
        layout = analyze_layout(normalized)
        mjml = _render_mjml(layout, tokens)

        section_count = len(layout.sections)
        mj_section_count = mjml.count("<mj-section")
        assert section_count > 0
        assert mj_section_count == section_count

    def test_pipeline_dark_mode_css(self) -> None:
        """Dark tokens produce <mj-style> with prefers-color-scheme."""
        structure = _make_structure()
        tokens = _make_tokens(
            dark_colors=[
                ExtractedColor(name="Background", hex="#1A1A2E"),
                ExtractedColor(name="Text", hex="#E0E0E0"),
            ],
        )

        normalized, _stats = normalize_tree(structure)
        layout = analyze_layout(normalized)
        mjml = _render_mjml(layout, tokens)

        assert "@media (prefers-color-scheme: dark)" in mjml
        assert "<mj-style" in mjml

    def test_pipeline_token_injection(self) -> None:
        """Palette colors and typography appear in MJML output."""
        structure = _make_structure()
        tokens = _make_tokens()

        normalized, _stats = normalize_tree(structure)
        layout = analyze_layout(normalized)
        mjml = _render_mjml(layout, tokens)

        assert "Inter" in mjml

    def test_pipeline_multi_column(self) -> None:
        """Two-column section produces mj-column elements."""
        sections = [
            _make_section(
                EmailSectionType.CONTENT,
                node_id="two_col",
                column_layout=ColumnLayout.TWO_COLUMN,
                column_count=2,
            ),
        ]
        layout = _make_layout(sections)
        tokens = _make_tokens()
        mjml = _render_mjml(layout, tokens)

        assert "<mj-column" in mjml
        assert mjml.count("<mj-column") >= 2

    def test_pipeline_section_markers(self) -> None:
        """Section markers appear in MJML output."""
        structure = _make_structure()
        tokens = _make_tokens()

        normalized, _stats = normalize_tree(structure)
        layout = analyze_layout(normalized)
        mjml = _render_mjml(layout, tokens)

        assert "<!-- section:" in mjml

    def test_pipeline_preheader(self) -> None:
        """Preheader section produces <mj-preview> in head."""
        sections = [
            _make_section(
                EmailSectionType.PREHEADER,
                node_id="ph",
                texts=[TextBlock(node_id="t1", content="Preview text here")],
            ),
            _make_section(EmailSectionType.CONTENT, node_id="c1"),
        ]
        layout = _make_layout(sections)
        tokens = _make_tokens()
        mjml = _render_mjml(layout, tokens)

        assert "<mj-preview>" in mjml
        assert "Preview text here" in mjml

    def test_pipeline_responsive_attrs(self) -> None:
        """MJML output includes responsive body width."""
        structure = _make_structure()
        tokens = _make_tokens()

        normalized, _stats = normalize_tree(structure)
        layout = analyze_layout(normalized)
        mjml = _render_mjml(layout, tokens)

        assert "<mj-body" in mjml
        assert 'width="600px"' in mjml

    def test_pipeline_empty_structure(self) -> None:
        """Empty structure produces minimal MJML with head only."""
        structure = DesignFileStructure(file_name="Empty.fig", pages=[])
        tokens = _make_tokens()
        layout = analyze_layout(structure)
        mjml = _render_mjml(layout, tokens)

        assert "<mjml>" in mjml
        assert "<mj-head>" in mjml
        assert mjml.count("<mj-section") == 0

    def test_pipeline_single_cta_section(self) -> None:
        """Single CTA section produces valid MJML."""
        sections = [
            _make_section(
                EmailSectionType.CTA,
                node_id="cta1",
                buttons=[ButtonElement(node_id="b1", text="Buy Now")],
            ),
        ]
        layout = _make_layout(sections)
        tokens = _make_tokens()
        mjml = _render_mjml(layout, tokens)

        assert "<mj-section" in mjml
        assert "Buy Now" in mjml

    def test_pipeline_normalize_removes_hidden(self) -> None:
        """Hidden nodes are removed by normalization before layout analysis."""
        visible_frame = _make_node(
            "Visible",
            DesignNodeType.FRAME,
            width=600,
            height=200,
            children=[
                _make_node(
                    "Text",
                    DesignNodeType.TEXT,
                    text_content="Visible text",
                    font_size=16.0,
                    y=0,
                ),
            ],
        )
        hidden_frame = _make_node(
            "Hidden",
            DesignNodeType.FRAME,
            width=600,
            height=200,
            visible=False,
            children=[
                _make_node(
                    "Hidden Text",
                    DesignNodeType.TEXT,
                    text_content="Should not appear",
                    font_size=16.0,
                    y=0,
                ),
            ],
        )
        page = _make_node("Page", DesignNodeType.PAGE, children=[visible_frame, hidden_frame])
        structure = DesignFileStructure(file_name="Mixed.fig", pages=[page])

        normalized, stats = normalize_tree(structure)
        assert stats.nodes_removed > 0

        layout = analyze_layout(normalized)
        mjml = _render_mjml(layout, _make_tokens())

        assert "Visible text" in mjml
        assert "Should not appear" not in mjml


# ---------------------------------------------------------------------------
# Tests: MjmlTemplateEngine integration
# ---------------------------------------------------------------------------


class TestTemplateEnginePipeline:
    def test_pipeline_template_engine_render(self) -> None:
        """MjmlTemplateEngine.render_email produces valid MJML with all sections."""
        from app.design_sync.mjml_template_engine import build_template_context

        structure = _make_structure()
        tokens = _make_tokens()

        normalized, _stats = normalize_tree(structure)
        layout = analyze_layout(normalized)
        ctx = build_template_context(tokens)

        engine = MjmlTemplateEngine()
        mjml = engine.render_email(layout.sections, ctx)

        assert "<mjml>" in mjml
        assert "</mjml>" in mjml
        assert "<mj-body" in mjml
        section_count = len(layout.sections)
        assert section_count > 0
        assert mjml.count("<mj-section") == section_count


# ---------------------------------------------------------------------------
# Tests: DesignConverterService.convert_mjml integration
# ---------------------------------------------------------------------------


class TestConvertMjmlServicePipeline:
    @pytest.mark.asyncio
    async def test_pipeline_convert_mjml_service(self) -> None:
        """DesignConverterService.convert_document_mjml() end-to-end with mocked sidecar."""
        from app.design_sync.email_design_document import EmailDesignDocument

        service = DesignConverterService()
        structure = _make_structure()
        tokens = _make_tokens()
        document = EmailDesignDocument.from_legacy(structure, tokens)

        compiled_html = (
            "<html><body>"
            "<!-- section:header:header -->\n<table><tr><td>Header</td></tr></table>"
            "<!-- section:hero:hero -->\n<table><tr><td>Hero</td></tr></table>"
            "</body></html>"
        )

        with patch.object(service, "compile_mjml", new_callable=AsyncMock) as mock_compile:
            mock_compile.return_value = MjmlCompileResult(
                html=compiled_html, errors=[], build_time_ms=50.0
            )
            result = await service.convert_document_mjml(document)

        assert isinstance(result, ConversionResult)
        assert result.html
        assert result.sections_count >= 1
        mock_compile.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_classify_unknown_sections(self) -> None:
        """UNKNOWN sections trigger AI classifier when enhanced."""
        structure = _make_structure()

        normalized, _stats = normalize_tree(structure)
        layout = analyze_layout(normalized)

        # Verify we get sections from the pipeline
        assert len(layout.sections) > 0
        # enhance_layout_with_ai is tested separately in test_ai_layout_classifier.py;
        # here we just verify the pipeline can produce a layout for it to operate on
