<template>
  <div class="editor">
    <div class="editor-toolbar">
      <div class="paper-size">
        <span>纸张（mm）</span
        ><el-input-number
          controls-position="right"
          v-model="width"
          :min="1"
          :max="500"
          :precision="2"
          aria-label="纸张宽度"
        />
        ×
        <el-input-number
          controls-position="right"
          v-model="height"
          :min="1"
          :max="500"
          :precision="2"
          aria-label="纸张高度"
        />
      </div>
      <div class="editor-tools">
        <el-button :disabled="!undoStack.length" @click="undo">撤销</el-button
        ><el-button :disabled="!redoStack.length" @click="redo">重做</el-button
        ><el-select v-model="zoom" aria-label="画布缩放"
          ><el-option
            v-for="z in [0.5, 1, 1.5, 2, 3, 4]"
            :key="z"
            :value="z"
            :label="`${z * 100}%`" /></el-select
        ><el-switch v-model="previewMode" active-text="打印预览" aria-label="打印预览" />
      </div>
    </div>
    <el-alert
      v-for="problem in problems"
      :key="problem"
      :title="problem"
      type="warning"
      :closable="false"
      show-icon
    />
    <div class="editor-layout">
      <aside class="element-palette">
        <h3>添加元素</h3>
        <div class="palette-grid">
          <el-button v-for="type in CREATABLE_TYPES" :key="type" @click="onAdd(type)">{{
            typeLabel(type)
          }}</el-button>
        </div>
        <h3>
          元素图层 <small>{{ localDoc.elements.length }}</small>
        </h3>
        <p class="panel-note">下方图层覆盖上方图层</p>
        <div class="layer-list">
          <button
            v-for="(el, index) in localDoc.elements"
            :key="index"
            :class="['layer-row', { selected: index === selected }]"
            @click="select(index)"
          >
            <strong>{{ index + 1 }} · {{ typeLabel(el.type) }}</strong
            ><span>{{ elementSummary(el) }}</span>
          </button>
        </div>
        <p v-if="!localDoc.elements.length" class="panel-note">点击上方类型添加元素</p>
        <div v-if="selectedEl" class="layer-actions">
          <el-button :disabled="selected === 0" @click="reorder(-1)">下移一层</el-button
          ><el-button :disabled="selected === localDoc.elements.length - 1" @click="reorder(1)"
            >上移一层</el-button
          ><el-button @click="duplicate">复制</el-button
          ><el-button type="danger" @click="onRemove">删除</el-button>
        </div>
      </aside>
      <section class="canvas-workspace">
        <div class="canvas-caption">
          <span>{{ localDoc.paper_width_mm }} × {{ localDoc.paper_height_mm }} mm</span
          ><span>{{
            previewMode ? '示例数据预览' : '拖动定位 · 方向键微调 0.1mm · Shift + 方向键 1mm'
          }}</span>
        </div>
        <div class="canvas-scroll">
          <div class="canvas-stage" :style="stageStyle">
            <div
              ref="canvas"
              class="canvas"
              :class="{ 'preview-mode': previewMode }"
              :style="canvasStyle"
              tabindex="0"
              role="region"
              aria-label="标签画布"
              @pointermove="onPointerMove"
              @pointerup="finishDrag"
              @pointercancel="cancelDrag"
              @lostpointercapture="finishDrag"
              @keydown="onKeyDown"
              @pointerdown.self="selected = null"
            >
              <div
                v-for="(el, index) in localDoc.elements"
                :key="index"
                :class="['el', { selected: index === selected && !previewMode }]"
                :style="elementStyle(el)"
                :data-element-index="index"
                @pointerdown.stop.prevent="onPointerDown(index, $event)"
              >
                <div class="el-content" :style="elementContentStyle(el)">
                  <template v-if="el.type === 'qrcode' || el.type === 'barcode'"
                    ><img
                      v-if="graphic(el).url"
                      :src="graphic(el).url"
                      :alt="typeLabel(el.type)"
                      draggable="false"
                    /><span v-else class="graphic-error">{{ graphic(el).error }}</span></template
                  >
                  <template v-else>{{ elementText(el, sampleData) }}</template>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="sample-data">
          <h3>预览数据 <small>仅影响预览</small></h3>
          <div>
            <label v-for="field in FIELDS" :key="field.value"
              >{{ field.label
              }}<el-input v-model="sampleData[field.value]" :aria-label="`预览${field.label}`"
            /></label>
          </div>
        </div>
      </section>
      <aside class="property-panel">
        <h3>
          元素属性 <small v-if="selectedEl">{{ typeLabel(selectedEl.type) }}</small>
        </h3>
        <p v-if="!selectedEl" class="panel-note">点击画布或图层中的元素进行编辑</p>
        <template v-else>
          <div class="coords property-grid">
            <label
              >X（mm）<el-input-number
                controls-position="right"
                v-model="selectedX"
                :min="0"
                :max="maxX"
                :step="0.1"
                :precision="2"
                aria-label="元素 X 坐标" /></label
            ><label
              >Y（mm）<el-input-number
                controls-position="right"
                v-model="selectedY"
                :min="0"
                :max="maxY"
                :step="0.1"
                :precision="2"
                aria-label="元素 Y 坐标"
            /></label>
          </div>
          <label
            >旋转角度<el-select
              :model-value="selectedEl.rotate ?? 0"
              aria-label="元素旋转角度"
              @update:model-value="setRotation"
              ><el-option
                v-for="angle in [0, 90, 180, 270]"
                :key="angle"
                :value="angle"
                :label="`${angle}°`" /></el-select
          ></label>
          <label v-if="selectedEl.type === 'qrcode'"
            >尺寸（mm）<el-input-number
              controls-position="right"
              :model-value="selectedEl.size ?? 15"
              :min="0.1"
              :max="Math.min(width, height)"
              :step="0.1"
              :precision="2"
              @update:model-value="setNumber('size', $event)"
          /></label>
          <div v-else class="property-grid">
            <label
              >宽度（mm）<el-input-number
                controls-position="right"
                :model-value="selectedEl.width ?? 20"
                :min="0.1"
                :max="width"
                :step="0.1"
                :precision="2"
                @update:model-value="setNumber('width', $event)" /></label
            ><label
              >高度（mm）<el-input-number
                controls-position="right"
                :model-value="selectedEl.height ?? selectedEl.font_size ?? 4.2"
                :min="0.1"
                :max="height"
                :step="0.1"
                :precision="2"
                @update:model-value="setNumber('height', $event)"
            /></label>
          </div>
          <div class="align-tools">
            <el-button
              v-for="alignment in ALIGNMENTS"
              :key="alignment.value"
              size="small"
              @click="alignElement(alignment.value)"
              >{{ alignment.label }}</el-button
            >
          </div>
          <template v-if="isGraphic">
            <label
              >内容来源<el-select :model-value="graphicSource" @update:model-value="setSource"
                ><el-option label="动态字段" value="field" /><el-option
                  label="固定内容"
                  value="fixed" /></el-select
            ></label>
            <label v-if="graphicSource === 'field'"
              >绑定字段<el-select
                :model-value="selectedEl.field_name ?? 'code_value'"
                @update:model-value="setAttr('field_name', $event)"
                ><el-option
                  v-for="field in FIELDS"
                  :key="field.value"
                  :label="field.label"
                  :value="field.value" /></el-select
            ></label>
            <label v-else
              >编码内容<el-input
                :model-value="selectedEl.content ?? ''"
                placeholder="请输入编码内容"
                @update:model-value="setAttr('content', $event)"
            /></label>
            <label v-if="selectedEl.type === 'qrcode'"
              >容错等级<el-select
                :model-value="selectedEl.ec_level ?? 'M'"
                @update:model-value="setAttr('ec_level', $event)"
                ><el-option
                  v-for="level in ['L', 'M', 'Q', 'H']"
                  :key="level"
                  :label="level"
                  :value="level" /></el-select
            ></label>
            <template v-else
              ><label
                >条码制式<el-select
                  :model-value="selectedEl.symbology ?? 'code128'"
                  @update:model-value="setAttr('symbology', $event)"
                  ><el-option
                    v-for="kind in ['code128', 'code39', 'ean13']"
                    :key="kind"
                    :label="kind.toUpperCase()"
                    :value="kind" /></el-select></label
              ><el-checkbox
                :model-value="selectedEl.show_text ?? false"
                @update:model-value="setAttr('show_text', $event)"
                >显示条码文字</el-checkbox
              ></template
            >
          </template>
          <template v-else>
            <label v-if="selectedEl.type === 'text'"
              >文本内容<el-input
                :model-value="selectedEl.content ?? ''"
                type="textarea"
                :rows="3"
                placeholder="请输入文本内容"
                @update:model-value="setAttr('content', $event)"
            /></label>
            <label v-if="selectedEl.type === 'field'"
              >绑定字段<el-select
                :model-value="selectedEl.field_name"
                @update:model-value="setAttr('field_name', $event)"
                ><el-option
                  v-for="field in FIELDS"
                  :key="field.value"
                  :label="field.label"
                  :value="field.value" /></el-select
            ></label>
            <template v-if="selectedEl.type === 'date'"
              ><label
                >日期来源<el-select
                  :model-value="selectedEl.date_source ?? 'print'"
                  @update:model-value="setAttr('date_source', $event)"
                  ><el-option label="首次打印日期" value="print" /><el-option
                    label="固定日期"
                    value="fixed" /></el-select></label
              ><label v-if="selectedEl.date_source === 'fixed'"
                >固定日期<el-date-picker
                  :model-value="selectedEl.content"
                  type="date"
                  value-format="YYYY-MM-DD"
                  @update:model-value="setAttr('content', $event ?? '')" /></label
              ><label
                >日期格式<el-select
                  :model-value="selectedEl.date_format ?? 'YYYY-MM-DD'"
                  @update:model-value="setAttr('date_format', $event)"
                  ><el-option
                    v-for="format in [
                      'YYYY-MM-DD',
                      'YY-MM-DD',
                      'YYYY/MM/DD',
                      'YYYYMMDD',
                      'YYYY年MM月DD日',
                    ]"
                    :key="format"
                    :label="format"
                    :value="format" /></el-select
              ></label>
              <p class="panel-note">首次打印日期由后台保存，补打不改变。</p></template
            >
            <template v-if="selectedEl.type === 'serial'"
              ><label
                >前缀<el-input
                  :model-value="selectedEl.prefix ?? ''"
                  maxlength="64"
                  @update:model-value="setAttr('prefix', $event)" /></label
              ><label
                >数字位数（不足补零）<el-input-number
                  controls-position="right"
                  :model-value="selectedEl.serial_digits ?? 6"
                  :min="1"
                  :max="12"
                  @update:model-value="setNumber('serial_digits', $event)" /></label
              ><label
                >后缀<el-input
                  :model-value="selectedEl.suffix ?? ''"
                  maxlength="64"
                  @update:model-value="setAttr('suffix', $event)"
              /></label>
              <p class="panel-note">每天从 1 开始，全工位共用。补打沿用原编号。</p></template
            >
            <label
              >字号（mm）<el-input-number
                controls-position="right"
                :model-value="selectedEl.font_size ?? 3"
                :min="0.5"
                :max="50"
                :step="0.1"
                :precision="2"
                @update:model-value="setNumber('font_size', $event)"
            /></label>
            <label
              >字体<el-select
                :model-value="selectedEl.font_family ?? 'Microsoft YaHei'"
                @update:model-value="setAttr('font_family', $event)"
                ><el-option
                  v-for="font in ['Microsoft YaHei', 'SimSun', 'Arial', 'monospace']"
                  :key="font"
                  :label="font"
                  :value="font" /></el-select
            ></label>
            <label
              >文字对齐<el-select
                :model-value="selectedEl.align ?? 'left'"
                @update:model-value="setAttr('align', $event)"
                ><el-option label="左对齐" value="left" /><el-option
                  label="居中"
                  value="center" /><el-option label="右对齐" value="right" /></el-select
            ></label>
            <el-checkbox
              aria-label="加粗"
              :model-value="selectedEl.bold ?? false"
              @update:model-value="setAttr('bold', $event)"
              >加粗</el-checkbox
            ><el-checkbox
              aria-label="允许换行"
              v-if="selectedEl.type === 'text'"
              :model-value="selectedEl.multiline ?? false"
              @update:model-value="setAttr('multiline', $event)"
              >允许换行</el-checkbox
            >
          </template>
        </template>
      </aside>
    </div>
    <slot name="actions" :doc="localDoc" :problems="problems" />
  </div>
</template>
<script setup lang="ts">
import { computed, ref, toRaw, watch } from 'vue'
import {
  CREATABLE_TYPES,
  addElement,
  clampElement,
  cloneTemplateDoc,
  elementSummary,
  moveElement,
  removeElement,
  rotateElement,
  typeLabel,
  updateElement,
  validateDocument,
} from '../utils/templateEditor'
import {
  CSS_PX_PER_MM,
  elementBoundsMm,
  elementContentStyle,
  elementStyle,
  elementText,
  graphicDataUrl,
  type TemplateDoc,
  type TemplateElement,
} from '../utils/templateRender'
const props = defineProps<{ doc: TemplateDoc }>()
const emit = defineEmits<{ 'update:doc': [TemplateDoc] }>()
const localDoc = ref(cloneTemplateDoc(props.doc))
const canvas = ref<HTMLElement | null>(null)
const selected = ref<number | null>(null)
const zoom = ref(2)
const previewMode = ref(false)
const undoStack = ref<TemplateDoc[]>([])
const redoStack = ref<TemplateDoc[]>([])
const FIELDS = [
  { value: 'code_value', label: '码值' },
  { value: 'product_name', label: '产品名称' },
  { value: 'company_name', label: '公司名称' },
  { value: 'batch_no', label: '分配单号' },
  { value: 'production_batch_no', label: '生产批号' },
  { value: 'print_date', label: '首次打印日期' },
  { value: 'serial_no', label: '每日流水号' },
]
const ALIGNMENTS = [
  { value: 'left', label: '靠左' },
  { value: 'center-x', label: '水平居中' },
  { value: 'right', label: '靠右' },
  { value: 'top', label: '靠上' },
  { value: 'center-y', label: '垂直居中' },
  { value: 'bottom', label: '靠下' },
]
const sampleData = ref<Record<string, string>>({
  code_value: 'A1B2C3D4',
  product_name: '标准产品 A',
  company_name: '示例公司',
  batch_no: 'ALL202610140001',
  production_batch_no: '22PT510020DPHXQ1V',
  print_date: '2026-10-14',
  serial_no: '1',
})
const selectedEl = computed(() =>
  selected.value === null ? null : (localDoc.value.elements[selected.value] ?? null),
)
const isGraphic = computed(() => ['qrcode', 'barcode'].includes(selectedEl.value?.type ?? ''))
const graphicSource = computed(() =>
  selectedEl.value?.field_name ||
  selectedEl.value?.content === undefined ||
  selectedEl.value?.content === null
    ? 'field'
    : 'fixed',
)
const maxX = computed(() =>
  Math.max(
    0,
    localDoc.value.paper_width_mm -
      (selectedEl.value ? elementBoundsMm(selectedEl.value).width : 0),
  ),
)
const maxY = computed(() =>
  Math.max(
    0,
    localDoc.value.paper_height_mm -
      (selectedEl.value ? elementBoundsMm(selectedEl.value).height : 0),
  ),
)
function remember(doc: TemplateDoc) {
  undoStack.value.push(cloneTemplateDoc(doc))
  if (undoStack.value.length > 80) undoStack.value.shift()
  redoStack.value = []
}
function commit(doc: TemplateDoc) {
  if (JSON.stringify(doc) === JSON.stringify(localDoc.value)) return
  remember(localDoc.value)
  localDoc.value = doc
}
watch(
  () => props.doc,
  (next) => {
    if (toRaw(next) === toRaw(localDoc.value)) return
    localDoc.value = cloneTemplateDoc(next)
    selected.value = null
    undoStack.value = []
    redoStack.value = []
  },
)
watch(localDoc, (value) => emit('update:doc', value), { deep: true })
function setAttr(key: string, value: unknown) {
  if (selected.value !== null)
    commit(updateElement(localDoc.value, selected.value, { [key]: value }))
}
function setNumber(key: string, value: number | null | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return
  if (key === 'font_size' && selected.value !== null && selectedEl.value) {
    commit(
      updateElement(localDoc.value, selected.value, {
        font_size: value,
        height: Math.max(selectedEl.value.height ?? 0, Math.round(value * 1.2 * 100) / 100),
      }),
    )
  } else {
    setAttr(key, value)
  }
}
const selectedX = computed({
  get: () => selectedEl.value?.x ?? 0,
  set: (v: number | null | undefined) => setNumber('x', v),
})
const selectedY = computed({
  get: () => selectedEl.value?.y ?? 0,
  set: (v: number | null | undefined) => setNumber('y', v),
})
function resizePaper(key: 'paper_width_mm' | 'paper_height_mm', value: number | null | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return
  const doc = { ...localDoc.value, [key]: value }
  commit({ ...doc, elements: doc.elements.map((el) => clampElement(el, doc)) })
}
const width = computed({
  get: () => localDoc.value.paper_width_mm,
  set: (v: number | null | undefined) => resizePaper('paper_width_mm', v),
})
const height = computed({
  get: () => localDoc.value.paper_height_mm,
  set: (v: number | null | undefined) => resizePaper('paper_height_mm', v),
})
const problems = computed(() => validateDocument(localDoc.value))
const canvasStyle = computed(() => ({
  width: `${width.value}mm`,
  height: `${height.value}mm`,
  transform: `scale(${zoom.value})`,
  backgroundSize: `${5 * CSS_PX_PER_MM}px ${5 * CSS_PX_PER_MM}px`,
}))
const stageStyle = computed(() => ({
  width: `${width.value * CSS_PX_PER_MM * zoom.value}px`,
  height: `${height.value * CSS_PX_PER_MM * zoom.value}px`,
}))
function select(index: number) {
  selected.value = index
  previewMode.value = false
}
function onAdd(type: string) {
  previewMode.value = false
  commit(addElement(localDoc.value, type))
  selected.value = localDoc.value.elements.length - 1
}
function onRemove() {
  if (selected.value === null) return
  commit(removeElement(localDoc.value, selected.value))
  selected.value = null
}
function duplicate() {
  if (!selectedEl.value) return
  const copy = cloneTemplateDoc({ ...localDoc.value, elements: [selectedEl.value] }).elements[0]
  commit({
    ...localDoc.value,
    elements: [
      ...localDoc.value.elements,
      clampElement({ ...copy, x: copy.x + 2, y: copy.y + 2 }, localDoc.value),
    ],
  })
  selected.value = localDoc.value.elements.length - 1
}
function reorder(delta: number) {
  if (selected.value === null) return
  const from = selected.value,
    to = from + delta
  if (to < 0 || to >= localDoc.value.elements.length) return
  const elements = [...localDoc.value.elements]
  const [el] = elements.splice(from, 1)
  elements.splice(to, 0, el)
  commit({ ...localDoc.value, elements })
  selected.value = to
}
function setRotation(angle: number) {
  if (selected.value === null) return
  commit(rotateElement(localDoc.value, selected.value, angle))
}
function setSource(source: string) {
  if (selected.value === null) return
  commit(
    updateElement(
      localDoc.value,
      selected.value,
      source === 'field'
        ? { field_name: 'code_value', content: undefined }
        : { field_name: undefined, content: '内容' },
    ),
  )
}
function alignElement(direction: string) {
  if (!selectedEl.value) return
  const values: Record<string, Partial<TemplateElement>> = {
    left: { x: 0 },
    'center-x': { x: maxX.value / 2 },
    right: { x: maxX.value },
    top: { y: 0 },
    'center-y': { y: maxY.value / 2 },
    bottom: { y: maxY.value },
  }
  if (selected.value !== null)
    commit(updateElement(localDoc.value, selected.value, values[direction]))
}
function undo() {
  const doc = undoStack.value.pop()
  if (!doc) return
  redoStack.value.push(cloneTemplateDoc(localDoc.value))
  localDoc.value = doc
  selected.value = null
}
function redo() {
  const doc = redoStack.value.pop()
  if (!doc) return
  undoStack.value.push(cloneTemplateDoc(localDoc.value))
  localDoc.value = doc
  selected.value = null
}
function graphic(el: TemplateElement) {
  try {
    return { url: graphicDataUrl(el, sampleData.value), error: '' }
  } catch (e) {
    return { url: '', error: e instanceof Error ? e.message : '编码失败' }
  }
}
interface Drag {
  index: number
  startX: number
  startY: number
  originX: number
  originY: number
  before: TemplateDoc
  pointerId: number
}
let drag: Drag | null = null
function onPointerDown(index: number, event: PointerEvent) {
  if (previewMode.value || event.button !== 0) return
  selected.value = index
  const el = localDoc.value.elements[index]
  drag = {
    index,
    startX: event.clientX,
    startY: event.clientY,
    originX: el.x,
    originY: el.y,
    before: cloneTemplateDoc(localDoc.value),
    pointerId: event.pointerId,
  }
  canvas.value?.focus({ preventScroll: true })
  canvas.value?.setPointerCapture(event.pointerId)
}
function onPointerMove(event: PointerEvent) {
  if (!drag || event.pointerId !== drag.pointerId) return
  const el = localDoc.value.elements[drag.index]
  const moved = moveElement(
    { ...el, x: drag.originX, y: drag.originY },
    (event.clientX - drag.startX) / zoom.value / CSS_PX_PER_MM,
    (event.clientY - drag.startY) / zoom.value / CSS_PX_PER_MM,
    localDoc.value,
  )
  localDoc.value = updateElement(localDoc.value, drag.index, { x: moved.x, y: moved.y })
}
function finishDrag() {
  if (!drag) return
  const current = drag
  drag = null
  if (JSON.stringify(current.before) !== JSON.stringify(localDoc.value)) remember(current.before)
  if (canvas.value?.hasPointerCapture(current.pointerId))
    canvas.value.releasePointerCapture(current.pointerId)
}
function cancelDrag() {
  if (!drag) return
  const before = drag.before
  drag = null
  localDoc.value = before
}
function onKeyDown(event: KeyboardEvent) {
  if (previewMode.value) return
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
    event.preventDefault()
    event.shiftKey ? redo() : undo()
    return
  }
  if (event.key === 'Escape') {
    selected.value = null
    return
  }
  if (!selectedEl.value) return
  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault()
    onRemove()
    return
  }
  const delta = event.shiftKey ? 1 : 0.1
  const directions: Record<string, [number, number]> = {
    ArrowLeft: [-delta, 0],
    ArrowRight: [delta, 0],
    ArrowUp: [0, -delta],
    ArrowDown: [0, delta],
  }
  if (directions[event.key]) {
    event.preventDefault()
    const [dx, dy] = directions[event.key]
    if (selected.value !== null)
      commit(
        updateElement(localDoc.value, selected.value, {
          x: selectedEl.value.x + dx,
          y: selectedEl.value.y + dy,
        }),
      )
  }
}
defineExpose({ problems, doc: localDoc })
</script>
<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.editor-toolbar,
.paper-size,
.editor-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.editor-toolbar {
  justify-content: space-between;
  padding: 14px;
  background: #f4f7fc;
  border-radius: 10px;
}
.paper-size {
  font-size: 12px;
}
.paper-size .el-input-number {
  width: 112px;
}
.editor-tools .el-select {
  width: 100px;
}
.editor-layout {
  display: grid;
  grid-template-columns: 180px minmax(280px, 1fr) 260px;
  gap: 14px;
  align-items: start;
}
.element-palette,
.property-panel {
  padding: 16px;
  border: 1px solid var(--lms-line);
  border-radius: 10px;
  background: #fff;
  min-width: 0;
}
h3 {
  margin: 0 0 12px;
  font-size: 14px;
}
h3 small {
  font-size: 11px;
  font-weight: 400;
  color: var(--lms-muted);
  margin-left: 5px;
}
.palette-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 24px;
}
.palette-grid .el-button {
  margin: 0;
  font-size: 12px;
  padding: 8px;
}
.panel-note {
  font-size: 12px;
  color: var(--lms-muted);
  line-height: 1.7;
}
.layer-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.layer-row {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid var(--lms-line);
  border-radius: 7px;
  background: #fff;
  padding: 9px;
  cursor: pointer;
  color: var(--lms-ink);
}
.layer-row.selected {
  background: var(--lms-soft);
  border-color: var(--lms-blue);
}
.layer-row strong {
  display: block;
  font-size: 12px;
}
.layer-row span {
  display: block;
  font-size: 11px;
  color: var(--lms-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.layer-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 7px;
  margin-top: 12px;
}
.layer-actions .el-button {
  margin: 0;
  font-size: 11px;
  padding: 6px;
}
.canvas-workspace {
  min-width: 0;
}
.canvas-caption {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: var(--lms-muted);
  margin-bottom: 10px;
}
.canvas-scroll {
  overflow: auto;
  min-height: 360px;
  max-height: 620px;
  padding: 24px;
  background: #eaf0f8;
  border: 1px solid var(--lms-line);
  border-radius: 10px;
}
.canvas-stage {
  position: relative;
  margin: auto;
}
.canvas {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: top left;
  background-color: #fff;
  background-image:
    linear-gradient(#2563eb0b 1px, transparent 1px),
    linear-gradient(90deg, #2563eb0b 1px, transparent 1px);
  box-shadow: 0 2px 10px #172b4d12;
  overflow: hidden;
  touch-action: none;
  outline: none;
}
.canvas:focus-visible {
  box-shadow: 0 0 0 1px var(--lms-blue);
}
.canvas.preview-mode {
  background-image: none;
}
.el {
  cursor: move;
  user-select: none;
  outline: 1px solid transparent;
  outline-offset: 0;
}
.el.selected {
  outline-color: var(--lms-blue);
  background: #2563eb08;
}
.el img {
  width: 100%;
  height: 100%;
  object-fit: fill;
  pointer-events: none;
  display: block;
}
.graphic-error {
  font-size: 2.5mm;
  color: #d64550;
}
.sample-data {
  padding: 16px 0;
}
.sample-data > div {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.sample-data label {
  font-size: 11px;
  color: var(--lms-muted);
}
.sample-data .el-input {
  margin-top: 5px;
}
.property-panel label {
  display: block;
  font-size: 12px;
  margin: 14px 0;
}
.property-panel .el-input,
.property-panel .el-select,
.property-panel .el-input-number,
.property-panel .el-date-editor {
  width: 100%;
  margin-top: 6px;
}
.property-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.align-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 14px 0;
}
.align-tools .el-button {
  margin: 0;
  font-size: 11px;
  padding: 6px;
}
.property-panel .el-checkbox {
  margin-right: 12px;
}
@media (max-width: 1000px) {
  .editor-layout {
    grid-template-columns: 160px minmax(220px, 1fr);
  }
  .property-panel {
    grid-column: 1/-1;
  }
  .property-panel > label {
    max-width: 440px;
  }
  .property-grid {
    max-width: 440px;
  }
}
@media (max-width: 600px) {
  .editor-layout {
    display: flex;
    flex-direction: column;
  }
  .element-palette,
  .property-panel,
  .canvas-workspace {
    width: 100%;
  }
  .palette-grid {
    grid-template-columns: repeat(3, 1fr);
  }
  .canvas-scroll {
    min-height: 280px;
    padding: 16px;
  }
  .sample-data > div {
    grid-template-columns: 1fr;
  }
}
</style>
