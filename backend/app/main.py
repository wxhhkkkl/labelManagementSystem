"""应用入口。

启动钩子把残留的中断导入批次置为 interrupted（research.md R3，本期不做断点续传）。
"""

import logging
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.v1.router import api_router
from app.core.config import assert_production_ready
from app.core.errors import ApiError, ErrorCode, error_body
from app.models.base import utcnow
from app.tasks import import_worker, lock_timeout_sweeper, task_expiry

logger = logging.getLogger(__name__)


def _mark_interrupted_imports() -> None:
    """服务重启后，残留的 processing 批次不可能再继续，标记为 interrupted。"""
    from app.core.db import SessionLocal
    from app.models.import_batch import ImportBatch

    try:
        with SessionLocal() as db:
            db.execute(
                update(ImportBatch)
                .where(ImportBatch.status == "processing")
                .values(status="interrupted", finished_at=utcnow())
            )
            db.commit()
    except Exception:  # noqa: BLE001
        # 数据库尚未就绪时不应阻塞服务启动（例如首次部署、迁移未执行）
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 先过安全闸：配置不安全时宁可起不来，也不要带着可伪造的密钥对外服务
    assert_production_ready()
    _mark_interrupted_imports()
    import_worker.start_worker()
    lock_timeout_sweeper.start_sweeper()
    task_expiry.start_expiry()
    try:
        yield
    finally:
        task_expiry.stop_expiry()
        lock_timeout_sweeper.stop_sweeper()
        import_worker.stop_worker()


app = FastAPI(title="打印管理系统", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------- 越权留痕


def _session_for_audit() -> tuple[Session, bool]:
    """给越权留痕取一个会话，返回 (会话, 是否由本函数创建)。

    测试里 get_db 被替换成测试库会话，这里必须**沿用同一个覆盖**——
    否则审计记录会写进生产库，那比不写还危险。

    第二个返回值很关键：**借来的会话不能关**。测试用的是共享夹具会话，
    关掉它会让后续断言全部变成 DetachedInstanceError。
    """
    from app.core.db import SessionLocal, get_db

    override = app.dependency_overrides.get(get_db)
    if override is not None:
        return override(), False
    return SessionLocal(), True


def _identify(request: Request) -> tuple[int, str] | None:
    """从 Bearer 令牌里解析出 (user_id, role)。

    解析不出来（未登录或令牌无效）就返回 None——无法归因的记录不写，
    与登录失败那条限制保持一致。
    """
    from app.core.security import decode_token

    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.InvalidTokenError:
        return None
    try:
        return int(payload["sub"]), str(payload.get("role", ""))
    except (KeyError, TypeError, ValueError):
        return None


def _record_denied(request: Request, message: str) -> None:
    """FR-007：越权请求 MUST 写入操作日志。

    写在全局异常处理器里而不是各个接口里——越权校验散落在服务层各处，
    逐个补埋点必然会漏。
    """
    from app.services import audit

    identity = _identify(request)
    if identity is None:
        return

    operator_id, role = identity
    try:
        db, owned = _session_for_audit()
    except Exception:  # noqa: BLE001
        return

    try:
        audit.record_denied(
            db,
            operator_id=operator_id,
            role=role,
            action="access.denied",
            # 路径借 target_type 落库，便于事后按接口排查
            target_type=f"{request.method} {request.url.path}"[:64],
            ip=request.client.host if request.client else None,
        )
        db.commit()
    except Exception:  # noqa: BLE001
        # 留痕失败不能影响给调用方的响应
        if owned:
            db.rollback()
    finally:
        # 只关自己开的会话；借来的（测试夹具）必须原样留着
        if owned:
            db.close()


@app.exception_handler(ApiError)
async def business_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    if exc.error_code == ErrorCode.FORBIDDEN_SCOPE:
        _record_denied(request, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.error_code, exc.message, exc.details),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """把请求体校验失败转成统一错误体，前端可直接展示出错的字段。"""
    errors = [
        {
            "loc": [str(part) for part in err.get("loc", ())],
            "msg": str(err.get("msg", "")),
            "type": str(err.get("type", "")),
        }
        for err in exc.errors()
    ]
    if request.url.path.startswith("/api/v1/templates"):
        # 模板内容不敏感；记录 input 便于定位编辑器产出的非法字段
        logger.warning(
            "template validation failed: %s %s %s",
            request.method,
            request.url.path,
            exc.errors(),
        )
    first = errors[0] if errors else {"loc": [], "msg": "请求参数不合法"}
    field = ".".join(part for part in first["loc"] if part != "body")
    message = f"{field}: {first['msg']}" if field else first["msg"]
    return JSONResponse(
        status_code=422,
        content=error_body(ErrorCode.VALIDATION_ERROR, message, {"errors": errors}),
    )


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "服务端内部错误"),
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(api_router)
