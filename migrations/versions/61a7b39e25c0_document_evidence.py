"""Keep original extraction evidence and the submitted document digest."""

import sqlalchemy as sa
from alembic import op

revision = "61a7b39e25c0"
down_revision = "5f2c9b0a7e41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sarvam_document_jobs", sa.Column("document_sha256", sa.String(64), nullable=True))
    op.add_column("sarvam_document_jobs", sa.Column("original_extraction", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sarvam_document_jobs", "original_extraction")
    op.drop_column("sarvam_document_jobs", "document_sha256")
