"""Citation persistence shared by graph repositories and algorithms."""

from uuid import UUID

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from mneme.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Citation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A directed citation edge with at least one locally resolved endpoint."""

    __tablename__ = "citations"
    __table_args__ = (
        CheckConstraint(
            "(source_paper_id IS NOT NULL AND external_source_id IS NULL) OR "
            "(source_paper_id IS NULL AND external_source_id IS NOT NULL)",
            name="ck_citations_one_source",
        ),
        CheckConstraint(
            "(target_paper_id IS NOT NULL AND external_target_id IS NULL) OR "
            "(target_paper_id IS NULL AND external_target_id IS NOT NULL)",
            name="ck_citations_one_target",
        ),
        CheckConstraint(
            "source_paper_id IS NOT NULL OR target_paper_id IS NOT NULL",
            name="ck_citations_has_local_endpoint",
        ),
        CheckConstraint(
            "target_paper_id IS NULL OR target_paper_id <> source_paper_id",
            name="ck_citations_no_self_edge",
        ),
        Index(
            "uq_citations_internal_edge",
            "source_paper_id",
            "target_paper_id",
            unique=True,
            postgresql_where=text("source_paper_id IS NOT NULL AND target_paper_id IS NOT NULL"),
        ),
        Index(
            "uq_citations_external_target_edge",
            "source_paper_id",
            "external_target_id",
            unique=True,
            postgresql_where=text("source_paper_id IS NOT NULL AND external_target_id IS NOT NULL"),
        ),
        Index(
            "uq_citations_external_source_edge",
            "external_source_id",
            "target_paper_id",
            unique=True,
            postgresql_where=text("external_source_id IS NOT NULL AND target_paper_id IS NOT NULL"),
        ),
        Index("ix_citations_external_target_id", "external_target_id"),
        Index("ix_citations_target_paper_id", "target_paper_id"),
    )

    source_paper_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=True
    )
    external_source_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_paper_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="RESTRICT"), nullable=True
    )
    external_target_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    algorithm_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    algorithm_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
