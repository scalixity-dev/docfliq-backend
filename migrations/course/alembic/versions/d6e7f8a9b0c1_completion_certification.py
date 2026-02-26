"""Completion customization, module unlock, and module-level certification.

Revision ID: d6e7f8a9b0c1
Revises: c4d5e6f7a8b9
Create Date: 2026-02-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "d6e7f8a9b0c1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────
    op.execute("CREATE TYPE completion_mode AS ENUM ('DEFAULT', 'CUSTOM')")
    op.execute(
        "CREATE TYPE module_unlock_mode AS ENUM ('ALL_UNLOCKED', 'SEQUENTIAL', 'CUSTOM')"
    )
    op.execute(
        "CREATE TYPE certification_mode AS ENUM ('COURSE', 'MODULE', 'BOTH', 'NONE')"
    )
    op.execute("CREATE TYPE certificate_type AS ENUM ('COURSE', 'MODULE')")

    # ── courses ──────────────────────────────────────────────────────────
    op.add_column(
        "courses",
        sa.Column(
            "completion_mode",
            sa.Enum("DEFAULT", "CUSTOM", name="completion_mode", create_type=False),
            nullable=False,
            server_default="DEFAULT",
        ),
    )
    op.add_column(
        "courses",
        sa.Column(
            "module_unlock_mode",
            sa.Enum(
                "ALL_UNLOCKED", "SEQUENTIAL", "CUSTOM",
                name="module_unlock_mode", create_type=False,
            ),
            nullable=False,
            server_default="ALL_UNLOCKED",
        ),
    )
    op.add_column(
        "courses",
        sa.Column(
            "certification_mode",
            sa.Enum(
                "COURSE", "MODULE", "BOTH", "NONE",
                name="certification_mode", create_type=False,
            ),
            nullable=False,
            server_default="COURSE",
        ),
    )
    op.add_column(
        "courses",
        sa.Column("cert_template", sa.String(100), nullable=True),
    )
    op.add_column(
        "courses",
        sa.Column("cert_custom_title", sa.String(300), nullable=True),
    )

    # ── course_modules ───────────────────────────────────────────────────
    op.add_column(
        "course_modules",
        sa.Column(
            "prerequisite_module_ids",
            sa.ARRAY(UUID(as_uuid=True)),
            nullable=True,
        ),
    )
    op.add_column(
        "course_modules",
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "course_modules",
        sa.Column("cert_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "course_modules",
        sa.Column("cert_template", sa.String(100), nullable=True),
    )
    op.add_column(
        "course_modules",
        sa.Column("cert_custom_title", sa.String(300), nullable=True),
    )

    # ── certificates ─────────────────────────────────────────────────────
    op.add_column(
        "certificates",
        sa.Column(
            "module_id",
            UUID(as_uuid=True),
            sa.ForeignKey("course_modules.module_id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "certificates",
        sa.Column(
            "certificate_type",
            sa.Enum("COURSE", "MODULE", name="certificate_type", create_type=False),
            nullable=False,
            server_default="COURSE",
        ),
    )
    op.add_column(
        "certificates",
        sa.Column("module_title", sa.String(300), nullable=True),
    )
    op.add_column(
        "certificates",
        sa.Column("template_used", sa.String(100), nullable=True),
    )

    # Drop the old unique constraint on enrollment_id
    op.drop_constraint("certificates_enrollment_id_key", "certificates", type_="unique")

    # Partial unique indexes: one course cert per enrollment, one module cert per (enrollment, module)
    op.execute(
        "CREATE UNIQUE INDEX uq_cert_enrollment_course "
        "ON certificates (enrollment_id) WHERE module_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_cert_enrollment_module "
        "ON certificates (enrollment_id, module_id) WHERE module_id IS NOT NULL"
    )
    op.create_index(
        "ix_certificates_module_id", "certificates", ["module_id"],
        postgresql_where=sa.text("module_id IS NOT NULL"),
    )

    # ── enrollments ──────────────────────────────────────────────────────
    op.add_column(
        "enrollments",
        sa.Column("certificate_recipient_name", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    # enrollments
    op.drop_column("enrollments", "certificate_recipient_name")

    # certificates
    op.drop_index("ix_certificates_module_id", table_name="certificates")
    op.execute("DROP INDEX IF EXISTS uq_cert_enrollment_module")
    op.execute("DROP INDEX IF EXISTS uq_cert_enrollment_course")
    op.create_unique_constraint(
        "certificates_enrollment_id_key", "certificates", ["enrollment_id"]
    )
    op.drop_column("certificates", "template_used")
    op.drop_column("certificates", "module_title")
    op.drop_column("certificates", "certificate_type")
    op.drop_column("certificates", "module_id")

    # course_modules
    op.drop_column("course_modules", "cert_custom_title")
    op.drop_column("course_modules", "cert_template")
    op.drop_column("course_modules", "cert_enabled")
    op.drop_column("course_modules", "is_required")
    op.drop_column("course_modules", "prerequisite_module_ids")

    # courses
    op.drop_column("courses", "cert_custom_title")
    op.drop_column("courses", "cert_template")
    op.drop_column("courses", "certification_mode")
    op.drop_column("courses", "module_unlock_mode")
    op.drop_column("courses", "completion_mode")

    # enums
    op.execute("DROP TYPE IF EXISTS certificate_type")
    op.execute("DROP TYPE IF EXISTS certification_mode")
    op.execute("DROP TYPE IF EXISTS module_unlock_mode")
    op.execute("DROP TYPE IF EXISTS completion_mode")
