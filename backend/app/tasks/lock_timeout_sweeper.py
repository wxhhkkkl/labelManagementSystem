"""T092：打印锁超时扫描（FR-047 / FR-048）。

背景：工位软件可能崩溃、断电，或本地打印服务的成功回执丢失，导致码长期停在
`printing`。若不处理，该码既不能再打印，也不在"已分配未打印"里，等于凭空消失。

已知取舍（spec 明确接受）：超时自动回退优先保证工位能继续作业，代价是
"实际已出纸但回执丢失"时会重复出纸。该风险由 timeout_reverted 记录兜底可审计。
"""

import logging
import threading

from app.core.config import get_settings
from app.services import printing

logger = logging.getLogger(__name__)

# 扫描周期：比起 5 分钟的默认超时，1 分钟一轮足够及时且开销可忽略
SCAN_INTERVAL_SECONDS = 60

_stop = threading.Event()
_thread: threading.Thread | None = None


def run_once() -> int:
    """跑一轮扫描，返回回退的码数。供测试直接调用（不启动线程）。"""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        reverted = printing.sweep_expired(db)
        db.commit()
    if reverted:
        logger.info("超时回退 %s 个打印中的码", reverted)
    return reverted


def _loop() -> None:
    while not _stop.wait(SCAN_INTERVAL_SECONDS):
        try:
            run_once()
        except Exception:  # noqa: BLE001
            # 扫描失败不应终止线程，否则后续超时会永久堆积
            logger.exception("打印锁超时扫描失败")


def start_sweeper() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="print-lock-sweeper", daemon=True)
    _thread.start()
    logger.info(
        "打印锁超时扫描已启动（阈值 %s 秒）", get_settings().print_lock_timeout_seconds
    )


def stop_sweeper() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=5)
