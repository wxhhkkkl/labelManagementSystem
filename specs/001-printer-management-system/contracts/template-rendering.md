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

- 打印接口响应中的 `data` 对象即为上表的取值结果，由服务端填充（见
  [workstation-api.md](./workstation-api.md)）。
- 取值缺失时（如码尚未分配故无 `batch_no`），该字段 MUST 渲染为空字符串，MUST NOT 渲染为
  `null` 或占位符。

## 5. 对齐与字体

- `align` ∈ `left` / `center` / `right`，默认 `left`；对齐相对元素自身边界。
- `text` 与 `field` 元素的高度由字号自动决定，MUST NOT 依赖自动换行；单行渲染。
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
