"""T057：导入校验流水线（FR-014 ~ FR-021）。

顺序：
  1. 两文件码集合必须完全一致（FR-014）——不一致即整批拒绝
  2. 逐行校验码值格式与长度（FR-015）
  3. 码值唯一：文件内重复 + 与库内已有码重复（FR-017）
  4. 对照关系引用的产品必须存在（FR-020）

失败明细会标明错误类型，覆盖 FR-021 要求的五类。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.models.product import Product
from app.services import code_value
from app.services.import_errors import RowError
from app.services.import_parser import iter_code_list, iter_mapping, iter_product_batch

# 与 FR-021 对应的错误类型
ERR_DUPLICATE_IN_FILE = "DUPLICATE_IN_FILE"
ERR_DUPLICATE_IN_DB = "DUPLICATE_IN_DB"
ERR_PRODUCT_NOT_FOUND = "PRODUCT_NOT_FOUND"
ERR_MISSING_IN_MAPPING = "MISSING_IN_MAPPING"
ERR_MISSING_IN_CODE_LIST = "MISSING_IN_CODE_LIST"

# 明细文件里最多列多少条集合差异——差异可能上万条，全列会让文件失去可读性
MISMATCH_SAMPLE_LIMIT = 500

_DUPLICATE_MESSAGES = {
    ERR_DUPLICATE_IN_FILE: "码值在本次文件中重复",
    ERR_DUPLICATE_IN_DB: "码值在系统中已存在",
}


@dataclass
class AcceptedRow:
    code_value: str
    product_id: int
    row_no: int
    production_batch_no: str | None = None


@dataclass
class ValidationOutcome:
    total_rows: int = 0
    accepted: list[AcceptedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    # 整批级失败：非空时不得入库任何码
    batch_error: str | None = None
    batch_error_message: str | None = None

    @property
    def failed_batch(self) -> bool:
        return self.batch_error is not None


def _chunked(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _existing_codes(db: Session, candidates: list[str]) -> set[str]:
    """按批查询库中已存在的码值。

    单条 IN 塞 10 万个参数会超出 MySQL 的占位符上限，必须分块。
    """
    from app.models.code import Code

    found: set[str] = set()
    batch_size = get_settings().import_batch_size
    for chunk in _chunked(candidates, batch_size):
        rows = db.execute(select(Code.code_value).where(Code.code_value.in_(chunk))).scalars()
        found.update(rows)
    return found


def _product_ids(db: Session) -> dict[str, int]:
    rows = db.execute(select(Product.code, Product.id)).all()
    return {code: pid for code, pid in rows}


def validate(
    db: Session,
    *,
    code_list_path: Path,
    mapping_path: Path,
    duplicate_policy: str | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> ValidationOutcome:
    settings = get_settings()
    policy = duplicate_policy or settings.import_duplicate_policy
    outcome = ValidationOutcome()

    # ---- 读取两个文件 ----
    code_rows: dict[str, int] = {}  # 码值 -> 首次出现的行号
    file_duplicates: dict[str, int] = {}  # 重复出现的码值 -> 行号
    for row_no, raw in iter_code_list(code_list_path):
        value, _ = code_value.check(raw)
        if not value:
            continue  # 空行/空单元格：格式校验阶段统一报
        if value in code_rows:
            file_duplicates.setdefault(value, row_no)
        else:
            code_rows[value] = row_no

    mapping: dict[str, tuple[str, int]] = {}  # 码值 -> (产品编码, 行号)
    mapping_value_errors: list[tuple[int, str, str]] = []
    for row_no, raw_code, raw_product in iter_mapping(mapping_path):
        value, err = code_value.check(raw_code)
        product_code = code_value.normalize(raw_product)
        if value:
            mapping.setdefault(value, (product_code, row_no))
        else:
            mapping_value_errors.append((row_no, code_value.normalize(raw_code), str(err)))

    outcome.total_rows = max(len(code_rows), len(mapping))
    if callable(on_progress):
        on_progress(outcome.total_rows)

    # ---- 1. 两文件码集合必须完全一致（FR-014）----
    missing_in_mapping = sorted(set(code_rows) - set(mapping))
    missing_in_code_list = sorted(set(mapping) - set(code_rows))
    if missing_in_mapping or missing_in_code_list:
        outcome.batch_error = ErrorCode.IMPORT_CODE_SET_MISMATCH
        outcome.batch_error_message = (
            f"码清单与对照关系文件的码集合不一致："
            f"仅存在于码清单 {len(missing_in_mapping)} 条，"
            f"仅存在于对照关系 {len(missing_in_code_list)} 条"
        )
        for value in missing_in_mapping[:MISMATCH_SAMPLE_LIMIT]:
            outcome.errors.append(
                RowError(
                    code_rows[value], value, None, ERR_MISSING_IN_MAPPING, "对照关系文件中缺少该码"
                )
            )
        for value in missing_in_code_list[:MISMATCH_SAMPLE_LIMIT]:
            _, row_no = mapping[value]
            outcome.errors.append(
                RowError(row_no, value, None, ERR_MISSING_IN_CODE_LIST, "码清单中缺少该码")
            )
        return outcome

    # ---- 2. 文件内重复（FR-017）----
    if file_duplicates:
        for value, row_no in sorted(file_duplicates.items(), key=lambda kv: kv[1]):
            outcome.errors.append(
                RowError(
                    row_no,
                    value,
                    mapping[value][0],
                    ERR_DUPLICATE_IN_FILE,
                    _DUPLICATE_MESSAGES[ERR_DUPLICATE_IN_FILE],
                )
            )
        if policy != "skip_row":
            outcome.batch_error = ErrorCode.IMPORT_DUPLICATE_CODE
            outcome.batch_error_message = f"本批次存在 {len(file_duplicates)} 个重复码值"
            return outcome

    # ---- 3. 与库内已有码重复（FR-017）----
    duplicates_in_db = _existing_codes(db, list(code_rows))
    if duplicates_in_db:
        for value in sorted(duplicates_in_db):
            outcome.errors.append(
                RowError(
                    code_rows[value],
                    value,
                    mapping[value][0],
                    ERR_DUPLICATE_IN_DB,
                    _DUPLICATE_MESSAGES[ERR_DUPLICATE_IN_DB],
                )
            )
        if policy != "skip_row":
            outcome.batch_error = ErrorCode.IMPORT_DUPLICATE_CODE
            outcome.batch_error_message = f"本批次有 {len(duplicates_in_db)} 个码值在系统中已存在"
            return outcome

    # ---- 4. 逐行校验并组装可入库行 ----
    products = _product_ids(db)
    rejected: set[str] = set()
    # 文件内重复：skip_row 语义是"保留首次出现、跳过重复行"，因此该码值仍可入库
    # 库内已存在：整条跳过（无论出现在文件里几次）
    if policy == "skip_row":
        rejected |= duplicates_in_db

    for row_no, raw_value, err in mapping_value_errors:
        outcome.errors.append(
            RowError(
                row_no,
                raw_value,
                None,
                err,
                code_value.ERROR_MESSAGES.get(err, "码值不合法") if err else "码值不合法",
            )
        )

    for value in sorted(code_rows, key=lambda v: code_rows[v]):
        if value in rejected:
            continue
        product_code, row_no = mapping[value]
        product_id = products.get(product_code)
        if product_id is None:
            outcome.errors.append(
                RowError(row_no, value, product_code, ERR_PRODUCT_NOT_FOUND, "产品编码不存在")
            )
            continue
        outcome.accepted.append(AcceptedRow(value, product_id, row_no))

    return outcome


def validate_product_batch(
    db: Session,
    *,
    code_list_path: Path,
    product_id: int,
    duplicate_policy: str | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> ValidationOutcome:
    outcome = ValidationOutcome()
    product = db.get(Product, product_id)
    if product is None or product.status != "active":
        outcome.batch_error = ERR_PRODUCT_NOT_FOUND
        outcome.batch_error_message = "请选择有效产品"
        return outcome
    policy = duplicate_policy or get_settings().import_duplicate_policy
    seen: set[str] = set()
    candidates: list[AcceptedRow] = []
    duplicate_found = False
    for row_no, raw_code, raw_batch, cell_error in iter_product_batch(code_list_path):
        outcome.total_rows += 1
        value, error = code_value.check(raw_code)
        batch = code_value.normalize(raw_batch)
        if cell_error or error:
            outcome.errors.append(
                RowError(
                    row_no,
                    value,
                    product.code,
                    "INVALID_CODE",
                    cell_error or code_value.ERROR_MESSAGES[error],
                )
            )
            continue
        if value in seen:
            duplicate_found = True
            outcome.errors.append(
                RowError(
                    row_no,
                    value,
                    product.code,
                    ERR_DUPLICATE_IN_FILE,
                    _DUPLICATE_MESSAGES[ERR_DUPLICATE_IN_FILE],
                )
            )
            continue
        seen.add(value)
        if not batch or len(batch) > 64 or any(ord(char) < 32 for char in batch):
            outcome.errors.append(
                RowError(
                    row_no,
                    value,
                    product.code,
                    "INVALID_PRODUCTION_BATCH",
                    "产品批号必填、最多64个字符，不能包含换行或控制字符",
                )
            )
            continue
        candidates.append(AcceptedRow(value, product_id, row_no, batch))
    if callable(on_progress):
        on_progress(outcome.total_rows)
    existing = _existing_codes(db, [row.code_value for row in candidates])
    for row in candidates:
        if row.code_value in existing:
            outcome.errors.append(
                RowError(
                    row.row_no,
                    row.code_value,
                    product.code,
                    ERR_DUPLICATE_IN_DB,
                    _DUPLICATE_MESSAGES[ERR_DUPLICATE_IN_DB],
                )
            )
        else:
            outcome.accepted.append(row)
    if policy != "skip_row" and (duplicate_found or existing):
        outcome.batch_error = ErrorCode.IMPORT_DUPLICATE_CODE
        outcome.batch_error_message = "文件内或系统中存在重复防伪码，整批拒绝"
        outcome.accepted.clear()
    return outcome
