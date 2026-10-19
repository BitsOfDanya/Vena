import sqlalchemy as sa
from alembic import op

revision = "b8e4f2a91c57"
down_revision = "b5d1e7c3a9f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("scopes", sa.JSON(), nullable=False, server_default='["all"]')
    )


def downgrade():
    op.drop_column("users", "scopes")
