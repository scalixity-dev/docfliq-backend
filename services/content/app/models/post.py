import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base

from .enums import (
    ContentType,
    PostStatus,
    PostVisibility,
    content_type_enum,
    post_status_enum,
    post_visibility_enum,
)


class Post(Base):
    __tablename__ = "posts"

    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Soft reference — User lives in identity_db, FK not enforceable cross-DB
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    content_type: Mapped[ContentType] = mapped_column(content_type_enum, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{url, type, thumbnail}]
    media_urls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {url, og_title, og_image, og_description}
    link_preview: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[PostVisibility] = mapped_column(
        post_visibility_enum, nullable=False, default=PostVisibility.PUBLIC
    )
    status: Mapped[PostStatus] = mapped_column(
        post_status_enum, nullable=False, default=PostStatus.PUBLISHED
    )
    specialty_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    hashtags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    share_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bookmark_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("channels.channel_id", ondelete="SET NULL"),
        nullable=True,
    )
    # For REPOST content type: points to the original post (self-referential)
    original_post_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.post_id", ondelete="SET NULL"),
        nullable=True,
    )
    # Set when status transitions to SOFT_DELETED; used for 30-day retention cleanup
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    channel = relationship("Channel", lazy="select")
    comments = relationship("Comment", back_populates="post", lazy="noload")
    bookmarks = relationship("Bookmark", back_populates="post", lazy="noload")
    shares = relationship("Share", back_populates="post", lazy="noload")
    versions = relationship("PostVersion", back_populates="post", lazy="noload")
    # Self-referential: the original post this repost points to
    original_post = relationship(
        "Post", remote_side="Post.post_id", foreign_keys=[original_post_id], lazy="select"
    )

    __table_args__ = (
        Index("ix_posts_author_id", "author_id"),
        Index("ix_posts_status", "status"),
        Index("ix_posts_created_at", "created_at"),
        # GIN index for array containment queries on specialty_tags
        Index("ix_posts_specialty_tags", "specialty_tags", postgresql_using="gin"),
        # GIN index for array containment queries on hashtags
        Index("ix_posts_hashtags", "hashtags", postgresql_using="gin"),
        # Functional GIN index for full-text search on title + body
        Index(
            "ix_posts_fts",
            text(
                "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body, ''))"
            ),
            postgresql_using="gin",
        ),
    )