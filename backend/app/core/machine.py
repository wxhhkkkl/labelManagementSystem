"""Check persisted machine ownership for workstation operations."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.db import get_db
from app.core.deps import CurrentUser
from app.core.errors import ApiError, ErrorCode
from app.models.workstation import Workstation


async def check_bound_machine(
    request: Request, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
):
    if request.url.path.rsplit("/", 1)[-1] in ("bind", "binding", "available"):
        return
    workstation_id = request.query_params.get("workstation_id")
    if workstation_id is None and request.method in ("POST", "PUT"):
        payload = await request.json()
        workstation_id = payload.get("workstation_id") if isinstance(payload, dict) else None
    if workstation_id is None:
        return
    # Waiting on a synchronous database lock must never block the event loop:
    # the request owning that lock still needs the loop to dispatch/finish its handler.
    await run_in_threadpool(
        _check_machine_ownership,
        db,
        workstation_id,
        user.company_id,
        request.headers.get("X-LMS-Machine-ID"),
    )


def _check_machine_ownership(
    db: Session, workstation_id: str | int, company_id: int | None, machine_id: str | None
):
    try:
        ws = db.scalar(
            select(Workstation).where(Workstation.id == int(workstation_id)).with_for_update()
        )
    except (ValueError, TypeError):
        return
    if ws is not None:
        if ws.machine_id is None and (machine_id or ws.bound_at is not None):
            raise ApiError(ErrorCode.WORKSTATION_NOT_BOUND, "工位已解绑，请重新绑定本机工位")
        if ws.machine_id is not None:
            if ws.company_id != company_id:
                raise ApiError(ErrorCode.FORBIDDEN_SCOPE, "账号不属于该工位企业")
            if machine_id != ws.machine_id:
                raise ApiError(ErrorCode.WORKSTATION_NOT_BOUND, "本机未绑定该工位，请重新绑定")
