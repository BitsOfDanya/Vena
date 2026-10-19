import sqlalchemy as sa
from alembic import op

revision = "b7d41c9e5a22"
down_revision = "b8e4f2a91c57"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("actions", sa.Column("helpdesk_ticket_id", sa.String(64), nullable=True))
    op.add_column("actions", sa.Column("helpdesk_status", sa.String(32), nullable=True))


def downgrade():
    op.drop_column("actions", "helpdesk_status")
    op.drop_column("actions", "helpdesk_ticket_id")
