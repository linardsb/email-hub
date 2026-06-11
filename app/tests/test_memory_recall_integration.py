# pyright: reportPrivateUsage=false
"""Memory recall integration regression (tech-debt-03-memory-recall-dead-on-read).

The per-tenant scoping fix (F001/F002/F003) made
`MemoryRepository.similarity_search` call `scoped_access(self.db)`
unconditionally. Every agent/background recall opened a plain
`get_db_context()` session, which carries no `tenant_access` stamp, so
`scoped_access` raised `RuntimeError`, each caller's failure-safe
`except` swallowed it, and `recall()` returned `[]` — silently. The fix
swaps those callers to `get_system_db_context()` (system sentinel).

This is the FIRST integration test under `app/memory`-adjacent code that
exercises the *real* `scoped_access` path. It must, because the bug is
invisible to mocks: the root `conftest.py` autouse fixture patches
`scoped_access` to a system constant for unit tests. The
``tenant_isolation`` marker opts OUT of that bypass (see
`conftest.py::_bypass_scoped_access_in_unit_tests`) so the genuine
guard runs here — without it these tests would pass even on the broken
code.

Harness: the `db` fixture (`app/tests/conftest.py`) provides an
alembic-upgraded, TRUNCATE-isolated `AsyncSession`. `get_system_db_context`
opens its own `AsyncSessionLocal` against the same test DB
(`DATABASE__URL == TEST_DATABASE__URL`, asserted by the harness).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.blueprints.engine import BlueprintEngine
from app.core.database import get_db_context
from app.core.scoped_db import get_system_db_context
from app.knowledge.embedding import EmbeddingProvider
from app.memory.repository import MemoryRepository
from app.memory.schemas import MemoryCreate
from app.memory.service import MemoryService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.tenant_isolation,
    # The `db` fixture is session-scoped (loop_scope="session"); async tests
    # must share that loop or asyncpg raises "Future attached to a different
    # loop". Mirrors app/tests/test_tenant_isolation.py.
    pytest.mark.asyncio(loop_scope="session"),
]


class _ConstantEmbedder:
    """Deterministic 1024-dim embedder: every text maps to the same vector.

    A constant non-zero vector makes pgvector cosine distance well-defined
    (0.0) and identical for seed and query, so recall is deterministic
    regardless of text. Dim 1024 matches the `Vector(1024)` column.
    """

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]

    @property
    def dimension(self) -> int:
        return 1024


@pytest.fixture
def fake_embedder() -> EmbeddingProvider:
    return _ConstantEmbedder()


async def test_system_session_recall_returns_seeded_memory(
    db: AsyncSession,
    fake_embedder: EmbeddingProvider,
) -> None:
    """A `get_system_db_context()` session recalls a stored memory (the fix).

    Seeding uses `project_id=None` so `store()` skips its `scoped_access`
    access check; recall goes through the production opener under test.
    """
    seeded = await MemoryService(db, fake_embedder).store(
        MemoryCreate(
            agent_type="design_sync",
            memory_type="semantic",
            content="avoid hero_banner template for dense product grids",
            project_id=None,
        )
    )

    async with get_system_db_context() as rdb:
        results = await MemoryService(rdb, fake_embedder).recall(
            "hero_banner dense product grids",
            memory_type="semantic",
            limit=5,
        )

    assert results, "system-session recall returned [] — the dead-on-read regression is back"
    assert any(entry.id == seeded.id for entry, _ in results)


async def test_unstamped_session_recall_raises_runtime_error(
    db: AsyncSession,
    fake_embedder: EmbeddingProvider,
) -> None:
    """An unstamped session must fail loud, locking the regression.

    The `db` fixture yields a session with no `tenant_access` stamp —
    exactly the shape `get_db_context()` produced at the dead recall sites.
    `scoped_access` must raise so a future caller that re-introduces the
    wrong opener can't silently swallow it back to `[]`. Asserting the raise
    is what keeps the swallow from re-hiding the bug.
    """
    with pytest.raises(RuntimeError):
        await MemoryService(db, fake_embedder).recall("anything", limit=1)

    # Same guarantee one layer down, on a real get_db_context() session.
    async with get_db_context() as plain:
        with pytest.raises(RuntimeError):
            await MemoryRepository(plain).similarity_search([0.1] * 1024, limit=1)


async def test_blueprint_engine_recall_injects_memory(
    db: AsyncSession,
    fake_embedder: EmbeddingProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: `engine._recall_memories` surfaces a seeded memory.

    This is the RED-before-GREEN regression: pre-fix `_recall_memories`
    opened `get_db_context()` → `scoped_access` raised → swallowed → `[]`.
    Post-fix it opens `get_system_db_context()` and the memory reaches the
    list that `_build_node_context` injects into the node prompt
    (`engine.py` LAYER 10). `_recall_memories` only reads `self._project_id`,
    so a bare instance is sufficient and avoids constructing a full
    `BlueprintDefinition`.
    """

    # Engine builds its provider via get_embedding_provider(get_settings());
    # the local import inside _recall_memories resolves this patched attr. A
    # typed factory (not a lambda) keeps the patched value fully typed for
    # pyright (reportUnknownArgumentType) — mirrors conftest's embedding_stub.
    def _provider_factory(_settings: object) -> EmbeddingProvider:
        return fake_embedder

    monkeypatch.setattr(
        "app.knowledge.embedding.get_embedding_provider",
        _provider_factory,
    )

    await MemoryService(db, fake_embedder).store(
        MemoryCreate(
            agent_type="scaffolder",
            memory_type="semantic",
            content="GMAIL_CLIP_FACT: Gmail clips email past 102KB",
            project_id=None,
        )
    )

    engine = BlueprintEngine.__new__(BlueprintEngine)
    engine._project_id = None

    recalled = await engine._recall_memories("Gmail clipping at 102KB")

    assert any("GMAIL_CLIP_FACT" in item["content"] for item in recalled)
