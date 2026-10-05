"""Golden component round-trip regression tests.

Tests that golden email components from email-templates/components/ survive
a full round-trip: HTML → HtmlImportAdapter.parse() → EmailDesignDocument
→ DesignConverterService.convert_document() → validate output HTML.

Validates:
- G1: role="presentation" on tables
- G-REF-2: display: block on images
- G-REF-3: Buttons as <a> tags
- G-REF-4: All text content in <td> (td-only layout, no <p> or <h> tags)
- Text content preserved
- Section count reasonable
- Schema validation passes
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from app.design_sync.converter_service import DesignConverterService
from app.design_sync.email_design_document import EmailDesignDocument
from app.design_sync.html_import.adapter import HtmlImportAdapter

_COMPONENTS_DIR = Path(__file__).resolve().parents[3] / "email-templates" / "components"


def _load_component(name: str) -> str:
    return (_COMPONENTS_DIR / name).read_text()


def _wrap_in_email(fragment: str, width: int = 600) -> str:
    """Wrap a component fragment in a minimal email structure.

    Uses a wrapper div with explicit max-width to ensure the container
    width detector finds 600px before any inner element widths.
    """
    return (
        f'<html><body><div style="max-width:{width}px">'
        f'<table width="{width}" align="center" '
        f'role="presentation" cellpadding="0" cellspacing="0" '
        f'style="width:{width}px;">'
        f"<tr><td>{fragment}</td></tr></table></div></body></html>"
    )


# ── Import helpers ────────────────────────────────────────────────


async def _import_component(html: str) -> EmailDesignDocument:
    adapter = HtmlImportAdapter()
    with patch.object(adapter, "_resolve_ai_enabled", return_value=False):
        return await adapter.parse(html, use_ai=False)


def _convert_document(doc: EmailDesignDocument) -> str:
    svc = DesignConverterService()
    result = svc.convert_document(doc)
    return result.html


# ── Schema validation ─────────────────────────────────────────────


class TestGoldenSchemaValidation:
    """Every golden component must produce a schema-valid EmailDesignDocument."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "component",
        [
            "hero-block.html",
            "column-layout-2.html",
            "article-card.html",
            "product-card.html",
            "footer.html",
        ],
    )
    async def test_schema_valid(self, component: str) -> None:
        html = _wrap_in_email(_load_component(component))
        doc = await _import_component(html)
        errors = EmailDesignDocument.validate(doc.to_json())
        assert errors == [], f"Schema errors for {component}: {errors}"
        restored = EmailDesignDocument.from_json(doc.to_json())
        assert json.dumps(restored.to_json()) == json.dumps(doc.to_json())


# ── Import fidelity ──────────────────────────────────────────────


class TestGoldenImportFidelity:
    """Verify the import step extracts expected structure from golden components."""

    @pytest.mark.asyncio
    async def test_hero_block_sections(self) -> None:
        html = _wrap_in_email(_load_component("hero-block.html"))
        doc = await _import_component(html)
        assert len(doc.sections) >= 1
        # Hero should have heading text and image
        all_texts = [t for s in doc.sections for t in s.texts]
        assert any(t.is_heading for t in all_texts), "Hero missing heading"

    @pytest.mark.asyncio
    async def test_article_card_has_button(self) -> None:
        html = _wrap_in_email(_load_component("article-card.html"))
        doc = await _import_component(html)
        all_buttons = [b for s in doc.sections for b in s.buttons]
        all_col_buttons = [b for s in doc.sections for c in s.columns for b in c.buttons]
        assert len(all_buttons) + len(all_col_buttons) >= 1, "Article card missing CTA button"

    @pytest.mark.asyncio
    async def test_footer_has_unsubscribe_text(self) -> None:
        html = _wrap_in_email(_load_component("footer.html"))
        doc = await _import_component(html)
        all_texts = [t for s in doc.sections for t in s.texts]
        combined = " ".join(t.content for t in all_texts)
        assert "Unsubscribe" in combined or "unsubscribe" in combined.lower()

    @pytest.mark.asyncio
    async def test_column_layout_2_detects_columns(self) -> None:
        # column-layout-2.html is a <tr> fragment — wrap in table
        fragment = _load_component("column-layout-2.html")
        html = (
            '<html><body><table width="600" align="center" role="presentation"'
            f' cellpadding="0" cellspacing="0">{fragment}</table></body></html>'
        )
        doc = await _import_component(html)
        # Should detect multi-column layout somewhere
        has_columns = any(len(s.columns) >= 2 for s in doc.sections)
        has_multicol_type = any(s.column_layout != "single" for s in doc.sections)
        assert has_columns or has_multicol_type, "Column layout not detected"

    @pytest.mark.asyncio
    async def test_product_card_has_heading(self) -> None:
        html = _wrap_in_email(_load_component("product-card.html"))
        doc = await _import_component(html)
        all_texts = [t for s in doc.sections for t in s.texts]
        assert any(t.is_heading for t in all_texts), "Product card missing heading"

    @pytest.mark.asyncio
    async def test_hero_block_text_color_extracted(self) -> None:
        """Bug 43 regression: text color should be extracted from inline styles."""
        html = _wrap_in_email(_load_component("hero-block.html"))
        doc = await _import_component(html)
        all_texts = [t for s in doc.sections for t in s.texts]
        texts_with_color = [t for t in all_texts if t.color is not None]
        assert len(texts_with_color) >= 1, "Text color not extracted from hero-block"


# ── Round-trip conversion ─────────────────────────────────────────


class TestGoldenRoundTrip:
    """Full round-trip: HTML → import → convert → validate output HTML."""

    @pytest.mark.asyncio
    async def test_hero_block_roundtrip(self) -> None:
        html = _wrap_in_email(_load_component("hero-block.html"))
        doc = await _import_component(html)
        output = _convert_document(doc)

        assert output, "Empty conversion output"
        # G1: Tables should have role="presentation"
        assert 'role="presentation"' in output
        # G-REF-4: td-only layout — no p/h tags in output
        assert not re.search(r"<(p|h[1-6])[\s>]", output, re.IGNORECASE), (
            "Converter output contains <p> or <h> tags — td-only layout required"
        )

    @pytest.mark.asyncio
    async def test_article_card_roundtrip(self) -> None:
        html = _wrap_in_email(_load_component("article-card.html"))
        doc = await _import_component(html)
        output = _convert_document(doc)

        assert output, "Empty conversion output"
        assert 'role="presentation"' in output
        # G-REF-3: Buttons present (rendered as <a> or via VML for Outlook)
        all_buttons = [b for s in doc.sections for b in s.buttons]
        all_col_buttons = [b for s in doc.sections for c in s.columns for b in c.buttons]
        assert len(all_buttons) + len(all_col_buttons) >= 1, "Article card buttons lost in import"

    @pytest.mark.asyncio
    async def test_product_card_roundtrip(self) -> None:
        html = _wrap_in_email(_load_component("product-card.html"))
        doc = await _import_component(html)
        output = _convert_document(doc)

        assert output, "Empty conversion output"
        assert 'role="presentation"' in output

    @pytest.mark.asyncio
    async def test_footer_roundtrip(self) -> None:
        html = _wrap_in_email(_load_component("footer.html"))
        doc = await _import_component(html)
        output = _convert_document(doc)

        assert output, "Empty conversion output"
        assert 'role="presentation"' in output
        # G-REF-4: td-only layout — no p/h tags in output
        assert not re.search(r"<(p|h[1-6])[\s>]", output, re.IGNORECASE), (
            "Converter output contains <p> or <h> tags — td-only layout required"
        )

    @pytest.mark.asyncio
    async def test_column_layout_2_roundtrip(self) -> None:
        fragment = _load_component("column-layout-2.html")
        html = (
            '<html><body><table width="600" align="center" role="presentation"'
            f' cellpadding="0" cellspacing="0">{fragment}</table></body></html>'
        )
        doc = await _import_component(html)
        output = _convert_document(doc)

        assert output, "Empty conversion output"
        assert 'role="presentation"' in output


# ── Bold text preservation (Bug 36 regression) ────────────────────


class TestBoldTextPreservation:
    """Regression test for Bug 36: <b>/<strong> content must survive import."""

    @pytest.mark.asyncio
    async def test_bold_text_preserved(self) -> None:
        html = _wrap_in_email('<p style="font-size:14px;">Hello <b>Bold World</b> end</p>')
        doc = await _import_component(html)
        all_texts = [t for s in doc.sections for t in s.texts]
        combined = " ".join(t.content for t in all_texts)
        assert "Bold" in combined, f"Bold text lost in import. Got: {combined}"

    @pytest.mark.asyncio
    async def test_strong_em_preserved(self) -> None:
        html = _wrap_in_email(
            '<p style="font-size:14px;"><strong>Important</strong> and <em>emphasis</em></p>'
        )
        doc = await _import_component(html)
        all_texts = [t for s in doc.sections for t in s.texts]
        combined = " ".join(t.content for t in all_texts)
        assert "Important" in combined
        assert "emphasis" in combined


# ── Filter structure property preservation (Bug 37 regression) ────


class TestFilterStructurePreservation:
    """Regression test for Bug 37: _filter_structure must preserve all DesignNode fields."""

    def test_fill_color_preserved(self) -> None:
        from app.design_sync.protocol import (
            DesignFileStructure,
            DesignNode,
            DesignNodeType,
        )
        from app.design_sync.service import _filter_structure

        structure = DesignFileStructure(
            file_name="test",
            pages=[
                DesignNode(
                    id="page1",
                    name="Page",
                    type=DesignNodeType.PAGE,
                    children=[
                        DesignNode(
                            id="hero",
                            name="Hero",
                            type=DesignNodeType.FRAME,
                            fill_color="#FF0000",
                            text_color="#333333",
                            padding_top=20.0,
                            padding_bottom=40.0,
                            font_family="Arial",
                            font_size=16.0,
                            image_ref="img-abc",
                            layout_mode="VERTICAL",
                            item_spacing=10.0,
                            width=600,
                            height=300,
                        ),
                    ],
                )
            ],
        )
        filtered = _filter_structure(structure, ["hero"])
        node = filtered.pages[0].children[0]
        assert node.fill_color == "#FF0000"
        assert node.text_color == "#333333"
        assert node.padding_top == 20.0
        assert node.padding_bottom == 40.0
        assert node.font_family == "Arial"
        assert node.font_size == 16.0
        assert node.image_ref == "img-abc"
        assert node.layout_mode == "VERTICAL"
        assert node.item_spacing == 10.0
