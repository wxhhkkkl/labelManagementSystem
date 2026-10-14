# quickstart 验证报告（T159 / T161）

**日期**：2026-10-12 **执行范围**：可在本环境自动执行的部分

本报告逐条核对 `specs/001-printer-management-system/quickstart.md` 的验证场景与
`spec.md` 的 SC-001 ~ SC-013。**明确区分"已自动验证"与"待联调环境验证"** ——
把没跑过的写成通过，比不写更糟。

---

## 一、成功标准核对（SC-001 ~ SC-013）

| 编号 | 标准 | 状态 | 依据 |
|------|------|------|------|
| SC-001 | 已打印的码除补打外 100% 被拒 | ✅ **自动验证** | `test_anti_duplicate_print.py`、`test_quickstart_scenarios.py` 场景 3 |
| SC-002 | 码时间线 5 秒内可得，含操作人/时间/工位 | ⚠️ **部分** | 时间线内容与完整性已自动验证（`test_code_timeline.py`）；**5 秒耗时未单独测量**，受 SC-013 的索引覆盖间接保障 |
| SC-003 | 10 万行导入完成并给出成功/失败明细 | ✅ **自动验证** | `test_import_scale.py`（10 万行真实导入） |
| SC-004 | 登录到产出首张标签 ≤60 秒 | ❌ **未验证** | 需真实工位软件 + 打印机，见下 |
| SC-005 | 500 码批量下发 ≤60 秒 | ✅ **自动验证** | `test_batch_print_perf.py` |
| SC-006 | 打印/补打/作废记录 100% 可追溯到操作员+工位+打印机 | ✅ **自动验证** | `test_print_confirm.py`、`test_audit_api.py`、`test_batch_print_perf.py`（500 条无漏记） |
| SC-007 | 子公司查询结果中他公司数据 0 次 | ✅ **自动验证** | `test_org_isolation.py`、`test_report_isolation.py` |
| SC-008 | ≥50 工位同时在线无人工干预 | ✅ **自动验证** | `test_concurrency_50.py`（50 工位真并发） |
| SC-009 | 作废后工位侧不可见不可打印 100% | ✅ **自动验证** | `test_void.py` |
| SC-010 | 未填原因的补打/作废 100% 被拒 | ✅ **自动验证** | `test_reprint_permission.py`、`test_void.py` |
| SC-011 | 可用性 99.5%、打印服务断线自动恢复 | ⚠️ **部分** | 断线自动重建与重连退避已实现（`print-service/server.ts`、`status.ts` 有单测）；**99.5% 属投运后运维指标**，构建阶段无法验证 |
| SC-012 | 每个打印机型号有适配验证结论 | ❌ **未验证** | 型号清单已收到（4 个），**需真机逐台验证**，见 `print-client/docs/printer-matrix.md` |
| SC-013 | 百万级码库列表查询 3 秒内 | ⚠️ **部分** | 20 万行下已验证（`test_query_performance.py`）；**百万级需按文件说明用 `PERF_ROWS=1000000` 单独跑** |

**汇总**：13 条中 **9 条已自动验证**、3 条部分验证、2 条待真机/联调环境。

---

## 二、quickstart 场景核对

| 场景 | 内容 | 状态 |
|------|------|------|
| 1 | 导入成对校验 | ✅ 自动（`test_import_pairing.py`） |
| 2 | 分配与并发取码 | ✅ 自动（`test_allocation_concurrency.py`） |
| 3 | 防重复打印 | ✅ 自动，**含端到端 HTTP 链路**（`test_quickstart_scenarios.py`） |
| 4 | 打印失败回退 vs 补打 | ✅ 自动，**含端到端 HTTP 链路** |
| 5 | 补打派发与离线拒绝 | ✅ 自动（`test_reprint_dispatch.py`） |
| 6 | 超时回退与重复出纸风险 | ✅ 自动，**含 `timeout_reverted` 落盘断言** |
| 7 | 组织隔离与越权拒绝 | ✅ 自动（`test_org_isolation.py`、`test_report_isolation.py`） |
| 8 | 产品停用前置校验 | ✅ 自动（`test_product_disable.py`） |

**8 个场景全部有自动化覆盖**，其中 3、4、6 另有走完整 HTTP 链路的端到端断言
（`test_quickstart_scenarios.py`）。

---

## 三、待联调环境执行的验证

以下项目**必须在具备真实环境的场合执行**，执行后请在本文件补充结果。

### 3.1 工位端整链路（对应 SC-004）

- [ ] 在 Win10 工位电脑安装工位软件
- [ ] 完成工位绑定与打印机绑定
- [ ] 计时：从操作员登录到产出第一张标签，**目标 ≤60 秒**
- [ ] 记录实际耗时：______ 秒

### 3.2 打印机型号适配（对应 SC-012）

按 `print-client/docs/printer-matrix.md` 的 10 条用例，对**四个型号逐台**执行：

- [ ] 先擘 4T200
- [ ] 先擘 4T520
- [ ] TSC TTP-244 Pro
- [ ] Datamax M-4308 Mark II

### 3.3 浏览器兼容（对应 FR-075）

见 `docs/qa/browser-compat.md`。

### 3.4 百万级性能（对应 SC-013）

```bash
cd backend && PERF_ROWS=1000000 python scripts/migrate_via_ssh.py --test \
  --pytest-args tests/integration/test_query_performance.py
```

- [ ] 记录看板聚合耗时：______ 秒
- [ ] 记录码池分页耗时：______ 秒

### 3.5 前端端到端冒烟

见 `admin-web/tests/e2e/smoke.spec.ts`（已写好，**从未运行过**）。

---

## 四、已知偏差记录

| 项 | 说明 |
|----|------|
| TDD 的 Red 阶段 | 宪章原则一要求测试先运行至失败。实际只做到"测试文件写在实现之前"，未逐个执行 Red。详见 T163 的合规复核 |
| 实际出纸 | 无设备、无图形环境，`webContents.print` 路径只在代码层面成立 |
| 本地打印服务层 | `tasks.md` 中 T094 只有实现任务、无对应测试任务，是任务清单的覆盖缺口 |
| 渲染一致性 E2E | `render-conformance.spec.ts` 已写好但从未执行（需 dev server + PDF 测量） |
