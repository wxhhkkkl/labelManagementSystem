"""T058：导入后台 worker（research.md R3）。

设计要点：
  * 解析与入库逻辑集中在 process_batch(db, batch_id)，**接收 Session 作为参数**。
    这样测试可以直接同步调用它，不必启动线程，也不会误连到应用主库。
  * 线程只负责从队列取 batch_id 再调用 process_batch —— 保持极薄。
  * 单工作线程：导入是重 CPU + 重 I/O 操作，并行跑多个只会互相拖垮。
"""

import logging
import queue
import threading
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.base import utcnow
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.import_batch import ImportBatch
from app.services import import_errors, import_validator
from app.services.import_errors import RowError

logger = logging.getLogger(__name__)

_queue: queue.Queue[int] = queue.Queue()
_thread: threading.Thread | None = None
_stop = threading.Event()


def storage_dir() -> Path:
    path = Path(get_settings().import_storage_dir)
    if not path.is_absolute():
        # 相对路径以 backend/ 为基准，与 alembic.ini 的定位方式保持一致
        path = Path(__file__).resolve().parent.parent.parent / path
    return path


def batch_dir(batch_no: str) -> Path:
    return storage_dir() / batch_no


def code_list_path(batch_no: str) -> Path:
    return batch_dir(batch_no) / "code_list.xlsx"


def mapping_path(batch_no: str) -> Path:
    return batch_dir(batch_no) / "mapping.xlsx"


def error_detail_path(batch_no: str) -> Path:
    return batch_dir(batch_no) / "errors.csv"


def _insert_codes(db: Session, batch: ImportBatch, outcome: import_validator.ValidationOutcome) -> None:
    """分块写入码与其导入事件。

    每块 flush 后回查 id：MySQL 的 executemany 不回传主键，而 CodeEvent 需要 code_id。
    """
    chunk_size = get_settings().import_batch_size
    accepted = outcome.accepted
    now = utcnow()

    for start in range(0, len(accepted), chunk_size):
        chunk = accepted[start : start + chunk_size]
        db.execute(
            insert(Code),
            [
                {
                    "code_value": row.code_value,
                    "status": "unallocated",
                    "product_id": row.product_id,
                    "import_batch_id": batch.id,
                }
                for row in chunk
            ],
        )
        db.flush()

        ids = dict(
            db.execute(
                select(Code.code_value, Code.id).where(
                    Code.code_value.in_([row.code_value for row in chunk])
                )
            ).all()
        )
        db.execute(
            insert(CodeEvent),
            [
                {
                    "code_id": ids[row.code_value],
                    "event_type": "imported",
                    "from_status": None,
                    "to_status": "unallocated",
                    "operator_id": batch.created_by,
                    "occurred_at": now,
                }
                for row in chunk
                if row.code_value in ids
            ],
        )
        db.flush()


def process_batch(db: Session, batch_id: int) -> None:
    """同步处理一个导入批次。线程与测试都走这里。"""
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        logger.warning("导入批次不存在: %s", batch_id)
        return
    if batch.status not in ("pending",):
        logger.info("批次 %s 状态为 %s，跳过", batch.batch_no, batch.status)
        return

    batch.status = "processing"
    batch.started_at = utcnow()
    db.flush()

    try:
        outcome = import_validator.validate(
            db,
            code_list_path=code_list_path(batch.batch_no),
            mapping_path=mapping_path(batch.batch_no),
            on_progress=lambda done: _update_progress(db, batch, done),
        )

        if not outcome.failed_batch:
            _insert_codes(db, batch, outcome)

        batch.total_rows = outcome.total_rows
        batch.processed_rows = outcome.total_rows
        batch.success_count = len(outcome.accepted) if not outcome.failed_batch else 0
        batch.failure_count = len(outcome.errors)

        if outcome.errors:
            detail = error_detail_path(batch.batch_no)
            import_errors.write_error_detail(detail, outcome.errors)
            batch.error_detail_path = str(detail)

        if outcome.failed_batch:
            batch.status = "failed"
            logger.info(
                "批次 %s 整批拒绝: %s", batch.batch_no, outcome.batch_error_message
            )
        else:
            batch.status = "succeeded"
    except Exception:
        batch.status = "failed"
        batch.finished_at = utcnow()
        db.flush()
        logger.exception("批次 %s 处理异常", batch.batch_no)
        raise
    else:
        batch.finished_at = utcnow()
    finally:
        db.flush()


def _update_progress(db: Session, batch: ImportBatch, processed: int) -> None:
    batch.processed_rows = processed
    db.flush()


def enqueue(batch_id: int) -> None:
    _queue.put(batch_id)


def _loop() -> None:
    while not _stop.is_set():
        try:
            batch_id = _queue.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            from app.core.db import SessionLocal

            with SessionLocal() as db:
                process_batch(db, batch_id)
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("导入任务失败: batch_id=%s", batch_id)
        finally:
            _queue.task_done()


def start_worker() -> None:
    """启动后台工作线程。重复调用无副作用。"""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="import-worker", daemon=True)
    _thread.start()
    logger.info("导入 worker 已启动")


def stop_worker() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=5)
