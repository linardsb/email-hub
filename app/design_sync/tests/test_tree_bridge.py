"""Tests for design-sync → EmailTree bridge (Phase 49.8)."""

from __future__ import annotations

import pytest

from app.components.tree_compiler import TreeCompiler
from app.components.tree_schema import (
    ButtonSlot,
    EmailTree,
    HtmlSlot,
    ImageSlot,
    TextSlot,
)
from app.core.exceptions import CompilationError
from app.design_sync.component_matcher import (
    ComponentMatch,
    CompositeSlot,
    SlotFill,
    TokenOverride,
)
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnLayout,
    DesignLayoutDescription,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
)
from app.design_sync.protocol import ExtractedColor, ExtractedTokens, ExtractedTypography
from app.design_sync.sibling_detector import RepeatingGroup
from app.design_sync.tree_bridge import (
    _build_design_tokens,
    _convert_slot_fills,
    _convert_token_overrides,
    _extract_preheader,
    build_email_tree,
)

# ── Factories ────────────────────────────────────────────────────────


def _section(
    section_type: EmailSectionType = EmailSectionType.CONTENT,
    *,
    node_id: str = "frame_1",
    texts: list[TextBlock] | None = None,
    images: list[ImagePlaceholder] | None = None,
    buttons: list[ButtonElement] | None = None,
) -> EmailSection:
    return EmailSection(
        section_type=section_type,
        node_id=node_id,
        node_name="Section",
        texts=texts or [],
        images=images or [],
        buttons=buttons or [],
        column_layout=ColumnLayout.SINGLE,
        column_count=1,
        width=None,
        height=200,
    )


def _text(content: str, *, is_heading: bool = False) -> TextBlock:
    return TextBlock(node_id="t1", content=content, is_heading=is_heading)


def _image(node_id: str = "img_1", w: float = 600, h: float = 400) -> ImagePlaceholder:
    return ImagePlaceholder(node_id=node_id, node_name="photo", width=w, height=h)


def _button(
    text: str = "Click me",
    fill_color: str | None = None,
    text_color: str | None = None,
) -> ButtonElement:
    return ButtonElement(
        node_id="btn_1",
        text=text,
        fill_color=fill_color,
        text_color=text_color,
    )


def _match(
    section: EmailSection,
    slug: str = "hero-default",
    slot_fills: list[SlotFill] | None = None,
    token_overrides: list[TokenOverride] | None = None,
    idx: int = 0,
    confidence: float = 1.0,
) -> ComponentMatch:
    return ComponentMatch(
        section_idx=idx,
        section=section,
        component_slug=slug,
        slot_fills=slot_fills or [],
        token_overrides=token_overrides or [],
        confidence=confidence,
    )


def _layout(sections: list[EmailSection] | None = None) -> DesignLayoutDescription:
    return DesignLayoutDescription(
        file_name="test.fig",
        sections=sections or [],
    )


def _tokens(
    colors: list[ExtractedColor] | None = None,
    typography: list[ExtractedTypography] | None = None,
    dark_colors: list[ExtractedColor] | None = None,
) -> ExtractedTokens:
    return ExtractedTokens(
        colors=colors or [],
        typography=typography or [],
        dark_colors=dark_colors or [],
    )


# ── Tests ────────────────────────────────────────────────────────────


class TestBasicSectionsToTree:
    def test_five_sections_creates_five_tree_sections(self) -> None:
        sections = [_section(node_id=f"f{i}") for i in range(5)]
        layout = _layout(sections)
        matches = [_match(s, slug=f"comp-{i}", idx=i) for i, s in enumerate(sections)]

        tree = build_email_tree(layout, matches, _tokens())

        assert isinstance(tree, EmailTree)
        assert len(tree.sections) == 5
        for i, ts in enumerate(tree.sections):
            assert ts.component_slug == f"comp-{i}"

    def test_empty_matches_creates_placeholder(self) -> None:
        tree = build_email_tree(_layout(), [], _tokens())
        assert len(tree.sections) == 1
        assert tree.sections[0].component_slug == "__custom__"


class TestTextSlotConversion:
    def test_text_fill_becomes_text_slot(self) -> None:
        sec = _section(texts=[_text("Hello World")])
        fills = [SlotFill(slot_id="heading", value="Hello World", slot_type="text")]
        result = _convert_slot_fills(fills, sec)

        assert "heading" in result
        slot = result["heading"]
        assert isinstance(slot, TextSlot)
        assert slot.text == "Hello World"

    def test_html_tags_stripped_from_text(self) -> None:
        sec = _section()
        fills = [SlotFill(slot_id="body", value="<b>Bold</b> text", slot_type="text")]
        result = _convert_slot_fills(fills, sec)

        assert result["body"].text == "Bold text"  # type: ignore[union-attr]


class TestImageSlotConversion:
    def test_image_fill_with_dimensions(self) -> None:
        sec = _section(images=[_image()])
        fills = [
            SlotFill(
                slot_id="hero_image",
                value="https://example.com/photo.jpg",
                slot_type="image",
                attr_overrides={"width": "800", "height": "600", "alt": "A photo"},
            )
        ]
        result = _convert_slot_fills(fills, sec)

        slot = result["hero_image"]
        assert isinstance(slot, ImageSlot)
        assert slot.src == "https://example.com/photo.jpg"
        assert slot.width == 800
        assert slot.height == 600
        assert slot.alt == "A photo"

    def test_image_dimensions_clamped(self) -> None:
        sec = _section()
        fills = [
            SlotFill(
                slot_id="img",
                value="https://example.com/big.jpg",
                slot_type="image",
                attr_overrides={"width": "5000", "height": "0"},
            )
        ]
        result = _convert_slot_fills(fills, sec)
        slot = result["img"]
        assert isinstance(slot, ImageSlot)
        assert slot.width == 2000
        assert slot.height == 1  # clamped from 0 to 1


class TestCtaSlotConversion:
    def test_cta_fill_with_section_buttons(self) -> None:
        sec = _section(buttons=[_button("Shop Now", fill_color="#FF0000", text_color="#FFFFFF")])
        fills = [SlotFill(slot_id="cta", value="https://shop.com", slot_type="cta")]
        result = _convert_slot_fills(fills, sec)

        slot = result["cta"]
        assert isinstance(slot, ButtonSlot)
        assert slot.text == "Shop Now"
        assert slot.href == "https://shop.com"
        assert slot.bg_color == "#FF0000"
        assert slot.text_color == "#FFFFFF"

    def test_cta_fill_with_attr_overrides(self) -> None:
        sec = _section()
        fills = [
            SlotFill(
                slot_id="cta",
                value="https://example.com",
                slot_type="cta",
                attr_overrides={
                    "text": "Buy Now",
                    "bg_color": "#00FF00",
                    "text_color": "#000000",
                },
            )
        ]
        result = _convert_slot_fills(fills, sec)

        slot = result["cta"]
        assert isinstance(slot, ButtonSlot)
        assert slot.text == "Buy Now"
        assert slot.bg_color == "#00FF00"
        assert slot.text_color == "#000000"

    def test_cta_fallback_colors(self) -> None:
        sec = _section()
        fills = [SlotFill(slot_id="cta", value="https://example.com", slot_type="cta")]
        result = _convert_slot_fills(fills, sec)

        slot = result["cta"]
        assert isinstance(slot, ButtonSlot)
        assert slot.text == "Click here"
        assert slot.bg_color == "#000000"
        assert slot.text_color == "#FFFFFF"


class TestHtmlSlotConversion:
    def test_attr_fill_becomes_html_slot(self) -> None:
        sec = _section()
        fills = [
            SlotFill(
                slot_id="custom", value="<table><tr><td>Hi</td></tr></table>", slot_type="attr"
            )
        ]
        result = _convert_slot_fills(fills, sec)

        slot = result["custom"]
        assert isinstance(slot, HtmlSlot)
        assert "Hi" in slot.html

    def test_empty_attr_skipped(self) -> None:
        sec = _section()
        fills = [SlotFill(slot_id="empty", value="   ", slot_type="attr")]
        result = _convert_slot_fills(fills, sec)
        assert "empty" not in result


class TestCompositeSlotConversion:
    """51.1 composite fills in the tree path.

    The composite is a renderer-path primitive with no tree-path equivalent yet,
    so the bridge SKIPS it (returns None) — it is NOT emitted as a ``cta_row``
    slot. Emitting an undefined slot would fail manifest validation and poison the
    whole tree compile (proven by ``test_undefined_slot_breaks_compile``). Full
    tree-path rendering waits on 51.2's ``data-slot-composite`` mode. Documented
    here so the deferral is a tested, honest fact rather than an assumption.
    """

    def _composite_fills(self) -> list[SlotFill]:
        anchor = '<a href="#" style="display:inline-block;">Explore now</a>'
        return [
            SlotFill(slot_id="body", value="Body copy", slot_type="text"),
            SlotFill(
                slot_id="cta_row",
                value="",
                slot_type="composite",
                composite=CompositeSlot(
                    children=(SlotFill("cta_anchor", anchor),),
                    after_slot="body",
                    cell_style="padding:0 24px 24px;",
                    child_separator="\n",
                ),
            ),
        ]

    def test_composite_skipped_at_bridge(self) -> None:
        # The dedicated branch returns None → cta_row is absent from the result
        # (no unknown_slot_type warning, no undefined slot reaching the compiler).
        result = _convert_slot_fills(self._composite_fills(), _section())
        assert "cta_row" not in result

    def test_body_slot_is_plain_text_without_anchor(self) -> None:
        # The body slot still converts cleanly; the CTA anchor is simply absent in
        # the tree path (moved to the renderer-only composite).
        result = _convert_slot_fills(self._composite_fills(), _section())
        body = result["body"]
        assert isinstance(body, TextSlot)
        assert "<a " not in body.text

    def test_undefined_slot_breaks_compile(self) -> None:
        # WHY the bridge must skip (not emit) the composite: an undefined slot on a
        # text-block section fails manifest validation → CompilationError, which
        # would force a fallback to the legacy renderer for every text-block-with-
        # CTA email. 51.2's data-slot-composite mode defines the slot and closes it.
        tree = EmailTree.model_validate(
            {
                "metadata": {"subject": "T", "preheader": "P"},
                "sections": [
                    {
                        "component_slug": "text-block",
                        "slot_fills": {
                            "body": {"type": "text", "text": "Body copy"},
                            "cta_row": {
                                "type": "html",
                                "html": (
                                    '<tr><td align="center"><a href="#">Explore now</a></td></tr>'
                                ),
                            },
                        },
                    }
                ],
            }
        )
        with pytest.raises(CompilationError, match="cta_row"):
            TreeCompiler().compile(tree)


class TestTokenOverrides:
    def test_overrides_converted_to_dict(self) -> None:
        overrides = [
            TokenOverride(
                css_property="background-color", target_class="hero-outer", value="#FF0000"
            ),
            TokenOverride(css_property="color", target_class="heading", value="#333333"),
        ]
        result = _convert_token_overrides(overrides)
        assert result == {"background-color": "#FF0000", "color": "#333333"}

    def test_last_wins_on_duplicate_property(self) -> None:
        overrides = [
            TokenOverride(css_property="color", target_class="a", value="#111111"),
            TokenOverride(css_property="color", target_class="b", value="#222222"),
        ]
        result = _convert_token_overrides(overrides)
        assert result["color"] == "#222222"


class TestRepeatingGroups:
    def test_group_creates_children(self) -> None:
        s1 = _section(node_id="card_1")
        s2 = _section(node_id="card_2")
        s3 = _section(node_id="card_3")
        group = RepeatingGroup(sections=[s1, s2, s3])
        group_map = {0: group, 1: group, 2: group}

        matches = [
            _match(s1, slug="article-card", idx=0),
            _match(s2, slug="article-card", idx=1),
            _match(s3, slug="article-card", idx=2),
        ]

        tree = build_email_tree(_layout([s1, s2, s3]), matches, _tokens(), group_map=group_map)

        assert len(tree.sections) == 1
        wrapper = tree.sections[0]
        assert wrapper.children is not None
        assert len(wrapper.children) == 3
        for child in wrapper.children:
            assert child.component_slug == "article-card"

    def test_group_bgcolor_in_style_overrides(self) -> None:
        s1 = _section(node_id="c1")
        s2 = _section(node_id="c2")
        group = RepeatingGroup(sections=[s1, s2], container_bgcolor="#F5F5F5")
        group_map = {0: group, 1: group}

        matches = [
            _match(s1, slug="article-card", idx=0),
            _match(s2, slug="article-card", idx=1),
        ]

        tree = build_email_tree(_layout([s1, s2]), matches, _tokens(), group_map=group_map)

        wrapper = tree.sections[0]
        assert wrapper.style_overrides.get("background-color") == "#F5F5F5"


class TestDesignTokens:
    def test_tokens_from_extracted(self) -> None:
        tokens = _tokens(
            colors=[ExtractedColor(name="primary", hex="#0066CC")],
            typography=[
                ExtractedTypography(
                    name="heading", family="Arial", weight="bold", size=24, line_height=28
                )
            ],
            dark_colors=[ExtractedColor(name="bg", hex="#1A1A1A")],
        )
        result = _build_design_tokens(tokens)

        assert result["colors"] == {"primary": "#0066CC"}
        assert result["typography"] == {"heading": "Arial"}
        assert result["dark_palette"] == {"bg": "#1A1A1A"}

    def test_empty_tokens_omitted(self) -> None:
        result = _build_design_tokens(_tokens())
        assert result == {}


class TestPreheader:
    def test_preheader_from_first_preheader_section(self) -> None:
        sections = [
            _section(
                EmailSectionType.PREHEADER,
                node_id="ph",
                texts=[_text("Preview text for the email")],
            ),
            _section(EmailSectionType.CONTENT, node_id="body"),
        ]
        layout = _layout(sections)
        assert _extract_preheader(layout) == "Preview text for the email"

    def test_no_preheader_returns_empty(self) -> None:
        layout = _layout([_section()])
        assert _extract_preheader(layout) == ""


class TestTreeValidation:
    def test_tree_validates_against_pydantic_schema(self) -> None:
        sec = _section(texts=[_text("Hello")])
        match = _match(
            sec,
            slug="hero-default",
            slot_fills=[SlotFill(slot_id="heading", value="Hello", slot_type="text")],
        )
        tree = build_email_tree(_layout([sec]), [match], _tokens(), subject="Test Email")

        # Pydantic validation — should not raise
        validated = EmailTree.model_validate(tree.model_dump())
        assert validated.metadata.subject == "Test Email"


class TestRoundtripTreeToHtml:
    def test_tree_compiles_to_valid_html(self) -> None:
        from app.components.tree_compiler import TreeCompiler

        sec = _section(texts=[_text("Welcome")])
        match = _match(
            sec,
            slug="article-2",
            slot_fills=[SlotFill(slot_id="heading", value="Welcome", slot_type="text")],
        )
        tree = build_email_tree(_layout([sec]), [match], _tokens(), subject="Roundtrip Test")

        compiler = TreeCompiler()
        compiled = compiler.compile(tree)
        assert compiled.html
        assert "<html" in compiled.html
        assert compiled.sections_compiled >= 1
