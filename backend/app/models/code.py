"""码 —— 核心实体。

状态机见 app/services/code_state.py，语意见 data-model.md 与 FR-077/FR-078。
并发控制依赖本表的行锁 + 事务内"读-判-写"（research.md R2），
MUST NOT 使用"先查询再更新"的两段式写法。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

CodeStatus = Enum(
    "unallocated", "allocated", "printing", "printed", "voided", name="code_status"
)


class Code(PkMixin, TimestampMixin, Base):
    __tablename__ = "code"
    __table_args__ = (
        # 工位端"按产品查本公司已分配未打印"（FR-039）与看板四态聚合（FR-065）
        Index("ix_code_company_product_status", "company_id", "product_id", "status"),
        # 码池取码与批次查询（FR-025）
        Index("ix_code_status_batch", "status", "import_batch_id"),
        # 分配取码的 FIFO 顺序（FR-025）。
        # 这个索引不是可有可无的优化：没有它 MySQL 需要 filesort，
        # 而 FOR UPDATE 会在应用 LIMIT 之前锁住**全部**匹配行，
        # 导致 SKIP LOCKED 把整池都跳过——并发分配会退化成互相饿死。
        Index("ix_code_pool_fifo", "status", "product_id", "import_batch_id"),
    )

    # 100 位以内、仅数字与字母（FR-015）；全库唯一，已作废的码仍占用该约束
    code_value: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(CodeStatus, nullable=False, default="unallocated")
    product_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("product.id"), nullable=False)
    company_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("company.id"))
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batch.id"), nullable=False
    )
    current_allocation_order_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("allocation_order.id"), index=True
    )

    # 打印预占（FR-042）与超时回退（FR-047）
    locked_at: Mapped[datetime | None] = mapped_column(DateTime)
    locked_workstation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workstation.id")
    )
    # 补打派发目标（FR-055）
    last_printed_workstation_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("workstation.id")
    )

    print_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reprint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    voided_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("user.id"))
    void_reason: Mapped[str | None] = mapped_column(String(255))
