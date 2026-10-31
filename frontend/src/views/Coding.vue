<template>
  <div class="coding-page">
    <div class="page-head">
      <h2>Coding Agent</h2>
      <el-button size="small" @click="loadProjects">刷新项目</el-button>
    </div>

    <el-card shadow="never" class="form-card">
      <div class="row">
        <span class="label">项目</span>
        <el-select v-model="project" placeholder="选择桌面端已注册的项目" style="flex: 1">
          <el-option v-for="p in projects" :key="p.path" :label="`${p.name} — ${p.path}`" :value="p.path" />
        </el-select>
      </div>
      <el-input
        v-model="input"
        type="textarea"
        :rows="4"
        placeholder="描述要完成的开发任务，例如：修复登录接口在 token 过期时的空指针，并补测试"
        class="task-input"
      />
      <div class="actions">
        <el-button type="primary" :loading="running" :disabled="!project || !input.trim()" @click="start">
          开始执行
        </el-button>
        <el-button v-if="running" type="danger" plain @click="cancel">取消</el-button>
        <span v-if="taskId" class="task-id">任务 {{ taskId }}</span>
      </div>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="alert" />
    </el-card>

    <el-card v-if="events.length || output" shadow="never" class="log-card">
      <template #header>
        <div class="log-head">
          <span>执行过程</span>
          <el-tag :type="statusType" size="small">{{ statusText }}</el-tag>
        </div>
      </template>
      <div ref="logEl" class="events">
        <div v-for="(ev, i) in events" :key="i" class="event">
          <el-tag size="small" :type="tagType(ev.event)">{{ ev.event }}</el-tag>
          <span class="event-text">{{ eventText(ev) }}</span>
        </div>
      </div>
      <pre v-if="output" class="output">{{ output }}</pre>
    </el-card>
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
const logEl = ref<HTMLElement | null>(null)

let ws: WebSocket | null = null
let reconnectTimer: any = null
let disposed = false

const statusText = computed(() => running.value ? '执行中' : (error.value ? '失败' : '空闲'))
const statusType = computed(() => running.value ? 'warning' : (error.value ? 'danger' : 'success'))

function tagType(event: string) {
  if (event === 'failed' || event === 'milestone') return 'warning'
  if (event === 'file') return 'success'
  return 'info'
}

function eventText(ev: any) {
  const d = ev?.data || {}
  if (ev.event === 'tool') return `${d.name || ''} ${d.detail || ''}`.trim()
  if (ev.event === 'file') return `${d.action || ''} ${d.path || ''}`.trim()
  if (ev.event === 'milestone') return d.stage || ''
  if (ev.event === 'failed') return d.error || ''
  return ''
}

async function loadProjects() {
  error.value = ''
  try {
    const r = await client.get('/vibecoding/projects')
    projects.value = r.data.projects || []
    if (!project.value && projects.value.length) project.value = projects.value[0].path
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '无法获取项目，请确认桌面端在线'
  }
}

async function start() {
  error.value = ''
  events.value = []
  output.value = ''
  taskId.value = ''
  running.value = true
  try {
    const r = await client.post('/vibecoding/tasks', {
      project: project.value,
      input: input.value,
      source: 'web',
    })
    taskId.value = r.data.task_id
  } catch (e: any) {
    running.value = false
    error.value = e?.response?.data?.detail || '派发失败'
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
  events.value.push(ev)
  if (ev.event === 'output') output.value = (output.value + (ev.data?.chunk || '')).slice(-80000)
  if (ev.event === 'done') {
    running.value = false
    if (ev.data?.output) output.value = String(ev.data.output)
  }
  if (ev.event === 'failed') {
    running.value = false
    error.value = ev.data?.error || '执行失败'
  }
  if (events.value.length > 300) events.value.splice(0, events.value.length - 300)
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
      if (data?.channel !== 'vibecoding') return
      if (data?.type === 'task.event' && (!taskId.value || data.task_id === taskId.value)) {
        handleEvent(data)
      }
    } catch { }
  }
  ws.onclose = () => {
    if (!disposed) reconnectTimer = setTimeout(connect, 5000)
  }
  ws.onerror = () => ws?.close()
}

onMounted(() => {
  loadProjects()
  connect()
})

onUnmounted(() => {
  disposed = true
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (ws) ws.close()
})
</script>

<style scoped>
.coding-page { padding: 20px; max-width: 1100px; margin: 0 auto; }
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.page-head h2 { margin: 0; font-size: 18px; }
.form-card { margin-bottom: 14px; }
.row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.label { font-size: 13px; color: #606266; white-space: nowrap; }
.task-input { margin-bottom: 12px; }
.actions { display: flex; align-items: center; gap: 10px; }
.task-id { font-size: 12px; color: #909399; }
.alert { margin-top: 12px; }
.log-head { display: flex; align-items: center; justify-content: space-between; }
.events { max-height: 320px; overflow-y: auto; margin-bottom: 10px; }
.event { display: flex; align-items: flex-start; gap: 8px; padding: 4px 0; border-bottom: 1px dashed #f0f0f0; font-size: 12px; }
.event-text { color: #606266; word-break: break-all; }
.output { margin: 0; max-height: 360px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; color: #303133; background: #fafafa; border-radius: 6px; padding: 10px; }
</style>
