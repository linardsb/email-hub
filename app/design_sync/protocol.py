"""Protocol interface for design tool sync implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ExtractedColor:
    """A colour extracted from a design file."""

    name: str
    hex: str
    opacity: float = 1.0


@dataclass(frozen=True)
class ExtractedTypography:
    """A typography style extracted from a design file."""

    name: str
    family: str
    weight: str
    size: float
    line_height: float
    letter_spacing: float | None = None
    text_transform: str | None = None  # uppercase|lowercase|capitalize|None
    text_decoration: str | None = None  # underline|line-through|None


@dataclass(frozen=True)
class ExtractedSpacing:
    """A spacing value extracted from a design file."""

    name: str
    value: float


@dataclass(frozen=True)
class ExtractedVariable:
    """A design variable from the Figma Variables API."""

    name: str
    collection: str
    type: str  # "COLOR", "FLOAT", "STRING", "BOOLEAN"
    values_by_mode: dict[str, Any]
    is_alias: bool = False
    alias_path: str | None = None


@dataclass(frozen=True)
class ExtractedGradient:
    """A gradient extracted from a design file."""

    name: str
    type: str  # "linear" | "radial"
    angle: float  # degrees, 0-360 (linear only)
    stops: tuple[tuple[str, float], ...]  # (hex_color, position 0.0-1.0)
    fallback_hex: str  # midpoint solid for Outlook


@dataclass(frozen=True)
class ExtractedTokens:
    """All design tokens extracted from a design file."""

    colors: list[ExtractedColor] = field(default_factory=list[ExtractedColor])
    typography: list[ExtractedTypography] = field(default_factory=list[ExtractedTypography])
    spacing: list[ExtractedSpacing] = field(default_factory=list[ExtractedSpacing])
    variables_source: bool = False
    modes: dict[str, str] | None = None
    stroke_colors: list[ExtractedColor] = field(default_factory=list[ExtractedColor])
    variables: list[ExtractedVariable] = field(default_factory=list[ExtractedVariable])
    dark_colors: list[ExtractedColor] = field(default_factory=list[ExtractedColor])
    gradients: list[ExtractedGradient] = field(default_factory=list[ExtractedGradient])


@dataclass(frozen=True)
class StyleRun:
    """A styled text segment within a TEXT node (bold, italic, color, link)."""

    start: int
    end: int
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    color_hex: str | None = None
    font_size: float | None = None
    link_url: str | None = None


class DesignNodeType(StrEnum):
    """Normalised node types across design tools."""

    PAGE = "PAGE"
    FRAME = "FRAME"
    COMPONENT = "COMPONENT"
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    GROUP = "GROUP"
    INSTANCE = "INSTANCE"
    VECTOR = "VECTOR"
    OTHER = "OTHER"


@dataclass(frozen=True)
class DesignNode:
    """A node in the design file tree."""

    id: str
    name: str
    type: DesignNodeType
    children: list[DesignNode] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    width: float | None = None
    height: float | None = None
    x: float | None = None
    y: float | None = None
    text_content: str | None = None
    fill_color: str | None = None  # Background/fill hex from design tool
    text_color: str | None = None  # Text fill color hex (TEXT nodes only)
    # Auto-layout spacing (Figma/Penpot frames)
    padding_top: float | None = None
    padding_right: float | None = None
    padding_bottom: float | None = None
    padding_left: float | None = None
    item_spacing: float | None = None
    counter_axis_spacing: float | None = None
    layout_mode: str | None = None  # "HORIZONTAL", "VERTICAL", or None
    # Typography (TEXT nodes — actual values, not bounding box)
    font_family: str | None = None
    font_size: float | None = None
    font_weight: int | None = None
    line_height_px: float | None = None
    letter_spacing_px: float | None = None
    text_transform: str | None = None  # uppercase|lowercase|capitalize|None (TEXT nodes only)
    text_decoration: str | None = None  # underline|line-through|None (TEXT nodes only)
    image_ref: str | None = None  # Figma imageRef hash (IMAGE fill on FRAME nodes)
    # Hyperlink (TEXT/FRAME nodes — validated http/https/mailto only)
    hyperlink: str | None = None
    # Corner radius (FRAME/RECTANGLE nodes)
    corner_radius: float | None = None
    corner_radii: tuple[float, ...] | None = None  # [TL, TR, BR, BL] per-corner
    # Text alignment
    text_align: str | None = None  # left|center|right|justify (TEXT nodes)
    primary_axis_align: str | None = None  # start|center|end|space-between (FRAME)
    counter_axis_align: str | None = None  # start|center|end (FRAME)
    # Borders/strokes
    stroke_weight: float | None = None
    stroke_color: str | None = None  # First SOLID stroke hex
    # Rich text style runs (TEXT nodes — characterStyleOverrides)
    style_runs: tuple[StyleRun, ...] = ()
    visible: bool = True  # Figma "visible" property (default True per API spec)
    opacity: float = 1.0  # Figma node opacity 0.0-1.0 (default 1.0)


@dataclass(frozen=True)
class DesignFileStructure:
    """Top-level structure of a design file."""

    file_name: str
    pages: list[DesignNode] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    # Full-frame PNG @ scale=2.0 for global visual context (Phase 50.1, Gap 9)
    design_image: bytes | None = None


@dataclass(frozen=True)
class DesignFile:
    """A browsable file returned by design tool providers."""

    file_id: str
    name: str
    url: str
    thumbnail_url: str | None = None
    last_modified: datetime | None = None
    folder: str | None = None


@dataclass(frozen=True)
class DesignComponent:
    """A reusable component from a design file."""

    component_id: str
    name: str
    description: str = ""
    thumbnail_url: str | None = None
    containing_page: str | None = None


@dataclass(frozen=True)
class ExportedImage:
    """An exported image from a design file node."""

    node_id: str
    url: str
    format: str  # "png", "jpg", "svg", "pdf"
    expires_at: datetime | None = None


@runtime_checkable
class BrowseableProvider(Protocol):
    """Protocol for providers that support listing files before connection.

    Separate from DesignSyncProvider to avoid breaking existing contract.
    Providers that don't support browsing simply don't implement this.
    """

    async def list_files(self, access_token: str) -> list[DesignFile]: ...


@runtime_checkable
class DesignSyncProvider(Protocol):
    """Protocol that all design tool sync services must implement."""

    async def validate_connection(self, file_ref: str, access_token: str) -> bool:
        """Validate that credentials can access the design file.

        Args:
            file_ref: Provider-specific file reference (e.g. Figma file key).
            access_token: Provider-specific access token or PAT.

        Returns:
            True if the connection is valid.

        Raises:
            SyncFailedError: If validation fails.
        """
        ...

    async def sync_tokens(
        self, file_ref: str, access_token: str, *, target_node_id: str | None = None
    ) -> ExtractedTokens:
        """Extract design tokens from a design file.

        Args:
            file_ref: Provider-specific file reference.
            access_token: Provider-specific access token.
            target_node_id: Optional node ID to scope token extraction to.

        Returns:
            Extracted design tokens (colors, typography, spacing).

        Raises:
            SyncFailedError: If extraction fails.
        """
        ...

    async def sync_tokens_and_structure(
        self, file_ref: str, access_token: str, *, target_node_id: str | None = None
    ) -> tuple[ExtractedTokens, DesignFileStructure]:
        """Extract tokens and file structure from a single API call.

        Providers should override for efficiency. Default falls back to two calls.
        """
        ...

    async def get_file_structure(
        self, file_ref: str, access_token: str, *, depth: int | None = 2
    ) -> DesignFileStructure:
        """Get the hierarchical structure of a design file.

        Args:
            file_ref: Provider-specific file reference.
            access_token: Provider-specific access token.
            depth: Max tree depth (None = unlimited, default 2 = pages + top-level frames).

        Returns:
            File structure with pages and nested nodes.

        Raises:
            SyncFailedError: If retrieval fails.
        """
        ...

    async def list_components(self, file_ref: str, access_token: str) -> list[DesignComponent]:
        """List reusable components defined in a design file.

        Args:
            file_ref: Provider-specific file reference.
            access_token: Provider-specific access token.

        Returns:
            List of components with metadata.

        Raises:
            SyncFailedError: If retrieval fails.
        """
        ...

    async def export_images(
        self,
        file_ref: str,
        access_token: str,
        node_ids: list[str],
        *,
        format: str = "png",
        scale: float = 2.0,
    ) -> list[ExportedImage]:
        """Export design nodes as images.

        Args:
            file_ref: Provider-specific file reference.
            access_token: Provider-specific access token.
            node_ids: IDs of nodes to export.
            format: Image format (png, jpg, svg, pdf).
            scale: Export scale factor (1.0-4.0).

        Returns:
            List of exported images with temporary download URLs.

        Raises:
            SyncFailedError: If export fails.
        """
        ...


@dataclass(frozen=True)
class _NodeProps:
    """Supplementary visual properties not carried by DesignNode."""

    bg_color: str | None = None
    font_family: str | None = None
    font_size: float | None = None
    font_weight: str | None = None
    padding_top: float = 0
    padding_right: float = 0
    padding_bottom: float = 0
    padding_left: float = 0
    border_color: str | None = None
    border_width: float = 0
    layout_direction: str | None = None  # "row" | "column" | None
    item_spacing: float = 0
    counter_axis_spacing: float = 0
    line_height_px: float | None = None
    letter_spacing_px: float | None = None
    text_transform: str | None = None
    text_decoration: str | None = None
