"""T060：导入失败明细的写出与读取。

用 CSV（UTF-8 BOM）而不是 xlsx：10 万条失败明细写成 xlsx 会占用大量内存与时间，
而 CSV 可以边写边落盘。BOM 是为了让 Excel 双击打开时正确识别中文。
"""

import csv
from dataclasses import dataclass
from pathlib import Path

ERROR_HEADERS = ("行号", "码值", "产品编码", "错误类型", "说明")


@dataclass(frozen=True)
class RowError:
    row_no: int
    code_value: str
    product_code: str | None
    error_type: str
    message: str


def write_error_detail(path: Path, errors: list[RowError]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(ERROR_HEADERS)
        for err in errors:
            writer.writerow(
                [err.row_no, err.code_value, err.product_code or "", err.error_type, err.message]
            )


def read_error_detail(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [row for row in csv.reader(fh)]
