from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a62840b781f7'
down_revision: Union[str, Sequence[str], None] = '6d3bb0b1dbb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('prediction_points',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('snapshot_id', sa.String(length=32), nullable=False),
    sa.Column('asset_id', sa.String(length=32), nullable=False),
    sa.Column('model_id', sa.String(length=40), nullable=False),
    sa.Column('horizon_hours', sa.Integer(), nullable=True),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('score_type', sa.String(length=32), nullable=False),
    sa.Column('risk_level', sa.String(length=16), nullable=False),
    sa.Column('prediction_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prediction_points_asset_id'), 'prediction_points', ['asset_id'], unique=False)
    op.create_index(op.f('ix_prediction_points_prediction_time'), 'prediction_points', ['prediction_time'], unique=False)
    op.create_index(op.f('ix_prediction_points_snapshot_id'), 'prediction_points', ['snapshot_id'], unique=False)
    op.create_table('processed_snapshots',
    sa.Column('snapshot_id', sa.String(length=32), nullable=False),
    sa.Column('prediction_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('prediction_count', sa.Integer(), nullable=False),
    sa.Column('notifications_created', sa.Integer(), nullable=False),
    sa.Column('stale', sa.Boolean(), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('snapshot_id')
    )
    op.add_column('actions', sa.Column('source_prediction_id', sa.String(length=80), nullable=True))
    op.add_column('actions', sa.Column('source_model_id', sa.String(length=40), nullable=True))
    op.add_column('actions', sa.Column('source_prediction_time', sa.DateTime(timezone=True), nullable=True))
    op.add_column('actions', sa.Column('source_score', sa.Float(), nullable=True))
    op.add_column('actions', sa.Column('source_horizon_hours', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('actions', 'source_horizon_hours')
    op.drop_column('actions', 'source_score')
    op.drop_column('actions', 'source_prediction_time')
    op.drop_column('actions', 'source_model_id')
    op.drop_column('actions', 'source_prediction_id')
    op.drop_table('processed_snapshots')
    op.drop_index(op.f('ix_prediction_points_snapshot_id'), table_name='prediction_points')
    op.drop_index(op.f('ix_prediction_points_prediction_time'), table_name='prediction_points')
    op.drop_index(op.f('ix_prediction_points_asset_id'), table_name='prediction_points')
    op.drop_table('prediction_points')
