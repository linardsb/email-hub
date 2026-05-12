"""Unit tests for app.knowledge.fusion.

Pure-function tests — no DB, no embeddings. The RerankerProvider is a
hand-rolled fake so assertions hit the fusion math, not the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from app.knowledge.fusion import CandidateRow, apply_rerank, rrf_fuse
from app.knowledge.reranker import RerankerProvider, RerankResult


@dataclass
class _StubChunk:
    """Stand-in for DocumentChunk with the attributes fusion needs."""

    id: int
    document_id: int
    content: str
    chunk_index: int
    metadata_json: str | None = None


@dataclass
class _StubDoc:
    """Stand-in for Document with the attributes fusion needs."""

    filename: str
    domain: str
    language: str


def _row(chunk_id: int, content: str = "c", domain: str = "d") -> CandidateRow:
    """Build a candidate row in the shape repository searches return.

    The stubs are duck-typed (only the attributes fusion reads), so we cast at
    the boundary rather than constructing real ORM rows in a unit test.
    """
    chunk = _StubChunk(id=chunk_id, document_id=chunk_id * 10, content=content, chunk_index=0)
    doc = _StubDoc(filename=f"doc{chunk_id}.md", domain=domain, language="en")
    return cast(CandidateRow, (chunk, doc, 0.0))


# ---------------------------------------------------------------------------
# rrf_fuse
# ---------------------------------------------------------------------------


class TestRrfFuse:
    def test_empty_inputs_return_empty(self) -> None:
        ordered, data = rrf_fuse([], [])
        assert ordered == []
        assert data == {}

    def test_vector_only_orders_by_vector_rank(self) -> None:
        rows = [_row(1), _row(2), _row(3)]
        ordered, data = rrf_fuse(rows, [])
        assert ordered == [1, 2, 3]
        assert set(data.keys()) == {1, 2, 3}

    def test_text_only_orders_by_text_rank(self) -> None:
        rows = [_row(7), _row(8)]
        ordered, _data = rrf_fuse([], rows)
        assert ordered == [7, 8]

    def test_overlapping_ids_accumulate_scores(self) -> None:
        # Chunk 1 ranks first in both -> 1/(60+0) + 1/(60+0) = 2/60.
        # Chunk 2 ranks second in both -> 2/61.
        # Chunk 3 ranks third in both -> 2/62.
        vec = [_row(1), _row(2), _row(3)]
        txt = [_row(1), _row(2), _row(3)]
        ordered, _data = rrf_fuse(vec, txt)
        assert ordered == [1, 2, 3]

    def test_disjoint_ids_surfaced_from_both_lists(self) -> None:
        vec = [_row(1), _row(2)]
        txt = [_row(3), _row(4)]
        ordered, data = rrf_fuse(vec, txt)
        assert set(ordered) == {1, 2, 3, 4}
        assert len(data) == 4

    def test_meta_picks_up_filename_domain_language(self) -> None:
        vec = [_row(11, content="hello", domain="best_practices")]
        ordered, data = rrf_fuse(vec, [])
        chunk, filename, domain, language = data[ordered[0]]
        assert chunk.content == "hello"
        assert filename == "doc11.md"
        assert domain == "best_practices"
        assert language == "en"

    def test_custom_k_changes_score_weight(self) -> None:
        # Larger k flattens score differences but ordering is rank-driven, so
        # the head order is unchanged.
        rows = [_row(1), _row(2)]
        ordered_default, _ = rrf_fuse(rows, [])
        ordered_high_k, _ = rrf_fuse(rows, [], k=600)
        assert ordered_default == ordered_high_k == [1, 2]


# ---------------------------------------------------------------------------
# apply_rerank
# ---------------------------------------------------------------------------


class _IdentityReranker:
    """Reranker that keeps input order and scores rank-derived values."""

    async def rerank(self, query: str, documents: list[str], top_k: int = 10) -> list[RerankResult]:
        del query
        return [
            RerankResult(index=i, score=1.0 / (i + 1), content=d)
            for i, d in enumerate(documents[:top_k])
        ]


class _NeverCalledReranker:
    """Reranker whose .rerank() raises if invoked — used to assert short-circuit."""

    async def rerank(self, query: str, documents: list[str], top_k: int = 10) -> list[RerankResult]:
        del query, documents, top_k
        raise AssertionError("reranker should not be called for empty inputs")


@pytest.mark.asyncio
class TestApplyRerank:
    async def test_empty_inputs_short_circuit(self) -> None:
        out = await apply_rerank(
            "anything",
            [],
            {},
            rerank_top_k=10,
            limit=5,
            reranker=cast(RerankerProvider, _NeverCalledReranker()),
        )
        assert out == []

    async def test_results_plumb_through_chunk_metadata(self) -> None:
        ordered, data = rrf_fuse(
            [_row(1, content="alpha", domain="best_practices")],
            [],
        )
        out = await apply_rerank(
            "query",
            ordered,
            data,
            rerank_top_k=10,
            limit=10,
            reranker=cast(RerankerProvider, _IdentityReranker()),
        )
        assert len(out) == 1
        result = out[0]
        assert result.chunk_content == "alpha"
        assert result.document_id == 10
        assert result.document_filename == "doc1.md"
        assert result.domain == "best_practices"
        assert result.language == "en"
        assert result.chunk_index == 0
        assert result.score == pytest.approx(1.0)  # pyright: ignore[reportUnknownMemberType]
        assert result.metadata_json is None

    async def test_top_k_cap_when_ordered_is_shorter(self) -> None:
        # rerank_top_k > ordered length — apply_rerank caps to len(ordered).
        ordered, data = rrf_fuse(
            [_row(1, content="a"), _row(2, content="b")],
            [],
        )
        out = await apply_rerank(
            "q",
            ordered,
            data,
            rerank_top_k=100,
            limit=100,
            reranker=cast(RerankerProvider, _IdentityReranker()),
        )
        assert [r.chunk_content for r in out] == ["a", "b"]

    async def test_top_k_slice_respected(self) -> None:
        # rerank_top_k < ordered length — reranker only sees the top slice.
        seen: list[list[str]] = []

        class _RecordingReranker:
            async def rerank(
                self, query: str, documents: list[str], top_k: int = 10
            ) -> list[RerankResult]:
                del query
                seen.append(list(documents))
                return [
                    RerankResult(index=i, score=1.0, content=d)
                    for i, d in enumerate(documents[:top_k])
                ]

        ordered, data = rrf_fuse(
            [_row(1, content="a"), _row(2, content="b"), _row(3, content="c")],
            [],
        )
        await apply_rerank(
            "q",
            ordered,
            data,
            rerank_top_k=2,
            limit=10,
            reranker=cast(RerankerProvider, _RecordingReranker()),
        )
        assert seen == [["a", "b"]]
