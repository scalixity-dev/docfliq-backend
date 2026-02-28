"""Refactor userrole enum: 6 roles → 4 roles.

doctor_specialist + doctor_gp → physician
nurse + student + pharmacist → non_physician
NEW: association
admin → admin (unchanged)

Revision ID: 011
Revises: 010
Create Date: 2026-02-23
"""
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename old enum type
    op.execute("ALTER TYPE userrole RENAME TO userrole_old")

    # 2. Create new enum type
    op.execute(
        "CREATE TYPE userrole AS ENUM "
        "('physician', 'association', 'non_physician', 'admin')"
    )

    # 3. Migrate the column, mapping old values to new
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE userrole
        USING (
            CASE role::text
                WHEN 'doctor_specialist' THEN 'physician'::userrole
                WHEN 'doctor_gp'         THEN 'physician'::userrole
                WHEN 'nurse'             THEN 'non_physician'::userrole
                WHEN 'student'           THEN 'non_physician'::userrole
                WHEN 'pharmacist'        THEN 'non_physician'::userrole
                WHEN 'admin'             THEN 'admin'::userrole
            END
        )
        """
    )

    # 4. Drop the old enum type
    op.execute("DROP TYPE userrole_old")


def downgrade() -> None:
    # Reverse: recreate old enum and map back
    op.execute("ALTER TYPE userrole RENAME TO userrole_new")
    op.execute(
        "CREATE TYPE userrole AS ENUM "
        "('doctor_specialist', 'doctor_gp', 'nurse', 'student', 'pharmacist', 'admin')"
    )
    op.execute(
        """
        ALTER TABLE users
        ALTER COLUMN role TYPE userrole
        USING (
            CASE role::text
                WHEN 'physician'     THEN 'doctor_specialist'::userrole
                WHEN 'association'   THEN 'student'::userrole
                WHEN 'non_physician' THEN 'student'::userrole
                WHEN 'admin'         THEN 'admin'::userrole
            END
        )
        """
    )
    op.execute("DROP TYPE userrole_new")
