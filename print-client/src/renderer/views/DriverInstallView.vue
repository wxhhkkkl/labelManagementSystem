<template>
  <section class="driver-page">
    <header class="driver-heading"><div><h1>打印机驱动安装</h1><p>选择打印机型号，下载 Windows 驱动并按步骤安装。</p></div><el-tag>Windows 工位电脑</el-tag></header>
    <div class="driver-layout">
      <nav class="driver-models" aria-label="打印机型号">
        <button v-for="guide in printerGuides" :key="guide.id" :class="{selected:guide.id===selected}" @click="selected=guide.id"><span>{{ guide.brand }}</span><strong>{{ guide.name }}</strong></button>
      </nav>
      <article class="driver-guide">
        <div class="driver-title"><div><p class="eyebrow">安装教程</p><h2>{{ current.name }}</h2><p>驱动型号：{{ current.model }}</p></div><a class="download-button" :href="current.download" target="_blank" rel="noopener noreferrer">下载驱动 ↗</a></div>
        <p class="download-description">在系统浏览器打开 Seagull / BarTender 驱动发布方的型号下载页。页面可能要求填写姓名、邮箱等信息；选择适合当前 Windows 版本的驱动包。驱动安装无需购买 BarTender 标签设计软件。</p>
        <ol class="install-steps">
          <li><h3>准备设备与耗材</h3><p>确认机身铭牌与所选型号一致，装好标签纸；使用碳带时装好碳带。接通电源，准备 USB 数据线。关闭正在向此打印机发送任务的软件。</p></li>
          <li><h3>下载并运行安装向导</h3><p>点击“下载驱动”，下载后解压，运行驱动包中的安装程序或 Driver Wizard。需要管理员权限时，按 Windows 提示操作；选择“安装打印机驱动程序”。</p></li>
          <li><h3>选择对应型号</h3><p>{{ current.detail }}</p></li>
          <li><h3>连接打印机并选择端口</h3><p>按安装向导提示接入 USB 数据线并开机，选择它识别的打印机或对应 USB 端口。若使用网口，先确认打印机实际 IP，再按向导添加 TCP/IP 端口。完成向导后，在 Windows“打印机和扫描仪”中确认设备已出现且处于可用状态。</p></li>
          <li><h3>设置标签尺寸与介质</h3><p>在打印首选项中设置实际纸张宽、高；本系统合格证为宽 40 mm × 高 55 mm，其他模板按实际尺寸设置。按耗材选择热转印（有碳带）或热敏（热敏纸），并选择间隙纸、黑标纸或连续纸。更换纸张后按该型号说明书执行介质校准。</p></li>
          <li><h3>回到工位软件验证</h3><p>进入“工位状态”，点击“刷新状态”，选择并保存刚安装的打印机，再点击“测试打印一张”。确认一张标签正常出纸、二维码清晰且没有偏移后，再打印业务标签。</p></li>
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
.driver-models span {display:block;font-size:11px;color:var(--lms-muted);margin-bottom:4px;}
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
