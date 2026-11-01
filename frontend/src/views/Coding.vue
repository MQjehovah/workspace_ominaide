<template>
  <div class="coding-page">
    <div class="page-head">
      <div>
        <h2>Coding Agent</h2>
        <p class="sub">后端执行 · 自动验证 · 分支提交推送</p>
      </div>
      <el-button size="small" @click="reload">刷新</el-button>
    </div>

    <div class="layout">
      <aside class="history">
        <div class="history-head">
          <span>任务历史</span>
          <el-button link size="small" @click="newTask">新任务</el-button>
        </div>
        <div v-if="!history.length" class="history-empty">还没有任务</div>
        <button
          v-for="t in history"
          :key="t.task_id"
          class="history-item"
          :class="{ active: t.task_id === taskId }"
          @click="selectTask(t)"
        >
          <div class="history-row">
            <i class="dot" :class="t.status"></i>
            <span class="history-project">{{ t.project_name || t.project }}</span>
            <span class="history-time">{{ shortTime(t.started_ts) }}</span>
          </div>
          <div class="history-input">{{ t.input || '（无描述）' }}</div>
          <div class="history-meta">
            <span>{{ statusLabel(t.status) }}</span>
            <span v-if="t.branch">· {{ t.branch }}</span>
          </div>
        </button>
      </aside>

      <main class="main">
        <el-card shadow="never" class="form-card">
          <div class="row">
            <span class="label">项目</span>
            <el-select v-model="project" :disabled="isContinuation || running" placeholder="选择工作区项目" style="flex: 1">
              <el-option v-for="p in projects" :key="p.path" :label="`${p.name} — ${p.path}`" :value="p.path" />
            </el-select>
          </div>
          <el-input
            v-model="input"
            type="textarea"
            :rows="4"
            :placeholder="isContinuation ? '在这个任务的基础上继续，例如：把刚才的实现补上单元测试' : '描述要完成的开发任务，例如：修复登录接口在 token 过期时的空指针，并补测试'"
            class="task-input"
          />
          <div class="actions">
            <el-button
              type="primary"
              :loading="running"
              :disabled="!project || !input.trim()"
              @click="submit"
            >
              {{ isContinuation ? '继续此任务' : '开始执行' }}
            </el-button>
            <el-button v-if="running" type="danger" plain @click="cancel">取消</el-button>
            <el-button v-if="isContinuation" link @click="newTask">开始新任务</el-button>
            <span v-if="taskId" class="task-id">{{ taskId }}</span>
          </div>
          <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="alert" />
        </el-card>

        <el-card v-if="taskId && (events.length || output)" shadow="never" class="log-card">
          <template #header>
            <div class="log-head">
              <span>执行过程</span>
              <div class="log-tags">
                <el-tag v-if="delivery" size="small" :type="delivery?.ok ? 'success' : 'warning'">
                  {{ deliveryText }}
                </el-tag>
                <el-tag :type="statusType" size="small">{{ statusText }}</el-tag>
              </div>
            </div>
          </template>
          <div ref="logEl" class="events">
            <div v-for="(ev, i) in events" :key="i" class="event" :class="ev.event">
              <el-tag size="small" :type="tagType(ev.event)">{{ eventLabel(ev.event) }}</el-tag>
              <span class="event-text">{{ eventText(ev) }}</span>
            </div>
          </div>
          <pre v-if="output" class="output">{{ output }}</pre>
        </el-card>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import client from '@/api/client'

const projects = ref<any[]>([])
const project = ref('')
const input = ref('')
const running = ref(false)
const taskId = ref('')
const events = ref<any[]>([])
const output = ref('')
const error = ref('')
const history = ref<any[]>([])
const logEl = ref<HTMLElement | null>(null)
const viewStatus = ref('')

let ws: WebSocket | null = null
let reconnectTimer: any = null
let disposed = false

const isContinuation = computed(() =>
  !!taskId.value && !running.value && ['done', 'failed', 'cancelled'].includes(viewStatus.value)
)

const delivery = computed(() => {
  const items = events.value.filter((ev) => ev.event === 'delivery')
  if (!items.length) return null
  const last = items[items.length - 1].data || {}
  const ok = items.every((ev) => ev.data?.ok !== false)
  return { ...last, ok }
})

const deliveryText = computed(() => {
  if (!delivery.value) return ''
  const d: any = delivery.value
  const map: Record<string, string> = {
    skipped: '无需交付', verify: '验证中', verify_passed: '验证通过', verify_failed: '验证失败',
    branch: '已建分支', commit: '已提交', push: '已推送', push_failed: '推送失败',
    pr: 'PR 已生成', commit_failed: '提交失败', branch_failed: '建分支失败',
    push_skipped: '未推送', sensitive_skipped: '已排除敏感文件', stage_failed: '暂存失败',
  }
  return map[d.stage] || d.stage || '交付'
})

const statusText = computed(() => {
  if (running.value) return '执行中'
  if (error.value) return '失败'
  if (taskId.value) return '已完成'
  return '空闲'
})
const statusType = computed(() => {
  if (running.value) return 'warning'
  if (error.value) return 'danger'
  return 'success'
})

const STATUS_LABEL: Record<string, string> = {
  running: '执行中', done: '已完成', failed: '失败', cancelled: '已取消',
}
function statusLabel(status: string) {
  return STATUS_LABEL[status] || status
}

const EVENT_LABEL: Record<string, string> = {
  started: '开始', milestone: '阶段', tool: '工具', file: '文件',
  output: '输出', delivery: '交付', done: '完成', failed: '失败',
}
function eventLabel(event: string) {
  return EVENT_LABEL[event] || event
}

function tagType(event: string) {
  if (event === 'failed') return 'danger'
  if (event === 'delivery') return 'success'
  if (event === 'milestone') return 'warning'
  if (event === 'file') return 'success'
  return 'info'
}

const STAGE_LABEL: Record<string, string> = {
  context: '读取项目快照', executing: '执行中', queued: '排队等待', cancelled: '已取消',
}

function eventText(ev: any) {
  const d = ev?.data || {}
  if (ev.event === 'tool') return `${d.name || ''} ${d.detail || ''}`.trim()
  if (ev.event === 'file') return `${d.action || ''} ${d.path || ''}`.trim()
  if (ev.event === 'milestone') {
    const label = STAGE_LABEL[d.stage] || d.stage || ''
    return d.detail ? `${label} · ${d.detail}` : label
  }
  if (ev.event === 'failed') return d.error || ''
  if (ev.event === 'delivery') {
    const labels: Record<string, string> = {
      skipped: '跳过', verify: '运行验证', verify_passed: '验证通过', verify_failed: '验证失败',
      branch: '创建分支', commit: '提交', push: '推送', push_failed: '推送失败', pr: 'PR',
      commit_failed: '提交失败', branch_failed: '建分支失败', push_skipped: '跳过推送',
      sensitive_skipped: '排除敏感文件', stage_failed: '暂存失败', repo: '仓库检查',
    }
    return `${labels[d.stage] || d.stage || ''}${d.detail ? ' · ' + d.detail : ''}`
  }
  if (ev.event === 'output') return String(d.chunk || '').trim().slice(0, 160)
  return ''
}

function shortTime(ts: number) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (d.toDateString() === now.toDateString()) return hm
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${hm}`
}

async function loadProjects() {
  error.value = ''
  try {
    const r = await client.get('/vibecoding/projects')
    projects.value = r.data.projects || []
    if (!project.value && projects.value.length) project.value = projects.value[0].path
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '无法获取工作区项目'
  }
}

async function loadHistory() {
  try {
    const r = await client.get('/vibecoding/tasks', { params: { limit: 30 } })
    history.value = r.data.tasks || []
  } catch { }
}

function reload() {
  loadProjects()
  loadHistory()
}

async function selectTask(task: any) {
  if (running.value) return
  error.value = ''
  try {
    const r = await client.get(`/vibecoding/tasks/${task.task_id}`)
    const data = r.data
    taskId.value = data.task_id
    project.value = data.project
    input.value = ''
    events.value = data.events || []
    output.value = data.output || ''
    running.value = data.status === 'running'
    viewStatus.value = data.status || ''
    if (running.value) {
      error.value = '该任务仍在执行，请等待完成或取消'
    }
    nextTick(() => {
      if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
    })
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '无法加载任务详情'
  }
}

function newTask() {
  if (running.value) return
  taskId.value = ''
  viewStatus.value = ''
  events.value = []
  output.value = ''
  error.value = ''
  input.value = ''
}

async function submit() {
  if (isContinuation.value) return continueTask()
  return start()
}

async function start() {
  error.value = ''
  events.value = []
  output.value = ''
  running.value = true
  viewStatus.value = 'running'
  try {
    const r = await client.post('/vibecoding/tasks', {
      project: project.value,
      input: input.value,
      source: 'web',
    })
    taskId.value = r.data.task_id
    loadHistory()
  } catch (e: any) {
    running.value = false
    error.value = e?.response?.data?.detail || '派发失败'
  }
}

async function continueTask() {
  error.value = ''
  const parent = taskId.value
  const text = input.value.trim()
  if (!parent || !text) return
  running.value = true
  viewStatus.value = 'running'
  events.value = []
  output.value = ''
  try {
    const r = await client.post(`/vibecoding/tasks/${parent}/continue`, { input: text })
    taskId.value = r.data.task_id
    input.value = ''
    loadHistory()
  } catch (e: any) {
    running.value = false
    error.value = e?.response?.data?.detail || '无法继续该任务'
    taskId.value = parent
  }
}

function cancel() {
  if (!taskId.value || ws?.readyState !== WebSocket.OPEN) return
  ws.send(JSON.stringify({
    channel: 'vibecoding',
    type: 'task.control',
    task_id: taskId.value,
    action: 'cancel',
  }))
}

function handleEvent(ev: any) {
  if (ev.task_id && taskId.value && ev.task_id !== taskId.value) return
  events.value.push(ev)
  if (ev.event === 'output') output.value = (output.value + (ev.data?.chunk || '')).slice(-80000)
  if (ev.event === 'done') {
    running.value = false
    viewStatus.value = 'done'
    if (ev.data?.output) output.value = String(ev.data.output)
    loadHistory()
  }
  if (ev.event === 'failed') {
    running.value = false
    viewStatus.value = 'failed'
    error.value = ev.data?.error || '执行失败'
    loadHistory()
  }
  if (events.value.length > 400) events.value.splice(0, events.value.length - 400)
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

function connect() {
  if (disposed) return
  const token = localStorage.getItem('token')
  if (!token) return
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const base = import.meta.env.BASE_URL.replace(/\/$/, '')
  ws = new WebSocket(`${proto}://${window.location.host}${base}/ws/host?role=viewer&token=${encodeURIComponent(token)}`)
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data?.channel !== 'vibecoding' || data?.type !== 'task.event') return
      // The HTTP response may arrive after the first event: adopt the running task id.
      if (!taskId.value) {
        if (!running.value) return
        taskId.value = data.task_id
      }
      if (data.task_id === taskId.value) handleEvent(data)
    } catch { }
  }
  ws.onclose = () => {
    if (!disposed) reconnectTimer = setTimeout(connect, 5000)
  }
  ws.onerror = () => ws?.close()
}

onMounted(() => {
  loadProjects()
  loadHistory()
  connect()
})

onUnmounted(() => {
  disposed = true
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (ws) ws.close()
})
</script>

<style scoped>
.coding-page { padding: 20px; max-width: 1280px; margin: 0 auto; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 14px; }
.page-head h2 { margin: 0; font-size: 18px; }
.sub { margin: 4px 0 0; font-size: 12px; color: #909399; }

.layout { display: grid; grid-template-columns: 280px 1fr; gap: 16px; align-items: start; }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .history { max-height: 220px; }
}

.history { border: 1px solid #ebeef5; border-radius: 8px; background: #fff; overflow: hidden; }
.history-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; font-size: 13px; font-weight: 600; border-bottom: 1px solid #f2f3f5; }
.history-empty { padding: 18px 12px; font-size: 12px; color: #a8abb2; }
.history-item { display: block; width: 100%; text-align: left; padding: 10px 12px; border: 0; border-bottom: 1px solid #f5f6f7; background: transparent; cursor: pointer; font: inherit; }
.history-item:hover { background: #f7f9fc; }
.history-item.active { background: #ecf5ff; box-shadow: inset 3px 0 0 #409eff; }
.history-row { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.history-project { flex: 1; font-weight: 600; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-time { color: #a8abb2; font-size: 11px; }
.history-input { margin-top: 4px; font-size: 12px; color: #606266; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-meta { margin-top: 4px; font-size: 11px; color: #a8abb2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: #c0c4cc; flex: none; }
.dot.running { background: #e6a23c; box-shadow: 0 0 6px #e6a23c; }
.dot.done { background: #67c23a; }
.dot.failed { background: #f56c6c; }
.dot.cancelled { background: #909399; }

.form-card { margin-bottom: 14px; }
.row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.label { font-size: 13px; color: #606266; white-space: nowrap; }
.task-input { margin-bottom: 12px; }
.actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.task-id { font-size: 12px; color: #909399; }
.alert { margin-top: 12px; }

.log-head { display: flex; align-items: center; justify-content: space-between; }
.log-tags { display: flex; gap: 6px; align-items: center; }
.events { max-height: 340px; overflow-y: auto; margin-bottom: 10px; }
.event { display: flex; align-items: flex-start; gap: 8px; padding: 5px 0; border-bottom: 1px dashed #f0f0f0; font-size: 12px; }
.event-text { color: #606266; word-break: break-all; }
.event.delivery .event-text { color: #529b2e; }
.event.failed .event-text { color: #f56c6c; }
.output { margin: 0; max-height: 380px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: #303133; background: #fafafa; border-radius: 6px; padding: 10px; }
</style>
