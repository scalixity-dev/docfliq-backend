import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base


class PostVersion(Base):
    """Immutable snapshot of a post's content taken before each edit.

    version_number mirrors Post.version at the time of the snapshot.
    Enables edit history viewing and content restoration.
    """

    __tablename__ = "post_versions"

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.post_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Snapshot of media_urls JSONB at edit time
    media_urls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Snapshot of link_preview JSONB at edit time
    link_preview: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Soft reference — editor lives in identity_db
    edited_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    post = relationship("Post", back_populates="versions", lazy="select")

    __table_args__ = (
        Index("ix_post_versions_post_id", "post_id"),
        Index("ix_post_versions_post_version", "post_id", "version_number"),
    )
