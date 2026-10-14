<template>
  <div class="print-preview">
    <p class="hint">
      打印预览按与工位端相同的规则换算（同一份 contracts/template-rendering.md），
      所以这里看到的版面就是实际出纸的版面。
    </p>
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
