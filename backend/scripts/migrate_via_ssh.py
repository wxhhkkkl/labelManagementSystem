"""通过 SSH 隧道对远端 MySQL 执行建库与 Alembic 迁移。

背景：生产 MySQL 的 3306 未对公网开放（仅 SSH 可达），本机无法直连。
本脚本从本机拉起 SSH 本地转发（127.0.0.1:13306 -> MySQL 主机 127.0.0.1:3306），
再经隧道执行建库与迁移。

重要：隧道必须落在**运行 MySQL 的那台机器**上。
.env 里 SERVER_IP（应用服务器）与 MYSQL_DB_SERVER（数据库服务器）是两台不同的机器，
误用前者会连到一台没有 MySQL 的主机上。默认取 MYSQL_DB_SERVER，可用
MYSQL_SSH_HOST 覆盖。

凭据来源：
  - SSH：SERVER_USER / SERVER_PASSWRD（直接从 .env 读，**不进入 Settings**）
  - MySQL：MYSQL_DB_*（走 app.core.config.Settings，以便复用默认值）

用法：
    python scripts/migrate_via_ssh.py --check
    python scripts/migrate_via_ssh.py --create-db --upgrade --verify
"""

from __future__ import annotations

import argparse
import os
import select
import socketserver
import subprocess
import sys
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

LOCAL_PORT = 13306
REMOTE_MYSQL_HOST = "127.0.0.1"


def load_env() -> dict[str, str]:
    """极简 .env 解析，只用来取 **SSH 凭据**——它们刻意不进 Settings。"""
    if not ENV_FILE.exists():
        sys.exit(f"找不到 {ENV_FILE}")
    values: dict[str, str] = {}
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def db_settings():
    """复用应用配置（含 .env 与默认值），避免这里再抄一份库名/端口。"""
    sys.path.insert(0, str(BACKEND_DIR))
    from app.core.config import get_settings

    return get_settings()


class _ForwardServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def _make_handler(transport, chain_host: str, chain_port: int):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            try:
                chan = transport.open_channel(
                    "direct-tcpip",
                    (chain_host, chain_port),
                    self.request.getpeername(),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  ! 隧道建立失败: {exc}")
                return
            try:
                while True:
                    readable, _, _ = select.select([self.request, chan], [], [])
                    if self.request in readable:
                        data = self.request.recv(4096)
                        if not data:
                            break
                        chan.sendall(data)
                    if chan in readable:
                        data = chan.recv(4096)
                        if not data:
                            break
                        self.request.sendall(data)
            finally:
                chan.close()
                self.request.close()

    return Handler


def open_tunnel(env: dict[str, str], settings):
    """SSH 落到**应用机**，再由应用机转发到数据库机。

    这一点很关键：MySQL 只授予了 root@<应用机内网IP>，所以 TCP 连接 MUST 由应用机
    发起。若 SSH 直接落在数据库机（或在数据库机上转发到 127.0.0.1），MySQL 看到的
    来源是 localhost，会匹配到另一条账号而被拒绝。
    """
    import paramiko

    ssh_host = env.get("MYSQL_SSH_HOST") or env.get("SERVER_IP") or settings.mysql_db_server
    chain_host = settings.mysql_db_server
    chain_port = settings.mysql_db_port

    print(f"[隧道] SSH 落点（应用机）: {env['SERVER_USER']}@{ssh_host}:22")
    print(f"[隧道] 转发目标（数据库）: {chain_host}:{chain_port}")
    if ssh_host == chain_host:
        print("[隧道] ! SSH 落点与数据库地址相同，连接来源会退化为 localhost，可能被 MySQL 拒绝")

    transport = paramiko.Transport((ssh_host, 22))
    transport.connect(username=env["SERVER_USER"], password=env["SERVER_PASSWRD"])

    handler = _make_handler(transport, chain_host, chain_port)
    server = _ForwardServer(("127.0.0.1", LOCAL_PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[隧道] 已建立 127.0.0.1:{LOCAL_PORT} -> {ssh_host} -> {chain_host}:{chain_port}")
    return transport, server


def tunnel_url(settings, database: str | None) -> str:
    from urllib.parse import quote_plus

    u = quote_plus(settings.mysql_db_user)
    p = quote_plus(settings.mysql_db_psw)
    return (
        f"mysql+pymysql://{u}:{p}@127.0.0.1:{LOCAL_PORT}/{database or ''}"
        f"?charset={settings.mysql_db_charset}"
    )


def masked(settings, database: str) -> str:
    return (
        f"mysql+pymysql://{settings.mysql_db_user}:***"
        f"@127.0.0.1:{LOCAL_PORT}/{database}?charset={settings.mysql_db_charset}"
    )


def check(env: dict[str, str], settings) -> None:
    from sqlalchemy import create_engine, text

    eng = create_engine(tunnel_url(settings, None), connect_args={"connect_timeout": 15})
    with eng.connect() as conn:
        version = str(conn.execute(text("SELECT VERSION()")).scalar())
        databases = [r[0] for r in conn.execute(text("SHOW DATABASES")).fetchall()]
    eng.dispose()

    print(f"[自检] MySQL 版本: {version}")
    ok = tuple(int(x) for x in version.split(".")[:2]) >= (8, 0)
    print(f"[自检] 满足 8.0+（SKIP LOCKED 依赖）: {'是' if ok else '否 —— 迁移前必须升级'}")

    main_db = settings.mysql_db_name
    test_db = f"{main_db}_test"
    print(f"[自检] 现有库: {databases}")
    print(f"[自检] 主库 {main_db} 已存在: {main_db in databases}")
    print(f"[自检] 测试库 {test_db} 已存在: {test_db in databases}")


def create_databases(settings) -> None:
    from sqlalchemy import create_engine, text

    names = [settings.mysql_db_name, f"{settings.mysql_db_name}_test"]
    eng = create_engine(tunnel_url(settings, None), connect_args={"connect_timeout": 15})
    with eng.begin() as conn:
        for name in names:
            # 库名来自配置而非用户输入；这里再做一次白名单校验，防配置文件被写坏
            if not name.replace("_", "").isalnum():
                raise ValueError(f"库名含非法字符，拒绝执行: {name!r}")
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{name}` "
                    "DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci"
                )
            )
            print(f"[建库] {name} 就绪")
    eng.dispose()


def upgrade(settings) -> int:
    print(f"[迁移] 目标 {masked(settings, settings.mysql_db_name)}")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={
            **os.environ,
            "DATABASE_URL_OVERRIDE": tunnel_url(settings, settings.mysql_db_name),
            "PYTHONIOENCODING": "utf-8",
        },
        check=False,
    )
    return result.returncode


def verify(settings) -> None:
    from sqlalchemy import create_engine, text

    eng = create_engine(
        tunnel_url(settings, settings.mysql_db_name), connect_args={"connect_timeout": 15}
    )
    with eng.connect() as conn:
        names = sorted(r[0] for r in conn.execute(text("SHOW TABLES")).fetchall())
    eng.dispose()
    print(f"[校验] 共 {len(names)} 张表:")
    for n in names:
        print(f"         {n}")


def run_tests(settings, pytest_args: list[str]) -> int:
    """在隧道开着的情况下跑 pytest。

    集成/契约测试需要一个测试库（它们会 drop_all + create_all），
    这里把 TEST_DATABASE_URL 指向 <主库名>_test，经同一条隧道访问。
    conftest 的防护会再次确认库名含 "test" 且与主库不同。
    """
    test_db = f"{settings.mysql_db_name}_test"
    print(f"[测试] 测试库 {masked(settings, test_db)}")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *pytest_args],
        cwd=BACKEND_DIR,
        env={
            **os.environ,
            "TEST_DATABASE_URL": tunnel_url(settings, test_db),
            "PYTHONIOENCODING": "utf-8",
        },
        check=False,
    )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="经 SSH 隧道执行建库与迁移")
    parser.add_argument("--check", action="store_true", help="只做连通性与版本自检")
    parser.add_argument("--create-db", action="store_true", help="创建主库与测试库")
    parser.add_argument("--upgrade", action="store_true", help="执行 alembic upgrade head")
    parser.add_argument("--verify", action="store_true", help="列出目标库中的表")
    parser.add_argument("--test", action="store_true", help="在隧道内跑 pytest（用测试库）")
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        help="传给 pytest 的参数，例如 -- --markers 或 -- tests/unit",
    )
    args = parser.parse_args()

    if not any([args.check, args.create_db, args.upgrade, args.verify, args.test]):
        parser.print_help()
        return 1

    env = load_env()
    settings = db_settings()
    transport, server = open_tunnel(env, settings)
    try:
        if args.check:
            check(env, settings)
        if args.create_db:
            create_databases(settings)
        if args.upgrade:
            code = upgrade(settings)
            if code != 0:
                print(f"[迁移] 失败，退出码 {code}")
                return code
            print("[迁移] 完成")
        if args.verify:
            verify(settings)
        if args.test:
            code = run_tests(settings, list(args.pytest_args or []))
            print(f"[测试] pytest 退出码 {code}")
    finally:
        server.shutdown()
        server.server_close()
        transport.close()
        print("[隧道] 已关闭")
    return 0


if __name__ == "__main__":
    sys.exit(main())
