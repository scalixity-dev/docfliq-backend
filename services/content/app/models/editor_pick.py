import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base


class EditorPick(Base):
    """Curated posts hand-picked by admins for cold-start and discovery feeds.

    Each post may appear at most once (unique constraint on post_id).
    priority: lower integer = shown first (0 is highest priority).
    """

    __tablename__ = "editor_picks"

    pick_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.post_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Soft reference — admin user lives in identity_db
    added_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    post = relationship("Post", lazy="select")

    __table_args__ = (
        UniqueConstraint("post_id", name="uq_editor_picks_post_id"),
        Index("ix_editor_picks_priority", "priority"),
        Index("ix_editor_picks_is_active", "is_active"),
    )
