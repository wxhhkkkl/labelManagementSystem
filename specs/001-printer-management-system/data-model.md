# Phase 1 数据模型：打印管理系统

**功能**：[spec.md](./spec.md) | **日期**：2026-10-12 | **数据库**：MySQL 8.0+ / InnoDB / utf8mb4

字段按"存储需求"描述，不含具体 ORM 声明。所有表含 `id`（主键）与 `created_at` / `updated_at`（UTC `DATETIME`）。

---

## 实体关系概览

```text
Company 1──n Workstation 1──n PrintTask
   │              │  n──n User (WorkstationOperator)
   │              └──────────────┐
   │                             │
   └──n User                     │
   └──n Code ──n Product         │
          │                      │
          ├──1 ImportBatch       │
          ├──? AllocationOrder ──┘
          ├──n CodeEvent
          └──n PrintLog ─────────┘

Template 1──n TemplateVersion 1──n AllocationOrder
                               1──n PrintTask
AuditLog（独立，append-only）
```

---

## 1. Company（公司）

| 字段 | 类型 | 约束 |
|------|------|------|
| code | VARCHAR(32) | NOT NULL, UNIQUE |
| name | VARCHAR(128) | NOT NULL |
| contact | VARCHAR(64) | NULL |
| region | VARCHAR(64) | NULL |
| status | ENUM('active','disabled') | NOT NULL, 默认 'active' |

**规则**：停用即 `status='disabled'`（FR-003）。停用 MUST NOT 物理删除，历史数据引用 MUST 保留。
**注**：总部是隐式节点，不占 Company 记录；总部管理员以 `company_id IS NULL` 表示。

## 2. Workstation（工位）

| 字段 | 类型 | 约束 |
|------|------|------|
| code | VARCHAR(32) | NOT NULL，与 company_id 组合 UNIQUE |
| name | VARCHAR(128) | NOT NULL |
| company_id | FK → Company | NOT NULL |
| printer_name | VARCHAR(255) | NULL，绑定的默认打印机（FR-070） |
| status | ENUM('active','disabled') | NOT NULL，默认 'active' |
| bound_at | DATETIME | NULL，工位软件首次绑定本工位的时间（FR-069） |
| last_heartbeat_at | DATETIME | NULL，最后一次心跳时间 |

**规则**：`last_heartbeat_at` 超过 30 秒即判定离线（R1），用于 FR-056 的补打前置校验。该判定 MUST 由服务端计算，MUST NOT 信任客户端自报的在线状态。

## 3. User（用户）

| 字段 | 类型 | 约束 |
|------|------|------|
| username | VARCHAR(64) | NOT NULL, UNIQUE |
| display_name | VARCHAR(64) | NOT NULL |
| password_hash | VARCHAR(255) | NOT NULL |
| role | ENUM('hq_admin','sub_admin','operator') | NOT NULL |
| company_id | FK → Company | NULL（仅 hq_admin 可为 NULL） |
| status | ENUM('active','disabled') | NOT NULL，默认 'active' |

**规则**：
- `role='sub_admin'` 时 `company_id` MUST NOT 为 NULL。
- 账号停用 MUST 在每次请求时实时校验（R4），不能仅依赖令牌过期。

## 4. WorkstationOperator（工位—操作员绑定）

| 字段 | 类型 | 约束 |
|------|------|------|
| workstation_id | FK → Workstation | NOT NULL |
| user_id | FK → User | NOT NULL |

UNIQUE(workstation_id, user_id)。对应 FR-005。一个工位可绑多名操作员，一名操作员可绑多个工位（spec 假设）。

## 5. Product（产品）

| 字段 | 类型 | 约束 |
|------|------|------|
| code | VARCHAR(64) | NOT NULL, UNIQUE（全局唯一，产品由总部统一管理） |
| name | VARCHAR(128) | NOT NULL |
| spec | VARCHAR(255) | NULL |
| default_template_id | FK → Template | NULL |
| status | ENUM('active','disabled') | NOT NULL，默认 'active' |

**规则**：停用前置校验（FR-010）——存在该产品下 `status='allocated'` 的码时，停用操作 MUST 被拒绝。

## 6. Template（打印模板）与 TemplateVersion（模板版本）

**Template**

| 字段 | 类型 | 约束 |
|------|------|------|
| code | VARCHAR(64) | NOT NULL, UNIQUE |
| name | VARCHAR(128) | NOT NULL |
| status | ENUM('active','disabled') | NOT NULL，默认 'active' |

**TemplateVersion**

| 字段 | 类型 | 约束 |
|------|------|------|
| template_id | FK → Template | NOT NULL |
| version_no | INT | NOT NULL，与 template_id 组合 UNIQUE |
| paper_width_mm | DECIMAL(6,2) | NOT NULL |
| paper_height_mm | DECIMAL(6,2) | NOT NULL |
| elements_json | JSON | NOT NULL，元素数组（类型/坐标/尺寸/字体/字号/动态字段名） |
| frozen | BOOLEAN | NOT NULL，默认 false |

**规则**：
- 修改模板 MUST 新建一条 TemplateVersion 并递增 `version_no`，MUST NOT 修改既有版本行（FR-033）。
- 被 AllocationOrder 或 PrintTask 引用时置 `frozen=true`（FR-034）。
- 模板停用（`Template.status`）只影响新分配；已冻结的版本继续可用于打印与补打（spec 假设）。
- 动态字段约定：`product_name`、`company_name`、`code_value` 由系统填充；`batch_no` 取该码所在分配单的 `order_no`（FR-037）。

## 7. ImportBatch（导入批次）

| 字段 | 类型 | 约束 |
|------|------|------|
| batch_no | VARCHAR(32) | NOT NULL, UNIQUE |
| code_list_filename | VARCHAR(255) | NOT NULL |
| mapping_filename | VARCHAR(255) | NOT NULL |
| status | ENUM('pending','processing','succeeded','failed','interrupted') | NOT NULL |
| total_rows | INT | NULL |
| processed_rows | INT | NOT NULL，默认 0（异步进度，R3） |
| success_count | INT | NOT NULL，默认 0 |
| failure_count | INT | NOT NULL，默认 0 |
| error_detail_path | VARCHAR(512) | NULL，失败明细文件路径（FR-018） |
| created_by | FK → User | NOT NULL |
| started_at / finished_at | DATETIME | NULL |

**规则**：服务端重启后 `status='processing'` 的记录 MUST 被置为 `interrupted`（R3），不支持断点续传。

## 8. Code（码）—— 核心实体

| 字段 | 类型 | 约束 |
|------|------|------|
| code_value | VARCHAR(100) | NOT NULL, UNIQUE（FR-015） |
| status | ENUM('unallocated','allocated','printing','printed','voided') | NOT NULL，默认 'unallocated' |
| product_id | FK → Product | NOT NULL（导入时经对照关系绑定，FR-019） |
| company_id | FK → Company | NULL，仅 `allocated` 及之后非空 |
| import_batch_id | FK → ImportBatch | NOT NULL |
| current_allocation_order_id | FK → AllocationOrder | NULL |
| locked_at | DATETIME | NULL，进入 `printing` 的时间（FR-047 超时判定） |
| locked_workstation_id | FK → Workstation | NULL |
| last_printed_workstation_id | FK → Workstation | NULL，补打派发目标（FR-055） |
| print_count | INT | NOT NULL，默认 0 |
| reprint_count | INT | NOT NULL，默认 0（FR-054） |
| voided_at / voided_by / void_reason | DATETIME / FK → User / VARCHAR(255) | NULL（FR-058） |

**唯一性规则**：`code_value` 全库唯一，**已作废的码仍占用该约束**——同一码值不可重新导入（spec 假设）。

**状态机（FR-077 / FR-078，唯一合法流转）**

| 当前状态 | 动作 | 目标状态 | 执行角色 | 附加约束 |
|----------|------|----------|----------|----------|
| unallocated | 分配 | allocated | 总部管理员 | 写 company_id、current_allocation_order_id |
| allocated | 打印（预占） | printing | 工位操作员 | 同事务内串行化，写 locked_at |
| printing | 确认成功 | printed | 系统/操作员 | print_count+1，写 last_printed_workstation_id |
| printing | 标记失败 | allocated | 工位操作员 | 清 locked_* |
| printing | 超时未确认 | allocated | 系统 | 阈值可配置，默认 5 分钟；清 locked_*；不计补打 |
| printed | 补打 | printed | 总部/子公司管理员 | reprint_count+1；不改变产品与归属 |
| unallocated / allocated / printed | 作废 | voided | 总部/子公司管理员 | 必填原因 |
| allocated | 回收 | unallocated | 总部管理员 | 清 company_id、current_allocation_order_id |

任何未列出的流转 MUST 被拒绝（FR-078）。`voided` 为终态，MUST NOT 流转到任何状态（FR-059）。

## 9. AllocationOrder（分配单）

| 字段 | 类型 | 约束 |
|------|------|------|
| order_no | VARCHAR(32) | NOT NULL, UNIQUE |
| company_id | FK → Company | NOT NULL |
| product_id | FK → Product | NOT NULL |
| code_count | INT | NOT NULL |
| code_range_from / code_range_to | VARCHAR(100) | NULL，码段范围展示用 |
| template_version_id | FK → TemplateVersion | NOT NULL（FR-035） |
| allocated_by | FK → User | NOT NULL |
| allocated_at | DATETIME | NOT NULL |
| status | ENUM('active','reclaimed') | NOT NULL，默认 'active' |

**规则**：分配时 MUST 指定 `template_version_id`，未显式指定则取产品的 `default_template_id` 的当前版本（FR-035）。

## 10. PrintTask（打印任务 / 补打下发）

| 字段 | 类型 | 约束 |
|------|------|------|
| task_type | ENUM('reprint') | NOT NULL |
| code_id | FK → Code | NOT NULL |
| target_workstation_id | FK → Workstation | NOT NULL（= 该码 `last_printed_workstation_id`） |
| template_version_id | FK → TemplateVersion | NOT NULL |
| reason | VARCHAR(255) | NOT NULL（FR-053） |
| created_by | FK → User | NOT NULL |
| status | ENUM('pending','claimed','succeeded','failed','expired') | NOT NULL，默认 'pending' |
| claimed_at | DATETIME | NULL |
| finished_at | DATETIME | NULL |
| failure_reason | VARCHAR(255) | NULL |

**规则（R1 轮询模型）**：
- 工位端每 5 秒轮询 `pending` 任务；领取使用原子更新 `UPDATE ... WHERE status='pending' AND target_workstation_id=?`，避免重复领取。
- 任务创建时 MUST 校验目标工位心跳未超时，否则按 FR-056 拒绝创建（补打请求返回失败）。
- 任务仅在创建时校验离线；创建后目标工位掉线，任务保留在 `pending`，待其恢复后继续执行。
- **`pending` 状态只在服务端存在任务时才有意义；无任务时不产生任何写入**（避免 5 秒轮询把数据库打满）。

## 11. PrintLog（打印记录）

| 字段 | 类型 | 约束 |
|------|------|------|
| code_id | FK → Code | NOT NULL |
| code_value | VARCHAR(100) | NOT NULL（快照，便于码表变更后仍可追溯） |
| product_id | FK → Product | NOT NULL |
| company_id | FK → Company | NOT NULL |
| workstation_id | FK → Workstation | NOT NULL |
| operator_id | FK → User | NOT NULL |
| printer_name | VARCHAR(255) | NOT NULL |
| template_version_id | FK → TemplateVersion | NOT NULL |
| print_type | ENUM('first','reprint') | NOT NULL |
| result | ENUM('succeeded','failed','timeout_reverted') | NOT NULL |
| failure_reason | VARCHAR(255) | NULL |
| printed_at | DATETIME | NOT NULL |

**规则**：每一次打印动作（正常打印、补打、标记失败、超时回退）MUST 生成一条记录（FR-050）。记录 MUST NOT 被更新或删除。
**注**：`succeeded` 专指成功提交到打印机并收到确认；`failed` 含操作员主动标记失败与打印服务报错。

## 12. CodeEvent（码生命周期事件）

| 字段 | 类型 | 约束 |
|------|------|------|
| code_id | FK → Code | NOT NULL |
| event_type | ENUM('imported','bound','allocated','reclaimed','print_started','printed','print_failed','reprint','voided','timeout_reverted') | NOT NULL |
| from_status / to_status | VARCHAR(20) | NULL |
| operator_id | FK → User | NULL（系统动作为 NULL） |
| workstation_id | FK → Workstation | NULL |
| reason | VARCHAR(255) | NULL |
| occurred_at | DATETIME | NOT NULL |

**存在理由**：FR-064 要求按码值展示完整时间线（导入→绑定→分配→打印→补打/作废）。不能复用 AuditLog，因为 AuditLog 的可见范围是"仅总部管理员"（FR-062），而码的时间线需要按数据归属可见——两者访问规则不同，混用会导致越权或该看的人看不到。

## 13. AuditLog（操作日志）

| 字段 | 类型 | 约束 |
|------|------|------|
| operator_id | FK → User | NOT NULL |
| role | VARCHAR(20) | NOT NULL（快照，角色变更后仍可追溯） |
| company_id | FK → Company | NULL |
| workstation_id | FK → Workstation | NULL |
| action | VARCHAR(64) | NOT NULL |
| target_type / target_id | VARCHAR(64) / BIGINT | NULL |
| ip | VARCHAR(64) | NULL |
| result | ENUM('success','denied','failed') | NOT NULL |
| occurred_at | DATETIME | NOT NULL |

**规则**：append-only，MUST NOT 提供更新与删除入口（FR-060）。保留期 ≥ 2 年（FR-063）。
**注**：越权请求 MUST 以 `result='denied'` 记录（FR-007）。

---

## 索引设计（对应 SC-013：百万级码库下列表查询 3 秒内返回）

| 表 | 索引 | 服务的查询 |
|----|------|-----------|
| Code | UNIQUE(code_value) | 扫码定位、码详情（FR-040） |
| Code | (company_id, product_id, status) | 工位端"按产品查本公司已分配未打印"（FR-039） |
| Code | (status, import_batch_id) | 码池取码与批次查询（FR-025） |
| Code | (current_allocation_order_id) | 分配单详情 |
| Code | (company_id, product_id, status) 覆盖看板四态统计 | 看板与报表（FR-065） |
| PrintLog | (company_id, printed_at) | 打印明细按公司+时间段（FR-066） |
| PrintLog | (workstation_id, printed_at) | 按工位筛选 |
| PrintLog | (operator_id, printed_at) | 按操作员筛选 |
| PrintTask | (target_workstation_id, status) | 轮询领取（R1），必须高效 |
| CodeEvent | (code_id, occurred_at) | 码时间线（FR-064） |
| AuditLog | (occurred_at) | 日志按时间查询（FR-061） |
| Workstation | (last_heartbeat_at) | 离线判定扫描 |

**约束**：看板四态统计 MUST 走索引聚合，MUST NOT 在应用层拉全量再计数（百万级下必然超过 SC-013）。

---

## 由规格映射到模型的校验要点

| 规格条目 | 模型落点 |
|----------|----------|
| FR-014 两文件码集合一致 | ImportBatch 处理中先校验集合，不一致即整批失败，不写 Code |
| FR-017 码值全库唯一 | Code.code_value UNIQUE；重复时按策略整批拒绝 |
| FR-023 一码一产品 | Code.product_id 单值外键 |
| FR-033/034 模板版本冻结 | TemplateVersion.frozen |
| FR-044 并发抢码 | Code 行锁 + 状态机事务 |
| FR-047 打印中超时回退 | Code.locked_at + 可配置阈值 |
| FR-055/056 补打派发与离线拒绝 | PrintTask.target_workstation_id + Workstation.last_heartbeat_at |
| FR-006/007 组织隔离 | 所有含 company_id 的表在服务端查询层强制过滤 |
