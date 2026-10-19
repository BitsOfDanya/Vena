from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4d932c29b262"
down_revision: str | None = "b7d41c9e5a22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "situation_claims",
        sa.Column("situation_key", sa.String(length=200), nullable=False),
        sa.Column("situation_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("situation_key"),
    )


def downgrade() -> None:
    op.drop_table("situation_claims")
