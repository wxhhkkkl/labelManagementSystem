---

description: "打印管理系统实施任务清单"
---

# 任务清单：打印管理系统

**输入**：设计文档来自 `/specs/001-printer-management-system/`

**前置文档**：plan.md（必需）· spec.md（必需）· research.md · data-model.md · contracts/

**测试**：**本清单包含测试任务，且测试 MUST 排在其对应实现之前**。依据是项目宪章原则一
（测试优先，NON-NEGOTIABLE）：测试先写、先运行至失败，再写实现。每个实现任务的"完成"以
其测试通过为准。

**组织方式**：按用户故事分阶段，每个故事可独立实现、独立测试、独立交付。

## 格式：`[ID] [P?] [Story] 描述`

- **[P]**：可并行执行（不同文件、无未完成依赖）
- **[Story]**：所属用户故事（US1~US9）；Setup 与 Foundational 阶段不标
- 每个任务都给出确切文件路径

## 路径约定

- 后台：`backend/app/`、`backend/tests/`
- 管理后台：`admin-web/src/`、`admin-web/tests/`
- 工位软件：`print-client/src/`、`print-client/tests/`

> **开工前须知的两处已知事项**
>
> 1. **产品管理已并入 US2**。规格 FR-009 ~ FR-011（产品 CRUD、停用前置校验、产品列表统计）
>    原无用户故事承载，现已通过扩写 US2 解决——US2 更名为"产品管理与码导入"并补充了
>    产品管理的验收场景。产品与码绑定属同一条数据链的上下游，合为一个故事不影响独立性。
> 2. **US4 对模板有数据层依赖**。US4（打印）需要"分配单携带的模板版本"才能渲染，
>    因此 Template/TemplateVersion 的**模型与冻结逻辑**在 Foundational 阶段完成；
>    US6 只负责模板的**完整管理与可视化编辑器**。这使得 US4 可独立测试而不必等 US6。

---

## Phase 1: Setup（共享基础设施）

**目的**：初始化三个交付单元与开发环境

- [X] T001 创建仓库三目录骨架 `backend/`、`admin-web/`、`print-client/`，各自独立的 `package.json` / `pyproject.toml`，三者 MUST NOT 交叉引用（宪章原则六）
- [X] T002 初始化后台项目：`backend/pyproject.toml` 声明 FastAPI、SQLAlchemy 2.x、Alembic、PyMySQL、Pydantic v2、openpyxl、PyJWT、python-multipart，及 dev 依赖 pytest/httpx/ruff
- [X] T003 [P] 初始化管理后台项目：`admin-web/package.json` 使用 Vue 3 + Vite + TypeScript + Pinia + Vue Router + Element Plus + `vue-draggable-plus`
- [X] T004 [P] 初始化工位软件项目：`print-client/package.json` 使用 Electron + Vue 3 + TypeScript；`print-client/src/print-service/` 作为独立常驻进程入口
- [X] T005 [P] 配置格式与静态检查：`backend/ruff.toml`、`admin-web/.eslintrc.cjs` + `.prettierrc`、`print-client/.eslintrc.cjs`
- [X] T006 [P] 配置后台测试框架 `backend/pytest.ini`，并在 `backend/tests/conftest.py` 提供真实 MySQL 连接夹具（MUST NOT 用 SQLite 替代，并发语义不同，见 research R2）
- [X] T007 [P] 配置前端测试 `admin-web/vitest.config.ts` 与 `admin-web/tests/e2e/` 的 Playwright 配置
- [X] T008 编写 `docker-compose.yml` 提供本地 MySQL 8.0.1+（utf8mb4/InnoDB），供开发与集成测试使用
- [X] T009 初始化 Alembic：`backend/migrations/`，配置 `alembic.ini` 读取 `DATABASE_URL` 环境变量

**检查点**：三个项目可分别启动空跑，测试命令可执行且报 0 用例通过

---

## Phase 2: Foundational（阻塞性前置）

**目的**：所有用户故事都依赖的核心模型与基础设施

**⚠️ 关键**：本阶段完成前，任何用户故事都不得开始

### 数据模型（对应 data-model.md 的 14 张表）

- [X] T010 [P] 创建 Company 模型 `backend/app/models/company.py`：`code` VARCHAR(32) NOT NULL UNIQUE、`name` VARCHAR(128) NOT NULL、`contact` VARCHAR(64) NULL、`region` VARCHAR(64) NULL、`status` ENUM('active','disabled') NOT NULL 默认 'active'
- [X] T011 [P] 创建 Workstation 与 WorkstationOperator 模型 `backend/app/models/workstation.py`：Workstation 含 `code` VARCHAR(32)（与 company_id 组合 UNIQUE）、`name` VARCHAR(128) NOT NULL、`company_id` FK NOT NULL、`printer_name` VARCHAR(255) NULL、`status` ENUM('active','disabled')、`bound_at` DATETIME NULL、`last_heartbeat_at` DATETIME NULL；WorkstationOperator 含 (workstation_id, user_id) UNIQUE
- [X] T012 [P] 创建 User 模型 `backend/app/models/user.py`：`username` VARCHAR(64) NOT NULL UNIQUE、`display_name` VARCHAR(64) NOT NULL、`password_hash` VARCHAR(255) NOT NULL、`role` ENUM('hq_admin','sub_admin','operator') NOT NULL、`company_id` FK NULL（仅 hq_admin 可为 NULL）、`status` ENUM('active','disabled')
- [X] T013 [P] 创建 Product 模型 `backend/app/models/product.py`：`code` VARCHAR(64) NOT NULL UNIQUE、`name` VARCHAR(128) NOT NULL、`spec` VARCHAR(255) NULL、`default_template_id` FK NULL、`status` ENUM('active','disabled')
- [X] T014 [P] 创建 Template 与 TemplateVersion 模型 `backend/app/models/template.py`：Template 含 `code` UNIQUE、`name`、`status`；TemplateVersion 含 `template_id` FK、(template_id, version_no) UNIQUE、`paper_width_mm`/`paper_height_mm` DECIMAL(6,2) NOT NULL、`elements_json` JSON NOT NULL、`frozen` BOOLEAN NOT NULL 默认 false
- [X] T015 [P] 创建 ImportBatch 模型 `backend/app/models/import_batch.py`：`batch_no` UNIQUE、`code_list_filename`、`mapping_filename`、`status` ENUM('pending','processing','succeeded','failed','interrupted')、`total_rows` NULL、`processed_rows` 默认 0、`success_count` 默认 0、`failure_count` 默认 0、`error_detail_path` VARCHAR(512) NULL、`created_by` FK、`started_at`/`finished_at` NULL
- [X] T016 [P] 创建 AllocationOrder 模型 `backend/app/models/allocation_order.py`：`order_no` UNIQUE、`company_id` FK、`product_id` FK、`code_count` INT、`code_range_from`/`code_range_to` VARCHAR(100) NULL、`template_version_id` FK NOT NULL、`allocated_by` FK、`allocated_at` DATETIME、`status` ENUM('active','reclaimed')
- [X] T017 创建 Code 模型 `backend/app/models/code.py`（核心实体）：`code_value` VARCHAR(100) NOT NULL UNIQUE、`status` ENUM('unallocated','allocated','printing','printed','voided') NOT NULL 默认 'unallocated'、`product_id` FK NOT NULL、`company_id` FK NULL、`import_batch_id` FK NOT NULL、`current_allocation_order_id` FK NULL、`locked_at` DATETIME NULL、`locked_workstation_id` FK NULL、`last_printed_workstation_id` FK NULL、`print_count` INT 默认 0、`reprint_count` INT 默认 0、`voided_at`/`voided_by`/`void_reason` NULL
- [X] T018 [P] 创建 PrintTask 模型 `backend/app/models/print_task.py`：`task_type` ENUM('reprint')、`code_id` FK、`target_workstation_id` FK、`template_version_id` FK、`reason` VARCHAR(255) NOT NULL、`created_by` FK、`status` ENUM('pending','claimed','succeeded','failed','expired')、`claimed_at`/`finished_at`/`failure_reason` NULL
- [X] T019 [P] 创建 PrintLog 模型 `backend/app/models/print_log.py`：`code_id` FK、`code_value` VARCHAR(100) NOT NULL（快照）、`product_id` FK、`company_id` FK、`workstation_id` FK、`operator_id` FK、`printer_name` VARCHAR(255)、`template_version_id` FK、`print_type` ENUM('first','reprint')、`result` ENUM('succeeded','failed','timeout_reverted')、`failure_reason` NULL、`printed_at` DATETIME
- [X] T020 [P] 创建 CodeEvent 模型 `backend/app/models/code_event.py`：`code_id` FK、`event_type` ENUM('imported','bound','allocated','reclaimed','print_started','printed','print_failed','reprint','voided','timeout_reverted')、`from_status`/`to_status` VARCHAR(20) NULL、`operator_id` FK NULL、`workstation_id` FK NULL、`reason` VARCHAR(255) NULL、`occurred_at` DATETIME
- [X] T021 [P] 创建 AuditLog 模型 `backend/app/models/audit_log.py`：`operator_id` FK、`role` VARCHAR(20) NOT NULL（角色快照）、`company_id` NULL、`workstation_id` NULL、`action` VARCHAR(64)、`target_type`/`target_id`、`ip` VARCHAR(64)、`result` ENUM('success','denied','failed')、`occurred_at` DATETIME
- [X] T022 生成初始 Alembic 迁移 `backend/migrations/versions/0001_initial.py`，含 data-model.md 索引设计表中的全部索引：Code UNIQUE(code_value)、(company_id, product_id, status)、(status, import_batch_id)、(current_allocation_order_id)；PrintLog (company_id, printed_at)、(workstation_id, printed_at)、(operator_id, printed_at)；PrintTask (target_workstation_id, status)；CodeEvent (code_id, occurred_at)；AuditLog (occurred_at)；Workstation (last_heartbeat_at)

### 认证与授权

- [X] T023 [P] 单元测试：JWT 签发与校验（含过期、篡改、角色载荷）`backend/tests/unit/test_security.py` —— 先写并运行至失败
- [X] T024 实现 JWT 与密码哈希 `backend/app/core/security.py`：访问令牌 2 小时、刷新令牌 7 天，载荷含 `user_id`/`role`/`company_id`/`workstation_id`（research R4）
- [X] T025 [P] 契约测试：认证四接口 `backend/tests/contract/test_auth_api.py` —— 覆盖 login/refresh/me/logout 的正常结构与 `INVALID_CREDENTIALS`、`ACCOUNT_DISABLED` —— 先写并运行至失败
- [X] T026 实现认证接口 `backend/app/api/v1/auth.py`，契约见 `contracts/auth-api.md`：登录成功与失败均写 AuditLog
- [X] T027 实现认证依赖 `backend/app/core/deps.py`：解析 Bearer 令牌，并**每次请求实时校验 `User.status`**（MUST NOT 仅依赖令牌过期，research R4）

### 组织隔离（安全属性，收敛到一处）

- [X] T028 [P] 集成测试：越权用例 `backend/tests/integration/test_org_isolation.py` —— 子公司令牌访问他公司的码/记录/报表/补打/作废一律 `403 FORBIDDEN_SCOPE`，且每次拒绝写 `AuditLog(result='denied')`；断言他公司数据出现次数为 0（SC-007）—— 先写并运行至失败
- [X] T029 实现组织隔离依赖 `backend/app/core/scope.py`：按 `role`+`company_id` 注入强制过滤条件；**不接受客户端传入的 `company_id` 作为查询依据**；提供单对象归属校验函数（research R7）

### 横切基础设施

- [X] T030 [P] 定义统一错误码常量与异常映射 `backend/app/core/errors.py`，覆盖 `contracts/README.md` 的关键错误码表全部条目
- [X] T031 [P] 单元测试：统一错误响应格式与分页序列化 `backend/tests/unit/test_errors.py` —— 先写并运行至失败
- [X] T032 [P] 实现审计日志写入服务 `backend/app/services/audit.py`，提供 append-only 接口并**不暴露更新与删除方法**（FR-060）

### 码状态机（US3/US4/US5 共用）

- [X] T033 单元测试：码状态机全部合法与非法流转 `backend/tests/unit/test_code_state_machine.py` —— 逐条覆盖 FR-077 的八条合法流转与 FR-078 的非法流转拒绝，并断言 `voided` 为终态（FR-059）—— 先写并运行至失败
- [X] T034 实现码状态机 `backend/app/services/code_state.py`：集中定义合法流转表与守卫条件（如作废必填原因、回收仅限 `allocated`）

**检查点**：数据库可迁移建表；认证与隔离已验证；状态机单测全绿。用户故事可并行开始。

---

## Phase 3: US1 - 组织、工位与账号管理（优先级：P1）🎯 MVP

**目标**：总部建立分子公司与工位、创建账号并分配角色；子公司管理员可就地维护本公司工位与操作员账号

**独立测试**：建立两级公司及工位，创建三类角色账号并绑定工位；以子公司管理员登录可建本公司工位与操作员，但编辑他公司工位或创建管理员账号被拒绝；停用公司/工位后不可再分配或打印，历史数据仍可查

### 测试（先写，运行至失败）

- [X] T035 [P] [US1] 契约测试：组织与账号接口 `backend/tests/contract/test_org_api.py` —— 覆盖 `contracts/admin-api.md` 中组织与账号小节的全部端点，含子公司管理员越界返回 `FORBIDDEN_SCOPE` —— 先写并运行至失败
- [X] T036 [P] [US1] 集成测试：停用连带效应 `backend/tests/integration/test_disable_effects.py` —— 停用公司/工位后不可被分配新码、不可执行打印，历史记录仍可查（FR-003）—— 先写并运行至失败
- [X] T037 [P] [US1] 前端单元测试：组织树与账号表单校验 `admin-web/tests/unit/org.spec.ts` —— 先写并运行至失败
- [X] T038 [P] [US1] 契约测试：工位软件绑定工位 `backend/tests/contract/test_workstation_bind_api.py` —— `POST /api/v1/workstation/bind` 绑定成功并写入 `Workstation.bound_at`；绑定他公司工位返回 `FORBIDDEN_SCOPE`；工位或所属公司停用返回 `WORKSTATION_DISABLED`（FR-069）—— 先写并运行至失败

### 实现

- [X] T039 [P] [US1] 实现公司服务与接口 `backend/app/services/company.py` + `backend/app/api/v1/companies.py`：创建/编辑/停用/列表（FR-001、FR-003）
- [X] T040 [US1] 实现工位服务与接口 `backend/app/services/workstation.py` + `backend/app/api/v1/workstations.py`：总部可管任意公司工位、子公司仅限本公司（FR-002）；工位信息含绑定打印机与绑定操作员
- [X] T041 [US1] 实现账号服务与接口 `backend/app/services/user.py` + `backend/app/api/v1/users.py`：总部可管任意角色，子公司仅可管本公司操作员账号且不得创建 `sub_admin`/`hq_admin`（FR-004）
- [X] T042 [US1] 实现组织树接口 `backend/app/api/v1/org.py` `GET /api/v1/org/tree`，支持按公司汇总下钻查看工位（FR-008）
- [X] T043 [P] [US1] 管理后台：组织与工位管理页 `admin-web/src/views/org/OrgTreeView.vue` + `WorkstationListView.vue`
- [X] T044 [P] [US1] 管理后台：账号管理页 `admin-web/src/views/org/UserListView.vue`
- [X] T045 [P] [US1] 管理后台：契约客户端 `admin-web/src/api/org.ts`
- [X] T046 [US1] 工位软件：工位绑定页 `print-client/src/renderer/views/BindWorkstationView.vue`，调用 `POST /api/v1/workstation/bind`，将绑定结果持久化到本机（FR-069）

**检查点**：US1 可独立演示——组织、工位、账号全部可管理，越界被拒绝

---

## Phase 4: US2 - 产品管理与码导入（优先级：P1）

**目标**：总部维护产品（含默认打印模板与停用前置校验），下载标准模板，同时上传码清单与"码—产品"对照关系，成对校验后码绑定产品进入码池

**独立测试**：可创建产品并设默认模板；存在"已分配未打印"码的产品无法停用；上传两文件后校验通过的码带产品绑定进入码池且状态为 `unallocated`；码集合不一致时整批拒绝并输出差异明细；失败明细可下载；批次记录含进度

### 测试（先写，运行至失败）

- [X] T047 [P] [US2] 单元测试：码值校验规则 `backend/tests/unit/test_code_validation.py` —— 100 位以内、仅数字与字母、边界值（1 位/100 位/超长/含符号/带空格/大小写）（FR-015）—— 先写并运行至失败
- [X] T048 [P] [US2] 集成测试：成对校验与整批拒绝 `backend/tests/integration/test_import_pairing.py` —— 两文件码集合不一致时整批拒绝且不写 Code；库中已有重复码时默认整批拒绝（FR-014、FR-017）—— 先写并运行至失败
- [X] T049 [P] [US2] 集成测试：产品停用前置校验 `backend/tests/integration/test_product_disable.py` —— 存在 `status='allocated'` 的码时停用返回 `PRODUCT_HAS_ALLOCATED_CODES`；无在途码时停用成功（FR-010）—— 先写并运行至失败
- [X] T050 [P] [US2] 性能测试：10 万行导入 `backend/tests/integration/test_import_scale.py` —— 验证异步完成并输出成功/失败数（SC-003）—— 先写并运行至失败
- [X] T051 [P] [US2] 契约测试：产品与导入接口 `backend/tests/contract/test_import_api.py` —— 先写并运行至失败
- [X] T052 [P] [US2] 前端单元测试：导入页进度与失败明细展示 `admin-web/tests/unit/import.spec.ts` —— 先写并运行至失败
- [X] T053 [P] [US2] 集成测试：换绑限制与一码一产品 `backend/tests/integration/test_code_binding.py` —— 已分配的码换绑产品被拒；已打印的码任何绑定变更被拒；按批次批量绑定时每个码只归属于一个产品（FR-022、FR-023、FR-024）—— 先写并运行至失败

### 实现

- [X] T054 [P] [US2] 实现产品服务与接口 `backend/app/services/product.py` + `backend/app/api/v1/products.py`：CRUD、停用前置校验、列表含累计导入/已分配/已打印量（FR-009、FR-010、FR-011）
- [X] T055 [US2] 实现导入上传接口 `backend/app/api/v1/imports.py` `POST /api/v1/imports`：仅落盘与批次登记后立即返回 `batch_id`，**MUST NOT 在请求内解析文件**（research R3）
- [X] T056 [US2] 实现流式 Excel 解析 `backend/app/services/import_parser.py`：使用 openpyxl `read_only=True`，MUST NOT 全量 `load_workbook`
- [X] T057 [US2] 实现导入校验流水线 `backend/app/services/import_validator.py`：先校验两文件码集合一致（FR-014）→ 逐行格式与长度（FR-015）→ 库内唯一性（FR-017），错误类型须覆盖格式错误/长度超限/码值重复/两文件码集合不一致/产品编码不存在（FR-021）
- [X] T058 [US2] 实现导入后台 worker `backend/app/tasks/import_worker.py`：进程内单工作线程消费；每 1000 行 `executemany` 批量入库；持续更新 `processed_rows`（research R3）
- [X] T059 [US2] 实现服务启动时的中断恢复 `backend/app/main.py` 启动钩子：将残留 `status='processing'` 的批次置为 `interrupted`（research R3，不支持断点续传）
- [X] T060 [US2] 实现失败明细输出与下载 `backend/app/services/import_errors.py` + `GET /api/v1/imports/{batch_id}/errors`（FR-018）
- [X] T061 [US2] 实现批次查询接口 `GET /api/v1/imports/{batch_id}` 与列表，返回进度字段 `processed_rows`/`total_rows`
- [X] T062 [US2] 实现导入模板下载 `GET /api/v1/imports/template`，生成含"码值"列与"码值、产品编码"列的标准 Excel（FR-012）
- [X] T063 [US2] 实现码—产品绑定服务 `backend/app/services/code_binding.py`：导入时按对照关系绑定；支持按批次批量绑定与换绑；已分配不可换绑、已打印不可变更（FR-022、FR-023、FR-024）
- [X] T064 [P] [US2] 管理后台：产品管理页 `admin-web/src/views/product/ProductListView.vue`
- [X] T065 [P] [US2] 管理后台：码导入页 `admin-web/src/views/import/ImportView.vue`，以 2 秒间隔轮询批次进度直至终态（research R3）

**检查点**：US2 可独立演示——导入 10 万行码并完成产品绑定；产品可管理且停用受前置校验约束

---

## Phase 5: US3 - 码分配与回收（优先级：P1）

**目标**：总部按"公司 + 产品"分配码并携带模板版本；未打印的码可回收回码池

**独立测试**：选择公司、产品、数量后生成分配单，该公司"已分配未打印"码量相应增加；回收未打印码后其回到码池且状态回 `unallocated`；已打印的码无法回收

### 测试（先写，运行至失败）

- [X] T066 [P] [US3] 集成测试：分配单生成与模板携带 `backend/tests/integration/test_allocation_order.py` —— 分配单含单号、公司、产品、码数量、码段范围、模板版本、分配人、时间（FR-027）；未指定模板版本时取产品默认模板的当前版本（FR-035）；可用量不足返回 `409` 且 `details.available` 给出可分配数量 —— 先写并运行至失败
- [X] T067 [P] [US3] 集成测试：并发分配抢码 `backend/tests/integration/test_allocation_concurrency.py` —— 两个并发请求争抢同批码时各取各的、无重复无死锁（`SKIP LOCKED`，research R2）—— 先写并运行至失败
- [X] T068 [P] [US3] 集成测试：回收规则 `backend/tests/integration/test_reclaim.py` —— 分配单内含 `printed`/`printing` 的码时整单回收被拒（FR-030）；仅 `allocated` 的码回收到 `unallocated` 并清空 `company_id`—— 先写并运行至失败
- [X] T069 [P] [US3] 集成测试：先进先出取码 `backend/tests/integration/test_allocation_fifo.py` —— 默认按导入批次先进先出（FR-025）；定向选择批次或码段时按其范围取码（FR-026）—— 先写并运行至失败
- [X] T070 [P] [US3] 契约测试：分配与回收接口 `backend/tests/contract/test_allocation_api.py` —— 先写并运行至失败
- [X] T071 [P] [US3] 前端单元测试：分配表单可用量校验 `admin-web/tests/unit/allocation.spec.ts` —— 先写并运行至失败

### 实现

- [X] T072 [US3] 实现分配取码服务 `backend/app/services/allocation.py`：事务内 `SELECT ... FOR UPDATE SKIP LOCKED` 取码，默认按 `import_batch_id` 先进先出（FR-025、research R2）
- [X] T073 [US3] 实现分配单生成 `backend/app/services/allocation.py`：写 `order_no`、`code_count`、`code_range_from`/`to`、`template_version_id`、`allocated_by`、`allocated_at`（FR-027）；未指定模板版本时取产品默认模板的当前版本（FR-035）
- [X] T074 [US3] 实现分配接口 `backend/app/api/v1/allocations.py` `POST /api/v1/allocations`：可用量不足返回 `409` 且 `details.available` 给出可分配数量
- [X] T075 [US3] 实现回收接口 `POST /api/v1/allocations/{id}/reclaim`：仅回收 `allocated` 的码，含 `printed`/`printing` 时整单拒绝（FR-030）
- [X] T076 [US3] 实现码池查询接口 `GET /api/v1/codes`，支持按批次、产品、状态筛选（FR-025、FR-026）
- [X] T077 [US3] 实现分配单列表接口 `GET /api/v1/allocations`：返回单号、公司、产品、码数量、码段范围、模板版本、分配人、时间与状态（FR-027）
- [X] T078 [US3] 实现码量导出 `GET /api/v1/reports/code-stock/export`（FR-031）
- [X] T079 [P] [US3] 管理后台：分配与回收页 `admin-web/src/views/allocation/AllocationView.vue` + 码池查询页 `CodePoolView.vue`

**检查点**：US3 可独立演示——分配生成分配单并可回收；并发分配不重不丢

---

## Phase 6: US4 - 工位打印与防重复打印（优先级：P1）🎯 系统核心

**目标**：工位操作员按产品查看本公司可打印码并打印；已打印的码再次打印一律被拒绝

**独立测试**：选数量发起打印后码经 `printing` 变 `printed` 并生成打印记录；对同一码再次发起打印被拒；打印异常标记失败后码回退 `allocated`；两工位并发同一码仅一方成功

### 测试（先写，运行至失败）

- [X] T080 [P] [US4] 集成测试：**防重复打印**（最高优先） `backend/tests/integration/test_anti_duplicate_print.py` —— 对 `printed` 的码发起打印返回 `CODE_ALREADY_PRINTED`（FR-043）；对 `voided` 的码返回 `CODE_VOIDED` —— 先写并运行至失败
- [X] T081 [P] [US4] 集成测试：**并发抢码** `backend/tests/integration/test_print_concurrency.py` —— 同一码的并发打印请求仅一方成功，另一方 `CODE_LOCKED`；批量任务中部分码被抢先锁定不影响其余码（FR-044、FR-049）—— 先写并运行至失败
- [X] T082 [P] [US4] 集成测试：打印确认与失败回退 `backend/tests/integration/test_print_confirm.py` —— `succeeded` → `printed` 且 `print_count+1`、写 `last_printed_workstation_id`；`failed` → 回退 `allocated` 且**补打次数不变**（FR-045、FR-046）；并断言生成的 `PrintLog` 中工位、操作员、打印机三字段均非空（SC-006）—— 先写并运行至失败
- [X] T083 [P] [US4] 集成测试：确认请求来自非持锁工位时返回 `CODE_LOCKED` —— 先写并运行至失败
- [X] T084 [P] [US4] 契约测试：工位端打印接口 `backend/tests/contract/test_workstation_print_api.py` —— 先写并运行至失败
- [X] T085 [P] [US4] 单元测试：模板渲染换算 `print-client/tests/unit/render.spec.ts` 与 `admin-web/tests/unit/render.spec.ts` —— 两端各自实现、针对同一契约（`contracts/template-rendering.md`）测试同一组用例（R6）—— 先写并运行至失败
- [X] T086 [P] [US4] 集成测试：打印中超时回退 `backend/tests/integration/test_lock_timeout.py` —— 将锁超时阈值调至 10 秒，验证码自动回退为 `allocated`、写 `PrintLog(result='timeout_reverted')` 与 `CodeEvent(timeout_reverted)`、补打次数不变、该码可再次正常打印（FR-047、FR-048）—— 先写并运行至失败

### 实现

- [X] T087 [US4] 实现可打印码查询 `GET /api/v1/workstation/codes`：按产品返回**本公司**全部 `allocated` 的码，MUST NOT 按 `workstation_id` 过滤（spec 澄清记录：码在公司内共享）
- [X] T088 [US4] 实现扫码定位 `GET /api/v1/workstation/codes/{code_value}`：不可打印时返回对应错误码（FR-040）
- [X] T089 [US4] 实现打印预占接口 `POST /api/v1/workstation/print`：事务内将码由 `allocated` 置 `printing` 并写 `locked_at`/`locked_workstation_id`；逐码独立处理，部分失败不回滚已接受部分（FR-041、FR-042、FR-049）
- [X] T090 [US4] 实现打印确认接口 `POST /api/v1/workstation/print/confirm`：按 `outcome` 走状态机，写 `PrintLog` 与 `CodeEvent`（FR-050）
- [X] T091 [US4] 实现模板版本解析 `backend/app/services/template_resolver.py`：按分配单携带的版本取 `elements_json`，填充动态字段 `product_name`/`company_name`/`code_value`/`batch_no`（`batch_no` 取分配单 `order_no`，FR-037）
- [X] T092 [US4] 实现打印锁超时扫描 `backend/app/tasks/lock_timeout_sweeper.py`：阈值可配置 `PRINT_LOCK_TIMEOUT_SECONDS`，默认 300 秒；超时将 `printing` 回退 `allocated`，写 `PrintLog(result='timeout_reverted')` 与 `CodeEvent(timeout_reverted)`，**不计补打**（FR-047、FR-048）
- [X] T093 [P] [US4] 工位软件：模板渲染器 `print-client/src/print-render/renderer.ts`，严格实现 `contracts/template-rendering.md`（换算基准、`scaleFactor` 固定 100%、元素裁剪、未知类型抛错、字体回退）
- [X] T094 [P] [US4] 工位软件：本地打印服务 `print-client/src/print-service/server.ts`，监听 `127.0.0.1` 回环 HTTP，提供打印与状态端点（FR-041）
- [X] T095 [US4] 工位软件：静默打印通道 `print-client/src/main/print.ts`，使用 `webContents.print({ silent: true, deviceName, pageSize })`，`pageSize` 取模板毫米尺寸（research R5）
- [X] T096 [P] [US4] 工位软件：打印操作页 `print-client/src/renderer/views/PrintView.vue`，按产品选码、按数量发起打印、标记失败
- [X] T097 [P] [US4] 工位软件：契约客户端 `print-client/src/renderer/api/print.ts`
- [X] T098 [US4] 管理后台：模板渲染预览器 `admin-web/src/components/TemplatePreview.vue`，实现同一份 `contracts/template-rendering.md`
- [X] T099 [US4] 渲染一致性验证脚本 `admin-web/tests/e2e/render-conformance.spec.ts`：同一 `elements_json` 在预览与打印（输出 PDF）后逐元素比对位置与尺寸，偏差 MUST 在 ±0.5mm 内（`contracts/template-rendering.md` 验收方式）

**检查点**：US4 可独立演示——真实出纸、一码一打、并发安全。这是系统的核心控制点，必须全绿

---

## Phase 7: US5 - 补打与作废（优先级：P1）

**目标**：管理员对已打印的码补打（自动派发回原工位、必填原因）；对权限范围内的码作废（必填原因、终态）

**独立测试**：补打后补打次数加一且任务出现在原工位；原工位离线时补打被拒且码状态不变；未填原因被拒；作废后的码在任何工位不可见不可打印且无法恢复

### 测试（先写，运行至失败）

- [X] T100 [P] [US5] 集成测试：**补打派发与离线拒绝** `backend/tests/integration/test_reprint_dispatch.py` —— 补打自动派发到 `last_printed_workstation_id`；心跳超时 30 秒后补打返回 `WORKSTATION_OFFLINE` 且码状态不变（FR-055、FR-056、research R1）—— 先写并运行至失败
- [X] T101 [P] [US5] 集成测试：补打权限矩阵 `backend/tests/integration/test_reprint_permission.py` —— 子公司管理员仅限本公司码、工位操作员无补打权限、未填原因返回 `REASON_REQUIRED`（FR-051、FR-052、FR-053）—— 先写并运行至失败
- [X] T102 [P] [US5] 集成测试：作废终态 `backend/tests/integration/test_void.py` —— 作废后码不可见不可打印不可恢复；作废必填原因；批量中混入他公司码整体拒绝、混入已作废码按幂等跳过（FR-057、FR-058、FR-059、FR-060）—— 先写并运行至失败
- [X] T103 [P] [US5] 单元测试：心跳超时边界 `backend/tests/unit/test_offline_detection.py` —— 29 秒判在线、31 秒判离线 —— 先写并运行至失败
- [X] T104 [P] [US5] 契约测试：补打、作废、任务轮询接口 `backend/tests/contract/test_reprint_api.py` —— 先写并运行至失败
- [X] T105 [P] [US5] 前端单元测试：补打/作废原因必填校验 `admin-web/tests/unit/reprint.spec.ts` —— 先写并运行至失败

### 实现

- [X] T106 [US5] 实现补打接口 `POST /api/v1/codes/{code_value}/reprint`：校验 `printed` 状态、必填原因、目标工位心跳未超时，创建 `PrintTask`（FR-051、FR-053、FR-055、FR-056）
- [X] T107 [US5] 实现批量作废接口 `POST /api/v1/codes/void`：按 `contracts/admin-api.md` 的约束处理混入情况（FR-057）
- [X] T108 [US5] 实现工位心跳接口 `POST /api/v1/workstation/heartbeat`：更新 `last_heartbeat_at`（research R1）
- [X] T109 [US5] 实现任务领取接口 `GET /api/v1/workstation/tasks`：**原子领取**（`UPDATE ... WHERE status='pending'`），无任务时 MUST NOT 产生任何数据库写入（research R1）
- [X] T110 [US5] 实现任务结果回报 `POST /api/v1/workstation/tasks/{task_id}/result`：成功时 `reprint_count+1`，失败时不增加；两者均写 `PrintLog(print_type='reprint')` 与 `CodeEvent`
- [X] T111 [US5] 实现任务过期清理 `backend/app/tasks/task_expiry.py`：`pending` 超期任务置 `expired`，防止无限滞留
- [X] T112 [US5] 实现补打/作废台账接口 `GET /api/v1/reprints`（FR-067）
- [X] T113 [P] [US5] 工位软件：5 秒心跳与任务轮询循环 `print-client/src/renderer/composables/useHeartbeat.ts` + `useTaskPolling.ts`（research R1）
- [X] T114 [P] [US5] 工位软件：补打任务执行与回报 `print-client/src/renderer/views/TaskView.vue`
- [X] T115 [P] [US5] 管理后台：补打与作废操作入口 `admin-web/src/views/code/CodeActionsPanel.vue`，复用 `useReasonPrompt` 强制原因
- [X] T116 [P] [US5] 管理后台：补打/作废台账页 `admin-web/src/views/report/ReprintLedgerView.vue`

**检查点**：US5 可独立演示——补打落到原工位、离线被拒、作废不可逆

---

## Phase 8: US6 - 打印模板管理与下发（优先级：P2）

**目标**：总部创建与维护模板，带版本号与冻结机制；可视化拖拽编辑与打印预览

**独立测试**：创建模板产生版本；修改生成新版本且历史版本保留；已被分配单引用的版本内容冻结不受修改影响；子公司无法修改模板

### 测试（先写，运行至失败）

- [X] T117 [P] [US6] 集成测试：版本冻结 `backend/tests/integration/test_template_freeze.py` —— 修改 `frozen=true` 的版本返回 `TEMPLATE_VERSION_FROZEN`；模板停用不影响已冻结版本继续用于打印（FR-034）—— 先写并运行至失败
- [X] T118 [P] [US6] 集成测试：模板访问控制 `backend/tests/integration/test_template_readonly.py` —— 模板读写接口仅总部可访问，子公司管理员或工位操作员请求返回 `FORBIDDEN_SCOPE`（FR-036）—— 先写并运行至失败
- [X] T119 [P] [US6] 契约测试：模板接口 `backend/tests/contract/test_template_api.py` —— 先写并运行至失败
- [X] T120 [P] [US6] 前端单元测试：模板编辑器坐标与拖拽 `admin-web/tests/unit/template-editor.spec.ts` —— 先写并运行至失败

### 实现

- [X] T121 [US6] 实现模板服务 `backend/app/services/template.py`：新建含首个版本；修改 MUST 新建版本并递增 `version_no`，MUST NOT 修改既有版本行（FR-033）
- [X] T122 [US6] 实现模板接口 `backend/app/api/v1/templates.py`：CRUD、版本列表、停用、版本内容更新（FR-032、FR-033）
- [X] T123 [US6] 实现版本冻结标记 `backend/app/services/template.py`：被 `AllocationOrder` 或 `PrintTask` 引用时置 `frozen=true`（FR-034）
- [X] T124 [US6] 实现模板元素结构校验 `backend/app/schemas/template.py`：按 `contracts/template-rendering.md` 校验元素类型、必填属性与单位
- [X] T125 [P] [US6] 管理后台：模板列表与版本管理页 `admin-web/src/views/template/TemplateListView.vue`
- [X] T126 [US6] 管理后台：可视化模板编辑器 `admin-web/src/components/TemplateEditor.vue`，使用 `vue-draggable-plus` 实现拖拽定位 + 实时预览（FR-038）
- [X] T127 [US6] 管理后台：打印预览 `admin-web/src/components/TemplatePrintPreview.vue`，复用 T098 的渲染器保证所见即所打

**检查点**：US6 可独立演示——模板版本化、冻结不可改、拖拽编辑与预览

---

## Phase 9: US7 - 统计报表与总部看板（优先级：P2）

**目标**：总部按公司/产品查看四态码量分布与打印明细并导出；子公司仅见本公司

**独立测试**：看板四态码量与实际一致；打印明细可多维筛选并导出；子公司账号查询结果不含他公司数据

### 测试（先写，运行至失败）

- [X] T128 [P] [US7] 集成测试：看板聚合正确性 `backend/tests/integration/test_dashboard.py` —— 四态码量与逐条统计一致；时间筛选生效（FR-065）—— 先写并运行至失败
- [X] T129 [P] [US7] 集成测试：报表组织隔离 `backend/tests/integration/test_report_isolation.py` —— 子公司报表查询结果中他公司数据出现 0 次（SC-007、FR-068）—— 先写并运行至失败
- [X] T130 [P] [US7] 性能测试：百万级下列表查询 3 秒内返回 `backend/tests/integration/test_query_performance.py`（SC-013）—— 先写并运行至失败
- [X] T131 [P] [US7] 契约测试：报表接口 `backend/tests/contract/test_report_api.py` —— 先写并运行至失败

### 实现

- [X] T132 [US7] 实现看板聚合接口 `backend/app/api/v1/dashboard.py`：**数据库聚合**，走 data-model.md 的 `(company_id, product_id, status)` 索引
- [X] T133 [US7] 实现打印明细接口 `GET /api/v1/reports/prints`：支持公司/工位/操作员/产品/时间段筛选（FR-066）
- [X] T134 [US7] 实现打印明细导出 `GET /api/v1/reports/prints/export`，流式写 Excel 避免大结果集占内存
- [X] T135 [P] [US7] 管理后台：总部看板页 `admin-web/src/views/dashboard/DashboardView.vue`，四态分布 + 时间筛选
- [X] T136 [P] [US7] 管理后台：打印明细页 `admin-web/src/views/report/PrintDetailView.vue`，多维筛选 + 导出

**检查点**：US7 可独立演示——看板与明细准确、导出可用、隔离生效

---

## Phase 10: US8 - 操作日志与码全生命周期追溯（优先级：P2）

**目标**：不可篡改的操作日志仅总部可查；输入码值展示完整时间线

**独立测试**：关键操作均入日志且字段完整；日志不可改删；非总部查询被拒；码时间线完整

### 测试（先写，运行至失败）

- [X] T137 [P] [US8] 集成测试：日志不可篡改与仅总部可查 `backend/tests/integration/test_audit_log.py` —— 非总部访问 `GET /api/v1/audit-logs` 返回 `FORBIDDEN_SCOPE`；无更新/删除入口（FR-060、FR-062）—— 先写并运行至失败
- [X] T138 [P] [US8] 集成测试：码时间线完整性 `backend/tests/integration/test_code_timeline.py` —— 走完导入→绑定→分配→打印→补打→作废全链路后，时间线含全部节点及操作人/时间/工位（FR-064）；并断言查询耗时 ≤5 秒（SC-002）—— 先写并运行至失败
- [X] T139 [P] [US8] 契约测试：审计与码详情接口 `backend/tests/contract/test_audit_api.py` —— 先写并运行至失败

### 实现

- [X] T140 [US8] 实现审计日志查询接口 `GET /api/v1/audit-logs`，含角色/公司/时间过滤（FR-061、FR-062）
- [X] T141 [US8] 实现码详情与时间线接口 `GET /api/v1/codes/{code_value}`，基于 `CodeEvent` 表返回完整时间线（FR-064）
- [X] T142 [US8] 审核并补齐全部关键操作的审计埋点 `backend/app/services/`：登录、导入、分配、回收、打印、补打、作废、模板变更、账号变更（FR-061）
- [X] T143 [P] [US8] 管理后台：操作日志页 `admin-web/src/views/audit/AuditLogView.vue`（仅总部可见菜单）
- [X] T144 [P] [US8] 管理后台：码生命周期时间线页 `admin-web/src/views/code/CodeTimelineView.vue`

**检查点**：US8 可独立演示——日志可审计、码可全链路追溯

---

## Phase 11: US9 - 打印机绑定与打印服务健壮性（优先级：P3）

**目标**：工位绑定默认打印机；打印前检测服务与打印机状态并给出明确提示；服务断线自动重连；新型号以驱动接入

**独立测试**：工位设置可列出本机打印机并绑定；服务未启动/打印机离线给出对应提示；断线后自动重连

- [X] T145 [P] [US9] 契约测试：打印机绑定接口 `backend/tests/contract/test_printer_api.py` —— 先写并运行至失败
- [X] T146 [P] [US9] 单元测试：打印服务与打印机状态判定 `print-client/tests/unit/print-service-status.spec.ts` —— 区分"打印服务未启动"与"打印机离线"两种提示；断线后自动重连并在界面内呈现常驻状态提示（FR-071、FR-072）—— 先写并运行至失败
- [X] T147 [US9] 实现打印机绑定接口 `PUT /api/v1/workstation/printer`（FR-070）
- [X] T148 [P] [US9] 工位软件：读取本机打印机清单 `print-client/src/print-service/printers.ts`（MUST NOT 由服务端提供，见 `contracts/workstation-api.md`）
- [X] T149 [US9] 工位软件：打印服务状态检测与提示 `print-client/src/renderer/composables/usePrintServiceStatus.ts`：区分"打印服务未启动"与"打印机离线"两种提示（FR-071）
- [X] T150 [US9] 工位软件：打印服务断线自动重连 `print-client/src/print-service/server.ts`，重连后向操作员提示（FR-072）
- [X] T151 [P] [US9] 工位软件：工位设置页 `print-client/src/renderer/views/SettingsView.vue`
- [X] T152 [US9] 编写打印机适配矩阵文档 `print-client/docs/printer-matrix.md`：为甲方提供的每个型号记录"型号—驱动—纸张规格—验证结论"（FR-073、SC-012）
- [X] T153 [US9] 工位软件打包配置 `print-client/electron-builder.yml`：Win10 安装包（32/64 位），安装后自动注册本地打印服务（FR-074）

**检查点**：US9 可独立演示——设备层可用性与兼容性闭环

---

## Phase 12: Polish 与横切关注点

**目的**：跨故事的收尾、性能与验收

- [X] T154 [P] 并发工位压测 `backend/tests/integration/test_concurrency_50.py`：模拟 50 工位同时心跳与打印，无错误、无需人工干预（SC-008）
- [X] T155 [P] 批量打印下发性能 `backend/tests/integration/test_batch_print_perf.py`：单次 500 码任务 60 秒内完成下发（SC-005）
- [X] T156 [P] 端到端冒烟测试 `admin-web/tests/e2e/smoke.spec.ts`：走完 quickstart 场景 1~8 的主链路
- [X] T157 补齐 `quickstart.md` 场景 3、4、6 的自动化断言：防重复打印、失败回退与补打区分、超时回退记录的 `timeout_reverted` 落盘
- [X] T158 全链路 HTTPS 与会话安全复查 `backend/app/core/security.py`：确认密码加密存储、令牌不落日志（非功能需求·安全）
- [X] T159 执行 `quickstart.md` 全部验证场景并记录结果，逐条核对 SC-001 ~ SC-013
- [X] T160 管理后台浏览器兼容性验证 `docs/qa/browser-compat.md`：在 Win10 的 Chrome 与 Edge 主流版本上走完 `quickstart.md` 场景 1~8，记录浏览器版本号与结果（FR-075）
- [X] T161 计时与可追溯性验证 `docs/qa/perf-trace.md`：工位操作员从登录到产出第一张标签 ≤60 秒（SC-004）；码时间线查询 ≤5 秒（SC-002）；抽样断言 `PrintLog` 的工位、操作员、打印机三字段非空率为 100%（SC-006）
- [X] T162 [P] 数据备份配置文档 `docs/ops/backup.md`：MySQL 每日自动备份保留 30 天、操作日志保留 ≥2 年（FR-063）
- [X] T163 复核宪章合规：确认全部任务的测试先于实现，并在 PR 描述中逐条对照宪章六条原则（宪章·合规审查）

---

## 依赖关系

```text
Phase 1 (Setup)
      ↓
Phase 2 (Foundational)  ← 阻塞全部用户故事
      ↓
┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
US1   US2   US3   US4   US5   US6   US7   US8   US9
组织  导入  分配  打印  补打  模板  报表  日志  打印机器
      │     │     │     │
      └─────┴─────┘     │
        US3 依赖 US2     │
        （需有码可分配） │
                        │
                  US4 依赖 US3（需分配单携带模板版本）
                        │
                  US5 依赖 US4（补打以已打印为前提）
```

**关键依赖链**：
- **US2 → US3**：没有码就无法分配
- **US3 → US4**：打印必须拿到"分配单携带的模板版本"
- **US4 → US5**：补打只作用于 `printed` 的码
- **US1** 独立，但其数据是全部故事的组织归属基础
- **US6 / US7 / US8 / US9** 相互独立；US6 不阻塞 US4（模板的数据层已在 Foundational 完成）

**可并行的故事**：US1 与 US2 可同时开始；US7、US8、US9 在任意时刻可并行介入

## 并行执行示例

```text
# 阶段 A：两人同时起步
开发者甲：T039 → T040 → T041 → T042   （US1 后台组织与账号）
开发者乙：T054 → T055 → T056 → T057   （US2 后台导入）

# 阶段 B：US3 完成后，前后端并行
开发者甲：T089 → T090 → T091 → T092   （US4 后台打印链路）
开发者乙：T093 → T094 → T095          （US4 工位端渲染与打印服务）
开发者丙：T098 → T099                 （US4 预览与一致性验证）
```

任务级并行标记 `[P]` 表示该任务与同阶段其他 `[P]` 任务可同时进行（不同文件、无未完成依赖）。

## 实施策略

### MVP 范围（建议）

**Phase 1 + 2 + US1**（46 个任务）。理由：US1 是唯一不需要码就能独立演示的完整闭环——组织、工位、
账号、下线控制全部可验收，且是后续一切数据归属的基础。

其次是 **US2**——有了码池，才能验证系统真正的价值主张（导入 10 万行、成对校验、产品绑定）。

### 增量交付顺序

1. **MVP**：Phase 1 + 2 + US1 —— 可演示组织与账号管理
2. **+US2**：码进入码池 —— 可演示导入与产品绑定
3. **+US3**：码分配到公司 —— 可演示分配与回收
4. **+US4**：真实出纸 + 一码一打 —— **系统的核心价值主张达成，此时已具备交付条件**
5. **+US5**：补打与作废 —— 异常通道闭环
6. **+US6 ~ US9**：模板编辑、报表、审计、设备健壮性

### 关于测试任务的排序（宪章原则一）

每个故事阶段内，**测试任务 MUST 先于其对应实现任务执行并运行至失败**。
TDD 循环为：写失败测试 → 实现至通过 → 重构。审查时若发现实现任务的代码先于其测试存在，
视为违反宪章原则一。

### 最高优先级的七个测试

按 `research.md R8` 列出的六个高风险点，另补"并发抢码"一项，以下七项是系统业务主张所在，
任何回归都直接破坏项目目标，其测试 MUST 最先编写：

| 测试任务 | 对应规格 | 保护的主张 |
|----------|----------|-----------|
| T080 | FR-043 | 已打印的码不可再打印 |
| T081 | FR-044 | 并发下同一码只有一个赢家 |
| T086 | FR-047/048 | 超时回退：不计补打且留痕可审计 |
| T100 | FR-055/056 | 补打落到原工位、离线被拒 |
| T028 | FR-006/007 | 组织隔离不可越权 |
| T048 | FR-014 | 导入成对校验 |
| T049 | FR-010 | 产品停用前置校验 |

## 备注

- T085 / T093 / T098 / T099 共同构成 `contracts/template-rendering.md` 的一致性保障。
  两端**各自实现**渲染规则（宪章原则六禁止交叉引用），因此这条链路有 4 个任务，不是冗余。
- 产品型号适配（T152）依赖甲方提供型号清单（PRD OI-01）与码单批上限（OI-02），
  这两项是外部依赖，不在本清单范围内。
- 本清单不含任何"改进相邻代码"类任务——仓库当前为全新，全部是新增文件（宪章原则五）。
- SC-011 的"99.5% 可用性"是投运后的运维指标，不由构建工作直接覆盖；其可构建的一半（本地打印服务断线后自动恢复、无需重装）由 T146 与 T150 覆盖。
