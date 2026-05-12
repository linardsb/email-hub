# pyright: reportPrivateUsage=false
"""Document ingestion + metadata management.

Owns the document lifecycle: ingest (extract → chunk → embed → store),
update, retrieve, list, delete, and best-effort LLM auto-tagging.

The module-level imports (`chunking`, `chunking_html`, `processing`,
`get_settings`, `_providers`) are also the canonical `unittest.mock.patch`
targets — see `app/knowledge/_providers.py` for the singleton-call idiom.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.knowledge import _providers, chunking, chunking_html, processing
from app.knowledge.exceptions import (
    DocumentNotFoundError,
    ProcessingError,
)
from app.knowledge.models import DocumentChunk
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import (
    DocumentChunkResponse,
    DocumentContentResponse,
    DocumentResponse,
    DocumentUpdate,
    DocumentUpload,
    DomainListResponse,
    TagResponse,
)
from app.shared.schemas import PaginatedResponse, PaginationParams

logger = get_logger(__name__)


class IngestionService:
    """Document ingestion + metadata management."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialise with an async database session."""
        self.db = db
        self.repository = KnowledgeRepository(db)

    async def ingest_document(
        self,
        *,
        file_path: str,
        upload: DocumentUpload,
        filename: str,
        source_type: str,
        file_size: int | None,
    ) -> DocumentResponse:
        """Ingest a document: extract text, chunk, embed, and store."""
        settings = get_settings()
        start = time.monotonic()
        title = upload.title or Path(filename).stem
        logger.info(
            "knowledge.ingest.started",
            filename=filename,
            title=title,
            domain=upload.domain,
            source_type=source_type,
        )

        doc = await self.repository.create_document(
            filename=filename,
            domain=upload.domain,
            source_type=source_type,
            language=upload.language,
            file_size_bytes=file_size,
            metadata_json=upload.metadata_json,
            title=title,
            description=upload.description,
            status="processing",
            ocr_applied=False,
        )

        try:
            text, ocr_applied = await processing.extract_text(file_path, source_type)
            if ocr_applied:
                logger.info("knowledge.ingest.ocr_applied", document_id=doc.id)

            if settings.security.prompt_guard_enabled:
                from app.ai.security.prompt_guard import scan_for_injection

                _scan = scan_for_injection(text, mode=settings.security.prompt_guard_mode)
                if not _scan.clean:
                    logger.warning(
                        "security.prompt_injection_detected",
                        source="knowledge_ingest",
                        document_id=str(doc.id),
                        flags=_scan.flags,
                    )
                    if _scan.sanitized is not None:
                        text = _scan.sanitized

            storage_dir = Path(settings.knowledge.document_storage_path) / str(doc.id)
            storage_dir.mkdir(parents=True, exist_ok=True)
            stored_path = storage_dir / filename
            if not stored_path.resolve().is_relative_to(storage_dir.resolve()):
                raise ProcessingError(f"Invalid filename: {filename}")
            shutil.copy2(file_path, stored_path)
            await self.repository.update_document_file_path(doc.id, str(stored_path))
            logger.info(
                "knowledge.document.file_stored",
                document_id=doc.id,
                file_path=str(stored_path),
            )

            if settings.knowledge.html_chunking_enabled and chunking_html.is_html_content(text):
                logger.info("knowledge.ingest.html_chunking", document_id=doc.id)
                html_results = chunking_html.chunk_html(
                    text,
                    chunk_size=settings.knowledge.html_chunk_size,
                    chunk_overlap=settings.knowledge.html_chunk_overlap,
                )
                if not html_results:
                    await self.repository.update_document_status(doc.id, "completed", None, 0)
                    return await self.get_document(doc.id)

                if settings.knowledge.multi_rep_enabled:
                    from app.knowledge.summarizer import ChunkSummarizer

                    summarizer = ChunkSummarizer()
                    chunk_summaries = await summarizer.summarize(
                        [(c.chunk_index, c.content, c.section_type) for c in html_results]
                    )
                    summaries: list[str | None] = [
                        cs.summary or html_results[i].summary
                        for i, cs in enumerate(chunk_summaries)
                    ]
                    texts_to_embed: list[str] = [
                        summaries[i] or html_results[i].content for i in range(len(html_results))
                    ]
                else:
                    summaries = [c.summary for c in html_results]
                    texts_to_embed = [c.content for c in html_results]

                embeddings = await _providers._get_embedding().embed(texts_to_embed)
                chunk_objects = [
                    DocumentChunk(
                        document_id=doc.id,
                        content=html_results[i].content,
                        chunk_index=html_results[i].chunk_index,
                        embedding=embeddings[i],
                        metadata_json=None,
                        section_type=html_results[i].section_type,
                        summary=summaries[i],
                    )
                    for i in range(len(html_results))
                ]
                chunk_count = len(html_results)
            else:
                chunks_text = chunking.chunk_text(
                    text,
                    chunk_size=settings.knowledge.chunk_size,
                    chunk_overlap=settings.knowledge.chunk_overlap,
                )

                if not chunks_text:
                    await self.repository.update_document_status(doc.id, "completed", None, 0)
                    return await self.get_document(doc.id)

                texts_to_embed = [c.content for c in chunks_text]
                embeddings = await _providers._get_embedding().embed(texts_to_embed)
                chunk_objects = [
                    DocumentChunk(
                        document_id=doc.id,
                        content=chunks_text[i].content,
                        chunk_index=chunks_text[i].chunk_index,
                        embedding=embeddings[i],
                        metadata_json=None,
                    )
                    for i in range(len(chunks_text))
                ]
                chunk_count = len(chunks_text)

            await self.repository.bulk_create_chunks(chunk_objects)
            await self.repository.update_document_status(doc.id, "completed", None, chunk_count)

            if ocr_applied:
                await self.repository.update_document_ocr_applied(doc.id, ocr_applied=True)

            await self._auto_tag_document(doc.id, text)

        except Exception as e:
            try:
                await self.repository.update_document_status(doc.id, "failed", str(e), 0)
            except Exception:
                logger.error(
                    "knowledge.ingest.status_update_failed",
                    document_id=doc.id,
                    exc_info=True,
                )
            try:
                stored_dir = Path(settings.knowledge.document_storage_path) / str(doc.id)
                if stored_dir.exists():
                    shutil.rmtree(stored_dir)
                    logger.info("knowledge.ingest.cleanup", document_id=doc.id)
            except Exception:
                logger.error("knowledge.ingest.cleanup_failed", document_id=doc.id)
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "knowledge.ingest.failed",
                exc_info=True,
                error=str(e),
                error_type=type(e).__name__,
                document_id=doc.id,
                duration_ms=duration_ms,
            )
            raise

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "knowledge.ingest.completed",
            document_id=doc.id,
            chunk_count=chunk_count,
            duration_ms=duration_ms,
        )

        return await self.get_document(doc.id)

    async def ingest_text(
        self,
        *,
        title: str,
        content: str,
        domain: str,
        metadata_json: str | None = None,
        language: str = "en",
    ) -> int:
        """Ingest a text string directly as a knowledge document (no file on disk)."""
        settings = get_settings()

        doc = await self.repository.create_document(
            filename=f"{title[:100]}.md",
            domain=domain,
            source_type="text",
            language=language,
            file_size_bytes=len(content.encode("utf-8")),
            metadata_json=metadata_json,
            title=title,
            description=None,
            status="processing",
            ocr_applied=False,
        )

        try:
            chunks = chunking.chunk_text(
                content,
                chunk_size=settings.knowledge.chunk_size,
                chunk_overlap=settings.knowledge.chunk_overlap,
            )

            if not chunks:
                await self.repository.update_document_status(doc.id, "completed", None, 0)
                return doc.id

            texts = [c.content for c in chunks]
            embeddings = await _providers._get_embedding().embed(texts)

            chunk_objects = [
                DocumentChunk(
                    document_id=doc.id,
                    content=chunks[i].content,
                    chunk_index=chunks[i].chunk_index,
                    embedding=embeddings[i],
                    metadata_json=None,
                )
                for i in range(len(chunks))
            ]

            await self.repository.bulk_create_chunks(chunk_objects)
            await self.repository.update_document_status(doc.id, "completed", None, len(chunks))

        except Exception as e:
            try:
                await self.repository.update_document_status(doc.id, "failed", str(e), 0)
            except Exception:
                logger.error(
                    "knowledge.ingest_text.status_update_failed",
                    document_id=doc.id,
                    exc_info=True,
                )
            raise

        logger.info(
            "knowledge.ingest_text.completed",
            document_id=doc.id,
            title=title,
            domain=domain,
            chunk_count=len(chunks),
        )
        return doc.id

    async def update_document(self, document_id: int, data: DocumentUpdate) -> DocumentResponse:
        """Update document metadata."""
        logger.info("knowledge.document.update_started", document_id=document_id)
        updated = await self.repository.update_document(
            document_id, **data.model_dump(exclude_unset=True)
        )
        if not updated:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        logger.info("knowledge.document.update_completed", document_id=document_id)
        return await self.get_document(document_id)

    async def get_document_content(self, document_id: int) -> DocumentContentResponse:
        """Get document metadata and extracted text chunks."""
        doc = await self.repository.get_document(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document {document_id} not found")

        chunks = await self.repository.get_chunks_by_document(document_id)
        logger.info(
            "knowledge.document.content_retrieved",
            document_id=document_id,
            chunk_count=len(chunks),
        )

        return DocumentContentResponse(
            document_id=doc.id,
            filename=doc.filename,
            title=doc.title,
            total_chunks=len(chunks),
            chunks=[
                DocumentChunkResponse(chunk_index=c.chunk_index, content=c.content) for c in chunks
            ],
        )

    async def get_document_file_path(self, document_id: int) -> tuple[str, str]:
        """Get the stored file path and filename for download."""
        doc = await self.repository.get_document(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        if not doc.file_path:
            raise ProcessingError(f"Document {document_id} has no stored file (legacy upload)")
        return (doc.file_path, doc.filename)

    async def list_domains(self) -> DomainListResponse:
        """List all unique document domains."""
        domains = await self.repository.list_domains()
        logger.info("knowledge.domains.list_completed", domain_count=len(domains))
        return DomainListResponse(domains=domains, total=len(domains))

    async def get_document(self, document_id: int) -> DocumentResponse:
        """Get a document by ID."""
        doc = await self.repository.get_document(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        doc_resp = DocumentResponse.model_validate(doc)
        doc_tags = await self.repository.get_tags_for_document(document_id)
        doc_resp.tags = [TagResponse.model_validate(t) for t in doc_tags]
        return doc_resp

    async def list_documents(
        self,
        pagination: PaginationParams,
        *,
        domain: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> PaginatedResponse[DocumentResponse]:
        """List documents with pagination and optional filtering."""
        docs = await self.repository.list_documents(
            offset=pagination.offset,
            limit=pagination.page_size,
            domain=domain,
            status=status,
            tag=tag,
        )
        total = await self.repository.count_documents(domain=domain, status=status, tag=tag)

        doc_ids = [d.id for d in docs]
        tags_map = await self.repository.get_tags_for_documents(doc_ids)

        items: list[DocumentResponse] = []
        for d in docs:
            doc_resp = DocumentResponse.model_validate(d)
            doc_resp.tags = [TagResponse.model_validate(t) for t in tags_map.get(d.id, [])]
            items.append(doc_resp)

        return PaginatedResponse[DocumentResponse](
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    async def delete_document(self, document_id: int) -> None:
        """Delete a document, its chunks, and stored file."""
        doc = await self.repository.get_document(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document {document_id} not found")

        if doc.file_path:
            file_dir = Path(doc.file_path).parent
            shutil.rmtree(file_dir, ignore_errors=True)
            logger.info(
                "knowledge.document.file_deleted",
                document_id=document_id,
                file_dir=str(file_dir),
            )

        await self.repository.delete_document(document_id)
        logger.info("knowledge.delete.completed", document_id=document_id)

    async def _auto_tag_document(self, document_id: int, text: str) -> None:
        """Auto-tag a document using LLM classification.

        Best-effort: failures are logged but never raise exceptions.
        Only runs when auto_tag_enabled is True in settings.
        """
        import json as json_lib

        import httpx

        settings = get_settings()
        if not settings.knowledge.auto_tag_enabled:
            return

        logger.info("knowledge.autotag.started", document_id=document_id)

        try:
            truncated = text[: settings.knowledge.auto_tag_max_chars]

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.knowledge.auto_tag_api_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.knowledge.auto_tag_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.knowledge.auto_tag_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are a document classifier. Given document text, return 1-3 short "
                                    "tags as a JSON array of lowercase single-word strings. "
                                    'Example: ["finance", "policy", "safety"]. Return ONLY the JSON array.'
                                ),
                            },
                            {"role": "user", "content": truncated},
                        ],
                        "temperature": 0.0,
                    },
                )
                response.raise_for_status()
                data = response.json()
                raw_response = data["choices"][0]["message"]["content"]

            parsed = json_lib.loads(raw_response)
            if not isinstance(parsed, list):
                logger.warning(
                    "knowledge.autotag.failed",
                    document_id=document_id,
                    reason="LLM response is not a list",
                )
                return

            created_count = 0
            for name in parsed[:3]:  # pyright: ignore[reportUnknownVariableType]
                if not isinstance(name, str) or not name.strip():
                    continue
                normalized = name.strip().lower()
                tag = await self.repository.get_or_create_tag(normalized)
                await self.repository.add_tags_to_document(document_id, [tag.id])
                created_count += 1

            logger.info(
                "knowledge.autotag.completed",
                document_id=document_id,
                tag_count=created_count,
            )

        except Exception as e:
            logger.warning(
                "knowledge.autotag.failed",
                document_id=document_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
