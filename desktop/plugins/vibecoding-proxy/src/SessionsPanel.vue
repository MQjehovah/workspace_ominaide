<template>
  <div class="sessions-page">
    <div class="sessions-toolbar">
      <div class="scope-tabs">
        <button :class="['scope-tab', scope === 'local' && 'active']" @click="setScope('local')">
          本机
        </button>
        <button :class="['scope-tab', scope === 'cloud' && 'active']" @click="setScope('cloud')">
          跨设备
        </button>
      </div>

      <button class="btn primary" @click="openCreate()">＋ 新建会话</button>
      <button class="btn" @click="refreshAll">刷新</button>
      <button
        :class="['filter-chip', onlyRunning && 'active']"
        :title="onlyRunning ? '显示全部会话' : '只看运行中的会话'"
        @click="onlyRunning = !onlyRunning"
      >
        <span class="filter-dot"></span> 运行中 {{ runningCount }}
      </button>
      <span class="hint">
        {{ scope === 'local' ? '本机会话，离线可用' : '所有设备的会话，需要联网' }}
      </span>

      <div class="toolbar-right">
        <span class="toolbar-label">项目</span>
        <select v-model="selectedProjectKey" class="proj-select" title="按项目过滤">
          <option value="">全部项目（{{ sessions.length }}）</option>
          <option v-for="p in projects" :key="p.key" :value="p.key">
            {{ p.name }}（{{ p.count }}）{{ scope === 'cloud' ? ` · ${p.machine_name}` : '' }}
          </option>
        </select>
        <button
          class="btn quick-btn"
          :disabled="!!quickCreating"
          :title="selectedProject ? '在选中项目快速开始' : '选择项目后可快速开始'"
          @click="quickStart"
        >
          {{ quickCreating ? '…' : '＋' }}
        </button>
      </div>
    </div>

    <div v-if="scope === 'cloud' && error" class="cloud-error">
      {{ error }}
      <button class="btn sm" @click="setScope('local')">改用本机会话</button>
    </div>

    <div class="sessions-layout">
      <aside class="session-list">
        <div class="pane-head">
          <span>{{ selectedProject ? selectedProject.name : '全部会话' }}</span>
          <span class="pane-count">{{ visibleSessions.length }}</span>
        </div>
        <div
          v-for="s in visibleSessions"
          :key="sessionKey(s)"
          :class="[
            'session-item',
            isRunning(s) && 'running',
            activeKey === sessionKey(s) && 'active',
          ]"
          @click="openSession(s)"
        >
          <div class="session-title-row">
            <span v-if="isRunning(s)" class="run-dot"></span>
            <span class="session-title">{{ s.title }}</span>
          </div>
          <div class="session-path" :title="s.project">{{ s.project || '未指定项目路径' }}</div>
          <div class="session-tags">
            <span class="tag source">{{ sourceLabel(s.agent) }}</span>
            <span :class="['tag', isRunning(s) ? 'running' : 'idle']">
              <span v-if="isRunning(s)" class="mini-spin"></span>
              {{ isRunning(s) ? '运行中' : '空闲' }}
            </span>
            <span v-if="scope === 'cloud' && !selectedProject" class="tag machine">
              {{ s.machine_name || s.machine_id }}
            </span>
            <span class="session-time">{{ timeAgo(s.updated) }}</span>
          </div>
          <button class="session-del" title="删除会话" @click.stop="deleteSession(s)">🗑</button>
        </div>
        <div v-if="!visibleSessions.length" class="pane-empty">
          {{ loading ? '加载中…' : (selectedProject ? '这个项目还没有会话' : '还没有会话') }}
        </div>
      </aside>

      <section class="chat-pane">
        <template v-if="detail">
          <div class="chat-head">
            <div class="chat-head-text">
              <div class="chat-title">{{ detail.session.title || '会话' }}</div>
              <div class="chat-sub">
                <span>{{ sourceLabel(detail.session.agent) }}</span>
                <span> · </span>
                <span :title="detail.session.project">{{ detail.session.project || '未指定项目' }}</span>
                <span v-if="scope === 'cloud'">
                  · {{ machineName(detail.session.machine_id) }}
                </span>
              </div>
            </div>
            <span v-if="detail.running" class="running-badge">
              <span class="mini-spin"></span> 运行中
            </span>
            <button v-if="detail.running" class="btn danger sm" @click="stop">■ 停止</button>
          </div>

          <div ref="messagesEl" class="chat-messages">
            <div v-if="detail.running || detail.liveTools.length" class="live-bar">
              <span v-if="detail.running" class="mini-spin big"></span>
              <span class="live-title">{{ detail.running ? '正在执行' : '最近工具' }}</span>
              <span
                v-for="(tool, ti) in detail.liveTools"
                :key="ti"
                :class="['live-tool', tool.status]"
              >
                <span v-if="tool.status === 'running'" class="mini-spin"></span>
                <span v-else class="tool-mark">{{ tool.status === 'failed' ? '✗' : '✓' }}</span>
                <span class="live-tool-name">{{ tool.name }}</span>
                <span v-if="tool.detail" class="live-tool-detail">{{ tool.detail }}</span>
              </span>
            </div>
            <div v-if="!shownMessages.length && !detail.streaming" class="chat-empty">
              这个会话还没有消息，直接在下面输入继续。
            </div>
            <div v-for="(m, i) in shownMessages" :key="i" :class="['msg', m.role]">
              <div class="bubble">
                <div v-if="m.tools && m.tools.length" class="msg-tools">
                  <span
                    v-for="(t, ti) in m.tools"
                    :key="ti"
                    :class="['tool-chip', toolStatus(t)]"
                  >
                    <span v-if="isToolRunning(t)" class="mini-spin"></span>
                    <span v-else class="tool-mark">{{ toolMark(t) }}</span>
                    <span class="tool-name">{{ toolName(t) }}</span>
                    <span v-if="toolDetail(t)" class="tool-detail">{{ toolDetail(t) }}</span>
                  </span>
                </div>
                <div
                  v-if="m.text"
                  class="md-body"
                  @click="onMarkdownClick"
                  v-html="renderMarkdown(m.text)"
                ></div>
              </div>
            </div>
            <div v-if="detail.streaming" class="msg assistant">
              <div class="bubble streaming">
                <div
                  class="md-body"
                  @click="onMarkdownClick"
                  v-html="renderMarkdown(detail.streaming)"
                ></div>
              </div>
            </div>
          </div>

          <div class="chat-composer">
            <textarea
              v-model="input"
              class="chat-input"
              rows="3"
              placeholder="继续这个会话…（Ctrl+Enter 发送）"
              @keydown.ctrl.enter.prevent="send"
              @keydown.meta.enter.prevent="send"
            ></textarea>
            <div class="composer-actions">
              <span class="composer-hint">
                {{ scope === 'local' ? '在本机执行' : `在 ${machineName(detail.session.machine_id)} 上执行` }}
              </span>
              <button class="btn primary" :disabled="!input.trim() || sending" @click="send">
                {{ sending ? '发送中…' : '发送' }}
              </button>
            </div>
          </div>
        </template>
        <div v-else class="chat-empty">
          {{ scope === 'local'
            ? '选择项目和会话，或直接在选中的项目上点 ＋ 开始开发。'
            : '选择任意设备上的项目和会话，或点 ＋ 开始开发。' }}
        </div>
      </section>
    </div>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <h3>{{ scope === 'local' ? '新建本机会话' : '新建跨设备会话' }}</h3>

        <template v-if="scope === 'cloud'">
          <label class="field-label">设备</label>
          <select v-model="createMachine" class="proj-select wide" @change="loadCloudMeta">
            <option v-for="m in onlineMachines" :key="m.machine_id" :value="m.machine_id">
              {{ m.name }}
            </option>
          </select>
        </template>

        <label class="field-label">项目</label>
        <select v-if="!manualProject" v-model="createProject" class="proj-select wide">
          <option value="">选择项目…</option>
          <option v-for="p in createProjects" :key="p.path" :value="p.path">
            {{ projectName(p.path) }} — {{ p.path }}
          </option>
        </select>
        <input
          v-else
          v-model="createProject"
          class="text-input"
          placeholder="输入项目绝对路径"
        />
        <label class="manual-toggle">
          <input type="checkbox" v-model="manualProject" /> 手动输入路径
        </label>

        <label class="field-label">会话标题（可选）</label>
        <input v-model="createTitle" class="text-input" placeholder="例如：修复登录空指针" />
        <div v-if="metaError" class="meta-error">{{ metaError }}</div>
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button
            class="btn primary"
            :disabled="creating || !createProject || (scope === 'cloud' && !createMachine)"
            @click="createSession"
          >
            {{ creating ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import MarkdownIt from 'markdown-it'

const props = defineProps<{ execute?: Function; projects?: any[] }>()

const api = () => (window as any).mqbox?.api

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const markdownCache = new Map<string, string>()

function renderMarkdown(text: string): string {
  if (!text) return ''
  const cached = markdownCache.get(text)
  if (cached !== undefined) return cached
  let html = ''
  try {
    html = md.render(text)
  } catch {
    html = `<pre>${text.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>`
  }
  if (markdownCache.size > 240) markdownCache.clear()
  markdownCache.set(text, html)
  return html
}

function toolObj(tool: any) {
  if (typeof tool === 'string') return { name: tool, status: '', detail: '' }
  return tool || {}
}

function toolName(tool: any) {
  return toolObj(tool).name || 'tool'
}

function toolDetail(tool: any) {
  return toolObj(tool).detail || ''
}

function toolStatus(tool: any) {
  const status = toolObj(tool).status
  if (status === 'failed') return 'failed'
  if (status === 'running' || status === 'pending') return 'running'
  if (status === 'completed' || status === 'success') return 'success'
  return ''
}

function isToolRunning(tool: any) {
  const status = toolObj(tool).status
  return status === 'running' || status === 'pending'
}

function toolMark(tool: any) {
  const status = toolObj(tool).status
  if (status === 'failed') return '✗'
  if (status === 'completed' || status === 'success') return '✓'
  return '🛠'
}

function onMarkdownClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  const anchor = target?.closest('a')
  if (!anchor) return
  const href = anchor.getAttribute('href') || ''
  if (!href) return
  event.preventDefault()
  const shell = (window as any).mqbox?.shell
  if (shell?.openExternal) shell.openExternal(href)
}

const scope = ref<'local' | 'cloud'>(
  (localStorage.getItem('vibecoding.scope') as 'local' | 'cloud') || 'local',
)
const sessions = ref<any[]>([])
const machines = ref<any[]>([])
const selectedProjectKey = ref(localStorage.getItem('vibecoding.project.v2') || '')
const activeKey = ref('')
const detail = ref<any>(null)
const input = ref('')
const loading = ref(false)
const sending = ref(false)
const quickCreating = ref('')
const onlyRunning = ref(false)
const error = ref('')
const messagesEl = ref<HTMLElement | null>(null)
let pollTimer: any = null
let tick = 0

const showCreate = ref(false)
const createMachine = ref('')
const createProject = ref('')
const createTitle = ref('')
const createProjects = ref<any[]>([])
const manualProject = ref(false)
const creating = ref(false)
const metaError = ref('')

function projectKey(machineId: string, path: string) {
  return `${machineId}|${path || ''}`
}

function projectName(path: string) {
  if (!path) return '未指定项目'
  const parts = String(path).split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] || path
}

function sourceLabel(agent: string) {
  const value = String(agent || '').toLowerCase()
  if (value === 'opencode') return 'OpenCode'
  if (value === 'codex') return 'Codex'
  if (value === 'claude') return 'Claude Code'
  if (value === 'omniaide') return 'OmniAide'
  return agent || '未知'
}

const machineOptions = computed(() => {
  const map = new Map<string, any>()
  for (const m of machines.value) map.set(m.machine_id, m)
  for (const s of sessions.value) {
    if (!map.has(s.machine_id)) {
      map.set(s.machine_id, {
        machine_id: s.machine_id,
        name: s.machine_name || s.machine_id,
        online: !!s.machine_online,
      })
    }
  }
  return Array.from(map.values())
})
const onlineMachines = computed(() => machineOptions.value.filter((m) => m.online))

const projects = computed(() => {
  const map = new Map<string, any>()
  const ensure = (machineId: string, path: string) => {
    const key = projectKey(machineId, path)
    let item = map.get(key)
    if (!item) {
      const machine = machineOptions.value.find((m) => m.machine_id === machineId)
      item = {
        key,
        machine_id: machineId,
        machine_name: machine?.name || (machineId === 'local' ? '本机' : machineId),
        online: machineId === 'local' || !!machine?.online,
        path: path || '',
        name: projectName(path),
        count: 0,
        running: false,
      }
      map.set(key, item)
    }
    return item
  }
  for (const s of sessions.value) {
    const item = ensure(s.machine_id, s.project || '')
    item.count += 1
    item.running = item.running || !!s.running
  }
  if (scope.value === 'local') {
    for (const project of props.projects || []) {
      ensure('local', project.path)
    }
  }
  return Array.from(map.values()).sort(
    (a, b) =>
      Number(b.running) - Number(a.running) ||
      b.count - a.count ||
      String(a.name).localeCompare(String(b.name)),
  )
})

const selectedProject = computed(() =>
  projects.value.find((p) => p.key === selectedProjectKey.value) || null,
)

function isRunning(session: any) {
  if (activeKey.value === sessionKey(session) && detail.value) {
    return !!detail.value.running
  }
  return !!session.running
}

const runningCount = computed(
  () => sessions.value.filter((session) => isRunning(session)).length,
)

const shownMessages = computed(() => {
  const current = detail.value
  if (!current) return []
  const list = current.messages || []
  const streamingId = current.streamingId
  if (current.streaming && streamingId) {
    return list.filter((message: any) => message.id !== streamingId)
  }
  return list
})

const visibleSessions = computed(() => {
  let list = selectedProject.value
    ? sessions.value.filter(
        (s) =>
          s.machine_id === selectedProject.value.machine_id &&
          (s.project || '') === selectedProject.value.path,
      )
    : sessions.value
  if (onlyRunning.value) list = list.filter((s) => isRunning(s))
  return [...list].sort(
    (a, b) =>
      Number(isRunning(b)) - Number(isRunning(a)) ||
      Number(b.updated || 0) - Number(a.updated || 0),
  )
})

function sessionKey(session: any) {
  return `${scope.value}:${session.machine_id}:${session.id}`
}

function machineName(machineId: string) {
  if (scope.value === 'local' || machineId === 'local') return '本机'
  const hit = machineOptions.value.find((m) => m.machine_id === machineId)
  return hit?.name || machineId
}

function timeAgo(ms: number) {
  if (!ms) return ''
  const diff = Date.now() - Number(ms)
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return `${Math.floor(diff / 86_400_000)} 天前`
}

function persistProject() {
  localStorage.setItem('vibecoding.project.v2', selectedProjectKey.value)
}

async function setScope(next: 'local' | 'cloud') {
  if (scope.value === next) return
  scope.value = next
  localStorage.setItem('vibecoding.scope', next)
  selectedProjectKey.value = ''
  activeKey.value = ''
  detail.value = null
  error.value = ''
  await loadSessions()
}

async function loadSessions() {
  if (scope.value === 'local') {
    loading.value = true
    try {
      const rows = (await props.execute?.('listLocalSessions')) || []
      sessions.value = (Array.isArray(rows) ? rows : []).map((row: any) => ({
        ...row,
        machine_id: 'local',
        machine_name: '本机',
        machine_online: true,
      }))
      machines.value = []
    } catch (e: any) {
      error.value = e?.message || '读取本机会话失败'
    } finally {
      loading.value = false
    }
  } else {
    loading.value = true
    try {
      const res = await api().get('/vibecoding/sessions')
      sessions.value = res?.sessions || []
      machines.value = res?.machines || []
      error.value = ''
    } catch (e: any) {
      error.value = e?.message || '无法读取跨设备会话（可能离线）'
    } finally {
      loading.value = false
    }
  }
  if (
    selectedProjectKey.value &&
    !projects.value.some((p) => p.key === selectedProjectKey.value)
  ) {
    selectedProjectKey.value = ''
    persistProject()
  }
}

async function refreshAll() {
  await loadSessions()
  if (detail.value) await loadDetail()
}

async function openSession(session: any) {
  activeKey.value = sessionKey(session)
  // Opening a session must not change the project filter, otherwise the rest
  // of the list disappears.
  detail.value = {
    session: { ...session },
    messages: [],
    streaming: '',
    streamingId: '',
    liveTools: [],
    running: !!session.running,
  }
  await loadDetail()
}

async function loadDetail() {
  const current = detail.value
  if (!current) return
  const session = current.session
  if (scope.value === 'local') {
    try {
      const res = await props.execute?.('getAgentSession', {
        agent: session.agent,
        sessionId: session.id,
        title: session.title,
        project: session.project,
      })
      if (!res || res.ok === false) {
        error.value = res?.error || '读取本机会话失败'
        return
      }
      const previous = detail.value?.messages?.length || 0
      detail.value = {
        session: {
          ...session,
          ...(res.session || {}),
          machine_id: 'local',
          machine_name: '本机',
        },
        messages: res.messages || [],
        streaming: res.streaming || '',
        streamingId: res.streaming_id || '',
        liveTools: res.live_tools || [],
        running: !!res.session?.running,
      }
      if (
        detail.value.running ||
        detail.value.messages.length !== previous ||
        detail.value.streaming
      ) {
        await nextTick()
        scrollToBottom()
      }
    } catch (e: any) {
      error.value = e?.message || '读取本机会话失败'
    }
    return
  }

  try {
    const res = await api().get(
      `/vibecoding/machines/${encodeURIComponent(session.machine_id)}/sessions/${encodeURIComponent(session.id)}`,
    )
    const previous = detail.value?.messages?.length || 0
    detail.value = {
      session: { ...session, ...(res?.session || {}) },
      messages: res?.messages || [],
      streaming: res?.streaming || '',
      streamingId: res?.streaming_id || '',
      liveTools: res?.live_tools || [],
      running: !!res?.running,
    }
    if (
      detail.value.running ||
      detail.value.messages.length !== previous ||
      detail.value.streaming
    ) {
      await nextTick()
      scrollToBottom()
    }
  } catch (e: any) {
    error.value = e?.message || '读取跨设备会话失败'
  }
}

function scrollToBottom() {
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

async function loadCloudMeta() {
  metaError.value = ''
  createProjects.value = []
  createProject.value = ''
  if (scope.value !== 'cloud' || !createMachine.value) return
  try {
    const projectsRes = await api().get(
      `/vibecoding/machines/${encodeURIComponent(createMachine.value)}/projects`,
    )
    createProjects.value = projectsRes?.projects || []
    if (!createProject.value && createProjects.value.length) {
      createProject.value = createProjects.value[0].path
    }
    manualProject.value = createProjects.value.length === 0
  } catch (e: any) {
    metaError.value = e?.message || '读取设备项目失败，请确认插件已更新'
    manualProject.value = true
  }
}

function loadLocalMeta() {
  metaError.value = ''
  manualProject.value = false
  createProjects.value = (props.projects || []).map((project: any) => ({
    name: project.name,
    path: project.path,
  }))
  if (!createProject.value && createProjects.value.length) {
    createProject.value = createProjects.value[0].path
  }
  manualProject.value = createProjects.value.length === 0
}

async function openCreate(project?: any) {
  error.value = ''
  metaError.value = ''
  createTitle.value = ''
  createProject.value = project?.path || selectedProject.value?.path || ''
  manualProject.value = false

  if (scope.value === 'local') {
    showCreate.value = true
    loadLocalMeta()
    if (createProject.value) createProject.value = project?.path || selectedProject.value?.path || createProject.value
    return
  }

  if (!onlineMachines.value.length) {
    error.value = '没有在线设备'
    return
  }
  const target = project?.machine_id || selectedProject.value?.machine_id
  if (target && onlineMachines.value.some((m) => m.machine_id === target)) {
    createMachine.value = target
  } else if (
    !createMachine.value ||
    !onlineMachines.value.some((m) => m.machine_id === createMachine.value)
  ) {
    createMachine.value = onlineMachines.value[0].machine_id
  }
  showCreate.value = true
  await loadCloudMeta()
  if (project?.path || selectedProject.value?.path) {
    createProject.value = project?.path || selectedProject.value?.path || ''
  }
}

async function quickStart() {
  if (selectedProject.value) {
    await quickCreate(selectedProject.value)
  } else {
    await openCreate()
  }
}

async function quickCreate(project: any) {
  if (quickCreating.value) return
  quickCreating.value = project.key
  error.value = ''
  selectedProjectKey.value = project.key
  persistProject()
  try {
    if (scope.value === 'local') {
      const res = await props.execute?.('createAgentSession', {
        project: project.path,
        title: '',
      })
      if (!res?.ok) throw new Error(res?.error || '创建失败')
      await loadSessions()
      if (res.session?.id) {
        await openSession({
          id: res.session.id,
          machine_id: 'local',
          machine_name: '本机',
          machine_online: true,
          agent: res.session.agent || '',
          title: res.session.title || '新会话',
          project: res.session.project || project.path,
          running: false,
          updated: res.session.updated || Date.now(),
        })
      }
      return
    }

    const res = await api().post(
      `/vibecoding/machines/${encodeURIComponent(project.machine_id)}/sessions`,
      { project: project.path, title: '' },
    )
    await loadSessions()
    const created = res?.session
    if (created?.id) {
      await openSession({
        id: created.id,
        machine_id: project.machine_id,
        machine_name: project.machine_name,
        machine_online: true,
        agent: '',
        title: created.title || '新会话',
        project: created.directory || project.path,
        running: false,
        updated: Date.now(),
      })
    }
  } catch (e: any) {
    error.value = e?.message || '创建失败'
  } finally {
    quickCreating.value = ''
  }
}

async function createSession() {
  if (creating.value) return
  creating.value = true
  metaError.value = ''
  try {
    let created: any = null
    if (scope.value === 'local') {
      const res = await props.execute?.('createAgentSession', {
        project: createProject.value,
        title: createTitle.value,
      })
      if (!res?.ok) throw new Error(res?.error || '创建失败')
      created = {
        id: res.session?.id,
        machine_id: 'local',
        machine_name: '本机',
        machine_online: true,
        agent: res.session?.agent || '',
        title: res.session?.title || createTitle.value || '新会话',
        project: res.session?.project || createProject.value,
        running: false,
        updated: res.session?.updated || Date.now(),
      }
    } else {
      const res = await api().post(
        `/vibecoding/machines/${encodeURIComponent(createMachine.value)}/sessions`,
        {
          project: createProject.value,
          title: createTitle.value,
        },
      )
      created = {
        id: res?.session?.id,
        machine_id: createMachine.value,
        machine_name: machineName(createMachine.value),
        machine_online: true,
        agent: '',
        title: res?.session?.title || createTitle.value || '新会话',
        project: res?.session?.directory || createProject.value,
        running: false,
        updated: Date.now(),
      }
    }
    showCreate.value = false
    await loadSessions()
    if (created?.id) {
      const createdKey = projectKey(created.machine_id, created.project || '')
      if (selectedProjectKey.value && selectedProjectKey.value !== createdKey) {
        selectedProjectKey.value = createdKey
        persistProject()
      }
      await openSession(created)
    }
  } catch (e: any) {
    metaError.value = e?.message || '创建失败'
  } finally {
    creating.value = false
  }
}

async function deleteSession(session: any) {
  if (!confirm(`删除会话「${session.title}」？`)) return
  try {
    if (scope.value === 'local') {
      await props.execute?.('deleteAgentSession', {
        agent: session.agent,
        sessionId: session.id,
      })
    } else {
      await api().delete(
        `/vibecoding/machines/${encodeURIComponent(session.machine_id)}/sessions/${encodeURIComponent(session.id)}`,
      )
    }
    if (activeKey.value === sessionKey(session)) {
      activeKey.value = ''
      detail.value = null
    }
    await loadSessions()
  } catch (e: any) {
    error.value = e?.message || '删除失败'
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || !detail.value || sending.value) return
  sending.value = true
  error.value = ''
  const session = detail.value.session
  try {
    if (scope.value === 'local') {
      const res = await props.execute?.('sendAgentMessage', {
        agent: session.agent,
        sessionId: session.id,
        text,
      })
      if (!res?.ok) throw new Error(res?.error || '发送失败')
    } else {
      await api().post(
        `/vibecoding/machines/${encodeURIComponent(session.machine_id)}/sessions/${encodeURIComponent(session.id)}/prompt`,
        { text },
      )
    }
    input.value = ''
    await loadDetail()
    await loadSessions()
  } catch (e: any) {
    error.value = e?.message || '发送失败'
  } finally {
    sending.value = false
  }
}

async function stop() {
  if (!detail.value) return
  const session = detail.value.session
  try {
    if (scope.value === 'local') {
      await props.execute?.('stopAgentMessage', {
        agent: session.agent,
        sessionId: session.id,
      })
    } else {
      await api().post(
        `/vibecoding/machines/${encodeURIComponent(session.machine_id)}/sessions/${encodeURIComponent(session.id)}/interrupt`,
        {},
      )
    }
    await loadDetail()
  } catch (e: any) {
    error.value = e?.message || '停止失败'
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (detail.value) await loadDetail()
    tick += 1
    if (tick % 5 === 0) await loadSessions()
  }, 1200)
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}

onMounted(async () => {
  await loadSessions()
  startPolling()
})

onUnmounted(stopPolling)
</script>

<style scoped>
.sessions-page { display:flex; flex-direction:column; gap:12px; }
.sessions-toolbar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.scope-tabs { display:flex; gap:4px; background:#f1f5f9; border-radius:8px; padding:3px; }
.scope-tab { border:none; background:transparent; color:#64748b; border-radius:6px; padding:5px 12px; font-size:12px; cursor:pointer; }
.scope-tab.active { background:#fff; color:#4f46e5; box-shadow:0 1px 4px rgba(15,23,42,.08); font-weight:600; }
.hint { font-size:10.5px; color:#94a3b8; }
.filter-chip { display:flex; align-items:center; gap:5px; padding:5px 10px; border:1px solid #e2e8f0; border-radius:6px; background:#fff; color:#64748b; font-size:11.5px; cursor:pointer; }
.filter-chip.active { background:#f0fdf4; border-color:#86efac; color:#15803d; font-weight:600; }
.filter-dot { width:7px; height:7px; border-radius:50%; background:#22c55e; }
.mini-spin { width:9px; height:9px; border:1.5px solid currentColor; border-top-color:transparent; border-radius:50%; display:inline-block; animation:spin 0.8s linear infinite; vertical-align:middle; }
.mini-spin.big { width:12px; height:12px; border-width:2px; color:#16a34a; }
@keyframes spin { to { transform:rotate(360deg); } }
@keyframes pulse { 0%,100% { box-shadow:0 0 0 0 rgba(34,197,94,.5); } 50% { box-shadow:0 0 0 4px rgba(34,197,94,0); } }
.toolbar-right { display:flex; align-items:center; gap:6px; margin-left:auto; }
.toolbar-label { font-size:11px; color:#64748b; }
.proj-select { min-width:170px; max-width:280px; padding:6px 8px; border:1px solid #e2e8f0; border-radius:6px; font-size:12px; background:#fff; }
.proj-select.wide { width:100%; max-width:none; margin-bottom:8px; }
.quick-btn { padding:4px 10px; }
.cloud-error { display:flex; align-items:center; gap:10px; background:#fffbeb; border:1px solid #fde68a; color:#92400e; border-radius:8px; padding:7px 10px; font-size:11.5px; }
.sessions-layout { display:grid; grid-template-columns:360px 1fr; gap:10px; min-height:calc(100vh - 220px); }
.session-list { border:1px solid #e2e8f0; border-radius:10px; background:#fff; overflow-y:auto; max-height:calc(100vh - 220px); }
.pane-head { display:flex; align-items:center; justify-content:space-between; padding:9px 12px; font-size:11.5px; font-weight:700; color:#475569; border-bottom:1px solid #f1f5f9; position:sticky; top:0; background:#fff; z-index:1; }
.pane-count { font-size:10px; color:#94a3b8; font-weight:500; }
.session-item { position:relative; padding:10px 32px 10px 12px; border-bottom:1px solid #f1f5f9; cursor:pointer; }
.session-item:hover { background:#f8fafc; }
.session-item.active { background:#eef2ff; border-left:3px solid #6366f1; }
.session-item.running { background:#f0fdf4; }
.session-item.running.active { background:#eef2ff; }
.session-item.running .run-dot { animation:pulse 1.4s infinite; }
.session-item.running .tag.running { display:inline-flex; align-items:center; gap:4px; font-weight:600; }
.session-title-row { display:flex; align-items:center; gap:5px; }
.session-title { font-size:12.5px; font-weight:600; color:#1e293b; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.run-dot { width:6px; height:6px; flex-shrink:0; border-radius:50%; background:#22c55e; }
.session-path { margin-top:3px; font-size:10px; color:#94a3b8; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.session-tags { display:flex; align-items:center; gap:5px; margin-top:5px; flex-wrap:wrap; }
.tag { font-size:9px; line-height:15px; padding:0 5px; border-radius:4px; background:#f1f5f9; color:#64748b; }
.tag.source { background:#eef2ff; color:#4f46e5; }
.tag.running { background:#dcfce7; color:#15803d; }
.tag.idle { background:#f1f5f9; color:#64748b; }
.tag.machine { background:#fef3c7; color:#b45309; }
.session-time { font-size:9px; color:#94a3b8; margin-left:auto; }
.session-del { position:absolute; right:4px; top:10px; border:none; background:transparent; cursor:pointer; opacity:0; font-size:11px; }
.session-item:hover .session-del { opacity:.6; }
.session-del:hover { opacity:1; }
.pane-empty { padding:22px 12px; font-size:11px; color:#94a3b8; text-align:center; }
.chat-pane { border:1px solid #e2e8f0; border-radius:10px; background:#fff; display:flex; flex-direction:column; max-height:calc(100vh - 220px); }
.chat-head { display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid #f1f5f9; }
.chat-head-text { flex:1; min-width:0; }
.chat-title { font-size:13px; font-weight:700; color:#1e293b; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.chat-sub { font-size:10px; color:#94a3b8; margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.running-badge { display:inline-flex; align-items:center; gap:5px; font-size:10px; color:#15803d; background:#dcfce7; border-radius:4px; padding:2px 7px; font-weight:600; }
.live-bar { display:flex; align-items:center; flex-wrap:wrap; gap:6px; padding:7px 9px; border:1px solid #bbf7d0; background:#f0fdf4; border-radius:8px; font-size:11px; color:#15803d; }
.live-title { font-weight:700; }
.live-tool { display:inline-flex; align-items:center; gap:4px; padding:1px 6px; border-radius:5px; background:#fff; border:1px solid #dcfce7; color:#166534; }
.live-tool.failed { border-color:#fecaca; background:#fef2f2; color:#b91c1c; }
.live-tool.success { color:#15803d; }
.live-tool-name { font-weight:600; }
.live-tool-detail { max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#475569; font-family:ui-monospace,Menlo,monospace; font-size:10px; }
.chat-messages { flex:1; overflow-y:auto; padding:14px; display:flex; flex-direction:column; gap:10px; background:#f8fafc; }
.chat-empty { margin:auto; color:#94a3b8; font-size:12px; text-align:center; padding:30px; }
.msg { display:flex; }
.msg.user { justify-content:flex-end; }
.bubble { max-width:78%; border-radius:12px; padding:9px 12px; background:#fff; border:1px solid #e2e8f0; }
.msg.user .bubble { background:#eef2ff; border-color:#c7d2fe; }
.bubble.streaming { border-style:dashed; }
.bubble pre { margin:0; white-space:pre-wrap; word-break:break-word; font-family:inherit; font-size:12px; line-height:1.65; color:#334155; }
.md-body { font-size:12px; line-height:1.7; color:#334155; word-break:break-word; }
.md-body p { margin:0 0 6px; }
.md-body p:last-child { margin-bottom:0; }
.md-body h1, .md-body h2, .md-body h3, .md-body h4, .md-body h5, .md-body h6 { margin:6px 0 4px; font-weight:700; color:#1e293b; }
.md-body h1 { font-size:17px; } .md-body h2 { font-size:15px; } .md-body h3 { font-size:13.5px; }
.md-body ul, .md-body ol { margin:2px 0 6px; padding-left:18px; }
.md-body li { margin:1px 0; }
.md-body code { background:#eef2ff; color:#4f46e5; padding:1px 4px; border-radius:3px; font-size:11px; font-family:ui-monospace,Menlo,monospace; }
.md-body pre { background:#0f172a; color:#e2e8f0; padding:8px 10px; border-radius:6px; overflow-x:auto; margin:4px 0 6px; }
.md-body pre code { background:transparent; color:inherit; padding:0; font-size:11px; }
.md-body blockquote { border-left:3px solid #cbd5e1; margin:4px 0; padding:2px 8px; color:#64748b; }
.md-body a { color:#4f46e5; text-decoration:underline; }
.md-body table { border-collapse:collapse; margin:4px 0 6px; }
.md-body th, .md-body td { border:1px solid #e2e8f0; padding:3px 6px; font-size:11px; }
.md-body hr { border:none; border-top:1px solid #e2e8f0; margin:8px 0; }
.msg-tools { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:6px; }
.tool-chip { display:inline-flex; align-items:center; gap:4px; padding:1px 6px; border-radius:5px; background:#eef2ff; color:#4f46e5; border:1px solid #e0e7ff; font-size:9.5px; }
.tool-chip.running { background:#ecfdf5; border-color:#86efac; color:#15803d; }
.tool-chip.failed { background:#fef2f2; border-color:#fecaca; color:#b91c1c; }
.tool-mark { font-size:10px; line-height:1; }
.tool-name { font-weight:600; }
.tool-detail { max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-family:ui-monospace,Menlo,monospace; font-size:9px; color:#475569; }
.tool-chip.running .mini-spin { color:#16a34a; width:8px; height:8px; border-width:1.5px; }
.chat-composer { border-top:1px solid #f1f5f9; padding:10px 12px; }
.chat-input { width:100%; box-sizing:border-box; resize:vertical; border:1px solid #e2e8f0; border-radius:8px; padding:8px 10px; font-size:12px; font-family:inherit; outline:none; }
.chat-input:focus { border-color:#6366f1; }
.composer-actions { display:flex; align-items:center; justify-content:flex-end; gap:10px; margin-top:8px; }
.composer-hint { font-size:10px; color:#94a3b8; margin-right:auto; }
.modal-mask { position:fixed; inset:0; background:rgba(15,23,42,.4); display:flex; align-items:center; justify-content:center; z-index:60; }
.modal { width:460px; max-width:92vw; background:#fff; border-radius:12px; padding:18px 20px; box-shadow:0 12px 40px rgba(15,23,42,.25); }
.modal h3 { margin:0 0 12px; font-size:15px; color:#1e293b; }
.field-label { display:block; font-size:11px; color:#64748b; margin:8px 0 4px; }
.text-input { width:100%; box-sizing:border-box; border:1px solid #e2e8f0; border-radius:8px; padding:7px 9px; font-size:12px; outline:none; }
.text-input:focus { border-color:#6366f1; }
.manual-toggle { display:flex; align-items:center; gap:5px; font-size:11px; color:#64748b; margin:4px 0 2px; }
.meta-error { margin-top:8px; font-size:11px; color:#dc2626; }
.modal-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:16px; }
.btn { padding:6px 12px; border:1px solid #e2e8f0; border-radius:6px; background:#fff; color:#475569; font-size:12px; cursor:pointer; }
.btn.primary { background:#4f46e5; border-color:#4f46e5; color:#fff; }
.btn.primary:disabled { opacity:.5; cursor:default; }
.btn.danger { background:#ef4444; border-color:#ef4444; color:#fff; }
.btn.sm { padding:4px 9px; font-size:11px; }
</style>
