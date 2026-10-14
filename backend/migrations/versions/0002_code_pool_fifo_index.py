"""为分配取码的 FIFO 顺序补索引。

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12

背景：分配取码走 `WHERE status='unallocated' AND product_id=? ORDER BY
import_batch_id, id LIMIT n FOR UPDATE SKIP LOCKED`。没有覆盖该排序的索引时
MySQL 需要 filesort，而 FOR UPDATE 会在应用 LIMIT 之前锁住全部匹配行——
SKIP LOCKED 于是把整池都跳过，并发分配互相饿死并误报"库存不足"。
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_code_pool_fifo",
        "code",
        ["status", "product_id", "import_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_code_pool_fifo", table_name="code")
