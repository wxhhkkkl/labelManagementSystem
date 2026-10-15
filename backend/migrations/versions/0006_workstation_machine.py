"""Bind a workstation to one persistent client machine identity."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workstation", sa.Column("machine_id", sa.String(36), nullable=True))
    op.create_unique_constraint("uq_workstation_machine_id", "workstation", ["machine_id"])


def downgrade():
    op.drop_constraint("uq_workstation_machine_id", "workstation", type_="unique")
    op.drop_column("workstation", "machine_id")
