# pyright: reportUnusedFunction=false
"""Lazy provider singletons shared by IngestionService and SearchService.

Lives in its own module so both sub-services dereference the same instance
and so `unittest.mock.patch("app.knowledge._providers._get_embedding")`
intercepts every call — sub-services use `_providers._get_embedding()` via
the module attribute, not `from _providers import _get_embedding`.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.knowledge.embedding import EmbeddingProvider, get_embedding_provider
from app.knowledge.reranker import RerankerProvider, get_reranker_provider

_embedding_provider: EmbeddingProvider | None = None
_reranker_provider: RerankerProvider | None = None


def _get_embedding() -> EmbeddingProvider:
    """Return the process-wide embedding provider singleton."""
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = get_embedding_provider(get_settings())
    return _embedding_provider


def _get_reranker() -> RerankerProvider:
    """Return the process-wide reranker provider singleton."""
    global _reranker_provider
    if _reranker_provider is None:
        _reranker_provider = get_reranker_provider(get_settings())
    return _reranker_provider
