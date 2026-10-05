"""DSL node dataclasses — round-trip, omitted defaults, nesting and value guards."""

from __future__ import annotations

from typing import Any

import pytest

from app.design_sync.dsl.nodes import (
    NODE_CLASSES,
    AnyNode,
    ButtonNode,
    ColumnChild,
    ColumnNode,
    ContainerStyle,
    DividerNode,
    DividerStyle,
    HorizontalAlign,
    ImageNode,
    NodeType,
    RawNode,
    SectionNode,
    Sizing,
    SpacerNode,
    TextNode,
    TextRole,
    VerticalAlign,
    WrapperNode,
    body_from_json,
)
from app.design_sync.email_design_document import DocumentButton, DocumentImage, DocumentText

_TEXT = DocumentText(node_id="1:2", content="Hello", font_size=24.0, font_family="Inter")
_IMAGE = DocumentImage(node_id="1:3", node_name="hero", width=600.0, height=300.0)
_BUTTON = DocumentButton(node_id="1:4", text="Shop now", fill_color="#000000")
_STACK = ("Inter", "Helvetica", "Arial", "sans-serif")


def _round_trip(node: AnyNode) -> dict[str, Any]:
    data = node.to_json()
    assert NODE_CLASSES[node.type].from_json(data) == node
    return data


_FULL_LEAVES: list[ColumnChild] = [
    TextNode(id="t", name="t", text=_TEXT, role=TextRole.BODY, font_stack=_STACK),
    ImageNode(
        id="i", name="i", image=_IMAGE, alt="Hero", href="https://x.test", sizing=Sizing.FILL
    ),
    ButtonNode(id="b", name="b", button=_BUTTON, align=HorizontalAlign.RIGHT, sizing=Sizing.FIXED),
    DividerNode(
        id="d", name="d", thickness=2, color="#dddddd", style=DividerStyle.DASHED, width=200
    ),
    SpacerNode(id="s", name="s", height=32, background_color="#f0f0f0"),
    RawNode(id="r", name="r", html="<table></table>", reason="dsl.overlap"),
]


@pytest.mark.parametrize("node", _FULL_LEAVES, ids=lambda n: n.type.value)
def test_leaf_round_trip_all_fields(node: AnyNode) -> None:
    data = _round_trip(node)
    assert list(data)[:3] == ["type", "id", "name"]
    assert data["type"] == node.type.value


def test_leaves_omit_absent_optionals() -> None:
    image = _round_trip(ImageNode(id="i", name="i", image=_IMAGE, alt=""))
    assert set(image) == {"type", "id", "name", "image", "alt"}
    button = _round_trip(ButtonNode(id="b", name="b", button=_BUTTON))
    assert set(button) == {"type", "id", "name", "button"}
    divider = _round_trip(
        DividerNode(id="d", name="d", thickness=1, color="#000000", style=DividerStyle.SOLID)
    )
    assert "width" not in divider
    spacer = _round_trip(SpacerNode(id="s", name="s", height=8))
    assert set(spacer) == {"type", "id", "name", "height"}


def test_containers_round_trip_with_and_without_style() -> None:
    column = ColumnNode(id="c", name="c", children=tuple(_FULL_LEAVES))
    assert "style" not in _round_trip(column)
    styled = ColumnNode(
        id="c2",
        name="c2",
        children=(),
        style=ContainerStyle(
            background_color="#ffffff",
            radius=(4, 4, 0, 0),
            padding=(8, 16, 8, 16),
            vertical_align=VerticalAlign.MIDDLE,
            sizing=Sizing.HUG,
            full_width=True,
            background_image=_IMAGE,
        ),
    )
    _round_trip(styled)
    section = SectionNode(id="s", name="s", children=(column, RawNode("r", "r", "<table/>", "x")))
    wrapper = WrapperNode(id="w", name="w", children=(section,), style=ContainerStyle(radius=8))
    data = _round_trip(wrapper)
    assert data["style"] == {"radius": 8}


def test_container_style_radius_shapes() -> None:
    scalar = ContainerStyle(radius=12)
    assert scalar.to_json() == {"radius": 12}
    assert ContainerStyle.from_json(scalar.to_json()) == scalar
    corners = ContainerStyle(radius=(1, 2, 3, 4))
    assert corners.to_json() == {"radius": [1, 2, 3, 4]}
    restored = ContainerStyle.from_json(corners.to_json())
    assert restored == corners
    assert isinstance(restored.radius, tuple)
    assert ContainerStyle().to_json() == {}


def test_container_style_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="expected 4 values"):
        ContainerStyle.from_json({"padding": [1, 2, 3]})
    with pytest.raises(ValueError, match="expected 4 values"):
        ContainerStyle.from_json({"radius": [1, 2]})


def test_body_from_json_rejects_column_under_body() -> None:
    column = ColumnNode(id="c", name="c", children=()).to_json()
    with pytest.raises(ValueError, match="'column' not allowed in a body"):
        body_from_json([column])


def test_section_rejects_text_child() -> None:
    text = TextNode(id="t", name="t", text=_TEXT, role=TextRole.BODY, font_stack=_STACK)
    data = {"type": "section", "id": "s", "name": "s", "children": [text.to_json()]}
    with pytest.raises(ValueError, match="'text' not allowed in a section"):
        SectionNode.from_json(data)


def test_column_rejects_section_child() -> None:
    section = SectionNode(id="s", name="s", children=()).to_json()
    data = {"type": "column", "id": "c", "name": "c", "children": [section]}
    with pytest.raises(ValueError, match="'section' not allowed in a column"):
        ColumnNode.from_json(data)


def test_unknown_type_raises_value_error() -> None:
    with pytest.raises(ValueError, match="'carousel' is not a valid NodeType"):
        body_from_json([{"type": "carousel", "id": "x", "name": "x"}])


def test_missing_type_raises_key_error() -> None:
    with pytest.raises(KeyError):
        body_from_json([{"id": "x", "name": "x", "html": "", "reason": "x"}])


@pytest.mark.parametrize("stack", [(), ("Inter",), ("sans-serif", "Inter")])
def test_text_node_rejects_stack_without_trailing_generic(stack: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="font_stack must end in"):
        TextNode(id="t", name="t", text=_TEXT, role=TextRole.BODY, font_stack=stack)


def test_node_classes_cover_every_type() -> None:
    assert set(NODE_CLASSES) == set(NodeType)
    assert all(cls.type is t for t, cls in NODE_CLASSES.items())
