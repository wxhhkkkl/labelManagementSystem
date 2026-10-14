"""T111：补打任务的过期清理。

工位可能被停用或长期离线，派发给它的补打任务会一直挂在 pending。
不清理的话，工位几天后恢复上线会把陈年任务翻出来执行——
那张标签早就没意义了，而且码可能已经被作废。
"""

import logging
import threading

from app.core.config import get_settings
from app.services import print_task as print_task_service

logger = logging.getLogger(__name__)

SCAN_INTERVAL_SECONDS = 300

_stop = threading.Event()
_thread: threading.Thread | None = None


def run_once() -> int:
    """跑一轮清理，返回过期的任务数。供测试直接调用。"""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        expired = print_task_service.expire_stale_tasks(db)
        db.commit()
    if expired:
        logger.info("过期补打任务 %s 条", expired)
    return expired


def _loop() -> None:
    while not _stop.wait(SCAN_INTERVAL_SECONDS):
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("补打任务过期清理失败")


def start_expiry() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="print-task-expiry", daemon=True)
    _thread.start()
    logger.info("补打任务过期清理已启动（TTL %s 秒）", get_settings().print_task_ttl_seconds)


def stop_expiry() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=5)
