<template>
  <div class="editor">
    <div class="toolbar">
      <el-select v-model="newType" style="width: 140px">
        <el-option
          v-for="t in CREATABLE_TYPES"
          :key="t"
          :label="typeLabel(t)"
          :value="t"
        />
      </el-select>
      <el-button @click="onAdd">添加元素</el-button>

      <span class="paper-size">
        纸张
        <el-input-number v-model="width" :min="1" :max="500" size="small" @change="onPaperChange" />
        ×
        <el-input-number v-model="height" :min="1" :max="500" size="small" @change="onPaperChange" />
        mm
      </span>

      <el-slider v-model="zoom" :min="1" :max="4" :step="0.5" style="width: 140px" />
      <span class="zoom">{{ zoom }}×</span>
    </div>

    <el-alert
      v-for="problem in problems"
      :key="problem"
      :title="problem"
      type="warning"
      :closable="false"
      show-icon
      class="problem"
    />

    <div class="body">
      <!-- 画布：拖动元素改坐标。坐标是毫米，缩放只影响显示。 -->
      <div
        ref="canvas"
        class="canvas"
        :style="canvasStyle"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointerleave="onPointerUp"
      >
        <div
          v-for="(el, index) in localDoc.elements"
          :key="index"
          :class="['el', { selected: index === selected }]"
          :style="elementStyle(el)"
          @pointerdown="onPointerDown(index, $event)"
          @click="selected = index"
        >
          <template v-if="el.type === 'qrcode' || el.type === 'barcode'">
            <span class="graphic">{{ typeLabel(el.type) }}</span>
          </template>
          <template v-else-if="el.type === 'field'">
            {{ sampleValue(el) }}
          </template>
          <template v-else>{{ el.content }}</template>
        </div>

        <!-- 选中元素的坐标读数，拖不准时可直接改数字 -->
        <div v-if="selectedEl" class="coords">
          X <el-input-number v-model="selectedX" :min="0" size="small" style="width: 90px" />
          Y <el-input-number v-model="selectedY" :min="0" size="small" style="width: 90px" />
          <el-button size="small" type="danger" link @click="onRemove">删除</el-button>
        </div>
      </div>

      <!-- 元素列表：拖拽排序（vue-draggable-plus） -->
      <div class="list">
        <p class="list-title">元素（可拖拽排序，顺序即叠放次序）</p>
        <VueDraggable v-model="elements" :animation="150" handle=".handle" class="list-body">
          <div
            v-for="(el, index) in elements"
            :key="index"
            :class="['row', { selected: index === selected }]"
            @click="selected = index"
          >
            <span class="handle">☰</span>
            <span class="row-label">{{ typeLabel(el.type) }}</span>
            <span class="row-summary">{{ elementSummary(el) }}</span>
          </div>
        </VueDraggable>
      </div>
    </div>

    <div class="footer">
      <slot name="actions" :doc="localDoc" :problems="problems" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { VueDraggable } from 'vue-draggable-plus'
import { computed, ref, watch } from 'vue'

import {
  CREATABLE_TYPES,
  addElement,
  clampElement,
  elementSummary,
  moveElement,
  removeElement,
  typeLabel,
  updateElement,
  validateDocument,
} from '../utils/templateEditor'
import {
  CSS_PX_PER_MM,
  elementStyle,
  resolveFieldValue,
  type TemplateDoc,
  type TemplateElement,
} from '../utils/templateRender'

const props = defineProps<{ doc: TemplateDoc }>()
const emit = defineEmits<{ 'update:doc': [TemplateDoc] }>()

const localDoc = ref<TemplateDoc>(structuredClone(props.doc))
const selected = ref<number | null>(null)
const newType = ref<string>('qrcode')
const zoom = ref(2)

watch(
  () => props.doc,
  (next) => {
    localDoc.value = structuredClone(next)
    selected.value = null
  },
)

/** 元素列表是 localDoc.elements 的一个可写视图，供 vue-draggable-plus 排序。 */
const elements = computed<TemplateElement[]>({
  get: () => localDoc.value.elements,
  set: (value) => {
    localDoc.value = { ...localDoc.value, elements: value }
  },
})

const width = computed({
  get: () => localDoc.value.paper_width_mm,
  set: (value: number) => {
    localDoc.value = { ...localDoc.value, paper_width_mm: value }
  },
})

const height = computed({
  get: () => localDoc.value.paper_height_mm,
  set: (value: number) => {
    localDoc.value = { ...localDoc.value, paper_height_mm: value }
  },
})

const selectedEl = computed(() =>
  selected.value === null ? null : (localDoc.value.elements[selected.value] ?? null),
)

const selectedX = computed({
  get: () => selectedEl.value?.x ?? 0,
  set: (value: number) => {
    if (selected.value !== null) {
      localDoc.value = updateElement(localDoc.value, selected.value, { x: value })
    }
  },
})

const selectedY = computed({
  get: () => selectedEl.value?.y ?? 0,
  set: (value: number) => {
    if (selected.value !== null) {
      localDoc.value = updateElement(localDoc.value, selected.value, { y: value })
    }
  },
})

const problems = computed(() => validateDocument(localDoc.value))

const canvasStyle = computed(() => ({
  width: `${localDoc.value.paper_width_mm * zoom.value}mm`,
  height: `${localDoc.value.paper_height_mm * zoom.value}mm`,
}))

watch(
  localDoc,
  (value) => emit('update:doc', value),
  { deep: true },
)

/** 预览用的动态字段样例，让管理员看到"这里会印什么"。 */
function sampleValue(el: TemplateElement): string {
  const samples: Record<string, string> = {
    product_name: '500ml 矿泉水',
    company_name: '华东分公司',
    code_value: 'A1B2C3D4',
    batch_no: 'ALL202610120001',
  }
  return resolveFieldValue(el.field_name ?? '', samples)
}

function onAdd(): void {
  localDoc.value = addElement(localDoc.value, newType.value)
  selected.value = localDoc.value.elements.length - 1
}

function onRemove(): void {
  if (selected.value === null) return
  localDoc.value = removeElement(localDoc.value, selected.value)
  selected.value = null
}

function onPaperChange(): void {
  // 纸张变小后，原本在纸外的元素要夹回来，否则一改尺寸就出现一堆校验告警
  const doc = localDoc.value
  localDoc.value = { ...doc, elements: doc.elements.map((el) => clampElement(el, doc)) }
}

// ---- 画布拖动：按毫米换算位移，缩放不影响实际坐标 ----

interface DragState {
  index: number
  startX: number
  startY: number
  originX: number
  originY: number
}

let drag: DragState | null = null

function onPointerDown(index: number, event: PointerEvent): void {
  const el = localDoc.value.elements[index]
  if (!el) return
  selected.value = index
  drag = {
    index,
    startX: event.clientX,
    startY: event.clientY,
    originX: el.x,
    originY: el.y,
  }
  ;(event.target as HTMLElement).setPointerCapture?.(event.pointerId)
}

function onPointerMove(event: PointerEvent): void {
  if (!drag) return
  // 屏幕像素 → 毫米：先除以缩放，再除以基准换算
  const deltaXmm = (event.clientX - drag.startX) / zoom.value / CSS_PX_PER_MM
  const deltaYmm = (event.clientY - drag.startY) / zoom.value / CSS_PX_PER_MM

  const current = localDoc.value.elements[drag.index]
  if (!current) return
  const moved = moveElement(
    { ...current, x: drag.originX, y: drag.originY },
    deltaXmm,
    deltaYmm,
    localDoc.value,
  )
  localDoc.value = updateElement(localDoc.value, drag.index, { x: moved.x, y: moved.y })
}

function onPointerUp(): void {
  drag = null
}

defineExpose({ problems, doc: localDoc })
</script>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.paper-size {
  font-size: 13px;
}
.zoom {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.problem {
  margin: 0;
}
.body {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.canvas {
  position: relative;
  background: #fff;
  border: 1px solid var(--el-border-color);
  overflow: hidden;
  flex-shrink: 0;
}
.el {
  cursor: move;
  user-select: none;
  border: 1px dashed transparent;
}
.el.selected {
  border-color: var(--el-color-primary);
  background: rgba(64, 158, 255, 0.06);
}
.graphic {
  display: block;
  width: 100%;
  height: 100%;
  border: 1px dashed var(--el-border-color);
  font-size: 8px;
  color: var(--el-text-color-secondary);
  text-align: center;
  padding-top: 4px;
  box-sizing: border-box;
}
.coords {
  position: absolute;
  right: 4px;
  bottom: 4px;
  background: rgba(255, 255, 255, 0.9);
  padding: 4px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.list {
  flex: 1;
  min-width: 260px;
}
.list-title {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 0 0 6px;
}
.list-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.row.selected {
  border-color: var(--el-color-primary);
  background: rgba(64, 158, 255, 0.06);
}
.handle {
  cursor: grab;
  color: var(--el-text-color-secondary);
}
.row-label {
  font-weight: 600;
}
.row-summary {
  color: var(--el-text-color-secondary);
  margin-left: auto;
}
.footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}
</style>
