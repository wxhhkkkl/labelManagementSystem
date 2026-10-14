"""T129：报表组织隔离（FR-068 / SC-007）。

子公司报表查询结果中他公司数据出现次数 MUST 为 0。
这是可被直接断言的安全属性，也是 SC-007 的原文要求。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.code import Code
from app.models.user import User
from tests.conftest import auth_header
from tests.helpers import make_printed

pytestmark = pytest.mark.integration


@pytest.fixture
def two_companies_with_printlog(
    db: Session,
    product,
    hq_company,
    other_company,
    import_batch,
    template_version,
    hq_admin,
    workstation,
    operator,
):
    """本公司有打印记录；他公司也有自己的码与记录。"""
    make_printed(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        workstation=workstation,
        values=["ISO1", "ISO2"],
    )
    db.add(
        Code(
            code_value="FOREIGN-R",
            status="printed",
            product_id=product.id,
            company_id=other_company.id,
            import_batch_id=import_batch.id,
        )
    )
    db.flush()


def _get(client, user, url):
    resp = client.get(url, headers=auth_header(user))
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestDashboardIsolation:
    def test_sub_admin_sees_only_own_company_rows(
        self, client, sub_admin: User, hq_company, two_companies_with_printlog
    ):
        body = _get(client, sub_admin, "/api/v1/dashboard/code-distribution")
        company_names = {r["company_name"] for r in body["rows"]}
        assert company_names <= {hq_company.name}

    def test_totals_only_count_own_company(
        self, client, db: Session, sub_admin, hq_company, other_company, two_companies_with_printlog
    ):
        body = _get(client, sub_admin, "/api/v1/dashboard/code-distribution")
        own = db.execute(
            select(Code).where(Code.company_id == hq_company.id, Code.status == "printed")
        ).scalars().all()
        assert body["totals"]["printed"] == len(own)

    def test_group_by_company_shows_a_single_row(
        self, client, sub_admin, hq_company, two_companies_with_printlog
    ):
        body = _get(client, sub_admin, "/api/v1/dashboard/code-distribution?group_by=company")
        assert [r["key"] for r in body["rows"]] == [hq_company.name]


class TestPrintDetailIsolation:
    def test_sub_admin_sees_only_own_records(
        self, client, sub_admin, hq_company, other_company, two_companies_with_printlog
    ):
        rows = _get(client, sub_admin, "/api/v1/reports/prints")
        assert rows, "本公司应有打印记录"
        assert all(r["company_name"] == hq_company.name for r in rows)

    def test_explicit_other_company_filter_is_denied(self, client, sub_admin, other_company):
        resp = client.get(
            f"/api/v1/reports/prints?company_id={other_company.id}",
            headers=auth_header(sub_admin),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "FORBIDDEN_SCOPE"

    def test_export_is_scoped_too(self, client, sub_admin, hq_company, two_companies_with_printlog):
        """导出是最容易漏掉隔离的出口——必须同样受限。"""
        resp = client.get("/api/v1/reports/prints/export", headers=auth_header(sub_admin))
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]

    def test_export_rejects_cross_company_filter(self, client, sub_admin, other_company):
        resp = client.get(
            f"/api/v1/reports/prints/export?company_id={other_company.id}",
            headers=auth_header(sub_admin),
        )
        assert resp.status_code == 403


class TestLedgerIsolation:
    def test_sub_admin_ledger_excludes_foreign_voids(
        self, client, db: Session, sub_admin, other_company, product, import_batch
    ):
        db.add(
            Code(
                code_value="FOREIGN-V",
                status="voided",
                product_id=product.id,
                company_id=other_company.id,
                import_batch_id=import_batch.id,
                voided_at=utcnow(),
                void_reason="他公司作废",
            )
        )
        db.flush()

        rows = _get(client, sub_admin, "/api/v1/reprints")
        assert all(r["code_value"] != "FOREIGN-V" for r in rows)


class TestHqSeesEverything:
    def test_hq_admin_sees_both_companies(
        self, client, hq_admin: User, hq_company, other_company, two_companies_with_printlog
    ):
        rows = _get(client, hq_admin, "/api/v1/reports/prints")
        names = {r["company_name"] for r in rows}
        assert names == {hq_company.name}

        body = _get(client, hq_admin, "/api/v1/dashboard/code-distribution")
        company_names = {r["company_name"] for r in body["rows"]}
        assert other_company.name in company_names, "总部应看得到他公司的码"


class TestZeroLeakAssertion:
    """SC-007 的直接断言：任取子公司管理员，他公司数据出现 0 次。"""

    def test_no_foreign_code_appears_anywhere(
        self,
        client,
        db: Session,
        sub_admin: User,
        hq_company,
        other_company,
        two_companies_with_printlog,
    ):
        foreign_codes = set(
            db.execute(
                select(Code.code_value).where(Code.company_id == other_company.id)
            ).scalars()
        )
        assert foreign_codes, "夹具应造出他公司的码，否则这条断言没有意义"

        endpoints = [
            "/api/v1/reports/prints",
            "/api/v1/reprints",
        ]
        for url in endpoints:
            for row in _get(client, sub_admin, url):
                assert row.get("code_value") not in foreign_codes, f"{url} 泄漏了他公司数据"
                assert row.get("company_name") != other_company.name
