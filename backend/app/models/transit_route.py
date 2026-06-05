import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class TransitRoute(Base):
    __tablename__ = "transit_routes"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    transit_resource_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transit_resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    landing_vps_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("vps_servers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    listen_port: Mapped[int] = mapped_column(Integer, nullable=False)
    target_host: Mapped[str] = mapped_column(String(255), nullable=False)
    target_port: Mapped[int] = mapped_column(Integer, nullable=False)
    forwarding_method: Mapped[str] = mapped_column(String(40), nullable=False)
    service_name: Mapped[str] = mapped_column(String(160), nullable=False)
    service_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    share_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at = mapped_column(DateTime(timezone=True), nullable=True)

    transit_resource = relationship("TransitResource")
    node = relationship("Node")
    landing_vps = relationship("VpsServer")
