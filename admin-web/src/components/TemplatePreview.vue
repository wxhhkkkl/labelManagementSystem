<template>
  <div class="preview">
    <div class="paper" :style="paperStyle">
      <div
        v-for="(item, index) in rendered"
        :key="index"
        :class="['el', item.element.type]"
        :style="item.style"
        :data-type="item.element.type"
        :data-field="item.element.field_name ?? ''"
        :title="item.clipped ? '该元素超出纸张，已裁剪' : undefined"
      >
        <!-- 图形元素在真实渲染时由二维码/条码库接管；预览里先标出占位与取值 -->
        <template v-if="item.element.type === 'qrcode' || item.element.type === 'barcode'">
          <span class="graphic">{{ graphicLabel(item) }}</span>
        </template>
        <template v-else>{{ item.text }}</template>
      </div>
    </div>

    <p v-if="clippedCount" class="warn">
      有 {{ clippedCount }} 个元素超出纸张被裁剪。超出部分按契约裁剪而不缩放，
      请调整坐标或纸张尺寸。
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import {
  clipToPaper,
  elementStyle,
  paperSize,
  resolveFieldValue,
  type TemplateDoc,
} from '../utils/templateRender'

const props = withDefaults(
  defineProps<{
    doc: TemplateDoc
    data?: Record<string, string>
    /** 预览缩放系数，仅影响显示，不写入模板 */
    zoom?: number
  }>(),
  { data: () => ({}), zoom: 1 },
)

const rendered = computed(() =>
  props.doc.elements.map((original) => {
    const { element, clipped } = clipToPaper(original, props.doc)
    const text =
      element.type === 'text'
        ? (element.content ?? '')
        : element.type === 'field'
          ? resolveFieldValue(element.field_name ?? '', props.data)
          : null
    return { element, clipped, text, style: elementStyle(element) }
  }),
)

const clippedCount = computed(() => rendered.value.filter((r) => r.clipped).length)

const paperStyle = computed(() => {
  const { width, height } = paperSize(props.doc)
  return {
    width: `${width * props.zoom}mm`,
    height: `${height * props.zoom}mm`,
  }
})

function graphicLabel(item: { element: TemplateDoc['elements'][number]; text: string | null }): string {
  return item.element.type === 'qrcode' ? '二维码' : '条码'
}
</script>

<style scoped>
.paper {
  position: relative;
  background: #fff;
  border: 1px solid var(--el-border-color);
  overflow: hidden;
  /* 预览与打印共用同一套毫米坐标，缩放只在这里叠加 */
  transform-origin: top left;
}
.el {
  white-space: nowrap;
}
.graphic {
  display: block;
  width: 100%;
  height: 100%;
  border: 1px dashed var(--el-border-color);
  font-size: 8px;
  color: var(--el-text-color-secondary);
  text-align: center;
  line-height: 1.2;
  padding-top: 4px;
  box-sizing: border-box;
}
.warn {
  margin-top: 8px;
  color: var(--el-color-warning);
  font-size: 12px;
}
</style>
