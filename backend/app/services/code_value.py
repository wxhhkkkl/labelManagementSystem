"""码值格式规则（FR-015）。

纯函数，不依赖数据库或 Excel 库，便于单测覆盖边界值。
"""

import re
from enum import StrEnum

# FR-015：100 位以内、仅含数字与字母
CODE_MAX_LENGTH = 100

# 限定 ASCII 字母数字。中文、全角字符、符号一律拒绝——
# 码要落到二维码/条码上，非 ASCII 会在打印环节引入编码歧义。
_ALNUM = re.compile(r"^[A-Za-z0-9]+$")


class CodeValueError(StrEnum):
    """失败明细里记录的错误类型（FR-021）。"""

    EMPTY = "EMPTY"
    TOO_LONG = "TOO_LONG"
    FORMAT = "FORMAT"


def normalize(raw: object) -> str:
    """把单元格值规整成待校验的字符串。

    Excel 会把纯数字码读成 int/float（如 12345.0），这里统一转成文本；
    前后空白也一并去掉——导入文件里带上空白是常见情况。
    """
    if raw is None:
        return ""
    if isinstance(raw, bool):
        # bool 是 int 的子类，必须挡住，否则 True 会变成 "True"
        return ""
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, float):
        # 12345.0 -> "12345"，避免把浮点尾数带进码值
        return str(int(raw)) if raw.is_integer() else ""
    return str(raw).strip()


def validate(value: str) -> CodeValueError | None:
    """返回错误类型；通过校验则返回 None。"""
    if not value:
        return CodeValueError.EMPTY
    if len(value) > CODE_MAX_LENGTH:
        return CodeValueError.TOO_LONG
    if not _ALNUM.match(value):
        return CodeValueError.FORMAT
    return None


def check(raw: object) -> tuple[str, CodeValueError | None]:
    """规整并校验，返回 (规整后的码值, 错误类型或 None)。"""
    value = normalize(raw)
    return value, validate(value)


ERROR_MESSAGES: dict[CodeValueError, str] = {
    CodeValueError.EMPTY: "码值为空",
    CodeValueError.TOO_LONG: f"码值超过 {CODE_MAX_LENGTH} 位",
    CodeValueError.FORMAT: "码值只能包含数字与字母",
}
