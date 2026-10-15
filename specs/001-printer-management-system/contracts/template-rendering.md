# 契约：模板渲染规则

**日期**：2026-10-12 | **规格**：FR-032 ~ FR-038 | **决策**：[research.md R6](../research.md)

本契约定义 `TemplateVersion.elements_json` 的**渲染语义**，使管理后台的模板预览与工位端的实际
打印产出一致的版面。

**为什么是契约而不是共享代码**：宪章原则六规定两端代码 MUST NOT 交叉引用。因此同一套渲染规则
由**两端各自独立实现**，以本文件为唯一事实来源。任何一端实现与本契约不符即为缺陷。

---

## 1. 坐标系与单位

- 模板以**毫米**为坐标单位，原点在纸张左上角，x 向右、y 向下。
- 元素坐标 `x` / `y` 表示元素**左上角**位置，单位为毫米（`DECIMAL(6,2)`）。
- 纸张尺寸由 `paper_width_mm` / `paper_height_mm` 定义（见 data-model.md）。
- 元素 MUST NOT 溢出纸张范围；渲染时超出部分 MUST 被裁剪而非缩放（避免改变已定义版面）。

## 2. 毫米 → 像素换算（两端必须一致）

```text
CSS_PX_PER_MM = 96 / 25.4        // ≈ 3.7795275591，固定基准，不随屏幕 DPI 变化
pixel = mm * CSS_PX_PER_MM
```

- **预览**（管理后台）：按上式换算到 CSS 像素，再乘以画布缩放系数 `zoom`（仅影响显示，不写入模板）。
- **打印**（工位端）：同样按 `CSS_PX_PER_MM` 换算成 CSS 像素构建打印页面，由 Electron 的
  `print({ silent: true, pageSize: { width, height } })` 以**毫米**指定纸张尺寸，
  **MUST NOT** 使用打印预览的默认缩放（`scaleFactor` 固定为 100）。

**关键点**：两端都先在 CSS 像素空间排版，再交给各自的渲染目标。`zoom`（预览）与 `scaleFactor`
（打印）是仅有的两个缩放入口，且打印侧 MUST 固定为 100%。

## 3. 元素类型

| type | 语义 | 必填属性 | 可选属性 |
|------|------|----------|----------|
| `qrcode` | 二维码 | `x`,`y`,`size` | `ec_level`（默认 `M`） |
| `barcode` | 一维条码 | `x`,`y`,`width`,`height` | `symbology`（默认 `code128`）、`show_text` |
| `text` | 静态文本 | `x`,`y`,`content`,`font_size` | `font_family`、`bold`、`align` |
| `field` | 动态字段 | `x`,`y`,`field_name`,`font_size` | `font_family`、`bold`、`align` |
| `date` | 日期 | `x`,`y`,`font_size` | `date_source`（`print` / `fixed`）、`date_format`、固定日期 `content` |
| `serial` | 每日流水号 | `x`,`y`,`font_size` | `prefix`、`suffix`、`serial_digits`（1～12，默认 6） |

- 属性名 MUST 使用 `snake_case`，与 `elements_json` 保持一致。
- `size` / `width` / `height` / `font_size` 单位均为毫米（字号亦为毫米高，**不是 pt**）。
- 未识别的 `type` MUST 导致渲染失败并显式报错，MUST NOT 静默跳过。

## 4. 动态字段取值

`type='field'` 的 `field_name` 取值与来源（FR-037）：

| field_name | 取值来源 |
|------------|----------|
| `product_name` | 该码所属产品的名称 |
| `company_name` | 该码归属公司的名称 |
| `code_value` | 码值本身 |
| `batch_no` | **该码所在分配单的 `order_no`**（不是导入批次号） |
| `print_date` | 该码首次打印任务使用的北京时间日期（`YYYY-MM-DD`），持久化保存 |
| `serial_no` | 该日服务端统一分配的整数流水号，补打复用原编号 |

- 打印接口响应中的 `data` 对象即为上表的取值结果，由服务端填充（见
  [workstation-api.md](./workstation-api.md)）。
- 取值缺失时（如码尚未分配故无 `batch_no`），该字段 MUST 渲染为空字符串，MUST NOT 渲染为
  `null` 或占位符。

## 5. 对齐与字体

- `align` ∈ `left` / `center` / `right`，默认 `left`；对齐相对元素自身边界。
- 文本类元素可设置 `width` 与 `height`；未指定宽度时兼容旧模板，使用 20mm；未指定高度时沿用字号高度。新建文本框默认高 4.2mm、字号 3mm。
- 默认单行；`text` 可启用 `multiline`，按照指定文本框尺寸换行并裁剪溢出内容。
- 字体缺失时回退顺序：模板声明字体 → `微软雅黑`（Microsoft YaHei）→ `monospace`。
  工位端与预览端 MUST 使用同一回退顺序。

## 6. 契约测试要求（宪章原则一）

两端各自持有针对本契约的测试，且 MUST 覆盖同一组用例：

| 用例 | 断言 |
|------|------|
| 换算基准 | `10mm` 换算为 `37.795275591px`（容差 `1e-6`） |
| 缩放入口 | 打印侧 `scaleFactor` 恒为 100%，不随系统 DPI 变化 |
| 元素越界 | 超出纸张的元素被裁剪，尺寸不改变 |
| 未知类型 | 抛错而非跳过 |
| 动态字段 | `batch_no` 取分配单号；缺失时渲染空串 |
| 字体回退 | 声明字体不可用时回退到雅黑 |

**验收方式**：同一份 `elements_json` 在管理后台预览与工位端打印（输出到 PDF）后，
逐元素比对位置与尺寸，偏差 MUST 在 ±0.5mm 内。该比对是 FR-038 打印预览功能的验收依据。

## 7. 内容、图形与日期流水号补充（2026-10-14）

- 二维码/条码的内容来源为 `field_name` 或静态 `content`；旧模板两项均为空时使用 `code_value`。二维码支持 L/M/Q/H 容错；条码支持 code128/code39/ean13。
- 两端独立使用同版本本地图形编码库生成 SVG；打印 HTML 包含图形，不依赖远程图形服务或占位容器。
- 管理预览缩放同时作用于元素位置、尺寸、字号和纸张。坐标与尺寸始终保存为毫米。超出纸张时由纸张边界裁剪，图形不得缩小。
- 日期支持 YYYY-MM-DD、YYYY/MM/DD、YYYYMMDD、YYYY年MM月DD日；固定日期使用有效的 ISO 日期 `content`。
- 每日流水号的计数范围为整个系统、所有工位；日期界线为 UTC+08:00 的午夜。后端事务中的原子计数与码行锁保证并发不重复。
- 首次打印预占时分配日期与编号，保存到 `print_identity`。补打或不确定是否出纸的超时重试沿用快照，不重新编号。
- 明确失败回退后释放码的快照，下次打印重新取当天编号；已消耗的编号不回收，因此可能有断号。不存在“无间隙编号”的承诺。
- 渲染端不读取本机日期或自行递增流水号；缺少必要快照时实际打印报错，避免打印空白日期或编号。
