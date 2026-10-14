# 契约：工位软件接口

**日期**：2026-10-12 | **规格**：[spec.md](../spec.md) | **适用角色**：工位操作员（`operator`）

工位软件（Electron）是唯一会**主动轮询**的客户端（R1）。其与**本地打印服务**之间的通信
（本地回环 HTTP/WS）不在本契约范围内——那是设备内部通信，不承载业务数据（FR-076）。

---

## 工位绑定

### POST /api/v1/workstation/bind

**用途**：工位软件首次配置时声明本机代表的工位（FR-069）。绑定关系持久化在工位端本地，
后续每次心跳与打印请求都携带 `workstation_id`。

**请求**：`{ "workstation_id": 11 }`

**响应 200**

```json
{ "workstation_id": 11, "name": "一号包装工位", "company_id": 7, "printer_name": "Zebra ZD421" }
```

**约束**
- 请求的工位 MUST 属于当前用户所在公司，否则 `403 FORBIDDEN_SCOPE`。
- 工位或其所属公司已停用 → `409 WORKSTATION_DISABLED`（FR-003）。
- 绑定成功时更新 `Workstation.bound_at`。

### PUT /api/v1/workstation/printer

**用途**：保存本工位默认打印机（FR-070）。请求：`{ "printer_name": "Zebra ZD421" }`。
本机打印机清单由工位端从操作系统读取，MUST NOT 由服务端提供。

---

## 心跳与任务轮询

### POST /api/v1/workstation/heartbeat

**用途**：上报本工位在线（R1）。请求：`{ "workstation_id": 11, "print_service_ok": true }`。
响应 `204`。服务端更新 `Workstation.last_heartbeat_at`。

- 频率 **5 秒**；超过 **30 秒**未上报即判定离线，影响 FR-056 的补打校验。
- 工位端 MUST 在断网时进入重试；恢复后 MUST NOT 重放历史心跳。

### GET /api/v1/workstation/tasks

**用途**：领取本工位的待执行任务（当前仅 `reprint`）。**R1 轮询入口**。

**查询参数**：`workstation_id`（必填）

**响应 200**

```json
{
  "tasks": [
    {
      "task_id": 501,
      "task_type": "reprint",
      "code_value": "A1B2C3D4",
      "template_version_id": 88,
      "elements_json": { "paper_width_mm": 60, "paper_height_mm": 40, "elements": [] },
      "data": {
        "product_name": "500ml 矿泉水",
        "company_name": "华东分公司",
        "code_value": "A1B2C3D4",
        "batch_no": "ALL20261012003"
      },
      "product_name": "500ml 矿泉水",
      "company_name": "华东分公司",
      "reason": "标签破损"
    }
  ]
}
```

**约束**
- 频率 **5 秒**。无待执行任务时 MUST 返回空数组且**不产生任何数据库写入**（R1）。
- 领取为原子操作：服务端以 `SELECT ... FOR UPDATE SKIP LOCKED` 锁定候选行后再改状态，
  并发领取时后来者直接跳过，不会拿到同一任务。
- **模板内容与动态字段随任务一并下发**（`elements_json` + `data`）。若只给
  `template_version_id`，工位端还得再取一次模板才能渲染，多一次往返也多一个失败点——
  补打路径上任何多余的往返都会让"标签损坏要立刻重印"这个场景变慢。
- 工位端领取后 MUST 立即调用 `POST /api/v1/workstation/tasks/{id}/result` 回报结果；
  不回会导致任务长期停在 `claimed`。

### POST /api/v1/workstation/tasks/{task_id}/result

**用途**：回报任务执行结果。

**请求**：`{ "result": "succeeded", "failure_reason": null }`

**约束**
- 无论成功失败，服务端 MUST 写 `PrintLog`（`print_type='reprint'`）与 `CodeEvent`。
- 成功时 `Code.reprint_count + 1`，码保持 `printed`（FR-077 状态机）。
- 失败时补打次数 MUST NOT 增加，任务置为 `failed`，供管理员重试。

---

## 可打印码与打印

### GET /api/v1/workstation/codes

**用途**：按产品查看本公司"已分配未打印"的码（FR-039）。

**查询参数**：`product_id`（必填）、`page` / `page_size`

**响应 200**

```json
{
  "total": 4820,
  "items": [{ "code_value": "A1B2C3D4", "product_id": 3, "product_name": "500ml 矿泉水" }],
  "screen_scope_note": "本公司全部工位共享，码不限定工位"
}
```

**约束**：可见范围是**整个公司**，MUST NOT 按 `workstation_id` 过滤（spec 澄清记录：码在公司内
全部工位共享）。

### GET /api/v1/workstation/codes/{code_value}

**用途**：扫码定位单个码（FR-040）。返回该码当前状态；若不可打印，返回对应错误码
（`CODE_ALREADY_PRINTED` / `CODE_VOIDED` / `WORKSTATION_DISABLED`）。

### POST /api/v1/workstation/print

**用途**：发起打印（预占），是"防重复打印"的入口（FR-041 / FR-042 / FR-043 / FR-044）。

**请求**

```json
{
  "workstation_id": 11,
  "code_values": ["A1B2C3D4", "E5F6G7H8"],
  "printer_name": "Zebra ZD421"
}
```

**响应 200**

```json
{
  "accepted": [
    {
      "code_value": "A1B2C3D4",
      "template_version_id": 88,
      "elements_json": { "paper_width_mm": 60, "paper_height_mm": 40, "elements": [] },
      "data": { "product_name": "500ml 矿泉水", "company_name": "华东分公司", "code_value": "A1B2C3D4", "batch_no": "ALL20261012003" }
    }
  ],
  "rejected": [{ "code_value": "E5F6G7H8", "error_code": "CODE_ALREADY_PRINTED" }]
}
```

**约束**
- 服务端在同一事务内将被接受的码由 `allocated` 置为 `printing`，写 `locked_at` 与
  `locked_workstation_id`（FR-041 / FR-042）。
- 并发请求同一码：仅一方成功，另一方返回 `409 CODE_LOCKED`（FR-044 / R2 行锁）。
- 逐码独立处理，部分失败 MUST NOT 回滚已接受的部分（FR-049 批量任务逐码独立）。
- `template_version_id` 由服务端按分配单携带的版本确定，**工位端 MUST NOT 自行选择模板**（FR-036）。
- 响应中的 `elements_json` 与 `data` 供工位端渲染；渲染规则两端共享（R6）。

### POST /api/v1/workstation/print/confirm

**用途**：确认打印结果，`printing` → `printed` 或回退 `allocated`（FR-045 / FR-046）。

**请求**

```json
{
  "workstation_id": 11,
  "results": [
    { "code_value": "A1B2C3D4", "outcome": "succeeded", "printer_name": "Zebra ZD421" },
    { "code_value": "E5F6G7H8", "outcome": "failed", "failure_reason": "打印机缺纸" }
  ]
}
```

- `outcome='succeeded'` → 码置 `printed`，`print_count+1`，写 `last_printed_workstation_id`，
  写 `PrintLog(print_type='first', result='succeeded')`（FR-050）。
- `outcome='failed'` → 码回退 `allocated`，清 `locked_*`，写 `PrintLog(result='failed')`；
  **MUST NOT 增加补打次数**（FR-046）。
- 服务端 MUST 校验确认请求来自持有锁的同一工位，否则 `409 CODE_LOCKED`。

---

## 超时回退（服务端行为，非接口）

码处于 `printing` 超过阈值（默认 5 分钟，可配置 `PRINT_LOCK_TIMEOUT_SECONDS`）仍未收到确认时，
由服务端定时任务将其回退为 `allocated`，清 `locked_*`，写
`PrintLog(result='timeout_reverted')` 与 `CodeEvent(event_type='timeout_reverted')`（FR-047 / FR-048）。

**已知风险（spec 假设，需在测试中显式覆盖）**：若本地打印服务实际已出纸但确认回执丢失，
回退后该码可被再次打印，会造成重复出纸。该情形 MUST 在 `PrintLog` 中留下
`timeout_reverted` 记录，供审计核查。

---

## 工位端轮询时序

```text
每 5 秒 ─┬─→ POST /workstation/heartbeat        （保活 + 在线判定）
         └─→ GET  /workstation/tasks            （领补打任务，通常为空）

正常打印 ──→ GET  /workstation/codes            （按产品查可打印码）
         └─→ POST /workstation/print            （预占 → printing）
         └─→ [本地打印服务出纸]
         └─→ POST /workstation/print/confirm    （printed 或回退 allocated）

补打     ──→ （管理员在后台发起，见 admin-api）
         └─→ GET  /workstation/tasks            （本工位领到任务）
         └─→ [本地打印服务出纸]
         └─→ POST /workstation/tasks/{id}/result
```
