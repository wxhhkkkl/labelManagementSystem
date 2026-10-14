"""T101：补打权限矩阵（FR-051 / FR-052 / FR-053）。

补打是"一码一打"的唯一例外通道，权限必须收紧：
  * 总部管理员：任意公司的码
  * 子公司管理员：仅本公司码（已确认下沉，无需总部审批）
  * 工位操作员：无补打权限
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.base import utcnow
from app.models.code import Code
from app.models.user import User
from app.services import reprint as reprint_service
from tests.conftest import make_user
from tests.helpers import make_printed

pytestmark = pytest.mark.integration


@pytest.fixture
def printed(db: Session, product, hq_company, import_batch, template_version, hq_admin, workstation, operator):
    make_printed(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        workstation=workstation,
        values=["PM01", "PM02", "PM03", "PM04"],
    )
    workstation.last_heartbeat_at = utcnow()
    db.flush()
    return ["PM01", "PM02", "PM03", "PM04"]


class TestHeadquartersAdmin:
    def test_can_reprint_any_company_code(self, db: Session, hq_admin: User, printed):
        task = reprint_service.request_reprint(
            db, code_value="PM01", reason="总部补打", user=hq_admin
        )
        assert task.status == "pending"

    def test_needs_a_reason(self, db: Session, hq_admin: User, printed):
        for blank in (None, "", "   "):
            with pytest.raises(ApiError) as exc:
                reprint_service.request_reprint(
                    db, code_value="PM01", reason=blank, user=hq_admin
                )
            assert exc.value.error_code == "REASON_REQUIRED"

    def test_reason_is_trimmed(self, db: Session, hq_admin, printed):
        task = reprint_service.request_reprint(
            db, code_value="PM01", reason="  标签破损  ", user=hq_admin
        )
        assert task.reason == "标签破损"


class TestSubsidiaryAdmin:
    def test_can_reprint_own_company_code(self, db: Session, sub_admin: User, printed):
        task = reprint_service.request_reprint(
            db, code_value="PM02", reason="本公司补打", user=sub_admin
        )
        assert task.status == "pending", "补打权限已确认下沉，无需总部审批"

    def test_cannot_reprint_another_companys_code(
        self, db: Session, other_sub_admin: User, printed
    ):
        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(
                db, code_value="PM03", reason="越权", user=other_sub_admin
            )
        assert exc.value.error_code == "FORBIDDEN_SCOPE"

    def test_rejected_request_creates_no_task(
        self, db: Session, other_sub_admin, printed
    ):
        from app.models.print_task import PrintTask

        with pytest.raises(ApiError):
            reprint_service.request_reprint(
                db, code_value="PM04", reason="越权", user=other_sub_admin
            )
        assert list(db.execute(select(PrintTask)).scalars()) == []

    def test_cannot_reprint_a_code_that_belongs_to_no_company(
        self, db: Session, sub_admin, product, import_batch
    ):
        """归属为空的码（池中码）不属于任何公司，子公司管理员无权补打。"""
        code = Code(
            code_value="POOL01",
            status="printed",
            product_id=product.id,
            company_id=None,
            import_batch_id=import_batch.id,
        )
        db.add(code)
        db.flush()

        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(
                db, code_value="POOL01", reason="越权", user=sub_admin
            )
        assert exc.value.error_code == "FORBIDDEN_SCOPE"


class TestOperator:
    def test_operator_has_no_reprint_permission(
        self, db: Session, operator: User, printed
    ):
        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(
                db, code_value="PM01", reason="操作员想补打", user=operator
            )
        assert exc.value.error_code == "FORBIDDEN_SCOPE"
        assert "操作员" in exc.value.message

    def test_operator_of_another_company_also_denied(
        self, db: Session, other_company, printed
    ):
        outsider = make_user(db, username="op-out", role="operator", company=other_company)
        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(db, code_value="PM01", reason="x", user=outsider)
        assert exc.value.error_code == "FORBIDDEN_SCOPE"


class TestPermissionIsCheckedBeforeState:
    def test_wrong_role_fails_even_for_a_printable_code(
        self, db: Session, operator, product, import_batch, hq_company, template_version
    ):
        """权限先于状态校验：不该让越权者从错误码反推码的状态。"""
        from tests.helpers import make_printable

        make_printable(
            db,
            product=product,
            batch=import_batch,
            company=hq_company,
            operator_id=operator.id,
            values=["ALLOC1"],
        )

        with pytest.raises(ApiError) as exc:
            reprint_service.request_reprint(db, code_value="ALLOC1", reason="x", user=operator)
        assert exc.value.error_code == "FORBIDDEN_SCOPE"
