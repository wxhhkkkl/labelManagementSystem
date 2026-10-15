"""Store the production batch supplied when allocating labels.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "allocation_order", sa.Column("production_batch_no", sa.String(64), nullable=True)
    )


def downgrade():
    op.drop_column("allocation_order", "production_batch_no")
