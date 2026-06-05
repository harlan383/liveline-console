import uuid

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class VpsServer(Base):
    __tablename__ = "vps_servers"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    ssh_username: Mapped[str] = mapped_column(String(80), nullable=False, default="root")
    ssh_key_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    xray_installed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    xray_config_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, default="unconfigured")
    ssh_host_key_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_known_config_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_known_meta_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    nodes = relationship("Node", back_populates="vps")
    tasks = relationship("Task", back_populates="vps")
