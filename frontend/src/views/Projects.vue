<template>
  <div class="page-wrapper projects">
    <div class="page-header projects-header">
      <div>
        <h2>项目</h2>
        <p class="sub">项目管理与 Coding Run；代码执行由 Bot 的 coding 能力负责。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="loadProjects">刷新</el-button>
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
          还没有项目。点“添加项目”手动添加。
        </div>
      </aside>

      <section v-if="selected" class="project-main">
        <div class="page-card project-head">
          <div>
            <h3>{{ selected.name }}</h3>
            <p class="muted">{{ selected.path }}</p>
            <p class="muted">
              <template v-if="selected.repos?.length">
                多仓库工作区 · {{ selected.repos.length }} 个 Git 项目
              </template>
              <template v-else-if="selected.is_git">
                Git 项目 · 默认分支 {{ selected.default_branch || 'master' }}
                <template v-if="selected.repo_url"> · {{ selected.repo_url }}</template>
              </template>
              <template v-else>非 Git 项目 · 仅作为目录管理</template>
            </p>
          </div>
          <div class="head-actions">
            <el-button :icon="ChatDotRound" @click="askAssistant">让助手处理</el-button>
            <el-button :icon="ChatDotRound" @click="commentsOpen = true">评论</el-button>
            <el-button type="primary" :icon="VideoPlay" @click="openRun">发起 Coding Run</el-button>
            <el-popconfirm title="删除这个项目？会同时删除项目目录，不可恢复；历史 Run 保留。" @confirm="deleteProject">
              <template #reference><el-button type="danger" plain>删除</el-button></template>
            </el-popconfirm>
          </div>
        </div>

        <div v-if="selected.repos?.length" class="page-card">
          <div class="page-card-body">
            <div class="section-head">
              <div>
                <h4>Git 仓库</h4>
                <p>一个 workspace 可以包含多个独立仓库。</p>
              </div>
              <el-button :icon="Refresh" @click="loadProjects">刷新</el-button>
            </div>
            <div class="repo-list">
              <div v-for="repo in selected.repos" :key="repo.id" class="repo-row">
                <div class="repo-main">
                  <span class="repo-name">{{ repo.name }}</span>
                  <span class="repo-path">{{ repo.path }}/</span>
                  <span class="repo-url">{{ repo.url }}</span>
                </div>
                <el-tag size="small" :type="repo.status === 'cloned' ? 'success' : repo.status === 'error' ? 'danger' : 'warning'">
                  {{ repo.status }}
                </el-tag>
                <el-button
                  v-if="repo.status !== 'cloned' && repo.status !== 'cloning'"
                  size="small"
                  :icon="Refresh"
                  @click="cloneRepo(repo)"
                >克隆</el-button>
                <span v-if="repo.error" class="repo-error">{{ repo.error }}</span>
              </div>
            </div>
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
            <el-table :data="runs" size="small" empty-text="还没有运行记录" @row-click="openRunDetail">
              <el-table-column prop="id" label="#" width="60" />
              <el-table-column label="状态" width="120">
                <template #default="{ row }">
                  <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="branch" label="分支" width="180">
                <template #default="{ row }">{{ row.branch || 'feature/*' }}</template>
              </el-table-column>
              <el-table-column prop="engine" label="引擎" width="100" />
              <el-table-column prop="session_id" label="会话" width="150" show-overflow-tooltip />
              <el-table-column prop="input" label="任务" min-width="260" show-overflow-tooltip />
              <el-table-column label="输出" min-width="240" show-overflow-tooltip>
                <template #default="{ row }">{{ row.output || row.error || '' }}</template>
              </el-table-column>
              <el-table-column label="时间" width="150">
                <template #default="{ row }">{{ fmt(row.created_at) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="90">
                <template #default="{ row }">
                  <el-button link type="primary" @click.stop="openRunDetail(row)">详情</el-button>
                </template>
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
          <el-input v-model="form.path" :placeholder="pathPlaceholder" />
        </el-form-item>
        <el-form-item label="Git 项目">
          <el-checkbox v-model="form.is_git">这是一个 Git 仓库</el-checkbox>
        </el-form-item>
        <template v-if="form.is_git">
          <el-form-item v-if="!form.repos_text.trim()" label="仓库地址" required>
            <el-input v-model="form.repo_url" placeholder="必填，例如 git@github.com:user/repo.git" />
          </el-form-item>
          <el-form-item v-if="!form.repos_text.trim()" label="默认分支">
            <el-input v-model="form.default_branch" placeholder="master" />
          </el-form-item>
          <el-form-item label="多仓库">
            <el-input
              v-model="form.repos_text"
              type="textarea"
              :rows="4"
              placeholder="每行一个仓库：目录名 仓库地址 分支&#10;例如：gateway https://github.com/MQjehovah/gateway.git master"
            />
            <div class="form-hint">填写多仓库后，上面的单仓库地址会被忽略。项目会克隆到各自子目录。</div>
          </el-form-item>
          <el-form-item v-if="form.repos_text.trim()" label="自动克隆">
            <el-checkbox v-model="form.clone">创建后自动执行 git clone</el-checkbox>
            <span class="form-hint">服务器无法访问 GitHub 时可关闭，稍后手动放入仓库目录。</span>
          </el-form-item>
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

    <el-drawer
      v-model="runDrawer"
      :title="`Coding Run #${runDetail?.id || ''}`"
      size="720px"
      @closed="stopRunPolling"
    >
      <div v-if="runDetail" v-loading="runLoading" class="run-detail">
        <div class="run-summary">
          <el-tag :type="statusType(runDetail.status)">{{ runDetail.status }}</el-tag>
          <span class="muted">触发：{{ runDetail.trigger }}</span>
          <span class="muted">创建：{{ fmt(runDetail.created_at) }}</span>
          <span class="muted">结束：{{ fmt(runDetail.finished_at) }}</span>
          <div style="flex:1"></div>
          <el-button
            v-if="!isTerminal(runDetail.status)"
            size="small" type="danger" plain @click="cancelRun"
          >取消运行</el-button>
          <el-button size="small" :icon="Refresh" @click="loadRunDetail(runDetail.id)">刷新</el-button>
        </div>

        <div class="detail-block">
          <h4>任务</h4>
          <pre>{{ runDetail.input || '(空)' }}</pre>
        </div>
        <div v-if="runDetail.error" class="detail-block">
          <h4>错误</h4>
          <pre class="error">{{ runDetail.error }}</pre>
        </div>
        <div v-if="runDetail.output" class="detail-block">
          <h4>交付结果</h4>
          <pre>{{ runDetail.output }}</pre>
          <el-button v-if="prUrl" type="primary" size="small" style="margin-top:8px" tag="a" :href="prUrl" target="_blank">
            打开 Pull Request / Compare
          </el-button>
        </div>
        <div v-if="runDetail.partial" class="detail-block">
          <h4>中间输出</h4>
          <pre>{{ runDetail.partial }}</pre>
        </div>

        <div class="detail-block">
          <h4>工具调用（{{ (runDetail.steps || []).length }}）</h4>
          <el-table :data="runDetail.steps || []" size="small" empty-text="还没有工具调用">
            <el-table-column prop="seq" label="#" width="55" />
            <el-table-column prop="tool_name" label="工具" width="150" />
            <el-table-column label="参数" min-width="220">
              <template #default="{ row }">
                <span class="args">{{ JSON.stringify(row.arguments || {}).slice(0, 200) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="结果" min-width="180">
              <template #default="{ row }">
                <span class="muted">{{ (row.result || '').slice(0, 160) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="80" />
          </el-table>
        </div>

        <div class="run-footer">
          <el-button @click="runDrawer = false">关闭</el-button>
          <el-button type="primary" @click="retryRun">以此为任务再跑一次</el-button>
        </div>
      </div>
    </el-drawer>

    <ObjectCommentsDrawer
      v-model="commentsOpen"
      type="project"
      :object-id="selected?.id || 0"
      :title="selected?.name || '项目评论'"
    />

    <el-dialog v-model="runOpen" title="发起 Coding Run" width="560px">
      <el-form :model="runForm" label-width="80px">
        <el-form-item label="任务">
          <el-input v-model="runForm.instruction" type="textarea" :rows="5" placeholder="描述要改什么、验收标准是什么" />
        </el-form-item>
        <el-form-item label="分支">
          <el-input v-model="runForm.branch" placeholder="留空自动创建 feature/*；明确要求时才填 master" />
        </el-form-item>
        <el-form-item label="引擎">
          <el-select v-model="runForm.engine" style="width:100%">
            <el-option label="内置 Coding Agent" value="builtin" />
            <el-option label="OpenCode" value="opencode" />
          </el-select>
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
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { FolderOpened, Plus, Refresh, VideoPlay, ChatDotRound } from '@element-plus/icons-vue'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'
import ObjectCommentsDrawer from '@/components/ObjectCommentsDrawer.vue'

const projects = ref<any[]>([])
const route = useRoute()
const router = useRouter()
const runs = ref<any[]>([])
const selectedId = ref<number | null>(null)
const selected = computed(() => projects.value.find(p => p.id === selectedId.value) || null)
const commentsOpen = ref(false)

const createOpen = ref(false)
const saving = ref(false)
const form = reactive({
  name: '', path: '', is_git: true, repo_url: '', default_branch: 'master',
  repos_text: '', clone: true, description: '',
})
const pathPlaceholder = computed(() =>
  form.name.trim() ? `/workspace/${form.name.trim()}` : '/workspace/<名称>'
)

const runOpen = ref(false)
const starting = ref(false)
const runForm = reactive({ instruction: '', branch: '', engine: 'builtin' })

const runDrawer = ref(false)
const runDetail = ref<any>(null)
const runLoading = ref(false)
let runTimer: ReturnType<typeof setInterval> | null = null

const prUrl = computed(() => {
  const text = `${runDetail.value?.output || ''}\n${runDetail.value?.partial || ''}`
  const m = text.match(/https:\/\/github\.com\/[^\s)<>"']+/)
  return m ? m[0] : ''
})

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
    if (selectedId.value) {
      await loadRuns()
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载项目失败')
  }
}

function askAssistant() {
  if (!selected.value?.id) return
  router.push({ path: '/chat', query: { ref: `project:${selected.value.id}` } })
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

function isTerminal(status: string) {
  return ['done', 'failed', 'cancelled', 'error', 'timeout'].includes(status)
}

async function loadRunDetail(id: number) {
  runLoading.value = true
  try {
    const r = await client.get(`/runs/${id}`)
    runDetail.value = r.data
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载运行详情失败')
  } finally {
    runLoading.value = false
  }
}

async function openRunDetail(row: any) {
  runDrawer.value = true
  runDetail.value = row
  await loadRunDetail(row.id)
  startRunPolling()
}

function startRunPolling() {
  stopRunPolling()
  runTimer = setInterval(async () => {
    if (!runDetail.value || isTerminal(runDetail.value.status)) {
      stopRunPolling()
      await loadRuns()
      return
    }
    await loadRunDetail(runDetail.value.id)
  }, 3000)
}

function stopRunPolling() {
  if (runTimer) {
    clearInterval(runTimer)
    runTimer = null
  }
}

async function cancelRun() {
  if (!runDetail.value) return
  try {
    await client.post(`/runs/${runDetail.value.id}/cancel`)
    ElMessage.success('已请求取消')
    await loadRunDetail(runDetail.value.id)
    await loadRuns()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '取消失败')
  }
}

function retryRun() {
  runForm.instruction = runDetail.value?.input || ''
  runForm.branch = ''
  runForm.engine = runDetail.value?.engine || 'builtin'
  runDrawer.value = false
  runOpen.value = true
}

function openCreate() {
  Object.assign(form, {
    name: '', path: '', is_git: true, repo_url: '', default_branch: 'master',
    repos_text: '', clone: true, description: '',
  })
  createOpen.value = true
}

function parseRepos() {
  return form.repos_text
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      const [name, url, branch] = line.split(/\s+/)
      return {
        name,
        url,
        path: name,
        default_branch: branch || 'master',
      }
    })
    .filter(repo => repo.name && repo.url)
}

async function createProject() {
  const name = form.name.trim()
  if (!name) {
    ElMessage.warning('名称必填')
    return
  }
  const repos = parseRepos()
  if (form.is_git && !repos.length && !form.repo_url.trim()) {
    ElMessage.warning('Git 项目必须填写仓库地址，或多仓库列表')
    return
  }
  const path = form.path.trim() || `/workspace/${name}`
  saving.value = true
  try {
    await client.post('/projects', {
      name,
      path,
      is_git: form.is_git || repos.length > 0,
      repo_url: repos.length ? undefined : form.repo_url.trim(),
      default_branch: form.default_branch.trim() || 'master',
      repos,
      clone: form.clone,
      description: form.description,
    })
    createOpen.value = false
    await loadProjects()
    ElMessage.success('项目已添加，仓库开始克隆')
    window.setTimeout(loadProjects, 2500)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '添加失败')
  } finally {
    saving.value = false
  }
}

async function cloneRepo(repo: any) {
  if (!selected.value) return
  try {
    await client.post(`/projects/${selected.value.id}/repos/${repo.id}/clone`)
    await loadProjects()
    ElMessage.success('克隆完成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '克隆失败')
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
  runForm.engine = 'builtin'
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
      engine: runForm.engine,
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

onMounted(async () => {
  await loadProjects()
  const id = Number(route.query.project)
  if (Number.isFinite(id) && id > 0) {
    if (!projects.value.some((p) => p.id === id)) {
      try {
        const { data } = await client.get(`/projects/${id}`)
        projects.value.unshift(data)
      } catch { /* ignore invalid deep link */ }
    }
    if (projects.value.some((p) => p.id === id)) selectProject(id)
  }
})
onUnmounted(stopRunPolling)
</script>

<style scoped>
.projects-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.projects-header .sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.header-actions { display: flex; gap: 8px; flex-shrink: 0; }
.repo-list { display: flex; flex-direction: column; gap: 8px; }
.repo-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 8px 10px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; }
.repo-main { display: flex; align-items: baseline; gap: 8px; flex: 1; min-width: 240px; flex-wrap: wrap; }
.repo-name { font-weight: 600; }
.repo-path { font-family: monospace; font-size: 12px; color: var(--el-text-color-secondary); }
.repo-url { font-size: 12px; color: var(--el-text-color-secondary); }
.repo-error { width: 100%; font-size: 12px; color: var(--el-color-danger); }
.form-hint { margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
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
.run-detail { font-size: 13px; }
.run-summary { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.detail-block { margin-bottom: 18px; }
.detail-block h4 { margin: 0 0 6px; font-size: 13px; color: #2c3550; }
.detail-block pre { margin: 0; background: #f7f9fc; border: 1px solid #edf0f5; border-radius: 8px; padding: 10px 12px; font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; color: #2c3550; max-height: 300px; overflow: auto; }
.detail-block pre.error { background: #fff5f5; border-color: #ffd6d6; color: #c45656; }
.detail-block .args { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: #606266; }
.run-footer { display: flex; justify-content: flex-end; gap: 8px; padding-top: 12px; border-top: 1px solid #f0f2f5; }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
.section-head h4 { margin: 0; font-size: 14px; color: #1a1a2e; }
.section-head p { margin: 4px 0 0; font-size: 12px; color: #909399; }
.empty-hint { font-size: 12px; color: #909399; text-align: center; padding: 24px 8px; }
.empty-main { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; min-height: 320px; color: #909399; }
.empty-main h3 { margin: 4px 0 0; color: #606266; font-size: 15px; }
.empty-main p { margin: 0; font-size: 12px; }
@media (max-width: 980px) {
  .repo-list { display: flex; flex-direction: column; gap: 8px; }
.repo-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 8px 10px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; }
.repo-main { display: flex; align-items: baseline; gap: 8px; flex: 1; min-width: 240px; flex-wrap: wrap; }
.repo-name { font-weight: 600; }
.repo-path { font-family: monospace; font-size: 12px; color: var(--el-text-color-secondary); }
.repo-url { font-size: 12px; color: var(--el-text-color-secondary); }
.repo-error { width: 100%; font-size: 12px; color: var(--el-color-danger); }
.form-hint { margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
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
