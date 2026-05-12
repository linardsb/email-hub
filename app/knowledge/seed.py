"""Seed the knowledge base with email development content.

Usage:
    uv run python -m app.knowledge.seed              # Skip existing
    uv run python -m app.knowledge.seed --force       # Re-ingest all
    uv run python -m app.knowledge.seed --skip-graph  # RAG only, no Cognee

Requires:
    - Database running (make db)
    - EMBEDDING configuration in environment
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.database import get_db_context
from app.core.logging import get_logger
from app.knowledge.data.seed_manifest import SEED_MANIFEST, SeedEntry
from app.knowledge.schemas import DocumentTagRequest, DocumentUpload
from app.knowledge.services.ingestion import IngestionService
from app.knowledge.services.tags import TagService

SEED_DIR = Path(__file__).parent / "data" / "seeds"

logger = get_logger(__name__)


async def _get_existing_filenames(ingestion: IngestionService) -> set[str]:
    """Collect all filenames already in the knowledge base."""
    filenames: set[str] = set()
    offset = 0
    batch_size = 100
    while True:
        docs = await ingestion.repository.list_documents(offset=offset, limit=batch_size)
        if not docs:
            break
        for doc in docs:
            filenames.add(doc.filename)
        if len(docs) < batch_size:
            break
        offset += batch_size
    return filenames


async def _ensure_tags(ingestion: IngestionService) -> dict[str, int]:
    """Pre-create all tags from the manifest and return name->id mapping."""
    all_tags: set[str] = set()
    for entry in SEED_MANIFEST:
        all_tags.update(entry.tags)

    tag_map: dict[str, int] = {}
    for tag_name in sorted(all_tags):
        tag = await ingestion.repository.get_or_create_tag(tag_name)
        tag_map[tag_name] = tag.id
    return tag_map


async def _ingest_entry(
    ingestion: IngestionService,
    tags: TagService,
    entry: SeedEntry,
    tag_map: dict[str, int],
) -> int:
    """Ingest a single seed entry and tag it. Returns chunk count."""
    file_path = SEED_DIR / entry.filename

    upload = DocumentUpload(
        domain=entry.domain,
        title=entry.title,
        description=entry.description,
        metadata_json=None,
    )
    doc = await ingestion.ingest_document(
        file_path=str(file_path),
        upload=upload,
        filename=file_path.name,
        source_type="text",
        file_size=file_path.stat().st_size,
    )

    tag_ids = [tag_map[t] for t in entry.tags]
    if tag_ids:
        await tags.add_tags_to_document(doc.id, DocumentTagRequest(tag_ids=tag_ids))

    return doc.chunk_count


async def _seed_graph(entries: list[SeedEntry]) -> None:
    """Feed seed documents through Cognee's ECL pipeline.

    Reads each document file, groups by domain (dataset), and runs
    cognee.add() + cognee.cognify() per dataset.

    Skipped gracefully if Cognee is disabled or not installed.
    """
    settings = get_settings()

    if not settings.cognee.enabled:
        logger.info("  Graph seeding skipped (COGNEE__ENABLED=false)")
        return

    try:
        from app.knowledge.graph import cognee_provider as _cp

        provider_cls = _cp.CogneeGraphProvider
    except ImportError:
        logger.info("  Graph seeding skipped (cognee not installed)")
        return

    logger.info("  Seeding knowledge graph...")
    start = time.monotonic()

    provider = provider_cls(settings)

    # Group documents by domain for per-dataset ingestion
    by_domain: dict[str, list[str]] = {}
    for entry in entries:
        file_path = SEED_DIR / entry.filename
        if not file_path.is_file():
            continue
        text = file_path.read_text(encoding="utf-8")
        by_domain.setdefault(entry.domain, []).append(text)

    total_docs = 0
    for domain, texts in by_domain.items():
        try:
            await provider.add_documents(texts, dataset_name=domain)
            logger.info(f"  GRAPH ADD  {domain}: {len(texts)} documents")
            total_docs += len(texts)
        except Exception as e:
            logger.error(f"  GRAPH FAIL {domain}: {e}")
            logger.error(
                "knowledge.graph_seed.add_failed",
                domain=domain,
                count=len(texts),
                error=str(e),
            )

    # Run ECL pipeline per dataset (foreground — we want to see errors)
    for domain in by_domain:
        try:
            await provider.build_graph(dataset_name=domain, background=False)
            logger.info(f"  GRAPH BUILD {domain}: cognify complete")
        except Exception as e:
            logger.error(f"  GRAPH BUILD FAIL {domain}: {e}")
            logger.error(
                "knowledge.graph_seed.build_failed",
                domain=domain,
                error=str(e),
            )

    duration = time.monotonic() - start
    logger.info(
        f"  Graph seeding done in {duration:.1f}s ({total_docs} documents across {len(by_domain)} datasets)"
    )


async def _seed_ontology_graph() -> None:
    """Seed ontology-derived documents into Cognee graph."""
    settings = get_settings()

    if not settings.cognee.enabled:
        logger.info("  Ontology graph seeding skipped (COGNEE__ENABLED=false)")
        return

    try:
        from app.knowledge.graph import cognee_provider as _cp

        provider_cls = _cp.CogneeGraphProvider
    except ImportError:
        logger.info("  Ontology graph seeding skipped (cognee not installed)")
        return

    from app.knowledge.ontology.graph_export import export_ontology_documents

    logger.info("  Seeding ontology into knowledge graph...")
    start = time.monotonic()

    provider = provider_cls(settings)
    documents = export_ontology_documents()

    # Group by dataset
    by_dataset: dict[str, list[str]] = {}
    for dataset_name, text in documents:
        by_dataset.setdefault(dataset_name, []).append(text)

    total_docs = 0
    for dataset, texts in by_dataset.items():
        try:
            await provider.add_documents(texts, dataset_name=dataset)
            logger.info(f"  ONTOLOGY ADD  {dataset}: {len(texts)} documents")
            total_docs += len(texts)
        except Exception as e:
            logger.error(f"  ONTOLOGY FAIL {dataset}: {e}")
            logger.error(
                "knowledge.ontology_seed.add_failed",
                dataset=dataset,
                count=len(texts),
                error=str(e),
            )

    for dataset in by_dataset:
        try:
            await provider.build_graph(dataset_name=dataset, background=False)
            logger.info(f"  ONTOLOGY BUILD {dataset}: cognify complete")
        except Exception as e:
            logger.error(f"  ONTOLOGY BUILD FAIL {dataset}: {e}")
            logger.error(
                "knowledge.ontology_seed.build_failed",
                dataset=dataset,
                error=str(e),
            )

    duration = time.monotonic() - start
    logger.info(
        f"  Ontology graph done in {duration:.1f}s"
        f" ({total_docs} documents across {len(by_dataset)} datasets)"
    )


async def seed_knowledge_base(*, force: bool = False, skip_graph: bool = False) -> None:
    """Seed the knowledge base with email development content.

    Args:
        force: If True, skip idempotency checks and re-ingest all documents.
        skip_graph: If True, skip Cognee graph seeding (RAG only).
    """
    start = time.monotonic()
    logger.info(f"  Seeding knowledge base ({len(SEED_MANIFEST)} documents)...")
    logger.info(f"  Source: {SEED_DIR}")
    logger.info(f"  Force: {force}")

    async with get_db_context() as db:
        ingestion = IngestionService(db)
        tags = TagService(db)

        # Check existing documents for idempotency
        existing = await _get_existing_filenames(ingestion) if not force else set[str]()

        # Pre-create tags
        tag_map = await _ensure_tags(ingestion)
        logger.info(f"  Tags ready: {len(tag_map)}")

        seeded = 0
        skipped = 0
        failed = 0
        total_chunks = 0

        for entry in SEED_MANIFEST:
            file_path = SEED_DIR / entry.filename

            # Validate file exists
            if not file_path.is_file():
                logger.info(f"  MISS {entry.filename} (file not found)")
                failed += 1
                continue

            # Idempotency: skip if filename already exists
            if file_path.name in existing:
                logger.debug(f"  SKIP {entry.filename} (already seeded)")
                skipped += 1
                continue

            try:
                chunks = await _ingest_entry(ingestion, tags, entry, tag_map)
                total_chunks += chunks
                seeded += 1
                logger.info(f"  OK   {entry.filename} -> {chunks} chunks")
            except Exception as e:
                failed += 1
                logger.error(f"  FAIL {entry.filename}: {e}")
                logger.error(
                    "knowledge.seed.entry_failed",
                    filename=entry.filename,
                    error=str(e),
                    error_type=type(e).__name__,
                )

    duration = time.monotonic() - start
    logger.info(f"  Done in {duration:.1f}s: {seeded} seeded, {skipped} skipped, {failed} failed")
    logger.info(f"  Total chunks: {total_chunks}")

    # --- Phase 2: Graph seeding (Cognee ECL pipeline) ---
    # Use all manifest entries (not just newly seeded — graph needs full corpus)
    if not skip_graph:
        await _seed_graph(SEED_MANIFEST)
        await _seed_ontology_graph()
    else:
        logger.info("  Graph seeding skipped (--skip-graph flag)")

    if failed > 0:
        sys.exit(1)


def main() -> None:
    """CLI entry point."""
    force = "--force" in sys.argv
    skip_graph = "--skip-graph" in sys.argv
    asyncio.run(seed_knowledge_base(force=force, skip_graph=skip_graph))


if __name__ == "__main__":
    main()
