"""Drop routing_history table (adaptive model tier routing removed in Phase 54.2).

The AI__ADAPTIVE_ROUTING_ENABLED loop and its routing_history model/repo were
deleted in Phase 54.2 (doubly inert — engine computed effective_tier but no node
read it). The table-creating migration m8n9o0p1q2r3 stays in-chain (history is
immutable); this revision drops the now-orphaned table so model ↔ schema parity
(``alembic check``) is restored.

Revision ID: drop_routing_history
Revises: normalize_schema_drift
Create Date: 2026-06-22
"""

import sqlalchemy as sa

from alembic import op

revision = "drop_routing_history"
down_revision = "normalize_schema_drift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("routing_history")


def downgrade() -> None:
    op.create_table(
        "routing_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("agent_name", sa.String(64), nullable=False, index=True),
        sa.Column("project_id", sa.Integer, nullable=True, index=True),
        sa.Column("tier_used", sa.String(16), nullable=False),
        sa.Column("accepted", sa.Boolean, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_routing_history_agent_project",
        "routing_history",
        ["agent_name", "project_id"],
    )
