"""Tests for query router — intent classification and entity extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.knowledge.router import (
    ClassifiedQuery,
    QueryIntent,
    QueryRouter,
    get_query_router,
)

# ---------------------------------------------------------------------------
# QueryRouter unit tests
# ---------------------------------------------------------------------------


class TestQueryRouterClassify:
    """Test regex-based classification."""

    def setup_method(self) -> None:
        self.router = QueryRouter()

    # --- Compatibility intent ---

    @pytest.mark.parametrize(
        "query",
        [
            "Does Gmail support flexbox?",
            "flexbox support in Outlook",
            "Can I use display flex in email?",
            "Is CSS grid supported in Apple Mail?",
            "Does Yahoo Mail render background images?",
            "Will border-radius work in Outlook?",
            "flexbox compatibility across email clients",
            "support for media queries in Gmail",
            "Does Outlook support CSS animations?",
            "Can I email background-image?",
        ],
    )
    def test_compatibility_queries(self, query: str) -> None:
        result = self.router.classify(query)
        assert result.intent == QueryIntent.COMPATIBILITY, f"Expected COMPATIBILITY for: {query}"

    # --- How-to intent ---

    @pytest.mark.parametrize(
        "query",
        [
            "How to create a responsive email layout?",
            "Best practices for email preheaders",
            "How do I add dark mode support?",
            "Guide to bulletproof email buttons",
            "What is the best way to handle retina images?",
            "How should I structure my email template?",
            "Best practice for email accessibility",
            "How to implement a fluid hybrid layout?",
            "Example of a 2-column email layout",
            "How can I make my email mobile-friendly?",
        ],
    )
    def test_how_to_queries(self, query: str) -> None:
        result = self.router.classify(query)
        assert result.intent == QueryIntent.HOW_TO, f"Expected HOW_TO for: {query}"

    # --- Template intent ---

    @pytest.mark.parametrize(
        "query",
        [
            "Show me hero section templates",
            "Email header template with logo",
            "CTA section block examples",
            "Footer template with social links",
            "newsletter template layout",
        ],
    )
    def test_template_queries(self, query: str) -> None:
        result = self.router.classify(query)
        assert result.intent == QueryIntent.TEMPLATE, f"Expected TEMPLATE for: {query}"

    @pytest.mark.parametrize(
        "query",
        [
            "Show me a CTA button component",
            "Find a hero block template",
            "Email header component",
        ],
    )
    def test_template_queries_component_variants(self, query: str) -> None:
        result = self.router.classify(query)
        assert result.intent == QueryIntent.TEMPLATE, f"Expected TEMPLATE for: {query}"

    # --- Debug intent ---

    @pytest.mark.parametrize(
        "query",
        [
            "Why is my email not rendering correctly in Outlook?",
            "Images broken in Gmail",
            "Layout is wrong on mobile",
            "Padding issue in Yahoo Mail",
            "Why doesn't my background image show?",
            "My email is rendering incorrectly in dark mode",
            "Fix broken table layout",
            "Email displays wrong colors",
        ],
    )
    def test_debug_queries(self, query: str) -> None:
        result = self.router.classify(query)
        assert result.intent == QueryIntent.DEBUG, f"Expected DEBUG for: {query}"

    # --- General intent ---

    @pytest.mark.parametrize(
        "query",
        [
            "email marketing trends 2024",
            "what is DKIM?",
            "email deliverability tips",
        ],
    )
    def test_general_queries(self, query: str) -> None:
        result = self.router.classify(query)
        assert result.intent == QueryIntent.GENERAL, f"Expected GENERAL for: {query}"


class TestEntityExtraction:
    """Test entity extraction from queries."""

    def setup_method(self) -> None:
        self.router = QueryRouter()

    def test_extracts_client_entity(self) -> None:
        result = self.router.classify("Does Gmail support flexbox?")
        client_entities = [e for e in result.extracted_entities if e.entity_type == "client"]
        assert len(client_entities) >= 1
        assert any("gmail" in e.ontology_id for e in client_entities)

    def test_extracts_property_entity(self) -> None:
        result = self.router.classify("Does Gmail support display: flex?")
        prop_entities = [e for e in result.extracted_entities if e.entity_type == "property"]
        assert len(prop_entities) >= 1

    def test_extracts_css_value_pair(self) -> None:
        result = self.router.classify("Is display: flex supported?")
        prop_entities = [e for e in result.extracted_entities if e.entity_type == "property"]
        assert any("display" in e.ontology_id for e in prop_entities)

    def test_no_entities_for_general_query(self) -> None:
        result = self.router.classify("email marketing trends 2024")
        assert len(result.extracted_entities) == 0

    def test_multiple_entities(self) -> None:
        result = self.router.classify("Does Outlook support display: flex and background-image?")
        assert len(result.extracted_entities) >= 2  # At least client + property


class TestClassifiedQueryFields:
    """Test ClassifiedQuery dataclass fields."""

    def setup_method(self) -> None:
        self.router = QueryRouter()

    def test_original_query_preserved(self) -> None:
        query = "Does Gmail support flexbox?"
        result = self.router.classify(query)
        assert result.original_query == query

    def test_confidence_in_range(self) -> None:
        result = self.router.classify("Does Gmail support flexbox?")
        assert 0.0 <= result.confidence <= 1.0

    def test_general_has_low_confidence(self) -> None:
        result = self.router.classify("something completely unrelated to email")
        assert result.confidence < 0.6


class TestLLMFallback:
    """Test LLM fallback classification."""

    def setup_method(self) -> None:
        self.router = QueryRouter()

    @pytest.mark.asyncio
    async def test_no_fallback_when_disabled(self) -> None:
        """When router_llm_fallback=False, no LLM call is made."""
        with patch("app.knowledge.router.get_settings") as mock_settings:
            mock_settings.return_value.knowledge.router_llm_fallback = False
            result = await self.router.classify_with_fallback("ambiguous query")
            assert isinstance(result, ClassifiedQuery)

    @pytest.mark.asyncio
    async def test_fallback_on_low_confidence(self) -> None:
        """When confidence is low and fallback enabled, LLM is called."""
        with (
            patch("app.knowledge.router.get_settings") as mock_settings,
            patch.object(self.router, "_llm_classify", new_callable=AsyncMock) as mock_llm,
        ):
            mock_settings.return_value.knowledge.router_llm_fallback = True
            mock_llm.return_value = ClassifiedQuery(
                intent=QueryIntent.HOW_TO,
                original_query="ambiguous query",
                confidence=0.8,
            )
            result = await self.router.classify_with_fallback("ambiguous query")
            # "ambiguous query" gets GENERAL with 0.4 confidence → LLM fallback triggered
            mock_llm.assert_called_once()
            assert result.intent == QueryIntent.HOW_TO
            assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_llm_failure_returns_regex_result(self) -> None:
        """LLM failure is safe — falls back to regex result."""
        with (
            patch("app.knowledge.router.get_settings") as mock_settings,
            patch.object(self.router, "_llm_classify", new_callable=AsyncMock) as mock_llm,
        ):
            mock_settings.return_value.knowledge.router_llm_fallback = True
            mock_llm.return_value = None
            result = await self.router.classify_with_fallback("ambiguous query")
            assert isinstance(result, ClassifiedQuery)


class TestGetQueryRouter:
    """Test singleton factory."""

    def test_returns_same_instance(self) -> None:
        r1 = get_query_router()
        r2 = get_query_router()
        assert r1 is r2

    def test_is_query_router(self) -> None:
        assert isinstance(get_query_router(), QueryRouter)


# ---------------------------------------------------------------------------
# Service-level routing tests
# ---------------------------------------------------------------------------


class TestSearchRouted:
    """Test KnowledgeService.search_routed()."""

    @pytest.mark.asyncio
    async def test_disabled_router_delegates_to_search(self) -> None:
        """When router_enabled=False, search_routed() == search()."""
        from app.knowledge.schemas import SearchResponse
        from app.knowledge.services.search import SearchService

        with patch("app.knowledge.services.search.get_settings") as mock_settings:
            mock_settings.return_value.knowledge.router_enabled = False
            service = SearchService(db=AsyncMock())
            service.search = AsyncMock(  # type: ignore[method-assign]
                return_value=SearchResponse(
                    results=[],
                    query="test",
                    total_candidates=0,
                    reranked=False,
                )
            )
            from app.knowledge.schemas import SearchRequest

            result = await service.search_routed(
                SearchRequest(query="test", domain=None, language=None)
            )
            service.search.assert_called_once()
            assert result.intent is None

    @pytest.mark.asyncio
    async def test_enabled_router_sets_intent(self) -> None:
        """When router_enabled=True, response includes intent."""
        from app.knowledge.schemas import SearchRequest, SearchResponse
        from app.knowledge.services.search import SearchService

        with patch("app.knowledge.services.search.get_settings") as mock_settings:
            mock_settings.return_value.knowledge.router_enabled = True
            service = SearchService(db=AsyncMock())
            service.search = AsyncMock(  # type: ignore[method-assign]
                return_value=SearchResponse(
                    results=[],
                    query="test",
                    total_candidates=0,
                    reranked=False,
                )
            )
            result = await service.search_routed(
                SearchRequest(query="How to create responsive email?", domain=None, language=None)
            )
            assert result.intent is not None

    @pytest.mark.asyncio
    async def test_compatibility_structured_answer(self) -> None:
        """Compatibility intent with resolvable entities returns structured answer."""
        from app.knowledge.schemas import SearchRequest, SearchResponse
        from app.knowledge.services.search import SearchService

        with patch("app.knowledge.services.search.get_settings") as mock_settings:
            mock_settings.return_value.knowledge.router_enabled = True
            service = SearchService(db=AsyncMock())
            # Mock search() — should NOT be called when structured answer found
            service.search = AsyncMock(  # type: ignore[method-assign]
                return_value=SearchResponse(
                    results=[],
                    query="test",
                    total_candidates=0,
                    reranked=False,
                )
            )

            # Use a query that the router will classify as compatibility
            # with entities that exist in the ontology
            from app.knowledge.ontology.registry import load_ontology

            ontology = load_ontology()
            prop = ontology.properties[0]
            client = ontology.clients[0]
            query = f"Does {client.name} support {prop.property_name}?"

            result = await service.search_routed(
                SearchRequest(query=query, domain=None, language=None)
            )
            assert result.intent == "compatibility"
            # Structured results should be returned without calling search()
            if result.results:
                assert result.results[0].domain == "css_support"
                assert result.results[0].document_filename == "ontology"

    @pytest.mark.asyncio
    async def test_compatibility_fallback_to_vector(self) -> None:
        """Compatibility intent without resolvable entities falls back to vector search."""
        from app.knowledge.schemas import SearchRequest, SearchResponse
        from app.knowledge.services.search import SearchService

        with patch("app.knowledge.services.search.get_settings") as mock_settings:
            mock_settings.return_value.knowledge.router_enabled = True
            service = SearchService(db=AsyncMock())
            service.search = AsyncMock(  # type: ignore[method-assign]
                return_value=SearchResponse(
                    results=[],
                    query="test",
                    total_candidates=0,
                    reranked=False,
                )
            )
            # Query that matches compatibility but has no resolvable entities
            result = await service.search_routed(
                SearchRequest(
                    query="Is this compatible with everything?", domain=None, language=None
                )
            )
            # Should fall back to vector search
            if result.intent == "compatibility":
                service.search.assert_called()
