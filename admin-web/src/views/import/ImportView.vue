<template>
  <div>
    <h2>码导入</h2>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <el-card shadow="never" class="section">
      <template #header>
        <div class="card-header">
          <span>导入码清单与"码—产品"对照关系</span>
          <el-button size="small" @click="onDownloadTemplate">下载导入模板</el-button>
        </div>
      </template>

      <p class="hint">
        模板含两个工作表，请分别另存为两个文件后一并上传：<strong>码清单</strong>（列：码值）与
        <strong>码—产品对照关系</strong>（列：码值、产品编码）。
        两个文件的码集合必须完全一致，否则整批拒绝。码值限 100 位以内数字与字母。
      </p>

      <el-form label-width="120px">
        <el-form-item label="码清单文件">
          <input type="file" accept=".xlsx" @change="onPickCodeList" />
        </el-form-item>
        <el-form-item label="对照关系文件">
          <input type="file" accept=".xlsx" @change="onPickMapping" />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="uploading"
            :disabled="!codeListFile || !mappingFile"
            @click="submit"
          >
            上传并导入
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="current" shadow="never" class="section">
      <template #header>
        <div class="card-header">
          <span>批次 {{ current.batch_no }}</span>
          <el-tag :type="statusTagType(current.status)" size="small">
            {{ statusLabel(current.status) }}
          </el-tag>
        </div>
      </template>

      <el-progress :percentage="progressPercent(current)" :stroke-width="14" />
      <p class="progress-text">{{ progressText(current) }}</p>

      <el-button
        v-if="canDownloadErrors(current)"
        size="small"
        @click="onDownloadErrors"
      >
        下载失败明细
      </el-button>
    </el-card>

    <el-card shadow="never" class="section">
      <template #header><span>历史批次</span></template>
      <el-table v-loading="loading" :data="batches" border size="small">
        <el-table-column prop="batch_no" label="批次号" width="230" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="总行数" width="100">
          <template #default="{ row }">{{ row.total_rows ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="success_count" label="成功" width="90" />
        <el-table-column prop="failure_count" label="失败" width="90" />
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button
              v-if="canDownloadErrors(row)"
              size="small"
              link
              @click="onDownloadErrorsFor(row)"
            >
              失败明细
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import {
  downloadErrors,
  downloadTemplate,
  getBatch,
  listBatches,
  uploadImport,
  type ImportBatch,
} from '../../api/import'
import {
  POLL_INTERVAL_MS,
  canDownloadErrors,
  isFinal,
  progressPercent,
  progressText,
  statusLabel,
  statusTagType,
  validateUploadSelection,
} from '../../utils/importView'

const codeListFile = ref<File | null>(null)
const mappingFile = ref<File | null>(null)
const uploading = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)

const batches = ref<ImportBatch[]>([])
const current = ref<ImportBatch | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

function fail(e: unknown, fallback: string): void {
  error.value = e instanceof ApiError ? e.body.message : fallback
  ElMessage.error(error.value)
}

function onPickCodeList(event: Event): void {
  const input = event.target as HTMLInputElement
  codeListFile.value = input.files?.[0] ?? null
}

function onPickMapping(event: Event): void {
  const input = event.target as HTMLInputElement
  mappingFile.value = input.files?.[0] ?? null
}

async function load(): Promise<void> {
  loading.value = true
  try {
    batches.value = await listBatches()
  } catch (e) {
    fail(e, '加载批次失败')
  } finally {
    loading.value = false
  }
}

function stopPolling(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

/** 轮询批次进度，抵达终态即停止（否则会一直打服务端）。 */
function startPolling(batchId: number): void {
  stopPolling()
  timer = setInterval(async () => {
    try {
      const batch = await getBatch(batchId)
      current.value = batch
      if (isFinal(batch.status)) {
        stopPolling()
        await load()
        if (batch.status === 'succeeded') ElMessage.success('导入完成')
        else ElMessage.warning(progressText(batch))
      }
    } catch (e) {
      stopPolling()
      fail(e, '查询批次进度失败')
    }
  }, POLL_INTERVAL_MS)
}

async function submit(): Promise<void> {
  const invalid = validateUploadSelection(codeListFile.value, mappingFile.value)
  if (invalid) {
    ElMessage.warning(invalid)
    return
  }

  error.value = null
  uploading.value = true
  try {
    const created = await uploadImport(codeListFile.value!, mappingFile.value!)
    current.value = {
      id: created.batch_id,
      batch_no: created.batch_no,
      code_list_filename: '',
      mapping_filename: '',
      status: created.status,
      total_rows: null,
      processed_rows: 0,
      success_count: 0,
      failure_count: 0,
      started_at: null,
      finished_at: null,
      created_at: new Date().toISOString(),
    }
    startPolling(created.batch_id)
    await load()
  } catch (e) {
    fail(e, '上传失败')
  } finally {
    uploading.value = false
  }
}

async function onDownloadTemplate(): Promise<void> {
  try {
    await downloadTemplate()
  } catch (e) {
    fail(e, '下载模板失败')
  }
}

async function onDownloadErrors(): Promise<void> {
  if (current.value) await onDownloadErrorsFor(current.value)
}

async function onDownloadErrorsFor(batch: ImportBatch): Promise<void> {
  try {
    await downloadErrors(batch.id, batch.batch_no)
  } catch (e) {
    fail(e, '下载失败明细失败')
  }
}

onMounted(load)
onBeforeUnmount(stopPolling)
</script>

<style scoped>
.section {
  margin-bottom: 16px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.8;
}
.progress-text {
  margin: 8px 0 12px;
}
</style>
