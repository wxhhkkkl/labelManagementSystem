"""导入批次。异步导入的进度与结果载体（research.md R3）。

服务端重启后残留的 processing 记录会被置为 interrupted，不支持断点续传。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PkMixin, TimestampMixin

ImportBatchStatus = Enum(
    "pending", "processing", "succeeded", "failed", "interrupted", name="import_batch_status"
)


class ImportBatch(PkMixin, TimestampMixin, Base):
    __tablename__ = "import_batch"

    batch_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    code_list_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mapping_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        ImportBatchStatus, nullable=False, default="pending"
    )
    total_rows: Mapped[int | None] = mapped_column(Integer)
    processed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_detail_path: Mapped[str | None] = mapped_column(String(512))
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
