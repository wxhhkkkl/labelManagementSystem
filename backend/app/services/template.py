"""T121 / T123：模板管理与版本冻结（FR-032 ~ FR-034）。

两条不可动摇的规则：

1. **版本不可变**：修改模板 MUST 新建版本并递增 version_no，
   MUST NOT 改动既有版本行（FR-033）。历史版本要能原样复现。
2. **被引用即冻结**：一旦某个版本被分配单或补打任务引用，其内容就冻结（FR-034），
   后续改模板不影响已经发出去的活。

冻结逻辑集中在本模块的 freeze_version()，分配与补打都调它——
散成两处迟早会走叉。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, ErrorCode
from app.models.product import Product
from app.models.template import Template, TemplateVersion
from app.schemas.template import to_document

# 新建模板但未指定纸张尺寸时的默认版面
DEFAULT_PAPER_MM = (60.0, 40.0)


def get_template(db: Session, template_id: int) -> Template:
    template = db.get(Template, template_id)
    if template is None:
        raise ApiError(ErrorCode.NOT_FOUND, "模板不存在")
    return template


def get_by_code(db: Session, code: str) -> Template | None:
    return db.execute(select(Template).where(Template.code == code)).scalar_one_or_none()


def current_version(db: Session, template_id: int) -> TemplateVersion | None:
    """取最新版本（version_no 最大的那条）。"""
    return db.execute(
        select(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
        .order_by(TemplateVersion.version_no.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_version(db: Session, version_id: int) -> TemplateVersion:
    version = db.get(TemplateVersion, version_id)
    if version is None:
        raise ApiError(ErrorCode.NOT_FOUND, "模板版本不存在")
    return version


def list_templates(db: Session) -> list[tuple[Template, int, int | None]]:
    """返回 (模板, 版本数, 当前版本号)。"""
    templates = list(db.execute(select(Template).order_by(Template.code)).scalars())
    if not templates:
        return []

    rows = db.execute(
        select(
            TemplateVersion.template_id,
            func.count().label("count"),
            func.max(TemplateVersion.version_no).label("latest"),
        )
        .where(TemplateVersion.template_id.in_([t.id for t in templates]))
        .group_by(TemplateVersion.template_id)
    ).all()
    stats = {tid: (int(count), int(latest)) for tid, count, latest in rows}
    return [(t, *stats.get(t.id, (0, None))) for t in templates]


def list_versions(db: Session, template_id: int) -> list[TemplateVersion]:
    get_template(db, template_id)
    return list(
        db.execute(
            select(TemplateVersion)
            .where(TemplateVersion.template_id == template_id)
            .order_by(TemplateVersion.version_no.desc())
        ).scalars()
    )


def create_template(
    db: Session,
    *,
    code: str,
    name: str,
    paper_width_mm: float | None = None,
    paper_height_mm: float | None = None,
    elements: list | None = None,
) -> tuple[Template, TemplateVersion]:
    if get_by_code(db, code) is not None:
        raise ApiError(ErrorCode.VALIDATION_ERROR, f"模板编码已存在：{code}")

    width = paper_width_mm or DEFAULT_PAPER_MM[0]
    height = paper_height_mm or DEFAULT_PAPER_MM[1]

    template = Template(code=code, name=name, status="active")
    db.add(template)
    db.flush()

    version = TemplateVersion(
        template_id=template.id,
        version_no=1,
        paper_width_mm=width,
        paper_height_mm=height,
        elements_json=to_document(width, height, elements or []),
        frozen=False,
    )
    db.add(version)
    db.flush()
    return template, version


def add_version(
    db: Session,
    template_id: int,
    *,
    paper_width_mm: float,
    paper_height_mm: float,
    elements: list,
) -> TemplateVersion:
    """修改模板 = 追加新版本（FR-033）。"""
    template = get_template(db, template_id)
    if template.status != "active":
        raise ApiError(ErrorCode.VALIDATION_ERROR, "停用的模板不可再新增版本")

    latest = current_version(db, template_id)
    next_no = (latest.version_no if latest else 0) + 1

    version = TemplateVersion(
        template_id=template_id,
        version_no=next_no,
        paper_width_mm=paper_width_mm,
        paper_height_mm=paper_height_mm,
        elements_json=to_document(paper_width_mm, paper_height_mm, elements),
        frozen=False,
    )
    db.add(version)
    db.flush()
    return version


def replace_version_content(
    db: Session,
    version_id: int,
    *,
    paper_width_mm: float,
    paper_height_mm: float,
    elements: list,
) -> TemplateVersion:
    """就地修改某个版本 —— 仅在该版本尚未被引用时允许。

    被引用过的版本 MUST 冻结（FR-034），这里直接拒绝，
    避免"改了模板导致已发出的分配单印出来的东西变了"。
    """
    version = get_version(db, version_id)
    if version.frozen:
        raise ApiError(
            ErrorCode.TEMPLATE_VERSION_FROZEN,
            "该版本已被分配单或补打任务引用，内容已冻结，请改为新增版本",
        )

    version.paper_width_mm = paper_width_mm
    version.paper_height_mm = paper_height_mm
    version.elements_json = to_document(paper_width_mm, paper_height_mm, elements)
    db.flush()
    return version


def freeze_version(db: Session, version_id: int) -> None:
    """标记版本为冻结（FR-034）。幂等。

    由分配单创建与补打任务创建共同调用——集中在一处，
    新增引用点时才不会漏掉冻结。
    """
    version = db.get(TemplateVersion, version_id)
    if version is None:
        return
    if not version.frozen:
        version.frozen = True
    db.flush()


def disable_template(db: Session, template_id: int) -> Template:
    """停用模板（FR-032）。

    只影响后续新的分配与绑定；已冻结的历史版本继续可用于打印与补打
    （spec 假设），因此这里不校验引用情况。
    """
    template = get_template(db, template_id)
    template.status = "disabled"
    db.flush()
    return template


def delete_check(db: Session, template_id: int) -> list[str]:
    """模板被哪些产品当作默认模板引用 —— 停用前提示用。"""
    rows = db.execute(
        select(Product.code).where(Product.default_template_id == template_id)
    ).scalars()
    return list(rows)
