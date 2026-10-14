"""T050：10 万行级导入（FR-016 / SC-003）。

验证异步导入在目标体量下能跑完并给出成功数与失败明细。
行数可用环境变量 IMPORT_SCALE_ROWS 下调，便于本地快速回归。

耗时较长，可用 -m "not scale" 排除。
"""

import os
import time

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.user import User
from app.tasks import import_worker
from tests.helpers import stage_batch

pytestmark = [pytest.mark.integration, pytest.mark.scale]

ROWS = int(os.environ.get("IMPORT_SCALE_ROWS", "100000"))


@pytest.fixture(scope="module")
def scale_rows() -> int:
    return ROWS


def _generate(prefix: str, count: int) -> tuple[list[str], list[tuple[str, str]]]:
    """生成 count 个码值与对应关系。

    码值固定 12 位（前缀 3 位 + 9 位序号），保证不超 100 位且在文件内唯一。
    """
    codes = [f"{prefix}{i:09d}" for i in range(count)]
    return codes, [(code, "P-SCALE") for code in codes]


def test_large_import_completes(
    db: Session, hq_admin: User, import_storage, scale_rows: int
):
    from app.models.product import Product

    product = Product(code="P-SCALE", name="规模测试产品", status="active")
    db.add(product)
    db.flush()

    codes, mapping = _generate("SCL", scale_rows)

    started = time.monotonic()
    batch = stage_batch(
        db,
        batch_no="IMPSCALE",
        created_by=hq_admin.id,
        code_values=codes,
        mapping_rows=mapping,
    )
    batch = db.get(type(batch), batch.id)
    import_worker.process_batch(db, batch.id)
    elapsed = time.monotonic() - started

    assert batch.status == "succeeded", f"批次失败: {batch.status}"
    assert batch.total_rows == scale_rows
    assert batch.success_count == scale_rows
    assert batch.failure_count == 0

    stored = db.execute(select(func.count()).select_from(Code)).scalar_one()
    assert stored == scale_rows

    # SC-003 要求"一次操作中完成"；这里给一个宽松上界，用于发现数量级退化
    assert elapsed < 600, f"导入耗时 {elapsed:.1f}s，超出预期数量级"


def test_large_import_writes_no_error_file_when_clean(
    db: Session, hq_admin: User, import_storage, scale_rows: int
):
    """零失败时不应产出空的失败明细文件。"""
    from app.models.product import Product

    if db.execute(select(func.count()).select_from(Product).where(Product.code == "P-SCALE")).scalar_one() == 0:
        db.add(Product(code="P-SCALE", name="规模测试产品", status="active"))
        db.flush()

    codes = [f"SCM{i:09d}" for i in range(min(scale_rows, 1000))]
    mapping = [(code, "P-SCALE") for code in codes]

    batch = stage_batch(
        db, batch_no="IMPSCALE2", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
    )
    import_worker.process_batch(db, batch.id)

    assert batch.status == "succeeded"
    assert batch.error_detail_path is None
