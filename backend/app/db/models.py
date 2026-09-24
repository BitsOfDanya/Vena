from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    pass


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    asset_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pattern_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dedup_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    source_detail: Mapped[str] = mapped_column(String(120), default="")
    source_pattern_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), default="inspect")
    reason: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    recommended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="planned")
    assignee: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    notify_channels: Mapped[str] = mapped_column(String(120), default="")
    created_by: Mapped[str] = mapped_column(String(120), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    source_prediction_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_model_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_prediction_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_horizon_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    result_note: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    history: Mapped[list["ActionEvent"]] = relationship(
        back_populates="action", cascade="all, delete-orphan", order_by="ActionEvent.at"
    )


class ActionEvent(Base):
    __tablename__ = "action_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(120), default="system")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")

    action: Mapped[Action] = relationship(back_populates="history")


class DeliveryLog(Base):
    __tablename__ = "delivery_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel: Mapped[str] = mapped_column(String(32))
    recipient: Mapped[str] = mapped_column(String(200), default="")
    dedup_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SettingsRecord(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class PredictionPoint(Base):
    __tablename__ = "prediction_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String(32), index=True)
    asset_id: Mapped[str] = mapped_column(String(32), index=True)
    model_id: Mapped[str] = mapped_column(String(40))
    horizon_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float] = mapped_column(Float)
    score_type: Mapped[str] = mapped_column(String(32), default="risk_score")
    risk_level: Mapped[str] = mapped_column(String(16), default="normal")
    prediction_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessedSnapshot(Base):
    __tablename__ = "processed_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    prediction_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prediction_count: Mapped[int] = mapped_column(Integer, default=0)
    notifications_created: Mapped[int] = mapped_column(Integer, default=0)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(255))
    status_code: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    accepted_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InfrastructureObject(Base):
    __tablename__ = "infrastructure_objects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    system_name: Mapped[str] = mapped_column(String(255), default="")
    tag: Mapped[str] = mapped_column(String(120), default="")
    district: Mapped[str] = mapped_column(String(80), default="")
    object_type: Mapped[str] = mapped_column(String(32), default="collector")
    status: Mapped[str] = mapped_column(String(16), default="normal")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SensorChannel(Base):
    __tablename__ = "sensor_channels"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_tag: Mapped[str] = mapped_column(String(120), default="")
    channel_type: Mapped[str] = mapped_column(String(80), default="")
    display_name: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"
    __table_args__ = (
        UniqueConstraint("source_record_id", "channel_id", name="uq_event_source_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_record_id: Mapped[str] = mapped_column(String(80))
    channel_id: Mapped[str] = mapped_column(String(64), index=True)
    channel_type: Mapped[str] = mapped_column(String(80), default="")
    value_raw: Mapped[str] = mapped_column(String(255))
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    import_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("import_batches.id"), nullable=True, index=True
    )


class NetworkEdge(Base):
    __tablename__ = "network_edges"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("infrastructure_objects.id"), index=True)
    target_id: Mapped[str] = mapped_column(ForeignKey("infrastructure_objects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="collector")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
