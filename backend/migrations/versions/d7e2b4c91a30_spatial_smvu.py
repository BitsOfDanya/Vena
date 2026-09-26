"""Add spatial_layers and smvu_ingest_state.

Revision ID: d7e2b4c91a30
Revises: c4f8a91e2b10
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7e2b4c91a30"
down_revision: str | None = "c4f8a91e2b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spatial_layers",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("feature_collection", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "smvu_ingest_state",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("last_batch_id", sa.String(length=80), nullable=False),
        sa.Column("last_event_count", sa.Integer(), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("smvu_ingest_state")
    op.drop_table("spatial_layers")
