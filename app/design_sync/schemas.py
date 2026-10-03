"""Pydantic schemas for design sync."""

import datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

# ── Requests ──


class ConnectionConfigRequest(BaseModel):
    """Per-connection converter configuration hints."""

    naming_convention: str = Field(
        default="auto",
        pattern=r"^(auto|mjml|descriptive|generic|custom)$",
        description="Naming convention: auto-detect or specify",
    )
    section_name_map: dict[str, str] | None = Field(
        default=None,
        description="Custom section name → type mapping (e.g. {'my-hero': 'hero'})",
    )
    button_name_hints: list[str] | None = Field(
        default=None,
        description="Extra button name prefixes (e.g. ['btn-', 'cta-'])",
    )
    container_width: int | None = Field(
        default=None,
        ge=320,
        le=1200,
        description="Override auto-detected container width",
    )


class ConnectionCreateRequest(BaseModel):
    """Request to create a design tool connection."""

    name: str = Field(..., min_length=1, max_length=200, description="Display name")
    provider: str = Field(default="figma", max_length=50, description="Design tool provider")
    file_url: str = Field(..., min_length=1, max_length=500, description="Design file URL")
    access_token: str = Field(..., min_length=1, description="Provider access token / PAT")
    project_id: int | None = Field(default=None, description="Link to a project")
    config: ConnectionConfigRequest | None = Field(
        default=None,
        description="Optional converter configuration hints",
    )


class BrowseFilesRequest(BaseModel):
    """Request to browse design files from a provider."""

    provider: str = Field(..., max_length=50, description="Design tool provider")
    access_token: str = Field(..., min_length=1, description="Provider access token / PAT")


class DesignFileResponse(BaseModel):
    """A single browsable design file."""

    file_id: str
    name: str
    url: str
    thumbnail_url: str | None = None
    last_modified: datetime.datetime | None = None
    folder: str | None = None


class BrowseFilesResponse(BaseModel):
    """Result of browsing design files."""

    provider: str
    files: list[DesignFileResponse]
    total: int


class ConnectionDeleteRequest(BaseModel):
    """Request to delete a connection."""

    id: int = Field(..., description="Connection ID to delete")


class ConnectionSyncRequest(BaseModel):
    """Request to sync tokens from a connection."""

    id: int = Field(..., description="Connection ID to sync")


class ConnectionUpdateTokenRequest(BaseModel):
    """Request to update the access token on an existing connection."""

    access_token: str = Field(..., min_length=1, description="New provider access token / PAT")


class ConnectionLinkProjectRequest(BaseModel):
    """Request to link/unlink a connection to a project."""

    project_id: int | None = Field(None, description="Project ID to link (null to unlink)")


# ── Responses ──


class ConnectionResponse(BaseModel):
    """Design connection response (maps DB fields for frontend compat)."""

    id: int
    name: str
    provider: str
    file_key: str = Field(description="Provider file reference")
    file_url: str
    access_token_last4: str = Field(description="Last 4 chars of token for display")
    status: str
    error_message: str | None = None
    last_synced_at: datetime.datetime | None = None
    project_id: int | None = None
    project_name: str | None = None
    config: ConnectionConfigRequest | None = None
    webhook_id: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(
        cls,
        conn: "object",
        project_name: str | None = None,
    ) -> "ConnectionResponse":
        """Build response from a DesignConnection model, mapping field names."""
        from app.design_sync.models import DesignConnection

        if not isinstance(conn, DesignConnection):
            msg = "Expected DesignConnection instance"
            raise TypeError(msg)
        config = None
        if conn.config_json:
            import contextlib

            with contextlib.suppress(Exception):
                config = ConnectionConfigRequest.model_validate(conn.config_json)
        return cls(
            id=conn.id,
            name=conn.name,
            provider=conn.provider,
            file_key=conn.file_ref,
            file_url=conn.file_url,
            access_token_last4=conn.token_last4,
            status=conn.status,
            error_message=conn.error_message,
            last_synced_at=conn.last_synced_at,
            project_id=conn.project_id,
            project_name=project_name,
            config=config,
            webhook_id=conn.webhook_id if type(conn.webhook_id) is str else None,
            created_at=cast(datetime.datetime, conn.created_at),
            updated_at=cast(datetime.datetime, conn.updated_at),
        )


class DesignColorResponse(BaseModel):
    """Single design colour."""

    name: str
    hex: str
    opacity: float


class DesignTypographyResponse(BaseModel):
    """Single typography style."""

    name: str
    family: str
    weight: str
    size: float
    lineHeight: float
    letterSpacing: float | None = None
    textTransform: str | None = None
    textDecoration: str | None = None


class DesignSpacingResponse(BaseModel):
    """Single spacing value."""

    name: str
    value: float


class CompatibilityHintResponse(BaseModel):
    """A client compatibility observation surfaced during conversion."""

    level: str  # "info" | "warning"
    css_property: str
    message: str
    affected_clients: list[str]


class DesignGradientStopResponse(BaseModel):
    """A single gradient stop."""

    hex: str
    position: float


class DesignGradientResponse(BaseModel):
    """A gradient extracted from a design file."""

    name: str
    type: str
    angle: float
    stops: list[DesignGradientStopResponse]
    fallback_hex: str


class DesignTokensResponse(BaseModel):
    """Design tokens extracted from a connection."""

    connection_id: int
    colors: list[DesignColorResponse]
    dark_colors: list[DesignColorResponse] = Field(default_factory=list[DesignColorResponse])
    typography: list[DesignTypographyResponse]
    spacing: list[DesignSpacingResponse]
    gradients: list[DesignGradientResponse] = Field(default_factory=list[DesignGradientResponse])
    extracted_at: datetime.datetime
    warnings: list[str] | None = None
    compatibility_hints: list[CompatibilityHintResponse] | None = None


class TokenDiffEntry(BaseModel):
    """A single token change between snapshots."""

    category: str
    name: str
    change: Literal["added", "removed", "changed"]
    old_value: str | None = None
    new_value: str | None = None


class TokenDiffResponse(BaseModel):
    """Token diff between current and previous sync."""

    connection_id: int
    current_extracted_at: datetime.datetime
    previous_extracted_at: datetime.datetime | None = None
    entries: list[TokenDiffEntry]
    has_previous: bool = False


# ── W3C Design Tokens ──


class ImportW3cTokensRequest(BaseModel):
    """Request to import W3C Design Tokens v1.0 JSON."""

    tokens_json: dict[str, object] = Field(
        ...,
        description="W3C Design Tokens v1.0 JSON",
        max_length=10_000,
    )
    connection_id: int | None = Field(
        None, description="Optional connection to store snapshot against"
    )
    target_clients: list[str] | None = Field(
        None,
        description="Target clients for compatibility checks",
        max_length=50,
    )


class W3cImportResponse(BaseModel):
    """Response from W3C token import."""

    colors: list[DesignColorResponse]
    dark_colors: list[DesignColorResponse] = []  # pyright: ignore[reportUnknownVariableType]
    typography: list[DesignTypographyResponse]
    spacing: list[DesignSpacingResponse]
    gradients: list[DesignGradientResponse] = []  # pyright: ignore[reportUnknownVariableType]
    warnings: list[str]
    compatibility_hints: list[CompatibilityHintResponse] = []  # pyright: ignore[reportUnknownVariableType]


# ── File Structure Responses ──


class DesignNodeResponse(BaseModel):
    """A node in the design file tree."""

    id: str
    name: str
    type: str
    children: list["DesignNodeResponse"] = Field(default_factory=list["DesignNodeResponse"])
    width: float | None = None
    height: float | None = None
    x: float | None = None
    y: float | None = None
    text_content: str | None = None

    model_config = ConfigDict(from_attributes=True)


DesignNodeResponse.model_rebuild()


class FileStructureResponse(BaseModel):
    """Design file structure response."""

    connection_id: int
    file_name: str
    pages: list[DesignNodeResponse]
    thumbnails: dict[str, str] = Field(default_factory=dict, description="node_id → image URL")


# ── Component Responses ──


class DesignComponentResponse(BaseModel):
    """A reusable design component."""

    component_id: str
    name: str
    description: str = ""
    thumbnail_url: str | None = None
    containing_page: str | None = None


class ComponentListResponse(BaseModel):
    """List of design components."""

    connection_id: int
    components: list[DesignComponentResponse]
    total: int


# ── Image Export ──


class ExportImageRequest(BaseModel):
    """Request to export design nodes as images."""

    connection_id: int
    node_ids: list[str] = Field(..., min_length=1, max_length=500, description="Node IDs to export")
    format: str = Field(default="png", pattern=r"^(png|jpg|svg|pdf)$")
    scale: float = Field(default=2.0, ge=0.01, le=4.0)


class ExportedImageResponse(BaseModel):
    """An exported image."""

    node_id: str
    url: str
    format: str
    expires_at: datetime.datetime | None = None


class ImageExportResponse(BaseModel):
    """Image export result."""

    connection_id: int
    images: list[ExportedImageResponse]
    total: int


# ── Asset Storage ──


class DownloadAssetsRequest(BaseModel):
    """Request to download and store exported images locally."""

    connection_id: int
    node_ids: list[str] = Field(
        ..., min_length=1, max_length=500, description="Node IDs to download"
    )
    format: str = Field(default="png", pattern=r"^(png|jpg|svg|pdf)$")
    scale: float = Field(default=2.0, ge=0.01, le=4.0)


class StoredAssetResponse(BaseModel):
    """A locally stored asset."""

    node_id: str
    filename: str


class DownloadAssetsResponse(BaseModel):
    """Result of downloading and storing assets."""

    connection_id: int
    assets: list[StoredAssetResponse]
    total: int
    skipped: int = Field(description="Count of failed downloads")


class ImportedImageResponse(BaseModel):
    """Image asset imported from a design file and stored locally."""

    node_id: str
    filename: str
    hub_url: str


# ── Design Imports ──

IMPORT_STATUSES = {"pending", "extracting", "converting", "completed", "failed", "cancelled"}
ASSET_USAGES = {"hero", "logo", "icon", "background", "content"}


class CreateImportRequest(BaseModel):
    """Request to create a design import job."""

    connection_id: int
    project_id: int
    selected_node_ids: list[str] = Field(
        ..., min_length=1, max_length=500, description="Figma node IDs to import"
    )


class UpdateImportBriefRequest(BaseModel):
    """Request to update the generated brief before conversion."""

    generated_brief: str = Field(..., min_length=1, max_length=50000)


class ImportAssetResponse(BaseModel):
    """A single import asset."""

    id: int
    node_id: str
    node_name: str
    file_path: str
    width: int | None = None
    height: int | None = None
    format: str
    usage: str | None = None
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ImportResponse(BaseModel):
    """Design import job response."""

    id: int
    connection_id: int
    project_id: int
    status: str
    selected_node_ids: list[str]
    structure_json: dict[str, object] | None = None
    generated_brief: str | None = None
    result_template_id: int | None = None
    error_message: str | None = None
    created_by_id: int
    assets: list[ImportAssetResponse] = Field(default_factory=list[ImportAssetResponse])
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class ImportListResponse(BaseModel):
    """List of design imports."""

    imports: list[ImportResponse]
    total: int


# ── Layout Analysis (12.4) ──


class TextBlockResponse(BaseModel):
    """A text element from the design."""

    node_id: str
    content: str
    font_size: float | None = None
    is_heading: bool = False
    font_family: str | None = None
    font_weight: int | None = None
    line_height: float | None = None
    letter_spacing: float | None = None


class ImagePlaceholderResponse(BaseModel):
    """An image placeholder from the design."""

    node_id: str
    node_name: str
    width: float | None = None
    height: float | None = None
    export_node_id: str | None = None


class ButtonElementResponse(BaseModel):
    """A CTA button from the design."""

    node_id: str
    text: str
    width: float | None = None
    height: float | None = None
    icon_node_id: str | None = None


class AnalyzedSectionResponse(BaseModel):
    """A detected email section."""

    section_type: str
    node_id: str
    node_name: str
    y_position: float | None = None
    width: float | None = None
    height: float | None = None
    column_layout: str = "single"
    column_count: int = 1
    texts: list[TextBlockResponse] = Field(default_factory=list[TextBlockResponse])
    images: list[ImagePlaceholderResponse] = Field(default_factory=list[ImagePlaceholderResponse])
    buttons: list[ButtonElementResponse] = Field(default_factory=list[ButtonElementResponse])
    spacing_after: float | None = None
    bg_color: str | None = None
    classification_confidence: float | None = None
    content_roles: list[str] = Field(default_factory=list)


class LayoutAnalysisResponse(BaseModel):
    """Layout analysis result for preview."""

    connection_id: int
    file_name: str
    overall_width: float | None = None
    sections: list[AnalyzedSectionResponse]
    total_text_blocks: int
    total_images: int


class AnalyzeLayoutRequest(BaseModel):
    """Request to analyze layout of selected nodes."""

    connection_id: int
    selected_node_ids: list[str] = Field(
        default_factory=list,
        max_length=500,
        description="Node IDs to analyze (empty = all top-level frames)",
    )


class GenerateBriefRequest(BaseModel):
    """Request to generate a campaign brief from design analysis."""

    connection_id: int
    selected_node_ids: list[str] = Field(
        default_factory=list,
        max_length=500,
        description="Node IDs to include (empty = all top-level frames)",
    )
    include_tokens: bool = Field(default=True, description="Include design token summary")


class GenerateBriefResponse(BaseModel):
    """Generated campaign brief."""

    connection_id: int
    brief: str = Field(description="Structured markdown brief for the Scaffolder")
    sections_detected: int
    layout_summary: str


# ── Component Extraction (12.6) ──


class ExtractComponentsRequest(BaseModel):
    """Request to extract components from a design connection."""

    component_ids: list[str] | None = None  # None = extract all
    generate_html: bool = True  # False = preview-only, skip Scaffolder


class ExtractComponentsResponse(BaseModel):
    """Response for component extraction kickoff."""

    import_id: int
    status: str  # "extracting"
    total_components: int
    message: str


# ── Phase 12.5: AI-Assisted Conversion Pipeline ──


class DesignContextSchema(BaseModel):
    """Figma-specific context passed to the Scaffolder alongside the brief."""

    image_urls: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of node_id → locally stored asset URL",
    )
    layout_summary: str | None = Field(
        default=None,
        description="Detected layout summary (e.g. 'header, hero, 2-col content, cta, footer')",
    )
    sections: list[AnalyzedSectionResponse] = Field(
        default_factory=list[AnalyzedSectionResponse],
        description="Analyzed sections from layout analysis",
    )
    design_tokens: dict[str, object] | None = Field(
        default=None,
        description="Extracted design tokens (colors, typography, spacing)",
    )
    source_file: str | None = Field(
        default=None,
        description="Source Figma file name for provenance",
    )


class StartImportRequest(BaseModel):
    """Request to create a design import with a brief for conversion."""

    connection_id: int
    brief: str = Field(
        ..., min_length=10, max_length=50000, description="Campaign brief from ESP/CMS"
    )
    selected_node_ids: list[str] = Field(
        default_factory=list,
        max_length=500,
        description="Figma node IDs to import (empty = all top-level frames)",
    )
    template_name: str | None = Field(
        default=None,
        max_length=200,
        description="Override template name (auto-derived from brief if omitted)",
    )


class ConvertImportRequest(BaseModel):
    """Request to trigger Scaffolder conversion on an existing import."""

    run_qa: bool = Field(default=True, description="Run QA gate on generated HTML")
    output_mode: Literal["html", "structured"] = Field(default="structured")
    output_format: Literal["html", "mjml"] = Field(
        default="html",
        description="Conversion backend: 'html' (recursive) or 'mjml' (MJML generation + compilation)",
    )
    score_fidelity: bool = Field(
        default=False,
        description="Run visual fidelity scoring after conversion (requires FIDELITY_ENABLED)",
    )


# ── Phase 35.6: Visual Fidelity Scoring ──


class SectionFidelityScore(BaseModel):
    """Per-section SSIM fidelity score."""

    section_id: str
    section_name: str
    section_type: str
    ssim: float = Field(ge=0.0, le=1.0, description="Structural Similarity Index (0-1)")
    severity: Literal["ok", "warning", "critical"]


class FidelityResult(BaseModel):
    """Aggregate fidelity scoring result for a design import."""

    overall_ssim: float = Field(ge=0.0, le=1.0)
    sections: list[SectionFidelityScore]
    diff_image_available: bool = False
    scored_at: datetime.datetime


class FidelityResponse(BaseModel):
    """API response wrapping fidelity scores for a design import."""

    import_id: int
    fidelity: FidelityResult | None = None


# ── Webhook Schemas ──


class FigmaWebhookPayload(BaseModel):
    """Figma FILE_UPDATE webhook event payload."""

    event_type: str
    file_key: str
    file_name: str
    timestamp: str
    team_id: str | None = None


class DesignSyncUpdateMessage(BaseModel):
    """WebSocket message for live design sync updates."""

    type: Literal["design_sync_update"] = "design_sync_update"
    connection_id: int
    diff_summary: str
    total_changes: int
    preview_url: str | None = None
    timestamp: datetime.datetime


class CacheClearResponse(BaseModel):
    """Response for section cache clear endpoint."""

    cleared_entries: int


class DocumentValidationResponse(BaseModel):
    """Response for the EmailDesignDocument validation endpoint."""

    valid: bool
    errors: list[str]


# ── HTML Import (36.5) ──


class HtmlImportRequest(BaseModel):
    """Request to reverse-engineer email HTML into an EmailDesignDocument."""

    model_config = ConfigDict(strict=True)

    html: str = Field(..., max_length=2_097_152, description="Raw email HTML (max 2 MB)")
    use_ai: bool | None = Field(None, description="Override AI fallback (None = use config)")
    source_name: str | None = Field(None, max_length=255, description="Source identifier")


class HtmlImportResponse(BaseModel):
    """Response from HTML reverse-engineering import."""

    document: dict[str, object] = Field(..., description="EmailDesignDocument JSON")
    section_count: int
    ai_sections_classified: int
    warnings: list[str] = Field(default_factory=list)


# ── MJML Import (36.4) ──


class ImportMjmlRequest(BaseModel):
    """Request to import MJML markup into an EmailDesignDocument."""

    model_config = ConfigDict(strict=True)

    mjml_source: str = Field(..., max_length=2_100_000, description="Raw MJML markup (max ~2 MB)")


class ImportMjmlResponse(BaseModel):
    """Response from MJML import."""

    document: dict[str, object] = Field(..., description="EmailDesignDocument JSON")
    sections_count: int
    warnings: list[str] = Field(default_factory=list)
