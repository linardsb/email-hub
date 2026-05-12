# pyright: reportUnknownMemberType=false, reportUntypedFunctionDecorator=false
"""Knowledge base REST API endpoints."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.knowledge.graph.cognee_provider import CogneeGraphProvider

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.requests import Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_role
from app.auth.models import User
from app.core.rate_limit import limiter
from app.core.scoped_db import get_scoped_db
from app.knowledge.exceptions import DuplicateTagError
from app.knowledge.proactive_qa_routes import router as proactive_qa_router
from app.knowledge.schemas import (
    DocumentContentResponse,
    DocumentResponse,
    DocumentTagRequest,
    DocumentUpdate,
    DocumentUpload,
    DomainListResponse,
    GraphEntityResponse,
    GraphRelationshipResponse,
    GraphSearchRequest,
    GraphSearchResponse,
    GraphSearchResultResponse,
    SearchRequest,
    SearchResponse,
    TagCreate,
    TagListResponse,
    TagResponse,
)
from app.knowledge.services.graph import GraphSearchService
from app.knowledge.services.ingestion import IngestionService
from app.knowledge.services.search import SearchService
from app.knowledge.services.tags import TagService
from app.shared.schemas import PaginatedResponse, PaginationParams

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
router.include_router(proactive_qa_router)


def get_ingestion_service(db: AsyncSession = Depends(get_scoped_db)) -> IngestionService:
    """Dependency: build an IngestionService for the request-scoped session."""
    return IngestionService(db)


def get_search_service(db: AsyncSession = Depends(get_scoped_db)) -> SearchService:
    """Dependency: build a SearchService for the request-scoped session."""
    return SearchService(db)


def get_tag_service(db: AsyncSession = Depends(get_scoped_db)) -> TagService:
    """Dependency: build a TagService for the request-scoped session."""
    return TagService(db)


_CONTENT_TYPE_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "message/rfc822": "email",
    "text/plain": "text",
    "text/markdown": "text",
    "text/csv": "csv",
}


def _detect_source_type(content_type: str | None) -> str:
    """Detect source type from MIME content type.

    Args:
        content_type: MIME type string from upload.

    Returns:
        Source type string (pdf, docx, email, image, text, xlsx, csv).
    """
    if content_type is None:
        return "text"
    if content_type in _CONTENT_TYPE_MAP:
        return _CONTENT_TYPE_MAP[content_type]
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("text/"):
        return "text"
    return "unknown"


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    domain: str = Form(...),
    language: str = Form(default="en"),
    metadata_json: str | None = Form(default=None),
    title: str | None = Form(default=None),
    description: str | None = Form(default=None),
    service: IngestionService = Depends(get_ingestion_service),
    _current_user: User = Depends(require_role("admin", "developer")),
) -> DocumentResponse:
    """Upload and ingest a document into the knowledge base."""
    _ = request
    upload = DocumentUpload(
        domain=domain,
        language=language,
        metadata_json=metadata_json,
        title=title,
        description=description,
    )
    source_type = _detect_source_type(file.content_type)
    if source_type == "unknown":
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Supported: PDF, DOCX, XLSX, CSV, TXT, images, email.",
        )

    # Sanitize filename: strip path components, limit to basename
    raw_filename = file.filename or "unknown"
    safe_filename = re.sub(r"[^\w\-.]", "_", Path(raw_filename).name.replace("\x00", ""))
    if not safe_filename or safe_filename.startswith("."):
        safe_filename = "upload" + Path(raw_filename).suffix

    # Save to temp file with streaming size limit
    max_upload_size = 50 * 1024 * 1024  # 50MB
    suffix = Path(safe_filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        size = 0
        while chunk := await file.read(8192):
            size += len(chunk)
            if size > max_upload_size:
                tmp.close()
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="File exceeds 50MB limit")
            tmp.write(chunk)
        tmp.flush()
    try:
        return await service.ingest_document(
            file_path=str(tmp_path),
            upload=upload,
            filename=safe_filename,
            source_type=source_type,
            file_size=size,
        )
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@router.get("/documents", response_model=PaginatedResponse[DocumentResponse])
@limiter.limit("30/minute")
async def list_documents(
    request: Request,
    pagination: PaginationParams = Depends(),
    domain: str | None = Query(None, max_length=50),
    document_status: str | None = Query(None, alias="status", max_length=20),
    tag: str | None = Query(None, max_length=100),
    service: IngestionService = Depends(get_ingestion_service),
    _current_user: User = Depends(get_current_user),
) -> PaginatedResponse[DocumentResponse]:
    """List documents with pagination and optional filtering."""
    _ = request
    return await service.list_documents(pagination, domain=domain, status=document_status, tag=tag)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
@limiter.limit("30/minute")
async def get_document(
    request: Request,
    document_id: int,
    service: IngestionService = Depends(get_ingestion_service),
    _current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    """Get a document by its database ID."""
    _ = request
    return await service.get_document(document_id)


@router.patch("/documents/{document_id}", response_model=DocumentResponse)
@limiter.limit("10/minute")
async def update_document(
    request: Request,
    document_id: int,
    body: DocumentUpdate,
    service: IngestionService = Depends(get_ingestion_service),
    _current_user: User = Depends(require_role("admin", "developer")),
) -> DocumentResponse:
    """Update document metadata (title, description, domain, language)."""
    _ = request
    return await service.update_document(document_id, body)


@router.get("/documents/{document_id}/download")
@limiter.limit("30/minute")
async def download_document(
    request: Request,
    document_id: int,
    service: IngestionService = Depends(get_ingestion_service),
    _current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download the original uploaded file."""
    _ = request
    file_path, filename = await service.get_document_file_path(document_id)
    resolved = Path(file_path).resolve()
    from app.core.config import get_settings

    storage_root = Path(get_settings().knowledge.document_storage_path).resolve()
    if not resolved.is_relative_to(storage_root):
        from app.knowledge.exceptions import ProcessingError

        raise ProcessingError("File path outside storage directory")
    return FileResponse(
        path=resolved,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.get("/documents/{document_id}/content", response_model=DocumentContentResponse)
@limiter.limit("30/minute")
async def get_document_content(
    request: Request,
    document_id: int,
    service: IngestionService = Depends(get_ingestion_service),
    _current_user: User = Depends(get_current_user),
) -> DocumentContentResponse:
    """Get extracted text chunks for a document."""
    _ = request
    return await service.get_document_content(document_id)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_document(
    request: Request,
    document_id: int,
    service: IngestionService = Depends(get_ingestion_service),
    _current_user: User = Depends(require_role("admin", "developer")),
) -> None:
    """Delete a document and its chunks."""
    _ = request
    await service.delete_document(document_id)


@router.get("/domains", response_model=DomainListResponse)
@limiter.limit("30/minute")
async def list_domains(
    request: Request,
    service: IngestionService = Depends(get_ingestion_service),
    _current_user: User = Depends(get_current_user),
) -> DomainListResponse:
    """List all unique document domains."""
    _ = request
    return await service.list_domains()


# ---------------------------------------------------------------------------
# Tag endpoints
# ---------------------------------------------------------------------------


@router.get("/tags", response_model=TagListResponse)
@limiter.limit("30/minute")
async def list_tags(
    request: Request,
    service: TagService = Depends(get_tag_service),
    _current_user: User = Depends(get_current_user),
) -> TagListResponse:
    """List all tags."""
    _ = request
    return await service.list_tags()


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_tag(
    request: Request,
    body: TagCreate,
    service: TagService = Depends(get_tag_service),
    _current_user: User = Depends(require_role("admin", "developer")),
) -> TagResponse:
    """Create a new tag."""
    _ = request
    try:
        return await service.create_tag(body)
    except DuplicateTagError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_tag(
    request: Request,
    tag_id: int,
    service: TagService = Depends(get_tag_service),
    _current_user: User = Depends(require_role("admin", "developer")),
) -> None:
    """Delete a tag (CASCADE removes document associations)."""
    _ = request
    await service.delete_tag(tag_id)


@router.post(
    "/documents/{document_id}/tags",
    response_model=DocumentResponse,
)
@limiter.limit("10/minute")
async def add_tags_to_document(
    request: Request,
    document_id: int,
    body: DocumentTagRequest,
    service: TagService = Depends(get_tag_service),
    _current_user: User = Depends(require_role("admin", "developer")),
) -> DocumentResponse:
    """Add tags to a document."""
    _ = request
    return await service.add_tags_to_document(document_id, body)


@router.delete(
    "/documents/{document_id}/tags/{tag_id}",
    response_model=DocumentResponse,
)
@limiter.limit("10/minute")
async def remove_tag_from_document(
    request: Request,
    document_id: int,
    tag_id: int,
    service: TagService = Depends(get_tag_service),
    _current_user: User = Depends(require_role("admin", "developer")),
) -> DocumentResponse:
    """Remove a tag from a document."""
    _ = request
    return await service.remove_tag_from_document(document_id, tag_id)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.post("/search", response_model=SearchResponse)
@limiter.limit("30/minute")
async def search_knowledge(
    request: Request,
    body: SearchRequest,
    service: SearchService = Depends(get_search_service),
    _current_user: User = Depends(get_current_user),
) -> SearchResponse:
    """Search the knowledge base with hybrid vector + fulltext search."""
    _ = request
    return await service.search(body)


@router.post("/search/routed", response_model=SearchResponse)
@limiter.limit("30/minute")
async def search_knowledge_routed(
    request: Request,
    body: SearchRequest,
    service: SearchService = Depends(get_search_service),
    _current_user: User = Depends(get_current_user),
) -> SearchResponse:
    """Search with intent-based query routing."""
    _ = request
    return await service.search_routed(body)


# ---------------------------------------------------------------------------
# Graph knowledge search
# ---------------------------------------------------------------------------


def _get_graph_provider() -> CogneeGraphProvider | None:
    """Factory: returns CogneeGraphProvider if enabled, else None."""
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.cognee.enabled:
        return None
    from app.knowledge.graph.cognee_provider import CogneeGraphProvider as Provider

    return Provider(settings)


@router.post("/graph/search", response_model=GraphSearchResponse)
@limiter.limit("20/minute")
async def search_graph(
    request: Request,
    body: GraphSearchRequest,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_scoped_db),
) -> GraphSearchResponse:
    """Search the knowledge graph for entity-relationship results."""
    _ = request
    graph_provider = _get_graph_provider()
    service = GraphSearchService(db=db, graph_provider=graph_provider)

    if body.mode == "completion":
        answer = await service.search_graph_completion(
            body.query,
            dataset_name=body.dataset_name,
            system_prompt=body.system_prompt,
        )
        return GraphSearchResponse(
            results=[GraphSearchResultResponse(content=answer)],
            query=body.query,
            mode="completion",
        )

    results = await service.search_graph(
        body.query,
        dataset_name=body.dataset_name,
        top_k=body.top_k,
    )
    return GraphSearchResponse(
        results=[
            GraphSearchResultResponse(
                content=r.content,
                entities=[
                    GraphEntityResponse(
                        id=e.id,
                        name=e.name,
                        entity_type=e.entity_type,
                        description=e.description,
                        properties=e.properties,
                    )
                    for e in r.entities
                ],
                relationships=[
                    GraphRelationshipResponse(
                        source_id=rel.source_id,
                        target_id=rel.target_id,
                        relationship_type=rel.relationship_type,
                        properties=rel.properties,
                    )
                    for rel in r.relationships
                ],
                score=r.score,
            )
            for r in results
        ],
        query=body.query,
        mode="chunks",
    )
