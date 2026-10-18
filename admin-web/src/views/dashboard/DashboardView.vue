<template>
  <div>
    <h2>码量看板</h2>
    <p class="hint">
      四态口径："已分配未打印"包含正在打印的码。时间筛选按<strong>码入库时间</strong>过滤——
      四态是当前快照，查不到"历史某时刻的分布"。
    </p>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <el-radio-group v-model="groupBy" @change="load">
        <el-radio-button value="company_product">按公司 + 产品</el-radio-button>
        <el-radio-button value="company">按公司</el-radio-button>
        <el-radio-button value="product">按产品</el-radio-button>
      </el-radio-group>

      <el-date-picker
        v-model="range"
        type="daterange"
        range-separator="至"
        start-placeholder="入库起始"
        end-placeholder="入库截止"
        value-format="YYYY-MM-DDTHH:mm:ss"
        @change="load"
      />

      <el-button @click="load">刷新</el-button>
      <el-button v-if="me?.role === 'hq_admin'" @click="onExportStock">导出码量</el-button>
    </div>

    <el-card shadow="never" class="totals">
      <div class="total-row">
        <span class="total-label">合计</span>
        <span class="total-value">{{ totals.total }}</span>
      </div>
      <div class="states">
        <div v-for="state in STATES" :key="state.key" class="state">
          <span class="dot" :style="{ background: state.color }" />
          <span class="state-label">{{ state.label }}</span>
          <span class="state-value">{{ totals[state.key] }}</span>
          <div class="bar">
            <div
              class="bar-fill"
              :style="{ width: percent(totals[state.key], totals.total), background: state.color }"
            />
          </div>
        </div>
      </div>
    </el-card>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column label="维度" min-width="220">
        <template #default="{ row }">{{ row.key }}</template>
      </el-table-column>
      <el-table-column prop="unallocated" label="待分配" width="100" />
      <el-table-column prop="allocated_not_printed" label="已分配未打印" width="130" />
      <el-table-column prop="printed" label="已打印" width="100" />
      <el-table-column prop="voided" label="已作废" width="100" />
      <el-table-column prop="total" label="合计" width="100" />
    </el-table>

    <el-empty v-if="!loading && !rows.length" description="所选条件下没有码" />
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

import { fetchMe, type MeUser } from '../../api/auth'
import { ApiError } from '../../api/client'
import {
  exportCodeStock,
  fetchDistribution,
  type DistributionRow,
  type GroupBy,
} from '../../api/report'

const STATES = [
  { key: 'unallocated' as const, label: '待分配', color: '#687C99' },
  { key: 'allocated_not_printed' as const, label: '已分配未打印', color: '#2563EB' },
  { key: 'printed' as const, label: '已打印', color: '#138565' },
  { key: 'voided' as const, label: '已作废', color: '#D64550' },
]

const EMPTY: DistributionRow = {
  key: 'ALL',
  company_name: null,
  product_name: null,
  unallocated: 0,
  allocated: 0,
  printing: 0,
  printed: 0,
  voided: 0,
  allocated_not_printed: 0,
  total: 0,
}

const me = ref<MeUser | null>(null)
const rows = ref<DistributionRow[]>([])
const totals = ref<DistributionRow>({ ...EMPTY })
const groupBy = ref<GroupBy>('company_product')
const range = ref<[string, string] | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

function percent(value: number, total: number): string {
  return total > 0 ? `${Math.round((value / total) * 100)}%` : '0%'
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const body = await fetchDistribution({
      group_by: groupBy.value,
      created_from: range.value?.[0],
      created_to: range.value?.[1],
    })
    rows.value = body.rows
    totals.value = body.totals
  } catch (e) {
    error.value = e instanceof ApiError ? e.body.message : '加载看板失败'
  } finally {
    loading.value = false
  }
}

async function onExportStock(): Promise<void> {
  try {
    await exportCodeStock()
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.body.message : '导出失败')
  }
}

onMounted(async () => {
  me.value = await fetchMe().catch(() => null)
  await load()
})
</script>

<style scoped>
.hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
  flex-wrap: wrap;
}
.totals {
  margin-bottom: 16px;
  background: transparent;
  border: none;
}
:deep(.totals .el-card__body) { padding: 0; }
.total-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.total-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.total-value {
  font-size: 24px;
  font-weight: 600;
}
.states {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}
.state {
  display: grid;
  grid-template-columns: 10px 1fr auto;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  background: #fff;
  padding: 20px;
  border: 1px solid var(--lms-line);
  border-radius: 12px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.state-value {
  font-weight: 600;
  font-size: 26px;
  grid-column: 2 / 4;
  margin: 8px 0;
  font-variant-numeric: tabular-nums;
}
.bar {
  grid-column: 2 / 4;
  height: 6px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  transition: width 0.3s;
}
</style>
