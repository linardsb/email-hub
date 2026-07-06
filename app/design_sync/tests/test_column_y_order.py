"""Column content renders in design tree order, not category buckets (F10).

``_build_column_fill_html`` used to emit ``images → texts → buttons`` buckets,
discarding the design's vertical order (``phase-53f-column-category-order``):
the c7 tip-card tag pill (a ``ButtonElement``) rendered below the body instead
of above the heading, and the treats-card spec icons rendered above the
product name. ``ColumnGroup.content_order`` — node ids captured in pre-order
tree order at group construction — restores the interleave; groups without it
(older persisted documents, the content-group conversion) keep the legacy
bucket order.
"""

from __future__ import annotations

from app.design_sync.component_matcher import _build_column_fill_html
from app.design_sync.email_design_document import DocumentColumn
from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnGroup,
    ImagePlaceholder,
    TextBlock,
    _build_column_groups,
    _detect_mj_columns,
)
from app.design_sync.protocol import DesignNode, DesignNodeType


def _node(
    name: str,
    *,
    ntype: DesignNodeType = DesignNodeType.FRAME,
    children: list[DesignNode] | None = None,
    width: float | None = 600,
    height: float | None = 200,
    text_content: str | None = None,
    fill_color: str | None = None,
    font_size: float | None = None,
) -> DesignNode:
    return DesignNode(
        id=f"id-{name}",
        name=name,
        type=ntype,
        children=children or [],
        width=width,
        height=height,
        text_content=text_content,
        fill_color=fill_color,
        font_size=font_size,
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


def _image_node(name: str, *, width: float = 24, height: float = 24) -> DesignNode:
    return _node(name, ntype=DesignNodeType.IMAGE, width=width, height=height)


def _tip_card_column() -> DesignNode:
    """Mixed-order column mirroring c7 sec[5] col 2: pill → heading → body → CTA."""
    return _node(
        "mj-column",
        width=250,
        height=280,
        children=[
            _node(
                "tag-pill",
                fill_color="#F1E4B2",
                width=90,
                height=28,
                children=[_text_node("pill-label", "Art prints", font_size=12)],
            ),
            _text_node("card-heading", "Bundle of 6 Halloween posters", font_size=20),
            _text_node("card-body", "As a member, you can make this yours.", font_size=14),
            _node(
                "mj-button",
                fill_color="#FF6D00",
                width=140,
                height=44,
                children=[_text_node("cta-label", "Redeem reward", font_size=14)],
            ),
        ],
    )


def _treats_card_column() -> DesignNode:
    """Mixed-order column mirroring c7 sec[9] col 1: name → icon/spec pairs → CTA."""
    return _node(
        "mj-column",
        width=270,
        height=300,
        children=[
            _text_node("product-name", "Halloween Wreath", font_size=18),
            _image_node("Pieces count icon"),
            _text_node("pieces-count", "617 Pieces", font_size=12),
            _image_node("Points badge icon"),
            _text_node("points-count", "+260 Insiders Points", font_size=12),
            _node(
                "mj-button",
                fill_color="#FF6D00",
                width=140,
                height=44,
                children=[_text_node("treats-cta-label", "Shop now", font_size=14)],
            ),
        ],
    )


def _assert_markers_in_order(html: str, markers: list[str]) -> None:
    positions = [(html.index(marker), marker) for marker in markers]
    assert positions == sorted(positions), (
        f"expected design order {markers}, got emission order {[m for _, m in sorted(positions)]}"
    )


class TestColumnDesignOrder:
    def test_tip_card_pill_renders_above_heading(self) -> None:
        """The tag pill (a ButtonElement) must precede the heading, CTA stays last."""
        columns = _detect_mj_columns(_node("mj-section", children=[_tip_card_column()]))
        assert len(columns) == 1
        assert len(columns[0].buttons) == 2  # pill + CTA both classify as buttons

        html = _build_column_fill_html(columns[0])
        _assert_markers_in_order(
            html,
            [
                "Art prints",
                "Bundle of 6 Halloween posters",
                "As a member, you can make this yours.",
                "Redeem reward",
            ],
        )

    def test_treats_card_name_renders_above_icon_rows(self) -> None:
        """The product name precedes the spec icons; each icon precedes its label."""
        columns = _detect_mj_columns(_node("mj-section", children=[_treats_card_column()]))
        assert len(columns) == 1

        html = _build_column_fill_html(columns[0])
        _assert_markers_in_order(
            html,
            [
                "Halloween Wreath",
                'alt="Pieces count icon"',
                "617 Pieces",
                'alt="Points badge icon"',
                "+260 Insiders Points",
                "Shop now",
            ],
        )

    def test_auto_layout_columns_also_capture_order(self) -> None:
        """_build_column_groups (auto-layout path) threads content_order too."""
        groups = _build_column_groups([_tip_card_column()])
        assert len(groups) == 1

        html = _build_column_fill_html(groups[0])
        _assert_markers_in_order(
            html,
            ["Art prints", "Bundle of 6 Halloween posters", "Redeem reward"],
        )


class TestContentOrderCapture:
    def test_detect_mj_columns_captures_pre_order_ids(self) -> None:
        columns = _detect_mj_columns(_node("mj-section", children=[_treats_card_column()]))
        assert columns[0].content_order == (
            "id-product-name",
            "id-Pieces count icon",
            "id-pieces-count",
            "id-Points badge icon",
            "id-points-count",
            "id-mj-button",
        )

    def test_group_without_content_order_keeps_bucket_order(self) -> None:
        """Legacy fallback: no content_order → images → texts → buttons unchanged."""
        group = ColumnGroup(
            column_idx=1,
            node_id="col1",
            node_name="Col 1",
            texts=[TextBlock(node_id="t1", content="Caption text")],
            images=[ImagePlaceholder(node_id="img1", node_name="Product photo")],
            buttons=[ButtonElement(node_id="b1", text="Click")],
            width=280,
        )
        html = _build_column_fill_html(group)
        _assert_markers_in_order(html, ['alt="Product photo"', "Caption text", "Click"])

    def test_document_column_round_trips_content_order(self) -> None:
        """The #327 lesson: a render field is real only if it survives the bridge."""
        columns = _detect_mj_columns(_node("mj-section", children=[_tip_card_column()]))
        original = columns[0]
        assert original.content_order  # non-empty by construction

        doc_column = DocumentColumn.from_column_group(original)
        restored = DocumentColumn.from_json(doc_column.to_json()).to_column_group()
        assert restored.content_order == original.content_order
        assert restored == original
