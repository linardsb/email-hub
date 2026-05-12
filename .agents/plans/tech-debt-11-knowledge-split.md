# Plan: Tech-Debt 11 — Split KnowledgeService + extract RRF/rerank fusion (F052 + F053)

Branch: `refactor/tech-debt-11-knowledge-split`
Gate: `make check-full` + knowledge route tests + RAG eval delta ≤ 3pp.

## Context

`app/knowledge/service.py` is a 1050-LOC `KnowledgeService` god class with **22 methods** spanning four unrelated responsibilities: document ingestion, hybrid search, tag management, and graph knowledge search. The `search()` body inlines a Reciprocal-Rank Fusion (RRF) loop and a reranker pass that are pure functions worth unit-testing in isolation.

This refactor is **behaviour-preserving**. No endpoint shape, repository call, or wire response changes. The aim is single-responsibility services and a small `fusion` module so:

- New tests can target ingestion / search / tags / graph independently.
- Future scope changes (e.g. swapping the reranker, adding a hybrid weight, splitting tags into a feature) land surgically.
- The 1050-LOC file stops collecting cross-domain churn.

Deferred-items grep against `.agents/deferred-items.json`: no entries touch `app/knowledge/service.py` or reference F052/F053 — clean slate.

## Mapping current methods → new homes

`KnowledgeService` (22 methods, including `__init__`):

| Method | Lines | New home |
|---|---|---|
| `__init__` | 76–89 | each service builds its own `KnowledgeRepository(db)` |
| `ingest_document` | 91–293 | `IngestionService` |
| `ingest_text` | 295–370 | `IngestionService` |
| `update_document` | 372–392 | `IngestionService` |
| `get_document_content` | 394–425 | `IngestionService` |
| `get_document_file_path` | 427–445 | `IngestionService` |
| `list_domains` | 447–455 | `IngestionService` |
| `get_document` | 735–753 | `IngestionService` |
| `list_documents` | 755–798 | `IngestionService` |
| `delete_document` | 800–824 | `IngestionService` |
| `_auto_tag_document` | 965–1050 | `IngestionService` (private) |
| `search` | 457–547 | `SearchService` |
| `search_routed` | 549–581 | `SearchService` |
| `_search_compatibility` | 583–661 | `SearchService` |
| `_search_debug` | 663–678 | `SearchService` |
| `_search_components` | 680–733 | `SearchService` |
| `list_tags` | 830–838 | `TagService` |
| `create_tag` | 840–857 | `TagService` |
| `delete_tag` | 859–871 | `TagService` |
| `add_tags_to_document` | 873–898 | `TagService` |
| `remove_tag_from_document` | 900–923 | `TagService` |
| `search_graph` | 929–941 | `GraphSearchService` |
| `search_graph_completion` | 943–959 | `GraphSearchService` |

Two methods needs special routing:

- `TagService.add_tags_to_document` / `remove_tag_from_document` currently end with `return await self.get_document(...)` (lines 898, 923). After split, `TagService` is constructed with the same `db` session and instantiates `IngestionService(db)` lazily for that response shape — keeps the route contract identical without circular imports.
- `IngestionService.ingest_document` triggers `_auto_tag_document` (writes tags via repository). The repository is the only collaborator, so this stays self-contained.

## Files to Create

- `app/knowledge/fusion.py` — `rrf_fuse(...)`, `apply_rerank(...)` extracted from `KnowledgeService.search` body.
- `app/knowledge/_providers.py` — module-level `_get_embedding()` / `_get_reranker()` singletons (moved out of `service.py` so the four sub-services share one canonical home; the legacy patch target `app.knowledge.service._get_embedding` is migrated, not preserved — see Step 7).
- `app/knowledge/services/__init__.py` — re-exports the four new services.
- `app/knowledge/services/ingestion.py` — `IngestionService`.
- `app/knowledge/services/search.py` — `SearchService`.
- `app/knowledge/services/tags.py` — `TagService`.
- `app/knowledge/services/graph.py` — `GraphSearchService`.
- `app/knowledge/tests/test_fusion.py` — unit tests for `rrf_fuse` (rank ordering, score sum, missing IDs) and `apply_rerank` (no-op when empty, score plumbed through).
- `app/knowledge/tests/test_services_split.py` — smoke tests that each service exposes the expected methods and that an end-to-end search round-trip via `SearchService` matches a captured `KnowledgeService.search` baseline (run before the refactor and pin into the fixture file).

## Files to Modify

### Source modules
- `app/knowledge/service.py` — collapse to a back-compat façade. Construct the four sub-services from a single `db` (plus optional `graph_provider`); expose them via `self.ingestion` / `self.search_svc` / `self.tags` / `self.graph` and forward `self.repository = self.ingestion.repository`. **No `*args/**kwargs` pass-through methods** (would fail pyright strict). Target ≤ 80 LOC. Continues to live at the legacy import path so `patch("app.knowledge.service.KnowledgeService")` keeps resolving in callers that still hold the class (templates/upload defensive patches, ontology change-detector test, mcp tests).
- `app/knowledge/routes.py` — replace the single `get_service` dependency with four targeted dependencies (`get_ingestion_service`, `get_search_service`, `get_tag_service`). Each endpoint picks the service it needs. The graph endpoint instantiates `GraphSearchService` inline as today.
- `app/knowledge/seed.py` — switch to `IngestionService` + `TagService`. Replace `service.repository.list_documents(...)` (line 38) with `ingestion.repository.list_documents(...)`; replace `service.repository.get_or_create_tag(tag_name)` (line 57) with `ingestion.repository.get_or_create_tag(...)`; replace `service.ingest_document(...)` (line 76) with `ingestion.ingest_document(...)`; replace `service.add_tags_to_document(...)` (line 87) with `tags.add_tags_to_document(...)`. Instantiate both services at line 238 (`ingestion = IngestionService(db); tags = TagService(db)`).
- `app/mcp/tools/knowledge.py:43-51` — `from app.knowledge.services.search import SearchService`; construct `SearchService(db)`.
- `app/mcp/tools/agents.py:457-462` — `from app.knowledge.services.search import SearchService`; construct `SearchService(db)`.
- `app/ai/agents/knowledge/service.py:20,55` — change `from app.knowledge.service import KnowledgeService as RAGService` → `from app.knowledge.services.search import SearchService as RAGService` (only `search_routed` is called).
- `app/qa_engine/chaos/knowledge_writer.py:13,48` — switch to `IngestionService`; only `ingest_text` is called.
- `app/knowledge/ontology/change_poller.py:78-81` — switch to `IngestionService` (poller calls only `ingest_text` on the constructed service in `_store_changes_as_knowledge`).
- `app/ai/agents/evals/runner.py:441,451` — replace `from app.knowledge.service import KnowledgeService as RAGService` with `from app.knowledge.services.search import SearchService as RAGService`. Only `search_routed` is invoked via `KnowledgeAgentService.process`.
- `app/templates/upload/knowledge_injector.py:15,56,97` — change the type annotation and constructor parameter from `KnowledgeService` to `IngestionService`; the only method called is `self.knowledge.ingest_document(...)`. Update the corresponding callsite that builds the injector (search for `KnowledgeInjector(` to find it).

### Tests
- `app/knowledge/tests/test_component_search.py` — five `KnowledgeService(mock_db)` constructions become `SearchService(mock_db)` (lines 183/186, 241/244, 275/278, 305/308, 350/353). Only `_search_components` is exercised; the `# type: ignore[arg-type]` comments stay.
- `app/knowledge/tests/test_service_multi_rep.py` — three constructions (lines 96/99, 178/181, 246/249) become `IngestionService(db)`. Repoint patches:
  - `patch("app.knowledge.service.get_settings")` (lines 18, 32) → `patch("app.knowledge.services.ingestion.get_settings")`.
  - `patch("app.knowledge.service.chunking_html.is_html_content")` (lines 82, 165, 229) → `patch("app.knowledge.services.ingestion.chunking_html.is_html_content")`.
  - `patch("app.knowledge.service.chunking_html.chunk_html")` (lines 83, 166) → `patch("app.knowledge.services.ingestion.chunking_html.chunk_html")`.
  - `patch("app.knowledge.service.processing.extract_text")` (lines 85, 168, 232) → `patch("app.knowledge.services.ingestion.processing.extract_text")`.
  - `patch("app.knowledge.service.chunking.chunk_text")` (line 230) → `patch("app.knowledge.services.ingestion.chunking.chunk_text")`.
  - `patch("app.knowledge.service._get_embedding")` (lines 89, 172, 236) → `patch("app.knowledge._providers._get_embedding")`. (`_get_embedding` moves into `app/knowledge/_providers.py` — see Step 7.)
- `app/knowledge/tests/test_router.py` — four constructions (lines 252/256, 277/281, 299/303, 336/340) become `SearchService(db=AsyncMock())`. Repoint the four `patch("app.knowledge.service.get_settings")` calls (lines 254, 279, 301, 338) to `patch("app.knowledge.services.search.get_settings")`. The `service.search = AsyncMock(...)` monkey-patches stay (still set on the `SearchService` instance).
- `app/mcp/tests/test_tool_execution.py:230,249` — repoint `patch("app.knowledge.service.KnowledgeService")` → `patch("app.knowledge.services.search.SearchService")`. **Patch at the source module, not the importing module:** `mcp/tools/knowledge.py:43` does `from app.knowledge.services.search import SearchService` *inside* the tool function body, so `SearchService` is never bound on `mcp.tools.knowledge` and patching there is a silent no-op.
- `app/mcp/tests/test_agent_tools.py:440` — repoint to `patch("app.knowledge.services.search.SearchService")`. Same deferred-import rationale (`mcp/tools/agents.py:457`).
- `app/knowledge/ontology/tests/test_change_detector.py:326` — repoint to `patch("app.knowledge.services.ingestion.IngestionService", return_value=mock_service)`. `change_poller.py:78` does the import inside `_store_changes_as_knowledge`, so the source module is the only valid patch site.
- `app/templates/upload/tests/test_service.py:229` — repoint `patch("app.knowledge.service.KnowledgeService")` → `patch("app.knowledge.service.IngestionService")` (or delete — the defensive patch is redundant since `KnowledgeInjector` itself is mocked at line 230, but updating keeps intent explicit).

No schemas, no models, no Alembic migrations, no API surface change.

## Step 1 — Create `app/knowledge/fusion.py` (F053)

Pure-function module. No imports from `service.py`. Lives next to `repository.py` / `reranker.py`.

Signature target:

```python
# app/knowledge/fusion.py
from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.knowledge.models import Document, DocumentChunk
from app.knowledge.schemas import SearchResult

if TYPE_CHECKING:
    from app.knowledge.reranker import RerankerProvider

ChunkMeta = tuple[DocumentChunk, str, str, str]  # chunk, filename, domain, language
CandidateRow = tuple[DocumentChunk, Document, float]


def rrf_fuse(
    vector_results: Sequence[CandidateRow],
    text_results: Sequence[CandidateRow],
    *,
    k: int = 60,
) -> tuple[list[int], dict[int, ChunkMeta]]:
    """Reciprocal-Rank Fusion of two ranked candidate lists.

    Returns (ordered_chunk_ids, chunk_meta_by_id).
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
    reranker: "RerankerProvider",
) -> list[SearchResult]:
    """Run reranker on top-K fused candidates → materialised `SearchResult` list."""
    if not ordered_ids:
        return []
    cap = min(rerank_top_k, len(ordered_ids))
    top_ids = ordered_ids[:cap]
    contents = [chunk_data[cid][0].content for cid in top_ids]
    reranked = await reranker.rerank(query, contents, limit)
    out: list[SearchResult] = []
    for rr in reranked:
        cid = top_ids[rr.index]
        chunk, filename, domain, language = chunk_data[cid]
        out.append(
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
    return out
```

Notes:

- The current `search()` body at `app/knowledge/service.py:489-512` is the verbatim source for both helpers — same `rrf_k = 60`, same sort, same rerank slice, same `SearchResult` construction.
- No behaviour change: same `rrf_k`, same dict-of-scores accumulation order, same `top_ids` slice, same `min(top_k, len(ordered))` cap.
- `apply_rerank` accepts an injected `RerankerProvider` so unit tests can supply a fake without touching the module-level singleton.

## Step 2 — Create the four service modules

Layout under `app/knowledge/services/`:

```
app/knowledge/services/
  __init__.py          # re-exports
  ingestion.py         # IngestionService
  search.py            # SearchService
  tags.py              # TagService
  graph.py             # GraphSearchService
```

### `__init__.py`

```python
"""Knowledge service decomposition (F052).

The original `KnowledgeService` god class is now a façade in
`app/knowledge/service.py` that composes these four single-responsibility
services. New code should import the specific service it needs.
"""
from app.knowledge.services.graph import GraphSearchService
from app.knowledge.services.ingestion import IngestionService
from app.knowledge.services.search import SearchService
from app.knowledge.services.tags import TagService

__all__ = [
    "GraphSearchService",
    "IngestionService",
    "SearchService",
    "TagService",
]
```

### `IngestionService` (`ingestion.py`)

- Constructor: `__init__(self, db: AsyncSession) -> None` → builds `self.repository = KnowledgeRepository(db)`.
- Methods (move verbatim from `service.py`, no logic edits):
  - `ingest_document`, `ingest_text`, `update_document`, `get_document_content`, `get_document_file_path`, `list_domains`, `get_document`, `list_documents`, `delete_document`.
  - Private: `_auto_tag_document` — internal-only, called from `ingest_document` and `ingest_text` via `await self._auto_tag_document(doc.id, text)`.
- Module-level imports (must match the names tests patch — see Step 7): `from app.knowledge import chunking, chunking_html, processing`; `from app.core.config import get_settings`; `from app.knowledge import _providers`. **Do not** do `from app.knowledge._providers import _get_embedding` — that creates a local name binding that `patch("app.knowledge._providers._get_embedding")` cannot reach. Call as `_providers._get_embedding()` at every use site so the patch resolves through the module attribute. Test patches under `app.knowledge.services.ingestion.{get_settings,chunking,chunking_html,processing}` target the other module-level bindings unchanged.

### `SearchService` (`search.py`)

- Constructor: `__init__(self, db: AsyncSession) -> None` → builds `self.db = db; self.repository = KnowledgeRepository(db)`.
- Module-level imports (patch targets — see Step 7): `from app.core.config import get_settings`; `from app.knowledge import _providers`. **Same idiom as `IngestionService`:** call `_providers._get_embedding()` / `_providers._get_reranker()` via the module attribute so `patch("app.knowledge._providers._get_embedding")` resolves. Tests reach `get_settings` via `app.knowledge.services.search.get_settings`.
- Methods: `search`, `search_routed`, `_search_compatibility`, `_search_debug`, `_search_components` — moved verbatim **except** that `search()` swaps its inline RRF + rerank block (lines 489–531 in the current file) for calls into `app/knowledge/fusion.py`:

```python
# inside SearchService.search()
from app.knowledge.fusion import apply_rerank, rrf_fuse

settings = get_settings()
start = time.monotonic()
logger.info("knowledge.search.started", query_length=len(request.query),
            domain=request.domain, language=request.language)

query_embedding = (await _get_embedding().embed([request.query]))[0]
search_limit = settings.knowledge.search_limit
vector_results = await self.repository.search_vector(
    query_embedding, search_limit, request.domain, request.language
)
clamped_query = request.query[:1024]  # F054 — tsquery DoS guard, preserved
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
    reranker=_get_reranker(),
)
is_reranked = settings.reranker.provider.lower() != "none"

duration_ms = int((time.monotonic() - start) * 1000)
logger.info("knowledge.search.completed", result_count=len(results),
            total_candidates=total_candidates, reranked=is_reranked,
            duration_ms=duration_ms)
return SearchResponse(results=results, query=request.query,
                      total_candidates=total_candidates, reranked=is_reranked)
```

- `_search_components` keeps using `ComponentSearchService(self.db)` exactly as today.
- `_search_compatibility` and `_search_debug` keep their existing `await self.search(...)` fallbacks (now `self.search` on `SearchService`).

### `TagService` (`tags.py`)

- Constructor: `__init__(self, db: AsyncSession) -> None` → `self.db = db; self.repository = KnowledgeRepository(db)`.
- Methods: `list_tags`, `create_tag`, `delete_tag`, `add_tags_to_document`, `remove_tag_from_document` — moved verbatim, except that the trailing `return await self.get_document(...)` in `add_tags_to_document` and `remove_tag_from_document` is rewritten to use the same repository call chain instead of importing `IngestionService`:

```python
# replace:  return await self.get_document(document_id)
doc = await self.repository.get_document(document_id)
if not doc:
    raise DocumentNotFoundError(f"Document {document_id} not found")
doc_resp = DocumentResponse.model_validate(doc)
doc_resp.tags = [
    TagResponse.model_validate(t)
    for t in await self.repository.get_tags_for_document(document_id)
]
return doc_resp
```

This keeps `TagService` independent of `IngestionService` while preserving the exact response. The duplication is 4 lines — well below the "rule of three" threshold for an extraction.

### `GraphSearchService` (`graph.py`)

- Constructor: `__init__(self, db: AsyncSession, graph_provider: GraphKnowledgeProvider | None = None) -> None` → keeps both the session (unused but symmetric) and the optional graph provider.
- Methods: `search_graph`, `search_graph_completion` — moved verbatim. They depend only on `self._graph`; `db` is held to keep dependency-injection signatures uniform across the four services.

## Step 3 — Update `app/knowledge/routes.py`

Replace the single `get_service` dependency with four targeted ones:

```python
def get_ingestion_service(db: AsyncSession = Depends(get_scoped_db)) -> IngestionService:
    return IngestionService(db)

def get_search_service(db: AsyncSession = Depends(get_scoped_db)) -> SearchService:
    return SearchService(db)

def get_tag_service(db: AsyncSession = Depends(get_scoped_db)) -> TagService:
    return TagService(db)
```

Endpoint rewires (line numbers from current `routes.py`):

| Line | Endpoint | New service param |
|---|---|---|
| 86 | `POST /documents` | `service: IngestionService = Depends(get_ingestion_service)` |
| 155 | `GET /documents` | `IngestionService` |
| 170 | `GET /documents/{id}` | `IngestionService` |
| 187 | `PATCH /documents/{id}` | `IngestionService` |
| 200 | `GET /documents/{id}/download` | `IngestionService` |
| 226 | `GET /documents/{id}/content` | `IngestionService` |
| 239 | `DELETE /documents/{id}` | `IngestionService` |
| 251 | `GET /domains` | `IngestionService` |
| 268 | `GET /tags` | `TagService` |
| 282 | `POST /tags` | `TagService` |
| 297 | `DELETE /tags/{id}` | `TagService` |
| 314 | `POST /documents/{id}/tags` | `TagService` |
| 331 | `DELETE /documents/{id}/tags/{tag_id}` | `TagService` |
| 341 | `POST /search` | `SearchService` |
| 354 | `POST /search/routed` | `SearchService` |
| 384 | `POST /graph/search` | inline `GraphSearchService(db=db, graph_provider=_get_graph_provider())` — keeps the existing `_get_graph_provider()` factory wiring at line 370 |

Drop the legacy `def get_service(...)` factory once nothing imports it.

## Step 4 — Update external consumers

1. **`app/mcp/tools/knowledge.py:47-51`**

```python
service = SearchService(db)
if not request.use_router:
    results = await service.search(request)
else:
    results = await service.search_routed(request)
```

2. **`app/mcp/tools/agents.py:462`**: `rag_service = SearchService(db)` (only `search_routed` is called).

3. **`app/ai/agents/knowledge/service.py:55`**: change the parameter type from `KnowledgeService` to `SearchService`; `search_routed` is the only method touched.

4. **`app/qa_engine/chaos/knowledge_writer.py:48,84`**: `self._service = IngestionService(db)` (only `ingest_text` is called).

5. **`app/knowledge/seed.py`**:

   - Line 38: replace `service.repository.list_documents(...)` with a local `KnowledgeRepository(db).list_documents(...)` call — the seeder is iterating documents at the repository layer, no service helper is needed.
   - Line 76: `await ingestion.ingest_document(...)`.
   - Line 87: `await tags.add_tags_to_document(...)`.
   - Line 238: instantiate both services side-by-side:
     ```python
     ingestion = IngestionService(db)
     tags = TagService(db)
     ```
   - Pass each by name where used.

6. **Tests**

   - `app/knowledge/tests/test_component_search.py` lines 186, 244, 278, 308, 353: rename `KnowledgeService(mock_db)` → `SearchService(mock_db)`. Only `_search_components` is exercised.
   - `app/knowledge/tests/test_service_multi_rep.py`: verify which methods it touches; almost certainly `ingest_*` → switch to `IngestionService`. If any test imports `KnowledgeService` purely as a smoke-import, repoint at `IngestionService` or `SearchService` based on the method called.

## Step 5 — `app/knowledge/service.py` becomes a thin façade

Trim `service.py` to a back-compat shim. Target ≤ 60 LOC, no pyright-fragile pass-through methods:

```python
"""Knowledge service façade.

The original 1050-LOC god class has been split into four single-responsibility
services under `app/knowledge/services/`. This module keeps a slim composite
so out-of-tree callers can still hold one handle and so existing
`patch("app.knowledge.service.KnowledgeService")` test scaffolds keep
resolving the class name.
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
        self.db = db
        self.ingestion = IngestionService(db)
        self.search_svc = SearchService(db)
        self.tags = TagService(db)
        self.graph = GraphSearchService(db, graph_provider=graph_provider)
        # Mirror the pre-refactor surface for the few callers still grabbing
        # `service.repository.*` directly (rewired in this PR; kept defensively
        # to make the bisect window safer).
        self.repository = self.ingestion.repository
```

No `*args/**kwargs` pass-through methods (pyright strict rejects them without explicit annotations, and the seeder is rewired to use the explicit sub-services in Step 4). The façade is purely a composite holder.

## Step 7 — Singleton location & test-patch migration

The current `service.py` hosts two module-level singletons (`_get_embedding`, `_get_reranker`) and re-imports `chunking`, `chunking_html`, `processing`, `get_settings` at the same namespace. Existing tests patch all of these via `app.knowledge.service.<name>` paths.

After the split there is no longer a single canonical caller for the singletons (both `IngestionService` and `SearchService` use them). Two viable patterns:

**Chosen — Path B: move + repoint patches.**

- Extract the singletons into `app/knowledge/_providers.py`:

  ```python
  # app/knowledge/_providers.py
  """Lazy provider singletons used by IngestionService and SearchService."""
  from __future__ import annotations

  from app.core.config import get_settings
  from app.knowledge.embedding import EmbeddingProvider, get_embedding_provider
  from app.knowledge.reranker import RerankerProvider, get_reranker_provider

  _embedding_provider: EmbeddingProvider | None = None
  _reranker_provider: RerankerProvider | None = None


  def _get_embedding() -> EmbeddingProvider:
      global _embedding_provider
      if _embedding_provider is None:
          _embedding_provider = get_embedding_provider(get_settings())
      return _embedding_provider


  def _get_reranker() -> RerankerProvider:
      global _reranker_provider
      if _reranker_provider is None:
          _reranker_provider = get_reranker_provider(get_settings())
      return _reranker_provider
  ```

- `IngestionService` and `SearchService` import the **module**, not the names: `from app.knowledge import _providers`. Every call site uses module-attribute access — `await _providers._get_embedding().embed([...])`, `_providers._get_reranker()`. This is the canonical idiom for `unittest.mock.patch`: the patch sets a new attribute on the `_providers` module object, and the next `_providers._get_embedding` lookup picks it up. A `from _providers import _get_embedding` style would create a separate name binding inside the service module that `patch("app.knowledge._providers._get_embedding")` cannot reach.

- Repoint every existing patch (see test list in "Files to Modify"). The mapping is mechanical:
  - `app.knowledge.service.get_settings` → `app.knowledge.services.ingestion.get_settings` (or `…services.search.get_settings`, picked per the test's intent).
  - `app.knowledge.service.chunking_html.*`, `app.knowledge.service.chunking.*`, `app.knowledge.service.processing.*` → `app.knowledge.services.ingestion.<same>` (only `IngestionService` calls into the chunking modules).
  - `app.knowledge.service._get_embedding` → `app.knowledge._providers._get_embedding`.
  - `app.knowledge.service.KnowledgeService` → resolved per consumer (see test patch list in "Files to Modify").

**Why not Path A (keep symbols re-exported from `service.py`):** A re-export is a separate name binding; patching `service._get_embedding` would not mutate the binding that `services/ingestion.py` actually calls. Tests would silently no-op. The Path B churn (~14 patch path strings across 5 test files) is one-shot mechanical and gives an honest test surface.

## Step 8 — Tests

### `app/knowledge/tests/test_fusion.py` (new)

Unit-test `rrf_fuse` and `apply_rerank` end-to-end without DB or embeddings:

- **`rrf_fuse` cases**
  - Empty inputs → returns `([], {})`.
  - Vector-only input → ids ordered by their vector rank.
  - Text-only input → ids ordered by their text rank.
  - Overlapping chunk IDs accumulate scores (sum of `1/(60+rank)` from both lists).
  - Unique IDs from both lists are surfaced even if not in the other ranker.
  - Tie order is stable (Python sort, no key drift).
- **`apply_rerank` cases**
  - `ordered_ids=[]` short-circuits to `[]` without calling the reranker.
  - Reranker called with the top-K chunk **contents** in fused order.
  - Resulting `SearchResult` fields plumb chunk metadata correctly (domain/language/filename/index/score/metadata_json).
  - `min(rerank_top_k, len(ordered_ids))` cap honoured when `ordered_ids` is shorter than `rerank_top_k`.

Use a tiny in-memory `RerankerProvider` fake; build `DocumentChunk` / `Document` rows with the existing factory pattern from `app/knowledge/tests/conftest.py` (do not fabricate ORM rows by hand).

### `app/knowledge/tests/test_services_split.py` (new)

- **Smoke (compile-time):** import each of `IngestionService`, `SearchService`, `TagService`, `GraphSearchService`; assert the method-name set matches the migration table above. Catches accidental renames during the move.
- **Behaviour parity:** for one representative `SearchRequest` against a seeded fixture, run `SearchService.search()` and assert `(total_candidates, [r.document_id for r in results], [round(r.score, 6) for r in results])` matches a snapshot captured **before** the refactor (commit the snapshot JSON into the repo under `app/knowledge/tests/fixtures/search_parity_snapshot.json`).

  Capture procedure (run on `main` before branching):
  ```bash
  pytest app/knowledge/tests/test_service_multi_rep.py -k "parity_capture" -s
  ```
  A helper test under `@pytest.mark.skip(reason="capture only")` writes the snapshot file. Unskip locally, run once, commit the JSON, re-skip. This is the deterministic guard for the "RAG eval delta ≤ 3pp" gate.

### Existing tests to touch

The full list of constructor + patch repoints is in the "Files to Modify › Tests" section. Quick double-check grep to run after the edits land — every match should be a *new* patch path, not a stale `app.knowledge.service.*`:

```bash
grep -rn -E "patch\(\"app\.knowledge\.service\.(get_settings|_get_embedding|_get_reranker|chunking|chunking_html|processing)|KnowledgeService\(\b" app cms
```

Only the legacy `KnowledgeService` class patches in `mcp/tests/test_tool_execution.py`, `mcp/tests/test_agent_tools.py`, `ontology/tests/test_change_detector.py`, `templates/upload/tests/test_service.py` should appear, and each is repointed per the table above.

## Security Checklist

This refactor adds no new endpoints, no new HTTP surface, no new input parsing. The existing route-level guards are preserved verbatim by the rewires in Step 3:

- Auth — every endpoint keeps its existing `Depends(get_current_user)` or `Depends(require_role(...))`.
- Rate limiting — every `@limiter.limit("...")` decorator is preserved in place.
- Input validation — Pydantic `SearchRequest` / `DocumentTagRequest` / `TagCreate` / `DocumentUpdate` unchanged.
- Tsquery DoS guard — `clamped_query = request.query[:1024]` (F054) is retained in `SearchService.search` (see Step 2 code block).
- Error sanitisation — `DocumentNotFoundError`, `DuplicateTagError`, `TagNotFoundError`, `ProcessingError`, `GraphNotEnabledError` keep their exception types; `app/core/exceptions.py:setup_exception_handlers` still maps them via `AppError`.
- SQL injection — repository calls are unchanged; no new raw SQL.
- File-system — `delete_document` still uses `shutil.rmtree(file_dir, ignore_errors=True)` against `Path(doc.file_path).parent`; `file_path` is a server-controlled path written at ingest time.

## Verification

- [ ] `make check-full` passes (ruff 26-rule lint, mypy strict, pyright strict, backend tests, frontend lint+format+types+tests, security-check, golden-conformance, flag audit, migration lint).
- [ ] `pytest app/knowledge/tests -x` green (route tests + new fusion + parity snapshot).
- [ ] `pytest app/knowledge/tests/test_fusion.py -x` exercises every case from Step 6.
- [ ] Parity snapshot matches: `pytest app/knowledge/tests/test_services_split.py::test_search_parity -x`.
- [ ] RAG eval gate: `make eval-check` shows ≤ 3pp absolute delta on Knowledge agent TPR/TNR vs. the pre-refactor calibration (per-agent regression tolerance is 3pp via `AGENT_REGRESSION_TOLERANCE`).
- [ ] `grep -rn "from app.knowledge.service import KnowledgeService" app cms scripts tests` — should be empty after this PR (the seeder now imports `IngestionService` + `TagService`; tests construct the specific sub-service they exercise). Defensive class-level patches in `mcp/tests`, `ontology/tests`, `templates/upload/tests` reference the symbol by string and don't trigger this grep.
- [ ] `git diff app/knowledge/service.py | wc -l` — façade is ≤ 80 LOC.
- [ ] No new endpoint added; OpenAPI snapshot (if checked) is byte-identical.

## Out of scope (defer)

- Deleting the façade entirely (`app/knowledge/service.py`) — track in a follow-up once `seed.py`-style callers all migrate.
- Splitting `KnowledgeRepository` (523 LOC) — separate session.
- Renaming the `services/__init__.py` re-exports into the package root — current layout (`app/knowledge/services/`) keeps existing `app/knowledge/*` modules (`chunking`, `processing`, `embedding`, `reranker`, `router`, `repository`) discoverable side-by-side.

## Branch + commit cadence

```
refactor/tech-debt-11-knowledge-split

c1  fusion: extract rrf_fuse + apply_rerank into app/knowledge/fusion.py
    (verbatim from service.search; behaviour-preserving)
c2  services: introduce IngestionService / SearchService / TagService / GraphSearchService
    (no consumer rewires yet — façade still delegates to legacy paths)
c3  routes: switch app/knowledge/routes.py to per-endpoint service dependencies
c4  consumers: mcp/tools, ai/agents/knowledge, qa_engine/chaos, seed migrate off KnowledgeService
c5  service: shrink app/knowledge/service.py to ≤ 60 LOC façade + extract _providers.py
c6  tests: repoint patch targets (test_router.py, test_service_multi_rep.py, mcp/tests/*, ontology/tests/*, templates/upload/tests/*)
c7  tests: add test_fusion.py + test_services_split.py + parity snapshot
```

Each commit is independently `make test` green so a bisect lands on a real regression rather than a transient.
