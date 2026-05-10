"""Database models for QA engine."""

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.models import TimestampMixin


class QAResult(Base, TimestampMixin):
    """Aggregate QA result for an email build."""

    __tablename__ = "qa_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    build_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("email_builds.id"), nullable=True, index=True
    )
    template_version_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("template_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checks_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=11)

    checks: Mapped[list["QACheck"]] = relationship(
        back_populates="qa_result", cascade="all, delete-orphan", lazy="selectin"
    )
    override: Mapped["QAOverride | None"] = relationship(
        back_populates="qa_result", uselist=False, lazy="selectin"
    )


class QACheck(Base, TimestampMixin):
    """Individual QA check result."""

    __tablename__ = "qa_checks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    qa_result_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("qa_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_name: Mapped[str] = mapped_column(String(50), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning")

    qa_result: Mapped["QAResult"] = relationship(back_populates="checks")


class QAOverride(Base, TimestampMixin):
    """Records admin/developer override of failing QA checks."""

    __tablename__ = "qa_overrides"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Unique constraint qa_overrides_qa_result_id_key (declared in __table_args__)
    # is backed by a unique btree index — no separate index= needed.
    qa_result_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("qa_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    overridden_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    checks_overridden: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    qa_result: Mapped["QAResult"] = relationship(back_populates="override")

    __table_args__ = (UniqueConstraint("qa_result_id", name="qa_overrides_qa_result_id_key"),)
