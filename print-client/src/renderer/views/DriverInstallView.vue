<template>
  <section class="driver-page">
    <header class="driver-heading"><div><h1>打印机驱动安装</h1><p>按品牌下载驱动安装包，跟随六个步骤完成安装。</p></div><el-tag>Windows 工位电脑</el-tag></header>
    <div class="driver-layout">
      <nav class="driver-models" aria-label="打印机品牌">
        <button v-for="guide in printerGuides" :key="guide.id" :class="{selected:guide.id===selected}" @click="selected=guide.id"><strong>{{ guide.name }}</strong><span>{{ guide.model }}</span></button>
      </nav>
      <article class="driver-guide">
        <div class="driver-title"><div><p class="eyebrow">安装教程</p><h2>{{ current.name }}</h2><p>适用型号：{{ current.model }}</p></div><a class="download-button" :href="current.download" target="_blank" rel="noopener noreferrer">下载驱动 ↗</a></div>
        <p class="download-description">{{ current.name }} 共用一个驱动安装包，适用于 {{ current.model }}。安装前请连接打印机并接通电源。</p>
        <ol class="install-steps">
          <li><h3>下载驱动</h3><p>点击“下载驱动”，下载 {{ current.name }} 驱动安装包到电脑。</p></li>
          <li><h3>解压缩到本地</h3><p>将下载的压缩包完整解压到本地文件夹，再打开解压后的文件夹。</p></li>
          <li><h3>点击 DriverWizard.exe</h3><p>双击文件夹中的 DriverWizard.exe，启动驱动安装向导。Windows 提示需要权限时，按提示确认。</p></li>
          <li><h3>识别出对应的打印机</h3><p>{{ current.detail }} 若未识别到设备，请检查电源和数据线后重新识别。</p></li>
          <li><h3>安装驱动</h3><p>确认识别出的打印机，按照向导提示点击“下一步”并安装驱动，等待安装完成。</p></li>
          <li><h3>完成</h3><p>点击“完成”关闭安装向导。回到“工位状态”刷新列表，选择打印机后即可测试打印。</p></li>
        </ol>
        <div class="driver-bottom"><a :href="current.support" target="_blank" rel="noopener noreferrer">{{ current.supportLabel }} ↗</a><el-button type="primary" @click="$emit('settings')">{{ bound ? '前往工位状态' : '登录后选择打印机' }}</el-button></div>
        <details class="driver-faq"><summary>安装后找不到打印机、偏移或连续出纸怎么办？</summary><p>找不到设备：检查电源和数据线，在 Windows 中确认打印机可用，再刷新工位状态；必要时重新打开工位软件。没有出纸：检查驱动型号、端口、队列暂停/脱机状态。偏移或连续出纸：核对纸张宽高、方向和介质类型，按说明书重新校准；不要通过缩放模板补偿纸张配置错误。</p></details>
      </article>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { printerGuides } from '../../printerSupport'
defineProps<{bound:boolean}>()
defineEmits<{settings:[]}>()
const selected=ref<string>(printerGuides[0].id)
const current=computed(()=>printerGuides.find(guide=>guide.id===selected.value) ?? printerGuides[0])
</script>
<style scoped>
.driver-page {display:flex;flex:1;flex-direction:column;min-height:0;}
.driver-heading,.driver-title,.driver-bottom {display:flex;justify-content:space-between;align-items:center;gap:16px;}
.driver-heading {margin-bottom:16px;flex-shrink:0;}
h1 {margin:0;font-size:23px;} .driver-heading p,.driver-title p {margin:4px 0;color:var(--lms-muted);font-size:13px;}
.driver-layout {display:grid;grid-template-columns:220px minmax(0,1fr);gap:16px;min-height:0;flex:1;}
.driver-models {display:flex;flex-direction:column;gap:10px;overflow:auto;}
.driver-models button {text-align:left;padding:16px;border:1px solid var(--lms-line);border-radius:10px;background:white;color:var(--lms-ink);cursor:pointer;}
.driver-models button.selected {border-color:var(--lms-blue);background:var(--lms-soft);}
.driver-models span {display:block;font-size:11px;color:var(--lms-muted);margin-top:6px;}
.driver-models strong {font-size:14px;}
.driver-guide {overflow:auto;min-height:0;background:white;border:1px solid var(--lms-line);border-radius:12px;padding:24px;}
h2 {margin:0;font-size:21px;} a {color:var(--lms-blue);text-decoration:none;}
.download-button {background:var(--lms-blue);color:white;padding:10px 18px;border-radius:8px;white-space:nowrap;}
.download-description {padding:12px;background:var(--lms-soft);border-radius:8px;font-size:12px;color:var(--lms-muted);}
.install-steps {padding-left:24px;} li {padding-left:6px;margin-bottom:16px;} li::marker {color:var(--lms-blue);font-weight:700;}
h3 {font-size:14px;margin:0 0 4px;} li p,.driver-faq p {font-size:13px;color:var(--lms-muted);margin:0;line-height:1.8;}
.driver-bottom {border-top:1px solid var(--lms-line);padding-top:16px;font-size:12px;}
.driver-faq {margin-top:18px;font-size:13px;} summary {cursor:pointer;color:var(--lms-blue);}.driver-faq p {margin-top:10px;}
@media(max-width:900px) {.driver-layout {grid-template-columns:170px minmax(0,1fr);gap:12px;}.driver-guide {padding:16px;}.driver-title {align-items:flex-start;flex-wrap:wrap;}.driver-heading {margin-bottom:10px;}.driver-models button {padding:12px;}}
</style>
