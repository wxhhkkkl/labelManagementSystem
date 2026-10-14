"""测试夹具。

T006 明确要求：集成与契约测试使用**真实 MySQL**，MUST NOT 用 SQLite 替代——
SQLite 的单写者模型测不出 FR-044 的并发语义（research.md R2）。

MySQL 不可用时，依赖数据库的测试会被 **skip**（而不是假装通过）。
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import Base
from app.models.company import Company
from app.models.user import User
from app.models.workstation import Workstation


def _test_db_url() -> str:
    """解析测试库连接串，并拦下任何可能打到主库的配置。

    本夹具会 drop_all + create_all。若连接串指向应用主库，跑一次 pytest 就会清空
    生产数据。因此这里设两道闸：
      1. MUST 显式设置 TEST_DATABASE_URL，不提供则整体跳过；
      2. 其库名 MUST 包含 "test"，且 MUST NOT 与应用主库同名。
    """
    settings = get_settings()
    url = settings.test_database_url
    if not url:
        pytest.skip(
            "未设置 TEST_DATABASE_URL，跳过需要数据库的测试。"
            "集成/契约测试需要一个独立的测试库——它们会先清空再建表。",
            allow_module_level=True,
        )

    if url == settings.db_url:
        raise RuntimeError(
            "TEST_DATABASE_URL 与应用主库 (DB) 完全相同，拒绝执行："
            "测试会 drop_all 清空该库。请另建一个测试库。"
        )

    db_name = url.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in db_name.lower():
        raise RuntimeError(
            f"测试库名 {db_name!r} 不含 'test'，拒绝执行以免误清生产数据。"
            "请把库名改为形如 labelManagementSystemDB_test。"
        )
    return url


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = create_engine(_test_db_url(), pool_pre_ping=True, future=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"测试库不可达，跳过需要数据库的测试：{exc}")

    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """每个测试跑在自己的事务里，结束时回滚，用例之间互不污染。

    join_transaction_mode='create_savepoint' 让被测代码内部的 session.commit()
    只提交到 savepoint，不会真的落库。
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    # 不用 with：避免触发 lifespan 里的导入中断恢复（那会连真实库）
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------- 组织与账号夹具 ----------


@pytest.fixture
def hq_company(db: Session) -> Company:
    """总部不占 Company 记录，这里只建一个子公司用于测试。"""
    company = Company(code="C001", name="华东分公司", region="上海", status="active")
    db.add(company)
    db.flush()
    return company


@pytest.fixture
def other_company(db: Session) -> Company:
    company = Company(code="C002", name="华南分公司", region="广州", status="active")
    db.add(company)
    db.flush()
    return company


def make_user(
    db: Session,
    *,
    username: str,
    role: str,
    company: Company | None = None,
    password: str = "pw123456",
) -> User:
    user = User(
        username=username,
        display_name=username,
        password_hash=hash_password(password),
        role=role,
        company_id=company.id if company else None,
        status="active",
    )
    db.add(user)
    db.flush()
    return user


def auth_header(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role, user.company_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def hq_admin(db: Session) -> User:
    return make_user(db, username="hq", role="hq_admin")


@pytest.fixture
def sub_admin(db: Session, hq_company: Company) -> User:
    return make_user(db, username="sub1", role="sub_admin", company=hq_company)


@pytest.fixture
def other_sub_admin(db: Session, other_company: Company) -> User:
    return make_user(db, username="sub2", role="sub_admin", company=other_company)


@pytest.fixture
def operator(db: Session, hq_company: Company) -> User:
    return make_user(db, username="op1", role="operator", company=hq_company)


@pytest.fixture
def workstation(db: Session, hq_company: Company, operator: User) -> Workstation:
    ws = Workstation(
        code="W001",
        name="一号包装工位",
        company_id=hq_company.id,
        printer_name="Zebra ZD421",
        status="active",
    )
    db.add(ws)
    db.flush()
    return ws


# ---------- 产品与导入 ----------


@pytest.fixture
def product(db: Session):
    from app.models.product import Product

    item = Product(code="P001", name="500ml 矿泉水", spec="500ml", status="active")
    db.add(item)
    db.flush()
    return item


@pytest.fixture
def import_storage(tmp_path, monkeypatch) -> str:
    """把导入文件目录指向临时目录，避免测试往 backend/var 里写东西。"""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "import_storage_dir", str(tmp_path))
    return str(tmp_path)


@pytest.fixture
def template_version(db: Session, product):
    """给产品绑定一个含单版本的默认模板，并把该版本返回。

    分配单的 template_version_id 是 NOT NULL（FR-035），任何分配测试都需要它。
    """
    from app.models.template import Template, TemplateVersion

    template = Template(code="TPL1", name="标准标签模板", status="active")
    db.add(template)
    db.flush()

    version = TemplateVersion(
        template_id=template.id,
        version_no=1,
        paper_width_mm=60,
        paper_height_mm=40,
        elements_json={
            "paper_width_mm": 60,
            "paper_height_mm": 40,
            "elements": [
                {"type": "field", "x": 2, "y": 2, "field_name": "code_value", "font_size": 3}
            ],
        },
        frozen=False,
    )
    db.add(version)
    db.flush()

    product.default_template_id = template.id
    db.flush()
    return version


@pytest.fixture
def import_batch(db: Session, hq_admin: User):
    """已完成的批次。

    Code.import_batch_id 是外键，构造码时不能随便写一个数字——
    必须有真实的批次行，否则会撞 FK 约束。
    """
    from app.models.import_batch import ImportBatch

    batch = ImportBatch(
        batch_no="IMPFIX",
        code_list_filename="code_list.xlsx",
        mapping_filename="mapping.xlsx",
        status="succeeded",
        processed_rows=0,
        success_count=0,
        failure_count=0,
        created_by=hq_admin.id,
    )
    db.add(batch)
    db.flush()
    return batch
