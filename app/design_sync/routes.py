# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false
"""REST API routes for design sync."""

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.requests import Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.auth.models import User
from app.core.rate_limit import limiter
from app.core.scoped_db import get_scoped_db
from app.design_sync.diagnose.schemas import DiagnosticReportResponse
from app.design_sync.repository import DesignSyncRepository
from app.design_sync.schemas import (
    AnalyzeLayoutRequest,
    BrowseFilesRequest,
    BrowseFilesResponse,
    CacheClearResponse,
    ComponentListResponse,
    ConnectionCreateRequest,
    ConnectionDeleteRequest,
    ConnectionLinkProjectRequest,
    ConnectionResponse,
    ConnectionSyncRequest,
    ConnectionUpdateTokenRequest,
    ConvertImportRequest,
    DesignTokensResponse,
    DocumentValidationResponse,
    DownloadAssetsRequest,
    DownloadAssetsResponse,
    ExportImageRequest,
    ExtractComponentsRequest,
    ExtractComponentsResponse,
    FidelityResponse,
    FidelityResult,
    FileStructureResponse,
    GenerateBriefRequest,
    GenerateBriefResponse,
    HtmlImportRequest,
    HtmlImportResponse,
    ImageExportResponse,
    ImportMjmlRequest,
    ImportMjmlResponse,
    ImportResponse,
    ImportW3cTokensRequest,
    LayoutAnalysisResponse,
    StartImportRequest,
    TokenDiffResponse,
    UpdateImportBriefRequest,
    W3cImportResponse,
)
from app.design_sync.services import (
    AccessService,
    AssetsService,
    ConnectionService,
    DesignSyncContext,
    ImportRequestService,
    TokenConversionService,
    WebhookService,
)

router = APIRouter(prefix="/api/v1/design-sync", tags=["design-sync"])


def _ctx(db: AsyncSession = Depends(get_scoped_db)) -> DesignSyncContext:
    return DesignSyncContext(db)


def get_connection_service(ctx: DesignSyncContext = Depends(_ctx)) -> ConnectionService:
    return ConnectionService(ctx)


def get_assets_service(ctx: DesignSyncContext = Depends(_ctx)) -> AssetsService:
    return AssetsService(ctx)


def get_token_service(ctx: DesignSyncContext = Depends(_ctx)) -> TokenConversionService:
    return TokenConversionService(ctx)


def get_import_service(ctx: DesignSyncContext = Depends(_ctx)) -> ImportRequestService:
    return ImportRequestService(ctx)


def get_webhook_service(ctx: DesignSyncContext = Depends(_ctx)) -> WebhookService:
    return WebhookService(ctx)


def get_access_service(ctx: DesignSyncContext = Depends(_ctx)) -> AccessService:
    return AccessService(ctx)


@router.post("/browse-files", response_model=BrowseFilesResponse)
@limiter.limit("30/minute")
async def browse_files(
    request: Request,
    data: BrowseFilesRequest,
    service: ConnectionService = Depends(get_connection_service),
    current_user: User = Depends(require_role("developer")),
) -> BrowseFilesResponse:
    """Browse design files from a provider before creating a connection.

    Token is passed in the request body, NOT logged or persisted.
    """
    _ = request
    _ = current_user  # auth required but no BOLA check (pre-connection)
    return await service.browse_files(data.provider, data.access_token)


@router.get("/connections", response_model=list[ConnectionResponse])
@limiter.limit("30/minute")
async def list_connections(
    request: Request,
    service: ConnectionService = Depends(get_connection_service),
    current_user: User = Depends(require_role("viewer")),
) -> list[ConnectionResponse]:
    """List all design tool connections."""
    _ = request
    return await service.list_connections(current_user)


@router.get("/connections/{connection_id}", response_model=ConnectionResponse)
@limiter.limit("30/minute")
async def get_connection(
    connection_id: int,
    request: Request,
    service: ConnectionService = Depends(get_connection_service),
    current_user: User = Depends(require_role("viewer")),
) -> ConnectionResponse:
    """Get a single design connection."""
    _ = request
    return await service.get_connection(connection_id, current_user)


@router.get("/connections/{connection_id}/tokens", response_model=DesignTokensResponse)
@limiter.limit("30/minute")
async def get_tokens(
    connection_id: int,
    request: Request,
    service: TokenConversionService = Depends(get_token_service),
    current_user: User = Depends(require_role("viewer")),
) -> DesignTokensResponse:
    """Get design tokens for a connection."""
    _ = request
    return await service.get_tokens(connection_id, current_user)


@router.get("/connections/{connection_id}/tokens/diff", response_model=TokenDiffResponse)
@limiter.limit("30/minute")
async def get_token_diff(
    connection_id: int,
    request: Request,
    service: TokenConversionService = Depends(get_token_service),
    current_user: User = Depends(require_role("viewer")),
) -> TokenDiffResponse:
    """Compare current token snapshot with previous sync."""
    _ = request
    return await service.get_token_diff(connection_id, current_user)


# ── Phase 35.8: W3C Design Tokens ──


@router.post("/tokens/import-w3c", response_model=W3cImportResponse)
@limiter.limit("10/minute")
async def import_w3c_tokens(
    request: Request,
    body: ImportW3cTokensRequest,
    service: TokenConversionService = Depends(get_token_service),
    current_user: User = Depends(require_role("developer")),
) -> W3cImportResponse:
    """Import tokens from W3C Design Tokens v1.0 JSON format."""
    _ = request
    return await service.import_w3c_tokens(body, current_user)


@router.get("/connections/{connection_id}/tokens/export-w3c", response_model=dict[str, object])
@limiter.limit("30/minute")
async def export_w3c_tokens_endpoint(
    connection_id: int,
    request: Request,
    service: TokenConversionService = Depends(get_token_service),
    current_user: User = Depends(require_role("viewer")),
) -> dict[str, object]:
    """Export tokens in W3C Design Tokens v1.0 JSON format."""
    _ = request
    return await service.export_w3c_tokens(connection_id, current_user)


@router.post("/connections", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_connection(
    request: Request,
    data: ConnectionCreateRequest,
    service: ConnectionService = Depends(get_connection_service),
    current_user: User = Depends(require_role("developer")),
) -> ConnectionResponse:
    """Create a new design tool connection."""
    _ = request
    return await service.create_connection(data, current_user)


@router.post("/connections/delete")
@limiter.limit("10/minute")
async def delete_connection(
    request: Request,
    data: ConnectionDeleteRequest,
    service: ConnectionService = Depends(get_connection_service),
    current_user: User = Depends(require_role("developer")),
) -> dict[str, bool]:
    """Delete a design connection."""
    _ = request
    result = await service.delete_connection(data.id, current_user)
    return {"success": result}


@router.post("/connections/sync", response_model=ConnectionResponse)
@limiter.limit("5/minute")
async def sync_connection(
    request: Request,
    data: ConnectionSyncRequest,
    service: ConnectionService = Depends(get_connection_service),
    current_user: User = Depends(require_role("developer")),
) -> ConnectionResponse:
    """Trigger a design token sync."""
    _ = request
    return await service.sync_connection(data.id, current_user)


@router.patch(
    "/connections/{connection_id}/token",
    response_model=ConnectionResponse,
)
@limiter.limit("10/minute")
async def refresh_connection_token(
    connection_id: int,
    request: Request,
    data: ConnectionUpdateTokenRequest,
    service: ConnectionService = Depends(get_connection_service),
    current_user: User = Depends(require_role("developer")),
) -> ConnectionResponse:
    """Refresh the access token for a design connection."""
    _ = request
    return await service.refresh_token(connection_id, data.access_token, current_user)


@router.patch(
    "/connections/{connection_id}/project",
    response_model=ConnectionResponse,
)
@limiter.limit("10/minute")
async def link_connection_to_project(
    connection_id: int,
    request: Request,
    data: ConnectionLinkProjectRequest,
    service: ConnectionService = Depends(get_connection_service),
    current_user: User = Depends(require_role("developer")),
) -> ConnectionResponse:
    """Link or unlink a design connection to a project."""
    _ = request
    return await service.link_connection_to_project(connection_id, data.project_id, current_user)


# ── Phase 12.1: File Structure, Components, Image Export ──


@router.get(
    "/connections/{connection_id}/file-structure",
    response_model=FileStructureResponse,
)
@limiter.limit("15/minute")
async def get_file_structure(
    connection_id: int,
    request: Request,
    depth: int | None = Query(default=2, ge=1, description="Max tree depth (None = unlimited)"),
    service: AssetsService = Depends(get_assets_service),
    current_user: User = Depends(require_role("viewer")),
) -> FileStructureResponse:
    """Get the hierarchical file structure of a design file."""
    _ = request
    return await service.get_file_structure(connection_id, current_user, depth=depth)


@router.get(
    "/connections/{connection_id}/components",
    response_model=ComponentListResponse,
)
@limiter.limit("20/minute")
async def list_components(
    connection_id: int,
    request: Request,
    service: AssetsService = Depends(get_assets_service),
    current_user: User = Depends(require_role("viewer")),
) -> ComponentListResponse:
    """List reusable components defined in the design file."""
    _ = request
    return await service.list_components(connection_id, current_user)


@router.post(
    "/connections/export-images",
    response_model=ImageExportResponse,
)
@limiter.limit("20/minute")
async def export_images(
    request: Request,
    data: ExportImageRequest,
    service: AssetsService = Depends(get_assets_service),
    current_user: User = Depends(require_role("developer")),
) -> ImageExportResponse:
    """Export design nodes as images."""
    _ = request
    return await service.export_images(
        data.connection_id,
        current_user,
        data.node_ids,
        format=data.format,
        scale=data.scale,
    )


# ── Phase 12.2: Asset Storage ──


@router.post(
    "/connections/download-assets",
    response_model=DownloadAssetsResponse,
)
@limiter.limit("5/minute")
async def download_assets(
    request: Request,
    data: DownloadAssetsRequest,
    service: AssetsService = Depends(get_assets_service),
    current_user: User = Depends(require_role("developer")),
) -> DownloadAssetsResponse:
    """Export and download design assets to local storage."""
    _ = request
    return await service.download_assets(
        data.connection_id,
        current_user,
        data.node_ids,
        format=data.format,
        scale=data.scale,
    )


@router.get(
    "/assets/{connection_id}/{filename}",
)
@limiter.limit("60/minute")
async def serve_asset(
    connection_id: int,
    filename: str,
    request: Request,
    service: AssetsService = Depends(get_assets_service),
    connections: ConnectionService = Depends(get_connection_service),
    current_user: User = Depends(require_role("viewer")),
) -> FileResponse:
    """Serve a stored design asset file."""
    _ = request
    # BOLA check: verify user can access this connection
    await connections.get_connection(connection_id, current_user)
    # Get validated path
    path = service.get_asset_path(connection_id, filename)
    # Determine media type from extension
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
    }
    media_type = media_types.get(path.suffix, "application/octet-stream")
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Content-Security-Policy": "default-src 'none'"},
    )


# ── Phase 12.4: Layout Analysis & Brief Generation ──


@router.post(
    "/connections/analyze-layout",
    response_model=LayoutAnalysisResponse,
)
@limiter.limit("10/minute")
async def analyze_layout(
    request: Request,
    data: AnalyzeLayoutRequest,
    service: TokenConversionService = Depends(get_token_service),
    current_user: User = Depends(require_role("viewer")),
) -> LayoutAnalysisResponse:
    """Analyze design file layout and detect email sections (preview)."""
    _ = request
    return await service.analyze_layout(
        data.connection_id,
        current_user,
        selected_node_ids=data.selected_node_ids or None,
    )


@router.post(
    "/connections/generate-brief",
    response_model=GenerateBriefResponse,
)
@limiter.limit("5/minute")
async def generate_brief(
    request: Request,
    data: GenerateBriefRequest,
    service: TokenConversionService = Depends(get_token_service),
    current_user: User = Depends(require_role("developer")),
) -> GenerateBriefResponse:
    """Generate a Scaffolder-compatible campaign brief from design analysis."""
    _ = request
    return await service.generate_brief(
        data.connection_id,
        current_user,
        selected_node_ids=data.selected_node_ids or None,
        include_tokens=data.include_tokens,
    )


# ── Phase 12.6: Component Extraction ──


@router.post(
    "/connections/{connection_id}/extract-components",
    response_model=ExtractComponentsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("5/minute")
async def extract_components(
    connection_id: int,
    request: Request,
    body: ExtractComponentsRequest,
    service: ImportRequestService = Depends(get_import_service),
    current_user: User = Depends(require_role("developer")),
) -> ExtractComponentsResponse:
    """Extract Figma components into Hub components with AI-generated HTML.

    Returns immediately with import_id for polling status via
    GET /imports/{import_id}.
    """
    _ = request
    return await service.extract_components(
        connection_id=connection_id,
        user=current_user,
        component_ids=body.component_ids,
        generate_html=body.generate_html,
    )


# ── Phase 12.5: Design Import & Conversion Pipeline ──


@router.post("/imports", response_model=ImportResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_import(
    request: Request,
    data: StartImportRequest,
    service: ImportRequestService = Depends(get_import_service),
    current_user: User = Depends(require_role("developer")),
) -> ImportResponse:
    """Create a design import job with a brief for Scaffolder conversion."""
    _ = request
    return await service.create_design_import(data, current_user)


@router.get("/imports/by-template/{template_id}", response_model=ImportResponse | None)
@limiter.limit("30/minute")
async def get_import_by_template(
    template_id: int,
    request: Request,
    project_id: int = Query(..., description="Project ID for BOLA check"),
    service: ImportRequestService = Depends(get_import_service),
    current_user: User = Depends(require_role("viewer")),
) -> ImportResponse | None:
    """Get the design import that produced a template (for design reference panel)."""
    _ = request
    return await service.get_import_by_template(template_id, project_id, current_user)


@router.get("/imports/{import_id}", response_model=ImportResponse)
@limiter.limit("30/minute")
async def get_import(
    import_id: int,
    request: Request,
    service: ImportRequestService = Depends(get_import_service),
    current_user: User = Depends(require_role("viewer")),
) -> ImportResponse:
    """Get import status and result (poll this until completed/failed)."""
    _ = request
    return await service.get_design_import(import_id, current_user)


@router.patch("/imports/{import_id}/brief", response_model=ImportResponse)
@limiter.limit("10/minute")
async def update_import_brief(
    import_id: int,
    request: Request,
    data: UpdateImportBriefRequest,
    service: ImportRequestService = Depends(get_import_service),
    current_user: User = Depends(require_role("developer")),
) -> ImportResponse:
    """Edit the brief before triggering conversion. Only works in 'pending' state."""
    _ = request
    return await service.update_import_brief(import_id, data.generated_brief, current_user)


@router.post(
    "/imports/{import_id}/convert",
    response_model=ImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("3/minute")
async def convert_import(
    import_id: int,
    request: Request,
    body: ConvertImportRequest,
    service: ImportRequestService = Depends(get_import_service),
    current_user: User = Depends(require_role("developer")),
) -> ImportResponse:
    """Trigger the Scaffolder conversion pipeline. Returns immediately; poll GET /imports/{id}."""
    _ = request
    return await service.start_conversion(
        import_id,
        current_user,
        run_qa=body.run_qa,
        output_mode=body.output_mode,
        output_format=body.output_format,
        score_fidelity=body.score_fidelity,
    )


# ── Visual Fidelity Scoring (Phase 35.6) ──


@router.get("/imports/{import_id}/fidelity", response_model=FidelityResponse)
@limiter.limit("30/minute")
async def get_fidelity(
    import_id: int,
    request: Request,
    db: AsyncSession = Depends(get_scoped_db),
    current_user: User = Depends(require_role("developer")),
) -> FidelityResponse:
    """Get visual fidelity scoring results for a design import."""
    _ = request
    from app.design_sync.exceptions import ImportNotFoundError
    from app.design_sync.repository import DesignSyncRepository

    repo = DesignSyncRepository(db)
    design_import = await repo.get_import(import_id)
    if design_import is None:
        raise ImportNotFoundError(f"Import {import_id} not found")
    await AccessService(DesignSyncContext(db)).verify_access(design_import.project_id, current_user)
    fidelity = None
    if design_import.fidelity_json:
        fidelity = FidelityResult(**design_import.fidelity_json)
    return FidelityResponse(import_id=import_id, fidelity=fidelity)


@router.post(
    "/imports/{import_id}/score-fidelity",
    response_model=FidelityResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("5/minute")
async def trigger_fidelity_scoring(
    import_id: int,
    request: Request,
    db: AsyncSession = Depends(get_scoped_db),
    current_user: User = Depends(require_role("developer")),
) -> FidelityResponse:
    """Validate that an import is eligible for fidelity scoring and return current scores.

    To actually score, re-run conversion via POST /imports/{id}/convert with score_fidelity=true.
    """
    _ = request
    from app.design_sync.exceptions import ImportNotFoundError, ImportStateError
    from app.design_sync.repository import DesignSyncRepository

    repo = DesignSyncRepository(db)
    design_import = await repo.get_import(import_id)
    if design_import is None:
        raise ImportNotFoundError(f"Import {import_id} not found")
    await AccessService(DesignSyncContext(db)).verify_access(design_import.project_id, current_user)
    if design_import.status != "completed":
        raise ImportStateError("Fidelity scoring requires a completed import")
    fidelity = None
    if design_import.fidelity_json:
        fidelity = FidelityResult(**design_import.fidelity_json)
    return FidelityResponse(import_id=import_id, fidelity=fidelity)


@router.get("/imports/{import_id}/fidelity/diff-image")
@limiter.limit("30/minute")
async def get_diff_image(
    import_id: int,
    request: Request,
    db: AsyncSession = Depends(get_scoped_db),
    current_user: User = Depends(require_role("developer")),
) -> Response:
    """Get the visual diff overlay image for a fidelity-scored import."""
    _ = request
    from app.core.config import get_settings
    from app.core.exceptions import NotFoundError
    from app.design_sync.exceptions import ImportNotFoundError
    from app.design_sync.repository import DesignSyncRepository

    repo = DesignSyncRepository(db)
    design_import = await repo.get_import(import_id)
    if design_import is None:
        raise ImportNotFoundError(f"Import {import_id} not found")
    await AccessService(DesignSyncContext(db)).verify_access(design_import.project_id, current_user)
    if not design_import.fidelity_json:
        raise NotFoundError("No fidelity scores available for this import")

    settings = get_settings()
    diff_path = (
        Path(settings.design_sync.asset_storage_path) / "fidelity" / str(import_id) / "diff.png"
    )
    if not diff_path.exists():
        raise NotFoundError("Diff image not found")

    return Response(
        content=diff_path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ── Conversion Diagnostics ──


@router.get(
    "/connections/{connection_id}/diagnose",
    response_model=DiagnosticReportResponse,
)
@limiter.limit("2/minute")
async def diagnose_connection(
    connection_id: int,
    request: Request,
    service: TokenConversionService = Depends(get_token_service),
    current_user: User = Depends(require_role("developer")),
) -> DiagnosticReportResponse:
    """Run conversion diagnostics on a design connection.

    Returns a detailed report with per-section traces, data loss events,
    and pipeline stage metrics. Rate limited to 2/min (expensive operation).
    """
    _ = request
    from app.design_sync.diagnose.runner import DiagnosticRunner
    from app.design_sync.diagnose.schemas import DiagnosticReportResponse as DRR

    structure, tokens = await service.get_diagnostic_data(connection_id, current_user)

    runner = DiagnosticRunner()
    report = runner.run_from_structure(structure, tokens)
    return DRR.from_report(report)


# ── Correction Pattern Tracking (Phase 35.7) ──


@router.get("/correction-patterns")
@limiter.limit("30/minute")
async def list_correction_patterns(
    request: Request,
    min_occurrences: int = Query(default=5, ge=1),
    min_confidence: float = Query(default=0.9, ge=0.0, le=1.0),
    agent: str | None = Query(default=None),
    current_user: User = Depends(require_role("admin")),
) -> list[dict[str, object]]:
    """List frequent correction patterns above threshold. Admin only."""
    _ = (request, current_user)
    from app.design_sync.correction_tracker import CorrectionPatternResponse, CorrectionTracker

    tracker = CorrectionTracker(data_dir=Path("data"))
    patterns = tracker.get_frequent_patterns(
        min_occurrences=min_occurrences,
        min_confidence=min_confidence,
    )
    if agent:
        patterns = [p for p in patterns if p.agent == agent]
    return [CorrectionPatternResponse.from_pattern(p).model_dump(mode="json") for p in patterns]


@router.get("/correction-patterns/suggestions")
@limiter.limit("30/minute")
async def get_rule_suggestions(
    request: Request,
    current_user: User = Depends(require_role("admin")),
) -> list[dict[str, object]]:
    """Get converter rule suggestions from frequent patterns. Admin only."""
    _ = (request, current_user)
    from app.design_sync.correction_tracker import (
        ConverterRuleSuggestionResponse,
        CorrectionTracker,
    )

    tracker = CorrectionTracker(data_dir=Path("data"))
    suggestions = tracker.suggest_converter_rules()
    return [
        ConverterRuleSuggestionResponse.from_suggestion(s).model_dump(mode="json")
        for s in suggestions
    ]


@router.post("/correction-patterns/{pattern_hash}/approve")
@limiter.limit("10/minute")
async def approve_correction_rule(
    pattern_hash: str,
    request: Request,
    current_user: User = Depends(require_role("admin")),
) -> dict[str, str]:
    """Approve a correction pattern for converter rule application. Admin only."""
    _ = (request, current_user)
    import re

    if not re.fullmatch(r"[0-9a-f]{16}", pattern_hash):
        from app.core.exceptions import DomainValidationError

        raise DomainValidationError("Invalid pattern hash format")

    from app.design_sync.correction_tracker import CorrectionTracker

    tracker = CorrectionTracker(data_dir=Path("data"))
    tracker.approve_rule(pattern_hash)
    return {"status": "approved", "pattern_hash": pattern_hash}


# ── Figma Webhooks ──

_webhook_tasks: set[asyncio.Task[None]] = set()


@router.post("/webhooks/figma", status_code=200, include_in_schema=False)
@limiter.limit("60/minute")
async def handle_figma_webhook(
    request: Request,
    db: AsyncSession = Depends(get_scoped_db),
) -> dict[str, str]:
    """Receive Figma FILE_UPDATE webhook. Must respond < 5s."""
    from app.core.config import get_settings
    from app.core.logging import get_logger
    from app.design_sync.webhook import (
        debounced_sync_worker,
        enqueue_debounced_sync,
        verify_signature,
    )

    log = get_logger(__name__)
    settings = get_settings()

    if not settings.design_sync.figma_webhook_enabled:
        return {"status": "disabled"}

    from app.design_sync.exceptions import WebhookSignatureError

    body = await request.body()
    signature = request.headers.get("X-Figma-Signature", "")
    try:
        verify_signature(body, signature, settings.design_sync.figma_webhook_passcode)
    except WebhookSignatureError:
        log.warning("design_sync.webhook_signature_invalid")
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid webhook signature") from None

    from app.design_sync.schemas import FigmaWebhookPayload

    payload = FigmaWebhookPayload.model_validate_json(body)
    if payload.event_type != "FILE_UPDATE":
        return {"status": "ignored"}

    repo = DesignSyncRepository(db)
    conn = await repo.get_connection_by_file_ref("figma", payload.file_key)
    if conn is None:
        log.info("design_sync.webhook_no_connection", file_key=payload.file_key)
        return {"status": "ok"}

    await enqueue_debounced_sync(payload.file_key, conn.id)
    task = asyncio.create_task(debounced_sync_worker(conn.id, payload.file_key, conn.project_id))
    _webhook_tasks.add(task)
    task.add_done_callback(_webhook_tasks.discard)

    return {"status": "ok"}


@router.post(
    "/connections/{connection_id}/webhook",
    status_code=201,
    response_model=dict[str, str],
)
@limiter.limit("10/minute")
async def register_webhook(
    connection_id: int,
    request: Request,
    team_id: str = Query(..., description="Figma team ID for webhook scope"),
    service: WebhookService = Depends(get_webhook_service),
    current_user: User = Depends(require_role("admin")),
) -> dict[str, str]:
    """Register a Figma webhook for live sync. Admin only."""
    _ = request
    webhook_id = await service.register_figma_webhook(
        connection_id, team_id=team_id, user=current_user
    )
    return {"webhook_id": webhook_id}


@router.delete(
    "/connections/{connection_id}/webhook",
    status_code=204,
)
@limiter.limit("10/minute")
async def unregister_webhook(
    connection_id: int,
    request: Request,
    service: WebhookService = Depends(get_webhook_service),
    current_user: User = Depends(require_role("admin")),
) -> Response:
    """Remove a Figma webhook. Admin only."""
    _ = request
    await service.unregister_figma_webhook(connection_id, user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Section Cache (Phase 35.10) ──


@router.delete(
    "/connections/{connection_id}/cache",
    response_model=CacheClearResponse,
    status_code=200,
)
@limiter.limit("10/minute")
async def clear_section_cache(
    connection_id: int,
    request: Request,
    current_user: User = Depends(require_role("admin")),
) -> CacheClearResponse:
    """Clear cached conversion results for a connection. Admin only."""
    _ = request
    _ = current_user
    from app.design_sync.section_cache import get_section_cache

    cache = get_section_cache()
    cleared = await cache.invalidate_connection(str(connection_id))
    return CacheClearResponse(cleared_entries=cleared)


# ── EmailDesignDocument Schema (Phase 36.1) ──

_MAX_DOCUMENT_BODY_BYTES = 5 * 1024 * 1024  # 5 MB


@router.get("/schema/v1")
@limiter.limit("60/minute")
async def get_document_schema(request: Request) -> Response:
    """Serve the EmailDesignDocument v1 JSON Schema (public, no auth required)."""
    _ = request
    from app.design_sync.email_design_document import EmailDesignDocument

    body = json.dumps(EmailDesignDocument.schema(), separators=(",", ":"))
    return Response(
        content=body,
        media_type="application/schema+json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/validate-document", response_model=DocumentValidationResponse)
@limiter.limit("30/minute")
async def validate_document(
    request: Request,
    current_user: User = Depends(require_role("viewer")),
) -> DocumentValidationResponse:
    """Validate a JSON body against the EmailDesignDocument schema for its version (1.0, 2.0)."""
    _ = current_user
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_DOCUMENT_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Request body exceeds 5 MB limit")
        except ValueError:
            pass  # Malformed Content-Length — let body-length check below handle it

    body = await request.body()
    if len(body) > _MAX_DOCUMENT_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Request body exceeds 5 MB limit")

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return DocumentValidationResponse(valid=False, errors=["Request body is not valid JSON"])

    if not isinstance(data, dict):
        return DocumentValidationResponse(valid=False, errors=["Document must be a JSON object"])

    from app.design_sync.email_design_document import EmailDesignDocument

    errors = EmailDesignDocument.validate(cast(dict[str, Any], data))
    return DocumentValidationResponse(valid=not errors, errors=errors)


# ── MJML import (36.4) ──────────────────────────────────────────────


@router.post("/import/mjml", response_model=ImportMjmlResponse)
@limiter.limit("10/minute")
async def import_mjml(
    request: Request,
    body: ImportMjmlRequest,
    current_user: User = Depends(require_role("developer")),
) -> ImportMjmlResponse:
    """Import MJML markup and produce an EmailDesignDocument."""
    from app.core.config import get_settings
    from app.core.logging import get_logger
    from app.design_sync.email_design_document import EmailDesignDocument
    from app.design_sync.exceptions import MjmlImportError
    from app.design_sync.mjml_import.adapter import MjmlImportAdapter

    logger = get_logger(__name__)

    settings = get_settings()
    if not settings.design_sync.mjml_import_enabled:
        raise HTTPException(status_code=503, detail="MJML import is disabled")

    adapter = MjmlImportAdapter()
    try:
        document = adapter.parse(body.mjml_source)
    except MjmlImportError as exc:
        logger.warning("design_sync.mjml_import_failed", reason=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    doc_json = document.to_json()
    errors = EmailDesignDocument.validate(doc_json)
    warnings = [str(e) for e in errors] if errors else []

    logger.info(
        "design_sync.mjml_import_completed",
        sections_count=len(document.sections),
        warning_count=len(warnings),
    )

    return ImportMjmlResponse(
        document=doc_json,
        sections_count=len(document.sections),
        warnings=warnings,
    )


# ── HTML reverse-engineering import (36.5) ─────────────────────────


@router.post(
    "/import/html",
    response_model=HtmlImportResponse,
    summary="Import email HTML as EmailDesignDocument",
)
@limiter.limit("10/minute")
async def import_html(
    request: Request,
    body: HtmlImportRequest,
    current_user: User = Depends(require_role("developer")),
) -> HtmlImportResponse:
    """Reverse-engineer arbitrary email HTML into a structured EmailDesignDocument."""
    from app.design_sync.exceptions import HtmlImportError
    from app.design_sync.html_import.adapter import HtmlImportAdapter

    adapter = HtmlImportAdapter()
    try:
        document = await adapter.parse(
            body.html,
            use_ai=body.use_ai,
            source_name=body.source_name,
        )
    except HtmlImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    doc_json = document.to_json()
    ai_count = sum(1 for s in document.sections if s.classification_confidence is not None)

    return HtmlImportResponse(
        document=doc_json,
        section_count=len(document.sections),
        ai_sections_classified=ai_count,
        warnings=[],
    )


# ── Training case endpoints ──────────────────────────────────────


class CreateTrainingCaseRequest(BaseModel):
    """Request body for creating a training case."""

    case_id: str = PydanticField(..., description="Case slug (alphanumeric, hyphens, underscores)")
    case_name: str = PydanticField(..., description="Human-readable case name")
    html_content: str = PydanticField(..., description="HTML email source")
    source_name: str = PydanticField(default="training", description="Source label")
    figma_url: str | None = PydanticField(default=None, description="Figma design URL")
    figma_node: str | None = PydanticField(default=None, description="Figma frame node ID")
    screenshot_b64: str | None = PydanticField(
        default=None, description="Base64-encoded screenshot (data URL or raw)"
    )


@router.post(
    "/training-cases",
    status_code=status.HTTP_201_CREATED,
    summary="Save HTML training case to disk and register in manifest",
)
@limiter.limit("10/minute")
async def create_training_case(
    request: Request,
    body: CreateTrainingCaseRequest,
    current_user: User = Depends(require_role("developer")),
) -> dict[str, Any]:
    """Save an HTML email + optional screenshot as a training case.

    Creates ``data/debug/{case_id}/`` with ``expected.html`` and optionally
    ``design.png``, then registers the case in the global manifest.
    """
    from app.design_sync.exceptions import TrainingCaseError, TrainingCaseExistsError
    from app.design_sync.service import create_training_case as create_case

    screenshot_data: bytes | None = None
    if body.screenshot_b64:
        import base64

        try:
            raw = body.screenshot_b64
            # Strip data URL prefix if present (e.g. "data:image/png;base64,...")
            if "," in raw:
                raw = raw.split(",", 1)[1]
            screenshot_data = base64.b64decode(raw)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"Invalid screenshot base64: {exc}"
            ) from exc

    try:
        return await create_case(
            case_id=body.case_id,
            case_name=body.case_name,
            html_content=body.html_content,
            source_name=body.source_name,
            figma_url=body.figma_url,
            figma_node=body.figma_node,
            screenshot_data=screenshot_data,
        )
    except TrainingCaseExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TrainingCaseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/training-cases/{case_id}/backfill",
    summary="Backfill a training case into the learning loop",
)
@limiter.limit("5/minute")
async def backfill_training_case_route(
    case_id: str,
    request: Request,
    traces_only: bool = Query(default=False, description="Write JSONL traces only (no DB)"),
    current_user: User = Depends(require_role("developer")),
) -> dict[str, Any]:
    """Trigger learning loop backfill for a single training case.

    For Figma-sourced cases (with ``structure.json``), runs the full converter.
    For HTML-only cases, parses ``expected.html`` to build a synthetic result
    and persists traces/memory/insights from it.
    """
    from app.design_sync.exceptions import TrainingCaseError
    from app.design_sync.service import backfill_training_case

    try:
        return await backfill_training_case(case_id, traces_only=traces_only)
    except TrainingCaseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
