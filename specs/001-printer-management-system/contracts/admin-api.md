# 契约：管理后台接口

**日期**：2026-10-12 | **规格**：[spec.md](../spec.md) | **适用角色**：总部管理员、子公司管理员

所有接口按 R7 强制组织隔离；下表"角色"列标注最低权限要求。总部管理员除特别说明外拥有全部权限。

---

## 组织与账号

| 方法 | 路径 | 用途 | 角色 | 规格 |
|------|------|------|------|------|
| POST | `/api/v1/companies` | 创建公司 | 总部 | FR-001 |
| PATCH | `/api/v1/companies/{id}` | 编辑公司 | 总部 | FR-001 |
| POST | `/api/v1/companies/{id}/disable` | 停用公司 | 总部 | FR-003 |
| GET | `/api/v1/companies` | 公司列表 | 总部 | FR-001 |
| GET | `/api/v1/org/tree` | 组织树（公司→工位下钻） | 总部 | FR-008 |
| POST | `/api/v1/workstations` | 创建工位 | 总部 / 子公司 | FR-002 |
| PATCH | `/api/v1/workstations/{id}` | 编辑工位（含绑定打印机、绑定操作员） | 总部 / 本子公司 | FR-002 |
| POST | `/api/v1/workstations/{id}/disable` | 停用工位 | 总部 / 本子公司 | FR-003 |
| GET | `/api/v1/workstations` | 工位列表（含在线状态） | 总部 / 本子公司 | FR-002 |
| POST | `/api/v1/users` | 创建账号 | 总部（任意角色）/ 子公司（仅操作员） | FR-004 |
| PATCH | `/api/v1/users/{id}` | 编辑账号 | 同上 | FR-004 |
| POST | `/api/v1/users/{id}/disable` | 停用账号 | 同上 | FR-004 |
| GET | `/api/v1/users` | 账号列表 | 总部 / 本子公司操作员 | FR-004 |

**约束**：`POST/PATCH /users` 由子公司管理员调用时，`role` MUST 为 `operator` 且 `company_id` MUST
等于其自身公司；越界返回 `403 FORBIDDEN_SCOPE`（FR-004）。

---

## 产品

| 方法 | 路径 | 用途 | 角色 | 规格 |
|------|------|------|------|------|
| POST | `/api/v1/products` | 创建产品 | 总部 | FR-009 |
| PATCH | `/api/v1/products/{id}` | 编辑产品 | 总部 | FR-009 |
| POST | `/api/v1/products/{id}/disable` | 停用产品 | 总部 | FR-010 |
| GET | `/api/v1/products` | 产品列表（含累计导入/已分配/已打印量） | 总部 / 子公司 | FR-011 |

**约束**：`disable` 在该产品仍存在 `status='allocated'` 的码时返回
`409 PRODUCT_HAS_ALLOCATED_CODES`（FR-010）。

---

## 码导入

| 方法 | 路径 | 用途 | 角色 | 规格 |
|------|------|------|------|------|
| GET | `/api/v1/imports/template` | 下载标准 Excel 导入模板 | 总部 | FR-012 |
| POST | `/api/v1/imports` | 上传码清单 + 对照关系文件，立即返回批次号 | 总部 | FR-013 / R3 |
| GET | `/api/v1/imports/{batch_id}` | 查询批次状态与进度（`processed_rows`/`total_rows`） | 总部 | FR-018 / R3 |
| GET | `/api/v1/imports/{batch_id}/errors` | 下载失败明细 | 总部 | FR-018 |
| GET | `/api/v1/imports` | 导入批次列表 | 总部 | FR-018 |

**`POST /imports` 请求**：`multipart/form-data`，字段 `code_list_file` 与 `mapping_file`（均为必填）。
**响应 202**：`{ "batch_id": 91, "batch_no": "IMP20261012001", "status": "pending" }`

**约束**
- 上传阶段 MUST NOT 解析文件内容（R3）；两文件缺一返回 `400`。
- 集合不一致的判定发生在后台处理阶段，结果记入批次（`IMPORT_CODE_SET_MISMATCH` 语义），
  前端 MUST 通过批次详情读取，MUST NOT 期望上传请求同步返回该错误。
- 前端 MUST 以 2 秒间隔轮询批次详情直至状态为终态（`succeeded` / `failed` / `interrupted`）。

---

## 码与产品绑定 / 码分配与回收

| 方法 | 路径 | 用途 | 角色 | 规格 |
|------|------|------|------|------|
| POST | `/api/v1/codes/bind` | 按批次批量绑定或换绑产品 | 总部 | FR-022 |
| GET | `/api/v1/codes` | 码池查询（按批次/产品/状态筛选） | 总部 / 子公司 | FR-011 |
| GET | `/api/v1/codes/{code_value}` | 码详情 + 生命周期时间线 | 总部 / 子公司（本公司） | FR-064 |
| POST | `/api/v1/allocations` | 按"公司 + 产品 + 数量"分配码 | 总部 | FR-025 |
| POST | `/api/v1/allocations/{id}/reclaim` | 回收未打印的码 | 总部 | FR-029 |
| GET | `/api/v1/allocations` | 分配单列表 | 总部 / 子公司 | FR-027 |

**`POST /allocations` 请求**

```json
{
  "company_id": 7,
  "product_id": 3,
  "quantity": 5000,
  "template_version_id": null,
  "batch_id": null,
  "code_range": null
}
```

- `template_version_id` 为 `null` 时服务端取产品的默认模板当前版本（FR-035）。
- `batch_id` / `code_range` 非空表示定向分配（FR-026）。
- 可用量不足返回 `409`，并在 `details.available` 给出可分配数量。
- 取码 MUST 使用 `SELECT ... FOR UPDATE SKIP LOCKED`（R2），默认按导入批次先进先出（FR-025）。

**`POST /allocations/{id}/reclaim` 约束**：若该分配单下存在 `status='printed'` 或 `'printing'` 的码，
MUST 拒绝回收整单（FR-030）；仅 `allocated` 的码可回收到码池。

---

## 打印模板

| 方法 | 路径 | 用途 | 角色 | 规格 |
|------|------|------|------|------|
| POST | `/api/v1/templates` | 新建模板（含首个版本） | 总部 | FR-032 |
| PATCH | `/api/v1/templates/{id}` | 编辑模板 → 生成新版本 | 总部 | FR-033 |
| POST | `/api/v1/templates/{id}/disable` | 停用模板 | 总部 | FR-033 |
| GET | `/api/v1/templates` | 模板列表 | 总部 / 子公司（只读） | FR-032 |
| GET | `/api/v1/templates/{id}/versions` | 版本列表 | 总部 / 子公司（只读） | FR-033 |
| PUT | `/api/v1/templates/{id}/versions/{no}` | 修改模板版本内容 | 总部 | FR-033 |

**约束**：修改 `frozen=true` 的版本返回 `409 TEMPLATE_VERSION_FROZEN`（FR-034）。
模板元素定义（`elements_json`）的渲染规则由两端共享（R6），本接口只负责存取。

---

## 补打与作废

| 方法 | 路径 | 用途 | 角色 | 规格 |
|------|------|------|------|------|
| POST | `/api/v1/codes/{code_value}/reprint` | 对已打印的码发起补打 | 总部 / 子公司（本公司） | FR-051 / FR-055 |
| POST | `/api/v1/codes/void` | 批量作废 | 总部 / 子公司（本公司） | FR-057 |
| GET | `/api/v1/reprints` | 补打/作废台账 | 总部 / 子公司（本公司） | FR-067 |

**`POST /codes/{code_value}/reprint` 请求**

```json
{ "reason": "标签破损，重新打印" }
```

- `reason` 为空 → `400 REASON_REQUIRED`（FR-053）。
- 该码非 `printed` → `409 CODE_NOT_PRINTED`（FR-051）。
- 目标工位（`last_printed_workstation_id`）离线或已停用 → `409 WORKSTATION_OFFLINE` /
  `WORKSTATION_DISABLED`，**且码状态 MUST NOT 改变**（FR-056）。
- 成功时创建 `PrintTask`（`task_type='reprint'`），响应返回 `task_id` 与目标工位；
  实际出纸由工位端轮询领取后执行。请求 MUST NOT 要求管理员选择工位（FR-055）。

**`POST /codes/void` 请求**

```json
{ "code_values": ["A001", "A002"], "reason": "整批报废" }
```

- `reason` 为空 → `400 REASON_REQUIRED`（FR-058）。
- 批量中混入他公司码 → 整体拒绝并返回 `403 FORBIDDEN_SCOPE`（不部分成功）。
- 批量中混入已作废码 → 该码按幂等跳过，其余照常作废，响应 `details.skipped` 列出。

---

## 报表与审计

| 方法 | 路径 | 用途 | 角色 | 规格 |
|------|------|------|------|------|
| GET | `/api/v1/dashboard/code-distribution` | 看板：按公司/产品的四态码量分布 | 总部 / 子公司 | FR-065 |
| GET | `/api/v1/reports/prints` | 打印明细（公司/工位/操作员/产品/时间段筛选） | 总部 / 子公司 | FR-066 |
| GET | `/api/v1/reports/prints/export` | 导出打印明细 Excel | 总部 / 子公司 | FR-066 |
| GET | `/api/v1/reports/code-stock/export` | 导出码量看板 Excel | 总部 | FR-031 |
| GET | `/api/v1/audit-logs` | 操作日志查询 | **仅总部** | FR-061 / FR-062 |

**约束**
- 子公司管理员访问报表时，服务端 MUST 强制注入本公司过滤；他公司数据出现次数必须为 0（SC-007）。
- 非总部角色访问 `/audit-logs` → `403 FORBIDDEN_SCOPE`（FR-062）。
- 四态统计 MUST 由数据库聚合完成（索引见 data-model），MUST NOT 应用层拉全量计数（SC-013）。
