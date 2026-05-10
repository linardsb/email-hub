"""normalize schema drift (TIMESTAMPTZ + NOT NULL + comments)

Revision ID: normalize_schema_drift
Revises: drop_items_table
Create Date: 2026-05-10 12:00:00.000000

Closes the long-standing drift cataloged in
``.agents/deferred-items.json::tech-debt-alembic-schema-drift``. The
``items`` table portion of that drift was already closed by
``drop_items_table`` (F007 cleanup); this migration tackles the rest.

Reconciled here (DB-side DDL):

1. **NULL backfill** on created_at/updated_at for 5 tables before flipping
   them to NOT NULL. Local audit on 2026-05-10 found 0 NULLs in all 10
   columns (most tables empty); the UPDATEs are idempotent no-ops in that
   case. Re-audit on staging before deploy — if production NULLs exist
   they will be backfilled to NOW() AT TIME ZONE 'UTC'.
2. **TIMESTAMPTZ conversion** on 12 columns across 6 tables. Models use
   ``DateTime(timezone=True)`` (via ``TimestampMixin``); the historical
   migrations declared bare ``TIMESTAMP()``.
3. **SET NOT NULL** on 10 columns across 5 tables, matching the
   ``Mapped[datetime]`` annotation in ``TimestampMixin``.
4. **COMMENT ON COLUMN** for 5 columns on ``collaborative_documents``
   where the model declares ``comment=`` strings that never made it to
   the DB.

Reconciled model-side (parity, no DDL — applied in the same PR):

- ``qa_overrides.qa_result_id``: drop column-level ``unique=True`` and
  declare an explicit named ``UniqueConstraint`` in ``__table_args__``
  to match the existing ``qa_overrides_qa_result_id_key`` constraint.
- ``memory_entries``: declare ``Index("ix_memory_entries_embedding_hnsw",
  ...)`` with ``postgresql_using="hnsw"`` matching the live indexdef
  (``WITH (m='16', ef_construction='64')``, ``vector_cosine_ops``).
- ``design_connections.config_json``: change column type from ``JSON``
  to ``JSONB`` to match the live DB.
- ``design_token_snapshots.document_json``: add ``comment="..."`` to
  match the existing column comment in the DB.

PK-index drift (model declared ``ix_<table>_id`` for 7 tables, DB has
none — Postgres auto-creates the PK btree) is suppressed via the new
``include_object`` filter in ``alembic/env.py``.

## Forward-only

This migration is **forward-only**. The ``downgrade()`` raises
``NotImplementedError``:

- ``ALTER COLUMN ... TYPE TIMESTAMP WITHOUT TIME ZONE`` on populated
  tables loses tz offset information.
- ``SET NOT NULL`` rows cannot be reversed without retaining the
  pre-migration null state.
- ``scripts/safe_alembic.sh:34`` already blocks ``alembic downgrade``
  in this repo, so no CI path exercises the downgrade.

If rollback is required, restore from the pre-migration backup.

## Lock / runtime warning

``ALTER TABLE ... TYPE TIMESTAMPTZ`` takes an ACCESS EXCLUSIVE lock and
rewrites the table. Largest expected tables in production: blueprint
checkpoints, design connections, esp connections. Run during a
maintenance window if either has >1M rows. Squawk's ``column-type-change``
rule will fire — suppressed inline per ``op.execute()`` site below.

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "normalize_schema_drift"
down_revision: str | None = "drop_items_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables × cols where created_at/updated_at need TIMESTAMP -> TIMESTAMPTZ.
# Source: `uv run alembic check` on 2026-05-10 against fresh DB.
_TIMESTAMPTZ_DRIFT: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("blueprint_checkpoints", ("created_at", "updated_at")),
    ("design_connections", ("created_at", "updated_at")),
    ("design_import_assets", ("created_at", "updated_at")),
    ("design_imports", ("created_at", "updated_at")),
    ("design_token_snapshots", ("created_at", "updated_at")),
    ("esp_connections", ("created_at", "updated_at")),
)

# Tables × cols where DB allows NULL but model says NOT NULL.
# Order matters: backfill must run before SET NOT NULL.
_NOT_NULL_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("calibration_records", ("created_at", "updated_at")),
    ("calibration_summaries", ("created_at", "updated_at")),
    ("component_qa_results", ("created_at", "updated_at")),
    ("rendering_screenshots", ("created_at", "updated_at")),
    ("rendering_tests", ("created_at", "updated_at")),
)

# Column comments declared on the SQLAlchemy model but never applied to DB.
# Source: app/streaming/crdt/models.py CollaborativeDocument.
_COLLABORATIVE_DOCUMENTS_COMMENTS: tuple[tuple[str, str], ...] = (
    ("room_id", "Room identifier (project:{id}:template:{id})"),
    ("state", "Compacted Yjs document state (full snapshot)"),
    ("pending_updates", "Accumulated incremental Yjs updates since last compaction"),
    ("pending_update_count", "Number of updates since last compaction"),
    ("document_size_bytes", "Total document size for quota enforcement"),
)


def upgrade() -> None:
    # 1. NULL backfill — gate for SET NOT NULL. Idempotent: no-op when no NULLs.
    # Identifiers come from the hardcoded _NOT_NULL_TARGETS tuple, not user input.
    for tbl, cols in _NOT_NULL_TARGETS:
        for col in cols:
            op.execute(f"UPDATE {tbl} SET {col} = NOW() WHERE {col} IS NULL")  # noqa: S608

    # 2. TIMESTAMP -> TIMESTAMPTZ. Raw DDL because alembic's alter_column
    #    helper choked on TZ conversions in some configurations.
    for tbl, cols in _TIMESTAMPTZ_DRIFT:
        for col in cols:
            # squawk-ignore: column-type-change
            op.execute(
                f"ALTER TABLE {tbl} ALTER COLUMN {col} "
                f"TYPE TIMESTAMP WITH TIME ZONE USING {col} AT TIME ZONE 'UTC'"
            )

    # 3. SET NOT NULL on the 10 created_at/updated_at columns now backfilled.
    for tbl, cols in _NOT_NULL_TARGETS:
        for col in cols:
            op.alter_column(tbl, col, nullable=False)

    # 4. COMMENT ON COLUMN for collaborative_documents (5 cols).
    for col, comment in _COLLABORATIVE_DOCUMENTS_COMMENTS:
        # SQL string literals: escape single quotes via doubling.
        escaped = comment.replace("'", "''")
        op.execute(f"COMMENT ON COLUMN collaborative_documents.{col} IS '{escaped}'")

    # 5. Drop the redundant unique index on qa_overrides.qa_result_id.
    #    The named unique constraint qa_overrides_qa_result_id_key (declared in
    #    the model __table_args__) is already backed by its own unique btree
    #    index, so the explicit ix_qa_overrides_qa_result_id from a long-ago
    #    `unique=True, index=True` column is duplicated work.
    op.execute("DROP INDEX IF EXISTS ix_qa_overrides_qa_result_id")


def downgrade() -> None:
    """Forward-only migration — see module docstring."""
    raise NotImplementedError(
        "Schema drift normalization is forward-only. "
        "TIMESTAMPTZ -> TIMESTAMP loses tz info; SET NOT NULL is irreversible "
        "without the pre-migration null state. Restore from snapshot if rollback "
        "is required."
    )
