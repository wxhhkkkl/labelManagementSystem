"""T117：版本冻结（FR-033 / FR-034）。

冻结的意义：已经发出去的分配单必须**原样复现**。
如果总部改了模板，已打印/待打印的码不该跟着变——否则同一批货会出现两种标签。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.base import utcnow
from app.models.template import TemplateVersion
from app.services import allocation as allocation_service
from app.services import reprint as reprint_service
from app.services import template as template_service
from tests.helpers import make_printable, make_printed

pytestmark = pytest.mark.integration

ELEMENTS = [{"type": "qrcode", "x": 2, "y": 2, "size": 15}]


def _new_template(db: Session, code: str = "TF1"):
    return template_service.create_template(
        db, code=code, name="冻结测试模板", paper_width_mm=60, paper_height_mm=40, elements=ELEMENTS
    )


class TestVersionImmutability:
    """FR-033：修改模板 = 追加新版本，既有版本行原样不动。"""

    def test_update_creates_a_new_version(self, db: Session):
        template, v1 = _new_template(db)

        v2 = template_service.add_version(
            db,
            template.id,
            paper_width_mm=70,
            paper_height_mm=50,
            elements=[{"type": "qrcode", "x": 1, "y": 1, "size": 10}],
        )

        assert v2.version_no == 2
        assert v2.paper_width_mm == 70

        db.refresh(v1)
        assert v1.version_no == 1
        assert float(v1.paper_width_mm) == 60, "既有版本不该被改动"

    def test_versions_are_listed_newest_first(self, db: Session):
        template, _ = _new_template(db, "TF2")
        template_service.add_version(
            db, template.id, paper_width_mm=70, paper_height_mm=50, elements=ELEMENTS
        )

        versions = template_service.list_versions(db, template.id)
        assert [v.version_no for v in versions] == [2, 1]

    def test_new_version_is_not_frozen(self, db: Session):
        template, _ = _new_template(db, "TF3")
        v2 = template_service.add_version(
            db, template.id, paper_width_mm=70, paper_height_mm=50, elements=ELEMENTS
        )
        assert v2.frozen is False


class TestFrozenVersionCannotBeEdited:
    def test_replacing_content_of_a_frozen_version_is_rejected(self, db: Session):
        _, version = _new_template(db, "TF4")
        template_service.freeze_version(db, version.id)

        with pytest.raises(ApiError) as exc:
            template_service.replace_version_content(
                db,
                version.id,
                paper_width_mm=99,
                paper_height_mm=99,
                elements=ELEMENTS,
            )
        assert exc.value.error_code == "TEMPLATE_VERSION_FROZEN"

    def test_content_is_unchanged_after_rejection(self, db: Session):
        _, version = _new_template(db, "TF5")
        template_service.freeze_version(db, version.id)
        before = dict(version.elements_json)

        with pytest.raises(ApiError):
            template_service.replace_version_content(
                db, version.id, paper_width_mm=99, paper_height_mm=99, elements=[]
            )

        db.refresh(version)
        assert version.elements_json == before

    def test_unfrozen_version_can_still_be_edited(self, db: Session):
        _, version = _new_template(db, "TF6")
        updated = template_service.replace_version_content(
            db,
            version.id,
            paper_width_mm=80,
            paper_height_mm=60,
            elements=ELEMENTS,
        )
        assert float(updated.paper_width_mm) == 80


class TestAllocationFreezesTheVersion:
    def test_allocating_freezes_the_carried_version(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version
    ):
        assert template_version.frozen is False
        make_printable(
            db,
            product=product,
            batch=import_batch,
            company=hq_company,
            operator_id=hq_admin.id,
            values=["FZ01"],
        )

        db.refresh(template_version)
        assert template_version.frozen is True

    def test_frozen_version_still_usable_for_the_existing_order(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version, workstation, operator
    ):
        """冻结不是"禁止使用"，而是"禁止改动"。已发出的分配单照样能打印。"""
        from app.services import printing

        order = make_printable(
            db,
            product=product,
            batch=import_batch,
            company=hq_company,
            operator_id=hq_admin.id,
            values=["FZ02"],
        )

        # 总部此时改了模板 → 新版本
        template_service.add_version(
            db,
            template_version.template_id,
            paper_width_mm=99,
            paper_height_mm=99,
            elements=ELEMENTS,
        )

        accepted, rejected = printing.preempt(
            db, workstation=workstation, operator_id=operator.id, code_values=["FZ02"]
        )
        assert not rejected
        # 打印用的仍是分配单携带的旧版本
        assert accepted[0].template_version_id == template_version.id
        assert accepted[0].elements_json["paper_width_mm"] == 60
        assert order.template_version_id == template_version.id


class TestReprintTaskFreezesTheVersion:
    def test_creating_a_reprint_task_freezes_its_version(
        self, db: Session, hq_admin, product, hq_company, import_batch, template_version, workstation, operator
    ):
        """FR-034 的"被 PrintTask 引用"分支。

        若这里漏了冻结，总部在补打任务排队期间改模板，
        工位出纸的内容就会和当初打印的那张不一致。
        """
        make_printed(
            db,
            product=product,
            batch=import_batch,
            company=hq_company,
            operator_id=hq_admin.id,
            workstation=workstation,
            values=["FZ03"],
        )
        workstation.last_heartbeat_at = utcnow()
        db.flush()

        # 先解冻以模拟"尚未被引用"的版本
        template_version.frozen = False
        db.flush()

        reprint_service.request_reprint(db, code_value="FZ03", reason="破损", user=hq_admin)

        db.refresh(template_version)
        assert template_version.frozen is True


class TestTemplateDisable:
    def test_disable_only_affects_future_allocations(self, db: Session):
        template, version = _new_template(db, "TF7")
        template_service.freeze_version(db, version.id)

        template_service.disable_template(db, template.id)

        db.refresh(template)
        db.refresh(version)
        assert template.status == "disabled"
        assert version.frozen is True, "停用模板不该影响已冻结版本的可用性"

    def test_disabled_template_cannot_get_new_versions(self, db: Session):
        template, _ = _new_template(db, "TF8")
        template_service.disable_template(db, template.id)

        with pytest.raises(ApiError) as exc:
            template_service.add_version(
                db, template.id, paper_width_mm=70, paper_height_mm=50, elements=ELEMENTS
            )
        assert "停用" in exc.value.message


class TestFreezeIsIdempotent:
    def test_freezing_twice_is_fine(self, db: Session):
        _, version = _new_template(db, "TF9")
        template_service.freeze_version(db, version.id)
        template_service.freeze_version(db, version.id)
        db.refresh(version)
        assert version.frozen is True

    def test_freezing_a_missing_version_does_not_raise(self, db: Session):
        # 幂等入口被分配与补打共用，不该因为查不到就炸
        template_service.freeze_version(db, 999999)
