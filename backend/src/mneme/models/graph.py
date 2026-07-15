"""Citation persistence shared by graph repositories and algorithms."""

from uuid import UUID

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from mneme.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Citation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A directed citation edge that may initially target an external work."""

    __tablename__ = "citations"
    __table_args__ = (
        CheckConstraint(
            "target_paper_id IS NOT NULL OR external_target_id IS NOT NULL",
            name="ck_citations_has_target",
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
            postgresql_where=text("target_paper_id IS NOT NULL"),
        ),
        Index(
            "uq_citations_external_edge",
            "source_paper_id",
            "external_target_id",
            unique=True,
            postgresql_where=text("external_target_id IS NOT NULL"),
        ),
    )

    source_paper_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    target_paper_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="RESTRICT"), nullable=True
    )
    external_target_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    algorithm_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    algorithm_metadata: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
