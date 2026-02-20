"""
Identity service — SQLAlchemy ORM models for the verification domain.

Tables owned by this module:
  - user_verifications   Document upload + admin review records
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.database.postgres import Base

from app.auth.constants import DocumentType, VerificationDocStatus

if TYPE_CHECKING:
    from app.auth.models import User


class UserVerification(Base):
    """
    A single verification document submission by a user.

    State machine:
      PENDING  →  APPROVED  (admin approves)
      PENDING  →  REJECTED  (admin rejects with reason)
      REJECTED →  PENDING   (user re-uploads a new document; old row is archived)

    The reviewed_by FK is nullable because documents start without a reviewer.
    ondelete=SET NULL ensures the row survives even if the reviewing admin is
    later deleted from the system.
    """

    __tablename__ = "user_verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_user_verifications_user_id",
        ),
        nullable=False,
        index=True,
    )
    document_type: Mapped[DocumentType] = mapped_column(
        sa.Enum(DocumentType, name="documenttype", create_type=False),
        nullable=False,
    )
    # S3 object URL (presigned PUT → confirmed via /verify/confirm endpoint)
    document_url: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    status: Mapped[VerificationDocStatus] = mapped_column(
        sa.Enum(VerificationDocStatus, name="verificationdocstatus", create_type=False),
        nullable=False,
        default=VerificationDocStatus.PENDING,
        server_default=sa.text("'pending'"),
        index=True,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_user_verifications_reviewed_by",
        ),
        nullable=True,
    )
    review_notes: Mapped[str | None] = mapped_column(sa.Text(), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    # Explicit foreign_keys required because two FKs point to users.id.
    # String-based class reference avoids a circular import at module level;
    # TYPE_CHECKING guard provides correct type hints for static analysis.
    user: Mapped[User] = relationship(
        "User",
        foreign_keys=[user_id],
    )
    reviewer: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[reviewed_by],
    )
