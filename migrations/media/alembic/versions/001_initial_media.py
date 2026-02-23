"""Initial media_assets table

Revision ID: 001_initial_media
Revises:
Create Date: 2026-02-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "001_initial_media"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    asset_type = sa.Enum(
        "VIDEO", "IMAGE", "PDF", "SCORM",
        name="assettype",
    )
    transcode_status = sa.Enum(
        "PENDING", "PROCESSING", "COMPLETED", "FAILED",
        name="transcodestatus",
    )

    asset_type.create(op.get_bind(), checkfirst=True)
    transcode_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "media_assets",
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("uploaded_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "asset_type",
            asset_type,
            nullable=False,
        ),
        sa.Column("original_url", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("processed_url", sa.String(500), nullable=True),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column("hls_url", sa.String(500), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("duration_secs", sa.Integer, nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column(
            "transcode_status",
            transcode_status,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("mediaconvert_job_id", sa.String(100), nullable=True),
        sa.Column("transcode_error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )

    # Indexes
    op.create_index("ix_media_assets_uploaded_by", "media_assets", ["uploaded_by"])
    op.create_index("ix_media_assets_asset_type", "media_assets", ["asset_type"])
    op.create_index("ix_media_assets_transcode_status", "media_assets", ["transcode_status"])
    op.create_index(
        "ix_media_assets_uploaded_by_type",
        "media_assets",
        ["uploaded_by", "asset_type"],
    )
    op.create_index(
        "ix_media_assets_status_created",
        "media_assets",
        ["transcode_status", "created_at"],
    )
    op.create_index(
        "ix_media_assets_mediaconvert_job_id",
        "media_assets",
        ["mediaconvert_job_id"],
    )


def downgrade() -> None:
    op.drop_table("media_assets")
    op.execute("DROP TYPE IF EXISTS transcodestatus")
    op.execute("DROP TYPE IF EXISTS assettype")
