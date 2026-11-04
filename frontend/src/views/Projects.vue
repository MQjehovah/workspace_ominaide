<template>
  <div class="page-wrapper projects">
    <div class="page-header projects-header">
      <div>
        <h2>项目</h2>
        <p class="sub">项目管理与 Coding Run；代码执行由 Bot 的 coding 能力负责。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="loadProjects">刷新</el-button>
        <el-button :icon="Search" @click="scanWorkspace">扫描工作区</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">添加项目</el-button>
      </div>
    </div>

    <div class="project-grid">
      <aside class="page-card project-list">
        <div class="panel-title">
          <span>Projects</span>
          <span class="count">{{ projects.length }}</span>
        </div>
        <button
          v-for="p in projects"
          :key="p.id"
          class="project-item"
          :class="{ active: p.id === selectedId }"
          @click="selectProject(p.id)"
        >
          <span class="project-icon">⌘</span>
          <span class="project-meta">
            <span class="project-name">{{ p.name }}</span>
            <span class="project-path">{{ p.path }}</span>
          </span>
        </button>
        <div v-if="projects.length === 0" class="empty-hint">
          还没有项目。点“扫描工作区”从 /workspace 导入。
        </div>
      </aside>

      <section v-if="selected" class="project-main">
        <div class="page-card project-head">
          <div>
            <h3>{{ selected.name }}</h3>
            <p class="muted">{{ selected.path }}</p>
            <p class="muted">
              <template v-if="selected.is_git">
                Git 项目 · 默认分支 {{ selected.default_branch || 'main' }}
                <template v-if="selected.repo_url"> · {{ selected.repo_url }}</template>
              </template>
              <template v-else>非 Git 项目 · 仅作为目录管理</template>
            </p>
          </div>
          <div class="head-actions">
            <el-button type="primary" :icon="VideoPlay" @click="openRun">发起 Coding Run</el-button>
            <el-popconfirm title="删除这个项目？项目记录会删除，历史 Run 保留。" @confirm="deleteProject">
              <template #reference><el-button type="danger" plain>删除</el-button></template>
            </el-popconfirm>
          </div>
        </div>

        <div class="page-card">
          <div class="page-card-body">
            <div class="section-head">
              <div>
                <h4>运行记录</h4>
                <p>每个 Coding Run 都是一次独立的 Bot 子运行。</p>
              </div>
              <el-button :icon="Refresh" @click="loadRuns">刷新</el-button>
            </div>
            <el-table :data="runs" size="small" empty-text="还没有运行记录">
              <el-table-column prop="id" label="#" width="60" />
              <el-table-column label="状态" width="120">
                <template #default="{ row }">
                  <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="branch" label="分支" width="180">
                <template #default="{ row }">{{ row.branch || 'feature/*' }}</template>
              </el-table-column>
              <el-table-column prop="input" label="任务" min-width="260" show-overflow-tooltip />
              <el-table-column label="输出" min-width="240" show-overflow-tooltip>
                <template #default="{ row }">{{ row.output || row.error || '' }}</template>
              </el-table-column>
              <el-table-column label="时间" width="150">
                <template #default="{ row }">{{ fmt(row.created_at) }}</template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </section>

      <section v-else class="page-card empty-main">
        <el-icon :size="30"><FolderOpened /></el-icon>
        <h3>选择或添加一个项目</h3>
        <p>项目是业务数据；Coding 是 Bot 的能力。</p>
      </section>
    </div>

    <el-dialog v-model="createOpen" title="添加项目" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="路径">
          <el-input v-model="form.path" placeholder="/workspace/workspace_ominaide" />
        </el-form-item>
        <el-form-item label="Git 项目">
          <el-checkbox v-model="form.is_git">这是一个 Git 仓库</el-checkbox>
        </el-form-item>
        <template v-if="form.is_git">
          <el-form-item label="仓库地址"><el-input v-model="form.repo_url" placeholder="可选" /></el-form-item>
          <el-form-item label="默认分支"><el-input v-model="form.default_branch" placeholder="main" /></el-form-item>
        </template>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createProject">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runOpen" title="发起 Coding Run" width="560px">
      <el-form :model="runForm" label-width="80px">
        <el-form-item label="任务">
          <el-input v-model="runForm.instruction" type="textarea" :rows="5" placeholder="描述要改什么、验收标准是什么" />
        </el-form-item>
        <el-form-item label="分支">
          <el-input v-model="runForm.branch" placeholder="留空自动创建 feature/*；明确要求时才填 master" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runOpen = false">取消</el-button>
        <el-button type="primary" :loading="starting" @click="startRun">开始</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened, Plus, Refresh, Search, VideoPlay } from '@element-plus/icons-vue'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'

const projects = ref<any[]>([])
const runs = ref<any[]>([])
const selectedId = ref<number | null>(null)
const selected = computed(() => projects.value.find(p => p.id === selectedId.value) || null)

const createOpen = ref(false)
const saving = ref(false)
const form = reactive({
  name: '', path: '', is_git: true, repo_url: '', default_branch: 'main',
  description: '',
})

const runOpen = ref(false)
const starting = ref(false)
const runForm = reactive({ instruction: '', branch: '' })

function fmt(value: string) {
  return value ? formatBackendDate(value) : '—'
}

function statusType(status: string) {
  return ({
    done: 'success', failed: 'danger', running: 'warning',
    queued: 'info', cancelled: 'info', waiting_approval: 'warning',
  } as Record<string, string>)[status] || 'info'
}

async function loadProjects() {
  try {
    const r = await client.get('/projects')
    projects.value = r.data || []
    if (!selectedId.value || !projects.value.some(p => p.id === selectedId.value)) {
      selectedId.value = projects.value[0]?.id || null
    }
    if (selectedId.value) await loadRuns()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载项目失败')
  }
}

function selectProject(id: number) {
  selectedId.value = id
  loadRuns()
}

async function loadRuns() {
  if (!selectedId.value) {
    runs.value = []
    return
  }
  try {
    const r = await client.get(`/projects/${selectedId.value}/runs`)
    runs.value = r.data || []
  } catch {
    runs.value = []
  }
}

function openCreate() {
  Object.assign(form, {
    name: '', path: '', is_git: true, repo_url: '', default_branch: 'main',
    description: '',
  })
  createOpen.value = true
}

async function createProject() {
  if (!form.name.trim() || !form.path.trim()) {
    ElMessage.warning('名称和路径必填')
    return
  }
  saving.value = true
  try {
    await client.post('/projects', { ...form })
    createOpen.value = false
    await loadProjects()
    ElMessage.success('项目已添加')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '添加失败')
  } finally {
    saving.value = false
  }
}

async function scanWorkspace() {
  try {
    const r = await client.post('/projects/scan')
    const created = r.data || []
    await loadProjects()
    ElMessage.success(created.length ? `导入 ${created.length} 个项目` : '没有发现新项目')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '扫描失败')
  }
}

async function deleteProject() {
  if (!selected.value) return
  try {
    await client.delete(`/projects/${selected.value.id}`)
    selectedId.value = null
    await loadProjects()
    ElMessage.success('已删除')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

function openRun() {
  runForm.instruction = ''
  runForm.branch = ''
  runOpen.value = true
}

async function startRun() {
  if (!runForm.instruction.trim()) {
    ElMessage.warning('任务描述不能为空')
    return
  }
  starting.value = true
  try {
    const r = await client.post(`/projects/${selectedId.value}/runs`, {
      instruction: runForm.instruction.trim(),
      branch: runForm.branch.trim() || null,
    })
    runOpen.value = false
    await loadRuns()
    ElMessage.success(`Coding Run #${r.data.id} 已创建`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  } finally {
    starting.value = false
  }
}

onMounted(loadProjects)
</script>

<style scoped>
.projects-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.projects-header .sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.header-actions { display: flex; gap: 8px; flex-shrink: 0; }
.project-grid { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 16px; align-items: start; }
.project-list { padding: 12px; position: sticky; top: 12px; }
.panel-title { display: flex; justify-content: space-between; align-items: center; padding: 4px 6px 10px; font-size: 12px; font-weight: 700; color: #606266; letter-spacing: .5px; }
.panel-title .count { background: #f0f2f5; color: #909399; border-radius: 10px; padding: 1px 7px; font-size: 11px; }
.project-item { width: 100%; display: flex; gap: 10px; align-items: center; text-align: left; padding: 10px; border: 1px solid transparent; border-radius: 10px; background: transparent; cursor: pointer; }
.project-item:hover { background: #f7f9fc; }
.project-item.active { background: #eef4ff; border-color: #c6d9ff; }
.project-icon { width: 34px; height: 34px; border-radius: 10px; background: #f2f4f8; display: flex; align-items: center; justify-content: center; color: #6366f1; flex-shrink: 0; }
.project-meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.project-name { font-size: 13px; font-weight: 600; color: #2c3550; }
.project-path { font-size: 11px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.project-main { min-width: 0; }
.project-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 16px 18px; margin-bottom: 12px; }
.project-head h3 { margin: 0; font-size: 17px; color: #1a1a2e; }
.project-head p { margin: 4px 0 0; }
.head-actions { display: flex; gap: 8px; flex-shrink: 0; }
.muted { color: #909399; font-size: 12px; }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
.section-head h4 { margin: 0; font-size: 14px; color: #1a1a2e; }
.section-head p { margin: 4px 0 0; font-size: 12px; color: #909399; }
.empty-hint { font-size: 12px; color: #909399; text-align: center; padding: 24px 8px; }
.empty-main { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; min-height: 320px; color: #909399; }
.empty-main h3 { margin: 4px 0 0; color: #606266; font-size: 15px; }
.empty-main p { margin: 0; font-size: 12px; }
@media (max-width: 980px) {
  .project-grid { grid-template-columns: 1fr; }
  .project-list { position: static; }
}
@media (max-width: 600px) {
  .projects-header { flex-direction: column; align-items: stretch; }
  .header-actions { flex-wrap: wrap; }
  .project-list { display: flex; gap: 8px; overflow-x: auto; }
  .project-list .panel-title { display: none; }
  .project-item { min-width: 190px; }
  .project-head { flex-direction: column; align-items: flex-start; }
  .head-actions { flex-wrap: wrap; }
  .section-head { flex-direction: column; align-items: stretch; }
}
</style>
