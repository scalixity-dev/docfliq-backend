"""
Social graph domain — SQLAlchemy ORM models.

Tables:
  follows  — unidirectional follow edges (follower → following)
  blocks   — block edges (blocker blocks blocked)
  mutes    — mute edges (muter mutes muted)
  reports  — user / content reports submitted for admin review
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database.postgres import Base
from app.social_graph.constants import ReportStatus, ReportTargetType


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Follow(Base):
    __tablename__ = "follows"

    follow_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    follower_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    following_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_now
    )

    # Relationships for eager loading user info
    follower = relationship("User", foreign_keys=[follower_id], lazy="raise")
    following = relationship("User", foreign_keys=[following_id], lazy="raise")

    __table_args__ = (
        sa.UniqueConstraint("follower_id", "following_id", name="uq_follows_pair"),
        sa.CheckConstraint("follower_id != following_id", name="ck_follows_no_self"),
        sa.Index("idx_follows_follower_id", "follower_id"),
        sa.Index("idx_follows_following_id", "following_id"),
    )


class Block(Base):
    __tablename__ = "blocks"

    block_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    blocker_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_now
    )

    blocker = relationship("User", foreign_keys=[blocker_id], lazy="raise")
    blocked = relationship("User", foreign_keys=[blocked_id], lazy="raise")

    __table_args__ = (
        sa.UniqueConstraint("blocker_id", "blocked_id", name="uq_blocks_pair"),
        sa.CheckConstraint("blocker_id != blocked_id", name="ck_blocks_no_self"),
        sa.Index("idx_blocks_blocker_id", "blocker_id"),
        sa.Index("idx_blocks_blocked_id", "blocked_id"),
    )


class Mute(Base):
    __tablename__ = "mutes"

    mute_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    muter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    muted_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_now
    )

    muter = relationship("User", foreign_keys=[muter_id], lazy="raise")
    muted = relationship("User", foreign_keys=[muted_id], lazy="raise")

    __table_args__ = (
        sa.UniqueConstraint("muter_id", "muted_id", name="uq_mutes_pair"),
        sa.CheckConstraint("muter_id != muted_id", name="ck_mutes_no_self"),
        sa.Index("idx_mutes_muter_id", "muter_id"),
        sa.Index("idx_mutes_muted_id", "muted_id"),
    )


class Report(Base):
    __tablename__ = "reports"

    report_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[ReportTargetType] = mapped_column(
        PgEnum(
            ReportTargetType,
            name="reporttargettype",
            create_type=False,
        ),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        PgEnum(
            ReportStatus,
            name="reportstatus",
            create_type=False,
        ),
        nullable=False,
        default=ReportStatus.OPEN,
        index=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action_taken: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, default=_now
    )

    reporter = relationship("User", foreign_keys=[reporter_id], lazy="raise")
    reviewer = relationship("User", foreign_keys=[reviewed_by], lazy="raise")

    __table_args__ = (
        sa.Index("idx_reports_reporter_id", "reporter_id"),
        sa.Index("idx_reports_status", "status"),
        sa.Index("idx_reports_target", "target_type", "target_id"),
    )
