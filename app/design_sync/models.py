"""Database models for design tool sync."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.models import TimestampMixin


class DesignConnection(Base, TimestampMixin):
    """A connection to an external design tool file."""

    __tablename__ = "design_connections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    file_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="connected")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=True, index=True
    )
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    webhook_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    snapshots: Mapped[list["DesignTokenSnapshot"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )
    imports: Mapped[list["DesignImport"]] = relationship(
        back_populates="connection", cascade="all, delete-orphan"
    )


class DesignTokenSnapshot(Base, TimestampMixin):
    """A snapshot of design tokens extracted from a connection."""

    __tablename__ = "design_token_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("design_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tokens_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    document_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        comment="EmailDesignDocument v1 JSON (canonical intermediate representation)",
    )
    extracted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    connection: Mapped["DesignConnection"] = relationship(back_populates="snapshots")


class DesignImport(Base, TimestampMixin):
    """A design-to-email import job."""

    __tablename__ = "design_imports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("design_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    selected_node_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    structure_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    generated_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_template_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fidelity_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )

    connection: Mapped["DesignConnection"] = relationship(back_populates="imports")
    assets: Mapped[list["DesignImportAsset"]] = relationship(
        back_populates="design_import", cascade="all, delete-orphan"
    )


class DesignImportAsset(Base, TimestampMixin):
    """An image asset exported during a design import."""

    __tablename__ = "design_import_assets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    import_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("design_imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(100), nullable=False)
    node_name: Mapped[str] = mapped_column(String(300), nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    format: Mapped[str] = mapped_column(String(10), nullable=False, default="png")
    usage: Mapped[str | None] = mapped_column(String(20), nullable=True)

    design_import: Mapped["DesignImport"] = relationship(back_populates="assets")
