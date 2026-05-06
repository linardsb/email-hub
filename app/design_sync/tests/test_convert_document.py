# pyright: reportPrivateUsage=false
"""Tests for convert_document() / convert_document_mjml() (Phase 36.2).

Covers:
- Document-based conversion via convert_document()
- MJML document path via convert_document_mjml()
- Shim equivalence (convert vs convert_document)
- from_legacy() roundtrip
- Reverse bridge classmethods (DocumentTokens.from_extracted_tokens,
  DocumentSection.from_email_section)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.design_sync.converter_service import (
    DesignConverterService,
    MjmlCompileResult,
)
from app.design_sync.email_design_document import (
    DocumentLayout,
    DocumentSection,
    DocumentTokens,
    EmailDesignDocument,
)
from app.design_sync.exceptions import MjmlCompileError
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnLayout,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)
from app.design_sync.protocol import (
    DesignFileStructure,
    DesignNode,
    DesignNodeType,
    ExtractedColor,
    ExtractedGradient,
    ExtractedSpacing,
    ExtractedTokens,
    ExtractedTypography,
)

# ── Factories ──


def _make_tokens() -> ExtractedTokens:
    return ExtractedTokens(
        colors=[
            ExtractedColor(name="Background", hex="#FFFFFF"),
            ExtractedColor(name="Text Color", hex="#333333"),
            ExtractedColor(name="Primary", hex="#0066CC"),
        ],
        dark_colors=[
            ExtractedColor(name="Background", hex="#1A1A2E"),
            ExtractedColor(name="Text Color", hex="#E0E0E0"),
            ExtractedColor(name="Primary", hex="#66AAFF"),
        ],
        typography=[
            ExtractedTypography(
                name="Heading", family="Inter", weight="700", size=32.0, line_height=40.0
            ),
            ExtractedTypography(
                name="Body", family="Inter", weight="400", size=16.0, line_height=24.0
            ),
        ],
        spacing=[ExtractedSpacing(name="s1", value=16)],
        gradients=[
            ExtractedGradient(
                name="HeroBG",
                type="linear",
                angle=180.0,
                stops=(("#0066CC", 0.0), ("#003366", 1.0)),
                fallback_hex="#004C99",
            ),
        ],
    )


def _make_structure() -> DesignFileStructure:
    hero = DesignNode(
        id="hero",
        name="Hero Section",
        type=DesignNodeType.FRAME,
        width=600,
        height=400,
        layout_mode="VERTICAL",
        item_spacing=24,
        padding_top=48,
        padding_right=40,
        padding_bottom=48,
        padding_left=40,
        children=[
            DesignNode(
                id="hero_heading",
                name="Hero Title",
                type=DesignNodeType.TEXT,
                text_content="Welcome",
                font_size=32.0,
                font_weight=700,
                y=0,
            ),
            DesignNode(
                id="hero_img",
                name="Hero Image",
                type=DesignNodeType.IMAGE,
                width=520,
                height=200,
                y=100,
            ),
        ],
    )
    content = DesignNode(
        id="content",
        name="Content Section",
        type=DesignNodeType.FRAME,
        width=600,
        height=300,
        children=[
            DesignNode(
                id="body_text",
                name="Body",
                type=DesignNodeType.TEXT,
                text_content="Hello world",
                font_size=16.0,
                y=0,
            ),
        ],
    )
    footer = DesignNode(
        id="footer",
        name="Footer",
        type=DesignNodeType.FRAME,
        width=600,
        height=60,
        children=[
            DesignNode(
                id="footer_text",
                name="Legal",
                type=DesignNodeType.TEXT,
                text_content="© 2026",
                font_size=12.0,
                y=0,
            ),
        ],
    )
    page = DesignNode(
        id="page1",
        name="Page",
        type=DesignNodeType.PAGE,
        children=[hero, content, footer],
    )
    return DesignFileStructure(file_name="Test.fig", pages=[page])


def _make_document(container_width: int = 600, **overrides: Any) -> EmailDesignDocument:
    """Build a document via from_legacy() with test data."""
    doc = EmailDesignDocument.from_legacy(
        _make_structure(),
        _make_tokens(),
        connection_config={"container_width": container_width} if container_width != 600 else None,
    )
    if overrides:
        # Replace top-level fields
        data = doc.to_json()
        data.update(overrides)
        return EmailDesignDocument.from_json(data)
    return doc


# ── convert_document() tests ──


class TestConvertDocument:
    def test_basic_html(self) -> None:
        doc = _make_document()
        result = DesignConverterService().convert_document(doc)
        assert result.html
        assert "<!DOCTYPE html>" in result.html or "<html" in result.html
        assert result.sections_count > 0

    def test_sections_count(self) -> None:
        doc = _make_document()
        result = DesignConverterService().convert_document(doc)
        assert result.sections_count >= 1

    def test_tokens_in_html(self) -> None:
        doc = _make_document()
        result = DesignConverterService().convert_document(doc)
        # Typography token (Inter font) should appear in the HTML
        assert "Inter" in result.html or "inter" in result.html.lower()

    def test_container_width_respected(self) -> None:
        doc = _make_document(container_width=500)
        assert doc.layout.container_width == 500
        result = DesignConverterService().convert_document(doc)
        # Container width should appear in style or attribute
        assert "500" in result.html

    def test_empty_sections(self) -> None:
        doc = EmailDesignDocument(
            version="1.0",
            tokens=DocumentTokens(),
            sections=[],
            layout=DocumentLayout(),
        )
        result = DesignConverterService().convert_document(doc)
        assert result.html == ""
        assert result.sections_count == 0
        assert any("No sections" in w for w in result.warnings)


class TestConvertDocumentMjml:
    @pytest.mark.asyncio
    async def test_mjml_conversion(self) -> None:
        doc = _make_document()
        service = DesignConverterService()
        compiled = "<html><body><p>MJML compiled</p></body></html>"
        with patch.object(service, "compile_mjml", new_callable=AsyncMock) as mock_compile:
            mock_compile.return_value = MjmlCompileResult(
                html=compiled, errors=[], build_time_ms=10
            )
            result = await service.convert_document_mjml(doc)
            assert result.html
            assert result.sections_count >= 1
            mock_compile.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mjml_compile_error_raises(self) -> None:
        """convert_document_mjml does NOT fall back to recursive — it raises."""
        doc = _make_document()
        service = DesignConverterService()
        with patch.object(service, "compile_mjml", new_callable=AsyncMock) as mock_compile:
            mock_compile.side_effect = MjmlCompileError("compile failed")
            with pytest.raises(MjmlCompileError):
                await service.convert_document_mjml(doc)

    @pytest.mark.asyncio
    async def test_empty_sections(self) -> None:
        doc = EmailDesignDocument(
            version="1.0",
            tokens=DocumentTokens(),
            sections=[],
            layout=DocumentLayout(),
        )
        service = DesignConverterService()
        result = await service.convert_document_mjml(doc)
        assert result.html == ""
        assert result.sections_count == 0


# ── Shim equivalence ──


# `TestShimEquivalence` was deleted in 08c part 2: the `convert()` and
# `convert_mjml()` shims went away in part 3 / F013, so equivalence with the
# document path is no longer expressible. The document path is now the only
# path, and its happy-cases are covered above.


# ── from_legacy() tests ──


class TestFromLegacy:
    def test_roundtrip_tokens(self) -> None:
        """from_legacy → to_extracted_tokens preserves token data."""
        tokens = _make_tokens()
        structure = _make_structure()
        doc = EmailDesignDocument.from_legacy(structure, tokens)

        restored = doc.to_extracted_tokens()
        assert len(restored.colors) == len(tokens.colors)
        assert restored.colors[0].hex == tokens.colors[0].hex
        assert len(restored.typography) == len(tokens.typography)
        assert restored.typography[0].family == tokens.typography[0].family
        assert len(restored.dark_colors) == len(tokens.dark_colors)
        assert len(restored.gradients) == len(tokens.gradients)

    def test_sections_populated(self) -> None:
        doc = EmailDesignDocument.from_legacy(_make_structure(), _make_tokens())
        assert len(doc.sections) >= 1

    def test_container_width_from_config(self) -> None:
        doc = EmailDesignDocument.from_legacy(
            _make_structure(),
            _make_tokens(),
            connection_config={"container_width": 700},
        )
        assert doc.layout.container_width == 700

    def test_container_width_auto(self) -> None:
        """Without config override, width derived from layout analysis."""
        doc = EmailDesignDocument.from_legacy(_make_structure(), _make_tokens())
        assert 400 <= doc.layout.container_width <= 800

    def test_no_frames_returns_empty(self) -> None:
        """Structure with no visible frames → empty document."""
        empty = DesignFileStructure(
            file_name="empty.fig",
            pages=[DesignNode(id="p1", name="Page", type=DesignNodeType.PAGE, children=[])],
        )
        doc = EmailDesignDocument.from_legacy(empty, ExtractedTokens())
        assert doc.sections == []

    def test_source_provider(self) -> None:
        doc = EmailDesignDocument.from_legacy(
            _make_structure(),
            _make_tokens(),
            source_provider="penpot",
        )
        assert doc.source is not None
        assert doc.source.provider == "penpot"

    def test_json_roundtrip(self) -> None:
        """from_legacy → to_json → from_json preserves document."""
        doc = EmailDesignDocument.from_legacy(_make_structure(), _make_tokens())
        restored = EmailDesignDocument.from_json(doc.to_json())
        assert restored.version == doc.version
        assert len(restored.sections) == len(doc.sections)
        assert restored.layout.container_width == doc.layout.container_width


# ── Reverse bridge classmethods ──


class TestReverseBridges:
    def test_document_tokens_from_extracted(self) -> None:
        tokens = _make_tokens()
        doc_tokens = DocumentTokens.from_extracted_tokens(tokens)
        restored = doc_tokens.to_extracted_tokens()

        assert len(restored.colors) == len(tokens.colors)
        assert restored.colors[0].name == tokens.colors[0].name
        assert restored.colors[0].hex == tokens.colors[0].hex
        assert len(restored.typography) == len(tokens.typography)
        assert restored.typography[0].family == tokens.typography[0].family
        assert restored.typography[0].size == tokens.typography[0].size
        assert len(restored.dark_colors) == len(tokens.dark_colors)
        assert len(restored.gradients) == len(tokens.gradients)
        assert restored.gradients[0].stops == tokens.gradients[0].stops
        assert len(restored.spacing) == len(tokens.spacing)

    def test_document_section_from_email_section(self) -> None:
        section = EmailSection(
            section_type=EmailSectionType.HERO,
            node_id="hero1",
            node_name="Hero",
            y_position=0.0,
            width=600.0,
            height=400.0,
            column_layout=ColumnLayout.SINGLE,
            column_count=1,
            texts=[
                TextBlock(
                    node_id="t1",
                    content="Hello",
                    font_size=32.0,
                    is_heading=True,
                ),
            ],
            images=[
                ImagePlaceholder(node_id="i1", node_name="Img", width=600.0, height=200.0),
            ],
            buttons=[ButtonElement(node_id="b1", text="Click", width=200.0, height=48.0)],
            padding_top=20.0,
            padding_right=16.0,
            padding_bottom=20.0,
            padding_left=16.0,
            item_spacing=12.0,
            bg_color="#FF0000",
            classification_confidence=0.9,
            content_roles=("logo",),
        )

        doc_section = DocumentSection.from_email_section(section)
        restored = doc_section.to_email_section()

        assert restored.section_type == section.section_type
        assert restored.node_id == section.node_id
        assert restored.width == section.width
        assert restored.height == section.height
        assert len(restored.texts) == len(section.texts)
        assert restored.texts[0].content == "Hello"
        assert len(restored.images) == len(section.images)
        assert len(restored.buttons) == len(section.buttons)
        assert restored.padding_top == section.padding_top
        assert restored.padding_right == section.padding_right
        assert restored.item_spacing == section.item_spacing
        assert restored.bg_color == section.bg_color
        assert restored.classification_confidence == section.classification_confidence
        assert restored.content_roles == section.content_roles
