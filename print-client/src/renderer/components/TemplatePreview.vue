<template>
  <div ref="host" class="template-preview">
    <p v-if="rendered.error" role="alert">{{ rendered.error }}</p>
    <div v-else :style="{width:`${mmToPx(doc.paper_width_mm)*scale}px`,height:`${mmToPx(doc.paper_height_mm)*scale}px`}">
      <div class="preview-paper" :style="{width:`${doc.paper_width_mm}mm`,height:`${doc.paper_height_mm}mm`,transform:`scale(${scale})`}">
        <div v-for="(item,i) in rendered.items" :key="i" :style="item.style">
          <div :style="item.contentStyle">
            <img v-if="item.image" :src="item.image" alt="二维码或条码" /><template v-else>{{ item.text }}</template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { renderTemplate, graphicDataUrl, mmToPx, type TemplateDoc } from '../../print-render/renderer'
const props = defineProps<{doc:TemplateDoc; data:Record<string,string>}>()
const host = ref<HTMLElement>()
const width = ref(220), height = ref(300)
const scale = computed(() => Math.min(width.value/mmToPx(props.doc.paper_width_mm),height.value/mmToPx(props.doc.paper_height_mm),2))
const rendered = computed(() => {
  try {return {error:'',items:renderTemplate(props.doc,props.data).map(item => ({...item,image:['qrcode','barcode'].includes(item.element.type) ? graphicDataUrl(item.element,props.data) : ''}))}}
  catch(e) {return {error:e instanceof Error ? e.message : '模板预览失败',items:[]}}
})
let observer:ResizeObserver
onMounted(() => {
  observer=new ResizeObserver(([entry]) => {width.value=Math.max(1,entry.contentRect.width-24);height.value=Math.max(1,entry.contentRect.height-24)})
  if(host.value) observer.observe(host.value)
})
onUnmounted(() => observer?.disconnect())
</script>
<style scoped>
.template-preview { flex:1;min-height:0;display:flex;align-items:center;justify-content:center;background:#edf3fc;padding:12px;overflow:hidden; }
.preview-paper { position:relative;transform-origin:top left;background:white;color:black;box-shadow:0 2px 12px #15355b22;overflow:hidden; }
img {width:100%;height:100%;object-fit:fill;}
</style>
