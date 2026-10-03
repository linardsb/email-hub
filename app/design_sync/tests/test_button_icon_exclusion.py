"""CE-10 (#428): an icon inside a detected button is button content, not a section image.

A button frame often holds its label and a small trailing icon. Counting that icon
as a section image flips the matcher (text + button -> icon grid, image + heading +
button -> image grid, button-only -> image block) and the CTA is lost. These tests
pin the exclusion on every extraction path, the icon-leaf measurement, the bounded
button-only classifier rule, the export of excluded icons, and two invariants over
the real corpus. Node trees are minimal Figma input built here (generality rule).
"""

from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest

from app.design_sync.component_matcher import match_section
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    EmailSection,
    EmailSectionType,
    NamingConvention,
    _detect_column_layout_with_groups,
    _detect_mj_columns,
    _extract_content_groups,
    _walk_for_buttons,
    analyze_layout,
)
from app.design_sync.figma.tree_normalizer import normalize_tree
from app.design_sync.import_service import DesignImportService
from app.design_sync.protocol import DesignFileStructure, DesignNode, DesignNodeType
from app.design_sync.schemas import ButtonElementResponse
from app.design_sync.service import _layout_to_response
from app.design_sync.tests.test_icon_label_columns import _converter_matches, _live_cases
from app.design_sync.tests.test_snapshot_regression import _DEBUG_DIR

_FRAME = DesignNodeType.FRAME


def _text(
    node_id: str, content: str, *, font_size: float = 16.0, name: str = "mj-text"
) -> DesignNode:
    return DesignNode(
        id=node_id,
        name=name,
        type=DesignNodeType.TEXT,
        text_content=content,
        font_size=font_size,
        width=300,
        height=font_size * 1.5,
    )


def _image(node_id: str, *, w: float = 17, h: float = 17, name: str = "image") -> DesignNode:
    return DesignNode(id=node_id, name=name, type=DesignNodeType.IMAGE, width=w, height=h)


def _btn(
    node_id: str,
    *,
    icon_wrapper_w: float = 40,
    generic: bool = False,
    label: str = "Go now",
    icon: DesignNode | None = None,
    image_ref: str | None = None,
) -> DesignNode:
    """A button frame: label TEXT + trailing icon (wrapper FRAME -> IMAGE by default)."""
    if icon is None:
        icon = DesignNode(
            id=f"{node_id}:wrap",
            name="arrow-icon" if generic else "afterIcon-Frame",
            type=_FRAME,
            width=icon_wrapper_w,
            height=17,
            children=[_image(f"{node_id}:img")],
        )
    return DesignNode(
        id=node_id,
        name="button" if generic else "mj-button",
        type=_FRAME,
        fill_color="#123456",
        image_ref=image_ref,
        width=200,
        height=48,
        children=[_text(f"{node_id}:label", label, name="label"), icon],
    )


def _column(
    node_id: str, children: list[DesignNode], *, x: float = 0, w: float = 600
) -> DesignNode:
    return DesignNode(
        id=node_id, name="mj-column", type=_FRAME, x=x, y=0, width=w, height=200, children=children
    )


def _mj_section(columns: list[DesignNode], *, node_id: str = "sec") -> DesignNode:
    return DesignNode(
        id=node_id,
        name="mj-wrapper",
        type=_FRAME,
        x=0,
        y=0,
        width=600,
        height=200,
        children=[
            DesignNode(
                id=f"{node_id}:s",
                name="mj-section",
                type=_FRAME,
                x=0,
                y=0,
                width=600,
                height=200,
                children=columns,
            )
        ],
    )


def _page(*sections: DesignNode) -> DesignFileStructure:
    return DesignFileStructure(
        file_name="test",
        pages=[
            DesignNode(id="page", name="Email", type=DesignNodeType.PAGE, children=list(sections))
        ],
    )


def _filler(node_id: str, y: float, *, name: str = "Section 9") -> DesignNode:
    return DesignNode(
        id=node_id,
        name=name,
        type=_FRAME,
        x=0,
        y=y,
        width=600,
        height=100,
        children=[_text(f"{node_id}:t", "Some closing words for the reader", name="copy")],
    )


def _analyze_one(section: DesignNode) -> EmailSection:
    layout = analyze_layout(_page(section))
    assert len(layout.sections) == 1
    return layout.sections[0]


def _analyze_in_page(section: DesignNode) -> EmailSection:
    """Generic-named section second of four: no first/last/second-to-last position rule fires."""
    section = dataclasses.replace(section, y=200)
    others = [_filler("f2", 500, name="Section 3"), _filler("f3", 700)]
    layout = analyze_layout(_page(_filler("f0", 0, name="Section 1"), section, *others))
    return next(s for s in layout.sections if s.node_id == section.id)


def _mj_single(children: list[DesignNode]) -> EmailSection:
    return _analyze_one(_mj_section([_column("col", children)]))


def _generic_two_frames(*, stacked: bool) -> DesignNode:
    """A non-mj section with two child frames, each text + button with icon."""
    frames = [
        DesignNode(
            id=f"g{i}",
            name=f"Frame {i}",
            type=_FRAME,
            x=0 if stacked else i * 300,
            y=i * 150 if stacked else 0,
            width=600 if stacked else 280,
            height=140,
            children=[
                _text(f"g{i}:t", f"Body copy number {i}", name="copy"),
                _btn(f"g{i}:b", generic=True),
            ],
        )
        for i in range(2)
    ]
    return DesignNode(
        id="gsec", name="Section 2", type=_FRAME, x=0, y=0, width=600, height=300, children=frames
    )


# ── Image exclusion on every extraction path ──


class TestImageExclusion:
    def test_text_and_button_section_has_no_icon_image(self) -> None:
        section = _mj_single(
            [_text("t1", "A paragraph of body copy above the button."), _btn("b1")]
        )
        assert len(section.buttons) == 1
        assert section.images == []
        assert "text-with-icon" not in section.content_roles
        assert match_section(section, 0).component_slug == "text-block"

    def test_image_heading_button_section_keeps_only_the_content_image(self) -> None:
        section = _mj_single(
            [
                _image("hero", w=560, h=373, name="mj-image"),
                _text("h1", "A BIG HEADING", font_size=36),
                _text("t1", "Body copy under the heading for the reader."),
                _btn("b1"),
            ]
        )
        assert len(section.buttons) == 1
        assert [i.node_id for i in section.images] == ["hero"]
        assert match_section(section, 0).component_slug == "article-card"

    @pytest.mark.parametrize(
        "button",
        [
            pytest.param(
                _btn(
                    "b1",
                    icon=DesignNode(
                        id="b1:vec", name="icon", type=DesignNodeType.VECTOR, width=16, height=16
                    ),
                ),
                id="vector-icon",
            ),
            pytest.param(_btn("b1", image_ref="ref123"), id="button-image-fill"),
            pytest.param(
                _btn(
                    "b1",
                    icon=DesignNode(
                        id="b1:wrap",
                        name="afterIcon-Frame",
                        type=_FRAME,
                        width=90,
                        height=80,
                        children=[_image("b1:img", w=80, h=80)],
                    ),
                ),
                id="large-icon",
            ),
        ],
    )
    def test_other_icon_shapes_are_excluded(self, button: DesignNode) -> None:
        section = _mj_single([_text("t1", "A paragraph of body copy above the button."), button])
        assert len(section.buttons) == 1
        assert section.images == []

    # Two-column sections are peeled into solo sections by ``analyze_layout``,
    # so the column and content-group extractors are exercised directly.
    def test_mj_columns_have_no_icon_images(self) -> None:
        cols = [
            _column(f"c{i}", [_text(f"t{i}", f"Column copy {i}"), _btn(f"b{i}")], x=i * 300, w=300)
            for i in range(2)
        ]
        groups = _detect_mj_columns(_mj_section(cols))
        assert len(groups) == 2
        for group in groups:
            assert len(group.buttons) == 1
            assert group.images == []

    def test_position_columns_have_no_icon_images(self) -> None:
        _, _, groups = _detect_column_layout_with_groups(
            _generic_two_frames(stacked=False), NamingConvention.GENERIC
        )
        assert len(groups) == 2
        for group in groups:
            assert len(group.buttons) == 1
            assert group.images == []

    def test_content_groups_have_no_icon_images(self) -> None:
        groups = _extract_content_groups(_generic_two_frames(stacked=True))
        assert len(groups) == 2
        for group in groups:
            assert len(group.buttons) == 1
            assert group.images == []

    def test_guard_button_shaped_column_keeps_its_own_images(self) -> None:
        # The extraction root itself passes the button test (filled, <= 80 px, one
        # short TEXT): only buttons BELOW the root are excluded, so its logo stays.
        strip = DesignNode(
            id="strip",
            name="mj-column",
            type=_FRAME,
            fill_color="#000000",
            x=0,
            y=0,
            width=600,
            height=40,
            children=[
                _image("logo", w=80, h=24, name="logo"),
                _text("strip:t", "Free shipping over $50", font_size=12, name="copy"),
            ],
        )
        (group,) = _detect_mj_columns(_mj_section([strip]))
        assert [img.node_id for img in group.images] == ["logo"]


# ── Icon measured on its leaf ──


class TestIconLeaf:
    @staticmethod
    def _walk(node: DesignNode) -> ButtonElement:
        results: list[ButtonElement] = []
        _walk_for_buttons(node, results)
        assert len(results) == 1
        return results[0]

    @pytest.mark.parametrize("wrapper_w", [430, 40])
    def test_icon_id_is_the_leaf_image(self, wrapper_w: float) -> None:
        assert self._walk(_btn("b1", icon_wrapper_w=wrapper_w)).icon_node_id == "b1:img"

    @pytest.mark.parametrize(
        ("fill_color", "image_ref", "effects_summary"),
        [("#000000", None, None), (None, "ref", None), (None, None, "1:DROP_SHADOW")],
    )
    def test_styled_wrapper_is_the_icon(
        self, fill_color: str | None, image_ref: str | None, effects_summary: str | None
    ) -> None:
        # A wrapper that bakes its own fill/image/effects is the icon (glyph on a
        # circle): exporting the bare leaf would drop the circle.
        wrap = DesignNode(
            id="b1:wrap",
            name="social-icon-Frame",
            type=_FRAME,
            width=32,
            height=32,
            fill_color=fill_color,
            image_ref=image_ref,
            effects_summary=effects_summary,
            children=[_image("b1:img", w=24, h=24)],
        )
        assert self._walk(_btn("b1", icon=wrap)).icon_node_id == "b1:wrap"

    def test_guard_styled_fill_width_wrapper_is_walked_through(self) -> None:
        # A filled FILL-width wrapper is wider than any icon: measure the leaf.
        wrap = DesignNode(
            id="b1:wrap",
            name="afterIcon-Frame",
            type=_FRAME,
            fill_color="#FFFFFF",
            width=430,
            height=17,
            children=[_image("b1:img")],
        )
        assert self._walk(_btn("b1", icon=wrap)).icon_node_id == "b1:img"

    def test_large_leaf_is_not_an_icon(self) -> None:
        wrap = DesignNode(
            id="b1:wrap",
            name="afterIcon-Frame",
            type=_FRAME,
            width=90,
            height=80,
            children=[_image("b1:img", w=80, h=80)],
        )
        assert self._walk(_btn("b1", icon=wrap)).icon_node_id is None

    def test_group_of_vectors_keeps_the_wrapper_as_icon(self) -> None:
        group = DesignNode(
            id="b1:grp",
            name="Group 1",
            type=DesignNodeType.GROUP,
            width=20,
            height=20,
            children=[
                DesignNode(
                    id=f"b1:v{i}", name="Vector", type=DesignNodeType.VECTOR, width=10, height=10
                )
                for i in range(2)
            ],
        )
        wrap = DesignNode(
            id="b1:wrap", name="arrow-icon", type=_FRAME, width=24, height=24, children=[group]
        )
        assert self._walk(_btn("b1", icon=wrap)).icon_node_id == "b1:wrap"


# ── Button-only sections classify as CTA ──


class TestButtonOnlyClassification:
    def test_mj_single_button(self) -> None:
        section = _mj_single([_btn("b1", icon_wrapper_w=430)])
        assert section.section_type == EmailSectionType.CTA
        assert match_section(section, 0).component_slug == "cta-button"

    def test_mj_two_buttons(self) -> None:
        section = _mj_single([_btn("b1"), _btn("b2", label="Learn more")])
        assert section.section_type == EmailSectionType.CTA
        assert match_section(section, 0).component_slug == "cta-pair"

    def test_generic_single_button(self) -> None:
        sec = DesignNode(
            id="gsec",
            name="Section 2",
            type=_FRAME,
            x=0,
            y=0,
            width=600,
            height=200,
            children=[_btn("b1", generic=True)],
        )
        section = _analyze_in_page(sec)
        assert len(section.buttons) == 1
        assert section.section_type == EmailSectionType.CTA

    def test_guard_mj_four_link_buttons_not_cta(self) -> None:
        links = [
            DesignNode(
                id=f"l{i}",
                name="mj-button",
                type=_FRAME,
                width=100,
                height=30,
                children=[_text(f"l{i}:t", f"Link {i}", font_size=12, name="label")],
            )
            for i in range(4)
        ]
        section = _mj_single(links)
        assert len(section.buttons) == 4
        assert section.section_type != EmailSectionType.CTA

    def test_guard_mj_button_and_spacer_unchanged(self) -> None:
        spacer = DesignNode(id="sp", name="mj-spacer", type=_FRAME, width=600, height=20)
        plain = DesignNode(
            id="b1",
            name="mj-button",
            type=_FRAME,
            fill_color="#123456",
            width=200,
            height=48,
            children=[_text("b1:t", "Go now", name="label")],
        )
        section = _mj_single([plain, spacer])
        assert section.section_type == EmailSectionType.CONTENT

    def test_guard_generic_four_link_buttons_are_nav(self) -> None:
        links = [
            DesignNode(
                id=f"l{i}",
                name="link",
                type=_FRAME,
                x=i * 120,
                y=0,
                width=100,
                height=30,
                children=[_text(f"l{i}:t", f"Link {i}", font_size=12, name="label")],
            )
            for i in range(4)
        ]
        sec = DesignNode(
            id="gsec", name="Section 2", type=_FRAME, x=0, y=0, width=600, height=40, children=links
        )
        section = _analyze_in_page(sec)
        assert section.section_type == EmailSectionType.NAV


# ── Excluded icons stay exported ──


def _svc() -> DesignImportService:
    user = MagicMock()
    user.id = 1
    user.role = "admin"
    return DesignImportService(user=user)


class TestIconExport:
    def test_button_icon_is_exported(self) -> None:
        layout = MagicMock(spec=["sections"])
        section = MagicMock()
        section.images = []
        btn = MagicMock()
        btn.icon_node_id = "ic:1"
        section.buttons = [btn]
        layout.sections = [section]
        node_ids, _ = _svc()._collect_image_node_ids(layout)
        assert "ic:1" in node_ids

    def test_guard_icon_already_exported_is_not_duplicated(self) -> None:
        layout = MagicMock(spec=["sections"])
        img = MagicMock()
        img.node_id = "ic:1"
        img.export_node_id = None
        btn = MagicMock()
        btn.icon_node_id = "ic:1"
        section = MagicMock()
        section.images = [img]
        section.buttons = [btn]
        layout.sections = [section]
        node_ids, _ = _svc()._collect_image_node_ids(layout)
        assert node_ids == ["ic:1"]

    def test_response_carries_icon_node_id(self) -> None:
        resp = ButtonElementResponse(node_id="b", text="Go", icon_node_id="ic:1")
        assert getattr(resp, "icon_node_id", None) == "ic:1"

    @pytest.mark.parametrize(
        ("wrapper_fill", "exported"),
        [(None, "img"), ("#000000", "wrap")],
    )
    def test_guard_social_icons_reach_the_fill_through_export(
        self, wrapper_fill: str | None, exported: str
    ) -> None:
        def social_btn(i: int) -> DesignNode:
            return DesignNode(
                id=f"s{i}",
                name="social-link",
                type=_FRAME,
                width=120,
                height=32,
                hyperlink=f"https://social{i}.example/brand",
                children=[
                    DesignNode(
                        id=f"s{i}:wrap",
                        name="social-icon-Frame",
                        type=_FRAME,
                        fill_color=wrapper_fill,
                        width=32,
                        height=32,
                        children=[_image(f"s{i}:img", w=24, h=24)],
                    ),
                    _text(f"s{i}:t", f"Network {i}", font_size=12, name="label"),
                ],
            )

        social = DesignNode(
            id="soc",
            name="mj-social",
            type=_FRAME,
            width=600,
            height=40,
            children=[social_btn(0), social_btn(1)],
        )
        layout = analyze_layout(_page(_mj_section([_column("col", [social])])))
        (section,) = layout.sections
        assert section.section_type == EmailSectionType.SOCIAL
        assert len(section.buttons) == 2

        node_ids, _ = _svc()._collect_image_node_ids(_layout_to_response(1, layout))
        image_urls = {nid: f"https://cdn.example/{nid}.png" for nid in node_ids}
        fills = "".join(
            str(f.value) for f in match_section(section, 0, image_urls=image_urls).slot_fills
        )
        for i in range(2):
            assert f"https://cdn.example/s{i}:{exported}.png" in fills


# ── Real corpus (local only: data/debug structure.json is gitignored) ──


def _descendants(root: DesignNode) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}

    def visit(node: DesignNode) -> set[str]:
        below: set[str] = set()
        for child in node.children:
            below.add(child.id)
            below |= visit(child)
        out[node.id] = below
        return below

    visit(root)
    return out


_CTA_LABELS = {
    "9": ["WATCH THE VIDEO", "SHOP NOW"],
    "reframe": ["Register now", "Grab your spot", "Register for livestream"],
}


@pytest.mark.skipif(not _live_cases(), reason="data/debug fixtures not present")
@pytest.mark.parametrize("case", _live_cases())
class TestCorpusInvariants:
    def test_no_button_icon_counts_as_an_image(self, case: str) -> None:
        from app.design_sync.diagnose.report import load_structure_from_json

        structure, _ = normalize_tree(
            load_structure_from_json(_DEBUG_DIR / case / "structure.json")
        )
        below: dict[str, set[str]] = {}
        for page in structure.pages:
            below |= _descendants(page)
        matches, _ = _converter_matches(case)
        for m in matches:
            s = m.section
            containers = [(s.node_id, s.images, s.buttons)]
            containers += [(g.node_id, g.images, g.buttons) for g in s.column_groups]
            containers += [(g.frame_node_id, g.images, g.buttons) for g in s.child_content_groups]
            for cid, images, buttons in containers:
                inside: set[str] = set()
                for b in buttons:
                    inside |= below.get(b.node_id, set())
                stray = [i.node_id for i in images if i.node_id in inside]
                assert not stray, (case, s.node_id, cid, stray)

    def test_ctas_render_in_design_order(self, case: str) -> None:
        if case not in _CTA_LABELS:
            pytest.skip("no CE-10 target CTAs in this case")
        _, html = _converter_matches(case)
        lower = html.lower()
        for label in _CTA_LABELS[case]:
            assert label.lower() in lower, (case, label)
        if case == "9":
            assert 0 <= lower.find("from the davis dam") < lower.find("watch the video")
            assert 0 <= lower.find("hot trip, cool gear.") < lower.find("shop now")
