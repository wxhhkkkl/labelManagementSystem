"""Import production batches per code from one workbook."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("code", sa.Column("production_batch_no", sa.String(64), nullable=True))
    op.add_column("import_batch", sa.Column("product_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_import_batch_product", "import_batch", "product", ["product_id"], ["id"]
    )


def downgrade():
    op.drop_constraint("fk_import_batch_product", "import_batch", type_="foreignkey")
    op.drop_column("import_batch", "product_id")
    op.drop_column("code", "production_batch_no")
