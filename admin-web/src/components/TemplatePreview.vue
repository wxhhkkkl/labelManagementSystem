<template>
  <div class="preview">
    <el-alert v-if="errors.length" type="error" :closable="false" :title="errors.join('；')" />
    <div class="preview-scroll">
      <div class="paper-stage" :style="stageStyle">
        <div class="paper" :style="paperStyle">
          <div
            v-for="(item, index) in rendered"
            :key="index"
            :class="['el', item.element.type]"
            :style="item.style"
            :data-type="item.element.type"
            :data-field="item.element.field_name ?? ''"
          >
            <div class="el-content" :style="item.contentStyle">
              <img
                v-if="item.url"
                :src="item.url"
                :alt="item.element.type === 'qrcode' ? '二维码' : '条码'"
              />
              <template v-else>{{ item.text }}</template>
            </div>
          </div>
        </div>
      </div>
    </div>
    <p v-if="clippedCount" class="warn">
      有 {{ clippedCount }} 个元素超出纸张，超出部分将被裁剪，请调整位置或尺寸。
    </p>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import {
  CSS_PX_PER_MM,
  clipToPaper,
  elementContentStyle,
  elementStyle,
  elementText,
  graphicDataUrl,
  type TemplateDoc,
} from '../utils/templateRender'
const props = withDefaults(
  defineProps<{ doc: TemplateDoc; data?: Record<string, string>; zoom?: number }>(),
  { data: () => ({}), zoom: 1 },
)
const rendered = computed(() =>
  props.doc.elements.map((original) => {
    const { element, clipped } = clipToPaper(original, props.doc)
    let url = '',
      error = ''
    if (['qrcode', 'barcode'].includes(element.type)) {
      try {
        url = graphicDataUrl(original, props.data)
      } catch (e) {
        error = e instanceof Error ? e.message : '编码失败'
      }
    }
    return {
      element,
      clipped,
      style: elementStyle(original),
      contentStyle: elementContentStyle(original),
      text: elementText(original, props.data),
      url,
      error,
    }
  }),
)
const errors = computed(() => rendered.value.map((item) => item.error).filter(Boolean))
const clippedCount = computed(() => rendered.value.filter((item) => item.clipped).length)
const paperStyle = computed(() => ({
  width: `${props.doc.paper_width_mm}mm`,
  height: `${props.doc.paper_height_mm}mm`,
  transform: `scale(${props.zoom})`,
}))
const stageStyle = computed(() => ({
  width: `${props.doc.paper_width_mm * CSS_PX_PER_MM * props.zoom}px`,
  height: `${props.doc.paper_height_mm * CSS_PX_PER_MM * props.zoom}px`,
}))
</script>
<style scoped>
.preview-scroll {
  overflow: auto;
  padding: 12px;
  background: #f4f7fc;
  border-radius: 10px;
}
.paper-stage {
  position: relative;
}
.paper {
  position: absolute;
  inset: 0 auto auto 0;
  background: #fff;
  overflow: hidden;
  transform-origin: top left;
  box-shadow: 0 1px 6px #172b4d15;
}
.el img {
  width: 100%;
  height: 100%;
  object-fit: fill;
  display: block;
}
.warn {
  margin-top: 8px;
  color: var(--el-color-warning);
  font-size: 12px;
}
</style>
