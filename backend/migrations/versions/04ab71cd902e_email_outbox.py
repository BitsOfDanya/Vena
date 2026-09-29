import sqlalchemy as sa
from alembic import op

revision = "04ab71cd902e"
down_revision = "f3a9c2d7e410"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("subject", sa.String(240), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    ]:
        op.add_column("delivery_log", column)
    op.create_index("ix_delivery_queue", "delivery_log", ["channel", "status", "next_attempt_at"])
    # Legacy pending rows have no saved message and cannot be sent safely.
    op.execute("UPDATE delivery_log SET status='failed' WHERE status='pending'")


def downgrade():
    op.drop_index("ix_delivery_queue", table_name="delivery_log")
    for name in ["sent_at", "next_attempt_at", "attempts", "body", "subject"]:
        op.drop_column("delivery_log", name)
