# pyright: reportPrivateUsage=false
"""Hybrid + intent-routed knowledge search.

Wraps the repository's vector and full-text search results through RRF
fusion + reranking (see `app.knowledge.fusion`) and the intent router
(see `app.knowledge.router`).

The module-level imports (`get_settings`, `_providers`) are the canonical
`unittest.mock.patch` targets. See `app/knowledge/_providers.py` for the
singleton-call idiom.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.knowledge import _providers
from app.knowledge.fusion import apply_rerank, rrf_fuse
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import SearchRequest, SearchResponse, SearchResult

if TYPE_CHECKING:
    from app.knowledge.router import ClassifiedQuery

logger = get_logger(__name__)


class SearchService:
    """Hybrid + intent-routed knowledge search."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialise with an async database session."""
        self.db = db
        self.repository = KnowledgeRepository(db)

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Hybrid search: vector + fulltext + RRF fusion + reranking."""
        settings = get_settings()
        start = time.monotonic()
        logger.info(
            "knowledge.search.started",
            query_length=len(request.query),
            domain=request.domain,
            language=request.language,
        )

        query_embedding = (await _providers._get_embedding().embed([request.query]))[0]

        search_limit = settings.knowledge.search_limit
        vector_results = await self.repository.search_vector(
            query_embedding, search_limit, request.domain, request.language
        )
        # Clamp to bound Postgres tsquery cost (F054 — DoS via huge plainto_tsquery input).
        clamped_query = request.query[:1024]
        text_results = await self.repository.search_fulltext(
            clamped_query, search_limit, request.domain, request.language
        )

        ordered_ids, chunk_data = rrf_fuse(vector_results, text_results, k=60)
        total_candidates = len(ordered_ids)

        results = await apply_rerank(
            request.query,
            ordered_ids,
            chunk_data,
            rerank_top_k=settings.reranker.top_k,
            limit=request.limit,
            reranker=_providers._get_reranker(),
        )
        is_reranked = settings.reranker.provider.lower() != "none"

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "knowledge.search.completed",
            result_count=len(results),
            total_candidates=total_candidates,
            reranked=is_reranked,
            duration_ms=duration_ms,
        )

        return SearchResponse(
            results=results,
            query=request.query,
            total_candidates=total_candidates,
            reranked=is_reranked,
        )

    async def search_routed(self, request: SearchRequest) -> SearchResponse:
        """Intent-routed search: classifies query, then routes to optimal path."""
        settings = get_settings()
        if not settings.knowledge.router_enabled:
            return await self.search(request)

        from app.knowledge.router import QueryIntent, get_query_router

        router = get_query_router()
        classified = await router.classify_with_fallback(request.query)

        logger.info(
            "knowledge.search_routed.classified",
            intent=classified.intent.value,
            confidence=classified.confidence,
            entity_count=len(classified.extracted_entities),
        )

        response: SearchResponse
        if classified.intent == QueryIntent.COMPATIBILITY:
            response = await self._search_compatibility(request, classified)
        elif classified.intent == QueryIntent.DEBUG:
            response = await self._search_debug(request, classified)
        elif classified.intent == QueryIntent.TEMPLATE:
            response = await self._search_components(request, classified)
        else:
            response = await self.search(request)

        response.intent = classified.intent.value
        return response

    async def _search_compatibility(
        self, request: SearchRequest, classified: ClassifiedQuery
    ) -> SearchResponse:
        """Compatibility search: structured ontology query, vector fallback."""
        from app.knowledge.ontology.structured_query import OntologyQueryEngine

        engine = OntologyQueryEngine()

        client_ids = [
            e.ontology_id for e in classified.extracted_entities if e.entity_type == "client"
        ]
        property_ids = [
            e.ontology_id for e in classified.extracted_entities if e.entity_type == "property"
        ]

        all_result_dicts: list[dict[str, Any]] = []
        for prop_id in property_ids:
            answer = engine.query_property_support(
                prop_id,
                client_ids=client_ids or None,
            )
            if answer is not None:
                all_result_dicts.extend(engine.format_as_search_results(answer))

        if not property_ids and client_ids:
            for cid in client_ids[:1]:
                unsupported = engine.query_client_limitations(cid)
                if unsupported:
                    client = engine.get_client(cid)
                    client_name = client.name if client else cid
                    lines = [f"- `{p.property_name}`" for p in unsupported[:20]]
                    content = (
                        f"## Unsupported CSS in {client_name}\n\n"
                        f"{len(unsupported)} properties not supported:\n\n" + "\n".join(lines)
                    )
                    if len(unsupported) > 20:
                        content += f"\n\n... and {len(unsupported) - 20} more"
                    all_result_dicts.append(
                        {
                            "chunk_content": content,
                            "document_id": 0,
                            "document_filename": "ontology",
                            "domain": "css_support",
                            "language": "en",
                            "chunk_index": 0,
                            "score": 1.0,
                            "metadata_json": None,
                        }
                    )

        if all_result_dicts:
            results = [SearchResult(**d) for d in all_result_dicts]
            logger.info(
                "knowledge.search_compatibility.structured",
                result_count=len(results),
                property_count=len(property_ids),
                client_count=len(client_ids),
            )
            return SearchResponse(
                results=results,
                query=request.query,
                total_candidates=len(results),
                reranked=False,
            )

        logger.info(
            "knowledge.search_compatibility.fallback",
            reason="no_ontology_match",
        )
        return await self.search(request)

    async def _search_debug(
        self, request: SearchRequest, _classified: ClassifiedQuery
    ) -> SearchResponse:
        """Debug-optimized search: prioritize client_quirks domain."""
        debug_request = SearchRequest(
            query=request.query,
            domain="client_quirks",
            language=request.language,
            limit=request.limit,
        )
        quirks_response = await self.search(debug_request)

        if quirks_response.results and quirks_response.results[0].score > 0.3:
            return quirks_response

        return await self.search(request)

    async def _search_components(
        self, request: SearchRequest, classified: ClassifiedQuery
    ) -> SearchResponse:
        """Template/component search: search Component table, merge with knowledge results."""
        from app.knowledge.component_search import ComponentSearchService

        component_service = ComponentSearchService(self.db)

        category: str | None = None
        for entity in classified.extracted_entities:
            if entity.entity_type == "category":
                category = entity.raw_text
                break

        compatible_with: list[str] | None = None
        client_entities = [
            e.ontology_id for e in classified.extracted_entities if e.entity_type == "client"
        ]
        if client_entities:
            compatible_with = client_entities

        component_results = await component_service.search_components(
            request.query,
            category=category,
            compatible_with=compatible_with,
            limit=5,
        )

        knowledge_request = SearchRequest(
            query=request.query,
            domain="best_practices",
            language=request.language,
            limit=3,
        )
        knowledge_response = await self.search(knowledge_request)

        all_results = component_results + knowledge_response.results

        logger.info(
            "knowledge.search_components.completed",
            component_count=len(component_results),
            knowledge_count=len(knowledge_response.results),
        )

        return SearchResponse(
            results=all_results,
            query=request.query,
            total_candidates=len(all_results),
            reranked=False,
        )
