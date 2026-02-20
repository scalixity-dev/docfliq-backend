"""Add role-specific profile fields

Revision ID: 005
Revises: 004
Create Date: 2026-02-19

Changes:
  - users.hospital_name         VARCHAR(200) NULL — for Doctor Specialist, Doctor GP, Nurse
  - users.certification         VARCHAR(200) NULL — for Nurse (certification / specialty area)
  - users.university            VARCHAR(200) NULL — for Student
  - users.graduation_year       SMALLINT     NULL — for Student (expected graduation year)
  - users.student_id            VARCHAR(100) NULL — for Student (university-issued ID)
  - users.pharmacist_license_number VARCHAR(100) NULL — for Pharmacist (separate from medical)
  - users.pharmacy_name         VARCHAR(200) NULL — for Pharmacist
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("hospital_name", sa.String(200), nullable=True))
    op.add_column("users", sa.Column("certification", sa.String(200), nullable=True))
    op.add_column("users", sa.Column("university", sa.String(200), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "graduation_year",
            sa.SmallInteger(),
            nullable=True,
            comment="Expected or actual graduation year (Student role)",
        ),
    )
    op.add_column("users", sa.Column("student_id", sa.String(100), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "pharmacist_license_number",
            sa.String(100),
            nullable=True,
            unique=True,
        ),
    )
    op.add_column("users", sa.Column("pharmacy_name", sa.String(200), nullable=True))

    # Partial unique index — pharmacist_license_number must be unique when set
    op.create_index(
        "ix_users_pharmacist_license_number",
        "users",
        ["pharmacist_license_number"],
        unique=True,
        postgresql_where=sa.text("pharmacist_license_number IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_pharmacist_license_number", table_name="users")
    op.drop_column("users", "pharmacy_name")
    op.drop_column("users", "pharmacist_license_number")
    op.drop_column("users", "student_id")
    op.drop_column("users", "graduation_year")
    op.drop_column("users", "university")
    op.drop_column("users", "certification")
    op.drop_column("users", "hospital_name")
