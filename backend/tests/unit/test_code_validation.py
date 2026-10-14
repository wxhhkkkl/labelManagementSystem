"""T047：码值校验规则（FR-015）。

覆盖 100 位边界、字符集、以及 Excel 读取带来的类型与空白问题。
"""

import pytest

from app.services.code_value import (
    CODE_MAX_LENGTH,
    CodeValueError,
    check,
    normalize,
    validate,
)


class TestBoundaries:
    def test_single_char_is_valid(self):
        assert validate("A") is None

    def test_exactly_100_chars_is_valid(self):
        assert validate("A" * CODE_MAX_LENGTH) is None

    def test_101_chars_is_too_long(self):
        assert validate("A" * (CODE_MAX_LENGTH + 1)) is CodeValueError.TOO_LONG

    def test_1000_chars_is_too_long(self):
        assert validate("9" * 1000) is CodeValueError.TOO_LONG

    def test_empty_is_rejected(self):
        assert validate("") is CodeValueError.EMPTY


class TestCharacterSet:
    @pytest.mark.parametrize("value", ["ABC123", "abc123", "0", "9", "a", "Z9z0"])
    def test_ascii_alnum_accepted(self, value):
        assert validate(value) is None

    @pytest.mark.parametrize(
        "value",
        [
            "AB C",       # 内部空格
            "AB-CD",      # 连字符
            "AB_CD",      # 下划线
            "AB.CD",      # 点
            "标签A001",    # 中文
            "ＡＢＣ",      # 全角字母
            "AB#CD",
            "AB\tCD",
        ],
    )
    def test_non_alnum_rejected(self, value):
        assert validate(value) is CodeValueError.FORMAT


class TestNormalize:
    def test_strips_surrounding_whitespace(self):
        assert normalize("  A001  ") == "A001"

    def test_excel_integer_becomes_text(self):
        assert normalize(12345) == "12345"

    def test_excel_float_without_fraction_becomes_integer_text(self):
        # openpyxl 会把纯数字单元格读成 float
        assert normalize(12345.0) == "12345"

    def test_float_with_fraction_is_rejected(self):
        # 12345.5 不是合法码值，规整为空后由 validate 拦下
        value, err = check(12345.5)
        assert value == ""
        assert err is CodeValueError.EMPTY

    def test_none_becomes_empty(self):
        assert normalize(None) == ""

    def test_boolean_is_not_treated_as_number(self):
        # bool 是 int 子类，必须单独挡住
        assert normalize(True) == ""


class TestCheck:
    def test_returns_normalized_value_and_no_error(self):
        assert check("  A001 ") == ("A001", None)

    def test_returns_error_for_bad_value(self):
        value, err = check("A-001")
        assert value == "A-001"
        assert err is CodeValueError.FORMAT

    def test_whitespace_only_is_empty(self):
        assert check("   ") == ("", CodeValueError.EMPTY)
