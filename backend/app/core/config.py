"""应用配置。

配置来源与优先级：
  1. 真实环境变量（部署时可以覆盖 .env）
  2. backend/.env（键名沿用既有约定，见下方说明）
  3. 代码内默认值

安全边界：本类**只声明应用运行所需的键**。.env 里的 SERVER_IP / SERVER_USER /
SERVER_PASSWRD / MYSQL_DB_SERVER_USER / MYSQL_DB_SERVER_PASSWRD 属部署与建库凭据，
应用进程 MUST NOT 读取（extra="ignore" 保证它们不会被加载进配置对象）。
"""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# 仅供本机开发的占位密钥；生产环境用它会被拒绝启动
DEFAULT_JWT_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- 数据库连接（键名与既有 .env 保持一致，含其拼写习惯）----
    mysql_db_server: str = "127.0.0.1"
    mysql_db_port: int = 3306
    mysql_db_name: str = "labelManagementSystemDB"
    mysql_db_user: str = ""
    mysql_db_psw: str = ""
    mysql_db_charset: str = "utf8mb4"

    # 显式连接串。留空时由上面几项组装；CI 或多环境部署可直接给整串。
    database_url_override: str | None = None

    # ---- 测试库（与生产库彻底分离）----
    # 集成/契约测试会 drop_all + create_all，MUST 指向独立的测试库。
    # 未设置此项时相关测试一律 skip，绝不回退到上面的主库。
    test_database_url: str | None = None

    # ---- 运行环境 ----
    # 生产环境（默认）会对未替换的密钥直接拒绝启动，见 assert_production_ready()
    environment: str = "production"

    # ---- 认证（research.md R4）----
    # 这个默认值只是为了本机开发方便。生产必须由 JWT_SECRET 覆盖——
    # 否则任何知道它的人都能伪造任意角色（含总部管理员）的令牌。
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_seconds: int = 2 * 60 * 60  # 2 小时
    refresh_token_seconds: int = 7 * 24 * 60 * 60  # 7 天

    # ---- 打印锁超时（FR-047）----
    print_lock_timeout_seconds: int = 300

    # ---- 工位心跳与离线判定（research.md R1）----
    heartbeat_interval_seconds: int = 5
    offline_threshold_seconds: int = 30
    # 补打任务超过该时长仍无人领取即过期（T111），避免工位恢复后执行陈年任务
    print_task_ttl_seconds: int = 3600

    # ---- 导入（research.md R3）----
    import_batch_size: int = 1000
    import_max_rows: int = 200_000  # 单批上限，待甲方确认 OI-02 后调整
    # 上传文件与失败明细的落盘目录（相对 backend/）
    import_storage_dir: str = "var/imports"
    # 码值重复时的策略（FR-017）：reject_batch 整批拒绝（默认）| skip_row 按行跳过
    import_duplicate_policy: str = "reject_batch"

    # ---- 分页 ----
    default_page_size: int = 20
    max_page_size: int = 200

    @property
    def db_url(self) -> str:
        """应用使用的连接串。

        密码可能含 @ : / 等字符，必须做 URL 编码，否则连接串会被解析错位。
        """
        if self.database_url_override:
            return self.database_url_override
        user = quote_plus(self.mysql_db_user)
        psw = quote_plus(self.mysql_db_psw)
        return (
            f"mysql+pymysql://{user}:{psw}"
            f"@{self.mysql_db_server}:{self.mysql_db_port}"
            f"/{self.mysql_db_name}?charset={self.mysql_db_charset}"
        )

    @property
    def db_url_safe(self) -> str:
        """脱敏后的连接串，仅用于日志与排障输出。"""
        return (
            f"mysql+pymysql://{self.mysql_db_user}:***"
            f"@{self.mysql_db_server}:{self.mysql_db_port}/{self.mysql_db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


class InsecureConfigurationError(RuntimeError):
    """配置不安全，拒绝启动。"""


def assert_production_ready() -> None:
    """生产环境启动前的安全闸（T158）。

    用默认密钥意味着任何人都能签发"总部管理员"令牌，
    从而拿到全集团的码、模板与审计——这比服务不可用严重得多。
    所以这里**拒绝启动**而不是打条警告：警告在日志里太容易被忽略。

    本机开发把 ENVIRONMENT 设为 development 即可跳过。
    """
    settings = get_settings()
    if settings.environment.lower() in ("development", "dev", "test"):
        return

    problems: list[str] = []
    if settings.jwt_secret == DEFAULT_JWT_SECRET:
        problems.append(
            "JWT_SECRET 仍是默认值。生成随机值后写入 backend/.env："
            'python -c "import secrets;print(secrets.token_urlsafe(48))"'
        )
    if not settings.mysql_db_psw:
        problems.append("MYSQL_DB_PSW 为空，数据库连接串会缺少密码。")

    if problems:
        raise InsecureConfigurationError("检测到不安全的配置，拒绝启动：" + "；".join(problems))
