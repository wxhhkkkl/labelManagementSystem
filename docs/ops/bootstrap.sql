-- ---------------------------------------------------------------------------
-- 打印管理系统 · 数据库初始化（不使用 Docker，直接在 MySQL 服务器上执行）
--
-- 用管理员账号执行一次即可。执行前请把 <APP_PASSWORD> 换成 MYSQL_DB_PSW 的值。
-- ---------------------------------------------------------------------------

-- 1) 主库。字符集必须是 utf8mb4：码值与模板元素含中文。
CREATE DATABASE IF NOT EXISTS `labelManagementSystemDB`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

-- 2) 测试库。集成/契约测试会先清空再建表，必须与主库分开。
CREATE DATABASE IF NOT EXISTS `labelManagementSystemDB_test`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

-- 3) 应用账号（最小权限：只有数据读写，没有 DDL 之外的额外权限）。
--    账号名与密码见 .env 的 MYSQL_DB_USER / MYSQL_DB_PSW。
CREATE USER IF NOT EXISTS 'lms_app'@'%' IDENTIFIED BY '<APP_PASSWORD>';

GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE, SHOW VIEW
  ON `labelManagementSystemDB`.* TO 'lms_app'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES
  ON `labelManagementSystemDB_test`.* TO 'lms_app'@'%';

FLUSH PRIVILEGES;

-- ---------------------------------------------------------------------------
-- 说明：
--  * 主库给的是 DML 权限，不含 CREATE/DROP——建表由 Alembic 迁移完成。
--    若希望应用账号能自行执行迁移，把下面这行也执行掉（权限更大，二选一）：
--      GRANT CREATE, ALTER, DROP, INDEX, REFERENCES ON `labelManagementSystemDB`.* TO 'lms_app'@'%';
--  * 测试库给了完整 DDL 权限，因为测试夹具每次都会 drop_all + create_all。
-- ---------------------------------------------------------------------------
