<template>
  <div>
    <h2>打印模板管理</h2>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <div class="toolbar">
      <el-button type="primary" @click="openCreate">新建模板</el-button>
      <el-button @click="load">刷新</el-button>
      <span class="hint">模板由总部统一管理并随分配单下发，子公司与工位端只读。</span>
    </div>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column prop="code" label="模板编码" width="140" />
      <el-table-column prop="name" label="模板名称" />
      <el-table-column prop="current_version_no" label="当前版本" width="100">
        <template #default="{ row }">
          {{ row.current_version_no ? `V${row.current_version_no}` : '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="version_count" label="版本数" width="90" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
            {{ row.status === 'active' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="250">
        <template #default="{ row }">
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link @click="openPreview(row)">打印预览</el-button>
          <el-button
            v-if="row.status === 'active'"
            size="small"
            type="danger"
            link
            @click="disable(row)"
          >
            停用
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      class="template-dialog"
      :title="dialogTitle"
      width="min(1400px, calc(100vw - 32px))"
      top="4vh"
      :close-on-click-modal="false"
      :close-on-press-escape="!saving"
      :show-close="!saving"
    >
      <el-form v-if="!editingTemplate" inline class="create-form">
        <el-form-item label="模板编码">
          <el-input v-model="newCode" placeholder="如 TPL-A" style="width: 180px" />
        </el-form-item>
        <el-form-item label="模板名称">
          <el-input v-model="newName" placeholder="如 60×40 标准标签" style="width: 240px" />
        </el-form-item>
      </el-form>

      <TemplateEditor v-if="editingDoc" :doc="editingDoc" @update:doc="onDocChange" />

      <template #footer>
        <span class="footer-hint">
          {{ problems.length ? `还有 ${problems.length} 处问题需要修正` : '版面校验通过' }}
        </span>
        <el-button :disabled="saving" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="problems.length > 0" @click="save">
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="打印预览" width="min(900px, calc(100vw - 32px))">
      <TemplatePrintPreview v-if="previewDoc" :doc="previewDoc" :data="previewData" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { ApiError } from '../../api/client'
import {
  addTemplateVersion,
  createTemplate,
  disableTemplate,
  listTemplateVersions,
  listTemplates,
  type TemplateItem,
} from '../../api/template'
import TemplateEditor from '../../components/TemplateEditor.vue'
import TemplatePrintPreview from '../../components/TemplatePrintPreview.vue'
import { cloneTemplateDoc, validateDocument } from '../../utils/templateEditor'
import type { TemplateDoc } from '../../utils/templateRender'

const rows = ref<TemplateItem[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)

const dialogVisible = ref(false)
const editingDoc = ref<TemplateDoc | null>(null)
const editingTemplate = ref<TemplateItem | null>(null)
const newCode = ref('')
const newName = ref('')

const previewVisible = ref(false)
const previewDoc = ref<TemplateDoc | null>(null)

const EMPTY_DOC: TemplateDoc = { paper_width_mm: 60, paper_height_mm: 40, elements: [] }

const previewData = {
  product_name: '500ml 矿泉水',
  company_name: '华东分公司',
  code_value: 'A1B2C3D4',
  batch_no: 'ALL202610120001',
    production_batch_no: '22PT510020DPHXQ1V',
  print_date: '2026-10-14',
  serial_no: '1',
}

const problems = computed(() => (editingDoc.value ? validateDocument(editingDoc.value) : []))
const dialogTitle = computed(() =>
  editingTemplate.value ? `编辑模板：${editingTemplate.value.name}` : '新建模板',
)

function fail(e: unknown, fallback: string): void {
  error.value = e instanceof ApiError ? e.body.message : fallback
  ElMessage.error(error.value)
}

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await listTemplates()
  } catch (e) {
    fail(e, '加载模板列表失败')
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editingTemplate.value = null
  newCode.value = ''
  newName.value = ''
  editingDoc.value = cloneTemplateDoc(EMPTY_DOC)
  dialogVisible.value = true
}

async function openEdit(row: TemplateItem): Promise<void> {
  try {
    const versions = await listTemplateVersions(row.id)
    if (!versions.length) {
      ElMessage.warning('该模板还没有任何版本')
      return
    }
    editingTemplate.value = row
    editingDoc.value = cloneTemplateDoc(versions[0].elements_json)
    dialogVisible.value = true
  } catch (e) {
    fail(e, '加载模板版本失败')
  }
}

function onDocChange(doc: TemplateDoc): void {
  editingDoc.value = doc
}

/** 打印预览（FR-038）：用同一套渲染规则把当前版本按实际版面画出来。 */
async function openPreview(row: TemplateItem): Promise<void> {
  try {
    const versions = await listTemplateVersions(row.id)
    if (!versions.length) {
      ElMessage.warning('该模板还没有任何版本')
      return
    }
    previewDoc.value = versions[0].elements_json
    previewVisible.value = true
  } catch (e) {
    fail(e, '加载模板版本失败')
  }
}

async function save(): Promise<void> {
  if (!editingDoc.value || saving.value || problems.value.length) return
  saving.value = true
  try {
    if (editingTemplate.value) {
      // 修改 = 追加新版本（FR-033），历史版本保持原样
      const version = await addTemplateVersion(editingTemplate.value.id, editingDoc.value)
      ElMessage.success(`已生成新版本 V${version.version_no}`)
    } else {
      if (!newCode.value.trim() || !newName.value.trim()) {
        ElMessage.warning('请填写模板编码与名称')
        return
      }
      await createTemplate({
        code: newCode.value.trim(),
        name: newName.value.trim(),
        paper_width_mm: editingDoc.value.paper_width_mm,
        paper_height_mm: editingDoc.value.paper_height_mm,
        elements: editingDoc.value.elements,
      })
      ElMessage.success('模板已创建')
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    fail(e, '保存模板失败')
  } finally {
    saving.value = false
  }
}

async function disable(row: TemplateItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `停用后该模板不可再用于新分配；已冻结的历史版本仍可正常打印与补打。确认停用「${row.name}」？`,
      '停用模板',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await disableTemplate(row.id)
    ElMessage.success('已停用')
    await load()
  } catch (e) {
    fail(e, '停用模板失败')
  }
}

onMounted(load)
</script>

<style scoped>
:global(.template-dialog .el-dialog__body) {
  max-height: calc(100vh - 190px);
  overflow: auto;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.footer-hint {
  float: left;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 32px;
}
</style>
