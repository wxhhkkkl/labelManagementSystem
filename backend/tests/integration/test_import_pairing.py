"""T048：成对校验与整批拒绝（FR-014 / FR-017 / FR-020）。

覆盖导入流水线的四个关键判定：
  1. 两文件码集合必须完全一致，否则整批拒绝且不写任何码
  2. 文件内重复码值默认整批拒绝
  3. 与库内已有码重复默认整批拒绝
  4. 对照关系引用的产品不存在 → 该行计入失败明细，其余照常入库
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.code import Code
from app.models.user import User
from app.services.import_errors import read_error_detail
from app.services.import_validator import (
    ERR_DUPLICATE_IN_DB,
    ERR_DUPLICATE_IN_FILE,
    ERR_MISSING_IN_CODE_LIST,
    ERR_MISSING_IN_MAPPING,
    ERR_PRODUCT_NOT_FOUND,
)
from app.tasks import import_worker
from tests.helpers import paired_rows, stage_batch

pytestmark = pytest.mark.integration


def _codes(db: Session) -> set[str]:
    return set(db.execute(select(Code.code_value)).scalars())


class TestCodeSetMustMatch:
    """FR-014：两个文件的码集合必须完全一致。"""

    def test_identical_sets_import_successfully(
        self, db: Session, hq_admin: User, product, import_storage
    ):
        codes, mapping = paired_rows([f"A{i:04d}" for i in range(10)], product.code)
        batch = stage_batch(
            db, batch_no="IMP1", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )

        import_worker.process_batch(db, batch.id)

        assert batch.status == "succeeded"
        assert batch.success_count == 10
        assert batch.failure_count == 0
        assert len(_codes(db)) == 10

        stored = db.execute(select(Code).where(Code.code_value == "A0000")).scalar_one()
        assert stored.status == "unallocated"
        assert stored.product_id == product.id
        assert stored.import_batch_id == batch.id

    def test_code_present_only_in_code_list_rejects_whole_batch(
        self, db: Session, hq_admin, product, import_storage
    ):
        codes = ["A001", "A002", "A003"]
        mapping = [("A001", product.code), ("A002", product.code)]  # 少一个

        batch = stage_batch(
            db, batch_no="IMP2", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )
        import_worker.process_batch(db, batch.id)

        assert batch.status == "failed"
        assert batch.success_count == 0
        assert _codes(db) == set()  # 整批拒绝，一个码都不入库

        rows = read_error_detail(import_worker.error_detail_path(batch.batch_no))
        assert any(r[3] == ERR_MISSING_IN_MAPPING and r[1] == "A003" for r in rows[1:])

    def test_code_present_only_in_mapping_rejects_whole_batch(
        self, db: Session, hq_admin, product, import_storage
    ):
        codes = ["A001"]
        mapping = [("A001", product.code), ("A999", product.code)]  # 多一个

        batch = stage_batch(
            db, batch_no="IMP3", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )
        import_worker.process_batch(db, batch.id)

        assert batch.status == "failed"
        assert _codes(db) == set()
        rows = read_error_detail(import_worker.error_detail_path(batch.batch_no))
        assert any(r[3] == ERR_MISSING_IN_CODE_LIST and r[1] == "A999" for r in rows[1:])


class TestDuplicates:
    """FR-017：码值全库唯一，默认整批拒绝。"""

    def test_duplicate_within_file_rejects_batch(
        self, db: Session, hq_admin, product, import_storage
    ):
        codes = ["DUP1", "DUP1", "OTHER"]
        mapping = [("DUP1", product.code), ("DUP1", product.code), ("OTHER", product.code)]

        batch = stage_batch(
            db, batch_no="IMP4", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )
        import_worker.process_batch(db, batch.id)

        assert batch.status == "failed"
        assert _codes(db) == set()
        rows = read_error_detail(import_worker.error_detail_path(batch.batch_no))
        assert any(r[3] == ERR_DUPLICATE_IN_FILE for r in rows[1:])

    def test_duplicate_against_existing_code_rejects_batch(
        self, db: Session, hq_admin, product, import_storage
    ):
        # 先导入一批
        codes, mapping = paired_rows(["E001", "E002"], product.code)
        first = stage_batch(
            db, batch_no="IMP5", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )
        import_worker.process_batch(db, first.id)
        assert first.status == "succeeded"

        # 再导入含同码的一批
        codes2, mapping2 = paired_rows(["E002", "E003"], product.code)
        second = stage_batch(
            db, batch_no="IMP6", created_by=hq_admin.id, code_values=codes2, mapping_rows=mapping2
        )
        import_worker.process_batch(db, second.id)

        assert second.status == "failed"
        assert _codes(db) == {"E001", "E002"}  # 第二批一个都没进去
        rows = read_error_detail(import_worker.error_detail_path(second.batch_no))
        assert any(r[3] == ERR_DUPLICATE_IN_DB and r[1] == "E002" for r in rows[1:])

    def test_skip_row_policy_imports_the_rest(
        self, db: Session, hq_admin, product, import_storage, monkeypatch
    ):
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "import_duplicate_policy", "skip_row")

        codes, mapping = paired_rows(["S001", "S001", "S002"], product.code)
        batch = stage_batch(
            db, batch_no="IMP7", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )
        import_worker.process_batch(db, batch.id)

        assert batch.status == "succeeded"
        assert _codes(db) == {"S001", "S002"}
        assert batch.failure_count == 1


class TestProductReference:
    """FR-020：对照关系中引用了不存在的产品编码 → 该行失败，不入库。"""

    def test_unknown_product_fails_only_that_row(
        self, db: Session, hq_admin, product, import_storage
    ):
        codes = ["G001", "G002"]
        mapping = [("G001", product.code), ("G002", "NO-SUCH-PRODUCT")]

        batch = stage_batch(
            db, batch_no="IMP8", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )
        import_worker.process_batch(db, batch.id)

        assert batch.status == "succeeded"  # 非整批级失败
        assert batch.success_count == 1
        assert batch.failure_count == 1
        assert _codes(db) == {"G001"}

        rows = read_error_detail(import_worker.error_detail_path(batch.batch_no))
        assert any(r[3] == ERR_PRODUCT_NOT_FOUND and r[1] == "G002" for r in rows[1:])


class TestBatchRecord:
    """FR-018：批次记录字段完整。"""

    def test_records_counts_and_operator(
        self, db: Session, hq_admin, product, import_storage
    ):
        codes, mapping = paired_rows(["R001", "R002", "R003"], product.code)
        batch = stage_batch(
            db, batch_no="IMP9", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )
        import_worker.process_batch(db, batch.id)

        assert batch.total_rows == 3
        assert batch.processed_rows == 3
        assert batch.created_by == hq_admin.id
        assert batch.started_at is not None
        assert batch.finished_at is not None

    def test_reprocessing_a_finished_batch_is_noop(
        self, db: Session, hq_admin, product, import_storage
    ):
        codes, mapping = paired_rows(["N001"], product.code)
        batch = stage_batch(
            db, batch_no="IMPA", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )
        import_worker.process_batch(db, batch.id)
        import_worker.process_batch(db, batch.id)  # 再跑一次

        assert batch.success_count == 1
        assert len(_codes(db)) == 1


class TestImportEventIsRecorded:
    """FR-064 的导入节点：每个码在导入时留下一条事件。"""

    def test_each_code_gets_an_imported_event(
        self, db: Session, hq_admin, product, import_storage
    ):
        from app.models.code_event import CodeEvent

        codes, mapping = paired_rows(["V001", "V002"], product.code)
        batch = stage_batch(
            db, batch_no="IMPB", created_by=hq_admin.id, code_values=codes, mapping_rows=mapping
        )
        import_worker.process_batch(db, batch.id)

        events = list(db.execute(select(CodeEvent)).scalars())
        assert len(events) == 2
        assert {e.event_type for e in events} == {"imported"}
        assert {e.to_status for e in events} == {"unallocated"}
