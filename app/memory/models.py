# pyright: reportUnknownMemberType=false
"""SQLAlchemy models for agent memory entries."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import TimestampMixin


class MemoryEntry(Base, TimestampMixin):
    """Persistent agent memory with vector embedding for similarity search.

    Memory types:
    - procedural: learned patterns (e.g., "Samsung Mail needs inline styles for dark mode")
    - episodic: session logs (e.g., "fixed VML background in Outlook 2016 build")
    - semantic: durable facts (e.g., "Gmail clips emails over 102KB")
    """

    __tablename__ = "memory_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # procedural | episodic | semantic
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1024))
    project_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    metadata_json = mapped_column(JSONB, nullable=True)
    decay_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="agent"
    )  # agent | dcg | compaction
    source_agent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_evergreen: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("ix_memory_project_agent", "project_id", "agent_type"),
        Index("ix_memory_type_decay", "memory_type", "decay_weight"),
        Index(
            "ix_memory_entries_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
