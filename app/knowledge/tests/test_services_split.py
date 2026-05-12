"""Smoke tests for the F052 KnowledgeService split.

Asserts the four sub-services expose the methods promised by the refactor
plan. A renamed method would slip past pyright but break callers; this test
catches it during CI before runtime.
"""

from __future__ import annotations

from app.knowledge.services.graph import GraphSearchService
from app.knowledge.services.ingestion import IngestionService
from app.knowledge.services.search import SearchService
from app.knowledge.services.tags import TagService

_INGESTION_PUBLIC = {
    "ingest_document",
    "ingest_text",
    "update_document",
    "get_document_content",
    "get_document_file_path",
    "list_domains",
    "get_document",
    "list_documents",
    "delete_document",
}

_SEARCH_PUBLIC = {
    "search",
    "search_routed",
}

_TAG_PUBLIC = {
    "list_tags",
    "create_tag",
    "delete_tag",
    "add_tags_to_document",
    "remove_tag_from_document",
}

_GRAPH_PUBLIC = {
    "search_graph",
    "search_graph_completion",
}


def _has_all(svc: type, names: set[str]) -> set[str]:
    return {n for n in names if hasattr(svc, n)}


class TestServiceSurfaces:
    def test_ingestion_exposes_expected_methods(self) -> None:
        assert _has_all(IngestionService, _INGESTION_PUBLIC) == _INGESTION_PUBLIC

    def test_search_exposes_expected_methods(self) -> None:
        assert _has_all(SearchService, _SEARCH_PUBLIC) == _SEARCH_PUBLIC

    def test_tag_exposes_expected_methods(self) -> None:
        assert _has_all(TagService, _TAG_PUBLIC) == _TAG_PUBLIC

    def test_graph_exposes_expected_methods(self) -> None:
        assert _has_all(GraphSearchService, _GRAPH_PUBLIC) == _GRAPH_PUBLIC


class TestFacadeBackCompat:
    def test_facade_composes_all_four_services(self) -> None:
        from unittest.mock import AsyncMock

        from app.knowledge.service import KnowledgeService

        facade = KnowledgeService(db=AsyncMock())
        assert isinstance(facade.ingestion, IngestionService)
        assert isinstance(facade.search_svc, SearchService)
        assert isinstance(facade.tags, TagService)
        assert isinstance(facade.graph, GraphSearchService)
        # Repository mirror for legacy `service.repository.*` access.
        assert facade.repository is facade.ingestion.repository
