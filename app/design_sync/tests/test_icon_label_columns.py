"""CE-9 (#427): icon + short-label columns route to a tile, never to a CTA.

A row of icon + label columns (a nav band) is peeled into solo sections; a
position fallback can type them CTA although none holds a button, and the CTA
filler writes neither icon nor label. These tests pin the routing rule on a
minimal Figma node tree (generality rule), the tile HTML, the CTA guard on both
the heuristic and the VLM path, and two invariants over the real corpus.
"""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, patch

import pytest

from app.components.data.seeds import COMPONENT_SEEDS
from app.components.tree_schema import HtmlSlot
from app.design_sync import component_matcher
from app.design_sync.component_matcher import (
    _CTA_FAMILY_SLUGS,
    _SPEC_LABEL_MAX_CHARS,
    ComponentMatch,
    SlotFill,
    _build_slot_fills,
    _fills_icon_label_tile,
    match_all,
    match_section,
    match_section_with_vlm_fallback,
)
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
    analyze_layout,
)
from app.design_sync.protocol import DesignFileStructure, DesignNode, DesignNodeType
from app.design_sync.tests.test_snapshot_regression import _DEBUG_DIR, _run_conversion
from app.design_sync.tree_bridge import _fill_to_slot_value
from app.design_sync.vlm_classifier import VLMClassificationResult

_ROW = "wrap:r0"


def _icon(node_id: str = "img1", size: float = 42) -> ImagePlaceholder:
    return ImagePlaceholder(node_id=node_id, node_name="mj-image", width=size, height=size)


def _label(content: str = "APP", node_id: str = "t1") -> TextBlock:
    return TextBlock(
        node_id=node_id,
        content=content,
        font_family="Roboto",
        font_size=14.0,
        text_color="#FFFFFF",
        line_height=16.0,
        text_align="center",
    )


def _tile_section(
    section_type: EmailSectionType = EmailSectionType.CTA,
    *,
    peel_row_id: str | None = _ROW,
    images: list[ImagePlaceholder] | None = None,
    texts: list[TextBlock] | None = None,
    buttons: list[ButtonElement] | None = None,
) -> EmailSection:
    return EmailSection(
        section_type=section_type,
        node_id="col",
        node_name="mj-column",
        texts=[_label()] if texts is None else texts,
        images=[_icon()] if images is None else images,
        buttons=buttons or [],
        width=154,
        height=64,
        peel_row_id=peel_row_id,
    )


# ── Minimal Figma node tree (generality rule) ──


def _frame(
    node_id: str, name: str, *, y: float, h: float, children: list[DesignNode], **kw: object
) -> DesignNode:
    return DesignNode(
        id=node_id,
        name=name,
        type=DesignNodeType.FRAME,
        y=y,
        height=h,
        children=children,
        **kw,  # type: ignore[arg-type]
    )


def _nav_column(i: int, label: str, *, y: float) -> DesignNode:
    x = i * 150.0
    image = DesignNode(
        id=f"c{i}-img",
        name="mj-image",
        type=DesignNodeType.IMAGE,
        x=x + 54,
        y=y,
        width=42,
        height=42,
    )
    text = DesignNode(
        id=f"c{i}-txt",
        name="mj-text",
        type=DesignNodeType.TEXT,
        x=x,
        y=y + 48,
        width=150,
        height=16,
        text_content=label,
        font_size=14.0,
        text_color="#FFFFFF",
    )
    return _frame(
        f"c{i}",
        "mj-column",
        x=x,
        y=y,
        h=64,
        width=150,
        children=[
            _frame(f"c{i}-if", "mj-image-Frame", x=x, y=y, h=42, width=150, children=[image]),
            _frame(f"c{i}-tf", "mj-text-Frame", x=x, y=y + 42, h=22, width=150, children=[text]),
        ],
    )


def _nav_row_structure() -> DesignFileStructure:
    def text_section(node_id: str, y: float, words: str) -> DesignNode:
        txt = DesignNode(
            id=f"{node_id}-t",
            name="mj-text",
            type=DesignNodeType.TEXT,
            x=0,
            y=y,
            width=600,
            height=40,
            text_content=words,
            font_size=16.0,
        )
        col = _frame(f"{node_id}-c", "mj-column", x=0, y=y, h=200, width=600, children=[txt])
        return _frame(node_id, "mj-section", x=0, y=y, h=200, width=600, children=[col])

    labels = ("ONE", "TWO", "THREE", "FOUR")
    section = _frame(
        "row",
        "mj-section",
        x=0,
        y=328,
        h=64,
        width=600,
        children=[_nav_column(i, label, y=328) for i, label in enumerate(labels)],
    )
    wrapper = _frame(
        "wrap", "mj-wrapper", x=0, y=300, h=120, width=600, fill_color="#204020", children=[section]
    )
    body = [
        text_section("top", 0, "A paragraph of body copy that opens the email."),
        wrapper,
        text_section("bottom", 500, "A closing paragraph of body copy for the email."),
    ]
    page = DesignNode(id="page", name="Email", type=DesignNodeType.PAGE, children=body)
    return DesignFileStructure(file_name="nav-row", pages=[page])


class TestNodeTreeRouting:
    def test_icon_label_row_routes_to_tiles_not_cta(self) -> None:
        layout = analyze_layout(_nav_row_structure())
        row = [s for s in layout.sections if s.peel_row_id is not None]
        assert len(row) == 4
        # Precondition: the position fallback still types (some of) them CTA,
        # so this test exercises the bug, not a different section type.
        assert any(s.section_type == EmailSectionType.CTA for s in row)
        assert all(not s.buttons for s in row)

        matches = {m.section.node_id: m for m in match_all(layout.sections)}
        for s in row:
            m = matches[s.node_id]
            assert m.component_slug not in _CTA_FAMILY_SLUGS
            assert m.component_slug == "td"
            (content,) = m.slot_fills
            assert s.images[0].node_id in content.value
            assert s.texts[0].content in content.value


# ── Matcher rules ──


class TestMatcherRules:
    def test_cta_typed_tile_routes_to_td(self) -> None:
        assert match_section(_tile_section(), 0).component_slug == "td"

    def test_social_typed_peel_tile_routes_to_td(self) -> None:
        s = _tile_section(EmailSectionType.SOCIAL)
        assert match_section(s, 0).component_slug == "td"

    def test_standalone_social_link_keeps_social_icons(self) -> None:
        s = _tile_section(EmailSectionType.SOCIAL, peel_row_id=None)
        assert match_section(s, 0).component_slug == "social-icons"

    def test_header_typed_peel_tile_routes_to_td(self) -> None:
        s = _tile_section(EmailSectionType.HEADER)
        assert match_section(s, 0).component_slug == "td"

    def test_cta_without_button_is_not_a_cta_component(self) -> None:
        s = _tile_section(images=[], texts=[_label("Body copy")], peel_row_id=None)
        m = match_section(s, 0)
        assert m.component_slug not in _CTA_FAMILY_SLUGS
        assert m.component_slug == "text-block"

    def test_real_ctas_unchanged(self) -> None:
        one = _tile_section(
            images=[], texts=[], peel_row_id=None, buttons=[ButtonElement(node_id="b", text="Buy")]
        )
        two = dataclasses.replace(
            one, buttons=[*one.buttons, ButtonElement(node_id="c", text="More")]
        )
        assert match_section(one, 0).component_slug == "cta-button"
        assert match_section(two, 0).component_slug == "cta-pair"

    @pytest.mark.parametrize(
        "section",
        [
            pytest.param(
                _tile_section(buttons=[ButtonElement(node_id="b", text="Go")]), id="has-button"
            ),
            pytest.param(_tile_section(images=[_icon(size=65)]), id="image-too-big"),
            pytest.param(
                _tile_section(texts=[_label("x" * _SPEC_LABEL_MAX_CHARS)]), id="label-too-long"
            ),
            pytest.param(_tile_section(images=[_icon("a"), _icon("b")]), id="two-images"),
            pytest.param(_tile_section(texts=[]), id="no-label"),
            pytest.param(_tile_section(texts=[_label("Lorem ipsum")]), id="placeholder-label"),
            pytest.param(_tile_section(texts=[_label("   ")]), id="blank-label"),
            pytest.param(
                _tile_section(texts=[_label("APP"), _label("Lorem ipsum", node_id="t2")]),
                id="real-plus-placeholder",
            ),
            pytest.param(
                _tile_section(
                    images=[
                        ImagePlaceholder(node_id="img1", node_name="mj-image", width=42, height=65)
                    ]
                ),
                id="height-only-too-big",
            ),
        ],
    )
    def test_non_tile_shapes_do_not_route_to_td(self, section: EmailSection) -> None:
        assert match_section(section, 0).component_slug != "td"


class TestTileHtml:
    def test_icon_centred_at_design_width_above_styled_label(self) -> None:
        (fill,) = _fills_icon_label_tile(_tile_section(), image_urls=None)
        assert fill.slot_id == "content"
        html = fill.value
        icon = html.find('<td align="center"><img')
        label = html.find("APP")
        assert 0 <= icon < label
        assert 'width="42"' in html and "max-width:42px" in html
        assert "font-size:14px" in html and "color:#ffffff" in html.lower()
        for tag in ("<p", "<h1", "<h2", "<h3", "<div"):
            assert tag not in html

    def test_label_gap_from_column_geometry(self) -> None:
        """Column 64 - icon 42 - label line 16 = 6px above the label, none below."""
        (fill,) = _fills_icon_label_tile(_tile_section(), image_urls=None)
        assert "padding:6px 0 0;" in fill.value
        assert "padding:0 0 8px" not in fill.value

    def test_label_gap_zero_without_line_height(self) -> None:
        label = dataclasses.replace(_label(), line_height=None)
        (fill,) = _fills_icon_label_tile(_tile_section(texts=[label]), image_urls=None)
        assert "padding:0px 0 0;" in fill.value

    def test_two_labels_gap_above_first_only(self) -> None:
        """64 - 42 - 2x16 = -10 -> clamped to 0; the second label never gets the gap."""
        texts = [_label("APP"), _label("NEW", node_id="t2")]
        (fill,) = _fills_icon_label_tile(_tile_section(texts=texts), image_urls=None)
        assert fill.value.count("padding:0px 0 0;") == 2

    def test_tree_path_keeps_the_icon(self) -> None:
        """R2: the fill reaches the tree path as HTML, not tag-stripped text."""
        section = _tile_section()
        (fill,) = _fills_icon_label_tile(section, image_urls=None)
        value = _fill_to_slot_value(fill, section)
        assert isinstance(value, HtmlSlot)
        assert "<img" in value.html and "APP" in value.html


class TestVlmGuard:
    async def test_vlm_cta_slug_rejected_without_button(self) -> None:
        """R3: a VLM-picked CTA slug never replaces a button-less match."""
        section = EmailSection(
            section_type=EmailSectionType.CONTENT,
            node_id="n",
            node_name="Ambiguous",
            width=600,
            height=300,
        )
        settings = type(
            "S", (), {"design_sync": type("DS", (), {"vlm_fallback_enabled": True})()}
        )()
        vlm = AsyncMock(
            return_value=VLMClassificationResult(component_type="cta-button", confidence=0.9)
        )
        with (
            patch("app.core.config.get_settings", return_value=settings),
            patch("app.design_sync.vlm_classifier.vlm_classify_section", vlm),
        ):
            m = await match_section_with_vlm_fallback(
                section, 0, screenshot=b"png", candidate_types=["cta-button", "text-block"]
            )
        vlm.assert_awaited_once()
        assert m.component_slug not in _CTA_FAMILY_SLUGS


# ── Checked mapping + corpus invariants ──


def test_cta_family_set_matches_the_fill_dispatch() -> None:
    """Checked mapping: the seed slugs ``_build_slot_fills`` sends to ``_fills_cta`` == ``_CTA_FAMILY_SLUGS``."""
    section = _tile_section(peel_row_id=None)
    dispatched = {s["slug"] for s in COMPONENT_SEEDS if _dispatches_to_cta(s["slug"], section)}
    assert dispatched == _CTA_FAMILY_SLUGS


def _dispatches_to_cta(slug: str, section: EmailSection) -> bool:
    calls: list[str] = []
    real = component_matcher._fills_cta

    def spy(sec: EmailSection, cw: int, **kw: object) -> list[SlotFill]:
        calls.append(slug)
        return real(sec, cw, **kw)  # type: ignore[arg-type]

    with patch.object(component_matcher, "_fills_cta", spy):
        _build_slot_fills(slug, section, 600)
    return bool(calls)


def _live_cases() -> list[str]:
    return sorted(
        p.parent.name
        for p in _DEBUG_DIR.glob("*/structure.json")
        if (p.parent / "tokens.json").exists() and (p.parent / "expected.html").exists()
    )


def _converter_matches(case: str) -> tuple[list[ComponentMatch], str]:
    captured: list[list[ComponentMatch]] = []
    original = component_matcher.match_all

    def spy(*args: object, **kwargs: object) -> list[ComponentMatch]:
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        captured.append(result)
        return result

    with patch.object(component_matcher, "match_all", spy):
        html = _run_conversion(_DEBUG_DIR / case).html
    return captured[-1], html


@pytest.mark.skipif(not _live_cases(), reason="data/debug fixtures not present")
@pytest.mark.parametrize("case", _live_cases())
class TestCorpusInvariants:
    def test_cta_component_implies_a_button(self, case: str) -> None:
        matches, _ = _converter_matches(case)
        for m in matches:
            if m.component_slug in _CTA_FAMILY_SLUGS:
                assert m.section.buttons, f"{case} {m.section.node_id} {m.component_slug}"

    def test_icon_label_rows_reach_the_output(self, case: str) -> None:
        matches, html = _converter_matches(case)
        rows: dict[str, list[EmailSection]] = {}
        for m in matches:
            if m.section.peel_row_id is not None:
                rows.setdefault(m.section.peel_row_id, []).append(m.section)
        tile_rows = [
            members
            for members in rows.values()
            if all(component_matcher._is_icon_label_tile(s) for s in members)
        ]
        if case == "6":
            assert len(tile_rows) == 1 and len(tile_rows[0]) == 4
        for members in tile_rows:
            for s in members:
                assert s.images[0].node_id in html, s.node_id
                for t in s.texts:
                    assert t.content in html, (s.node_id, t.content)


_NAV_ROW_C6 = {
    "2833:1457": "APP",
    "2833:1462": "ORDER",
    "2833:1467": "OFFERS",
    "2833:1472": "REWARDS",
}


@pytest.mark.skipif(not (_DEBUG_DIR / "6").is_dir(), reason="data/debug fixtures not present")
def test_c6_nav_tiles_compile_on_the_tree_path() -> None:
    """R2: the real c6 nav tiles compile through the tree bridge with icon and label.

    Compiles only the nav-row matches: the whole-case c6 tree compile already falls
    back to the legacy renderer on base for an unrelated reason (a ``#`` button href
    elsewhere in the email, ledger ``ce-9-tree-path-corpus-compile-fallback``).
    """
    from app.components.tree_compiler import TreeCompiler
    from app.design_sync.diagnose.report import load_structure_from_json, load_tokens_from_json
    from app.design_sync.figma.tree_normalizer import normalize_tree
    from app.design_sync.tree_bridge import build_email_tree

    case_dir = _DEBUG_DIR / "6"
    structure, _ = normalize_tree(load_structure_from_json(case_dir / "structure.json"))
    layout = analyze_layout(structure)
    nav = [m for m in match_all(layout.sections) if m.component_slug == "td"]
    assert len(nav) == 4

    tree = build_email_tree(layout, nav, load_tokens_from_json(case_dir / "tokens.json"))
    html = TreeCompiler().compile(tree).html

    for node_id, label in _NAV_ROW_C6.items():
        assert node_id in html, node_id
        assert label in html, label
