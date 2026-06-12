"""EmailDesignDocument v1 — canonical intermediate representation.

Single contract between all input sources (Figma, Penpot, MJML, HTML)
and the email converter.  JSON Schema lives at
``data/schemas/email-design-document-v1.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator

from app.design_sync.figma.layout_analyzer import (
    ButtonElement,
    ColumnGroup,
    ColumnLayout,
    ContentGroup,
    DesignLayoutDescription,
    EmailSection,
    EmailSectionType,
    ImagePlaceholder,
    TextBlock,
    compute_column_width_fractions,
)
from app.design_sync.frame_rules import CornerRadiusSpec
from app.design_sync.protocol import (
    ExtractedColor,
    ExtractedGradient,
    ExtractedSpacing,
    ExtractedTokens,
    ExtractedTypography,
    ExtractedVariable,
    StyleRun,
)

if TYPE_CHECKING:
    from app.design_sync.protocol import DesignFileStructure, DesignNode
    from app.design_sync.vlm_classifier import VLMSectionClassification

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "schemas" / "email-design-document-v1.json"
)


# ── helpers ─────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text())  # type: ignore[no-any-return]


@lru_cache(maxsize=1)
def _get_validator() -> Draft202012Validator:
    return Draft202012Validator(_load_schema())


# ── Document sub-structures ─────────────────────────────────────────


@dataclass(frozen=True)
class DocumentSource:
    """Origin metadata for the design document."""

    provider: str
    file_ref: str | None = None
    synced_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"provider": self.provider}
        if self.file_ref is not None:
            d["file_ref"] = self.file_ref
        if self.synced_at is not None:
            d["synced_at"] = self.synced_at
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentSource:
        return cls(
            provider=data["provider"],
            file_ref=data.get("file_ref"),
            synced_at=data.get("synced_at"),
        )


@dataclass(frozen=True)
class DocumentColor:
    """A colour token."""

    name: str
    hex: str
    opacity: float = 1.0

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "hex": self.hex}
        if self.opacity != 1.0:
            d["opacity"] = self.opacity
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentColor:
        return cls(name=data["name"], hex=data["hex"], opacity=data.get("opacity", 1.0))


@dataclass(frozen=True)
class DocumentTypography:
    """A typography token."""

    name: str
    family: str
    weight: str
    size: float
    line_height: float
    letter_spacing: float | None = None
    text_transform: str | None = None
    text_decoration: str | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "family": self.family,
            "weight": self.weight,
            "size": self.size,
            "line_height": self.line_height,
        }
        if self.letter_spacing is not None:
            d["letter_spacing"] = self.letter_spacing
        if self.text_transform is not None:
            d["text_transform"] = self.text_transform
        if self.text_decoration is not None:
            d["text_decoration"] = self.text_decoration
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentTypography:
        return cls(
            name=data["name"],
            family=data["family"],
            weight=data["weight"],
            size=data["size"],
            line_height=data["line_height"],
            letter_spacing=data.get("letter_spacing"),
            text_transform=data.get("text_transform"),
            text_decoration=data.get("text_decoration"),
        )


@dataclass(frozen=True)
class DocumentSpacing:
    """A spacing token."""

    name: str
    value: float

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentSpacing:
        return cls(name=data["name"], value=data["value"])


@dataclass(frozen=True)
class DocumentGradientStop:
    """A single gradient colour stop."""

    hex: str
    position: float

    def to_json(self) -> dict[str, Any]:
        return {"hex": self.hex, "position": self.position}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentGradientStop:
        return cls(hex=data["hex"], position=data["position"])


@dataclass(frozen=True)
class DocumentGradient:
    """A gradient token."""

    name: str
    type: str
    angle: float
    stops: tuple[DocumentGradientStop, ...]
    fallback_hex: str
    node_id: str | None = None  # source node, for per-section reattachment (52.5)

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "angle": self.angle,
            "stops": [s.to_json() for s in self.stops],
            "fallback_hex": self.fallback_hex,
        }
        if self.node_id is not None:
            d["node_id"] = self.node_id
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentGradient:
        return cls(
            name=data["name"],
            type=data["type"],
            angle=data["angle"],
            stops=tuple(DocumentGradientStop.from_json(s) for s in data["stops"]),
            fallback_hex=data["fallback_hex"],
            node_id=data.get("node_id"),
        )


@dataclass(frozen=True)
class DocumentVariable:
    """A design variable."""

    name: str
    collection: str
    type: str
    values_by_mode: dict[str, Any]
    is_alias: bool = False
    alias_path: str | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "collection": self.collection,
            "type": self.type,
            "values_by_mode": self.values_by_mode,
        }
        if self.is_alias:
            d["is_alias"] = self.is_alias
        if self.alias_path is not None:
            d["alias_path"] = self.alias_path
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentVariable:
        return cls(
            name=data["name"],
            collection=data["collection"],
            type=data["type"],
            values_by_mode=data["values_by_mode"],
            is_alias=data.get("is_alias", False),
            alias_path=data.get("alias_path"),
        )


@dataclass(frozen=True)
class DocumentTokens:
    """All design tokens in the document."""

    colors: list[DocumentColor] = field(default_factory=list[DocumentColor])
    typography: list[DocumentTypography] = field(default_factory=list[DocumentTypography])
    spacing: list[DocumentSpacing] = field(default_factory=list[DocumentSpacing])
    dark_colors: list[DocumentColor] = field(default_factory=list[DocumentColor])
    gradients: list[DocumentGradient] = field(default_factory=list[DocumentGradient])
    variables: list[DocumentVariable] = field(default_factory=list[DocumentVariable])
    stroke_colors: list[DocumentColor] = field(default_factory=list[DocumentColor])
    variables_source: bool = False
    modes: dict[str, str] | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.colors:
            d["colors"] = [c.to_json() for c in self.colors]
        if self.typography:
            d["typography"] = [t.to_json() for t in self.typography]
        if self.spacing:
            d["spacing"] = [s.to_json() for s in self.spacing]
        if self.dark_colors:
            d["dark_colors"] = [c.to_json() for c in self.dark_colors]
        if self.gradients:
            d["gradients"] = [g.to_json() for g in self.gradients]
        if self.variables:
            d["variables"] = [v.to_json() for v in self.variables]
        if self.stroke_colors:
            d["stroke_colors"] = [c.to_json() for c in self.stroke_colors]
        if self.variables_source:
            d["variables_source"] = self.variables_source
        if self.modes is not None:
            d["modes"] = self.modes
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentTokens:
        return cls(
            colors=[DocumentColor.from_json(c) for c in data.get("colors", [])],
            typography=[DocumentTypography.from_json(t) for t in data.get("typography", [])],
            spacing=[DocumentSpacing.from_json(s) for s in data.get("spacing", [])],
            dark_colors=[DocumentColor.from_json(c) for c in data.get("dark_colors", [])],
            gradients=[DocumentGradient.from_json(g) for g in data.get("gradients", [])],
            variables=[DocumentVariable.from_json(v) for v in data.get("variables", [])],
            stroke_colors=[DocumentColor.from_json(c) for c in data.get("stroke_colors", [])],
            variables_source=data.get("variables_source", False),
            modes=data.get("modes"),
        )

    def to_extracted_tokens(self) -> ExtractedTokens:
        """Bridge to the existing ExtractedTokens dataclass."""
        return ExtractedTokens(
            colors=[ExtractedColor(name=c.name, hex=c.hex, opacity=c.opacity) for c in self.colors],
            typography=[
                ExtractedTypography(
                    name=t.name,
                    family=t.family,
                    weight=t.weight,
                    size=t.size,
                    line_height=t.line_height,
                    letter_spacing=t.letter_spacing,
                    text_transform=t.text_transform,
                    text_decoration=t.text_decoration,
                )
                for t in self.typography
            ],
            spacing=[ExtractedSpacing(name=s.name, value=s.value) for s in self.spacing],
            variables_source=self.variables_source,
            modes=self.modes,
            stroke_colors=[
                ExtractedColor(name=c.name, hex=c.hex, opacity=c.opacity)
                for c in self.stroke_colors
            ],
            variables=[
                ExtractedVariable(
                    name=v.name,
                    collection=v.collection,
                    type=v.type,
                    values_by_mode=v.values_by_mode,
                    is_alias=v.is_alias,
                    alias_path=v.alias_path,
                )
                for v in self.variables
            ],
            dark_colors=[
                ExtractedColor(name=c.name, hex=c.hex, opacity=c.opacity) for c in self.dark_colors
            ],
            gradients=[
                ExtractedGradient(
                    name=g.name,
                    type=g.type,
                    angle=g.angle,
                    stops=tuple((s.hex, s.position) for s in g.stops),
                    fallback_hex=g.fallback_hex,
                    node_id=g.node_id,
                )
                for g in self.gradients
            ],
        )

    @classmethod
    def from_extracted_tokens(cls, tokens: ExtractedTokens) -> DocumentTokens:
        """Reverse bridge: build DocumentTokens from ExtractedTokens."""
        return cls(
            colors=[
                DocumentColor(name=c.name, hex=c.hex, opacity=c.opacity) for c in tokens.colors
            ],
            typography=[
                DocumentTypography(
                    name=t.name,
                    family=t.family,
                    weight=t.weight,
                    size=t.size,
                    line_height=t.line_height,
                    letter_spacing=t.letter_spacing,
                    text_transform=t.text_transform,
                    text_decoration=t.text_decoration,
                )
                for t in tokens.typography
            ],
            spacing=[DocumentSpacing(name=s.name, value=s.value) for s in tokens.spacing],
            dark_colors=[
                DocumentColor(name=c.name, hex=c.hex, opacity=c.opacity) for c in tokens.dark_colors
            ],
            gradients=[
                DocumentGradient(
                    name=g.name,
                    type=g.type,
                    angle=g.angle,
                    stops=tuple(DocumentGradientStop(hex=s[0], position=s[1]) for s in g.stops),
                    fallback_hex=g.fallback_hex,
                    node_id=g.node_id,
                )
                for g in tokens.gradients
            ],
            variables=[
                DocumentVariable(
                    name=v.name,
                    collection=v.collection,
                    type=v.type,
                    values_by_mode=v.values_by_mode,
                    is_alias=v.is_alias,
                    alias_path=v.alias_path,
                )
                for v in tokens.variables
            ],
            stroke_colors=[
                DocumentColor(name=c.name, hex=c.hex, opacity=c.opacity)
                for c in tokens.stroke_colors
            ],
            variables_source=tokens.variables_source,
            modes=tokens.modes,
        )


# ── Section sub-structures ──────────────────────────────────────────


@dataclass(frozen=True)
class DocumentStyleRun:
    """A styled text segment within a text element (mirrors ``StyleRun``)."""

    start: int
    end: int
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    color_hex: str | None = None
    font_size: float | None = None
    link_url: str | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"start": self.start, "end": self.end}
        if self.bold:
            d["bold"] = self.bold
        if self.italic:
            d["italic"] = self.italic
        if self.underline:
            d["underline"] = self.underline
        if self.strikethrough:
            d["strikethrough"] = self.strikethrough
        if self.color_hex is not None:
            d["color_hex"] = self.color_hex
        if self.font_size is not None:
            d["font_size"] = self.font_size
        if self.link_url is not None:
            d["link_url"] = self.link_url
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentStyleRun:
        return cls(
            start=data["start"],
            end=data["end"],
            bold=data.get("bold", False),
            italic=data.get("italic", False),
            underline=data.get("underline", False),
            strikethrough=data.get("strikethrough", False),
            color_hex=data.get("color_hex"),
            font_size=data.get("font_size"),
            link_url=data.get("link_url"),
        )

    @classmethod
    def from_style_run(cls, run: StyleRun) -> DocumentStyleRun:
        return cls(
            start=run.start,
            end=run.end,
            bold=run.bold,
            italic=run.italic,
            underline=run.underline,
            strikethrough=run.strikethrough,
            color_hex=run.color_hex,
            font_size=run.font_size,
            link_url=run.link_url,
        )

    def to_style_run(self) -> StyleRun:
        return StyleRun(
            start=self.start,
            end=self.end,
            bold=self.bold,
            italic=self.italic,
            underline=self.underline,
            strikethrough=self.strikethrough,
            color_hex=self.color_hex,
            font_size=self.font_size,
            link_url=self.link_url,
        )


@dataclass(frozen=True)
class DocumentCornerRadiusSpec:
    """Per-corner radius spec (mirrors ``CornerRadiusSpec`` — Rule 8 / Rule 10)."""

    scalar: float | None = None
    per_corner: tuple[float, float, float, float] | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.scalar is not None:
            d["scalar"] = self.scalar
        if self.per_corner is not None:
            d["per_corner"] = list(self.per_corner)
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentCornerRadiusSpec:
        pc = data.get("per_corner")
        per_corner = (
            (float(pc[0]), float(pc[1]), float(pc[2]), float(pc[3]))
            if pc is not None and len(pc) == 4
            else None
        )
        return cls(scalar=data.get("scalar"), per_corner=per_corner)

    @classmethod
    def from_spec(cls, spec: CornerRadiusSpec) -> DocumentCornerRadiusSpec:
        return cls(scalar=spec.scalar, per_corner=spec.per_corner)

    def to_spec(self) -> CornerRadiusSpec:
        return CornerRadiusSpec(scalar=self.scalar, per_corner=self.per_corner)


@dataclass(frozen=True)
class DocumentText:
    """A text element within a section."""

    node_id: str
    content: str
    font_size: float | None = None
    is_heading: bool = False
    font_family: str | None = None
    font_weight: int | None = None
    line_height: float | None = None
    letter_spacing: float | None = None
    color: str | None = None
    text_align: str | None = None  # left|center|right|justify
    text_transform: str | None = None  # uppercase|lowercase|capitalize
    text_decoration: str | None = None  # underline|line-through
    hyperlink: str | None = None
    role_hint: str | None = None  # heading|body|label|cta
    layout_align: str | None = None  # left|center|right
    style_runs: tuple[DocumentStyleRun, ...] = ()

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"node_id": self.node_id, "content": self.content}
        if self.font_size is not None:
            d["font_size"] = self.font_size
        if self.is_heading:
            d["is_heading"] = self.is_heading
        if self.font_family is not None:
            d["font_family"] = self.font_family
        if self.font_weight is not None:
            d["font_weight"] = self.font_weight
        if self.line_height is not None:
            d["line_height"] = self.line_height
        if self.letter_spacing is not None:
            d["letter_spacing"] = self.letter_spacing
        if self.color is not None:
            d["color"] = self.color
        if self.text_align is not None:
            d["text_align"] = self.text_align
        if self.text_transform is not None:
            d["text_transform"] = self.text_transform
        if self.text_decoration is not None:
            d["text_decoration"] = self.text_decoration
        if self.hyperlink is not None:
            d["hyperlink"] = self.hyperlink
        if self.role_hint is not None:
            d["role_hint"] = self.role_hint
        if self.layout_align is not None:
            d["layout_align"] = self.layout_align
        if self.style_runs:
            d["style_runs"] = [r.to_json() for r in self.style_runs]
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentText:
        return cls(
            node_id=data["node_id"],
            content=data["content"],
            font_size=data.get("font_size"),
            is_heading=data.get("is_heading", False),
            font_family=data.get("font_family"),
            font_weight=data.get("font_weight"),
            line_height=data.get("line_height"),
            letter_spacing=data.get("letter_spacing"),
            color=data.get("color"),
            text_align=data.get("text_align"),
            text_transform=data.get("text_transform"),
            text_decoration=data.get("text_decoration"),
            hyperlink=data.get("hyperlink"),
            role_hint=data.get("role_hint"),
            layout_align=data.get("layout_align"),
            style_runs=tuple(DocumentStyleRun.from_json(r) for r in data.get("style_runs", [])),
        )

    @classmethod
    def from_text_block(cls, t: TextBlock) -> DocumentText:
        return cls(
            node_id=t.node_id,
            content=t.content,
            font_size=t.font_size,
            is_heading=t.is_heading,
            font_family=t.font_family,
            font_weight=t.font_weight,
            line_height=t.line_height,
            letter_spacing=t.letter_spacing,
            color=t.text_color,
            text_align=t.text_align,
            text_transform=t.text_transform,
            text_decoration=t.text_decoration,
            hyperlink=t.hyperlink,
            role_hint=t.role_hint,
            layout_align=t.layout_align,
            style_runs=tuple(DocumentStyleRun.from_style_run(r) for r in t.style_runs),
        )

    def to_text_block(self) -> TextBlock:
        return TextBlock(
            node_id=self.node_id,
            content=self.content,
            font_size=self.font_size,
            is_heading=self.is_heading,
            font_family=self.font_family,
            font_weight=self.font_weight,
            line_height=self.line_height,
            letter_spacing=self.letter_spacing,
            text_color=self.color,
            text_align=self.text_align,
            text_transform=self.text_transform,
            text_decoration=self.text_decoration,
            hyperlink=self.hyperlink,
            role_hint=self.role_hint,
            layout_align=self.layout_align,
            style_runs=tuple(r.to_style_run() for r in self.style_runs),
        )


@dataclass(frozen=True)
class DocumentImage:
    """An image placeholder within a section."""

    node_id: str
    node_name: str
    width: float | None = None
    height: float | None = None
    is_background: bool = False
    export_node_id: str | None = None
    corner_radius_spec: DocumentCornerRadiusSpec | None = None
    # Non-button border (52.5) — captured losslessly; rendering lands in 53.3.
    stroke_color: str | None = None
    stroke_weight: float | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"node_id": self.node_id, "node_name": self.node_name}
        if self.width is not None:
            d["width"] = self.width
        if self.height is not None:
            d["height"] = self.height
        if self.is_background:
            d["is_background"] = self.is_background
        if self.export_node_id is not None:
            d["export_node_id"] = self.export_node_id
        if self.corner_radius_spec is not None:
            d["corner_radius_spec"] = self.corner_radius_spec.to_json()
        if self.stroke_color is not None:
            d["stroke_color"] = self.stroke_color
        if self.stroke_weight is not None:
            d["stroke_weight"] = self.stroke_weight
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentImage:
        crs = data.get("corner_radius_spec")
        return cls(
            node_id=data["node_id"],
            node_name=data["node_name"],
            width=data.get("width"),
            height=data.get("height"),
            is_background=data.get("is_background", False),
            export_node_id=data.get("export_node_id"),
            corner_radius_spec=(
                DocumentCornerRadiusSpec.from_json(crs) if crs is not None else None
            ),
            stroke_color=data.get("stroke_color"),
            stroke_weight=data.get("stroke_weight"),
        )

    @classmethod
    def from_image_placeholder(cls, i: ImagePlaceholder) -> DocumentImage:
        return cls(
            node_id=i.node_id,
            node_name=i.node_name,
            width=i.width,
            height=i.height,
            is_background=i.is_background,
            export_node_id=i.export_node_id,
            corner_radius_spec=(
                DocumentCornerRadiusSpec.from_spec(i.corner_radius_spec)
                if i.corner_radius_spec is not None
                else None
            ),
            stroke_color=i.stroke_color,
            stroke_weight=i.stroke_weight,
        )

    def to_image_placeholder(self) -> ImagePlaceholder:
        return ImagePlaceholder(
            node_id=self.node_id,
            node_name=self.node_name,
            width=self.width,
            height=self.height,
            is_background=self.is_background,
            export_node_id=self.export_node_id,
            corner_radius_spec=(
                self.corner_radius_spec.to_spec() if self.corner_radius_spec is not None else None
            ),
            stroke_color=self.stroke_color,
            stroke_weight=self.stroke_weight,
        )


@dataclass(frozen=True)
class DocumentButton:
    """A CTA button within a section."""

    node_id: str
    text: str
    width: float | None = None
    height: float | None = None
    url: str | None = None
    border_radius: float | None = None
    fill_color: str | None = None
    text_color: str | None = None
    stroke_color: str | None = None
    stroke_weight: float | None = None
    icon_node_id: str | None = None
    font_size: float | None = None
    font_weight: int | None = None
    font_family: str | None = None
    corner_radius_spec: DocumentCornerRadiusSpec | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"node_id": self.node_id, "text": self.text}
        if self.width is not None:
            d["width"] = self.width
        if self.height is not None:
            d["height"] = self.height
        if self.url is not None:
            d["url"] = self.url
        if self.border_radius is not None:
            d["border_radius"] = self.border_radius
        if self.fill_color is not None:
            d["fill_color"] = self.fill_color
        if self.text_color is not None:
            d["text_color"] = self.text_color
        if self.stroke_color is not None:
            d["stroke_color"] = self.stroke_color
        if self.stroke_weight is not None:
            d["stroke_weight"] = self.stroke_weight
        if self.icon_node_id is not None:
            d["icon_node_id"] = self.icon_node_id
        if self.font_size is not None:
            d["font_size"] = self.font_size
        if self.font_weight is not None:
            d["font_weight"] = self.font_weight
        if self.font_family is not None:
            d["font_family"] = self.font_family
        if self.corner_radius_spec is not None:
            d["corner_radius_spec"] = self.corner_radius_spec.to_json()
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentButton:
        crs = data.get("corner_radius_spec")
        return cls(
            node_id=data["node_id"],
            text=data["text"],
            width=data.get("width"),
            height=data.get("height"),
            url=data.get("url"),
            border_radius=data.get("border_radius"),
            fill_color=data.get("fill_color"),
            text_color=data.get("text_color"),
            stroke_color=data.get("stroke_color"),
            stroke_weight=data.get("stroke_weight"),
            icon_node_id=data.get("icon_node_id"),
            font_size=data.get("font_size"),
            font_weight=data.get("font_weight"),
            font_family=data.get("font_family"),
            corner_radius_spec=(
                DocumentCornerRadiusSpec.from_json(crs) if crs is not None else None
            ),
        )

    @classmethod
    def from_button_element(cls, b: ButtonElement) -> DocumentButton:
        return cls(
            node_id=b.node_id,
            text=b.text,
            width=b.width,
            height=b.height,
            url=b.url,
            border_radius=b.border_radius,
            fill_color=b.fill_color,
            text_color=b.text_color,
            stroke_color=b.stroke_color,
            stroke_weight=b.stroke_weight,
            icon_node_id=b.icon_node_id,
            font_size=b.font_size,
            font_weight=b.font_weight,
            font_family=b.font_family,
            corner_radius_spec=(
                DocumentCornerRadiusSpec.from_spec(b.corner_radius_spec)
                if b.corner_radius_spec is not None
                else None
            ),
        )

    def to_button_element(self) -> ButtonElement:
        return ButtonElement(
            node_id=self.node_id,
            text=self.text,
            width=self.width,
            height=self.height,
            fill_color=self.fill_color,
            url=self.url,
            border_radius=self.border_radius,
            text_color=self.text_color,
            stroke_color=self.stroke_color,
            stroke_weight=self.stroke_weight,
            icon_node_id=self.icon_node_id,
            font_size=self.font_size,
            font_weight=self.font_weight,
            font_family=self.font_family,
            corner_radius_spec=(
                self.corner_radius_spec.to_spec() if self.corner_radius_spec is not None else None
            ),
        )


@dataclass(frozen=True)
class DocumentColumn:
    """A column group within a multi-column section."""

    column_idx: int
    node_id: str
    node_name: str
    width: float | None = None
    texts: list[DocumentText] = field(default_factory=list[DocumentText])
    images: list[DocumentImage] = field(default_factory=list[DocumentImage])
    buttons: list[DocumentButton] = field(default_factory=list[DocumentButton])

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "column_idx": self.column_idx,
            "node_id": self.node_id,
            "node_name": self.node_name,
        }
        if self.width is not None:
            d["width"] = self.width
        if self.texts:
            d["texts"] = [t.to_json() for t in self.texts]
        if self.images:
            d["images"] = [i.to_json() for i in self.images]
        if self.buttons:
            d["buttons"] = [b.to_json() for b in self.buttons]
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentColumn:
        return cls(
            column_idx=data["column_idx"],
            node_id=data["node_id"],
            node_name=data["node_name"],
            width=data.get("width"),
            texts=[DocumentText.from_json(t) for t in data.get("texts", [])],
            images=[DocumentImage.from_json(i) for i in data.get("images", [])],
            buttons=[DocumentButton.from_json(b) for b in data.get("buttons", [])],
        )

    @classmethod
    def from_column_group(cls, c: ColumnGroup) -> DocumentColumn:
        return cls(
            column_idx=c.column_idx,
            node_id=c.node_id,
            node_name=c.node_name,
            width=c.width,
            texts=[DocumentText.from_text_block(t) for t in c.texts],
            images=[DocumentImage.from_image_placeholder(i) for i in c.images],
            buttons=[DocumentButton.from_button_element(b) for b in c.buttons],
        )

    def to_column_group(self) -> ColumnGroup:
        return ColumnGroup(
            column_idx=self.column_idx,
            node_id=self.node_id,
            node_name=self.node_name,
            width=self.width,
            texts=[t.to_text_block() for t in self.texts],
            images=[i.to_image_placeholder() for i in self.images],
            buttons=[b.to_button_element() for b in self.buttons],
        )


@dataclass(frozen=True)
class DocumentContentGroup:
    """A visually distinct content block within a section (mirrors ``ContentGroup``)."""

    frame_node_id: str
    frame_name: str
    texts: list[DocumentText] = field(default_factory=list[DocumentText])
    images: list[DocumentImage] = field(default_factory=list[DocumentImage])
    buttons: list[DocumentButton] = field(default_factory=list[DocumentButton])

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "frame_node_id": self.frame_node_id,
            "frame_name": self.frame_name,
        }
        if self.texts:
            d["texts"] = [t.to_json() for t in self.texts]
        if self.images:
            d["images"] = [i.to_json() for i in self.images]
        if self.buttons:
            d["buttons"] = [b.to_json() for b in self.buttons]
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentContentGroup:
        return cls(
            frame_node_id=data["frame_node_id"],
            frame_name=data["frame_name"],
            texts=[DocumentText.from_json(t) for t in data.get("texts", [])],
            images=[DocumentImage.from_json(i) for i in data.get("images", [])],
            buttons=[DocumentButton.from_json(b) for b in data.get("buttons", [])],
        )

    @classmethod
    def from_content_group(cls, g: ContentGroup) -> DocumentContentGroup:
        return cls(
            frame_node_id=g.frame_node_id,
            frame_name=g.frame_name,
            texts=[DocumentText.from_text_block(t) for t in g.texts],
            images=[DocumentImage.from_image_placeholder(i) for i in g.images],
            buttons=[DocumentButton.from_button_element(b) for b in g.buttons],
        )

    def to_content_group(self) -> ContentGroup:
        return ContentGroup(
            frame_node_id=self.frame_node_id,
            frame_name=self.frame_name,
            texts=[t.to_text_block() for t in self.texts],
            images=[i.to_image_placeholder() for i in self.images],
            buttons=[b.to_button_element() for b in self.buttons],
        )


@dataclass(frozen=True)
class DocumentPadding:
    """Section padding values."""

    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0
    left: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {"top": self.top, "right": self.right, "bottom": self.bottom, "left": self.left}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentPadding:
        return cls(
            top=data.get("top", 0.0),
            right=data.get("right", 0.0),
            bottom=data.get("bottom", 0.0),
            left=data.get("left", 0.0),
        )


@dataclass(frozen=True)
class DocumentSection:
    """A detected email section."""

    id: str
    type: str
    node_name: str | None = None
    y_position: float | None = None
    x_position: float | None = None
    width: float | None = None
    height: float | None = None
    column_layout: str = "single"
    column_count: int = 1
    padding: DocumentPadding | None = None
    item_spacing: float | None = None
    background_color: str | None = None
    texts: list[DocumentText] = field(default_factory=list[DocumentText])
    images: list[DocumentImage] = field(default_factory=list[DocumentImage])
    buttons: list[DocumentButton] = field(default_factory=list[DocumentButton])
    columns: list[DocumentColumn] = field(default_factory=list[DocumentColumn])
    content_roles: list[str] = field(default_factory=list[str])
    spacing_after: float | None = None
    classification_confidence: float | None = None
    element_gaps: list[float] = field(default_factory=list[float])
    # Phase-50 structural fields carried through from EmailSection.
    child_content_groups: list[DocumentContentGroup] = field(
        default_factory=list[DocumentContentGroup]
    )
    boundary_above: str | None = None
    boundary_below: str | None = None
    sampled_top_color: str | None = None
    sampled_bottom_color: str | None = None
    container_bg: str | None = None
    parent_wrapper_id: str | None = None
    inner_bg: str | None = None
    inner_radius: float | None = None
    inner_card_fixed_width: int | None = None
    is_physical_card_surface: bool = False
    physical_card_signals: tuple[str, ...] = ()
    vlm_classification: str | None = None
    vlm_confidence: float | None = None
    # Non-button border (52.5) — captured losslessly; rendering lands in 53.3.
    stroke_color: str | None = None
    stroke_weight: float | None = None
    # D3 follow-up — same-row peel id (see EmailSection.peel_row_id).
    peel_row_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "type": self.type}
        if self.node_name is not None:
            d["node_name"] = self.node_name
        if self.y_position is not None:
            d["y_position"] = self.y_position
        if self.x_position is not None:
            d["x_position"] = self.x_position
        if self.peel_row_id is not None:
            d["peel_row_id"] = self.peel_row_id
        if self.width is not None:
            d["width"] = self.width
        if self.height is not None:
            d["height"] = self.height
        if self.column_layout != "single":
            d["column_layout"] = self.column_layout
        if self.column_count != 1:
            d["column_count"] = self.column_count
        if self.padding is not None:
            d["padding"] = self.padding.to_json()
        if self.item_spacing is not None:
            d["item_spacing"] = self.item_spacing
        if self.background_color is not None:
            d["background_color"] = self.background_color
        if self.texts:
            d["texts"] = [t.to_json() for t in self.texts]
        if self.images:
            d["images"] = [i.to_json() for i in self.images]
        if self.buttons:
            d["buttons"] = [b.to_json() for b in self.buttons]
        if self.columns:
            d["columns"] = [c.to_json() for c in self.columns]
        if self.content_roles:
            d["content_roles"] = list(self.content_roles)
        if self.spacing_after is not None:
            d["spacing_after"] = self.spacing_after
        if self.classification_confidence is not None:
            d["classification_confidence"] = self.classification_confidence
        if self.element_gaps:
            d["element_gaps"] = list(self.element_gaps)
        if self.child_content_groups:
            d["child_content_groups"] = [g.to_json() for g in self.child_content_groups]
        if self.boundary_above is not None:
            d["boundary_above"] = self.boundary_above
        if self.boundary_below is not None:
            d["boundary_below"] = self.boundary_below
        if self.sampled_top_color is not None:
            d["sampled_top_color"] = self.sampled_top_color
        if self.sampled_bottom_color is not None:
            d["sampled_bottom_color"] = self.sampled_bottom_color
        if self.container_bg is not None:
            d["container_bg"] = self.container_bg
        if self.parent_wrapper_id is not None:
            d["parent_wrapper_id"] = self.parent_wrapper_id
        if self.inner_bg is not None:
            d["inner_bg"] = self.inner_bg
        if self.inner_radius is not None:
            d["inner_radius"] = self.inner_radius
        if self.inner_card_fixed_width is not None:
            d["inner_card_fixed_width"] = self.inner_card_fixed_width
        if self.is_physical_card_surface:
            d["is_physical_card_surface"] = self.is_physical_card_surface
        if self.physical_card_signals:
            d["physical_card_signals"] = list(self.physical_card_signals)
        if self.vlm_classification is not None:
            d["vlm_classification"] = self.vlm_classification
        if self.vlm_confidence is not None:
            d["vlm_confidence"] = self.vlm_confidence
        if self.stroke_color is not None:
            d["stroke_color"] = self.stroke_color
        if self.stroke_weight is not None:
            d["stroke_weight"] = self.stroke_weight
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentSection:
        padding_data = data.get("padding")
        return cls(
            id=data["id"],
            type=data["type"],
            node_name=data.get("node_name"),
            y_position=data.get("y_position"),
            x_position=data.get("x_position"),
            peel_row_id=data.get("peel_row_id"),
            width=data.get("width"),
            height=data.get("height"),
            column_layout=data.get("column_layout", "single"),
            column_count=data.get("column_count", 1),
            padding=DocumentPadding.from_json(padding_data) if padding_data is not None else None,
            item_spacing=data.get("item_spacing"),
            background_color=data.get("background_color"),
            texts=[DocumentText.from_json(t) for t in data.get("texts", [])],
            images=[DocumentImage.from_json(i) for i in data.get("images", [])],
            buttons=[DocumentButton.from_json(b) for b in data.get("buttons", [])],
            columns=[DocumentColumn.from_json(c) for c in data.get("columns", [])],
            content_roles=data.get("content_roles", []),
            spacing_after=data.get("spacing_after"),
            classification_confidence=data.get("classification_confidence"),
            element_gaps=data.get("element_gaps", []),
            child_content_groups=[
                DocumentContentGroup.from_json(g) for g in data.get("child_content_groups", [])
            ],
            boundary_above=data.get("boundary_above"),
            boundary_below=data.get("boundary_below"),
            sampled_top_color=data.get("sampled_top_color"),
            sampled_bottom_color=data.get("sampled_bottom_color"),
            container_bg=data.get("container_bg"),
            parent_wrapper_id=data.get("parent_wrapper_id"),
            inner_bg=data.get("inner_bg"),
            inner_radius=data.get("inner_radius"),
            inner_card_fixed_width=data.get("inner_card_fixed_width"),
            is_physical_card_surface=data.get("is_physical_card_surface", False),
            physical_card_signals=tuple(data.get("physical_card_signals", [])),
            vlm_classification=data.get("vlm_classification"),
            vlm_confidence=data.get("vlm_confidence"),
            stroke_color=data.get("stroke_color"),
            stroke_weight=data.get("stroke_weight"),
        )

    def to_email_section(self) -> EmailSection:
        """Bridge to the existing EmailSection dataclass."""
        # A8 (Phase 53 D2): fractions are derived state — recompute from the
        # round-tripped per-column widths instead of persisting a second copy.
        pad = self.padding
        column_groups = [c.to_column_group() for c in self.columns]
        return EmailSection(
            section_type=EmailSectionType(self.type),
            node_id=self.id,
            node_name=self.node_name or "",
            y_position=self.y_position,
            x_position=self.x_position,
            width=self.width,
            height=self.height,
            column_layout=ColumnLayout(self.column_layout),
            column_count=self.column_count,
            texts=[t.to_text_block() for t in self.texts],
            images=[i.to_image_placeholder() for i in self.images],
            buttons=[b.to_button_element() for b in self.buttons],
            spacing_after=self.spacing_after,
            bg_color=self.background_color,
            padding_top=pad.top if pad else None,
            padding_right=pad.right if pad else None,
            padding_bottom=pad.bottom if pad else None,
            padding_left=pad.left if pad else None,
            item_spacing=self.item_spacing,
            element_gaps=tuple(self.element_gaps),
            column_groups=column_groups,
            column_width_fractions=compute_column_width_fractions(column_groups),
            classification_confidence=self.classification_confidence,
            vlm_classification=self.vlm_classification,
            vlm_confidence=self.vlm_confidence,
            content_roles=tuple(self.content_roles),
            child_content_groups=[g.to_content_group() for g in self.child_content_groups],
            boundary_above=self.boundary_above,
            boundary_below=self.boundary_below,
            sampled_top_color=self.sampled_top_color,
            sampled_bottom_color=self.sampled_bottom_color,
            container_bg=self.container_bg,
            parent_wrapper_id=self.parent_wrapper_id,
            inner_bg=self.inner_bg,
            inner_radius=self.inner_radius,
            inner_card_fixed_width=self.inner_card_fixed_width,
            is_physical_card_surface=self.is_physical_card_surface,
            physical_card_signals=self.physical_card_signals,
            stroke_color=self.stroke_color,
            stroke_weight=self.stroke_weight,
            peel_row_id=self.peel_row_id,
        )

    @classmethod
    def from_email_section(cls, section: EmailSection) -> DocumentSection:
        """Reverse bridge: build DocumentSection from EmailSection."""
        padding: DocumentPadding | None = None
        if any(
            v is not None
            for v in (
                section.padding_top,
                section.padding_right,
                section.padding_bottom,
                section.padding_left,
            )
        ):
            padding = DocumentPadding(
                top=section.padding_top if section.padding_top is not None else 0.0,
                right=section.padding_right if section.padding_right is not None else 0.0,
                bottom=section.padding_bottom if section.padding_bottom is not None else 0.0,
                left=section.padding_left if section.padding_left is not None else 0.0,
            )
        return cls(
            id=section.node_id,
            type=section.section_type.value,
            node_name=section.node_name or None,
            y_position=section.y_position,
            x_position=section.x_position,
            peel_row_id=section.peel_row_id,
            width=section.width,
            height=section.height,
            column_layout=section.column_layout.value,
            column_count=section.column_count,
            padding=padding,
            item_spacing=section.item_spacing,
            background_color=section.bg_color,
            texts=[DocumentText.from_text_block(t) for t in section.texts],
            images=[DocumentImage.from_image_placeholder(i) for i in section.images],
            buttons=[DocumentButton.from_button_element(b) for b in section.buttons],
            columns=[DocumentColumn.from_column_group(c) for c in section.column_groups],
            content_roles=list(section.content_roles),
            spacing_after=section.spacing_after,
            classification_confidence=section.classification_confidence,
            element_gaps=list(section.element_gaps),
            child_content_groups=[
                DocumentContentGroup.from_content_group(g) for g in section.child_content_groups
            ],
            boundary_above=section.boundary_above,
            boundary_below=section.boundary_below,
            sampled_top_color=section.sampled_top_color,
            sampled_bottom_color=section.sampled_bottom_color,
            container_bg=section.container_bg,
            parent_wrapper_id=section.parent_wrapper_id,
            inner_bg=section.inner_bg,
            inner_radius=section.inner_radius,
            inner_card_fixed_width=section.inner_card_fixed_width,
            is_physical_card_surface=section.is_physical_card_surface,
            physical_card_signals=section.physical_card_signals,
            vlm_classification=section.vlm_classification,
            vlm_confidence=section.vlm_confidence,
            stroke_color=section.stroke_color,
            stroke_weight=section.stroke_weight,
        )


@dataclass(frozen=True)
class DocumentLayout:
    """Global layout settings."""

    container_width: int = 600
    naming_convention: str | None = None
    overall_width: float | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"container_width": self.container_width}
        if self.naming_convention is not None:
            d["naming_convention"] = self.naming_convention
        if self.overall_width is not None:
            d["overall_width"] = self.overall_width
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DocumentLayout:
        return cls(
            container_width=data.get("container_width", 600),
            naming_convention=data.get("naming_convention"),
            overall_width=data.get("overall_width"),
        )


@dataclass(frozen=True)
class CompatibilityHint:
    """An email-client compatibility warning."""

    level: str
    css_property: str
    message: str
    affected_clients: list[str] = field(default_factory=list[str])

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "level": self.level,
            "css_property": self.css_property,
            "message": self.message,
        }
        if self.affected_clients:
            d["affected_clients"] = list(self.affected_clients)
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> CompatibilityHint:
        return cls(
            level=data["level"],
            css_property=data["css_property"],
            message=data["message"],
            affected_clients=data.get("affected_clients", []),
        )


@dataclass(frozen=True)
class TokenWarning:
    """A token extraction warning."""

    level: str
    field: str
    message: str
    fixed_value: str | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"level": self.level, "field": self.field, "message": self.message}
        if self.fixed_value is not None:
            d["fixed_value"] = self.fixed_value
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TokenWarning:
        return cls(
            level=data["level"],
            field=data["field"],
            message=data["message"],
            fixed_value=data.get("fixed_value"),
        )


# ── Top-level document ──────────────────────────────────────────────


@dataclass(frozen=True)
class EmailDesignDocument:
    """The canonical intermediate representation for email design conversion.

    Bridges all input sources (Figma, Penpot, MJML, HTML) to the converter
    via a single, schema-validated JSON contract.
    """

    version: str
    tokens: DocumentTokens
    sections: list[DocumentSection]
    layout: DocumentLayout
    source: DocumentSource | None = None
    compatibility_hints: list[CompatibilityHint] = field(default_factory=list[CompatibilityHint])
    token_warnings: list[TokenWarning] = field(default_factory=list[TokenWarning])

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "version": self.version,
            "tokens": self.tokens.to_json(),
            "sections": [s.to_json() for s in self.sections],
            "layout": self.layout.to_json(),
        }
        if self.source is not None:
            d["source"] = self.source.to_json()
        if self.compatibility_hints:
            d["compatibility_hints"] = [h.to_json() for h in self.compatibility_hints]
        if self.token_warnings:
            d["token_warnings"] = [w.to_json() for w in self.token_warnings]
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> EmailDesignDocument:
        """Deserialize from a JSON-compatible dict.

        Raises ``ValueError`` if the data is malformed (missing keys, wrong types).
        """
        try:
            source_data = data.get("source")
            return cls(
                version=data["version"],
                tokens=DocumentTokens.from_json(data["tokens"]),
                sections=[DocumentSection.from_json(s) for s in data["sections"]],
                layout=DocumentLayout.from_json(data["layout"]),
                source=DocumentSource.from_json(source_data) if source_data is not None else None,
                compatibility_hints=[
                    CompatibilityHint.from_json(h) for h in data.get("compatibility_hints", [])
                ],
                token_warnings=[TokenWarning.from_json(w) for w in data.get("token_warnings", [])],
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Malformed EmailDesignDocument: {exc}") from exc

    @staticmethod
    def validate(data: dict[str, Any]) -> list[str]:
        """Validate a dict against the JSON Schema.  Returns error messages (empty = valid)."""
        validator = _get_validator()
        errors: list[str] = []
        for error in validator.iter_errors(data):  # pyright: ignore[reportUnknownMemberType]
            path = (
                ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
            )
            errors.append(f"{path}: {error.message}")
        return errors

    @staticmethod
    def schema() -> dict[str, Any]:
        """Return the raw JSON Schema dict (cached)."""
        return _load_schema()

    # ── Bridge methods ──────────────────────────────────────────────

    def to_extracted_tokens(self) -> ExtractedTokens:
        """Convert tokens to the existing ``ExtractedTokens`` dataclass."""
        return self.tokens.to_extracted_tokens()

    def to_email_sections(self) -> list[EmailSection]:
        """Convert sections to the existing ``EmailSection`` dataclass list."""
        return [s.to_email_section() for s in self.sections]

    def to_layout_description(self, file_name: str = "") -> DesignLayoutDescription:
        """Convert to the existing ``DesignLayoutDescription`` dataclass."""
        sections = self.to_email_sections()
        resolved_name = file_name or (self.source.file_ref if self.source else "") or ""
        return DesignLayoutDescription(
            file_name=resolved_name,
            overall_width=self.layout.overall_width,
            sections=sections,
            total_text_blocks=sum(len(s.texts) for s in sections),
            total_images=sum(len(s.images) for s in sections),
            spacing_map={},
        )

    @classmethod
    def from_legacy(
        cls,
        structure: DesignFileStructure,
        tokens: ExtractedTokens,
        *,
        raw_file_data: dict[str, Any] | None = None,
        selected_nodes: list[str] | None = None,
        connection_config: dict[str, Any] | None = None,
        source_provider: str = "figma",
        _pre_normalized: bool = False,
        vlm_classifications: dict[str, VLMSectionClassification] | None = None,
    ) -> EmailDesignDocument:
        """Build an EmailDesignDocument from legacy converter inputs.

        Runs the full pre-processing pipeline (tree normalization, frame
        collection, layout analysis, width derivation) so the resulting
        document is ready for ``convert_document()``.
        """
        from app.design_sync.figma.layout_analyzer import analyze_layout
        from app.design_sync.figma.tree_normalizer import normalize_tree
        from app.design_sync.protocol import DesignNodeType

        # 1. Normalize tree (skip if caller already normalized)
        if not _pre_normalized:
            structure, _stats = normalize_tree(structure, raw_file_data=raw_file_data)

        # 2. Check for any top-level frame-type candidates.
        # Note: we do NOT filter by _has_visible_content here — that check
        # belongs in the recursive converter path (_collect_frames).  The
        # document path delegates to analyze_layout(), which correctly
        # creates sections from all frame-type candidates regardless of
        # whether they contain text/image children.
        frame_types = {DesignNodeType.FRAME, DesignNodeType.COMPONENT, DesignNodeType.INSTANCE}
        frames_found = any(
            child.type in frame_types and (selected_nodes is None or child.id in selected_nodes)
            for page in structure.pages
            for child in page.children
        )

        if not frames_found:
            return cls(
                version="1.0",
                tokens=DocumentTokens.from_extracted_tokens(tokens),
                sections=[],
                layout=DocumentLayout(),
                source=DocumentSource(provider=source_provider, file_ref=structure.file_name),
            )

        # 2b. Filter structure to selected nodes before layout analysis
        if selected_nodes is not None:
            from dataclasses import replace as dc_replace

            selected_set = set(selected_nodes)
            filtered_pages: list[DesignNode] = []
            for page in structure.pages:
                filtered_children = [
                    c for c in page.children if c.id in selected_set or c.type not in frame_types
                ]
                filtered_pages.append(dc_replace(page, children=filtered_children))
            structure = dc_replace(structure, pages=filtered_pages)

        # 3. Layout analysis with config hints
        layout_kwargs: dict[str, Any] = {}
        if connection_config:
            if nc := connection_config.get("naming_convention"):
                layout_kwargs["naming_convention"] = nc
            if snm := connection_config.get("section_name_map"):
                layout_kwargs["section_name_map"] = snm
            if bnh := connection_config.get("button_name_hints"):
                layout_kwargs["button_name_hints"] = bnh
        if vlm_classifications:
            layout_kwargs["vlm_classifications"] = vlm_classifications
        layout = analyze_layout(structure, **layout_kwargs)

        # 4. Derive container width (clamped 400-800, config override priority)
        container_width = 600
        config_cw = connection_config.get("container_width") if connection_config else None
        if isinstance(config_cw, int) and 320 <= config_cw <= 1200:
            container_width = config_cw
        elif layout.overall_width is not None:
            container_width = max(400, min(800, int(layout.overall_width)))

        # 5. Build document
        naming_convention = (
            connection_config.get("naming_convention") if connection_config else None
        )
        return cls(
            version="1.0",
            tokens=DocumentTokens.from_extracted_tokens(tokens),
            sections=[DocumentSection.from_email_section(s) for s in layout.sections],
            layout=DocumentLayout(
                container_width=container_width,
                overall_width=layout.overall_width,
                naming_convention=naming_convention,
            ),
            source=DocumentSource(provider=source_provider, file_ref=structure.file_name),
        )
