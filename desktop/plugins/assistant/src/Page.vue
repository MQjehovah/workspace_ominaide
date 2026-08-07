<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { renderMarkdown } from './markdown'

const props = defineProps<{ data?: any; execute?: (a: string, args?: any) => Promise<any>; close?: () => void }>()

interface Step {
  id: number
  name: string
  args: any
  result: string
  status: 'running' | 'done' | 'error'
  collapsed: boolean
}
interface TimelineItem {
  kind: 'reasoning' | 'tool' | 'text'
  text?: string
  stepId?: number
}
interface Msg {
  id: number
  role: 'user' | 'assistant'
  text: string
  html: string
  reasoning: string
  reasoningOpen: boolean
  steps: Step[]
  timeline: TimelineItem[]
  pending: boolean
  error: string
  collapsed?: boolean
  reasoningSeparated?: boolean
  usage?: { chars: number; tools: number; duration: number }
}
interface Session {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  messages: Msg[]
  promptHistory: string[]
  histIdx: number
  pinned?: boolean
}
interface Config {
  mode: 'backend' | 'direct' | 'desktop'
  apiKey: string
  baseUrl: string
  model: string
  notify: boolean
  temperature?: number
  maxTurns?: number
  maxTokens?: number
}
interface Attachment {
  id: number
  name: string
  kind: 'image' | 'text'
  dataUrl?: string
  text?: string
  size: number
}

const sessions = ref<Session[]>([])
const currentId = ref('')
const input = ref('')
const loading = ref(false)
const sidebar = ref(true)
const settingsOpen = ref(false)
const paletteOpen = ref(false)
const paletteQuery = ref('')
const paletteIdx = ref(0)
const toastMsg = ref('')
const listening = ref(false)
const detailOpen = ref(false)
const detailTab = ref<'process' | 'history' | 'skills' | 'deliverables'>('process')
const statusFilter = ref<'all' | 'running' | 'done' | 'error'>('all')
const stage = ref('')
const attachments = ref<Attachment[]>([])
const sessionQuery = ref('')
const searchOpen = ref(false)
const searchQuery = ref('')
const searchIdx = ref(0)
const flashId = ref(0)
const slashOpen = ref(false)
const slashIdx = ref(0)
const editingId = ref('')
const editingTitle = ref('')
const toolsCache = ref<any[]>([])
const skillsLoading = ref(false)
const agentOpen = ref(false)
const agentTab = ref<'local' | 'mcp' | 'skills'>('local')
const mcpServers = ref<any[]>([])
const mcpTools = ref<any[]>([])
const skillsList = ref<any[]>([])
const agentActive = ref<{ sessionId: string; asst: Msg } | null>(null)
const desktopTools = ref<string[]>([])
const agentStage = ref('')
const newServer = ref({ name: '', transport: 'stdio' as 'stdio' | 'http', command: 'npx', args: '', url: '', headers: '', enabled: true })
const newSkill = ref({ name: '', description: '', instructions: '' })
const skillUrl = ref('')
const openSkillCreate = ref(false)
const editingServer = ref<any>(null)
const editDraft = ref<any>(null)
const editingSkill = ref<any>(null)
const skillDraft = ref({ name: '', description: '', instructions: '' })
const toolTest = ref<any>(null)
const toolTestArgs = ref('')
const toolTestResult = ref('')
const toolTestLoading = ref(false)
const msgsRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const paletteInputRef = ref<HTMLInputElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const detailBodyRef = ref<HTMLElement | null>(null)
const searchInputRef = ref<HTMLInputElement | null>(null)

const cfg = ref<Config>({ mode: 'backend', apiKey: '', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini', notify: true })
const cfgMode = ref('backend')
const cfgKey = ref('')
const cfgUrl = ref('https://api.openai.com/v1')
const cfgModel = ref('gpt-4o-mini')
const cfgNotify = ref(true)
const cfgTemp = ref(0.7)
const cfgMaxTurns = ref(20)
const cfgMaxTokens = ref(0)

let idSeq = 1
let stepSeq = 1
let abortCtl: AbortController | null = null
let taskStartAt = 0
let toastTimer: any = null
let persistTimer: any = null
let recognition: any = null

const current = computed(() => sessions.value.find(s => s.id === currentId.value) || null)

function sessionStatus(s: Session): 'running' | 'done' | 'error' | 'idle' {
  if (s.messages.some(m => m.pending)) return 'running'
  const lastAsst = [...s.messages].reverse().find(m => m.role === 'assistant')
  if (lastAsst?.error) return 'error'
  return s.messages.length ? 'done' : 'idle'
}

const filteredSessions = computed(() => {
  let list = sessions.value
  if (statusFilter.value !== 'all') {
    list = list.filter(s => sessionStatus(s) === statusFilter.value)
  }
  const q = sessionQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(s => {
      if (s.title.toLowerCase().includes(q)) return true
      return s.messages.some(m => m.text.toLowerCase().includes(q))
    })
  }
  return [...list].sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || b.updatedAt - a.updatedAt)
})

const statusCounts = computed(() => {
  const c: Record<string, number> = { all: sessions.value.length, running: 0, done: 0, error: 0 }
  for (const s of sessions.value) {
    const st = sessionStatus(s)
    if (st === 'running' || st === 'done' || st === 'error') c[st]++
  }
  return c
})

const processEntries = computed(() => {
  const out: { kind: 'question' | 'reasoning' | 'step' | 'reply'; msgId: number; text?: string; step?: Step }[] = []
  for (const m of current?.value?.messages || []) {
    if (m.role === 'user') { out.push({ kind: 'question', msgId: m.id, text: m.text }); continue }
    if (m.reasoning) out.push({ kind: 'reasoning', msgId: m.id, text: m.reasoning })
    for (const st of m.steps) out.push({ kind: 'step', msgId: m.id, step: st })
    if (m.text) out.push({ kind: 'reply', msgId: m.id, text: m.text })
  }
  return out
})

const questionEntries = computed(() =>
  (current?.value?.messages || []).filter(m => m.role === 'user').map(m => ({ msgId: m.id, text: m.text }))
)

const searchMatches = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q || !current.value) return []
  return current.value.messages
    .map((m, i) => ({ m, i }))
    .filter(({ m }) => m.text.toLowerCase().includes(q))
    .map(({ m }) => m.id)
})

const deliverables = computed(() => {
  const out: { name: string; url: string; step: string; kind: 'url' | 'file' }[] = []
  for (const m of current?.value?.messages || []) {
    for (const st of m.steps) {
      if (!st.result) continue
      const result = st.result
      try {
        const parsed = JSON.parse(result)
        if (parsed && typeof parsed === 'object' && parsed.download_url) {
          out.push({
            name: parsed.filename || decodeURIComponent(parsed.download_url.split('?')[0].split('/').pop() || '') || st.name,
            url: parsed.download_url,
            step: st.name,
            kind: 'url',
          })
        }
      } catch { /* not json */ }
      // local file paths from desktop tools (create_office_doc / write_file / run_command)
      const fileRe = /([A-Za-z]:\\[^\s"']+\.(?:docx|pptx|txt|md|csv|json|log|py|js|ts|html|css|xml|zip))|(\/[^\s"']+\.(?:docx|pptx|txt|md|csv|json|log|py|js|ts|html|css|xml|zip))/g
      let fm: RegExpExecArray | null
      const seen = new Set<string>()
      while ((fm = fileRe.exec(result))) {
        const p = fm[1] || fm[2]
        if (!p || seen.has(p)) continue
        seen.add(p)
        const name = p.split(/[\\/]/).pop() || p
        out.push({ name, url: p, step: st.name, kind: 'file' })
      }
      // http links
      const m2 = result.match(/https?:\/\/[^\s"']+/)
      if (m2) out.push({ name: st.name, url: m2[1], step: st.name, kind: 'url' })
    }
  }
  return out
})

const slashItems = [
  { key: 'schedule', icon: '📅', name: '日程', prompt: '帮我把未来 3 天的日程整理出来,列出时间、主题和备注' },
  { key: 'files', icon: '📁', name: '文件', prompt: '帮我搜索一下文件:' },
  { key: 'mail', icon: '✉️', name: '邮件', prompt: '看看我的未读邮件,总结一下要点' },
  { key: 'daily', icon: '📝', name: '日报', prompt: '根据今天的日程和事项,帮我写一份日报' },
  { key: 'search', icon: '🔍', name: '搜索', prompt: '帮我搜索一下:' },
  { key: 'notify', icon: '🔔', name: '通知', prompt: '查看我的通知,汇总重要事项' },
  { key: 'memory', icon: '🧠', name: '记忆', prompt: '结合记忆,回忆一下我之前提到的:' },
  { key: 'brief', icon: '🗞️', name: '简报', prompt: '帮我生成一份今天的资讯简报' },
]

const filteredSlash = computed(() => {
  const q = input.value.startsWith('/') ? input.value.slice(1).trim().toLowerCase() : ''
  if (!q) return slashItems
  return slashItems.filter(s => (s.name + s.key).toLowerCase().includes(q))
})

const STORAGE_KEY = 'assistant.sessions.v2'

function newId(): string {
  return `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

function createSession(): Session {
  return { id: newId(), title: '新会话', createdAt: Date.now(), updatedAt: Date.now(), messages: [], promptHistory: [], histIdx: 0 }
}

function saveSessions() {
  const clean = sessions.value.map(s => ({
    id: s.id,
    title: s.title,
    createdAt: s.createdAt,
    updatedAt: s.updatedAt,
    pinned: !!s.pinned,
    messages: s.messages.slice(-200).map(m => ({
      id: m.id,
      role: m.role,
      text: m.text,
      reasoning: m.reasoning,
      steps: m.steps.map(st => ({ id: st.id, name: st.name, args: st.args, result: st.result, status: st.status })),
      timeline: (m.timeline || []).map(tl => ({ kind: tl.kind, text: tl.text, stepId: tl.stepId })),
      error: m.error,
    })),
    promptHistory: s.promptHistory.slice(-100),
  }))
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ current: currentId.value, sessions: clean.slice(0, 50) }))
  } catch { /* storage full */ }
}

function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    const loaded = (data.sessions || []).map((s: any) => ({
      ...s,
      pinned: !!s.pinned,
      messages: (s.messages || []).map((m: any) => {
        const steps = (m.steps || []).map((st: any) => ({ id: st.id, name: st.name, args: st.args, result: st.result || '', status: st.status, collapsed: false }))
        let timeline = (m.timeline || []).map((tl: any) => ({ kind: tl.kind, text: tl.text, stepId: tl.stepId }))
        if (!timeline.length && (steps.length || m.reasoning)) {
          if (m.reasoning) timeline.push({ kind: 'reasoning', text: m.reasoning })
          for (const st of steps) timeline.push({ kind: 'tool', stepId: st.id })
        }
        return {
          id: m.id,
          role: m.role,
          text: m.text || '',
          html: '',
          reasoning: m.reasoning || '',
          reasoningOpen: true,
          steps,
          timeline,
          pending: false,
          error: m.error || '',
        }
      }),
      promptHistory: s.promptHistory || [],
      histIdx: 0,
    }))
    sessions.value = loaded
    if (data.current && loaded.some((s: any) => s.id === data.current)) currentId.value = data.current
    else if (loaded.length) currentId.value = loaded[0].id
    for (const s of sessions.value) s.messages.forEach(m => { m.html = renderMarkdown(m.text) })
  } catch { /* ignore */ }
}

function loadConfig() {
  try {
    const raw = localStorage.getItem('ai_chat_config')
    if (raw) {
      const c = JSON.parse(raw)
      cfg.value = { mode: 'backend', apiKey: '', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini', notify: true, temperature: 0.7, maxTurns: 20, maxTokens: 0, ...c }
      cfgMode.value = cfg.value.mode
      cfgKey.value = cfg.value.apiKey
      cfgUrl.value = cfg.value.baseUrl
      cfgModel.value = cfg.value.model
      cfgNotify.value = cfg.value.notify
      cfgTemp.value = cfg.value.temperature ?? 0.7
      cfgMaxTurns.value = cfg.value.maxTurns ?? 20
      cfgMaxTokens.value = cfg.value.maxTokens ?? 0
    }
  } catch { /* ignore */ }
}

function showToast(msg: string) {
  toastMsg.value = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMsg.value = '' }, 1800)
}

async function serverUrl(): Promise<string> {
  try {
    const w = window as any
    if (w.mqbox?.config?.get) return (await w.mqbox.config.get('serverUrl')) || 'http://localhost:8000'
  } catch { /* ignore */ }
  return localStorage.getItem('server_url') || 'http://localhost:8000'
}

async function getToken(): Promise<string> {
  try {
    const w = window as any
    if (w.mqbox?.config?.get) {
      const t = await w.mqbox.config.get('token')
      if (t) return t
    }
  } catch { /* ignore */ }
  return localStorage.getItem('token') || ''
}

watch(sessions, () => {
  clearTimeout(persistTimer)
  persistTimer = setTimeout(saveSessions, 600)
}, { deep: true })

// ---------------- rendering helpers ----------------
const renderTimers = new Map<Msg, any>()

function scheduleRender(m: Msg) {
  if (renderTimers.has(m)) clearTimeout(renderTimers.get(m))
  renderTimers.set(m, setTimeout(() => {
    m.html = renderMarkdown(m.text)
    scrollBottom()
  }, 40))
}

function finishRender(m: Msg) {
  const t = renderTimers.get(m)
  if (t) clearTimeout(t)
  renderTimers.delete(m)
  m.html = renderMarkdown(m.text)
}

let userScrolledUp = false
let scrollLockTimer: any = null

function onMsgsScroll() {
  const el = msgsRef.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  if (!atBottom) {
    userScrolledUp = true
    clearTimeout(scrollLockTimer)
  } else {
    userScrolledUp = false
  }
}

function scrollBottom(force = false) {
  const el = msgsRef.value
  if (!el) return
  if (force || (!userScrolledUp && el.scrollHeight - el.scrollTop - el.clientHeight < 160)) {
    requestAnimationFrame(() => { if (el) el.scrollTop = el.scrollHeight })
  }
}

function scrollToBottomAfterRender() {
  nextTick(() => {
    scrollBottom(true)
    setTimeout(() => scrollBottom(true), 60)
    setTimeout(() => scrollBottom(true), 200)
  })
}

function autoSize() {
  nextTick(() => {
    const el = inputRef.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  })
}
watch(input, (v) => {
  autoSize()
  const shouldShow = v.startsWith('/') && !/\s/.test(v)
  if (shouldShow && !slashOpen.value) { slashOpen.value = true; slashIdx.value = 0 }
  else if (!shouldShow && slashOpen.value) slashOpen.value = false
})

watch(
  () => (detailOpen.value && detailTab.value === 'process' ? processEntries.value.length : 0),
  () => {
    nextTick(() => {
      const el = detailBodyRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }
)

watch(
  () => currentId.value,
  () => {
    nextTick(() => {
      setTimeout(() => scrollBottom(true), 60)
      setTimeout(() => scrollBottom(true), 250)
    })
  }
)

// keep scrolled to bottom when session content changes while viewing bottom
watch(
  () => current.value?.messages.length,
  () => {
    if (loading.value) return
    nextTick(() => scrollBottom())
  }
)

// ---------------- session management ----------------
function ensureSession(): Session {
  if (current.value) return current.value
  const s = createSession()
  sessions.value.unshift(s)
  currentId.value = s.id
  return s
}

function newSession() {
  const s = createSession()
  sessions.value.unshift(s)
  currentId.value = s.id
  statusFilter.value = 'all'
  input.value = ''
  scrollBottom()
  nextTick(() => inputRef.value?.focus())
}

function switchSession(id: string) {
  if (id === currentId.value) return
  currentId.value = id
  input.value = ''
  scrollBottom()
}

function deleteSession(id: string) {
  const idx = sessions.value.findIndex(s => s.id === id)
  if (idx < 0) return
  sessions.value.splice(idx, 1)
  if (currentId.value === id) {
    currentId.value = sessions.value[Math.max(0, idx - 1)]?.id || ''
    if (!currentId.value) newSession()
  }
  if (statusFilter.value !== 'all' && !filteredSessions.value.some(s => s.id === currentId.value)) {
    statusFilter.value = 'all'
  }
}

function clearSession() {
  if (!current.value) return
  current.value.messages = []
  scrollBottom()
}

function setTitleFrom(s: Session, text: string) {
  if (s.messages.filter(m => m.role === 'user').length <= 1 && s.title === '新会话') {
    const t = text.replace(/\s+/g, ' ').trim()
    s.title = t.length > 24 ? t.slice(0, 24) + '…' : (t || '新会话')
  }
}

function timeAgo(ts: number): string {
  const s = Math.floor((Date.now() - ts) / 1000)
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  return `${Math.floor(s / 86400)} 天前`
}

// ---------------- streaming ----------------
function appendToken(m: Msg, content: string) {
  m.text += content
  scheduleRender(m)
  scrollBottom()
}

function appendReasoning(m: Msg, content: string) {
  if (m.reasoning && !m.reasoningSeparated) {
    m.reasoning += '\n\n----------\n'
  }
  m.reasoning += content
  const last = m.timeline[m.timeline.length - 1]
  if (last && last.kind === 'reasoning') {
    last.text += content
  } else {
    m.timeline.push({ kind: 'reasoning', text: content })
  }
  m.reasoningSeparated = true
  scrollBottom()
  scrollReasoningIntoView(m)
}

function scrollReasoningIntoView(m: Msg) {
  nextTick(() => {
    const el = msgsRef.value
    if (!el) return
    const bodies = el.querySelectorAll('.reasoning-body')
    const lastBody = bodies[bodies.length - 1] as HTMLElement | undefined
    if (lastBody) lastBody.scrollTop = lastBody.scrollHeight
  })
}

function flushIntermediateText(m: Msg) {
  if (m.text && m.text.trim()) {
    m.timeline.push({ kind: 'text', text: m.text })
    m.text = ''
    m.html = ''
  }
}

function startStep(m: Msg, name: string, args: any) {
  flushIntermediateText(m)
  const step: Step = { id: stepSeq++, name, args, result: '', status: 'running', collapsed: false }
  m.steps.push(step)
  m.timeline.push({ kind: 'tool', stepId: step.id })
  m.reasoningSeparated = false
  scrollBottom()
}

function finishStep(m: Msg, name: string, result: string, isError: boolean) {
  const st = [...m.steps].reverse().find(s => s.name === name && s.status === 'running')
  if (st) {
    st.result = result
    st.status = isError ? 'error' : 'done'
  }
  scrollBottom()
}

function handleEvent(m: Msg, data: any) {
  switch (data.type) {
    case 'token': appendToken(m, data.content || ''); stage.value = '正在生成回复'; break
    case 'reasoning': appendReasoning(m, data.content || ''); stage.value = '正在思考分析'; break
    case 'tool_call': startStep(m, data.name, data.arguments); stage.value = `正在执行 · ${data.name}`; break
    case 'tool_result': finishStep(m, data.name, data.content || '', !!data.error); break
    case 'error': m.error = data.content || 'AI 请求出错'; break
    case 'usage': m.usage = { chars: data.chars || 0, tools: data.tools || 0, duration: Date.now() - taskStartAt }; break
    case 'tools_ready':
      desktopTools.value = (data.names || []).filter((n: string) => typeof n === 'string')
      agentStage.value = `已加载 ${data.count || 0} 个工具`
      break
  }
}

async function streamMessage(message: string, history: { role: string; content: string }[], images: string[], m: Msg): Promise<void> {
  const c = cfg.value
  if (c.mode === 'backend') {
    const su = await serverUrl()
    const tk = await getToken()
    const r = await fetch(`${su}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tk },
      body: JSON.stringify({ message, history, images }),
      signal: abortCtl?.signal,
    })
    if (!r.ok) {
      const err = await r.json().catch(() => null)
      throw new Error(err?.detail || `请求失败 (${r.status})`)
    }
    const reader = r.body?.getReader()
    if (!reader) throw new Error('无响应流')
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        const t = line.trim()
        if (!t.startsWith('data: ')) continue
        try { handleEvent(m, JSON.parse(t.slice(6))) } catch { /* ignore */ }
      }
    }
    const tail = buf.trim()
    if (tail.startsWith('data: ')) {
      try { handleEvent(m, JSON.parse(tail.slice(6))) } catch { /* ignore */ }
    }
  } else {
    const parts: any[] = [{ type: 'text', text: message }]
    for (const img of images) parts.push({ type: 'image_url', image_url: { url: img } })
    const messages = [...history, { role: 'user', content: parts.length > 1 ? parts : message }]
    const r = await fetch(`${c.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + c.apiKey },
      body: JSON.stringify({ model: c.model, messages, temperature: 0.7, stream: true }),
      signal: abortCtl?.signal,
    })
    if (!r.ok) throw new Error(`请求失败 (${r.status})`)
    const reader = r.body?.getReader()
    if (!reader) throw new Error('无响应流')
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        const t = line.trim()
        if (!t.startsWith('data: ')) continue
        const payload = t.slice(6)
        if (payload === '[DONE]') return
        try {
          const chunk = JSON.parse(payload)
          const content = chunk.choices?.[0]?.delta?.content
          if (content) appendToken(m, content)
        } catch { /* ignore */ }
      }
    }
  }
}

async function send() {
  const text = input.value.trim()
  const hasAtt = attachments.value.length > 0
  if ((!text && !hasAtt) || loading.value) return
  let message = text
  const textAtts = attachments.value.filter(a => a.kind === 'text')
  if (textAtts.length) {
    message = text + '\n\n' + textAtts.map(a => `[附件 ${a.name}]\n${a.text}`).join('\n\n')
  }
  const images = attachments.value.filter(a => a.kind === 'image').map(a => a.dataUrl!).slice(0, 6)
  if (!message.trim() && images.length) message = '请分析这张图片'
  attachments.value = []
  const s = ensureSession()
  s.messages.push({ id: idSeq++, role: 'user', text: message, html: '', reasoning: '', reasoningOpen: false, steps: [], timeline: [], pending: false, error: '' })
  s.promptHistory.push(message)
  s.histIdx = s.promptHistory.length
  input.value = ''
  autoSize()
  const asst: Msg = { id: idSeq++, role: 'assistant', text: '', html: '', reasoning: '', reasoningOpen: true, steps: [], timeline: [], pending: true, error: '' }
  s.messages.push(asst)
  setTitleFrom(s, message)
  s.updatedAt = Date.now()
  loading.value = true
  stage.value = '正在思考'
  taskStartAt = Date.now()
  userScrolledUp = false
  scrollToBottomAfterRender()
  abortCtl = new AbortController()
  try {
    const history = s.messages.slice(0, -1).filter(m => m.role === 'user' || (m.role === 'assistant' && m.text))
      .map(m => ({ role: m.role, content: m.text }))
    if (cfg.value.mode === 'desktop') {
      await sendDesktop(message, history, images, asst)
    } else {
      await streamMessage(message, history, images, asst)
    }
  } catch (e: any) {
    asst.error = e?.name === 'AbortError' ? '已停止生成' : `请求失败: ${e?.message || e}`
  } finally {
    asst.pending = false
    if (!asst.text && !asst.error) s.messages = s.messages.filter(m => m !== asst)
    finishRender(asst)
    loading.value = false
    stage.value = ''
    abortCtl = null
    s.updatedAt = Date.now()
    const duration = Date.now() - taskStartAt
    if (duration >= 5000) {
      if (asst.error) notify('AI 任务结束', `${s.title} · ${asst.error}`)
      else notify('AI 任务完成', `${s.title} · ${formatUsage(asst) || '已完成'}`)
    }
    scrollBottom()
    nextTick(() => inputRef.value?.focus())
  }
}

function stop() {
  if (cfg.value.mode === 'desktop' && agentActive.value) {
    (window as any).mqbox?.agent?.abort?.(agentActive.value.sessionId)
    return
  }
  abortCtl?.abort()
}

async function sendDesktop(message: string, history: { role: string; content: string }[], images: string[], asst: Msg): Promise<void> {
  const c = cfg.value
  if (!c.apiKey || !c.baseUrl || !c.model) {
    asst.error = '桌面 Agent 需要配置 LLM(设置 → Base URL / API Key / 模型)'
    return
  }
  const mq = (window as any).mqbox
  if (!mq?.agent) {
    asst.error = '桌面 Agent 不可用,请重启桌面应用'
    return
  }
  const sessionId = 'a_' + Date.now() + '_' + Math.floor(Math.random() * 10000)
  agentActive.value = { sessionId, asst }
  try {
    const r = await mq.agent.start({
      sessionId,
      message,
      history,
      images,
      llm: { baseUrl: c.baseUrl, apiKey: c.apiKey, model: c.model, temperature: c.temperature, maxTokens: c.maxTokens },
      maxTurns: c.maxTurns,
    })
    if (r?.error && !asst.error) asst.error = r.error
  } finally {
    agentActive.value = null
  }
}

function sendSuggestion(text: string) {
  input.value = text
  send()
}

// ---------------- attachments ----------------
const TEXT_EXT = /\.(txt|md|markdown|csv|json|yaml|yml|log|py|js|ts|jsx|tsx|html|css|xml|sh|sql|ini|env)$/i

function readDataUrl(f: File): Promise<string> {
  return new Promise((res, rej) => {
    const r = new FileReader()
    r.onload = () => res(r.result as string)
    r.onerror = rej
    r.readAsDataURL(f)
  })
}

async function addFile(file: File) {
  try {
    if (attachments.value.length >= 6) { showToast('最多 6 个附件'); return }
    const isImg = file.type.startsWith('image/')
    if (isImg) {
      if (file.size > 5 * 1024 * 1024) { showToast('图片超过 5MB,无法上传'); return }
      const dataUrl = await readDataUrl(file)
      attachments.value.push({ id: Date.now() + Math.random(), name: file.name, kind: 'image', dataUrl, size: file.size })
    } else if (TEXT_EXT.test(file.name) && file.size < 200 * 1024) {
      const text = await file.text()
      attachments.value.push({ id: Date.now() + Math.random(), name: file.name, kind: 'text', text, size: file.size })
    } else {
      showToast('仅支持图片或小于 200KB 的文本文件')
    }
  } catch {
    showToast('读取文件失败')
  }
}

function onPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  const files: File[] = []
  for (const it of items) {
    if (it.kind === 'file') {
      const f = it.getAsFile()
      if (f) files.push(f)
    }
  }
  if (files.length) { e.preventDefault(); files.forEach(f => addFile(f)) }
}

function onDrop(e: DragEvent) {
  const files = e.dataTransfer?.files
  if (files?.length) {
    e.preventDefault()
    Array.from(files).forEach(f => addFile(f))
  }
}

function removeAttachment(id: number) {
  attachments.value = attachments.value.filter(a => a.id !== id)
}

function pickFiles() {
  fileInputRef.value?.click()
}

function onFilePicked(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) Array.from(input.files).forEach(f => addFile(f))
  input.value = ''
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}

// ---------------- detail panel ----------------
function scrollToMsg(id: number) {
  const el = document.getElementById('msg-' + id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function openDetail(tab: 'process' | 'history' | 'skills' | 'deliverables') {
  detailTab.value = tab
  detailOpen.value = true
  if (tab === 'skills') loadTools()
}

// ---------------- message actions ----------------
function copyText(m: Msg) {
  navigator.clipboard.writeText(m.text).then(() => showToast('已复制'), () => showToast('复制失败'))
}

function retry(m: Msg) {
  const s = current.value
  if (!s || loading.value) return
  const idx = s.messages.indexOf(m)
  if (idx < 0) return
  let uidx = -1
  for (let i = idx - 1; i >= 0; i--) { if (s.messages[i].role === 'user') { uidx = i; break } }
  if (uidx < 0) return
  const prompt = s.messages[uidx].text
  s.messages = s.messages.slice(0, uidx)
  input.value = prompt
  send()
}

function toggleCollapse(m: Msg) {
  m.collapsed = !m.collapsed
}

function onMsgsClick(e: MouseEvent) {
  const t = (e.target as HTMLElement).closest('.code-copy') as HTMLElement | null
  if (t) {
    navigator.clipboard.writeText(t.getAttribute('data-code') || '').then(() => showToast('代码已复制'), () => showToast('复制失败'))
  }
}

function formatUsage(m: Msg): string {
  if (!m.usage) return ''
  const tokens = Math.max(1, Math.round(m.usage.chars / 3))
  const secs = (m.usage.duration / 1000).toFixed(1)
  let s = `⚡ 约 ${tokens} tokens · ${secs}s`
  if (m.usage.tools > 0) s += ` · ${m.usage.tools} 次工具调用`
  return s
}

// ---------------- rename / pin ----------------
function startRename(s: Session) {
  editingId.value = s.id
  editingTitle.value = s.title
}

function commitRename() {
  const s = sessions.value.find(x => x.id === editingId.value)
  if (s) {
    const t = editingTitle.value.trim()
    if (t) s.title = t
  }
  editingId.value = ''
}

function togglePin(s: Session) {
  s.pinned = !s.pinned
}

// ---------------- in-conversation search ----------------
function toggleSearch() {
  searchOpen.value = !searchOpen.value
  searchQuery.value = ''
  searchIdx.value = 0
  if (searchOpen.value) nextTick(() => searchInputRef.value?.focus())
}
watch(searchQuery, () => { searchIdx.value = 0 })

function nextMatch(step = 1) {
  const matches = searchMatches.value
  if (!matches.length) return
  searchIdx.value = (searchIdx.value + step + matches.length) % matches.length
  const id = matches[searchIdx.value]
  flashMsg(id)
}

function closeSearch() {
  searchOpen.value = false
  searchQuery.value = ''
  flashId.value = 0
}

function flashMsg(id: number) {
  scrollToMsg(id)
  flashId.value = id
  setTimeout(() => { if (flashId.value === id) flashId.value = 0 }, 1600)
}

// ---------------- export ---------------
function exportMarkdown() {
  const s = current.value
  if (!s) return
  let md = `# ${s.title}\n\n`
  for (const m of s.messages) {
    if (m.role === 'user') {
      md += `## 你\n\n${m.text}\n\n`
    } else {
      if (m.reasoning) md += `> 思考过程: ${m.reasoning}\n\n`
      for (const st of m.steps) {
        md += `### 工具调用: ${st.name}\n\n\`\`\`json\n${prettyJson(st.args)}\n\`\`\`\n\n${st.result}\n\n`
      }
      if (m.text) md += `${m.text}\n\n`
    }
  }
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = (s.title || '会话').replace(/[\\/:*?"<>|]/g, '_') + '.md'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  showToast('已导出为 Markdown')
}

// ---------------- skills / tools ----------------
async function loadTools() {
  if (toolsCache.value.length || skillsLoading.value) return
  skillsLoading.value = true
  try {
    if (cfg.value.mode === 'desktop' && mq()?.mcp?.tools) {
      const r = await mq().mcp.tools()
      toolsCache.value = r?.ok ? r.tools || [] : []
    } else {
      const su = await serverUrl()
      const tk = await getToken()
      const r = await fetch(`${su}/api/mcp/tools`, { headers: { Authorization: 'Bearer ' + tk } })
      if (r.ok) {
        const j = await r.json()
        toolsCache.value = j.tools || []
      } else {
        toolsCache.value = []
      }
    }
  } catch {
    toolsCache.value = []
  } finally {
    skillsLoading.value = false
  }
}

// ---------------- notification ----------------
function notify(title: string, body: string) {
  if (!cfg.value.notify) return
  try {
    const N = (window as any).Notification
    if (N && N.permission === 'granted') {
      new N(title, { body })
    }
  } catch { /* ignore */ }
}

// ---------------- MCP / skills management ----------------
function mq(): any {
  return (window as any).mqbox
}

async function loadMcp() {
  try {
    const t = await mq().mcp.tools()
    if (t?.ok) mcpTools.value = t.tools || []
    const list = await mq().mcp.list()
    mcpServers.value = list || []
  } catch { /* ignore */ }
}

async function loadSkills() {
  try {
    skillsList.value = (await mq().skills.list()) || []
  } catch { /* ignore */ }
}

async function addMcpServer() {
  const ns = newServer.value
  if (!ns.name) { showToast('请填写服务器名称'); return }
  const args = ns.transport === 'stdio'
    ? { command: ns.command || 'npx', args: ns.args ? ns.args.split(' ').filter(Boolean) : [] }
    : { url: ns.url }
  const r = await mq().mcp.add({ id: ns.name.trim(), name: ns.name.trim(), transport: ns.transport, enabled: true, ...args })
  if (r?.ok) {
    showToast('MCP 服务器已添加')
    newServer.value = { name: '', transport: 'stdio', command: 'npx', args: '', url: '', headers: '', enabled: true }
    await loadMcp()
  } else {
    showToast('添加失败: ' + (r?.error || ''))
  }
}

async function removeMcpServer(id: string) {
  const r = await mq().mcp.remove(id)
  if (r?.ok) await loadMcp()
}

async function toggleMcpServer(s: any) {
  await mq().mcp.update(s.id, { enabled: !s.enabled })
  await loadMcp()
}

function startEditServer(s: any) {
  editingServer.value = s
  editDraft.value = {
    name: s.name,
    transport: s.transport,
    command: s.command || '',
    args: (s.args || []).join(' '),
    url: s.url || '',
    enabled: s.enabled !== false,
  }
}

function cancelEditServer() {
  editingServer.value = null
  editDraft.value = null
}

async function saveMcpServer() {
  const d = editDraft.value
  if (!d) return
  const patch: any = { name: d.name, transport: d.transport, enabled: d.enabled }
  if (d.transport === 'stdio') {
    patch.command = d.command || 'npx'
    patch.args = d.args ? d.args.split(' ').filter(Boolean) : []
    patch.url = ''
  } else {
    patch.url = d.url
    patch.command = ''
    patch.args = []
  }
  const r = await mq().mcp.update(editingServer.value.id, patch)
  if (r?.ok) {
    showToast('已保存')
    editingServer.value = null
    editDraft.value = null
    await loadMcp()
  } else {
    showToast('保存失败: ' + (r?.error || ''))
  }
}

function openToolTest(t: any) {
  toolTest.value = t
  toolTestArgs.value = ''
  toolTestResult.value = ''
}

async function runToolTest() {
  if (!toolTest.value) return
  toolTestLoading.value = true
  toolTestResult.value = ''
  try {
    let args: any = {}
    if (toolTestArgs.value.trim()) {
      try { args = JSON.parse(toolTestArgs.value) } catch {
        toolTestResult.value = '参数必须是合法 JSON'
        return
      }
    }
    const r = await mq().mcp.testCall(toolTest.value.name, args)
    toolTestResult.value = r?.error ? `[错误] ${r.content}` : r?.content || '(空结果)'
  } catch (e: any) {
    toolTestResult.value = `调用失败: ${e?.message || e}`
  } finally {
    toolTestLoading.value = false
  }
}

async function refreshMcp() {
  showToast('正在连接 MCP 服务器…')
  const r = await mq().mcp.refresh()
  if (r?.ok) {
    mcpTools.value = r.tools || []
    showToast(`已发现 ${mcpTools.value.length} 个工具`)
  } else {
    showToast('刷新失败: ' + (r?.error || ''))
  }
  await loadMcp()
}

function addSkill() {
  const ns = newSkill.value
  if (!ns.name.trim()) { showToast('请填写技能名称'); return }
  mq().skills.create({ name: ns.name.trim(), description: ns.description, instructions: ns.instructions }).then((r: any) => {
    if (r?.ok) {
      showToast('技能已创建')
      newSkill.value = { name: '', description: '', instructions: '' }
      loadSkills()
    } else showToast('创建失败: ' + (r?.error || ''))
  })
}

async function installSkillFolder() {
  const r = await mq().skills.installFolder()
  if (r?.ok) { showToast('技能已安装: ' + r.skill.name); loadSkills() }
  else if (!r?.canceled) showToast('安装失败: ' + (r?.error || ''))
}

async function installSkillUrl() {
  if (!skillUrl.value.trim()) { showToast('请填写 ZIP 地址'); return }
  showToast('正在下载技能…')
  const r = await mq().skills.installUrl(skillUrl.value.trim())
  if (r?.ok) { showToast('技能已安装: ' + r.skill.name); skillUrl.value = ''; loadSkills() }
  else showToast('安装失败: ' + (r?.error || ''))
}

async function toggleSkill(s: any) {
  const r = await mq().skills.toggle(s.id, !s.enabled)
  if (r?.ok) loadSkills()
}

async function removeSkill(id: string) {
  const r = await mq().skills.remove(id)
  if (r?.ok) { showToast('技能已删除'); loadSkills() }
}

function startEditSkill(s: any) {
  editingSkill.value = s
  skillDraft.value = { name: s.name, description: s.description || '', instructions: s.instructions || '' }
}

function cancelEditSkill() {
  editingSkill.value = null
}

async function saveSkill() {
  if (!editingSkill.value) return
  const r = await mq().skills.update(editingSkill.value.id, skillDraft.value)
  if (r?.ok) {
    showToast('技能已更新')
    editingSkill.value = null
    loadSkills()
  } else {
    showToast('更新失败: ' + (r?.error || ''))
  }
}

function openAgentSettings(tab: 'local' | 'mcp' | 'skills' = 'local') {
  agentTab.value = tab
  agentOpen.value = true
  loadMcp()
  loadSkills()
}

// ---------------- cloud history ----------------
async function importCloudHistory() {
  try {
    const su = await serverUrl()
    const tk = await getToken()
    const r = await fetch(`${su}/api/chat/history?limit=100`, { headers: { Authorization: 'Bearer ' + tk } })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const items = await r.json()
    if (!items.length) { showToast('云端没有历史记录'); return }
    const s = createSession()
    s.title = '云端历史'
    for (const it of items) {
      if (it.role !== 'user' && it.role !== 'assistant') continue
      s.messages.push({ id: idSeq++, role: it.role, text: it.content || '', html: '', reasoning: '', reasoningOpen: false, steps: [], timeline: [], pending: false, error: '' })
    }
    for (const m of s.messages) m.html = renderMarkdown(m.text)
    sessions.value.unshift(s)
    currentId.value = s.id
    statusFilter.value = 'all'
    showToast(`已导入 ${s.messages.length} 条历史`)
  } catch (e: any) {
    showToast('导入失败: ' + (e?.message || e))
  }
}

function openDeliverable(d: { name: string; url: string; step: string; kind: 'url' | 'file' }) {
  try {
    const w = window as any
    if (d.kind === 'file') {
      if (w.mqbox?.shell?.openPath) {
        w.mqbox.shell.openPath(d.url).catch(() => {
          if (w.mqbox?.shell?.openExternal) w.mqbox.shell.openExternal('file:///' + d.url.replace(/\\/g, '/'))
        })
      } else if (w.mqbox?.shell?.openExternal) {
        w.mqbox.shell.openExternal('file:///' + d.url.replace(/\\/g, '/'))
      }
    } else {
      if (w.mqbox?.shell?.openExternal) w.mqbox.shell.openExternal(d.url)
      else window.open(d.url, '_blank')
    }
  } catch {
    try {
      const w = window as any
      if (w.mqbox?.shell?.openExternal) w.mqbox.shell.openExternal('file:///' + d.url.replace(/\\/g, '/'))
    } catch { /* ignore */ }
  }
}

// ---------------- command palette ----------------
const commands = computed(() => [
  { id: 'new', label: '新建会话', search: 'new session', icon: '＋', kbd: 'Ctrl+O', run: () => { newSession(); showToast('已新建会话') } },
  { id: 'clear', label: '清空当前会话', search: 'clear', icon: '⌫', kbd: 'Ctrl+L', run: () => { clearSession(); showToast('已清空会话') } },
  { id: 'sidebar', label: sidebar.value ? '隐藏侧边栏' : '显示侧边栏', search: 'sidebar toggle', icon: '☰', kbd: 'Ctrl+B', run: () => { sidebar.value = !sidebar.value } },
  { id: 'detail', label: detailOpen.value ? '收起详情面板' : '打开详情面板', search: 'detail panel process', icon: '▤', kbd: 'Ctrl+P', run: () => { detailOpen.value = !detailOpen.value; if (detailOpen.value) detailTab.value = 'process' } },
  { id: 'history', label: '查看历史提问', search: 'history questions', icon: '⏱', kbd: '', run: () => openDetail('history') },
  { id: 'skills', label: '查看可用技能/工具', search: 'skills tools mcp', icon: '🧰', kbd: '', run: () => openDetail('skills') },
  { id: 'deliverables', label: '查看任务产物', search: 'deliverables files results', icon: '📦', kbd: '', run: () => openDetail('deliverables') },
  { id: 'copy', label: '复制最后回复', search: 'copy', icon: '⧉', kbd: '', run: () => copyLastReply() },
  { id: 'export', label: '导出会话为 Markdown', search: 'export markdown md', icon: '⇩', kbd: '', run: () => exportMarkdown() },
  { id: 'cloud', label: '导入云端对话历史', search: 'import cloud history sync', icon: '☁', kbd: '', run: () => importCloudHistory() },
  { id: 'settings', label: '打开设置', search: 'settings config', icon: '⚙', kbd: '', run: () => { settingsOpen.value = true } },
  { id: 'agent', label: 'MCP / 技能管理', search: 'mcp skills agent tools', icon: '🧩', kbd: '', run: () => openAgentSettings('mcp') },
  { id: 'main', label: '返回主界面', search: 'main home', icon: '⌂', kbd: '', run: () => { (window as any).mqbox?.window?.openMain?.() } },
  { id: 'delete', label: '删除当前会话', search: 'delete', icon: '×', kbd: '', run: () => { if (current.value) deleteSession(current.value.id) } },
  { id: 'stop', label: loading.value ? '停止生成' : '停止生成（未在生成）', search: 'stop', icon: '■', kbd: 'Esc', run: () => stop() },
])

const filteredCommands = computed(() => {
  const q = paletteQuery.value.trim().toLowerCase()
  if (!q) return commands.value
  return commands.value.filter(c => c.label.toLowerCase().includes(q) || c.search.includes(q))
})

function openPalette() {
  paletteQuery.value = ''
  paletteIdx.value = 0
  paletteOpen.value = true
  nextTick(() => paletteInputRef.value?.focus())
}

function runCommand(c: any) {
  paletteOpen.value = false
  c.run()
}

function onPaletteKey(e: KeyboardEvent) {
  if (e.key === 'Escape') { paletteOpen.value = false; nextTick(() => inputRef.value?.focus()); return }
  if (e.key === 'ArrowDown') { e.preventDefault(); paletteIdx.value = Math.min(paletteIdx.value + 1, filteredCommands.value.length - 1); return }
  if (e.key === 'ArrowUp') { e.preventDefault(); paletteIdx.value = Math.max(paletteIdx.value - 1, 0); return }
  if (e.key === 'Enter') {
    e.preventDefault()
    const c = filteredCommands.value[paletteIdx.value]
    if (c) runCommand(c)
  }
}

function copyLastReply() {
  const s = current.value
  if (!s) return
  const last = [...s.messages].reverse().find(m => m.role === 'assistant' && m.text)
  if (!last) { showToast('暂无回复'); return }
  navigator.clipboard.writeText(last.text).then(() => showToast('已复制最后回复'), () => showToast('复制失败'))
}

// ---------------- keyboard ----------------
function onKeydown(e: KeyboardEvent) {
  const ctrl = e.ctrlKey || e.metaKey
  if (ctrl && e.key.toLowerCase() === 'f') { e.preventDefault(); toggleSearch(); return }
  if (slashOpen.value) {
    if (e.key === 'ArrowDown') { e.preventDefault(); slashIdx.value = Math.min(slashIdx.value + 1, filteredSlash.value.length - 1); return }
    if (e.key === 'ArrowUp') { e.preventDefault(); slashIdx.value = Math.max(slashIdx.value - 1, 0); return }
    if (e.key === 'Tab' || e.key === 'Enter') {
      e.preventDefault()
      const it = filteredSlash.value[slashIdx.value]
      if (it) { input.value = it.prompt + ' '; autoSize() }
      slashOpen.value = false
      return
    }
    if (e.key === 'Escape') { slashOpen.value = false; return }
  }
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
    return
  }
  if (e.key === 'ArrowUp' && ctrl) { e.preventDefault(); histPrev(); return }
  if (e.key === 'ArrowDown' && ctrl) { e.preventDefault(); histNext(); return }
}

function pickSlash(it: any) {
  input.value = it.prompt + ' '
  slashOpen.value = false
  autoSize()
}

function onGlobalKey(e: KeyboardEvent) {
  if (paletteOpen.value || settingsOpen.value) return
  const ctrl = e.ctrlKey || e.metaKey
  const k = e.key.toLowerCase()
  if (ctrl && k === 'f') { e.preventDefault(); toggleSearch(); return }
  if (ctrl && k === 'k') { e.preventDefault(); openPalette() }
  else if (ctrl && k === 'b') { e.preventDefault(); sidebar.value = !sidebar.value }
  else if (ctrl && k === 'p') { e.preventDefault(); detailOpen.value = !detailOpen.value; if (detailOpen.value) detailTab.value = 'process' }
  else if (ctrl && k === 'l') { e.preventDefault(); clearSession(); showToast('已清空会话') }
  else if (ctrl && k === 'o') { e.preventDefault(); newSession() }
  else if (e.key === 'Escape' && searchOpen.value) { closeSearch() }
  else if (e.key === 'Escape' && slashOpen.value) { slashOpen.value = false }
  else if (e.key === 'Escape' && loading.value) { stop() }
}

function histPrev() {
  const s = current.value
  if (!s || s.histIdx <= 0) return
  s.histIdx--
  input.value = s.promptHistory[s.histIdx] || ''
  autoSize()
}

function histNext() {
  const s = current.value
  if (!s || s.histIdx >= s.promptHistory.length) return
  s.histIdx++
  input.value = s.histIdx >= s.promptHistory.length ? '' : (s.promptHistory[s.histIdx] || '')
  autoSize()
}

// ---------------- voice ----------------
function toggleVoice() {
  const w = window as any
  const SR = w.SpeechRecognition || w.webkitSpeechRecognition
  if (!SR) return
  if (listening.value) { recognition?.stop(); listening.value = false; return }
  recognition = new SR()
  recognition.lang = 'zh-CN'
  recognition.interimResults = false
  recognition.onresult = (e: any) => { input.value += e.results[0][0].transcript; listening.value = false; autoSize() }
  recognition.onerror = () => { listening.value = false }
  recognition.onend = () => { listening.value = false }
  recognition.start()
  listening.value = true
}

// ---------------- settings ----------------
function openSettings() {
  cfgMode.value = cfg.value.mode
  cfgKey.value = cfg.value.apiKey
  cfgUrl.value = cfg.value.baseUrl
  cfgModel.value = cfg.value.model
  cfgNotify.value = cfg.value.notify
  cfgTemp.value = cfg.value.temperature ?? 0.7
  cfgMaxTurns.value = cfg.value.maxTurns ?? 20
  cfgMaxTokens.value = cfg.value.maxTokens ?? 0
  settingsOpen.value = true
}

function applySettings() {
  cfg.value = {
    mode: cfgMode.value as 'backend' | 'direct' | 'desktop',
    apiKey: cfgKey.value,
    baseUrl: cfgUrl.value.replace(/\/+$/, ''),
    model: cfgModel.value,
    notify: cfgNotify.value,
    temperature: cfgMode.value === 'desktop' ? cfgTemp.value : undefined,
    maxTurns: cfgMode.value === 'desktop' ? cfgMaxTurns.value : undefined,
    maxTokens: cfgMode.value === 'desktop' ? cfgMaxTokens.value : undefined,
  }
  try { localStorage.setItem('ai_chat_config', JSON.stringify(cfg.value)) } catch { /* ignore */ }
  settingsOpen.value = false
  showToast('设置已保存')
}

// ---------------- lifecycle ----------------
onMounted(() => {
  loadConfig()
  loadSessions()
  if (!current.value) newSession()
  try {
    const mqAgent = (window as any).mqbox?.agent
    if (mqAgent?.onEvent) {
      mqAgent.onEvent((p: any) => {
        const a = agentActive.value
        if (a && p.sessionId === a.sessionId) handleEvent(a.asst, p)
      })
    }
  } catch { /* ignore */ }
  try {
    const N = (window as any).Notification
    if (N && N.permission === 'default') N.requestPermission()
  } catch { /* ignore */ }
  window.addEventListener('keydown', onGlobalKey)
  nextTick(() => {
    inputRef.value?.focus()
    setTimeout(() => scrollBottom(true), 80)
    setTimeout(() => scrollBottom(true), 300)
  })
})

onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalKey)
  renderTimers.forEach(t => clearTimeout(t))
  clearTimeout(persistTimer)
  clearTimeout(toastTimer)
  saveSessions()
})

function stepIcon(st: Step): string {
  if (st.status === 'running') return '○'
  return st.status === 'error' ? '✕' : '✓'
}

function stepById(m: Msg, id?: number): Step | undefined {
  return m.steps.find(s => s.id === id)
}

function prettyJson(args: any): string {
  try { return JSON.stringify(args, null, 2) } catch { return String(args) }
}

const suggestions = [
  '创建一个明天下午 3 点的日程',
  '搜索一下关于 AI 的文件',
  '帮我总结今天发布的热门 RSS',
]
</script>

<template>
  <div class="console" :class="{ 'sidebar-hidden': !sidebar }">
    <aside v-if="sidebar" class="sidebar">
      <div class="sidebar-head">
        <span class="brand"><span class="brand-mark">⌘</span> AI 控制台</span>
        <button class="icon-btn" title="新建会话 (Ctrl+O)" @click="newSession">＋</button>
      </div>
      <div class="sidebar-search">
        <input v-model="sessionQuery" class="s-search" placeholder="搜索会话…" />
      </div>
      <div class="filter-row">
        <button v-for="f in (['all','running','done','error'] as const)" :key="f" class="filter-chip" :class="{ active: statusFilter === f }" @click="statusFilter = f">
          {{ f === 'all' ? '全部' : f === 'running' ? '进行中' : f === 'done' ? '已完成' : '失败' }}
          <span class="filter-count">{{ statusCounts[f] }}</span>
        </button>
      </div>
      <div class="session-list">
        <template v-for="s in filteredSessions" :key="s.id">
          <div v-if="editingId === s.id" class="session-item editing">
            <input v-model="editingTitle" class="rename-input" @keydown.enter="commitRename" @keydown.esc="editingId = ''" @blur="commitRename" />
          </div>
          <button v-else class="session-item" :class="{ active: s.id === current?.id, pinned: s.pinned }" @click="switchSession(s.id)" @dblclick="startRename(s)">
            <span class="st-dot" :class="sessionStatus(s)"></span>
            <span class="session-title">{{ s.title || '新会话' }}</span>
            <span class="session-meta">{{ timeAgo(s.updatedAt) }} · {{ s.messages.length }} 条</span>
            <span class="session-pin" :class="{ on: s.pinned }" title="置顶" @click.stop="togglePin(s)">{{ s.pinned ? '★' : '☆' }}</span>
            <span class="session-del" title="删除会话" @click.stop="deleteSession(s.id)">×</span>
          </button>
        </template>
        <div v-if="filteredSessions.length === 0" class="session-empty">{{ sessions.length ? '没有匹配的任务' : '暂无会话' }}</div>
      </div>
      <div class="sidebar-foot">
        <span class="model-badge" :title="cfg.baseUrl">{{ cfg.model }}</span>
        <button class="foot-btn" @click="openSettings">⚙ 设置</button>
      </div>
    </aside>

    <main class="main">
      <header class="console-head">
        <div class="head-left">
          <button class="icon-btn" title="切换侧边栏 (Ctrl+B)" @click="sidebar = !sidebar">☰</button>
          <span class="head-title" :title="current?.title || ''">{{ current?.title || '新会话' }}</span>
          <span v-if="loading" class="stage-indicator">
            <span class="status-dot"></span>
            {{ stage || '处理中' }}
          </span>
        </div>
        <div class="head-right">
          <span class="mode-badge" :class="cfg.mode">{{ cfg.mode === 'backend' ? '后端代理' : cfg.mode === 'desktop' ? '桌面 Agent' : '直连' }}</span>
          <span v-if="cfg.mode === 'desktop' && desktopTools.length" class="mode-badge desktop" :title="desktopTools.join('\n')">🧰 {{ desktopTools.length }} 工具</span>
          <button class="icon-btn" title="新建任务 (Ctrl+O)" @click="newSession">＋</button>
          <button class="icon-btn" title="历史提问" @click="openDetail('history')">⏱</button>
          <button class="icon-btn" :class="{ active: detailOpen }" title="详情面板 (Ctrl+P)" @click="detailOpen = !detailOpen; if (detailOpen) detailTab = 'process'">▤</button>
          <button class="icon-btn" title="MCP / 技能管理" @click="openAgentSettings('mcp')">🧩</button>
          <button class="icon-btn" title="打开命令面板 (Ctrl+K)" @click="openPalette">⌘</button>
          <button class="icon-btn" title="设置" @click="openSettings">⚙</button>
          <button class="icon-btn close" title="关闭" @click="close">×</button>
        </div>
      </header>

      <transition name="fade">
        <div v-if="searchOpen" class="conv-search">
          <span class="conv-search-icon">⌕</span>
          <input ref="searchInputRef" v-model="searchQuery" class="conv-search-input" placeholder="搜索当前会话 (Enter 下一个)" @keydown.enter.prevent="nextMatch(1)" />
          <span class="conv-search-count">{{ searchQuery ? `${searchMatches.length ? searchIdx + 1 : 0}/${searchMatches.length}` : '' }}</span>
          <button class="conv-search-btn" @click="nextMatch(1)">↓</button>
          <button class="conv-search-btn" @click="nextMatch(-1)">↑</button>
          <button class="conv-search-btn close" @click="closeSearch">×</button>
        </div>
      </transition>

      <div ref="msgsRef" class="msgs" @click="onMsgsClick" @scroll.passive="onMsgsScroll">
        <template v-if="current">
          <div v-for="m in current.messages" :id="'msg-' + m.id" :key="m.id" class="msg" :class="[m.role, { flash: flashId === m.id }]">
            <template v-if="m.role === 'user'">
              <div class="msg-user-label">你</div>
              <div class="user-text">{{ m.text }}</div>
            </template>
            <template v-else>
              <div v-for="(tl, tli) in m.timeline" :key="tli" class="tl-wrap">
                <div v-if="tl.kind === 'reasoning'" class="reasoning" :class="{ open: m.reasoningOpen }">
                  <button class="reasoning-hd" @click="m.reasoningOpen = !m.reasoningOpen">
                    <span class="chev">{{ m.reasoningOpen ? '▾' : '▸' }}</span>
                    <span class="reasoning-title">思考过程</span>
                  </button>
                  <div v-if="m.reasoningOpen" class="reasoning-body">{{ tl.text }}</div>
                </div>
                <div v-else-if="tl.kind === 'text'" class="tl-text">{{ tl.text }}</div>
                <div v-else-if="tl.kind === 'tool' && stepById(m, tl.stepId)" class="step" :class="stepById(m, tl.stepId)!.status">
                  <button class="step-hd" @click="stepById(m, tl.stepId)!.collapsed = !stepById(m, tl.stepId)!.collapsed">
                    <span class="step-icon">{{ stepIcon(stepById(m, tl.stepId)!) }}</span>
                    <span class="step-name">{{ stepById(m, tl.stepId)!.name }}</span>
                    <span class="step-status" :class="stepById(m, tl.stepId)!.status">
                      {{ stepById(m, tl.stepId)!.status === 'running' ? '执行中' : stepById(m, tl.stepId)!.status === 'error' ? '失败' : '完成' }}
                    </span>
                    <span class="chev">{{ stepById(m, tl.stepId)!.collapsed ? '▸' : '▾' }}</span>
                  </button>
                  <div v-if="!stepById(m, tl.stepId)!.collapsed" class="step-body">
                    <div class="step-sec">
                      <span class="step-sec-label">参数</span>
                      <pre class="step-args">{{ prettyJson(stepById(m, tl.stepId)!.args) }}</pre>
                    </div>
                    <div v-if="stepById(m, tl.stepId)!.result" class="step-sec">
                      <span class="step-sec-label">结果</span>
                      <pre class="step-result" :class="{ err: stepById(m, tl.stepId)!.status === 'error' }">{{ stepById(m, tl.stepId)!.result }}</pre>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="m.pending && !m.text && m.timeline.length === 0" class="pending">
                <span class="pdot"></span><span class="pdot"></span><span class="pdot"></span>
                <span class="pending-text">思考中…</span>
              </div>
              <div v-if="m.error" class="error-bubble">{{ m.error }}</div>
              <div v-if="m.text" class="md" :class="{ clipped: m.collapsed }" v-html="m.html"></div>
              <div v-if="m.usage" class="msg-usage">{{ formatUsage(m) }}</div>
              <div class="msg-actions">
                <button title="复制" @click="copyText(m)">⧉ 复制</button>
                <button title="重新生成" :disabled="loading" @click="retry(m)">↻ 重试</button>
                <button v-if="m.text.length > 800" title="折叠/展开" @click="toggleCollapse(m)">{{ m.collapsed ? '▾ 展开' : '▴ 收起' }}</button>
              </div>
            </template>
          </div>
        </template>

        <div v-else class="empty">
          <div class="empty-mark">⌘</div>
          <p class="empty-title">新的 AI 控制台</p>
          <p class="empty-sub">用自然语言下达指令,AI 会自动调用工具完成任务</p>
          <div class="suggestions">
            <button v-for="s in suggestions" :key="s" class="suggestion" @click="sendSuggestion(s)">{{ s }}</button>
          </div>
        </div>
      </div>

      <div class="input-area">
        <transition name="fade">
          <div v-if="slashOpen" class="slash-menu">
            <button v-for="(it, i) in filteredSlash" :key="it.key" class="slash-item" :class="{ active: i === slashIdx }" @click="pickSlash(it)" @mouseenter="slashIdx = i">
              <span class="slash-icon">{{ it.icon }}</span>
              <span class="slash-name">/{{ it.name }}</span>
              <span class="slash-desc">{{ it.prompt }}</span>
            </button>
            <div v-if="filteredSlash.length === 0" class="slash-empty">没有匹配的指令</div>
          </div>
        </transition>
        <div v-if="attachments.length" class="attach-row">
          <div v-for="a in attachments" :key="a.id" class="attach-chip" :class="a.kind">
            <img v-if="a.kind === 'image'" class="attach-thumb" :src="a.dataUrl" alt="" />
            <span class="attach-file" v-else>📄</span>
            <span class="attach-name" :title="a.name">{{ a.name }}</span>
            <span class="attach-size">{{ fmtSize(a.size) }}</span>
            <button class="attach-del" @click="removeAttachment(a.id)">×</button>
          </div>
          <button class="attach-clear" @click="attachments = []">清空</button>
        </div>
        <div class="input-box" :class="{ focused: loading }" @drop="onDrop" @dragover.prevent>
          <textarea
            ref="inputRef"
            v-model="input"
            rows="1"
            class="input"
            placeholder="给 AI 下达指令… (Ctrl+V 粘贴截图 / 拖拽文件)"
            @keydown="onKeydown"
            @paste="onPaste"
          ></textarea>
          <div class="input-tools">
            <button class="tool-btn" title="上传附件 (图片/文本)" @click="pickFiles">📎</button>
            <button class="tool-btn" :class="{ active: listening }" title="语音输入" @click="toggleVoice">🎤</button>
            <button v-if="loading" class="send-btn stop" @click="stop">■ 停止</button>
            <button v-else class="send-btn" :disabled="(!input.trim() && attachments.length === 0) || loading" @click="send">发送 ↵</button>
          </div>
          <input ref="fileInputRef" type="file" multiple accept="image/*,.txt,.md,.markdown,.csv,.json,.yaml,.yml,.log,.py,.js,.ts,.jsx,.tsx,.html,.css,.xml,.sh,.sql,.ini" style="display:none" @change="onFilePicked" />
        </div>
        <div class="input-hint">
          <span>Enter 发送 · Shift+Enter 换行</span>
          <span>Ctrl+K 面板 · Ctrl+P 详情</span>
          <span>Ctrl+V/拖拽 添加附件</span>
        </div>
      </div>
    </main>

    <template v-if="detailOpen">
      <div class="detail-backdrop" @click="detailOpen = false"></div>
      <aside class="detail-panel">
      <div class="detail-hd">
        <div class="detail-tabs">
          <button class="detail-tab" :class="{ active: detailTab === 'process' }" @click="detailTab = 'process'">过程 <span class="tab-badge">{{ processEntries.length }}</span></button>
          <button class="detail-tab" :class="{ active: detailTab === 'history' }" @click="detailTab = 'history'">提问 <span class="tab-badge">{{ questionEntries.length }}</span></button>
          <button class="detail-tab" :class="{ active: detailTab === 'deliverables' }" @click="detailTab = 'deliverables'">产物 <span class="tab-badge">{{ deliverables.length }}</span></button>
          <button class="detail-tab" :class="{ active: detailTab === 'skills' }" @click="detailTab = 'skills'; loadTools()">技能</button>
        </div>
        <button class="icon-btn" title="收起 (Ctrl+P)" @click="detailOpen = false">×</button>
      </div>
      <div ref="detailBodyRef" class="detail-body">
        <template v-if="detailTab === 'process'">
          <div v-if="processEntries.length === 0" class="detail-empty">执行过程会实时显示在这里</div>
          <div v-for="(e, i) in processEntries" :key="i" class="tl-entry" :class="e.kind" @click="scrollToMsg(e.msgId)">
            <template v-if="e.kind === 'question'">
              <span class="tl-icon">?</span>
              <div class="tl-main">
                <div class="tl-label">提问</div>
                <div class="tl-text one-line">{{ e.text }}</div>
              </div>
            </template>
            <template v-else-if="e.kind === 'reasoning'">
              <span class="tl-icon think">◎</span>
              <div class="tl-main">
                <div class="tl-label">思考过程</div>
                <div class="tl-text one-line">{{ e.text }}</div>
              </div>
            </template>
            <template v-else-if="e.kind === 'step' && e.step">
              <span class="tl-icon" :class="e.step.status">{{ stepIcon(e.step) }}</span>
              <div class="tl-main">
                <div class="tl-label">
                  <span class="tl-step-name">{{ e.step.name }}</span>
                  <span class="tl-status" :class="e.step.status">{{ e.step.status === 'running' ? '执行中' : e.step.status === 'error' ? '失败' : '完成' }}</span>
                </div>
                <div v-if="e.step.status !== 'running'" class="tl-args one-line">{{ prettyJson(e.step.args) }}</div>
                <div v-else class="tl-text dim">执行中…</div>
              </div>
            </template>
            <template v-else-if="e.kind === 'reply'">
              <span class="tl-icon done">✓</span>
              <div class="tl-main">
                <div class="tl-label">回复</div>
                <div class="tl-text one-line">{{ e.text }}</div>
              </div>
            </template>
          </div>
        </template>
        <template v-else-if="detailTab === 'history'">
          <div v-if="questionEntries.length === 0" class="detail-empty">还没有提问记录</div>
          <button v-for="(q, i) in questionEntries" :key="i" class="q-item" @click="scrollToMsg(q.msgId)">
            <span class="q-idx">{{ i + 1 }}</span>
            <span class="q-text one-line">{{ q.text }}</span>
          </button>
        </template>
        <template v-else-if="detailTab === 'deliverables'">
          <div v-if="deliverables.length === 0" class="detail-empty">工具生成了文件或链接后会显示在这里</div>
          <div v-for="(d, i) in deliverables" :key="i" class="deliv-item">
            <span class="deliv-icon">📦</span>
            <div class="deliv-main">
              <div class="deliv-name one-line" :title="d.name">{{ d.name }}</div>
              <div class="deliv-step">{{ d.step }}</div>
            </div>
            <button class="deliv-open" @click="openDeliverable(d)">打开</button>
          </div>
        </template>
        <template v-else-if="detailTab === 'skills'">
          <div v-if="skillsLoading" class="detail-empty">加载中…</div>
          <div v-else-if="!toolsCache.length" class="detail-empty">无法获取工具列表</div>
          <div v-for="t in toolsCache" :key="t.name" class="skill-item">
            <span class="skill-icon">🧰</span>
            <div class="skill-main">
              <div class="skill-name">{{ t.name }}<span v-if="t.serverId === '__local__'" class="skill-tag-local">本地</span></div>
              <div class="skill-desc">{{ t.description }}</div>
            </div>
          </div>
        </template>
      </div>
    </aside>
    </template>

    <transition name="fade">
      <div v-if="paletteOpen" class="overlay" @click.self="paletteOpen = false">
        <div class="palette">
          <div class="palette-input-row">
            <span class="palette-prefix">›</span>
            <input
              ref="paletteInputRef"
              v-model="paletteQuery"
              class="palette-input"
              placeholder="输入命令…"
              @keydown="onPaletteKey"
            />
            <span class="palette-esc">esc</span>
          </div>
          <div class="palette-list">
            <button
              v-for="(c, i) in filteredCommands"
              :key="c.id"
              class="palette-item"
              :class="{ active: i === paletteIdx }"
              @click="runCommand(c)"
              @mouseenter="paletteIdx = i"
            >
              <span class="palette-icon">{{ c.icon }}</span>
              <span class="palette-label">{{ c.label }}</span>
              <span v-if="c.kbd" class="palette-kbd">{{ c.kbd }}</span>
            </button>
            <div v-if="filteredCommands.length === 0" class="palette-empty">没有匹配的命令</div>
          </div>
        </div>
      </div>
    </transition>

    <transition name="fade">
      <div v-if="settingsOpen" class="overlay" @click.self="settingsOpen = false">
        <div class="settings-panel">
          <div class="settings-hd">设置</div>
          <div class="field">
            <label>模式</label>
            <select v-model="cfgMode" class="s-input">
              <option value="backend">后端代理</option>
              <option value="direct">前端直连</option>
              <option value="desktop">桌面 Agent</option>
            </select>
          </div>
          <template v-if="cfgMode === 'direct' || cfgMode === 'desktop'">
            <div class="field">
              <label>API Key</label>
              <input v-model="cfgKey" type="password" class="s-input" placeholder="sk-..." />
            </div>
            <div class="field">
              <label>Base URL</label>
              <input v-model="cfgUrl" class="s-input" placeholder="https://api.openai.com/v1" />
            </div>
            <div class="field">
              <label>模型</label>
              <input v-model="cfgModel" class="s-input" placeholder="gpt-4o-mini" />
            </div>
          </template>
          <template v-if="cfgMode === 'desktop'">
            <div class="field">
              <label>温度 (Temperature)</label>
              <input v-model.number="cfgTemp" type="number" min="0" max="2" step="0.1" class="s-input" />
            </div>
            <div class="field">
              <label>最大工具轮次</label>
              <input v-model.number="cfgMaxTurns" type="number" min="1" max="50" step="1" class="s-input" />
            </div>
            <div class="field">
              <label>最大输出 Tokens (0 = 不限制)</label>
              <input v-model.number="cfgMaxTokens" type="number" min="0" step="256" class="s-input" />
            </div>
            <button class="btn-ghost" style="width:100%" @click="loadMcp(); openAgentSettings('mcp')">查看可用工具 (MCP + 本地)</button>
          </template>
          <p class="settings-note">{{ cfgMode === 'desktop' ? '桌面 Agent 在本机直连 LLM,自动加载内置工具与已连接的 MCP 服务器。确保模型支持工具调用(function calling)。' : '后端代理模式下,模型由服务端配置,不加载本机工具;直连模式仅在本机保存配置,无工具调用。' }}</p>
          <div class="field">
            <label class="switch-label">
              <input v-model="cfgNotify" type="checkbox" class="switch" />
              任务完成时发送系统通知
            </label>
          </div>
          <div class="settings-actions">
            <button class="btn-ghost" @click="openAgentSettings('mcp')">🧩 MCP / 技能</button>
            <button class="btn-ghost" @click="settingsOpen = false">取消</button>
            <button class="btn-primary" @click="applySettings">应用</button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="fade">
      <div v-if="agentOpen" class="overlay" @click.self="agentOpen = false">
        <div class="settings-panel agent-panel">
          <div class="settings-hd">Agent 引擎</div>
          <div class="agent-tabs">
            <button class="agent-tab" :class="{ active: agentTab === 'local' }" @click="agentTab = 'local'; loadMcp()">本地工具</button>
            <button class="agent-tab" :class="{ active: agentTab === 'mcp' }" @click="agentTab = 'mcp'; loadMcp()">MCP 服务器</button>
            <button class="agent-tab" :class="{ active: agentTab === 'skills' }" @click="agentTab = 'skills'; loadSkills()">技能</button>
          </div>

          <div v-if="agentTab === 'mcp'" class="agent-body">
            <div class="mcp-add">
              <div class="mcp-add-row">
                <input v-model="newServer.name" class="s-input" placeholder="服务器名称 (e.g. filesystem)" />
                <select v-model="newServer.transport" class="s-input mcp-transport">
                  <option value="stdio">stdio 本地</option>
                  <option value="http">HTTP 远程</option>
                </select>
              </div>
              <template v-if="newServer.transport === 'stdio'">
                <div class="mcp-add-row">
                  <input v-model="newServer.command" class="s-input" placeholder="命令 (e.g. npx)" />
                  <input v-model="newServer.args" class="s-input" placeholder="参数,空格分隔" />
                </div>
              </template>
              <template v-else>
                <div class="mcp-add-row">
                  <input v-model="newServer.url" class="s-input" placeholder="https://mcp.example.com/mcp" />
                </div>
              </template>
              <div class="mcp-add-actions">
                <button class="btn-primary" @click="addMcpServer">添加服务器</button>
                <button class="btn-ghost" @click="refreshMcp">刷新工具</button>
              </div>
            </div>

            <div v-if="mcpServers.length" class="mcp-list">
              <div v-for="s in mcpServers" :key="s.id" class="mcp-server">
                <template v-if="editingServer?.id === s.id">
                  <div class="mcp-edit">
                    <div class="mcp-add-row">
                      <input v-model="editDraft.name" class="s-input" placeholder="服务器名称" />
                      <select v-model="editDraft.transport" class="s-input mcp-transport">
                        <option value="stdio">stdio 本地</option>
                        <option value="http">HTTP 远程</option>
                      </select>
                    </div>
                    <template v-if="editDraft.transport === 'stdio'">
                      <div class="mcp-add-row">
                        <input v-model="editDraft.command" class="s-input" placeholder="命令 (e.g. npx)" />
                        <input v-model="editDraft.args" class="s-input" placeholder="参数,空格分隔" />
                      </div>
                    </template>
                    <template v-else>
                      <div class="mcp-add-row">
                        <input v-model="editDraft.url" class="s-input" placeholder="https://mcp.example.com/mcp" />
                      </div>
                    </template>
                    <div class="mcp-add-actions">
                      <button class="btn-primary" @click="saveMcpServer">保存</button>
                      <button class="btn-ghost" @click="cancelEditServer">取消</button>
                    </div>
                  </div>
                </template>
                <template v-else>
                  <div class="mcp-server-main">
                    <div class="mcp-server-name">
                      <span class="mcp-dot" :class="s.status?.connected ? 'on' : s.status?.error ? 'err' : ''"></span>
                      {{ s.name }}
                      <span class="mcp-badge" :class="{ local: s.transport === 'internal' }">{{ s.transport === 'stdio' ? 'stdio' : s.transport === 'http' ? 'http' : '内置' }}</span>
                      <span class="mcp-tool-count">{{ s.status?.tools ?? 0 }} 工具</span>
                    </div>
                    <div class="mcp-server-sub">
                      <span v-if="s.transport === 'stdio'">{{ s.command }} {{ (s.args || []).join(' ') }}</span>
                      <span v-else-if="s.transport === 'http'">{{ s.url }}</span>
                      <span v-else>内置 Word / PPT 文档编辑,随应用提供</span>
                    </div>
                    <div v-if="s.status?.error" class="mcp-err">{{ s.status.error }}</div>
                  </div>
                  <div class="mcp-server-actions">
                    <template v-if="s.transport !== 'internal'">
                      <button class="mcp-btn" :class="{ on: s.enabled }" @click="toggleMcpServer(s)">{{ s.enabled ? '启用' : '停用' }}</button>
                      <button class="mcp-btn" @click="startEditServer(s)">编辑</button>
                      <button class="mcp-btn del" @click="removeMcpServer(s.id)">删除</button>
                    </template>
                    <span v-else class="mcp-btn builtin-label">随应用内置</span>
                  </div>
                </template>
              </div>
            </div>
            <div v-else class="detail-empty">还没有 MCP 服务器。添加一个 stdio 本地服务器或 HTTP 远程服务器。</div>

            <div class="mcp-tools">
              <div class="mcp-tools-hd">已发现工具 ({{ mcpTools.filter(t => t.serverId !== '__local__').length }})</div>
              <div v-if="!mcpTools.filter(t => t.serverId !== '__local__').length" class="detail-empty">连接后点击"刷新工具"发现工具</div>
              <div v-for="t in mcpTools.filter(t => t.serverId !== '__local__')" :key="t.name" class="mcp-tool">
                <div class="mcp-tool-row">
                  <div class="mcp-tool-info">
                    <span class="mcp-tool-name">{{ t.name }}</span>
                    <span class="mcp-tool-desc">{{ t.description }}</span>
                  </div>
                  <button class="mcp-btn" @click="openToolTest(t)">测试</button>
                </div>
              </div>
            </div>

            <div v-if="toolTest" class="tool-test">
              <div class="mcp-tools-hd">测试工具: {{ toolTest.name }}</div>
              <textarea v-model="toolTestArgs" class="s-input tool-test-args" placeholder='参数 JSON,留空为 {}' spellcheck="false"></textarea>
              <div class="mcp-add-actions">
                <button class="btn-primary" :disabled="toolTestLoading" @click="runToolTest">{{ toolTestLoading ? '运行中…' : '运行' }}</button>
                <button class="btn-ghost" @click="toolTest = null">关闭</button>
              </div>
              <pre v-if="toolTestResult" class="tool-test-result">{{ toolTestResult }}</pre>
            </div>
          </div>

          <div v-else-if="agentTab === 'local'" class="agent-body">
            <div class="mcp-tools-hd">内置本地工具 ({{ mcpTools.filter(t => t.serverId === '__local__').length }})</div>
            <p class="settings-note">这些工具由桌面 Agent 内置提供,无需连接外部服务器,对话中自动可用。可直接在下方测试。</p>
            <div v-if="!mcpTools.filter(t => t.serverId === '__local__').length" class="detail-empty">本地工具未加载,点击上方"刷新工具"。</div>
            <div v-for="t in mcpTools.filter(t => t.serverId === '__local__')" :key="t.name" class="mcp-tool">
              <div class="mcp-tool-row">
                <div class="mcp-tool-info">
                  <span class="mcp-tool-name">{{ t.name }}</span>
                  <span class="mcp-tool-desc">{{ t.description }}</span>
                </div>
                <button class="mcp-btn" @click="openToolTest(t)">测试</button>
              </div>
            </div>
            <div v-if="toolTest" class="tool-test">
              <div class="mcp-tools-hd">测试工具: {{ toolTest.name }}</div>
              <textarea v-model="toolTestArgs" class="s-input tool-test-args" placeholder='参数 JSON,留空为 {}' spellcheck="false"></textarea>
              <div class="mcp-add-actions">
                <button class="btn-primary" :disabled="toolTestLoading" @click="runToolTest">{{ toolTestLoading ? '运行中…' : '运行' }}</button>
                <button class="btn-ghost" @click="toolTest = null">关闭</button>
              </div>
              <pre v-if="toolTestResult" class="tool-test-result">{{ toolTestResult }}</pre>
            </div>
          </div>

          <div v-else class="agent-body">
            <div class="skill-actions">
              <button class="btn-primary" @click="installSkillFolder">从文件夹安装</button>
              <button class="btn-ghost" @click="openSkillCreate = !openSkillCreate">{{ openSkillCreate ? '收起' : '手动创建' }}</button>
            </div>
            <div v-if="openSkillCreate" class="skill-create">
              <input v-model="newSkill.name" class="s-input" placeholder="技能名称" />
              <input v-model="newSkill.description" class="s-input" placeholder="一句话描述" />
              <textarea v-model="newSkill.instructions" class="s-input skill-textarea" placeholder="技能指令 (Markdown)…"></textarea>
              <div class="mcp-add-actions">
                <button class="btn-primary" @click="addSkill">创建</button>
              </div>
            </div>
            <div class="skill-url">
              <input v-model="skillUrl" class="s-input" placeholder="GitHub 仓库 / 技能 ZIP 地址…" />
              <button class="btn-ghost" @click="installSkillUrl">安装</button>
            </div>
            <p class="settings-note">支持 Claude 技能(SKILL.md 文件夹)、GitHub 仓库 URL(如 https://github.com/xxx/skills)或直接 ZIP 链接。技能会在对话中自动启用。</p>

            <div v-if="skillsList.length" class="mcp-list">
              <div v-for="s in skillsList" :key="s.id" class="mcp-server">
                <template v-if="editingSkill?.id === s.id">
                  <div class="mcp-edit">
                    <input v-model="skillDraft.name" class="s-input" placeholder="技能名称" />
                    <input v-model="skillDraft.description" class="s-input" placeholder="一句话描述" />
                    <textarea v-model="skillDraft.instructions" class="s-input skill-textarea" placeholder="技能指令 (Markdown)…"></textarea>
                    <div class="mcp-add-actions">
                      <button class="btn-primary" @click="saveSkill">保存</button>
                      <button class="btn-ghost" @click="cancelEditSkill">取消</button>
                    </div>
                  </div>
                </template>
                <template v-else>
                  <div class="mcp-server-main">
                    <div class="mcp-server-name">
                      <span class="mcp-dot" :class="s.enabled ? 'on' : ''"></span>
                      {{ s.name }}
                      <span class="mcp-badge">{{ s.id }}</span>
                    </div>
                    <div class="mcp-server-sub">{{ s.description || s.instructions?.slice(0, 80) || s.id }}</div>
                  </div>
                  <div class="mcp-server-actions">
                    <button class="mcp-btn" :class="{ on: s.enabled }" @click="toggleSkill(s)">{{ s.enabled ? '启用' : '停用' }}</button>
                    <button class="mcp-btn" @click="startEditSkill(s)">编辑</button>
                    <button class="mcp-btn del" @click="removeSkill(s.id)">删除</button>
                  </div>
                </template>
              </div>
            </div>
            <div v-else class="detail-empty">还没有技能。安装一个 SKILL.md 文件夹或手动创建一个。</div>
          </div>

          <div class="settings-actions">
            <button class="btn-ghost" @click="agentOpen = false">关闭</button>
          </div>
        </div>
      </div>
    </transition>

    <transition name="toast">
      <div v-if="toastMsg" class="toast">{{ toastMsg }}</div>
    </transition>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }
.console {
  --bg: #0a0d13;
  --bg2: #0f141d;
  --bg3: #151b26;
  --bg4: #1c2431;
  --border: #202838;
  --text: #d7dce6;
  --dim: #8791a6;
  --accent: #6c5ce7;
  --accent2: #00d2ff;
  --green: #2fd6a5;
  --amber: #fbbf24;
  --red: #f4686d;
  height: 100vh;
  display: flex;
  position: relative;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  overflow: hidden;
}

/* ---------------- sidebar ---------------- */
.sidebar {
  width: 232px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg2);
  border-right: 1px solid var(--border);
}
.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 10px;
}
.brand { font-size: 13px; font-weight: 700; letter-spacing: .3px; color: var(--text); }
.brand-mark { color: var(--accent2); margin-right: 2px; }
.session-list { flex: 1; overflow-y: auto; padding: 0 8px; }
.session-item {
  position: relative;
  display: block;
  width: 100%;
  text-align: left;
  padding: 9px 24px 9px 24px;
  margin-bottom: 2px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
}
.session-item:hover { background: var(--bg3); }
.session-item.active { background: var(--bg4); box-shadow: inset 2px 0 0 var(--accent); }
.session-title {
  display: block;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-meta { display: block; font-size: 11px; color: var(--dim); margin-top: 2px; }
.session-del {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  line-height: 18px;
  text-align: center;
  border-radius: 5px;
  color: var(--dim);
  font-size: 14px;
  opacity: 0;
  cursor: pointer;
}
.session-item:hover .session-del { opacity: 1; }
.session-del:hover { background: var(--bg4); color: var(--red); }
.session-empty { padding: 20px 10px; font-size: 12px; color: var(--dim); text-align: center; }
.sidebar-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px;
  border-top: 1px solid var(--border);
}
.model-badge {
  font-size: 11px;
  color: var(--accent2);
  background: rgba(0, 210, 255, .08);
  border: 1px solid rgba(0, 210, 255, .2);
  padding: 3px 8px;
  border-radius: 6px;
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}
.foot-btn {
  border: none;
  background: transparent;
  color: var(--dim);
  font-size: 12px;
  cursor: pointer;
  padding: 5px 8px;
  border-radius: 6px;
}
.foot-btn:hover { background: var(--bg4); color: var(--text); }

/* ---------------- main ---------------- */
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.console-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--bg2);
}
.head-left, .head-right { display: flex; align-items: center; gap: 8px; }
.head-title {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}
.status-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 8px var(--green);
  animation: pulse 1.2s infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
.mode-badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  color: var(--dim);
  border: 1px solid var(--border);
  background: var(--bg3);
}
.mode-badge.backend { color: var(--green); border-color: rgba(47, 214, 165, .25); }
.mode-badge.direct { color: var(--amber); border-color: rgba(251, 191, 36, .25); }
.mode-badge.desktop { color: var(--accent2); border-color: rgba(0, 210, 255, .3); cursor: default; }
.icon-btn {
  width: 28px; height: 28px;
  border: none; border-radius: 7px;
  background: transparent;
  color: var(--dim);
  font-size: 15px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.icon-btn:hover { background: var(--bg4); color: var(--text); }
.icon-btn.close:hover { color: var(--red); }
.icon-btn.active { color: var(--accent2); background: var(--bg4); }

/* filter chips */
.filter-row { display: flex; gap: 6px; padding: 0 12px 8px; flex-wrap: wrap; }
.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--border);
  background: var(--bg2);
  color: var(--dim);
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 12px;
  cursor: pointer;
}
.filter-chip.active { border-color: var(--accent); color: var(--text); background: var(--bg3); }
.filter-count { font-size: 10px; background: var(--bg4); border-radius: 8px; padding: 0 5px; color: var(--dim); }
.filter-chip.active .filter-count { color: var(--accent2); }

/* status dots */
.st-dot {
  position: absolute;
  left: 9px;
  top: 13px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--dim);
}
.st-dot.running { background: var(--amber); box-shadow: 0 0 6px var(--amber); animation: pulse 1.2s infinite; }
.st-dot.done { background: var(--green); }
.st-dot.error { background: var(--red); }

/* stage indicator */
.stage-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--dim);
  background: var(--bg3);
  border: 1px solid var(--border);
  padding: 3px 9px;
  border-radius: 12px;
  white-space: nowrap;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* attachments */
.attach-row { display: flex; gap: 8px; padding: 0 2px 8px; flex-wrap: wrap; align-items: center; }
.attach-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border);
  background: var(--bg3);
  border-radius: 8px;
  padding: 4px 8px 4px 4px;
  font-size: 12px;
  max-width: 220px;
}
.attach-thumb { width: 26px; height: 26px; border-radius: 5px; object-fit: cover; background: var(--bg4); flex-shrink: 0; }
.attach-file { font-size: 15px; flex-shrink: 0; }
.attach-name { color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.attach-size { color: var(--dim); font-size: 10.5px; flex-shrink: 0; }
.attach-del {
  width: 18px; height: 18px;
  border: none; border-radius: 4px;
  background: transparent; color: var(--dim);
  cursor: pointer; font-size: 13px; line-height: 1;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.attach-del:hover { background: var(--bg4); color: var(--red); }
.attach-clear {
  border: none; background: transparent; color: var(--dim);
  font-size: 11px; cursor: pointer; padding: 4px 6px; border-radius: 6px;
}
.attach-clear:hover { color: var(--red); background: var(--bg3); }

/* detail panel */
.detail-panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 320px;
  max-width: 80vw;
  z-index: 30;
  display: flex;
  flex-direction: column;
  background: var(--bg2);
  border-left: 1px solid var(--border);
  box-shadow: -8px 0 24px rgba(0, 0, 0, .35);
}
.detail-backdrop {
  position: absolute;
  inset: 0;
  z-index: 29;
  background: rgba(4, 6, 10, .35);
  cursor: default;
}
.detail-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
}
.detail-tabs { display: flex; gap: 4px; }
.detail-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: none;
  background: transparent;
  color: var(--dim);
  font-size: 12.5px;
  padding: 5px 10px;
  border-radius: 7px;
  cursor: pointer;
}
.detail-tab.active { background: var(--bg4); color: var(--text); }
.tab-badge { font-size: 10px; background: var(--bg4); border-radius: 8px; padding: 0 5px; color: var(--dim); }
.detail-tab.active .tab-badge { color: var(--accent2); }
.detail-body { flex: 1; overflow-y: auto; padding: 8px; }
.detail-empty { text-align: center; color: var(--dim); font-size: 12px; padding: 30px 12px; }

.tl-entry {
  display: flex;
  gap: 10px;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 2px;
}
.tl-entry:hover { background: var(--bg3); }
.tl-icon {
  width: 20px; height: 20px;
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px;
  border-radius: 5px;
  background: var(--bg4);
  color: var(--dim);
}
.tl-icon.running { color: var(--amber); animation: spin 1s linear infinite; }
.tl-icon.done, .tl-icon.done { color: var(--green); }
.tl-icon.error { color: var(--red); }
.tl-icon.think { color: var(--accent2); }
.tl-main { flex: 1; min-width: 0; }
.tl-label {
  font-size: 11px;
  color: var(--dim);
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}
.tl-step-name { color: var(--text); font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace; font-size: 11.5px; }
.tl-status { font-size: 10px; border-radius: 8px; padding: 0 6px; }
.tl-status.running { color: var(--amber); background: rgba(251, 191, 36, .1); }
.tl-status.done { color: var(--green); background: rgba(47, 214, 165, .1); }
.tl-status.error { color: var(--red); background: rgba(244, 104, 109, .1); }
.tl-text { font-size: 12px; color: var(--text); }
.tl-args {
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 10.5px;
  color: #9aa6ba;
  margin-top: 2px;
}
.one-line { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dim { color: var(--dim); }

.q-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: none;
  background: transparent;
  color: var(--text);
  text-align: left;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 2px;
}
.q-item:hover { background: var(--bg3); }
.q-idx {
  width: 18px; height: 18px;
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 10.5px;
  border-radius: 5px;
  background: var(--bg4);
  color: var(--accent2);
}
.q-text { font-size: 12.5px; flex: 1; min-width: 0; }

/* sidebar search */
.sidebar-search { padding: 0 12px 8px; }
.s-search {
  width: 100%;
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg2);
  color: var(--text);
  font-size: 12px;
  outline: none;
}
.s-search:focus { border-color: var(--accent); }
.s-search::placeholder { color: #5b6476; }

/* pin + rename */
.session-pin {
  position: absolute;
  right: 30px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--dim);
  font-size: 13px;
  opacity: 0;
  cursor: pointer;
  width: 20px; height: 20px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 5px;
}
.session-pin.on { opacity: 1; color: var(--amber); }
.session-item:hover .session-pin { opacity: 1; }
.session-pin:hover { background: var(--bg4); }
.session-item.pinned { background: var(--bg3); }
.session-item.pinned .session-title { color: var(--accent2); }
.session-item.editing { padding: 6px 10px; }
.rename-input {
  width: 100%;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--accent);
  border-radius: 6px;
  background: var(--bg2);
  color: var(--text);
  font-size: 12.5px;
  outline: none;
}

/* message actions + usage + flash */
.msg { position: relative; }
.msg.flash { animation: flashbg 1.4s ease; }
@keyframes flashbg { 0%, 40% { background: rgba(108, 92, 231, .16); border-radius: 8px; } 100% { background: transparent; } }
.msg-actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
  opacity: 0;
  transition: opacity .12s;
}
.msg:hover .msg-actions { opacity: 1; }
.msg-actions button {
  border: 1px solid var(--border);
  background: var(--bg2);
  color: var(--dim);
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  cursor: pointer;
}
.msg-actions button:hover:not(:disabled) { color: var(--text); background: var(--bg4); border-color: var(--accent); }
.msg-actions button:disabled { opacity: .4; cursor: default; }
.msg-usage {
  margin-top: 6px;
  font-size: 11px;
  color: var(--dim);
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
}
.md.clipped { max-height: 320px; overflow: hidden; position: relative; }
.md.clipped::after {
  content: '';
  position: absolute;
  left: 0; right: 0; bottom: 0; height: 60px;
  background: linear-gradient(to top, var(--bg), transparent);
  pointer-events: none;
}

/* code copy (injected via v-html, needs :deep) */
.md :deep(.code-wrap) { position: relative; margin: 0 0 10px; }
.md :deep(.code-wrap pre) { margin: 0; }
.md :deep(.code-copy) {
  position: absolute;
  top: 6px;
  right: 6px;
  border: 1px solid var(--border);
  background: var(--bg4);
  color: var(--dim);
  font-size: 10.5px;
  padding: 2px 8px;
  border-radius: 5px;
  cursor: pointer;
  opacity: 0;
  transition: opacity .12s;
}
.md :deep(.code-wrap:hover .code-copy) { opacity: 1; }
.md :deep(.code-copy:hover) { color: var(--text); border-color: var(--accent); }

/* in-conversation search */
.conv-search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg2);
}
.conv-search-icon { color: var(--dim); font-size: 14px; }
.conv-search-input {
  flex: 1;
  height: 28px;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text);
  font-size: 12.5px;
}
.conv-search-input::placeholder { color: #5b6476; }
.conv-search-count { font-size: 11px; color: var(--dim); }
.conv-search-btn {
  height: 24px;
  min-width: 26px;
  border: 1px solid var(--border);
  background: var(--bg3);
  color: var(--dim);
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.conv-search-btn:hover { color: var(--text); border-color: var(--accent); }
.conv-search-btn.close:hover { color: var(--red); border-color: rgba(244, 104, 109, .4); }

/* slash menu */
.slash-menu {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  right: 0;
  max-height: 260px;
  overflow-y: auto;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, .45);
  padding: 6px;
  z-index: 30;
}
.slash-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  border: none;
  background: transparent;
  color: var(--text);
  text-align: left;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
}
.slash-item.active { background: var(--bg4); box-shadow: inset 2px 0 0 var(--accent); }
.slash-icon { width: 22px; text-align: center; }
.slash-name { font-size: 12.5px; font-weight: 600; width: 46px; flex-shrink: 0; color: var(--accent2); }
.slash-desc {
  font-size: 12px;
  color: var(--dim);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.slash-empty { padding: 14px; text-align: center; color: var(--dim); font-size: 12px; }
.input-area { position: relative; }

/* deliverables + skills */
.deliv-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 6px;
  background: var(--bg3);
}
.deliv-icon { font-size: 16px; flex-shrink: 0; }
.deliv-main { flex: 1; min-width: 0; }
.deliv-name { font-size: 12.5px; color: var(--text); }
.deliv-step { font-size: 10.5px; color: var(--dim); margin-top: 1px; }
.deliv-open {
  flex-shrink: 0;
  height: 26px;
  padding: 0 10px;
  border: 1px solid rgba(47, 214, 165, .3);
  background: rgba(47, 214, 165, .08);
  color: var(--green);
  border-radius: 6px;
  font-size: 11.5px;
  cursor: pointer;
}
.deliv-open:hover { background: rgba(47, 214, 165, .16); }

.skill-item {
  display: flex;
  gap: 10px;
  padding: 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 6px;
  background: var(--bg3);
}
.skill-icon { flex-shrink: 0; }
.skill-main { flex: 1; min-width: 0; }
.skill-name {
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  color: var(--accent2);
  display: flex;
  align-items: center;
  gap: 6px;
}
.skill-tag-local {
  font-family: inherit;
  font-size: 9.5px;
  color: var(--green);
  border: 1px solid rgba(47, 214, 165, .3);
  padding: 0 5px;
  border-radius: 6px;
}
.skill-desc { font-size: 11.5px; color: var(--dim); margin-top: 3px; line-height: 1.5; }

/* settings switch */
.switch-label {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  font-size: 12.5px;
  color: var(--text);
  cursor: pointer;
  user-select: none;
}
.switch { accent-color: var(--accent); width: 15px; height: 15px; cursor: pointer; }

/* agent panel */
.agent-panel { width: 520px; max-width: 94vw; max-height: 86vh; display: flex; flex-direction: column; }
.agent-tabs { display: flex; gap: 4px; margin-bottom: 12px; }
.agent-tab {
  flex: 1;
  border: 1px solid var(--border);
  background: var(--bg3);
  color: var(--dim);
  font-size: 12.5px;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
}
.agent-tab.active { color: var(--text); border-color: var(--accent); background: var(--bg4); }
.agent-body { flex: 1; overflow-y: auto; min-height: 0; padding-right: 4px; }

.mcp-add, .skill-create, .skill-url {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg3);
  margin-bottom: 12px;
}
.mcp-add-row { display: flex; gap: 8px; }
.mcp-transport { max-width: 130px; flex: 0 0 130px; }
.mcp-add-actions { display: flex; justify-content: flex-end; gap: 8px; }
.mcp-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.mcp-server {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg3);
}
.mcp-server-main { flex: 1; min-width: 0; }
.mcp-server-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.mcp-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--dim); flex-shrink: 0; }
.mcp-dot.on { background: var(--green); box-shadow: 0 0 6px var(--green); }
.mcp-dot.err { background: var(--red); }
.mcp-badge {
  font-size: 10px;
  color: var(--accent2);
  border: 1px solid rgba(0, 210, 255, .25);
  padding: 1px 6px;
  border-radius: 8px;
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
}
.mcp-badge.local { color: var(--green); border-color: rgba(47, 214, 165, .3); }
.mcp-server-sub {
  font-size: 11px;
  color: var(--dim);
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  gap: 8px;
  align-items: center;
}
.mcp-err { color: var(--red); }
.mcp-tool-count {
  font-size: 10px;
  color: var(--green);
  margin-left: auto;
  flex-shrink: 0;
}
.mcp-server-actions { display: flex; gap: 6px; flex-shrink: 0; }
.mcp-edit { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.mcp-btn {
  height: 26px;
  padding: 0 10px;
  border: 1px solid var(--border);
  background: var(--bg4);
  color: var(--dim);
  border-radius: 6px;
  font-size: 11.5px;
  cursor: pointer;
}
.mcp-btn.on { color: var(--green); border-color: rgba(47, 214, 165, .3); }
.mcp-btn.del:hover { color: var(--red); border-color: rgba(244, 104, 109, .4); }
.mcp-btn.builtin-label { cursor: default; opacity: .7; }

.mcp-tools { border-top: 1px solid var(--border); padding-top: 10px; }
.mcp-tools-hd { font-size: 11.5px; color: var(--dim); margin-bottom: 6px; font-weight: 600; }
.mcp-tool {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 5px 8px;
  border-radius: 6px;
}
.mcp-tool:hover { background: var(--bg3); }
.mcp-tool-row { display: flex; align-items: center; gap: 10px; width: 100%; }
.mcp-tool-info { flex: 1; min-width: 0; display: flex; gap: 8px; align-items: baseline; }
.mcp-tool-name {
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
  color: var(--accent2);
  flex-shrink: 0;
}
.mcp-tool-desc { font-size: 11.5px; color: var(--dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-test {
  border-top: 1px solid var(--border);
  padding-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tool-test-args {
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
  height: 70px;
  resize: vertical;
  padding: 8px 10px;
}
.tool-test-result {
  max-height: 180px;
  overflow: auto;
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
  color: var(--text);
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  white-space: pre-wrap;
  word-break: break-all;
}

.skill-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.skill-textarea { height: 90px; resize: vertical; padding: 8px 10px; font-family: inherit; line-height: 1.5; }
.skill-url { flex-direction: row; }

/* ---------------- messages ---------------- */
.msgs {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px 10px;
}
.msg { margin-bottom: 18px; }

.msg-user-label {
  font-size: 11px;
  color: var(--dim);
  margin-bottom: 5px;
  font-weight: 600;
}
.user-text {
  font-size: 14px;
  color: var(--text);
  padding: 9px 13px;
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 10px;
  border-top-left-radius: 2px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* reasoning */
.reasoning {
  margin-bottom: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg2);
}
.reasoning-hd {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  border: none;
  background: var(--bg3);
  color: var(--dim);
  font-size: 12px;
  padding: 6px 10px;
  cursor: pointer;
}
.reasoning-hd:hover { color: var(--text); }
.tl-text {
  margin-bottom: 10px;
  padding: 2px 2px;
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}
.reasoning-body {
  padding: 8px 12px;
  font-size: 12.5px;
  line-height: 1.65;
  color: #a7b0c0;
  font-style: italic;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
  overflow-y: auto;
}

/* tool steps */
.step {
  margin-bottom: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg2);
}
.step-hd {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: none;
  background: var(--bg3);
  color: var(--text);
  font-size: 12.5px;
  padding: 7px 10px;
  cursor: pointer;
  text-align: left;
}
.step-hd:hover { background: var(--bg4); }
.step-icon { color: var(--dim); font-size: 13px; width: 14px; text-align: center; }
.step.running .step-icon { color: var(--amber); animation: spin 1s linear infinite; display: inline-block; }
@keyframes spin { to { transform: rotate(360deg); } }
.step.done .step-icon { color: var(--green); }
.step.error .step-icon { color: var(--red); }
.step-name {
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 12.5px;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.step-status { font-size: 11px; color: var(--dim); flex-shrink: 0; }
.step-status.running { color: var(--amber); }
.step-status.done { color: var(--green); }
.step-status.error { color: var(--red); }
.chev { color: var(--dim); font-size: 11px; flex-shrink: 0; }
.step-body { padding: 8px 10px; }
.step-sec { margin-bottom: 6px; }
.step-sec-label { font-size: 10.5px; color: var(--dim); text-transform: uppercase; letter-spacing: .5px; }
.step-args, .step-result {
  margin-top: 4px;
  padding: 8px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.55;
  color: #b7c1d4;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow: auto;
}
.step-result.err { color: var(--red); }

/* pending */
.pending {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 2px;
}
.pdot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--dim);
  animation: blink 1.2s infinite;
}
.pdot:nth-child(2) { animation-delay: .2s; }
.pdot:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%,80%,100% { opacity: .25; } 40% { opacity: 1; } }
.pending-text { font-size: 12px; color: var(--dim); }

.error-bubble {
  padding: 8px 12px;
  background: rgba(244, 104, 109, .1);
  border: 1px solid rgba(244, 104, 109, .3);
  color: var(--red);
  border-radius: 8px;
  font-size: 12.5px;
  margin-bottom: 8px;
}

/* markdown body (v-html content, use :deep) */
.md {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text);
  word-break: break-word;
}
.md :deep(*) { box-sizing: border-box; }
.md :deep(p) { margin: 0 0 10px; }
.md :deep(h1), .md :deep(h2), .md :deep(h3), .md :deep(h4) {
  margin: 14px 0 8px;
  font-weight: 700;
  line-height: 1.4;
}
.md :deep(h1) { font-size: 17px; }
.md :deep(h2) { font-size: 15.5px; }
.md :deep(h3) { font-size: 14.5px; }
.md :deep(ul), .md :deep(ol) { padding-left: 20px; margin: 0 0 10px; }
.md :deep(li) { margin: 3px 0; }
.md :deep(code) {
  font-family: 'Cascadia Code', 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  background: var(--bg3);
  border: 1px solid var(--border);
  padding: 1.5px 5px;
  border-radius: 4px;
  color: #e6b9ff;
}
.md :deep(pre) {
  margin: 0 0 10px;
  padding: 12px 14px;
  background: #0c111b;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow-x: auto;
}
.md :deep(pre code) {
  background: transparent;
  border: none;
  padding: 0;
  color: var(--text);
  font-size: 12.5px;
  line-height: 1.6;
}
.md :deep(blockquote) {
  margin: 0 0 10px;
  padding: 4px 12px;
  border-left: 3px solid var(--accent);
  color: var(--dim);
  background: var(--bg2);
  border-radius: 0 6px 6px 0;
}
.md :deep(a) { color: var(--accent2); text-decoration: none; }
.md :deep(a):hover { text-decoration: underline; }
.md :deep(table) {
  border-collapse: collapse;
  margin: 0 0 10px;
  width: 100%;
  font-size: 12.5px;
}
.md :deep(th), .md :deep(td) {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}
.md :deep(th) { background: var(--bg3); }
.md :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 14px 0; }
.md :deep(strong) { font-weight: 700; }

/* empty */
.empty { text-align: center; padding-top: 12vh; }
.empty-mark {
  width: 64px; height: 64px;
  margin: 0 auto 18px;
  display: flex; align-items: center; justify-content: center;
  font-size: 30px;
  color: var(--accent2);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(108, 92, 231, .15), rgba(0, 210, 255, .15));
  border: 1px solid var(--border);
}
.empty-title { font-size: 17px; font-weight: 700; margin: 0 0 6px; }
.empty-sub { font-size: 13px; color: var(--dim); margin: 0 0 26px; }
.suggestions { display: flex; flex-direction: column; gap: 8px; align-items: center; }
.suggestion {
  border: 1px solid var(--border);
  background: var(--bg2);
  color: var(--text);
  font-size: 13px;
  padding: 8px 18px;
  border-radius: 20px;
  cursor: pointer;
  transition: all .15s;
}
.suggestion:hover { border-color: var(--accent); background: var(--bg3); color: var(--accent2); }

/* ---------------- input ---------------- */
.input-area { padding: 10px 16px 12px; border-top: 1px solid var(--border); background: var(--bg2); }
.input-box {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  border: 1px solid var(--border);
  background: var(--bg3);
  border-radius: 10px;
  padding: 8px 8px 8px 12px;
  transition: border-color .15s, box-shadow .15s;
}
.input-box:focus-within, .input-box.focused {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(108, 92, 231, .18);
}
.input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text);
  font-size: 13.5px;
  line-height: 1.5;
  resize: none;
  font-family: inherit;
  max-height: 160px;
  padding: 4px 0;
}
.input::placeholder { color: #5b6476; }
.input-tools { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.tool-btn {
  width: 30px; height: 30px;
  border: none; border-radius: 8px;
  background: transparent;
  font-size: 15px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.tool-btn:hover { background: var(--bg4); }
.tool-btn.active { background: rgba(244, 104, 109, .15); }
.send-btn {
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), #8f6cff);
  color: #fff;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  display: flex; align-items: center;
}
.send-btn:disabled { opacity: .45; cursor: not-allowed; }
.send-btn:hover:not(:disabled) { filter: brightness(1.12); }
.send-btn.stop { background: var(--bg4); color: var(--red); border: 1px solid rgba(244, 104, 109, .3); }
.input-hint { display: flex; gap: 16px; padding: 6px 4px 0; font-size: 11px; color: #59627a; }

/* ---------------- palette ---------------- */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(5, 8, 13, .6);
  backdrop-filter: blur(3px);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 12vh;
  z-index: 100;
}
.palette {
  width: 460px;
  max-width: 92vw;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, .5);
  overflow: hidden;
}
.palette-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}
.palette-prefix { color: var(--accent2); font-size: 16px; }
.palette-input {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text);
  font-size: 14px;
}
.palette-input::placeholder { color: #5b6476; }
.palette-esc {
  font-size: 10px;
  color: var(--dim);
  border: 1px solid var(--border);
  padding: 2px 6px;
  border-radius: 4px;
}
.palette-list { max-height: 320px; overflow-y: auto; padding: 6px; }
.palette-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 13px;
  padding: 9px 10px;
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
}
.palette-item.active { background: var(--bg4); box-shadow: inset 2px 0 0 var(--accent); }
.palette-icon { width: 20px; text-align: center; color: var(--accent2); }
.palette-label { flex: 1; }
.palette-kbd { font-size: 11px; color: var(--dim); border: 1px solid var(--border); padding: 1px 6px; border-radius: 4px; }
.palette-empty { padding: 18px; text-align: center; color: var(--dim); font-size: 12px; }

/* ---------------- settings ---------------- */
.settings-panel {
  width: 420px;
  max-width: 92vw;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, .5);
  padding: 18px;
}
.settings-hd { font-size: 15px; font-weight: 700; margin-bottom: 16px; }
.field { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.field label { width: 76px; font-size: 12.5px; color: var(--dim); flex-shrink: 0; }
.s-input {
  flex: 1;
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg3);
  color: var(--text);
  font-size: 12.5px;
  outline: none;
}
.s-input:focus { border-color: var(--accent); }
.settings-note { font-size: 11.5px; color: var(--dim); margin: 4px 0 14px; line-height: 1.6; }
.settings-actions { display: flex; justify-content: flex-end; gap: 8px; }
.btn-ghost {
  height: 32px; padding: 0 16px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: transparent;
  color: var(--dim);
  font-size: 12.5px;
  cursor: pointer;
}
.btn-ghost:hover { color: var(--text); background: var(--bg3); }
.btn-primary {
  height: 32px; padding: 0 18px;
  border: none; border-radius: 7px;
  background: linear-gradient(135deg, var(--accent), #8f6cff);
  color: #fff;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.btn-primary:hover { filter: brightness(1.12); }

/* ---------------- toast ---------------- */
.toast {
  position: fixed;
  left: 50%;
  bottom: 44px;
  transform: translateX(-50%);
  background: var(--bg4);
  border: 1px solid var(--border);
  color: var(--text);
  font-size: 12.5px;
  padding: 8px 16px;
  border-radius: 8px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, .4);
  z-index: 200;
}

/* ---------------- transitions ---------------- */
.fade-enter-active, .fade-leave-active { transition: opacity .15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.toast-enter-active, .toast-leave-active { transition: all .2s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }

/* ---------------- scrollbar ---------------- */
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-thumb { background: #262f40; border-radius: 5px; }
::-webkit-scrollbar-thumb:hover { background: #32405a; }
::-webkit-scrollbar-track { background: transparent; }
</style>
