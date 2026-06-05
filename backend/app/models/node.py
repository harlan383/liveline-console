import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    vps_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vps_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_name: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    protocol: Mapped[str] = mapped_column(String(40), nullable=False, default="vless")
    transport: Mapped[str | None] = mapped_column(String(40), nullable=True)
    security: Mapped[str] = mapped_column(String(40), nullable=False, default="reality")
    flow: Mapped[str | None] = mapped_column(String(80), nullable=True)
    xray_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uuid: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reality_public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    reality_short_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sni: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    share_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(80), nullable=True)
    service_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    connectivity_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="manual_add")
    status: Mapped[str] = mapped_column(String(80), nullable=False, default="deploying")
    deleted_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_remote_check_at = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(80), nullable=True)

    vps = relationship("VpsServer", back_populates="nodes")
    tasks = relationship("Task", back_populates="node")
