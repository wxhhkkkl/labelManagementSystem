# 接口契约：打印管理系统

**功能**：[spec.md](../spec.md) | **日期**：2026-10-12

本目录定义管理后台与工位软件共用的 HTTP 接口契约。两端 MUST 只通过本契约交互
（宪章原则六：工位软件 MUST NOT 直接访问服务端数据存储）。

## 通用约定

- **协议**：HTTPS，JSON 请求与响应体，`Content-Type: application/json`（文件上传除外）。
- **认证**：`Authorization: Bearer <access_token>`（R4 统一 JWT）。令牌载荷含 `user_id` / `role` /
  `company_id` / `workstation_id`（工位端）。
- **组织隔离**：服务端按令牌中的 `role` 与 `company_id` 强制注入过滤条件，**不接受客户端传入的
  `company_id` 作为查询依据**（R7）。越权访问返回 `403` 并写 `AuditLog(result='denied')`（FR-007）。
- **时间**：一律 ISO 8601 UTC，如 `2026-10-12T08:30:00Z`。
- **分页**：`page`（从 1 起）+ `page_size`（默认 20，上限 200），响应含 `total`。

## 统一错误响应

```json
{
  "error_code": "CODE_ALREADY_PRINTED",
  "message": "该码已打印，不可重复打印",
  "details": {}
}
```

`error_code` 为稳定标识，供前端做分支处理与自动化测试断言；`message` 面向用户，可调整。

## 关键错误码

| error_code | HTTP | 触发场景 | 规格 |
|------------|------|----------|------|
| `INVALID_CREDENTIALS` | 401 | 账号或密码错误 | FR-004 |
| `ACCOUNT_DISABLED` | 403 | 账号已停用（每次请求实时校验） | R4 |
| `FORBIDDEN_SCOPE` | 403 | 越权访问他公司数据 | FR-006 / FR-007 |
| `CODE_ALREADY_PRINTED` | 409 | 对"已打印"的码再次发起打印 | FR-043 |
| `CODE_LOCKED` | 409 | 该码正被其他工位打印（并发抢占失败） | FR-044 |
| `CODE_NOT_PRINTED` | 409 | 对非"已打印"的码发起补打 | FR-051 |
| `CODE_VOIDED` | 409 | 码已作废 | FR-053 |
| `REASON_REQUIRED` | 400 | 补打或作废未填原因 | FR-053 / FR-058 |
| `WORKSTATION_OFFLINE` | 409 | 补打目标工位离线（心跳超时） | FR-056 |
| `WORKSTATION_DISABLED` | 409 | 工位或所属公司已停用 | FR-003 |
| `PRODUCT_HAS_ALLOCATED_CODES` | 409 | 产品停用前仍有"已分配未打印"的码 | FR-010 |
| `INSUFFICIENT_STOCK` | 409 | 分配的可用码量不足（`details.available` 给可用数） | FR-025 |
| `IMPORT_CODE_SET_MISMATCH` | 400 | 码清单与对照关系文件码集合不一致 | FR-014 |
| `IMPORT_DUPLICATE_CODE` | 400 | 存在与库中重复的码值且策略为整批拒绝 | FR-017 |
| `TEMPLATE_VERSION_FROZEN` | 409 | 尝试修改已被引用的模板版本 | FR-034 |

## 契约文件

| 文件 | 面向 | 覆盖 |
|------|------|------|
| [auth-api.md](./auth-api.md) | 两端共用 | 登录、刷新、当前用户 |
| [admin-api.md](./admin-api.md) | 管理后台（浏览器） | 组织/产品/导入/分配/模板/补打作废/报表/日志 |
| [workstation-api.md](./workstation-api.md) | 工位软件（Electron） | 工位绑定、可打印码、打印、任务轮询、心跳、打印机设置 |
| [template-rendering.md](./template-rendering.md) | 两端各自实现 | 模板渲染语义（坐标/换算/元素/动态字段），保证"所见即所打" |

## 契约测试要求

每个接口 MUST 有对应的契约测试（`backend/tests/contract/`），先写后实现（宪章原则一）。
契约测试 MUST 至少覆盖：正常返回结构、上表所列错误码、以及**越权用例**（以子公司令牌访问他公司资源，
断言 `403` + `FORBIDDEN_SCOPE`）。接口结构变更时 MUST 同步更新本目录与契约测试。
