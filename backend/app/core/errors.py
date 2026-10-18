"""统一错误码与异常映射。

错误码表与 contracts/README.md 的"关键错误码"表一一对应，两端据此做分支处理与断言。
"""

from fastapi import status


class ErrorCode:
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    FORBIDDEN_SCOPE = "FORBIDDEN_SCOPE"
    CODE_ALREADY_PRINTED = "CODE_ALREADY_PRINTED"
    CODE_LOCKED = "CODE_LOCKED"
    CODE_NOT_PRINTED = "CODE_NOT_PRINTED"
    CODE_VOIDED = "CODE_VOIDED"
    REASON_REQUIRED = "REASON_REQUIRED"
    WORKSTATION_OFFLINE = "WORKSTATION_OFFLINE"
    WORKSTATION_DISABLED = "WORKSTATION_DISABLED"
    WORKSTATION_BOUND = "WORKSTATION_BOUND"
    WORKSTATION_NOT_BOUND = "WORKSTATION_NOT_BOUND"
    WORKSTATION_BUSY = "WORKSTATION_BUSY"
    PRODUCT_HAS_ALLOCATED_CODES = "PRODUCT_HAS_ALLOCATED_CODES"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    IMPORT_CODE_SET_MISMATCH = "IMPORT_CODE_SET_MISMATCH"
    IMPORT_DUPLICATE_CODE = "IMPORT_DUPLICATE_CODE"
    TEMPLATE_VERSION_FROZEN = "TEMPLATE_VERSION_FROZEN"
    TEMPLATE_EDIT_DENIED = "TEMPLATE_EDIT_DENIED"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"


# 每个错误码对应的 HTTP 状态码
STATUS_BY_CODE: dict[str, int] = {
    ErrorCode.INVALID_CREDENTIALS: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.ACCOUNT_DISABLED: status.HTTP_403_FORBIDDEN,
    ErrorCode.FORBIDDEN_SCOPE: status.HTTP_403_FORBIDDEN,
    ErrorCode.CODE_ALREADY_PRINTED: status.HTTP_409_CONFLICT,
    ErrorCode.CODE_LOCKED: status.HTTP_409_CONFLICT,
    ErrorCode.CODE_NOT_PRINTED: status.HTTP_409_CONFLICT,
    ErrorCode.CODE_VOIDED: status.HTTP_409_CONFLICT,
    ErrorCode.REASON_REQUIRED: status.HTTP_400_BAD_REQUEST,
    ErrorCode.WORKSTATION_OFFLINE: status.HTTP_409_CONFLICT,
    ErrorCode.WORKSTATION_DISABLED: status.HTTP_409_CONFLICT,
    ErrorCode.WORKSTATION_BOUND: status.HTTP_409_CONFLICT,
    ErrorCode.WORKSTATION_NOT_BOUND: status.HTTP_403_FORBIDDEN,
    ErrorCode.WORKSTATION_BUSY: status.HTTP_409_CONFLICT,
    ErrorCode.PRODUCT_HAS_ALLOCATED_CODES: status.HTTP_409_CONFLICT,
    ErrorCode.INSUFFICIENT_STOCK: status.HTTP_409_CONFLICT,
    ErrorCode.IMPORT_CODE_SET_MISMATCH: status.HTTP_400_BAD_REQUEST,
    ErrorCode.IMPORT_DUPLICATE_CODE: status.HTTP_400_BAD_REQUEST,
    ErrorCode.TEMPLATE_VERSION_FROZEN: status.HTTP_409_CONFLICT,
    ErrorCode.TEMPLATE_EDIT_DENIED: status.HTTP_403_FORBIDDEN,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
}


class ApiError(Exception):
    """业务异常。抛出后由 handler 统一转换为契约约定的响应体。"""

    def __init__(self, error_code: str, message: str, details: dict | None = None) -> None:
        if error_code not in STATUS_BY_CODE:
            raise ValueError(f"未登记的错误码: {error_code}")
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    @property
    def status_code(self) -> int:
        return STATUS_BY_CODE[self.error_code]


def error_body(error_code: str, message: str, details: dict | None = None) -> dict:
    return {"error_code": error_code, "message": message, "details": details or {}}
