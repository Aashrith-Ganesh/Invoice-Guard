"""Record the approving owner and exact validation run.

Revision ID: 3775fe1a4b08
Revises: dd75dbe236c5
"""

from alembic import op
import sqlalchemy as sa

revision = "3775fe1a4b08"
down_revision = "dd75dbe236c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical records have no reliable owner or validation-run binding.
    op.add_column("approvals", sa.Column("owner_id", sa.String(), nullable=True))
    op.add_column("approvals", sa.Column("validation_run_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("approvals", "validation_run_id")
    op.drop_column("approvals", "owner_id")
