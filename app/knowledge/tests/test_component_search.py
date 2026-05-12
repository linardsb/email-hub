"""Tests for ComponentSearchService and _search_components routing."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from app.components.tests.conftest import make_component, make_version
from app.knowledge.component_search import ComponentSearchService
from app.knowledge.schemas import SearchRequest, SearchResponse, SearchResult

# ---------------------------------------------------------------------------
# ComponentSearchService unit tests
# ---------------------------------------------------------------------------


class TestComponentSearchService:
    """Unit tests for ComponentSearchService."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> ComponentSearchService:
        return ComponentSearchService(mock_db)

    def _make_pair(
        self,
        *,
        comp_id: int = 1,
        name: str = "CTA Button",
        slug: str = "cta-button",
        category: str = "action",
        description: str | None = "A call-to-action button",
        html: str = "<a href='#'>Click</a>",
        compatibility: dict[str, str] | None = None,
    ) -> tuple[object, object]:
        comp = make_component(
            id=comp_id, name=name, slug=slug, category=category, description=description
        )
        ver = make_version(component_id=comp_id, html_source=html, compatibility=compatibility)
        return (comp, ver)

    @pytest.mark.anyio
    async def test_search_components_returns_results(self, service: ComponentSearchService) -> None:
        pairs = [
            self._make_pair(comp_id=1, name="Header", slug="header"),
            self._make_pair(comp_id=2, name="Footer", slug="footer"),
        ]
        with patch.object(
            service.repo, "search_with_compatibility", new_callable=AsyncMock, return_value=pairs
        ):
            results = await service.search_components("header")
        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)

    @pytest.mark.anyio
    async def test_search_components_empty_results(self, service: ComponentSearchService) -> None:
        with patch.object(
            service.repo, "search_with_compatibility", new_callable=AsyncMock, return_value=[]
        ):
            results = await service.search_components("nonexistent")
        assert results == []

    def test_format_as_search_results_fields(self) -> None:
        pairs = [self._make_pair(slug="cta-button")]
        results = ComponentSearchService._format_as_search_results(pairs)  # type: ignore[arg-type]

        assert len(results) == 1
        r = results[0]
        assert r.document_id == 0
        assert r.document_filename == "component:cta-button"
        assert r.domain == "components"
        assert r.score == 1.0
        assert r.language == "en"
        assert r.chunk_index == 0
        assert r.metadata_json is None

    def test_format_includes_html_source(self) -> None:
        pairs = [self._make_pair(html="<table><tr><td>CTA</td></tr></table>")]
        results = ComponentSearchService._format_as_search_results(pairs)  # type: ignore[arg-type]

        assert "<table><tr><td>CTA</td></tr></table>" in results[0].chunk_content

    def test_format_includes_compatibility(self) -> None:
        pairs = [self._make_pair(compatibility={"gmail_web": "full", "outlook_2019": "partial"})]
        results = ComponentSearchService._format_as_search_results(pairs)  # type: ignore[arg-type]

        assert "gmail_web: full" in results[0].chunk_content
        assert "outlook_2019: partial" in results[0].chunk_content

    def test_format_handles_no_compatibility(self) -> None:
        pairs = [self._make_pair(compatibility=None)]
        results = ComponentSearchService._format_as_search_results(pairs)  # type: ignore[arg-type]

        assert "Compatibility" not in results[0].chunk_content

    def test_format_includes_description(self) -> None:
        pairs = [self._make_pair(description="A hero banner")]
        results = ComponentSearchService._format_as_search_results(pairs)  # type: ignore[arg-type]

        assert "A hero banner" in results[0].chunk_content

    def test_format_handles_no_description(self) -> None:
        pairs = [self._make_pair(description=None)]
        results = ComponentSearchService._format_as_search_results(pairs)  # type: ignore[arg-type]

        # Should still have name and category
        assert "## Component:" in results[0].chunk_content
        assert "**Category:**" in results[0].chunk_content

    @pytest.mark.anyio
    async def test_search_passes_category_filter(self, service: ComponentSearchService) -> None:
        with patch.object(
            service.repo, "search_with_compatibility", new_callable=AsyncMock, return_value=[]
        ) as mock_search:
            await service.search_components("button", category="action")
        mock_search.assert_called_once_with(
            search="button", category="action", compatible_with=None, limit=5
        )

    @pytest.mark.anyio
    async def test_search_passes_compatible_with_filter(
        self, service: ComponentSearchService
    ) -> None:
        with patch.object(
            service.repo, "search_with_compatibility", new_callable=AsyncMock, return_value=[]
        ) as mock_search:
            await service.search_components("button", compatible_with=["outlook_2019_win"])
        mock_search.assert_called_once_with(
            search="button", category=None, compatible_with=["outlook_2019_win"], limit=5
        )

    @pytest.mark.anyio
    async def test_search_passes_limit(self, service: ComponentSearchService) -> None:
        with patch.object(
            service.repo, "search_with_compatibility", new_callable=AsyncMock, return_value=[]
        ) as mock_search:
            await service.search_components("button", limit=3)
        mock_search.assert_called_once_with(
            search="button", category=None, compatible_with=None, limit=3
        )


# ---------------------------------------------------------------------------
# _search_components integration tests (KnowledgeService)
# ---------------------------------------------------------------------------


class TestSearchComponentsRouting:
    """Integration tests for KnowledgeService._search_components."""

    def _make_classified(
        self,
        *,
        entities: list[tuple[str, str, str]] | None = None,
    ) -> object:
        """Build a ClassifiedQuery with optional entities."""
        from dataclasses import dataclass, field

        @dataclass(frozen=True)
        class FakeEntity:
            entity_type: str
            raw_text: str
            ontology_id: str

        @dataclass(frozen=True)
        class FakeClassified:
            intent: str = "template"
            confidence: float = 0.9
            extracted_entities: list[FakeEntity] = field(
                default_factory=lambda: cast(list[FakeEntity], [])
            )

        ents = [FakeEntity(t, r, o) for t, r, o in (entities or [])]
        return FakeClassified(extracted_entities=ents)

    @pytest.mark.anyio
    async def test_search_components_merges_with_knowledge(self) -> None:
        from app.knowledge.services.search import SearchService

        mock_db = AsyncMock()
        service = SearchService(mock_db)
        classified = self._make_classified()

        comp_results = [
            SearchResult(
                chunk_content="Component A",
                document_id=0,
                document_filename="component:a",
                domain="components",
                language="en",
                chunk_index=0,
                score=1.0,
                metadata_json=None,
            )
        ]
        knowledge_results = [
            SearchResult(
                chunk_content="Knowledge B",
                document_id=1,
                document_filename="doc.pdf",
                domain="best_practices",
                language="en",
                chunk_index=0,
                score=0.8,
                metadata_json=None,
            )
        ]

        with (
            patch(
                "app.knowledge.component_search.ComponentSearchService.search_components",
                new_callable=AsyncMock,
                return_value=comp_results,
            ),
            patch.object(
                service,
                "search",
                new_callable=AsyncMock,
                return_value=SearchResponse(
                    results=knowledge_results,
                    query="test",
                    total_candidates=1,
                    reranked=False,
                ),
            ),
        ):
            request = SearchRequest(query="CTA button", domain=None, language=None, limit=10)
            response = await service._search_components(request, classified)  # type: ignore[arg-type]

        assert len(response.results) == 2
        assert response.results[0].chunk_content == "Component A"
        assert response.results[1].chunk_content == "Knowledge B"

    @pytest.mark.anyio
    async def test_search_components_extracts_client_entities(self) -> None:
        from app.knowledge.services.search import SearchService

        mock_db = AsyncMock()
        service = SearchService(mock_db)
        classified = self._make_classified(
            entities=[("client", "Outlook 2019", "outlook_2019_win")]
        )

        with (
            patch(
                "app.knowledge.component_search.ComponentSearchService.search_components",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_search,
            patch.object(
                service,
                "search",
                new_callable=AsyncMock,
                return_value=SearchResponse(
                    results=[], query="test", total_candidates=0, reranked=False
                ),
            ),
        ):
            request = SearchRequest(
                query="button for Outlook", domain=None, language=None, limit=10
            )
            await service._search_components(request, classified)  # type: ignore[arg-type]

        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args
        assert call_kwargs.kwargs["compatible_with"] == ["outlook_2019_win"]

    @pytest.mark.anyio
    async def test_search_components_extracts_category_entities(self) -> None:
        from app.knowledge.services.search import SearchService

        mock_db = AsyncMock()
        service = SearchService(mock_db)
        classified = self._make_classified(entities=[("category", "cta", "cta")])

        with (
            patch(
                "app.knowledge.component_search.ComponentSearchService.search_components",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_search,
            patch.object(
                service,
                "search",
                new_callable=AsyncMock,
                return_value=SearchResponse(
                    results=[], query="test", total_candidates=0, reranked=False
                ),
            ),
        ):
            request = SearchRequest(query="CTA button", domain=None, language=None, limit=10)
            await service._search_components(request, classified)  # type: ignore[arg-type]

        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args
        assert call_kwargs.kwargs["category"] == "cta"

    @pytest.mark.anyio
    async def test_search_components_no_components_falls_back_to_knowledge(self) -> None:
        from app.knowledge.services.search import SearchService

        mock_db = AsyncMock()
        service = SearchService(mock_db)
        classified = self._make_classified()

        knowledge_results = [
            SearchResult(
                chunk_content="Fallback result",
                document_id=1,
                document_filename="doc.pdf",
                domain="best_practices",
                language="en",
                chunk_index=0,
                score=0.7,
                metadata_json=None,
            )
        ]

        with (
            patch(
                "app.knowledge.component_search.ComponentSearchService.search_components",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                service,
                "search",
                new_callable=AsyncMock,
                return_value=SearchResponse(
                    results=knowledge_results,
                    query="test",
                    total_candidates=1,
                    reranked=False,
                ),
            ),
        ):
            request = SearchRequest(query="some query", domain=None, language=None, limit=10)
            response = await service._search_components(request, classified)  # type: ignore[arg-type]

        assert len(response.results) == 1
        assert response.results[0].chunk_content == "Fallback result"

    @pytest.mark.anyio
    async def test_search_components_no_knowledge_returns_components_only(self) -> None:
        from app.knowledge.services.search import SearchService

        mock_db = AsyncMock()
        service = SearchService(mock_db)
        classified = self._make_classified()

        comp_results = [
            SearchResult(
                chunk_content="Component only",
                document_id=0,
                document_filename="component:hero",
                domain="components",
                language="en",
                chunk_index=0,
                score=1.0,
                metadata_json=None,
            )
        ]

        with (
            patch(
                "app.knowledge.component_search.ComponentSearchService.search_components",
                new_callable=AsyncMock,
                return_value=comp_results,
            ),
            patch.object(
                service,
                "search",
                new_callable=AsyncMock,
                return_value=SearchResponse(
                    results=[], query="test", total_candidates=0, reranked=False
                ),
            ),
        ):
            request = SearchRequest(query="hero block", domain=None, language=None, limit=10)
            response = await service._search_components(request, classified)  # type: ignore[arg-type]

        assert len(response.results) == 1
        assert response.results[0].document_filename == "component:hero"
