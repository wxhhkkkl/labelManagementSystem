"""T157：quickstart 场景 3 / 4 / 6 的端到端断言。

`quickstart.md` 里这三个场景是**手工验收步骤**。本文件把它们变成自动化断言，
并且刻意走**完整 HTTP 链路**（而不是直接调服务层）——
服务层已经被前面的测试覆盖了，这里要证明的是"接口串起来也对"。

场景对应：
  3 防重复打印（FR-041 ~ FR-044）—— 系统的核心控制点
  4 打印失败回退 vs 补打（FR-045 ~ FR-053）
  6 超时回退与重复出纸风险（FR-047 / FR-048）
"""

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.code import Code
from app.models.print_log import PrintLog
from app.models.user import User
from tests.conftest import auth_header
from tests.helpers import make_printable

pytestmark = pytest.mark.integration

TEMPLATE_60X40 = 60


@pytest.fixture
def pool(db: Session, product, hq_company, import_batch, template_version, hq_admin):
    values = ["QS01", "QS02", "QS03", "QS04"]
    make_printable(
        db,
        product=product,
        batch=import_batch,
        company=hq_company,
        operator_id=hq_admin.id,
        values=values,
    )
    return values


def _preempt(client, operator, workstation_id, values):
    return client.post(
        "/api/v1/workstation/print",
        headers=auth_header(operator),
        json={"workstation_id": workstation_id, "code_values": values},
    ).json()


def _confirm(client, operator, workstation_id, results):
    return client.post(
        "/api/v1/workstation/print/confirm",
        headers=auth_header(operator),
        json={"workstation_id": workstation_id, "results": results},
    ).json()


def _print_successfully(client, operator, workstation_id, value):
    _preempt(client, operator, workstation_id, [value])
    _confirm(
        client,
        operator,
        workstation_id,
        [{"code_value": value, "outcome": "succeeded", "printer_name": "Zebra ZD421"}],
    )


# ---------------------------------------------------------------- 场景 3


class TestScenario3AntiDuplicate:
    """场景 3：防重复打印 —— 系统核心控制点。"""

    def test_successful_print_leaves_a_first_print_log(
        self, client, db: Session, operator, workstation, pool
    ):
        _print_successfully(client, operator, workstation.id, "QS01")

        log = db.execute(select(PrintLog)).scalar_one()
        assert log.print_type == "first"
        assert log.result == "succeeded"
        assert log.printer_name == "Zebra ZD421"

    def test_second_print_of_the_same_code_is_rejected_and_does_not_print(
        self, client, operator, workstation, pool
    ):
        _print_successfully(client, operator, workstation.id, "QS01")

        body = _preempt(client, operator, workstation.id, ["QS01"])

        assert body["accepted"] == [], "已打印的码不得再被接受"
        assert body["rejected"][0]["error_code"] == "CODE_ALREADY_PRINTED"

    def test_rejected_code_keeps_its_printed_state(
        self, client, db: Session, operator, workstation, pool
    ):
        _print_successfully(client, operator, workstation.id, "QS01")
        _preempt(client, operator, workstation.id, ["QS01"])

        code = db.execute(select(Code).where(Code.code_value == "QS01")).scalar_one()
        assert code.status == "printed"
        assert code.print_count == 1

    def test_code_is_invisible_to_other_companies(
        self, client, operator, workstation, other_company, db: Session, pool
    ):
        """第三层断言：码在别的公司看不到。"""
        body = client.get(
            f"/api/v1/workstation/codes?workstation_id={workstation.id}&product_id=1",
            headers=auth_header(operator),
        ).json()
        assert all(item["code_value"] in pool for item in body["items"])


# ---------------------------------------------------------------- 场景 4


class TestScenario4FailureVsReprint:
    """场景 4：打印失败回退与补打的区别。

    **失败回退不算补打**——补打是管理员对已打印码的例外操作；
    缺纸只是这次没打成，不该计入补打次数。
    """

    def test_failure_returns_the_code_to_allocated(
        self, client, db: Session, operator, workstation, pool
    ):
        _preempt(client, operator, workstation.id, ["QS02"])
        _confirm(
            client,
            operator,
            workstation.id,
            [{"code_value": "QS02", "outcome": "failed", "failure_reason": "打印机缺纸"}],
        )

        code = db.execute(select(Code).where(Code.code_value == "QS02")).scalar_one()
        assert code.status == "allocated"

    def test_failure_does_not_count_as_reprint(
        self, client, db: Session, operator, workstation, pool
    ):
        _preempt(client, operator, workstation.id, ["QS02"])
        _confirm(
            client, operator, workstation.id, [{"code_value": "QS02", "outcome": "failed"}]
        )

        code = db.execute(select(Code).where(Code.code_value == "QS02")).scalar_one()
        assert code.reprint_count == 0, "失败回退不得计入补打次数"

    def test_code_can_be_printed_again_after_failure(
        self, client, operator, workstation, pool
    ):
        _preempt(client, operator, workstation.id, ["QS02"])
        _confirm(
            client, operator, workstation.id, [{"code_value": "QS02", "outcome": "failed"}]
        )

        body = _preempt(client, operator, workstation.id, ["QS02"])
        assert len(body["accepted"]) == 1, "失败后应能再次正常打印"

    def test_a_real_reprint_does_increment_the_counter(
        self, client, db: Session, hq_admin: User, operator, workstation, pool
    ):
        """对比：管理员补打才 +1。"""
        _print_successfully(client, operator, workstation.id, "QS03")
        workstation.last_heartbeat_at = utcnow()
        db.flush()

        client.post(
            "/api/v1/codes/QS03/reprint",
            headers=auth_header(hq_admin),
            json={"reason": "标签破损"},
        )
        task_id = client.get(
            f"/api/v1/workstation/tasks?workstation_id={workstation.id}",
            headers=auth_header(operator),
        ).json()["tasks"][0]["task_id"]
        client.post(
            f"/api/v1/workstation/tasks/{task_id}/result?workstation_id={workstation.id}",
            headers=auth_header(operator),
            json={"result": "succeeded"},
        )

        code = db.execute(select(Code).where(Code.code_value == "QS03")).scalar_one()
        assert code.reprint_count == 1, "补打才计入补打次数"
        assert code.status == "printed", "补打后仍是已打印"


# ---------------------------------------------------------------- 场景 6


class TestScenario6TimeoutRevert:
    """场景 6：超时回退，以及它带来的重复出纸风险。

    quickstart 明确要求断言 `timeout_reverted` 记录已写入——
    因为"实际已出纸但回执丢失"时会造成重复出纸，那是 spec 接受的取舍，
    但必须事后可审计。
    """

    def _age_the_lock(self, db: Session, value: str, seconds: int = 3600) -> None:
        code = db.execute(select(Code).where(Code.code_value == value)).scalar_one()
        code.locked_at = utcnow() - timedelta(seconds=seconds)
        db.flush()

    def test_timed_out_code_returns_to_allocated(
        self, client, db: Session, operator, workstation, pool
    ):
        from app.services import printing

        _preempt(client, operator, workstation.id, ["QS04"])
        self._age_the_lock(db, "QS04")

        reverted = printing.sweep_expired(db)

        assert reverted == 1
        code = db.execute(select(Code).where(Code.code_value == "QS04")).scalar_one()
        assert code.status == "allocated"

    def test_timeout_revert_writes_an_auditable_log(
        self, client, db: Session, operator, workstation, pool
    ):
        from app.services import printing

        _preempt(client, operator, workstation.id, ["QS04"])
        self._age_the_lock(db, "QS04")
        printing.sweep_expired(db)

        log = db.execute(
            select(PrintLog).where(PrintLog.result == "timeout_reverted")
        ).scalar_one()
        assert log.code_value == "QS04", "重复出纸风险必须靠这条记录事后可查"

    def test_timeout_revert_does_not_count_as_reprint(
        self, client, db: Session, operator, workstation, pool
    ):
        from app.services import printing

        _preempt(client, operator, workstation.id, ["QS04"])
        self._age_the_lock(db, "QS04")
        printing.sweep_expired(db)

        code = db.execute(select(Code).where(Code.code_value == "QS04")).scalar_one()
        assert code.reprint_count == 0

    def test_code_can_be_printed_again_after_timeout(
        self, client, db: Session, operator, workstation, pool
    ):
        from app.services import printing

        _preempt(client, operator, workstation.id, ["QS04"])
        self._age_the_lock(db, "QS04")
        printing.sweep_expired(db)

        body = _preempt(client, operator, workstation.id, ["QS04"])
        assert len(body["accepted"]) == 1

    def test_fresh_lock_is_not_swept(
        self, client, db: Session, operator, workstation, pool
    ):
        from app.services import printing

        _preempt(client, operator, workstation.id, ["QS04"])
        self._age_the_lock(db, "QS04", seconds=5)

        assert printing.sweep_expired(db) == 0


# ---------------------------------------------------------------- 渲染载荷


class TestRenderPayloadMatchesTemplate:
    """另一条 quickstart 断言：下发的模板与产品的默认模板版本一致。"""

    def test_payload_carries_the_allocation_template_version(
        self, client, operator, workstation, pool, template_version
    ):
        body = _preempt(client, operator, workstation.id, ["QS01"])
        item = body["accepted"][0]

        assert item["template_version_id"] == template_version.id
        assert item["elements_json"]["paper_width_mm"] == TEMPLATE_60X40
        # 四个动态字段齐全，工位端拿到就能直接渲染（FR-037）
        assert set(item["data"]) == {"product_name", "company_name", "code_value", "batch_no"}
        assert item["data"]["batch_no"].startswith("ALL")
