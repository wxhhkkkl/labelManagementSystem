# 实施计划：打印管理系统

**分支**：`001-printer-management-system` | **日期**：2026-10-12 | **规格**：[spec.md](./spec.md)

**输入**：功能规格来自 `/specs/001-printer-management-system/spec.md`

## 摘要

建造一套面向"总部 + 多分子公司"的打印管理系统，覆盖 79 条功能需求的完整闭环：
总部导入码与"码—产品"对照关系 → 按"公司 + 产品"分配并随单下发模板版本 →
工位操作员在工位电脑上打印并驱动本地打印机出纸 → 补打/作废全程留痕。

系统由三个互相隔离的部分组成：**后台服务**（FastAPI + MySQL 8）、**管理后台**
（Vue 3，浏览器访问）、**工位软件**（Electron，含独立本地打印服务）。

技术方案的关键决策（见 [research.md](./research.md)）：统一 JWT 认证、工位端 5 秒轮询领取
补打任务、异步处理 10 万行导入、走 Windows 打印驱动的静默打印路径。系统最核心的控制点是
**"一码一打"**——由数据库行锁 + 码状态机保证（FR-042 / FR-044）。

## 技术上下文

**Language/Version**：Python 3.12（后台）｜ TypeScript 5.x / Node.js 20 LTS（前端与工位端）

**Primary Dependencies**：
- 后台：FastAPI、SQLAlchemy 2.x、Alembic、PyMySQL、Pydantic v2、openpyxl（流式解析）、PyJWT
- 管理后台：Vue 3、Vite、Pinia、Vue Router、Element Plus、`vue-draggable-plus`（模板拖拽）
- 工位软件：Electron、Vue 3（复用管理后台的技术栈约定，但代码独立）

**Storage**：MySQL 8.0.1+ / InnoDB / utf8mb4（`SKIP LOCKED` 要求 8.0+，见 R2）

**Testing**：pytest（单元/集成/契约）· vitest（前端单元）· playwright（端到端）

**Target Platform**：服务端 Linux 云服务器 ｜ 管理后台 Win10 Chrome/Edge ｜ 工位软件 Win10 安装包（32/64 位）

**Project Type**：Web 服务 + 桌面客户端（单仓库三目录，见"结构决策"）

**Performance Goals**：码库百万级；列表查询 3 秒内（SC-013）；单次 500 码批量打印 60 秒内下发（SC-005）；10 万行导入（SC-003）

**Constraints**：
- 全链路 HTTPS；组织隔离由服务端强制注入，不信任客户端参数（R7）
- JWT 访问令牌 2 小时 / 刷新令牌 7 天；账号停用须每次请求实时校验（R4）
- 心跳 5 秒，离线判定阈值 30 秒（R1）——这是 FR-056 补打前置校验的依据
- 打印中锁超时默认 5 分钟，可配置（FR-047）
- 工位软件 MUST NOT 直接访问数据库，业务数据只走 HTTP 接口（FR-076）

**Scale/Scope**：码库百万级；≥50 工位并发；9 个用户故事；55 个 HTTP 接口；3 个交付单元

## 宪章检查

*门禁：Phase 0 研究前必须通过；Phase 1 设计后需复核。*

| 原则 | 结论 | 依据 |
|------|------|------|
| 一、测试优先（不可协商） | ✅ 通过 | [research.md R8](./research.md) 定义了三层测试与六个必须先行的高风险点；`tasks.md` 将按"测试任务先于实现任务"排序，每个实现任务的验收以其测试通过为准 |
| 二、不猜测，先问清楚 | ✅ 通过 | 规格阶段 8 项歧义已全部澄清并写入规格（`## Clarifications` 5 条 + `## 澄清记录` 3 条），无 `[NEEDS CLARIFICATION]` 残留 |
| 三、架构变更须先确认 | ✅ 通过 | 4 项架构决策（下发通道 / 数据库 / 导入处理 / 认证机制）已在 Phase 0 之前提交用户确认；本计划不含未经确认的架构变更 |
| 四、简单优先 | ✅ 通过 | 未引入 Redis/Celery/消息队列；轮询替代长连接；导入队列用进程内队列 + 数据库状态表。仅新增 PrintTask、CodeEvent 两张表，理由见下 |
| 五、外科手术式修改 | ✅ 通过 | 仓库当前为全新（仅含 `CLAUDE.md`、`PRD/`、`.specify/`），本计划全部为新增文件，不修改任何既有代码 |
| 六、双端分离架构 | ✅ 通过 | `backend/` `admin-web/` `print-client/` 三目录依赖与构建配置相互隔离；工位端业务数据只经 HTTP 接口获取（FR-076） |

**无违规项，无需填写复杂度豁免表。**

### 对两处"看似多余"的设计的说明

- **PrintTask 表**：不是过度设计。补打是**唯一**由服务端主动发起、需要工位端执行的场景；
  没有它，"补打自动派发到原工位"（FR-055）无从落地。轮询模型下它同时承担了任务队列的角色。
- **CodeEvent 表**：不能复用 AuditLog。两者可见范围不同——AuditLog 仅总部管理员可查（FR-062），
  而码的生命周期时间线需按数据归属可见（FR-064）。混用会导致越权或该看的人看不到。
  它同时是 FR-064 时间线查询的性能保障（避免从审计日志反推状态链）。

### Phase 1 复核（设计完成后）

| 检查项 | 结论 |
|--------|------|
| `data-model.md` 是否引入与规格无关的实体 | 未引入。14 张表逐条对应规格的 10 个关键实体 + TemplateVersion/PrintTask/CodeEvent/WorkstationOperator 四张版本、流程或关联表，均有规格条目支撑 |
| `contracts/` 是否泄漏实现细节到规格 | 未泄漏。契约只描述接口与错误码，不改变规格语义 |
| 是否出现新的架构决策 | **出现一处，已按原则六修正**：R6 原拟"两端共享渲染模块"与原则六"两端 MUST NOT 交叉引用"冲突，已改为"渲染规则以契约定死、两端各自实现"，见 [contracts/template-rendering.md](./contracts/template-rendering.md) |
| 高风险点是否有对应验证场景 | 已覆盖。`quickstart.md` 的场景 1~8 逐条对应 R8 的六个高风险点 |

## 结构决策

**选定结构**：单仓库三目录（`backend/` + `admin-web/` + `print-client/`），三者依赖清单与构建
配置完全独立，不设共享代码包。

```text
backend/
├── app/
│   ├── api/v1/            # 按领域划分的路由：auth, org, products, imports,
│   │                      #   codes, allocations, templates, printing, reports, audit
│   ├── core/              # 配置、安全（JWT）、数据库会话、组织隔离依赖
│   ├── models/            # SQLAlchemy 模型（对应 data-model.md 的 14 张表）
│   ├── schemas/           # Pydantic 请求/响应模型
│   ├── services/          # 业务逻辑：码状态机、分配取码、打印预占与确认、导入校验
│   ├── tasks/             # 后台任务：导入 worker、打印锁超时扫描
│   └── main.py
├── migrations/            # Alembic
├── tests/
│   ├── unit/              # 状态机、码值校验、渲染换算
│   ├── integration/       # 需真实 MySQL：并发抢码、组织隔离、批次导入
│   └── contract/          # 逐接口契约测试（含越权用例）
└── pyproject.toml

admin-web/
├── src/
│   ├── api/               # 契约客户端（按 contracts/ 生成或手写）
│   ├── views/             # 页面：组织、产品、导入、分配、模板、报表、日志
│   ├── components/        # 模板可视化编辑器、看板图表、数据表格
│   ├── stores/            # Pinia
│   └── router/
├── tests/{unit,e2e}/
└── package.json

print-client/
├── src/
│   ├── main/              # Electron 主进程：窗口、托盘、拉起打印服务
│   ├── renderer/          # 操作界面：工位绑定、选码、打印、任务列表
│   ├── print-service/     # 本地打印服务（独立常驻进程，监听 127.0.0.1 回环 HTTP）
│   └── print-render/      # 按 template-rendering.md 契约实现的渲染器
├── tests/
└── package.json

specs/001-printer-management-system/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/             # HTTP 接口契约 + 模板渲染契约
└── tasks.md               # 由 /speckit-tasks 生成
```

**结构理由**：
- 三目录对应宪章原则六的三方隔离要求；工位端与管理后台**不设共享代码包**，
  跨端一致性通过契约（`contracts/template-rendering.md`）而非共享模块保证。
- `print-service/` 独立成目录，对应"本地打印服务可被独立检测到未启动"（FR-071）与
  "安装后自动注册"（FR-074）——它必须是可独立于界面进程运行与注册的常驻进程。
- `tests/` 三层的划分直接对应宪章原则一与 R8 的测试策略。

**被否决的结构**：
- 引入 `packages/shared/` 共享渲染与类型定义 —— 违反宪章原则六"两端 MUST NOT 交叉引用"。
- 前后端同仓但单一 `src/` 根 —— 无法满足两端依赖清单隔离的要求。

## 复杂度追踪

无宪章违规项，本表不适用。
