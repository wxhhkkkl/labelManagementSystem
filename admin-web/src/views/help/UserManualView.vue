<template>
  <div class="manual-page">
    <header class="manual-hero">
      <div><span class="manual-kicker">从第一次登录到每天打印</span><h1>标签管理系统 · 使用说明</h1><p>网页管理后台与工位打印端图文教程 · 适合第一次使用的人员</p></div>
      <el-button :loading="preparingPrint" @click="printManual">打印 / 保存 PDF</el-button>
    </header>
    <div class="manual-tools">
      <el-radio-group v-model="group" aria-label="说明分类"><el-radio-button v-for="item in groups" :key="item" :value="item">{{ item }}</el-radio-button></el-radio-group>
    </div>
    <div class="manual-layout">
      <aside class="manual-toc" aria-label="使用说明目录">
        <p>操作目录 <small>{{ sections.length }} 节</small></p>
        <a v-for="section in sections" :key="section.id" :href="`#manual-${section.id}`" @click.prevent="go(section.id)">{{ section.title }}</a>
      </aside>
      <main class="manual-content">
        <section v-for="section in sections" :id="`manual-${section.id}`" :key="section.id" class="manual-section">
          <div class="manual-section-heading"><span>{{ section.group }}</span><span>适用人员：{{ section.audience }}</span></div>
          <h2>{{ section.title }}</h2><p class="manual-intro">{{ section.intro }}</p>
          <ol class="manual-steps"><li v-for="step in section.steps" :key="step">{{ step }}</li></ol>
          <div v-if="section.table" class="manual-table-wrap"><table><thead><tr><th v-for="head in section.table.headers" :key="head">{{ head }}</th></tr></thead><tbody><tr v-for="(row,index) in section.table.rows" :key="index"><td v-for="(cell,column) in row" :key="column">{{ cell }}</td></tr></tbody></table></div>
          <p v-for="tip in section.tips" :key="tip" class="manual-tip"><strong>请留意：</strong>{{ tip }}</p>
          <figure v-for="picture in section.images" :key="picture.file">
            <button class="manual-image" :aria-label="`放大截图：${picture.caption}`" @click="zoom=picture"><img :src="`${imageBase}${picture.file}`" :alt="picture.caption" loading="lazy" width="1400" height="950" /></button>
            <figcaption>{{ picture.caption }} <span>点击图片放大</span></figcaption>
          </figure>
        </section>
      </main>
    </div>
    <el-dialog :model-value="!!zoom" :title="zoom?.caption" width="min(1500px, 96vw)" top="3vh" @close="zoom=null"><img v-if="zoom" class="manual-zoom" :src="`${imageBase}${zoom.file}`" :alt="zoom.caption" /></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { manualSections } from '../../content/userManual'
const group=ref('全部')
const groups=['全部','入门','网页端','打印端','常见问题']
const imageBase=import.meta.env.BASE_URL+'manual/'
const zoom=ref<{file:string;caption:string}|null>(null)
const preparingPrint=ref(false)
const sections=computed(()=>manualSections.filter(section=>group.value==='全部'||section.group===group.value))
function go(id:string){document.getElementById(`manual-${id}`)?.scrollIntoView({behavior:'smooth',block:'start'})}
async function printManual(){
  preparingPrint.value=true
  try {
    const pictures=Array.from(document.querySelectorAll<HTMLImageElement>('.manual-image img'))
    await Promise.all(pictures.map(async picture=>{picture.loading='eager';await picture.decode().catch(()=>undefined)}))
    window.print()
  } finally {preparingPrint.value=false}
}
</script>
<style scoped>
.manual-hero {display:flex;align-items:center;justify-content:space-between;gap:20px;background:linear-gradient(120deg,#edf4ff,#fff);border:1px solid var(--lms-line);border-radius:14px;padding:28px;}
.manual-kicker {font-size:12px;color:var(--lms-blue);}h1 {font-size:26px;margin:6px 0 10px;}.manual-hero p {margin:0;color:var(--lms-muted);}
.manual-tools {display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:20px 0;}
.manual-layout {display:grid;grid-template-columns:250px minmax(0,1fr);gap:24px;align-items:start;}
.manual-toc {position:sticky;top:16px;max-height:calc(100vh - 32px);overflow:auto;overscroll-behavior-y:contain;background:white;border:1px solid var(--lms-line);border-radius:12px;padding:16px;}
.manual-toc p {margin:0 0 12px;font-weight:600;}.manual-toc small {color:var(--lms-muted);font-weight:400;}.manual-toc a {display:block;font-size:13px;line-height:1.6;padding:8px;color:var(--lms-ink);text-decoration:none;border-radius:6px;}.manual-toc a:hover {background:var(--lms-soft);color:var(--lms-blue);}
.manual-content {min-width:0;}.manual-section {scroll-margin-top:20px;padding:28px;background:white;border:1px solid var(--lms-line);border-radius:12px;margin-bottom:24px;}
.manual-section-heading {display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:var(--lms-muted);}.manual-section-heading span:first-child {color:var(--lms-blue);}
.manual-section h2 {font-size:22px;margin:10px 0 16px;line-height:1.5;}.manual-intro {font-size:15px;line-height:1.9;color:#536680;}
.manual-steps {padding-left:25px;}.manual-steps li {padding-left:5px;margin:14px 0;line-height:1.95;font-size:14px;}.manual-steps li::marker {font-weight:700;color:var(--lms-blue);}
.manual-tip {padding:14px 16px;background:#fff8e9;border-left:3px solid #d99d28;border-radius:4px;font-size:13px;line-height:1.9;}
.manual-table-wrap {overflow:auto;}table {border-collapse:collapse;width:100%;font-size:13px;margin:16px 0;}th,td {border:1px solid var(--lms-line);padding:12px;text-align:left;line-height:1.8;}th {background:var(--lms-soft);}
figure {margin:24px 0 0;}.manual-image {border:1px solid var(--lms-line);border-radius:8px;overflow:hidden;display:block;width:100%;padding:0;background:#f4f7fc;cursor:zoom-in;}.manual-image img {display:block;width:100%;height:auto;}
figcaption {font-size:12px;color:var(--lms-muted);line-height:1.8;margin:10px 0;}figcaption span {color:var(--lms-blue);white-space:nowrap;}.manual-zoom {display:block;width:100%;height:auto;}
@media(max-width:1100px){.manual-layout {grid-template-columns:200px minmax(0,1fr);gap:16px;}.manual-section {padding:20px;}}
@media(max-width:760px){.manual-layout {grid-template-columns:1fr;}.manual-toc {position:static;max-height:260px;}.manual-hero {padding:20px;flex-wrap:wrap;}h1 {font-size:22px;}.manual-section {padding:16px;}}
@media print {.manual-hero {background:white;padding:0;border:0;}.manual-hero .el-button,.manual-tools,.manual-toc,figcaption span {display:none!important;}.manual-layout {display:block;}.manual-section {border:0;border-radius:0;padding:0;break-before:page;}.manual-section:first-child {break-before:auto;}.manual-image {border:1px solid #ddd;}figure {break-inside:avoid;}.manual-section h2 {break-after:avoid;}.manual-steps li {break-inside:avoid;}}
</style>
<style>
@media print { body:has(.manual-page) .admin-sidebar,body:has(.manual-page) .admin-topbar,body:has(.manual-page) .app-footer {display:none!important;} body:has(.manual-page) .admin-main {padding:0!important;} body:has(.manual-page) .admin-shell,body:has(.manual-page) .admin-workarea {display:block!important;width:100%!important;} body:has(.manual-page) {background:white;} }
</style>
