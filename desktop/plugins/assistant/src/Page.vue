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
interface Msg {
  id: number
  role: 'user' | 'assistant'
  text: string
  html: string
  reasoning: string
  reasoningOpen: boolean
  steps: Step[]
  pending: boolean
  error: string
}
interface Session {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  messages: Msg[]
  promptHistory: string[]
  histIdx: number
}
interface Config {
  mode: 'backend' | 'direct'
  apiKey: string
  baseUrl: string
  model: string
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
const detailTab = ref<'process' | 'history'>('process')
const statusFilter = ref<'all' | 'running' | 'done' | 'error'>('all')
const stage = ref('')
const attachments = ref<Attachment[]>([])
const msgsRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const paletteInputRef = ref<HTMLInputElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const detailBodyRef = ref<HTMLElement | null>(null)

const cfg = ref<Config>({ mode: 'backend', apiKey: '', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini' })
const cfgMode = ref('backend')
const cfgKey = ref('')
const cfgUrl = ref('https://api.openai.com/v1')
const cfgModel = ref('gpt-4o-mini')

let idSeq = 1
let stepSeq = 1
let abortCtl: AbortController | null = null
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
  if (statusFilter.value === 'all') return sessions.value
  return sessions.value.filter(s => sessionStatus(s) === statusFilter.value)
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
    messages: s.messages.slice(-200).map(m => ({
      id: m.id,
      role: m.role,
      text: m.text,
      reasoning: m.reasoning,
      steps: m.steps.map(st => ({ id: st.id, name: st.name, args: st.args, result: st.result, status: st.status })),
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
      messages: (s.messages || []).map((m: any) => ({
        id: m.id,
        role: m.role,
        text: m.text || '',
        html: '',
        reasoning: m.reasoning || '',
        reasoningOpen: true,
        steps: (m.steps || []).map((st: any) => ({ id: st.id, name: st.name, args: st.args, result: st.result || '', status: st.status, collapsed: false })),
        pending: false,
        error: m.error || '',
      })),
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
      cfg.value = { mode: 'backend', apiKey: '', baseUrl: 'https://api.openai.com/v1', model: 'gpt-4o-mini', ...c }
      cfgMode.value = cfg.value.mode
      cfgKey.value = cfg.value.apiKey
      cfgUrl.value = cfg.value.baseUrl
      cfgModel.value = cfg.value.model
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

function scrollBottom() {
  const el = msgsRef.value
  if (!el) return
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 160) {
    requestAnimationFrame(() => { if (el) el.scrollTop = el.scrollHeight })
  }
}

function autoSize() {
  nextTick(() => {
    const el = inputRef.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  })
}
watch(input, autoSize)

watch(
  () => (detailOpen.value && detailTab.value === 'process' ? processEntries.value.length : 0),
  () => {
    nextTick(() => {
      const el = detailBodyRef.value
      if (el) el.scrollTop = el.scrollHeight
    })
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
  m.reasoning += content
  scrollBottom()
}

function startStep(m: Msg, name: string, args: any) {
  m.steps.push({ id: stepSeq++, name, args, result: '', status: 'running', collapsed: false })
  scrollBottom()
}

function finishStep(m: Msg, name: string, result: string, isError: boolean) {
  const st = [...m.steps].reverse().find(s => s.name === name && s.status === 'running')
  if (st) {
    st.result = result
    st.status = isError ? 'error' : 'done'
  }
}

function handleEvent(m: Msg, data: any) {
  switch (data.type) {
    case 'token': appendToken(m, data.content || ''); stage.value = '正在生成回复'; break
    case 'reasoning': appendReasoning(m, data.content || ''); stage.value = '正在思考分析'; break
    case 'tool_call': startStep(m, data.name, data.arguments); stage.value = `正在执行 · ${data.name}`; break
    case 'tool_result': finishStep(m, data.name, data.content || '', !!data.error); break
    case 'error': m.error = data.content || 'AI 请求出错'; break
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
  s.messages.push({ id: idSeq++, role: 'user', text: message, html: '', reasoning: '', reasoningOpen: false, steps: [], pending: false, error: '' })
  s.promptHistory.push(message)
  s.histIdx = s.promptHistory.length
  input.value = ''
  autoSize()
  const asst: Msg = { id: idSeq++, role: 'assistant', text: '', html: '', reasoning: '', reasoningOpen: true, steps: [], pending: true, error: '' }
  s.messages.push(asst)
  setTitleFrom(s, message)
  s.updatedAt = Date.now()
  loading.value = true
  stage.value = '正在思考'
  abortCtl = new AbortController()
  try {
    const history = s.messages.slice(0, -1).filter(m => m.role === 'user' || (m.role === 'assistant' && m.text))
      .map(m => ({ role: m.role, content: m.text }))
    await streamMessage(message, history, images, asst)
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
    scrollBottom()
    nextTick(() => inputRef.value?.focus())
  }
}

function stop() {
  abortCtl?.abort()
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

function openDetail(tab: 'process' | 'history') {
  detailTab.value = tab
  detailOpen.value = true
}

// ---------------- command palette ----------------
const commands = computed(() => [
  { id: 'new', label: '新建会话', search: 'new session', icon: '＋', kbd: 'Ctrl+O', run: () => { newSession(); showToast('已新建会话') } },
  { id: 'clear', label: '清空当前会话', search: 'clear', icon: '⌫', kbd: 'Ctrl+L', run: () => { clearSession(); showToast('已清空会话') } },
  { id: 'sidebar', label: sidebar.value ? '隐藏侧边栏' : '显示侧边栏', search: 'sidebar toggle', icon: '☰', kbd: 'Ctrl+B', run: () => { sidebar.value = !sidebar.value } },
  { id: 'detail', label: detailOpen.value ? '收起详情面板' : '打开详情面板', search: 'detail panel process', icon: '▤', kbd: 'Ctrl+P', run: () => { detailOpen.value = !detailOpen.value; if (detailOpen.value) detailTab.value = 'process' } },
  { id: 'history', label: '查看历史提问', search: 'history questions', icon: '⏱', kbd: '', run: () => openDetail('history') },
  { id: 'copy', label: '复制最后回复', search: 'copy', icon: '⧉', kbd: '', run: () => copyLastReply() },
  { id: 'export', label: '复制会话为 JSON', search: 'export json', icon: '⇩', kbd: '', run: () => exportSession() },
  { id: 'settings', label: '打开设置', search: 'settings config', icon: '⚙', kbd: '', run: () => { settingsOpen.value = true } },
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

function exportSession() {
  const s = current.value
  if (!s) return
  const data = { title: s.title, createdAt: new Date(s.createdAt).toISOString(), messages: s.messages.map(m => ({ role: m.role, content: m.role === 'assistant' && m.steps.length ? { text: m.text, steps: m.steps.map(st => ({ name: st.name, args: st.args, result: st.result, status: st.status })) } : m.text })) }
  navigator.clipboard.writeText(JSON.stringify(data, null, 2)).then(() => showToast('会话 JSON 已复制'), () => showToast('复制失败'))
}

// ---------------- keyboard ----------------
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
    return
  }
  const ctrl = e.ctrlKey || e.metaKey
  if (e.key === 'ArrowUp' && ctrl) { e.preventDefault(); histPrev(); return }
  if (e.key === 'ArrowDown' && ctrl) { e.preventDefault(); histNext(); return }
}

function onGlobalKey(e: KeyboardEvent) {
  if (paletteOpen.value || settingsOpen.value) return
  const ctrl = e.ctrlKey || e.metaKey
  const k = e.key.toLowerCase()
  if (ctrl && k === 'k') { e.preventDefault(); openPalette() }
  else if (ctrl && k === 'b') { e.preventDefault(); sidebar.value = !sidebar.value }
  else if (ctrl && k === 'p') { e.preventDefault(); detailOpen.value = !detailOpen.value; if (detailOpen.value) detailTab.value = 'process' }
  else if (ctrl && k === 'l') { e.preventDefault(); clearSession(); showToast('已清空会话') }
  else if (ctrl && k === 'o') { e.preventDefault(); newSession() }
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
  settingsOpen.value = true
}

function applySettings() {
  cfg.value = {
    mode: cfgMode.value as 'backend' | 'direct',
    apiKey: cfgKey.value,
    baseUrl: cfgUrl.value.replace(/\/+$/, ''),
    model: cfgModel.value,
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
  window.addEventListener('keydown', onGlobalKey)
  nextTick(() => inputRef.value?.focus())
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
      <div class="filter-row">
        <button v-for="f in (['all','running','done','error'] as const)" :key="f" class="filter-chip" :class="{ active: statusFilter === f }" @click="statusFilter = f">
          {{ f === 'all' ? '全部' : f === 'running' ? '进行中' : f === 'done' ? '已完成' : '失败' }}
          <span class="filter-count">{{ statusCounts[f] }}</span>
        </button>
      </div>
      <div class="session-list">
        <button v-for="s in filteredSessions" :key="s.id" class="session-item" :class="{ active: s.id === current?.id }" @click="switchSession(s.id)">
          <span class="st-dot" :class="sessionStatus(s)"></span>
          <span class="session-title">{{ s.title || '新会话' }}</span>
          <span class="session-meta">{{ timeAgo(s.updatedAt) }} · {{ s.messages.length }} 条</span>
          <span class="session-del" title="删除会话" @click.stop="deleteSession(s.id)">×</span>
        </button>
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
          <span class="mode-badge" :class="cfg.mode">{{ cfg.mode === 'backend' ? '后端代理' : '直连' }}</span>
          <button class="icon-btn" title="新建任务 (Ctrl+O)" @click="newSession">＋</button>
          <button class="icon-btn" title="历史提问" @click="openDetail('history')">⏱</button>
          <button class="icon-btn" :class="{ active: detailOpen }" title="详情面板 (Ctrl+P)" @click="detailOpen = !detailOpen; if (detailOpen) detailTab = 'process'">▤</button>
          <button class="icon-btn" title="打开命令面板 (Ctrl+K)" @click="openPalette">⌘</button>
          <button class="icon-btn" title="设置" @click="openSettings">⚙</button>
          <button class="icon-btn close" title="关闭" @click="close">×</button>
        </div>
      </header>

      <div ref="msgsRef" class="msgs">
        <template v-if="current">
          <div v-for="m in current.messages" :id="'msg-' + m.id" :key="m.id" class="msg" :class="m.role">
            <template v-if="m.role === 'user'">
              <div class="msg-user-label">你</div>
              <div class="user-text">{{ m.text }}</div>
            </template>
            <template v-else>
              <div v-if="m.reasoning" class="reasoning" :class="{ open: m.reasoningOpen }">
                <button class="reasoning-hd" @click="m.reasoningOpen = !m.reasoningOpen">
                  <span class="chev">{{ m.reasoningOpen ? '▾' : '▸' }}</span>
                  <span class="reasoning-title">思考过程</span>
                </button>
                <div v-if="m.reasoningOpen" class="reasoning-body">{{ m.reasoning }}</div>
              </div>

              <div v-for="st in m.steps" :key="st.id" class="step" :class="st.status">
                <button class="step-hd" @click="st.collapsed = !st.collapsed">
                  <span class="step-icon">{{ stepIcon(st) }}</span>
                  <span class="step-name">{{ st.name }}</span>
                  <span class="step-status" :class="st.status">
                    {{ st.status === 'running' ? '执行中' : st.status === 'error' ? '失败' : '完成' }}
                  </span>
                  <span class="chev">{{ st.collapsed ? '▸' : '▾' }}</span>
                </button>
                <div v-if="!st.collapsed" class="step-body">
                  <div class="step-sec">
                    <span class="step-sec-label">参数</span>
                    <pre class="step-args">{{ prettyJson(st.args) }}</pre>
                  </div>
                  <div v-if="st.result" class="step-sec">
                    <span class="step-sec-label">结果</span>
                    <pre class="step-result" :class="{ err: st.status === 'error' }">{{ st.result }}</pre>
                  </div>
                </div>
              </div>

              <div v-if="m.pending && !m.text && m.steps.length === 0" class="pending">
                <span class="pdot"></span><span class="pdot"></span><span class="pdot"></span>
                <span class="pending-text">思考中…</span>
              </div>
              <div v-if="m.error" class="error-bubble">{{ m.error }}</div>
              <div v-if="m.text" class="md" v-html="m.html"></div>
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

    <aside v-if="detailOpen" class="detail-panel">
      <div class="detail-hd">
        <div class="detail-tabs">
          <button class="detail-tab" :class="{ active: detailTab === 'process' }" @click="detailTab = 'process'">过程 <span class="tab-badge">{{ processEntries.length }}</span></button>
          <button class="detail-tab" :class="{ active: detailTab === 'history' }" @click="detailTab = 'history'">提问 <span class="tab-badge">{{ questionEntries.length }}</span></button>
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
        <template v-else>
          <div v-if="questionEntries.length === 0" class="detail-empty">还没有提问记录</div>
          <button v-for="(q, i) in questionEntries" :key="i" class="q-item" @click="scrollToMsg(q.msgId)">
            <span class="q-idx">{{ i + 1 }}</span>
            <span class="q-text one-line">{{ q.text }}</span>
          </button>
        </template>
      </div>
    </aside>

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
            </select>
          </div>
          <template v-if="cfgMode === 'direct'">
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
          <p class="settings-note">后端代理模式下,模型由服务端配置,直连模式仅在本机保存配置。</p>
          <div class="settings-actions">
            <button class="btn-ghost" @click="settingsOpen = false">取消</button>
            <button class="btn-primary" @click="applySettings">应用</button>
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
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg2);
  border-left: 1px solid var(--border);
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
.reasoning-body {
  padding: 8px 12px;
  font-size: 12.5px;
  line-height: 1.65;
  color: #a7b0c0;
  font-style: italic;
  white-space: pre-wrap;
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
