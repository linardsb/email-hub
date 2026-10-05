"""DSL layout-tree nodes carried in ``EmailDesignDocument.body`` (version 2.0).

Nine node types (spec ``docs/architecture/dsl-compiler.md`` S1-S3): three
containers (``wrapper``, ``section``, ``column``) and six leaves (``text``,
``image``, ``button``, ``divider``, ``spacer``, ``raw``). JSON Schema lives
in ``data/schemas/email-design-document-v2.json`` as the ``node_*`` defs.

``from_json`` checks type tags and the parent-child table (S2 "DSL allows")
but not the minimums (a wrapper needs a section, a section a column); those
are the schema's job, as loading has never validated.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

from app.design_sync.email_design_document import DocumentButton, DocumentImage, DocumentText
from app.design_sync.font_stacks import FontCategory


class NodeType(StrEnum):
    """Node ``type`` tag; values match the schema ``const``s."""

    WRAPPER = "wrapper"
    SECTION = "section"
    COLUMN = "column"
    TEXT = "text"
    IMAGE = "image"
    BUTTON = "button"
    DIVIDER = "divider"
    SPACER = "spacer"
    RAW = "raw"


class Sizing(StrEnum):
    """Figma ``layoutSizingHorizontal``, raw upper-case."""

    FIXED = "FIXED"
    FILL = "FILL"
    HUG = "HUG"


class TextRole(StrEnum):
    HEADING = "heading"
    BODY = "body"
    LABEL = "label"
    CTA = "cta"


class HorizontalAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class VerticalAlign(StrEnum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class DividerStyle(StrEnum):
    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"


Padding = tuple[int, int, int, int]
"""(top, right, bottom, left) px."""

Radius = int | tuple[int, int, int, int]
"""Scalar px, or per-corner (tl, tr, br, bl) px."""

_GENERIC_FAMILIES = frozenset(c.value for c in FontCategory)


def _four(value: list[int]) -> tuple[int, int, int, int]:
    if len(value) != 4:
        raise ValueError(f"expected 4 values, got {len(value)}")
    return (value[0], value[1], value[2], value[3])


def _opt_sizing(value: str | None) -> Sizing | None:
    return Sizing(value) if value is not None else None


@dataclass(frozen=True)
class ContainerStyle:
    """Paint and box properties shared by wrapper, section and column nodes."""

    background_color: str | None = None
    radius: Radius | None = None
    padding: Padding | None = None
    vertical_align: VerticalAlign | None = None
    sizing: Sizing | None = None
    full_width: bool = False
    background_image: DocumentImage | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.background_color is not None:
            d["background_color"] = self.background_color
        if self.radius is not None:
            d["radius"] = self.radius if isinstance(self.radius, int) else list(self.radius)
        if self.padding is not None:
            d["padding"] = list(self.padding)
        if self.vertical_align is not None:
            d["vertical_align"] = self.vertical_align.value
        if self.sizing is not None:
            d["sizing"] = self.sizing.value
        if self.full_width:
            d["full_width"] = self.full_width
        if self.background_image is not None:
            d["background_image"] = self.background_image.to_json()
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ContainerStyle:
        radius = data.get("radius")
        padding = data.get("padding")
        vertical_align = data.get("vertical_align")
        background_image = data.get("background_image")
        return cls(
            background_color=data.get("background_color"),
            radius=None if radius is None else radius if isinstance(radius, int) else _four(radius),
            padding=_four(padding) if padding is not None else None,
            vertical_align=VerticalAlign(vertical_align) if vertical_align is not None else None,
            sizing=_opt_sizing(data.get("sizing")),
            full_width=data.get("full_width", False),
            background_image=(
                DocumentImage.from_json(background_image) if background_image is not None else None
            ),
        )


def _opt_style(data: dict[str, Any]) -> ContainerStyle | None:
    style = data.get("style")
    return ContainerStyle.from_json(style) if style is not None else None


@dataclass(frozen=True)
class _Node:
    """Fields every node carries: the Figma node ``id`` and its ``name``."""

    type: ClassVar[NodeType]
    id: str
    name: str

    def _head(self) -> dict[str, Any]:
        return {"type": self.type.value, "id": self.id, "name": self.name}


# ── Leaves ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TextNode(_Node):
    """Text leaf; ``font_stack`` ends in a generic family (spec S3)."""

    type: ClassVar[NodeType] = NodeType.TEXT
    text: DocumentText
    role: TextRole
    font_stack: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.font_stack or self.font_stack[-1] not in _GENERIC_FAMILIES:
            raise ValueError(
                f"font_stack must end in one of {sorted(_GENERIC_FAMILIES)}: {self.font_stack!r}"
            )

    def to_json(self) -> dict[str, Any]:
        d = self._head()
        d["text"] = self.text.to_json()
        d["role"] = self.role.value
        d["font_stack"] = list(self.font_stack)
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TextNode:
        return cls(
            id=data["id"],
            name=data["name"],
            text=DocumentText.from_json(data["text"]),
            role=TextRole(data["role"]),
            font_stack=tuple(data["font_stack"]),
        )


@dataclass(frozen=True)
class ImageNode(_Node):
    type: ClassVar[NodeType] = NodeType.IMAGE
    image: DocumentImage
    alt: str
    href: str | None = None
    sizing: Sizing | None = None

    def to_json(self) -> dict[str, Any]:
        d = self._head()
        d["image"] = self.image.to_json()
        d["alt"] = self.alt
        if self.href is not None:
            d["href"] = self.href
        if self.sizing is not None:
            d["sizing"] = self.sizing.value
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ImageNode:
        return cls(
            id=data["id"],
            name=data["name"],
            image=DocumentImage.from_json(data["image"]),
            alt=data["alt"],
            href=data.get("href"),
            sizing=_opt_sizing(data.get("sizing")),
        )


@dataclass(frozen=True)
class ButtonNode(_Node):
    type: ClassVar[NodeType] = NodeType.BUTTON
    button: DocumentButton
    align: HorizontalAlign | None = None
    sizing: Sizing | None = None

    def to_json(self) -> dict[str, Any]:
        d = self._head()
        d["button"] = self.button.to_json()
        if self.align is not None:
            d["align"] = self.align.value
        if self.sizing is not None:
            d["sizing"] = self.sizing.value
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ButtonNode:
        align = data.get("align")
        return cls(
            id=data["id"],
            name=data["name"],
            button=DocumentButton.from_json(data["button"]),
            align=HorizontalAlign(align) if align is not None else None,
            sizing=_opt_sizing(data.get("sizing")),
        )


@dataclass(frozen=True)
class DividerNode(_Node):
    type: ClassVar[NodeType] = NodeType.DIVIDER
    thickness: int
    color: str
    style: DividerStyle
    width: int | None = None

    def to_json(self) -> dict[str, Any]:
        d = self._head()
        d["thickness"] = self.thickness
        d["color"] = self.color
        d["style"] = self.style.value
        if self.width is not None:
            d["width"] = self.width
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DividerNode:
        return cls(
            id=data["id"],
            name=data["name"],
            thickness=data["thickness"],
            color=data["color"],
            style=DividerStyle(data["style"]),
            width=data.get("width"),
        )


@dataclass(frozen=True)
class SpacerNode(_Node):
    type: ClassVar[NodeType] = NodeType.SPACER
    height: int
    background_color: str | None = None

    def to_json(self) -> dict[str, Any]:
        d = self._head()
        d["height"] = self.height
        if self.background_color is not None:
            d["background_color"] = self.background_color
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SpacerNode:
        return cls(
            id=data["id"],
            name=data["name"],
            height=data["height"],
            background_color=data.get("background_color"),
        )


@dataclass(frozen=True)
class RawNode(_Node):
    """Pass-through HTML, stored as given; the tree builder sanitises it first."""

    type: ClassVar[NodeType] = NodeType.RAW
    html: str
    reason: str

    def to_json(self) -> dict[str, Any]:
        d = self._head()
        d["html"] = self.html
        d["reason"] = self.reason
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RawNode:
        return cls(id=data["id"], name=data["name"], html=data["html"], reason=data["reason"])


ColumnChild = TextNode | ImageNode | ButtonNode | DividerNode | SpacerNode | RawNode


# ── Containers ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ColumnNode(_Node):
    type: ClassVar[NodeType] = NodeType.COLUMN
    children: tuple[ColumnChild, ...]
    style: ContainerStyle | None = None

    def to_json(self) -> dict[str, Any]:
        d = self._head()
        if self.style is not None:
            d["style"] = self.style.to_json()
        d["children"] = [c.to_json() for c in self.children]
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ColumnNode:
        return cls(
            id=data["id"],
            name=data["name"],
            children=tuple(_column_child(c) for c in data["children"]),
            style=_opt_style(data),
        )


@dataclass(frozen=True)
class SectionNode(_Node):
    type: ClassVar[NodeType] = NodeType.SECTION
    children: tuple[ColumnNode | RawNode, ...]
    style: ContainerStyle | None = None

    def to_json(self) -> dict[str, Any]:
        d = self._head()
        if self.style is not None:
            d["style"] = self.style.to_json()
        d["children"] = [c.to_json() for c in self.children]
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SectionNode:
        return cls(
            id=data["id"],
            name=data["name"],
            children=tuple(_section_child(c) for c in data["children"]),
            style=_opt_style(data),
        )


@dataclass(frozen=True)
class WrapperNode(_Node):
    type: ClassVar[NodeType] = NodeType.WRAPPER
    children: tuple[SectionNode | RawNode, ...]
    style: ContainerStyle | None = None

    def to_json(self) -> dict[str, Any]:
        d = self._head()
        if self.style is not None:
            d["style"] = self.style.to_json()
        d["children"] = [c.to_json() for c in self.children]
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> WrapperNode:
        return cls(
            id=data["id"],
            name=data["name"],
            children=tuple(_wrapper_child(c) for c in data["children"]),
            style=_opt_style(data),
        )


BodyNode = WrapperNode | SectionNode | RawNode
AnyNode = (
    WrapperNode
    | SectionNode
    | ColumnNode
    | TextNode
    | ImageNode
    | ButtonNode
    | DividerNode
    | SpacerNode
    | RawNode
)

NODE_CLASSES: dict[NodeType, type[AnyNode]] = {
    NodeType.WRAPPER: WrapperNode,
    NodeType.SECTION: SectionNode,
    NodeType.COLUMN: ColumnNode,
    NodeType.TEXT: TextNode,
    NodeType.IMAGE: ImageNode,
    NodeType.BUTTON: ButtonNode,
    NodeType.DIVIDER: DividerNode,
    NodeType.SPACER: SpacerNode,
    NodeType.RAW: RawNode,
}

# Allowed children per parent (spec S2, "DSL allows" column).
_BODY_CHILDREN = frozenset({NodeType.WRAPPER, NodeType.SECTION, NodeType.RAW})
_WRAPPER_CHILDREN = frozenset({NodeType.SECTION, NodeType.RAW})
_SECTION_CHILDREN = frozenset({NodeType.COLUMN, NodeType.RAW})
_COLUMN_CHILDREN = frozenset(
    {
        NodeType.TEXT,
        NodeType.IMAGE,
        NodeType.BUTTON,
        NodeType.DIVIDER,
        NodeType.SPACER,
        NodeType.RAW,
    }
)


def _node_from_json(data: dict[str, Any], allowed: frozenset[NodeType], parent: str) -> AnyNode:
    # Check the tag before parsing, so an illegal child fails here rather than
    # with a KeyError inside the wrong class's parser.
    node_type = NodeType(data["type"])
    if node_type not in allowed:
        raise ValueError(f"node type {node_type.value!r} not allowed in a {parent}")
    return NODE_CLASSES[node_type].from_json(data)


def _not_allowed(node: AnyNode, parent: str) -> ValueError:
    return ValueError(f"node type {node.type.value!r} not allowed in a {parent}")


# The isinstance checks below cannot fail after the tag check; they narrow the
# AnyNode union for the type checker.


def _body_child(data: dict[str, Any]) -> BodyNode:
    node = _node_from_json(data, _BODY_CHILDREN, "body")
    if not isinstance(node, WrapperNode | SectionNode | RawNode):
        raise _not_allowed(node, "body")
    return node


def _wrapper_child(data: dict[str, Any]) -> SectionNode | RawNode:
    node = _node_from_json(data, _WRAPPER_CHILDREN, "wrapper")
    if not isinstance(node, SectionNode | RawNode):
        raise _not_allowed(node, "wrapper")
    return node


def _section_child(data: dict[str, Any]) -> ColumnNode | RawNode:
    node = _node_from_json(data, _SECTION_CHILDREN, "section")
    if not isinstance(node, ColumnNode | RawNode):
        raise _not_allowed(node, "section")
    return node


def _column_child(data: dict[str, Any]) -> ColumnChild:
    node = _node_from_json(data, _COLUMN_CHILDREN, "column")
    if not isinstance(node, TextNode | ImageNode | ButtonNode | DividerNode | SpacerNode | RawNode):
        raise _not_allowed(node, "column")
    return node


def body_from_json(items: list[dict[str, Any]]) -> tuple[BodyNode, ...]:
    """Parse ``EmailDesignDocument.body``; raises ``ValueError`` on an unknown or misplaced type."""
    return tuple(_body_child(item) for item in items)
