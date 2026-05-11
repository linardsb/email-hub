"""Knowledge service façade.

The original 1050-LOC `KnowledgeService` god class has been split into four
single-responsibility services under `app/knowledge/services/`. This module
keeps a slim composite so out-of-tree callers can still hold one handle and
so existing `patch("app.knowledge.service.KnowledgeService")` test scaffolds
keep resolving the class name.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.graph.protocols import GraphKnowledgeProvider
from app.knowledge.services import (
    GraphSearchService,
    IngestionService,
    SearchService,
    TagService,
)

__all__ = [
    "GraphSearchService",
    "IngestionService",
    "KnowledgeService",
    "SearchService",
    "TagService",
]


class KnowledgeService:
    """Composite façade over the four split services."""

    def __init__(
        self,
        db: AsyncSession,
        graph_provider: GraphKnowledgeProvider | None = None,
    ) -> None:
        """Initialise the four sub-services from a single session.

        Args:
            db: SQLAlchemy async session.
            graph_provider: Optional graph knowledge provider (Cognee).
        """
        self.db = db
        self.ingestion = IngestionService(db)
        self.search_svc = SearchService(db)
        self.tags = TagService(db)
        self.graph = GraphSearchService(db, graph_provider=graph_provider)
        # Mirror the pre-refactor surface for callers still using
        # `service.repository.*` (rewired in this PR; kept defensively
        # to make the bisect window safer).
        self.repository = self.ingestion.repository
