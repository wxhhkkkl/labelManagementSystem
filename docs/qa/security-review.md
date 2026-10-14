# 安全复查（T158）

**日期**：2026-10-12 | **范围**：全链路 HTTPS、会话与密钥安全（非功能需求·安全）

复查方式：在代码里逐项查证，而不是写一份泛泛的清单。下面每条都注明**查证方法与结论**。

---

## 结论摘要

| 项 | 结论 |
|----|------|
| 密码存储 | ✅ 通过（bcrypt 加盐） |
| 令牌不落日志 | ✅ 通过 |
| SQL 注入 | ✅ 通过（全部参数化） |
| 组织隔离 | ✅ 通过（服务端强制，有专项测试） |
| 越权留痕 | ✅ 通过（本轮修复，见下） |
| **密钥管理** | ⚠️ **发现严重问题并已修复**（见下） |
| 全链路 HTTPS | ⚠️ 由 nginx 保证，部署后需自检 |

---

## 一、密钥管理：发现严重问题，已修复

### 问题

`app/core/config.py` 里 `jwt_secret` 带了一个硬编码默认值 `dev-only-change-me`，
而 `backend/.env` 里**没有设置 `JWT_SECRET`**。

后果：照当时的配置部署，应用会用这个公开的默认值签发令牌。
**任何知道这个值的人都能伪造总部管理员令牌**，进而拿到全集团的码、模板、
分配与审计数据——这比服务不可用严重得多。

### 修复

新增启动安全闸 `assert_production_ready()`（`app/core/config.py`），
在应用 lifespan 里首先执行：

- 生产环境（默认）若 `JWT_SECRET` 仍是默认值 → **拒绝启动**，并给出生成随机值的命令
- 若 `MYSQL_DB_PSW` 为空 → 同样拒绝启动
- 本机开发把 `ENVIRONMENT=development` 即可跳过

选择"拒绝启动"而不是"打条警告"：警告在日志里太容易被忽略，
而这类问题的代价是不可逆的数据泄露。

**部署前必做**：

```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"
# 把输出写入 backend/.env 的 JWT_SECRET=
```

### 为什么测试没受影响

测试用的 `TestClient` 不进入 lifespan，因此安全闸只在真实启动时生效；
本机开发设 `ENVIRONMENT=development` 亦可绕过。已实测三种情形。

---

## 二、密码存储

**方法**：查 `app/core/security.py` 的哈希实现。

**结论**：使用 `bcrypt` 加盐哈希（`bcrypt.hashpw` / `checkpw`），
每个密码独立盐值，同一明文两次哈希结果不同（有单测覆盖）。

**额外处理**：bcrypt 只处理前 72 字节，超长密码会被截断——
`_prepare()` 显式做了这件事，避免直接抛异常。这是一处容易被忽略的边界。

**未做**：密码强度策略（长度/复杂度）由前端与接口的 `min_length=6` 约束，
没有做"必须含大小写数字"这类规则。**这是有意为之**——强复杂度要求会促使
用户写便签，对内部系统的净收益存疑。如需强制，属产品决策而非安全缺陷。

---

## 三、令牌不落日志

**方法**：全局搜索 `logger.*` 与 `print(` 中是否出现 token/password/secret。

**结论**：未发现任何把令牌或密码写入日志的位置。

**设计约束**：`Settings.db_url_safe` 提供脱敏连接串用于排障输出，
日志中应使用它而不是 `db_url`。

**已知限制**：登录失败时，若账号不存在则无法归因，此时不写审计记录
（`AuditLog.operator_id` 非空）。这是数据模型约束下的取舍，
已在 `auth.py` 注释中说明。

---

## 四、SQL 注入

**方法**：搜索 `execute(f"`、`text(f"`、字符串格式化进 `execute` 的位置。

**结论**：未发现拼接式 SQL。唯一用到字符串拼接的是建库语句
（库名来自配置且有白名单校验），不涉及用户输入。

---

## 五、组织隔离

**方法**：检查隔离是否收敛在一处，以及有没有测试守着。

**结论**：隔离实现集中在 `app/core/scope.py`，所有列表与详情查询都经它注入过滤。
有专项测试断言"子公司查询结果中他公司数据出现 0 次"（SC-007），
覆盖工作站、账号、报表、台账、码时间线等多个出口。

---

## 六、越权留痕（本轮修复）

**发现**：FR-007 要求"越权请求 MUST 写入操作日志"，
但 `audit.record_denied()` 写好后**从未被调用过**——403 响应不留任何痕迹。

**修复**：在全局异常处理器（`app/main.py` 的 `business_error_handler`）里统一记录。
不逐个接口补埋点，因为越权校验散落在服务层十余处，逐个补必然漏。

---

## 七、全链路 HTTPS

**方法**：检查应用侧是否有明文出口。

**结论**：应用本身不处理 TLS，由 nginx 终止（见 `docs/ops/nginx.conf`），
其中已配置：

- 80 端口强制 301 跳转 443
- `Strict-Transport-Security` 响应头
- `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy`
- 健康检查仅允许 127.0.0.1 访问

**部署后 MUST 自检**：

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://meichao.yuwangchenfa.com/          # 期望 301
curl -sS -o /dev/null -w '%{http_code}\n' https://meichao.yuwangchenfa.com/api/v1/auth/me  # 期望 401
curl -sSI https://meichao.yuwangchenfa.com/ | grep -i strict-transport               # 期望有输出
```

第二条返回 401 才说明反代与鉴权都通了；返回 404 说明 `/api/` 的 location 没生效。

---

## 仍需人工处理的事项（不在代码可控范围）

| 事项 | 说明 |
|------|------|
| **JWT_SECRET 必须设置** | 见第一节。不设置则服务拒绝启动，这是刻意的 |
| **数据库账号建议换最小权限** | 当前 `.env` 用 `root`。建库脚本 `docs/ops/bootstrap.sql` 里有 `lms_app` 的建法 |
| **数据库机 Redis 暴露面** | `0.0.0.0:6379` 监听，未验证是否设认证。建议确认并限制来源 |
| **令牌吊销** | JWT 无法即时吊销。本期靠"短有效期 + 每次请求实时校验账号状态"缓解；强制下线依赖账号停用 |
