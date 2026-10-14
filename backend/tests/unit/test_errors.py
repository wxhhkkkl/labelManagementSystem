"""T031：统一错误响应格式与错误码映射。"""

import pytest

from app.core.errors import STATUS_BY_CODE, ApiError, ErrorCode, error_body


class TestErrorBodyShape:
    def test_has_exactly_the_contract_fields(self):
        body = error_body(ErrorCode.CODE_ALREADY_PRINTED, "该码已打印")
        assert set(body) == {"error_code", "message", "details"}
        assert body["error_code"] == "CODE_ALREADY_PRINTED"
        assert body["message"] == "该码已打印"
        assert body["details"] == {}

    def test_details_defaults_to_empty_dict_not_none(self):
        # 契约要求 details 始终是对象，前端可无条件访问
        assert error_body("NOT_FOUND", "x")["details"] == {}

    def test_details_passed_through(self):
        body = error_body("NOT_FOUND", "x", {"available": 12})
        assert body["details"] == {"available": 12}


class TestApiError:
    def test_status_code_comes_from_registry(self):
        err = ApiError(ErrorCode.FORBIDDEN_SCOPE, "越权")
        assert err.status_code == 403

    def test_conflict_codes_are_409(self):
        for code in (
            ErrorCode.CODE_ALREADY_PRINTED,
            ErrorCode.CODE_LOCKED,
            ErrorCode.CODE_NOT_PRINTED,
            ErrorCode.CODE_VOIDED,
            ErrorCode.WORKSTATION_OFFLINE,
            ErrorCode.PRODUCT_HAS_ALLOCATED_CODES,
        ):
            assert ApiError(code, "x").status_code == 409

    def test_validation_error_is_422(self):
        assert ApiError(ErrorCode.VALIDATION_ERROR, "x").status_code == 422

    def test_unknown_error_code_is_rejected_at_construction(self):
        # 防止拼错错误码后静默返回 500
        with pytest.raises(ValueError):
            ApiError("THIS_CODE_DOES_NOT_EXIST", "x")


class TestErrorCodeRegistry:
    def test_every_declared_code_has_an_http_status(self):
        declared = {
            name: value
            for name, value in vars(ErrorCode).items()
            if not name.startswith("_") and isinstance(value, str)
        }
        missing = set(declared.values()) - set(STATUS_BY_CODE)
        assert missing == set()

    def test_contract_error_codes_are_all_present(self):
        # 与 contracts/README.md 的"关键错误码"表保持一致
        required = {
            "INVALID_CREDENTIALS",
            "ACCOUNT_DISABLED",
            "FORBIDDEN_SCOPE",
            "CODE_ALREADY_PRINTED",
            "CODE_LOCKED",
            "CODE_NOT_PRINTED",
            "CODE_VOIDED",
            "REASON_REQUIRED",
            "WORKSTATION_OFFLINE",
            "WORKSTATION_DISABLED",
            "PRODUCT_HAS_ALLOCATED_CODES",
            "IMPORT_CODE_SET_MISMATCH",
            "IMPORT_DUPLICATE_CODE",
            "TEMPLATE_VERSION_FROZEN",
        }
        assert required.issubset(set(STATUS_BY_CODE))
