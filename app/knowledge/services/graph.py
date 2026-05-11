"""Knowledge-graph search (Cognee-backed)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.graph.protocols import GraphKnowledgeProvider, GraphSearchResult


class GraphSearchService:
    """Graph-knowledge search facade.

    Holds the optional graph provider (Cognee). The `db` session is held for
    constructor symmetry with the other sub-services even though graph search
    does not currently use it.
    """

    def __init__(
        self,
        db: AsyncSession,
        graph_provider: GraphKnowledgeProvider | None = None,
    ) -> None:
        """Initialise with a database session and optional graph provider."""
        self.db = db
        self._graph = graph_provider

    async def search_graph(
        self,
        query: str,
        *,
        dataset_name: str | None = None,
        top_k: int = 10,
    ) -> list[GraphSearchResult]:
        """Search the knowledge graph (delegates to the graph provider)."""
        if self._graph is None:
            from app.knowledge.graph.exceptions import GraphNotEnabledError

            raise GraphNotEnabledError("Graph knowledge provider not configured")
        return await self._graph.search(query, dataset_name=dataset_name, top_k=top_k)

    async def search_graph_completion(
        self,
        query: str,
        *,
        dataset_name: str | None = None,
        system_prompt: str = "",
    ) -> str:
        """Graph-grounded conversational answer."""
        if self._graph is None:
            from app.knowledge.graph.exceptions import GraphNotEnabledError

            raise GraphNotEnabledError("Graph knowledge provider not configured")
        return await self._graph.search_completion(
            query,
            dataset_name=dataset_name,
            system_prompt=system_prompt,
        )
