import uuid
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class TransitResource(Base):
    __tablename__ = "transit_resources"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(24), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    entry_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entry_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entry_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    exit_region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bandwidth_mbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    traffic_limit_gb: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    traffic_used_gb: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    protocol_hint: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    has_ssh: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )
    ssh_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssh_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ssh_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="active",
        server_default="active",
    )
    expires_at = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at = mapped_column(DateTime(timezone=True), nullable=True)
