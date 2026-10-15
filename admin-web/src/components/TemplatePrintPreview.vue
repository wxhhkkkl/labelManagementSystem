<template>
  <div class="print-preview">
    <p class="hint">按标签毫米尺寸显示；当前为示例数据，实际打印时使用该码的产品、日期和流水号。</p>
    <TemplatePreview :doc="doc" :data="data" :zoom="zoom" />
  </div>
</template>

<script setup lang="ts">
import TemplatePreview from './TemplatePreview.vue'
import type { TemplateDoc } from '../utils/templateRender'

withDefaults(
  defineProps<{
    doc: TemplateDoc
    data?: Record<string, string>
    /** 打印预览通常按原尺寸看，缩放交给用户自己调 */
    zoom?: number
  }>(),
  { data: () => ({}), zoom: 1 },
)
</script>

<style scoped>
.print-preview {
  padding: 8px 0;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-bottom: 8px;
}
</style>
