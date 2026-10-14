"""T102：作废终态（FR-057 ~ FR-060）。

作废是**不可恢复的终态**，因此这里的处理原则是"宁可整批拒绝，也不要部分成功"——
除了已作废码的幂等跳过。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.code import Code
from app.models.code_event import CodeEvent
from app.models.user import User
from app.services import void as void_service
from tests.conftest import make_user
from tests.helpers import make_printable, make_printed

pytestmark = pytest.mark.integration


@pytest.fixture
def mixed_codes(
    db: Session, product, hq_company, import_batch, template_version, hq_admin, workstation, operator
):
    """四种状态的码各一：待分配、已分配、已打印、（后续测试会作废其中一些）。

    注意顺序：make_printed 内部会自己做一次分配，所以 V-PRINT 不能再由
    make_printable 分配一遍——否则同一个码值会被插入两次。
    """
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=["V-ALLOC", "V-VOID"],
    )
    make_printed(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        workstation=workstation,
        values=["V-PRINT"],
    )
    # 池中码最后加，否则会被上面的分配顺手取走
    db.add(
        Code(
            code_value="V-POOL",
            status="unallocated",
            product_id=product.id,
            import_batch_id=import_batch.id,
        )
    )
    db.flush()


class TestVoidSucceeds:
    @pytest.mark.parametrize("value", ["V-POOL", "V-ALLOC", "V-PRINT"])
    def test_void_from_allowed_statuses(
        self, db: Session, hq_admin: User, mixed_codes, value
    ):
        result = void_service.void_codes(
            db, code_values=[value], reason="整批报废", user=hq_admin
        )

        assert result.voided == [value]
        code = db.execute(select(Code).where(Code.code_value == value)).scalar_one()
        assert code.status == "voided"
        assert code.void_reason == "整批报废"
        assert code.voided_by == hq_admin.id
        assert code.voided_at is not None

    def test_writes_a_voided_event(self, db: Session, hq_admin, mixed_codes):
        void_service.void_codes(db, code_values=["V-PRINT"], reason="报废", user=hq_admin)

        event = db.execute(
            select(CodeEvent).where(CodeEvent.event_type == "voided")
        ).scalar_one()
        assert event.to_status == "voided"
        assert event.reason == "报废"
        assert event.operator_id == hq_admin.id

    def test_releases_any_print_lock(self, db: Session, hq_admin, mixed_codes, workstation):
        """作废的码不该继续占着工位锁。"""
        from app.models.base import utcnow

        code = db.execute(select(Code).where(Code.code_value == "V-ALLOC")).scalar_one()
        code.locked_at = utcnow()
        code.locked_workstation_id = workstation.id
        db.flush()

        void_service.void_codes(db, code_values=["V-ALLOC"], reason="报废", user=hq_admin)

        db.refresh(code)
        assert code.locked_at is None
        assert code.locked_workstation_id is None


class TestReasonRequired:
    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_void_requires_a_reason(self, db: Session, hq_admin, mixed_codes, blank):
        with pytest.raises(ApiError) as exc:
            void_service.void_codes(db, code_values=["V-PRINT"], reason=blank, user=hq_admin)
        assert exc.value.error_code == "REASON_REQUIRED"

    def test_nothing_is_voided_when_reason_missing(self, db: Session, hq_admin, mixed_codes):
        with pytest.raises(ApiError):
            void_service.void_codes(db, code_values=["V-PRINT"], reason="", user=hq_admin)
        code = db.execute(select(Code).where(Code.code_value == "V-PRINT")).scalar_one()
        assert code.status == "printed"


class TestVoidIsTerminal:
    def test_already_voided_code_is_skipped_idempotently(
        self, db: Session, hq_admin, mixed_codes
    ):
        void_service.void_codes(db, code_values=["V-VOID"], reason="第一次", user=hq_admin)
        result = void_service.void_codes(
            db, code_values=["V-VOID"], reason="第二次", user=hq_admin
        )

        assert result.voided == []
        assert result.skipped == ["V-VOID"]

        code = db.execute(select(Code).where(Code.code_value == "V-VOID")).scalar_one()
        assert code.void_reason == "第一次", "重复作废不得覆盖首次原因"

    def test_voided_code_cannot_be_printed(
        self, db: Session, hq_admin, workstation, operator, mixed_codes
    ):
        from app.services import printing

        void_service.void_codes(db, code_values=["V-ALLOC"], reason="报废", user=hq_admin)

        _, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["V-ALLOC"]
        )
        assert rejected[0].error_code == "CODE_VOIDED"

    def test_voided_code_is_invisible_to_the_workstation(
        self, db: Session, hq_admin, workstation, operator, product, mixed_codes
    ):
        from app.services import printing

        void_service.void_codes(db, code_values=["V-ALLOC"], reason="报废", user=hq_admin)

        rows, _total = printing.list_printable_codes(
            db, company_id=workstation.company_id, product_id=product.id
        )
        visible = {c.code_value for c in rows}
        assert "V-ALLOC" not in visible, "作废的码不该再出现在可打印列表里"
        assert "V-VOID" in visible, "同公司未作废的码仍应可见"

    def test_voided_code_cannot_be_reprinted(
        self, db: Session, hq_admin, workstation, mixed_codes
    ):
        from app.core.errors import ApiError as Err
        from app.models.base import utcnow
        from app.services import reprint as reprint_service

        workstation.last_heartbeat_at = utcnow()
        db.flush()
        void_service.void_codes(db, code_values=["V-PRINT"], reason="报废", user=hq_admin)

        with pytest.raises(Err) as exc:
            reprint_service.request_reprint(
                db, code_value="V-PRINT", reason="想补打", user=hq_admin
            )
        assert exc.value.error_code == "CODE_NOT_PRINTED"


class TestBatchVoid:
    def test_batch_void_processes_all(self, db: Session, hq_admin, mixed_codes):
        result = void_service.void_codes(
            db, code_values=["V-PRINT", "V-ALLOC", "V-POOL"], reason="整批", user=hq_admin
        )
        assert sorted(result.voided) == ["V-ALLOC", "V-POOL", "V-PRINT"]

    def test_duplicate_values_in_request_are_deduplicated(
        self, db: Session, hq_admin, mixed_codes
    ):
        result = void_service.void_codes(
            db, code_values=["V-PRINT", "V-PRINT"], reason="整批", user=hq_admin
        )
        assert result.voided == ["V-PRINT"]

    def test_mixed_batch_with_already_voided_skips_it(
        self, db: Session, hq_admin, mixed_codes
    ):
        void_service.void_codes(db, code_values=["V-VOID"], reason="先作废", user=hq_admin)

        result = void_service.void_codes(
            db, code_values=["V-PRINT", "V-VOID"], reason="整批", user=hq_admin
        )
        assert result.voided == ["V-PRINT"]
        assert result.skipped == ["V-VOID"]

    def test_empty_list_is_rejected(self, db: Session, hq_admin):
        with pytest.raises(ApiError):
            void_service.void_codes(db, code_values=[], reason="x", user=hq_admin)

    def test_unknown_code_rejects_the_whole_batch(self, db: Session, hq_admin, mixed_codes):
        with pytest.raises(ApiError) as exc:
            void_service.void_codes(
                db, code_values=["V-PRINT", "NO-SUCH-CODE"], reason="整批", user=hq_admin
            )
        assert exc.value.error_code == "NOT_FOUND"

        code = db.execute(select(Code).where(Code.code_value == "V-PRINT")).scalar_one()
        assert code.status == "printed", "整批拒绝时不得部分作废"


class TestVoidPermissions:
    def test_sub_admin_can_void_own_company_codes(self, db: Session, sub_admin, mixed_codes):
        result = void_service.void_codes(
            db, code_values=["V-PRINT"], reason="本公司报废", user=sub_admin
        )
        assert result.voided == ["V-PRINT"]

    def test_mixed_batch_with_foreign_code_rejects_the_whole_batch(
        self, db: Session, sub_admin, mixed_codes, other_company, product, import_batch
    ):
        """FR-057 / 契约：混入他公司码整体拒绝，不部分成功。"""
        foreign = Code(
            code_value="FOREIGN1",
            status="printed",
            product_id=product.id,
            company_id=other_company.id,
            import_batch_id=import_batch.id,
        )
        db.add(foreign)
        db.flush()

        with pytest.raises(ApiError) as exc:
            void_service.void_codes(
                db, code_values=["V-PRINT", "FOREIGN1"], reason="整批", user=sub_admin
            )
        assert exc.value.error_code == "FORBIDDEN_SCOPE"

        own = db.execute(select(Code).where(Code.code_value == "V-PRINT")).scalar_one()
        assert own.status == "printed", "越权混入时不得部分作废"

    def test_operator_cannot_void(self, db: Session, operator, mixed_codes):
        with pytest.raises(ApiError) as exc:
            void_service.void_codes(
                db, code_values=["V-PRINT"], reason="操作员想作废", user=operator
            )
        assert exc.value.error_code == "FORBIDDEN_SCOPE"

    def test_sub_admin_cannot_void_foreign_code_alone(
        self, db: Session, sub_admin, other_company, product, import_batch
    ):
        foreign = Code(
            code_value="FOREIGN2",
            status="printed",
            product_id=product.id,
            company_id=other_company.id,
            import_batch_id=import_batch.id,
        )
        db.add(foreign)
        db.flush()

        with pytest.raises(ApiError) as exc:
            void_service.void_codes(
                db, code_values=["FOREIGN2"], reason="越权", user=sub_admin
            )
        assert exc.value.error_code == "FORBIDDEN_SCOPE"
