# pyright: reportPrivateUsage=false
"""End-to-end pipeline test: design tokens → email HTML (Phase 33.11 — Step 11).

Verifies the full conversion pipeline from ExtractedTokens + DesignFileStructure
through to complete email HTML output, including:
- HTML email skeleton (DOCTYPE, MSO conditionals, container)
- Multi-column layout with MSO ghost tables
- Semantic text (headings, paragraphs)
- Bulletproof buttons with VML fallback
- Dark mode CSS (prefers-color-scheme + Outlook.com selectors)
- Gradient CSS with solid fallback
- Typography with email-safe font stacks
- Spacing (padding + vertical spacers)
- Builder annotations (data-section-id, data-slot-name, data-component-name)
- Image placeholders with data-node-id
- Token validation (zero warnings for clean tokens)
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from app.design_sync.converter_service import DesignConverterService
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


class _TagBalanceChecker(HTMLParser):
    """Simple HTML validator checking tag balance."""

    VOID_ELEMENTS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in self.VOID_ELEMENTS:
            self.stack.append(tag.lower())

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self.VOID_ELEMENTS:
            return
        if not self.stack:
            self.errors.append(f"Unexpected closing </{tag}>")
            return
        if self.stack[-1] != tag_lower:
            self.errors.append(f"Expected </{self.stack[-1]}> but got </{tag}>")
        else:
            self.stack.pop()


def _check_html_balance(html: str) -> list[str]:
    """Check for unclosed/mismatched tags (excluding MSO conditionals)."""
    # Strip MSO conditional comments before parsing (they contain unpaired tags)
    cleaned = re.sub(r"<!--\[if[^\]]*\]>.*?<!\[endif\]-->", "", html, flags=re.DOTALL)
    checker = _TagBalanceChecker()
    checker.feed(cleaned)
    # Unclosed tags remaining on stack
    errors = list(checker.errors)
    if checker.stack:
        errors.append(f"Unclosed tags: {checker.stack}")
    return errors


# ── Test Data ──


def _make_e2e_tokens() -> ExtractedTokens:
    """Build realistic tokens: 6 colors (3 light, 3 dark), typography, spacing, gradient."""
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
                name="Heading",
                family="Inter",
                weight="700",
                size=32.0,
                line_height=40.0,
                letter_spacing=-0.5,
                text_transform="uppercase",
            ),
            ExtractedTypography(
                name="Body",
                family="Inter",
                weight="400",
                size=16.0,
                line_height=24.0,
            ),
        ],
        spacing=[
            ExtractedSpacing(name="s1", value=8),
            ExtractedSpacing(name="s2", value=16),
            ExtractedSpacing(name="s3", value=24),
            ExtractedSpacing(name="s4", value=32),
        ],
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


def _make_e2e_structure() -> DesignFileStructure:
    """Build a realistic design tree: header, hero, two-column content, footer."""
    header = DesignNode(
        id="header",
        name="Header",
        type=DesignNodeType.FRAME,
        width=600,
        height=80,
        layout_mode="HORIZONTAL",
        padding_top=16,
        padding_right=24,
        padding_bottom=16,
        padding_left=24,
        children=[
            DesignNode(
                id="logo",
                name="Logo",
                type=DesignNodeType.IMAGE,
                width=120,
                height=40,
                x=0,
                y=0,
            ),
            DesignNode(
                id="nav_text",
                name="Navigation",
                type=DesignNodeType.TEXT,
                text_content="Home | About | Contact",
                font_size=14.0,
                x=400,
                y=0,
            ),
        ],
    )

    hero = DesignNode(
        id="hero",
        name="HeroBG",  # Matches gradient name
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
                id="hero_img",
                name="Hero Image",
                type=DesignNodeType.IMAGE,
                width=520,
                height=200,
                y=0,
            ),
            DesignNode(
                id="hero_heading",
                name="Hero Title",
                type=DesignNodeType.TEXT,
                text_content="Summer Collection 2026",
                font_size=32.0,
                font_weight=700,
                text_color="#FFFFFF",
                y=200,
            ),
            DesignNode(
                id="hero_btn",
                name="CTA Button",
                type=DesignNodeType.COMPONENT,
                width=200,
                height=48,
                fill_color="#0066CC",
                y=280,
                children=[
                    DesignNode(
                        id="btn_text",
                        name="Label",
                        type=DesignNodeType.TEXT,
                        text_content="Shop Now",
                        text_color="#FFFFFF",
                        font_size=16.0,
                        y=0,
                    ),
                ],
            ),
        ],
    )

    content = DesignNode(
        id="content",
        name="Two Column Content",
        type=DesignNodeType.FRAME,
        width=600,
        height=300,
        layout_mode="HORIZONTAL",
        item_spacing=20,
        padding_top=32,
        padding_right=24,
        padding_bottom=32,
        padding_left=24,
        children=[
            DesignNode(
                id="col1",
                name="Column 1",
                type=DesignNodeType.FRAME,
                width=260,
                height=200,
                x=0,
                y=0,
                children=[
                    DesignNode(
                        id="col1_img",
                        name="Content Image",
                        type=DesignNodeType.IMAGE,
                        width=260,
                        height=150,
                        y=0,
                    ),
                    DesignNode(
                        id="col1_text",
                        name="Column Text",
                        type=DesignNodeType.TEXT,
                        text_content="Discover our new arrivals",
                        font_size=16.0,
                        y=160,
                    ),
                ],
            ),
            DesignNode(
                id="col2",
                name="Column 2",
                type=DesignNodeType.FRAME,
                width=260,
                height=200,
                x=280,
                y=0,
                children=[
                    DesignNode(
                        id="col2_text",
                        name="Description",
                        type=DesignNodeType.TEXT,
                        text_content="Premium quality materials\nSustainable sourcing\nFree shipping over $50",
                        font_size=16.0,
                        y=0,
                    ),
                ],
            ),
        ],
    )

    footer = DesignNode(
        id="footer",
        name="Footer",
        type=DesignNodeType.FRAME,
        width=600,
        height=60,
        padding_top=16,
        padding_right=24,
        padding_bottom=16,
        padding_left=24,
        children=[
            DesignNode(
                id="footer_text",
                name="Legal",
                type=DesignNodeType.TEXT,
                text_content="© 2026 Brand Inc. All rights reserved.",
                font_size=12.0,
                text_color="#666666",
                y=0,
            ),
        ],
    )

    page = DesignNode(
        id="page1",
        name="Email Page",
        type=DesignNodeType.PAGE,
        children=[header, hero, content, footer],
    )
    return DesignFileStructure(file_name="Summer Campaign.fig", pages=[page])


# TestEndToEndPipeline was deleted in 08c part 2: its fixtures ran the
# legacy  renderer (use_components=False), and every
# test in the class asserted specific HTML structure that the modern
# component-template path does not reproduce (gradient markup, ghost-table
# multi-column layouts, image src placeholders, builder annotation slots).
# The end-to-end coverage of the modern document path lives in
# test_snapshot_regression.py (real Figma fixtures, expected.html files).


class TestMjmlOutputFormat:
    """Tests for MJML output path in the E2E pipeline."""

    @pytest.mark.asyncio
    async def test_convert_mjml_output_contains_mjml_markers(self) -> None:
        """convert_document_mjml() produces HTML with section markers from MJML generation."""
        from unittest.mock import AsyncMock, patch

        from app.design_sync.converter_service import MjmlCompileResult
        from app.design_sync.email_design_document import EmailDesignDocument

        tokens = _make_e2e_tokens()
        structure = _make_e2e_structure()
        service = DesignConverterService()
        document = EmailDesignDocument.from_legacy(structure, tokens)

        compiled_html = (
            "<html><body>"
            "<!-- section:header:header -->\n<table><tr><td>Header</td></tr></table>"
            "</body></html>"
        )
        with patch.object(service, "compile_mjml", new_callable=AsyncMock) as mock_compile:
            mock_compile.return_value = MjmlCompileResult(
                html=compiled_html, errors=[], build_time_ms=30.0
            )
            result = await service.convert_document_mjml(document)

        assert result.html
        assert result.sections_count >= 1
        assert result.layout is not None

    # `test_convert_mjml_fallback_produces_valid_html` was deleted in 08c part 2.
    # It asserted the MJML→recursive-converter fallback behaviour that lived only
    # in the deprecated `convert_mjml()` shim; `convert_document_mjml()` does not
    # fall back, by design (see its docstring).
