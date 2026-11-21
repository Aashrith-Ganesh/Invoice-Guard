from alembic import op
import sqlalchemy as sa

revision = "730aa1bc73cf"
down_revision = "dd75dbe236c5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("sarvam_document_jobs",
                    sa.Column("job_id", sa.String(36), primary_key=True),
                    sa.Column("business_id", sa.Integer(), sa.ForeignKey("businesses.id"), nullable=False))


def downgrade():
    op.drop_table("sarvam_document_jobs")
