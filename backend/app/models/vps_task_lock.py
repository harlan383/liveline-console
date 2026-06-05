import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class VpsTaskLock(Base):
    __tablename__ = "vps_task_locks"

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
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lock_type: Mapped[str] = mapped_column(String(24), nullable=False)
    locked_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at = mapped_column(DateTime(timezone=True), nullable=False)
    lock_token: Mapped[str] = mapped_column(String(160), nullable=False)
    released_at = mapped_column(DateTime(timezone=True), nullable=True)
