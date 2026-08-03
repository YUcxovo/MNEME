"""Allow the explicit unmatched claim-provenance state on paper summaries.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_CONSTRAINT = "source_match_status"
_TABLE = "paper_summaries"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "source_match_status IN ('matched', 'partial', 'not_checked', 'unmatched')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE paper_summaries SET source_match_status = 'not_checked' "
        "WHERE source_match_status = 'unmatched'"
    )
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        "source_match_status IN ('matched', 'partial', 'not_checked')",
    )
