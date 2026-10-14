"""公司服务（FR-001、FR-003）。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.models.company import Company


def list_companies(db: Session, *, keyword: str | None = None) -> list[Company]:
    stmt = select(Company).order_by(Company.code)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(Company.name.like(like) | Company.code.like(like))
    return list(db.execute(stmt).scalars())


def get_company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise ApiError(ErrorCode.NOT_FOUND, "公司不存在")
    return company


def get_by_code(db: Session, code: str) -> Company | None:
    return db.execute(select(Company).where(Company.code == code)).scalar_one_or_none()


def create_company(db: Session, *, code: str, name: str, contact=None, region=None) -> Company:
    if get_by_code(db, code) is not None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"公司编码已存在：{code}")
    company = Company(code=code, name=name, contact=contact, region=region, status="active")
    db.add(company)
    db.flush()
    return company


def update_company(db: Session, company_id: int, **fields) -> Company:
    company = get_company(db, company_id)
    for key in ("name", "contact", "region"):
        if key in fields and fields[key] is not None:
            setattr(company, key, fields[key])
    db.flush()
    return company


def disable_company(db: Session, company_id: int) -> Company:
    """停用公司（FR-003）。

    停用后不可再被分配新码、不可再执行打印；历史数据保留可查。
    在途的"已分配未打印"码不会被自动处理——口径与产品停用不同，见 spec 边界情况。
    """
    company = get_company(db, company_id)
    company.status = "disabled"
    db.flush()
    return company


def count_workstations(db: Session, company_id: int) -> int:
    from app.models.workstation import Workstation

    return db.execute(
        select(func.count()).select_from(Workstation).where(Workstation.company_id == company_id)
    ).scalar_one()
