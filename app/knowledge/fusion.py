"""Reciprocal-Rank Fusion + reranking for hybrid knowledge search.

Pure functions extracted from `KnowledgeService.search()` so they can be
unit-tested without a database or live embedding provider.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.knowledge.models import Document, DocumentChunk
from app.knowledge.schemas import SearchResult

if TYPE_CHECKING:
    from app.knowledge.reranker import RerankerProvider

ChunkMeta = tuple[DocumentChunk, str, str, str]
"""(chunk, filename, domain, language) — the per-result metadata RRF carries forward."""

CandidateRow = tuple[DocumentChunk, Document, float]
"""Repository rows returned by both search_vector and search_fulltext."""


def rrf_fuse(
    vector_results: Sequence[CandidateRow],
    text_results: Sequence[CandidateRow],
    *,
    k: int = 60,
) -> tuple[list[int], dict[int, ChunkMeta]]:
    """Reciprocal-Rank Fusion of two ranked candidate lists.

    Args:
        vector_results: Rows from `KnowledgeRepository.search_vector`.
        text_results: Rows from `KnowledgeRepository.search_fulltext`.
        k: RRF constant. Default matches the legacy inline value (60).

    Returns:
        (ordered_chunk_ids, chunk_meta_by_id) — chunk IDs sorted by fused score
        descending, and a lookup table from chunk ID to its `(chunk, filename,
        domain, language)` tuple.
    """
    scores: dict[int, float] = {}
    data: dict[int, ChunkMeta] = {}
    for rank, (chunk, doc, _score) in enumerate(vector_results):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
        data[chunk.id] = (chunk, doc.filename, doc.domain, doc.language)
    for rank, (chunk, doc, _score) in enumerate(text_results):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
        data[chunk.id] = (chunk, doc.filename, doc.domain, doc.language)
    ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return ordered, data


async def apply_rerank(
    query: str,
    ordered_ids: list[int],
    chunk_data: dict[int, ChunkMeta],
    *,
    rerank_top_k: int,
    limit: int,
    reranker: RerankerProvider,
) -> list[SearchResult]:
    """Rerank the top-K fused candidates and materialise `SearchResult` rows."""
    if not ordered_ids:
        return []
    cap = min(rerank_top_k, len(ordered_ids))
    top_ids = ordered_ids[:cap]
    contents = [chunk_data[cid][0].content for cid in top_ids]
    reranked = await reranker.rerank(query, contents, limit)
    results: list[SearchResult] = []
    for rr in reranked:
        cid = top_ids[rr.index]
        chunk, filename, domain, language = chunk_data[cid]
        results.append(
            SearchResult(
                chunk_content=chunk.content,
                document_id=chunk.document_id,
                document_filename=filename,
                domain=domain,
                language=language,
                chunk_index=chunk.chunk_index,
                score=rr.score,
                metadata_json=chunk.metadata_json,
            )
        )
    return results
