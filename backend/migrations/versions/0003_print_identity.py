"""持久化每日打印流水号及首次打印日期。

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "print_daily_counter",
        sa.Column("print_date", sa.Date(), primary_key=True),
        sa.Column("last_number", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "print_identity",
        sa.Column("code_id", sa.BigInteger(), sa.ForeignKey("code.id"), primary_key=True),
        sa.Column("print_date", sa.Date(), nullable=False),
        sa.Column("serial_no", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("print_date", "serial_no", name="uq_print_identity_daily_serial"),
    )


def downgrade():
    op.drop_table("print_identity")
    op.drop_table("print_daily_counter")
