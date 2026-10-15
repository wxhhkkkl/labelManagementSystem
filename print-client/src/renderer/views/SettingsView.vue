<template>
  <section class="settings">
    <h3>工位状态</h3>
    <el-alert :title="serviceOk ? '打印服务正常' : '打印服务未启动'" :type="serviceOk ? 'success' : 'warning'" show-icon :closable="false" />
    <el-descriptions :column="1" border class="service-details">
      <el-descriptions-item label="当前工位">{{ stationName || '—' }}</el-descriptions-item>
      <el-descriptions-item label="当前打印机">{{ saved || '尚未选择' }}</el-descriptions-item>
    </el-descriptions>
    <label class="field-label">选择打印机</label>
    <div class="printer-choice">
      <el-select v-model="selection" placeholder="选择本机打印机" aria-label="选择打印机" :disabled="!serviceOk || saving || testing" @change="save">
        <el-option v-for="name in printers" :key="name" :label="name" :value="name" />
      </el-select>
      <el-button :loading="loading" @click="refresh">刷新状态</el-button>
    </div>
    <p class="hint">选择后自动保存，下次打开继续使用。</p>
    <el-alert v-if="saved && serviceOk && !printers.includes(saved)" title="已保存的打印机当前不可用，请重新选择或检查连接。" type="warning" :closable="false" />
    <el-button type="primary" :loading="testing" :disabled="!serviceOk || !saved || !printers.includes(saved) || saving" @click="testPrint">测试打印一张</el-button>
    <p class="hint">使用 40 × 55 mm 测试标签，仅打印独立测试二维码，不占用业务码。</p>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { isPrintServiceAlive, getDefaultPrinter, listPrinters, print } from '../api/print-service'
import { getMachineBinding, setWorkstationPrinter } from '../api/workstation'
import { getBoundPrinter, setBoundPrinter } from '../api/client'
import { testLabel } from '../utils/testLabel'
const props = defineProps<{workstationId:number}>()
const serviceOk=ref(false), stationName=ref(''), loading=ref(false), saving=ref(false), testing=ref(false)
const printers=ref<string[]>([]), saved=ref(getBoundPrinter() ?? ''), selection=ref(saved.value)
async function save():Promise<void> {
  saving.value=true
  try {
    await setWorkstationPrinter(props.workstationId,selection.value)
    setBoundPrinter(selection.value);saved.value=selection.value
    window.dispatchEvent(new Event('lms:printer-changed'))
    ElMessage.success('打印机已保存')
  } catch(e) {selection.value=saved.value;ElMessage.error(e instanceof Error ? e.message : '保存失败')}
  finally {saving.value=false}
}
async function refresh():Promise<void> {
  loading.value=true
  try {
    serviceOk.value=await isPrintServiceAlive()
    printers.value=serviceOk.value ? await listPrinters() : []
    stationName.value=(await getMachineBinding())?.name ?? ''
    saved.value=getBoundPrinter() ?? '';selection.value=saved.value
    if(!saved.value && serviceOk.value) {
      selection.value=await getDefaultPrinter() ?? ''
      if(selection.value && printers.value.includes(selection.value)) await save()
    }
  } catch(e) {ElMessage.error(e instanceof Error ? e.message : '读取工位状态失败')}
  finally {loading.value=false}
}
async function testPrint():Promise<void> {
  testing.value=true
  try {
    const result=await print({...testLabel(new Date()),deviceName:saved.value})
    if(!result.ok) throw new Error(result.error ?? '测试打印失败')
    ElMessage.success('已发送一张测试标签')
  } catch(e) {ElMessage.error(e instanceof Error ? e.message : '测试打印失败')}
  finally {testing.value=false}
}
onMounted(refresh)
</script>
<style scoped>
.service-details {margin-top:16px;}
.hint {color:var(--lms-muted);font-size:13px;margin:14px 0;}
.printer-choice {display:flex;gap:12px;max-width:600px;}
.printer-choice .el-select {flex:1;min-width:0;}
</style>
