"""T137：日志不可篡改与仅总部可查（FR-060 / FR-061 / FR-062 / FR-007）。

其中"越权也要留痕"这条原本是**没落实**的：`record_denied` 写好了却从没被调用。
现在由全局异常处理器统一记录——越权校验散落在服务层各处，逐个补埋点必然漏。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services import audit
from tests.conftest import auth_header

pytestmark = pytest.mark.integration


class TestOnlyHeadquartersCanRead:
    def test_sub_admin_is_denied(self, client, sub_admin: User):
        resp = client.get("/api/v1/audit-logs", headers=auth_header(sub_admin))
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"

    def test_operator_is_denied(self, client, operator: User):
        assert client.get("/api/v1/audit-logs", headers=auth_header(operator)).status_code == 403

    def test_anonymous_is_denied(self, client):
        assert client.get("/api/v1/audit-logs").status_code == 401

    def test_hq_admin_can_read(self, client, db: Session, hq_admin: User):
        audit.record(
            db,
            operator_id=hq_admin.id,
            role=hq_admin.role,
            action="test.action",
            result="success",
        )
        db.flush()

        resp = client.get("/api/v1/audit-logs", headers=auth_header(hq_admin))
        assert resp.status_code == 200
        assert any(row["action"] == "test.action" for row in resp.json())


class TestLogsAreAppendOnly:
    def test_no_update_or_delete_route_exists(self):
        """FR-060：日志 MUST 不可篡改、不可删除。

        这里断言的是**接口层面根本没有这类入口**——
        比"有但返回 403"更强：没有入口就不会有越权改日志的可能。
        """
        from app.main import app

        paths = app.openapi()["paths"]
        mutating = [
            (path, method)
            for path, methods in paths.items()
            if "audit-logs" in path
            for method in methods
            if method.upper() in ("PUT", "PATCH", "DELETE")
        ]
        assert mutating == []

    def test_service_module_exposes_no_write_back(self):
        """服务层同样不暴露修改或删除方法。"""
        forbidden = {"update", "delete", "remove", "edit", "purge"}
        public = {name for name in dir(audit) if not name.startswith("_")}
        assert not (public & forbidden), f"审计服务不应暴露：{public & forbidden}"

    def test_records_survive_and_are_queryable(self, client, db: Session, hq_admin: User):
        for i in range(3):
            audit.record(
                db,
                operator_id=hq_admin.id,
                role=hq_admin.role,
                action=f"bulk.{i}",
                result="success",
            )
        db.flush()

        rows = client.get("/api/v1/audit-logs", headers=auth_header(hq_admin)).json()
        assert len([r for r in rows if r["action"].startswith("bulk.")]) == 3


class TestDeniedRequestsAreAudited:
    """FR-007：越权请求一律被拒绝，且 MUST 写入操作日志。"""

    def test_cross_company_query_writes_a_denied_record(
        self, client, db: Session, sub_admin: User, other_company
    ):
        client.get(
            f"/api/v1/workstations?company_id={other_company.id}",
            headers=auth_header(sub_admin),
        )

        denied = list(
            db.execute(select(AuditLog).where(AuditLog.result == "denied")).scalars()
        )
        assert denied, "越权被拒后必须留下一条 denied 记录"
        assert denied[0].operator_id == sub_admin.id
        assert denied[0].role == "sub_admin"

    def test_denied_record_carries_the_path(
        self, client, db: Session, sub_admin: User, other_company
    ):
        client.get(
            f"/api/v1/reports/prints?company_id={other_company.id}",
            headers=auth_header(sub_admin),
        )

        row = db.execute(select(AuditLog).where(AuditLog.result == "denied")).scalar_one()
        assert "reports/prints" in (row.target_type or "")

    def test_denied_record_does_not_break_the_response(
        self, client, sub_admin: User, other_company
    ):
        resp = client.get(
            f"/api/v1/workstations?company_id={other_company.id}",
            headers=auth_header(sub_admin),
        )
        assert resp.status_code == 403, "留痕失败不得改变给调用方的响应"

    def test_unattributable_denial_is_skipped(self, client, db: Session):
        """没有可用令牌时无法归因，此时不写记录——不是每一条都能落到人头上。"""
        client.get("/api/v1/audit-logs")  # 未带令牌
        rows = list(db.execute(select(AuditLog)).scalars())
        assert rows == []


class TestQueryFilters:
    @pytest.fixture
    def seeded(self, db: Session, hq_admin: User, sub_admin: User, hq_company):
        audit.record(
            db,
            operator_id=hq_admin.id,
            role="hq_admin",
            action="import.create",
            result="success",
        )
        audit.record(
            db,
            operator_id=sub_admin.id,
            role="sub_admin",
            action="print",
            result="failed",
            company_id=hq_company.id,
        )
        db.flush()

    def test_filter_by_result(self, client, hq_admin, seeded):
        rows = client.get(
            "/api/v1/audit-logs?result=failed", headers=auth_header(hq_admin)
        ).json()
        assert rows
        assert all(r["result"] == "failed" for r in rows)

    def test_filter_by_role(self, client, hq_admin, seeded):
        rows = client.get(
            "/api/v1/audit-logs?role=sub_admin", headers=auth_header(hq_admin)
        ).json()
        assert rows
        assert all(r["role"] == "sub_admin" for r in rows)

    def test_filter_by_action_substring(self, client, hq_admin, seeded):
        rows = client.get(
            "/api/v1/audit-logs?action=import", headers=auth_header(hq_admin)
        ).json()
        assert any(r["action"] == "import.create" for r in rows)

    def test_filter_by_company(self, client, hq_admin, hq_company, seeded):
        rows = client.get(
            f"/api/v1/audit-logs?company_id={hq_company.id}", headers=auth_header(hq_admin)
        ).json()
        assert rows
        assert all(r["company_id"] == hq_company.id for r in rows)

    def test_invalid_result_value_is_422(self, client, hq_admin):
        resp = client.get(
            "/api/v1/audit-logs?result=nonsense", headers=auth_header(hq_admin)
        )
        assert resp.status_code == 422
