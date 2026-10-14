"""组织树接口（FR-008）。总部管理员按公司汇总下钻查看工位。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import HqAdmin
from app.models.company import Company
from app.models.workstation import Workstation
from app.schemas.org import OrgTreeNode
from app.api.v1.workstations import serialize as serialize_workstation

router = APIRouter(prefix="/org", tags=["org"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/tree", response_model=list[OrgTreeNode])
def org_tree(user: HqAdmin, db: DbSession) -> list[OrgTreeNode]:
    """公司 -> 工位 的两级树。总部专属视图，不做组织过滤。"""
    companies = list(db.execute(select(Company).order_by(Company.code)).scalars())
    stations = list(
        db.execute(select(Workstation).order_by(Workstation.company_id, Workstation.code)).scalars()
    )
    by_company: dict[int, list] = {}
    for ws in stations:
        by_company.setdefault(ws.company_id, []).append(serialize_workstation(db, ws))

    return [
        OrgTreeNode(
            id=c.id,
            code=c.code,
            name=c.name,
            status=c.status,
            workstations=by_company.get(c.id, []),
        )
        for c in companies
    ]
