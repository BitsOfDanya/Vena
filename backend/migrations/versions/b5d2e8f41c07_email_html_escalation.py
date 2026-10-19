import sqlalchemy as sa
from alembic import op

revision = "b5d2e8f41c07"
down_revision = "04ab71cd902e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("delivery_log", sa.Column("html", sa.Text(), nullable=True))
    op.add_column(
        "notifications", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE notifications SET escalated_at = created_at")


def downgrade():
    op.drop_column("notifications", "escalated_at")
    op.drop_column("delivery_log", "html")
