"""
MediaAsset ORM model — SQLAlchemy 2.0 async.

Stores metadata for all uploaded media: videos, images, PDFs, SCORM packages.
Actual files live in S3; this table tracks processing state and derived URLs.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.database.postgres import Base
from app.asset.constants import AssetType, TranscodeStatus


class MediaAsset(Base):
    __tablename__ = "media_assets"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    asset_type: Mapped[AssetType] = mapped_column(
        SAEnum(AssetType, name="assettype", create_constraint=True),
        nullable=False,
        index=True,
    )

    # Original upload
    original_url: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Processed outputs
    processed_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hls_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # File metadata
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_secs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Transcoding state
    transcode_status: Mapped[TranscodeStatus] = mapped_column(
        SAEnum(TranscodeStatus, name="transcodestatus", create_constraint=True),
        nullable=False,
        server_default=TranscodeStatus.PENDING.value,
        index=True,
    )
    mediaconvert_job_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True,
    )
    transcode_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[str | None] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=True,
    )

    __table_args__ = (
        Index("ix_media_assets_uploaded_by_type", "uploaded_by", "asset_type"),
        Index("ix_media_assets_status_created", "transcode_status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<MediaAsset {self.asset_id} type={self.asset_type} status={self.transcode_status}>"
