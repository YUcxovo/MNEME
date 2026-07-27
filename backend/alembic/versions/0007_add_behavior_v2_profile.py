"""Add contrastive behavior-v2 profile state.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from mneme.models.user import EMBEDDING_DIMENSIONS

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add negative evidence, confidence, and inspectable evidence metadata."""
    op.drop_constraint(
        "ck_user_preferences_behavior_embedding_has_model",
        "user_preferences",
        type_="check",
    )
    op.add_column(
        "user_preferences",
        sa.Column(
            "negative_behavior_embedding",
            Vector(EMBEDDING_DIMENSIONS),
            nullable=True,
        ),
    )
    op.add_column(
        "user_preferences",
        sa.Column("behavior_confidence", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "user_preferences",
        sa.Column(
            "behavior_evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        "UPDATE user_preferences SET behavior_confidence = 1 WHERE behavior_embedding IS NOT NULL"
    )
    op.create_check_constraint(
        "ck_user_preferences_behavior_embedding_has_model",
        "user_preferences",
        "(behavior_embedding IS NULL AND negative_behavior_embedding IS NULL AND "
        "behavior_embedding_model IS NULL) OR "
        "((behavior_embedding IS NOT NULL OR negative_behavior_embedding IS NOT NULL) AND "
        "behavior_embedding_model IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_user_preferences_behavior_confidence_range",
        "user_preferences",
        "behavior_confidence >= 0 AND behavior_confidence <= 1",
    )


def downgrade() -> None:
    """Remove v2-only state while retaining a valid positive v1-style profile."""
    op.drop_constraint(
        "ck_user_preferences_behavior_confidence_range",
        "user_preferences",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_preferences_behavior_embedding_has_model",
        "user_preferences",
        type_="check",
    )
    op.execute(
        "UPDATE user_preferences SET behavior_embedding_model = NULL "
        "WHERE behavior_embedding IS NULL"
    )
    op.drop_column("user_preferences", "behavior_evidence")
    op.drop_column("user_preferences", "behavior_confidence")
    op.drop_column("user_preferences", "negative_behavior_embedding")
    op.create_check_constraint(
        "ck_user_preferences_behavior_embedding_has_model",
        "user_preferences",
        "(behavior_embedding IS NULL AND behavior_embedding_model IS NULL) OR "
        "(behavior_embedding IS NOT NULL AND behavior_embedding_model IS NOT NULL)",
    )
