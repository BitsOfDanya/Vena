import sqlalchemy as sa
from alembic import op

revision = "f3a9c2d7e410"
down_revision = "e8b5c1d2a901"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("auth_provider", sa.String(16), nullable=False, server_default="local"))
    op.add_column("users", sa.Column("directory_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_users_directory_id", "users", ["directory_id"])
    op.create_table(
        "equipment",
        sa.Column("asset_id", sa.String(32), primary_key=True),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("object_id", sa.String(80), nullable=False),
        sa.Column("section", sa.String(120), nullable=False),
        sa.Column("equipment_type", sa.String(80), nullable=False),
        sa.Column("tag", sa.String(200), nullable=False),
        sa.Column("system_type", sa.String(120), nullable=False),
        sa.Column("manufacturer", sa.String(120), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("serial_number", sa.String(120), nullable=False),
        sa.Column("installed_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "external_id", name="uq_equipment_source_external"),
    )
    op.create_index("ix_equipment_object_id", "equipment", ["object_id"])
    op.create_table(
        "integration_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
    )
    op.create_index("ix_integration_runs_kind", "integration_runs", ["kind"])
    op.create_table(
        "historical_events",
        sa.Column("event_id", sa.String(40), primary_key=True),
        sa.Column("channel_id", sa.String(32), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.String(120), nullable=False),
        sa.Column("alarm", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_historical_events_channel_id", "historical_events", ["channel_id"])
    op.create_index("ix_historical_events_ts", "historical_events", ["ts"])
    op.create_table(
        "import_outbox",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("import_outbox")
    op.drop_table("historical_events")
    op.drop_table("integration_runs")
    op.drop_table("equipment")
    op.drop_constraint("uq_users_directory_id", "users", type_="unique")
    op.drop_column("users", "directory_id")
    op.drop_column("users", "auth_provider")
