"""跨工位共享、按中国业务日期递增的流水号。调用方必须持有码的行锁。"""

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from app.models.print_identity import PrintDailyCounter, PrintIdentity


def business_date(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(timezone(timedelta(hours=8))).date()


def requires_identity(document: dict) -> bool:
    return any(
        el.get("type") == "serial"
        or (el.get("type") == "date" and el.get("date_source", "print") != "fixed")
        or el.get("field_name") in ("print_date", "serial_no")
        for el in document.get("elements", [])
    )


def lock_daily_counter(db: Session, day: date) -> None:
    """打印批次先锁当日计数器，再锁码，避免不同批次形成码/计数器锁循环。"""
    stmt = insert(PrintDailyCounter).values(print_date=day, last_number=0)
    db.execute(stmt.on_duplicate_key_update(last_number=PrintDailyCounter.last_number))
    db.execute(
        select(PrintDailyCounter.print_date)
        .where(
            PrintDailyCounter.print_date == day,
        )
        .with_for_update()
    ).scalar_one()


def ensure_identity(db: Session, code_id: int, day: date | None = None) -> PrintIdentity:
    identity = db.get(PrintIdentity, code_id)
    if identity is not None:
        return identity
    day = day or business_date()
    # 原子 UPSERT 处理当天第一条记录的并发插入，行锁保持到打印预占事务提交。
    stmt = insert(PrintDailyCounter).values(print_date=day, last_number=1)
    db.execute(stmt.on_duplicate_key_update(last_number=PrintDailyCounter.last_number + 1))
    number = db.execute(
        select(PrintDailyCounter.last_number)
        .where(
            PrintDailyCounter.print_date == day,
        )
        .with_for_update()
    ).scalar_one()
    identity = PrintIdentity(code_id=code_id, print_date=day, serial_no=number)
    db.add(identity)
    db.flush()
    return identity


def fields_for(db: Session, code_id: int) -> dict[str, str]:
    identity = db.get(PrintIdentity, code_id)
    if identity is None:
        return {}
    return {"print_date": identity.print_date.isoformat(), "serial_no": str(identity.serial_no)}
