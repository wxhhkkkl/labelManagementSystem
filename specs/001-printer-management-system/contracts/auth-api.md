# 契约：认证接口（两端共用）

**日期**：2026-10-12 | **规格**：[spec.md](../spec.md) | **决策**：R4 统一 JWT

---

## POST /api/v1/auth/login

**用途**：账号密码登录，返回访问令牌与刷新令牌。管理后台与工位软件共用（FR-004）。

**请求**

```json
{ "username": "op001", "password": "********" }
```

**响应 200**

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "expires_in": 7200,
  "user": {
    "id": 42,
    "username": "op001",
    "display_name": "张三",
    "role": "operator",
    "company_id": 7
  }
}
```

**说明**
- `role` ∈ `hq_admin` / `sub_admin` / `operator`。
- 工位软件登录后 MUST 额外调用 `POST /api/v1/workstation/bind` 声明本机工位（见 workstation-api）。
- 账号停用返回 `403 ACCOUNT_DISABLED`；密码错误返回 `401 INVALID_CREDENTIALS`。
- 登录成功与失败 MUST 均写入 AuditLog（FR-061）。

---

## POST /api/v1/auth/refresh

**用途**：用刷新令牌换取新的访问令牌。

**请求**：`{ "refresh_token": "<jwt>" }`

**响应 200**：同 login 的 `access_token` / `expires_in` 字段。

---

## GET /api/v1/auth/me

**用途**：获取当前登录用户与其权限范围，供前端渲染菜单与做本地预校验。

**响应 200**

```json
{
  "id": 42,
  "username": "op001",
  "display_name": "张三",
  "role": "operator",
  "company": { "id": 7, "name": "华东分公司" },
  "workstations": [{ "id": 11, "name": "一号包装工位" }]
}
```

**注**：本接口返回的权限范围仅用于前端展示，**服务端 MUST NOT 依赖前端据此过滤**（R7）。

---

## POST /api/v1/auth/logout

**用途**：登出并写审计日志。无请求体。响应 `204`。
