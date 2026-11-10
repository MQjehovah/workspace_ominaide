<template>
  <div class="page-wrapper workspaces">
    <div class="page-header">
      <div>
        <h2>工作空间</h2>
        <p class="sub">模板化 Docker 容器：隔离环境、终端、端口访问和依赖预装。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" @click="reload">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建工作空间</el-button>
      </div>
    </div>

    <div class="page-card">
      <el-table :data="workspaces" v-loading="loading" empty-text="还没有工作空间">
        <el-table-column prop="name" label="名称" min-width="160">
          <template #default="{ row }">
            <div class="ws-name">{{ row.name }}</div>
            <div class="ws-id">{{ row.id }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="template" label="模板" width="130" />
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <el-tag :type="statusType(row)" effect="light">{{ statusText(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="project_path" label="项目目录" min-width="260" show-overflow-tooltip />
        <el-table-column label="端口" width="220">
          <template #default="{ row }">
            <div class="port-row">
              <el-select v-model="portInputs[row.id]" size="small" style="width: 110px" placeholder="端口">
                <el-option v-for="p in templatePorts(row.template)" :key="p" :label="String(p)" :value="p" />
              </el-select>
              <el-button size="small" :icon="Link" @click="openPort(row)">打开</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="330" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :icon="Monitor" @click="openTerminal(row)">终端</el-button>
            <el-button
              v-if="canStart(row)"
              size="small"
              type="success"
              :icon="VideoPlay"
              @click="start(row)"
            >启动</el-button>
            <el-button
              v-else
              size="small"
              :icon="VideoPause"
              :disabled="row.status === 'creating' || row.status === 'preparing'"
              @click="stop(row)"
            >停止</el-button>
            <el-button size="small" type="danger" :icon="Delete" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="createOpen" title="新建工作空间" width="560px">
      <el-form :model="form" label-width="96px">
        <el-form-item label="模板">
          <el-select v-model="form.template" style="width: 100%">
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="`${t.name} · ${t.image}`"
              :value="t.id"
            />
          </el-select>
          <div class="template-desc">{{ selectedTemplate?.description }}</div>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="例如 workspace_ominaide" />
        </el-form-item>
        <el-form-item label="项目目录">
          <el-select
            v-model="form.project_path"
            filterable
            allow-create
            clearable
            placeholder="留空则创建空工作空间"
            style="width: 100%"
          >
            <el-option v-for="p in projects" :key="p.id" :label="`${p.name} · ${p.path}`" :value="p.path" />
          </el-select>
        </el-form-item>
        <el-form-item label="空闲回收">
          <el-input-number v-model="form.ttl_seconds" :min="300" :max="86400" :step="300" />
          <span class="ttl-hint">秒</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="create">创建</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="terminalOpen" :title="terminalTitle" size="72%" @closed="closeTerminal">
      <div ref="terminalEl" class="terminal-host"></div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Link, Monitor, Plus, Refresh, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import client from '@/api/client'
import { apiUrl } from '@/api/base'
import { getAccessToken } from '@/api/tokens'

interface Template {
  id: string
  name: string
  description: string
  image: string
  ports: number[]
  has_build: boolean
}

interface Workspace {
  id: string
  owner_id: string
  template: string
  name: string
  project_path: string
  status: string
  created_at: number
  last_used_at: number
  ttl_seconds: number
  error?: string | null
}

interface Project {
  id: number
  name: string
  path: string
}

const loading = ref(false)
const creating = ref(false)
const createOpen = ref(false)
const workspaces = ref<Workspace[]>([])
const templates = ref<Template[]>([])
const projects = ref<Project[]>([])
const portInputs = reactive<Record<string, number | undefined>>({})

const form = reactive({
  template: 'omniaide-base',
  name: '',
  project_path: '',
  ttl_seconds: 1800,
})

const selectedTemplate = computed(() => templates.value.find(t => t.id === form.template))

let pollTimer: number | undefined

function statusText(row: Workspace): string {
  if (row.status === 'error') return '失败'
  return {
    creating: '创建中',
    building: '构建镜像',
    preparing: '准备环境',
    ready: '运行中',
    stopped: '已停止',
    running: '运行中',
  }[row.status] || row.status
}

function statusType(row: Workspace): 'success' | 'warning' | 'info' | 'danger' {
  if (row.status === 'error') return 'danger'
  if (row.status === 'ready' || row.status === 'running') return 'success'
  if (row.status === 'stopped') return 'info'
  return 'warning'
}

function canStart(row: Workspace): boolean {
  return row.status === 'stopped'
}

function templatePorts(templateId: string): number[] {
  return templates.value.find(t => t.id === templateId)?.ports || []
}

async function loadTemplates() {
  const { data } = await client.get('/sandbox/templates')
  templates.value = data
  if (!templates.value.find(t => t.id === form.template) && templates.value.length) {
    form.template = templates.value[0].id
  }
}

async function loadProjects() {
  const { data } = await client.get('/projects')
  projects.value = data
}

async function loadWorkspaces() {
  loading.value = true
  try {
    const { data } = await client.get('/sandbox/workspaces')
    workspaces.value = data
    for (const ws of data) {
      if (portInputs[ws.id] === undefined) {
        portInputs[ws.id] = templatePorts(ws.template)[0]
      }
    }
    const busy = data.some((w: Workspace) => ['creating', 'building', 'preparing'].includes(w.status))
    window.clearTimeout(pollTimer)
    if (busy) pollTimer = window.setTimeout(loadWorkspaces, 2500)
  } finally {
    loading.value = false
  }
}

async function reload() {
  await Promise.all([loadTemplates(), loadProjects(), loadWorkspaces()])
}

function openCreate() {
  form.name = ''
  form.project_path = ''
  form.ttl_seconds = 1800
  createOpen.value = true
}

async function create() {
  creating.value = true
  try {
    await client.post('/sandbox/workspaces', {
      template: form.template,
      name: form.name || undefined,
      project_path: form.project_path || undefined,
      ttl_seconds: form.ttl_seconds,
    })
    ElMessage.success('工作空间创建中')
    createOpen.value = false
    await loadWorkspaces()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '创建失败')
  } finally {
    creating.value = false
  }
}

async function start(row: Workspace) {
  await client.post(`/sandbox/workspaces/${row.id}/start`)
  ElMessage.success('已启动')
  await loadWorkspaces()
}

async function stop(row: Workspace) {
  await client.post(`/sandbox/workspaces/${row.id}/stop`)
  ElMessage.success('已停止')
  await loadWorkspaces()
}

async function remove(row: Workspace) {
  try {
    await ElMessageBox.confirm(`删除 ${row.name}？项目文件会保留。`, '删除工作空间', { type: 'warning' })
  } catch {
    return
  }
  await client.delete(`/sandbox/workspaces/${row.id}`)
  ElMessage.success('已删除')
  await loadWorkspaces()
}

function openPort(row: Workspace) {
  const port = portInputs[row.id] || templatePorts(row.template)[0]
  if (!port) {
    ElMessage.warning('请选择端口')
    return
  }
  const token = encodeURIComponent(getAccessToken())
  window.open(`${apiUrl(`/sandbox/workspaces/${row.id}/proxy/${port}/`)}?token=${token}`, '_blank')
}

// ---------------------------------------------------------------- terminal

const terminalOpen = ref(false)
const terminalTitle = ref('终端')
const terminalEl = ref<HTMLElement>()
let term: Terminal | null = null
let fitAddon: FitAddon | null = null
let socket: WebSocket | null = null
let resizeHandler: (() => void) | null = null

async function openTerminal(row: Workspace) {
  closeTerminal()
  terminalTitle.value = `${row.name} · ${row.id}`
  terminalOpen.value = true
  await nextTick()
  if (!terminalEl.value) return

  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: 'Menlo, Monaco, Consolas, monospace',
    theme: { background: '#111827', foreground: '#e5e7eb' },
  })
  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(terminalEl.value)
  fitAddon.fit()
  term.focus()

  const token = encodeURIComponent(getAccessToken())
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const path = apiUrl(`/sandbox/workspaces/${row.id}/terminal`)
  const url = `${proto}://${window.location.host}${path}?token=${token}`
  socket = new WebSocket(url)
  socket.binaryType = 'arraybuffer'

  socket.onmessage = event => {
    if (typeof event.data === 'string') term?.write(event.data)
    else term?.write(new Uint8Array(event.data))
  }
  socket.onclose = () => term?.write('\r\n[连接已关闭]\r\n')
  socket.onerror = () => term?.write('\r\n[连接失败]\r\n')

  term.onData(data => {
    if (socket?.readyState === WebSocket.OPEN) socket.send(data)
  })

  resizeHandler = () => {
    if (!fitAddon || !term) return
    fitAddon.fit()
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
    }
  }
  window.addEventListener('resize', resizeHandler)
}

function closeTerminal() {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  resizeHandler = null
  socket?.close()
  socket = null
  term?.dispose()
  term = null
  fitAddon = null
}

onMounted(reload)
onBeforeUnmount(() => {
  window.clearTimeout(pollTimer)
  closeTerminal()
})
</script>

<style scoped>
.workspaces .page-card { padding: 16px; }
.ws-name { font-weight: 600; }
.ws-id { font-size: 12px; color: var(--el-text-color-secondary); font-family: monospace; }
.port-row { display: flex; gap: 8px; align-items: center; }
.template-desc { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.ttl-hint { margin-left: 8px; color: var(--el-text-color-secondary); }
.terminal-host { height: 100%; min-height: 480px; padding: 8px; background: #111827; }
</style>
