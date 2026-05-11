"""Knowledge-base tag management."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.knowledge.exceptions import (
    DocumentNotFoundError,
    DuplicateTagError,
    TagNotFoundError,
)
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import (
    DocumentResponse,
    DocumentTagRequest,
    TagCreate,
    TagListResponse,
    TagResponse,
)

logger = get_logger(__name__)


class TagService:
    """Knowledge-base tag CRUD + document-tag assignment."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialise with an async database session."""
        self.db = db
        self.repository = KnowledgeRepository(db)

    async def list_tags(self) -> TagListResponse:
        """List all tags sorted by name."""
        tags = await self.repository.list_tags()
        tag_items = [TagResponse.model_validate(t) for t in tags]
        return TagListResponse(tags=tag_items, total=len(tag_items))

    async def create_tag(self, data: TagCreate) -> TagResponse:
        """Create a new tag."""
        existing = await self.repository.get_tag_by_name(data.name)
        if existing:
            raise DuplicateTagError(f"Tag '{data.name}' already exists")
        tag = await self.repository.create_tag(data.name)
        logger.info("knowledge.tag.created", tag_id=tag.id, tag_name=tag.name)
        return TagResponse.model_validate(tag)

    async def delete_tag(self, tag_id: int) -> None:
        """Delete a tag by ID (CASCADE removes document associations)."""
        deleted = await self.repository.delete_tag(tag_id)
        if not deleted:
            raise TagNotFoundError(f"Tag {tag_id} not found")
        logger.info("knowledge.tag.deleted", tag_id=tag_id)

    async def add_tags_to_document(
        self, document_id: int, data: DocumentTagRequest
    ) -> DocumentResponse:
        """Add tags to a document."""
        doc = await self.repository.get_document(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        await self.repository.add_tags_to_document(document_id, data.tag_ids)
        logger.info(
            "knowledge.document.tags_updated",
            document_id=document_id,
            tag_ids=data.tag_ids,
            action="add",
        )
        return await self._reload_document(document_id)

    async def remove_tag_from_document(self, document_id: int, tag_id: int) -> DocumentResponse:
        """Remove a tag from a document."""
        doc = await self.repository.get_document(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        await self.repository.remove_tag_from_document(document_id, tag_id)
        logger.info(
            "knowledge.document.tags_updated",
            document_id=document_id,
            tag_id=tag_id,
            action="remove",
        )
        return await self._reload_document(document_id)

    async def _reload_document(self, document_id: int) -> DocumentResponse:
        """Re-read the document + its tags into the response shape.

        Independent of IngestionService so TagService can stand alone.
        """
        doc = await self.repository.get_document(document_id)
        if not doc:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        doc_resp = DocumentResponse.model_validate(doc)
        doc_resp.tags = [
            TagResponse.model_validate(t)
            for t in await self.repository.get_tags_for_document(document_id)
        ]
        return doc_resp
