<template>
  <div class="page-wrapper chat-page">
    <div class="chat-layout">
      <aside class="session-pane page-card">
        <div class="session-head">
          <span class="pane-title">会话</span>
          <el-button size="small" type="primary" @click="newSession">新对话</el-button>
        </div>
        <el-input v-model="sessionQuery" size="small" clearable placeholder="搜索会话" class="session-search" />
        <div
          v-for="s in filteredSessions"
          :key="s.session_id"
          class="session-row"
          :class="{ active: s.session_id === sessionId }"
          @click="switchSession(s.session_id)"
          @contextmenu.prevent="startRename(s)"
        >
          <div v-if="renamingId !== s.session_id" class="session-main" @dblclick.stop="startRename(s)">
            <div class="session-title" :title="s.title || '未命名对话'">{{ s.title || '未命名对话' }}</div>
            <div class="session-time">{{ formatTime(s.updated_at) }}</div>
          </div>
          <div v-else class="session-main session-editing" @click.stop>
            <el-input
              v-model="renameValue"
              size="small"
              maxlength="200"
              placeholder="会话名称"
              @keyup.enter.stop="commitRename(s)"
              @keyup.esc.stop="cancelRename"
              @blur="commitRename(s)"
            />
          </div>
          <div v-if="renamingId !== s.session_id" class="session-actions">
            <button type="button" class="session-act" title="重命名会话" @click.stop="startRename(s)">✎</button>
            <button type="button" class="session-del" title="删除会话" @click.stop="removeSession(s.session_id)">×</button>
          </div>
        </div>
        <div v-if="sessions.length === 0" class="pane-empty">还没有会话</div>
      </aside>

      <section class="message-pane page-card">
        <div class="chat-toolbar">
          <div class="current-conv">
            <div class="current-title" @dblclick="currentSession && startRename(currentSession)">
              <span>{{ currentTitle }}</span>
              <button
                v-if="currentSession"
                type="button"
                class="title-edit"
                title="重命名会话"
                @click="startRename(currentSession)"
              >✎</button>
            </div>
            <div v-if="!loading" class="current-sub">{{ messages.length }} 条消息 · {{ botName }}</div>
            <div v-else class="run-pill">
              <span class="run-pulse"></span>
              <span class="run-stage-text">{{ stage || '处理中' }}</span>
              <span class="run-time">{{ elapsedLabel }}</span>
            </div>
          </div>
          <div class="toolbar-spacer"></div>
          <el-select v-model="botId" size="small" clearable placeholder="默认助手" style="width:180px">
            <el-option v-for="b in bots" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
        </div>

        <div v-if="approvals.length" class="approval-strip">
          <div v-for="a in approvals" :key="a.id" class="approval-item">
            <div class="approval-main">
              <span class="approval-tool">🔐 {{ a.tool_name }}</span>
              <span class="approval-reason">{{ a.reason || '需要确认后才能继续执行' }}</span>
            </div>
            <div class="approval-actions">
              <button type="button" class="ok" @click="decideApproval(a, true, false)">允许</button>
              <button type="button" class="ok ghost" @click="decideApproval(a, true, true)">总是允许</button>
              <button type="button" class="no" @click="decideApproval(a, false, false)">拒绝</button>
            </div>
          </div>
        </div>

        <div ref="bodyRef" class="message-body">
          <div v-if="messages.length === 0" class="chat-empty">
            <div class="chat-empty-icon">✦</div>
            <p>问点什么，或让助手帮你查日程、待办、邮件和笔记。</p>
            <div class="starter-prompts">
              <button v-for="p in starterPrompts" :key="p" type="button" @click="usePrompt(p)">{{ p }}</button>
            </div>
          </div>
          <div
            v-for="(m, i) in messages"
            :key="m.id || i"
            class="message-row"
            :class="[m.role, { live: m.pending }]"
          >
            <div class="msg-avatar">{{ m.role === 'user' ? '我' : '✦' }}</div>
            <div class="msg-main">
              <div class="bubble" :class="{ streaming: m.pending && m.role === 'assistant' }">
                <template v-if="m.role === 'assistant'">
                  <div v-if="m.reasoning" class="reasoning-box" :class="{ open: m.reasoningOpen }">
                    <button type="button" class="reasoning-hd" @click="m.reasoningOpen = !m.reasoningOpen">
                      <span class="chev">{{ m.reasoningOpen ? '▾' : '▸' }}</span>
                      <span class="reasoning-title">✦ 思考过程</span>
                      <span class="reasoning-len">{{ m.reasoning.length }} 字</span>
                    </button>
                    <div v-if="m.reasoningOpen" class="reasoning-text">{{ m.reasoning }}</div>
                  </div>

                  <div v-if="m.pending && !m.content && !m.steps?.length" class="thinking">
                    <span class="typing-dots"><i></i><i></i><i></i></span>
                    <span>{{ m.stage || '正在思考' }}</span>
                  </div>

                  <div v-if="m.content" class="assistant-body">
                    <div class="md-body" v-html="renderMarkdown(m.content)"></div>
                    <span v-if="m.pending" class="stream-cursor"></span>
                  </div>

                  <div v-if="m.error" class="error-box">⚠ {{ m.error }}</div>

                  <div v-if="m.steps?.length" class="tool-panel" :class="{ running: !!runningStep(m), failed: lastStepError(m) }">
                    <button type="button" class="tool-panel-toggle" @click="m.stepsOpen = !m.stepsOpen">
                      <span class="tool-spinner" :class="{ spin: !!runningStep(m) }">{{ runningStep(m) ? '◌' : lastStepError(m) ? '⚠' : '✓' }}</span>
                      <span class="tool-panel-title">
                        {{ m.steps.length }} 个工具调用<span v-if="runningStep(m)"> · {{ runningStep(m).name }}</span>
                      </span>
                      <span class="tool-badge" :class="{ running: !!runningStep(m), err: lastStepError(m) }">
                        {{ runningStep(m) ? '执行中' : lastStepError(m) ? '有失败' : '已完成' }}
                      </span>
                      <span class="tool-chev" :class="{ open: m.stepsOpen }">›</span>
                    </button>
                    <div v-if="m.stepsOpen" class="tool-steps">
                      <div v-for="(step, si) in m.steps" :key="step.id || si" class="tool-step" :class="step.status">
                        <div class="tool-step-head">
                          <span class="tool-step-icon">{{ toolIcon(step.name) }}</span>
                          <span class="tool-step-name">{{ step.name }}</span>
                          <span class="tool-step-duration" v-if="step.duration">{{ step.duration }}</span>
                          <span class="tool-step-status" :class="step.status">
                            {{ step.status === 'running' ? '执行中' : step.status === 'error' ? '失败' : '完成' }}
                          </span>
                        </div>
                        <div v-if="step.args" class="tool-sec">
                          <div class="tool-sec-hd">
                            <span>参数</span>
                            <button type="button" @click="copyText(step.args)">复制</button>
                          </div>
                          <pre class="tool-pre">{{ step.args }}</pre>
                        </div>
                        <div v-if="step.result" class="tool-sec">
                          <div class="tool-sec-hd">
                            <span>结果</span>
                            <button type="button" @click="copyText(step.result)">复制</button>
                          </div>
                          <pre class="tool-pre" :class="{ err: step.status === 'error' }">{{ truncate(step.result, 2400) }}</pre>
                        </div>
                        <div v-else-if="step.status === 'running'" class="tool-running">
                          <span class="typing-dots small"><i></i><i></i><i></i></span> 工具执行中…
                        </div>
                      </div>
                    </div>
                  </div>
                </template>
                <template v-else>
                  <div class="bubble-text">{{ m.content }}</div>
                </template>
              </div>
              <div class="msg-meta">
                <span>{{ m.role === 'user' ? '你' : 'AI 助手' }} · {{ formatTime(m.createdAt) }}</span>
                <span v-if="m.elapsed" class="msg-elapsed">{{ m.elapsed }}s</span>
                <button v-if="m.content" type="button" @click="copyMessage(m)">复制</button>
                <button v-if="m.role === 'assistant' && !loading" type="button" @click="retryMessage(i)">重新生成</button>
              </div>
            </div>
          </div>
        </div>

        <div class="context-bar">
          <el-button size="small" :icon="Plus" @click="pickerVisible = true">引用对象</el-button>
          <div v-if="contextRefs.length" class="context-chips">
            <span v-for="ref in contextRefs" :key="`${ref.type}:${ref.id}`" class="context-chip">
              <span class="chip-type">{{ ref.source_label || typeLabel(ref.type) }}</span>
              <span class="chip-title">{{ ref.title }}</span>
              <button type="button" class="chip-remove" @click="removeContextRef(ref)">×</button>
            </span>
          </div>
          <span v-else class="context-hint">可以引用日程、邮件、资讯、笔记、待办、文件或项目</span>
        </div>
        <div class="composer">
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            resize="none"
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            @keydown="onKeydown"
          />
          <el-button v-if="loading" type="danger" plain @click="stopRun">停止</el-button>
          <el-button v-else type="primary" :disabled="!input.trim()" @click="send()">发送</el-button>
        </div>
      </section>
    </div>

    <ObjectPicker v-model="pickerVisible" @select="addContextRef" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import client from '@/api/client'
import { apiUrl } from '@/api/base'
import { formatBackendDate } from '@/utils/date'
import ObjectPicker from '@/components/ObjectPicker.vue'

const route = useRoute()
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const starterPrompts = ['总结今天的待办', '帮我安排明天日程', '查看未读邮件']
const sessionQuery = ref('')
const renamingId = ref<string | null>(null)
const renameValue = ref('')
const sessions = ref<any[]>([])
const bots = ref<any[]>([])
const messages = ref<any[]>([])
const sessionId = ref<string>(newSessionId())
const botId = ref<number | null>(null)
const input = ref('')
const loading = ref(false)
const stage = ref('')
const elapsed = ref(0)
const runId = ref<number | null>(null)
const approvals = ref<any[]>([])
let elapsedTimer: ReturnType<typeof setInterval> | null = null
const bodyRef = ref<HTMLElement | null>(null)
const pickerVisible = ref(false)
const contextRefs = ref<any[]>([])
const contextCommentId = ref<number | null>(null)

const currentSession = computed(() => sessions.value.find((s) => s.session_id === sessionId.value))
const currentTitle = computed(() => currentSession.value?.title || '新对话')
const botName = computed(() => {
  const found = bots.value.find((b) => b.id === botId.value)
  return found?.name || '默认助手'
})

const elapsedLabel = computed(() => {
  if (elapsed.value < 60) return `${elapsed.value}s`
  const minutes = Math.floor(elapsed.value / 60)
  return `${minutes}m ${elapsed.value % 60}s`
})

const filteredSessions = computed(() => {
  const q = sessionQuery.value.trim().toLowerCase()
  if (!q) return sessions.value
  return sessions.value.filter((s) => String(s.title || '').toLowerCase().includes(q))
})

function renderMarkdown(text: string) {
  return DOMPurify.sanitize(md.render(String(text || '')))
}

function copyMessage(m: any) {
  navigator.clipboard.writeText(String(m.content || '')).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.error('复制失败'),
  )
}

function usePrompt(text: string) {
  input.value = text
  send()
}

const typeLabels: Record<string, string> = {
  schedule_event: '日程',
  mail_message: '邮件',
  source_item: '资讯',
  note: '笔记',
  todo: '待办',
  file: '文件',
  project: '项目',
}

function typeLabel(type: string) {
  return typeLabels[type] || type
}

function addContextRef(item: any) {
  if (!item?.type || !item?.id) return
  if (contextRefs.value.some((ref) => ref.type === item.type && ref.id === item.id)) return
  contextRefs.value.push({
    type: item.type,
    id: item.id,
    title: item.title || `${typeLabel(item.type)} #${item.id}`,
    subtitle: item.subtitle || '',
    source_label: item.source_label || typeLabel(item.type),
    url: item.url || '',
  })
}

function removeContextRef(ref: any) {
  contextRefs.value = contextRefs.value.filter(
    (item) => !(item.type === ref.type && item.id === ref.id),
  )
}

async function addContextRefById(type: string, id: number) {
  try {
    const { data } = await client.get(`/objects/${type}/${id}`)
    addContextRef(data)
  } catch {
    addContextRef({ type, id })
  }
}

async function applyRouteContext() {
  const rawRefs: string[] = []
  const single = route.query.ref
  if (typeof single === 'string') rawRefs.push(single)
  const many = route.query.refs
  if (typeof many === 'string') rawRefs.push(...many.split(','))
  for (const raw of rawRefs) {
    const [type, idText] = raw.split(':')
    const id = Number(idText)
    if (type && Number.isFinite(id)) await addContextRefById(type, id)
  }
  const direct: Array<[string, any]> = [
    ['schedule_event', route.query.event],
    ['mail_message', route.query.message],
    ['source_item', route.query.entry],
    ['note', route.query.note],
  ]
  for (const [type, value] of direct) {
    const id = Number(value)
    if (Number.isFinite(id) && id > 0) await addContextRefById(type, id)
  }
  const commentId = Number(route.query.comment)
  if (Number.isFinite(commentId) && commentId > 0) contextCommentId.value = commentId
}

function newSessionId() {
  return `web-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

async function loadSessions() {
  try {
    const { data } = await client.get('/chat/sessions')
    sessions.value = data || []
  } catch {
    sessions.value = []
  }
}

async function loadBots() {
  try {
    const { data } = await client.get('/bots')
    bots.value = (data || []).filter((b: any) => b.status !== 'archived')
  } catch {
    bots.value = []
  }
}

async function loadHistory() {
  try {
    const { data } = await client.get('/chat/history', {
      params: { session_id: sessionId.value, limit: 100 },
    })
    const items = (data || [])
      .filter((m: any) => m.content)
      .map((m: any, index: number) => ({
        id: `history-${index}-${m.created_at || ''}`,
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content,
        runId: m.run_id || null,
        steps: [] as any[],
        stepsOpen: false,
        reasoning: '',
        reasoningOpen: false,
        pending: false,
        stage: '',
        error: '',
        elapsed: 0,
        createdAt: m.created_at || '',
      }))
    messages.value = items
    await Promise.all(items
      .filter((m: any) => m.role === 'assistant' && m.runId)
      .map(async (m: any) => {
        try {
          const run = await client.get(`/runs/${m.runId}`)
          const steps = run.data?.steps || []
          m.steps = steps
            .filter((step: any) => step.type === 'tool' || step.type === 'delivery')
            .map((step: any) => ({
              id: step.id,
              name: step.tool_name || step.type,
              args: step.arguments ? JSON.stringify(step.arguments, null, 2) : '',
              result: step.result || '',
              status: step.status === 'error' || step.status === 'denied' ? 'error' : 'done',
              duration: '',
            }))
        } catch {
          m.steps = []
        }
      }))
    scrollBottom()
  } catch {
    messages.value = []
  }
}

function newSession() {
  sessionId.value = newSessionId()
  messages.value = []
  input.value = ''
  stage.value = ''
  cancelRename()
}

async function startRename(session: any) {
  if (!session?.session_id) return
  renamingId.value = session.session_id
  renameValue.value = session.title || ''
  await nextTick()
  const input = document.querySelector('.session-editing input') as HTMLInputElement | null
  input?.focus()
  input?.select()
}

function cancelRename() {
  renamingId.value = null
  renameValue.value = ''
}

async function commitRename(session: any) {
  if (renamingId.value !== session.session_id) return
  const title = renameValue.value.trim()
  if (!title) {
    ElMessage.warning('会话名称不能为空')
    return
  }
  const id = session.session_id
  renamingId.value = null
  try {
    await client.patch(`/chat/sessions/${encodeURIComponent(id)}`, { title })
    const found = sessions.value.find((item) => item.session_id === id)
    if (found) found.title = title
    ElMessage.success('会话已重命名')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '重命名失败')
  }
}

async function switchSession(id: string) {
  sessionId.value = id
  await loadHistory()
}

async function removeSession(id: string) {
  try {
    await ElMessageBox.confirm('删除这个会话及全部消息？', '删除会话', { type: 'warning' })
  } catch {
    return
  }
  await client.delete(`/chat/sessions/${encodeURIComponent(id)}`)
  if (sessionId.value === id) newSession()
  await loadSessions()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  send()
}

function startRunClock() {
  elapsed.value = 0
  stage.value = '正在提交…'
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = setInterval(() => { elapsed.value += 1 }, 1000)
}

function stopRunClock() {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

function prettyValue(value: any): string {
  if (value === null || value === undefined || value === '') return ''
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
      return value
    }
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function contentValue(value: any): string {
  if (typeof value === 'string') return value
  return prettyValue(value)
}

function upsertStep(message: any, data: any) {
  const id = Number(data.step_id || data.stepId || 0)
  const raw = String(data.status || 'running').toLowerCase()
  const status = raw === 'running' || raw === 'pending'
    ? 'running'
    : ['error', 'failed', 'denied', 'cancelled'].includes(raw) ? 'error' : 'done'
  const name = data.tool || data.name || (data.step_type === 'approval' ? '审批' : '步骤')
  let step = id ? message.steps.find((item: any) => item.id === id) : null
  if (!step) {
    step = {
      id: id || `step-${Date.now()}-${message.steps.length}`,
      name,
      args: prettyValue(data.arguments),
      result: contentValue(data.content),
      status,
      startedAt: Date.now(),
      duration: '',
    }
    message.steps.push(step)
  } else {
    if (data.tool || data.name) step.name = data.tool || data.name
    if (data.arguments !== undefined) step.args = prettyValue(data.arguments)
    if (data.content !== undefined) step.result = contentValue(data.content)
    step.status = status
  }
  if (status !== 'running' && step.startedAt && !step.duration) {
    step.duration = `${((Date.now() - step.startedAt) / 1000).toFixed(1)}s`
  }
  return step
}

function runningStep(message: any) {
  return [...(message.steps || [])].reverse().find((step: any) => step.status === 'running')
}

function lastStepError(message: any) {
  return (message.steps || []).some((step: any) => step.status === 'error')
}

const toolIconRules: Array<[RegExp, string]> = [
  [/search|find|query/, '⌕'],
  [/mail|email|imap|smtp/, '✉'],
  [/calendar|schedule|event/, '▦'],
  [/file|read|write|upload|download/, '▤'],
  [/shell|exec|terminal|code|command/, '⌘'],
  [/http|fetch|web|browser|url/, '◎'],
  [/todo|task|remind/, '✓'],
  [/note|memory/, '✎'],
  [/sql|database|db/, '▣'],
  [/approval|approve/, '🔐'],
]

function toolIcon(name: string) {
  const value = String(name || '').toLowerCase()
  const rule = toolIconRules.find(([pattern]) => pattern.test(value))
  return rule ? rule[1] : '⚙'
}

function truncate(value: string, limit: number) {
  const text = String(value || '')
  return text.length > limit ? `${text.slice(0, limit)}\n…（已截断）` : text
}

function copyText(text: string) {
  navigator.clipboard.writeText(String(text || '')).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.error('复制失败'),
  )
}

function upsertApproval(payload: any) {
  const id = Number(payload.approval_id || payload.id || 0)
  if (!id) return
  const value = {
    id,
    run_id: payload.run_id,
    tool_name: payload.tool || payload.tool_name || '工具调用',
    arguments: payload.arguments,
    reason: payload.reason || '',
    risk_level: payload.risk || payload.risk_level || 'exec',
    status: 'pending',
  }
  const existing = approvals.value.find((item) => item.id === id)
  if (existing) Object.assign(existing, value)
  else approvals.value.push(value)
}

async function loadApprovals() {
  try {
    const { data } = await client.get('/approvals', { params: { status: 'pending' } })
    approvals.value = data || []
  } catch {
    // ignore
  }
}

async function decideApproval(approval: any, approved: boolean, remember: boolean) {
  try {
    await client.post(`/approvals/${approval.id}/decision`, { approved, remember })
    approvals.value = approvals.value.filter((item) => item.id !== approval.id)
    ElMessage.success(approved ? (remember ? '已允许并记住' : '已允许') : '已拒绝')
    await resumeApprovedRun(approval)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '审批失败')
  }
}

async function stopRun() {
  if (!runId.value) return
  stage.value = '正在停止…'
  try {
    await client.post(`/runs/${runId.value}/cancel`)
  } catch {
    ElMessage.error('停止失败')
  }
}

function retryMessage(index: number) {
  if (loading.value) return
  const target = messages.value[index]
  if (!target || target.role !== 'assistant') return
  let userIndex = index - 1
  while (userIndex >= 0 && messages.value[userIndex].role !== 'user') userIndex -= 1
  if (userIndex < 0) return
  const text = messages.value[userIndex].content
  messages.value = messages.value.slice(0, index)
  input.value = text
  send(true)
}

async function consumeRun(
  rid: number,
  replyIndex: number,
  setStage: (value: string) => void,
) {
  const token = localStorage.getItem('token') || ''
  const streamResp = await fetch(apiUrl(`/runs/${rid}/stream`), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!streamResp.ok) throw new Error(`读取结果失败 (${streamResp.status})`)

  const reader = streamResp.body?.getReader()
  const decoder = new TextDecoder()
  let reply = ''
  let buffer = ''
  if (!reader) return

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''
    for (const ev of events) {
      if (!ev.startsWith('data: ')) continue
      try {
        const payload = JSON.parse(ev.slice(6))
        const message = messages.value[replyIndex]
        if (!message) continue
        if (payload.type === 'run_started') {
          runId.value = payload.run_id || runId.value
          setStage('开始执行')
        } else if (payload.type === 'run_status') {
          const labels: Record<string, string> = {
            running: '执行中',
            waiting_approval: '等待审批',
            done: '已完成',
            completed: '已完成',
            failed: '运行失败',
            cancelled: '已停止',
          }
          setStage(labels[payload.status] || payload.status || '执行中')
        } else if (payload.type === 'step') {
          const step = upsertStep(message, payload)
          if (step) {
            setStage(step.status === 'running' ? `执行中 · ${step.name}` : `完成 · ${step.name}`)
          }
          scrollBottom()
        } else if (payload.type === 'token') {
          reply += payload.content || ''
          message.content = reply
          setStage('正在生成回复')
          scrollBottom()
        } else if (payload.type === 'reasoning') {
          message.reasoning += payload.content || ''
          setStage('正在思考分析')
          scrollBottom()
        } else if (payload.type === 'tool_call') {
          const step = upsertStep(message, {
            step_id: `live-${message.steps.length + 1}`,
            tool: payload.name || 'tool',
            arguments: payload.arguments,
            status: 'running',
          })
          setStage(`正在执行 · ${step.name}`)
          scrollBottom()
        } else if (payload.type === 'tool_result') {
          const name = payload.tool || payload.name || '工具'
          const step = upsertStep(message, {
            step_id: `live-${message.steps.length}`,
            tool: name,
            content: payload.content || '',
            status: payload.error ? 'error' : 'done',
          })
          setStage(step.status === 'running' ? `执行中 · ${name}` : `完成 · ${name}`)
          scrollBottom()
        } else if (payload.type === 'approval') {
          upsertApproval(payload)
          setStage(`等待审批 · ${payload.tool || '工具'}`)
        } else if (payload.type === 'approval_required') {
          upsertApproval(payload)
          setStage(`等待审批 · ${payload.tool || '工具'}`)
        } else if (payload.type === 'done') {
          message.content = payload.reply || reply || message.content || '（无回复）'
          message.pending = false
          message.elapsed = elapsed.value
          if (payload.error) {
            message.error = payload.error
            ElMessage.error(payload.error)
          } else if (payload.status === 'cancelled') {
            setStage('已停止')
          }
          await loadSessions()
          await loadApprovals()
        } else if (payload.type === 'error') {
          message.error = payload.content || 'AI 请求出错'
          setStage('运行失败')
        }
      } catch { /* ignore malformed event */ }
    }
  }
  const message = messages.value[replyIndex]
  if (message && !message.content) message.content = '（无回复）'
}

async function resumeApprovedRun(approval: any) {
  const rid = Number(approval.run_id || 0)
  if (!rid) return
  const now = new Date().toISOString()
  const replyIndex = messages.value.push({
    id: `a-${Date.now()}`,
    role: 'assistant',
    content: '',
    steps: [],
    stepsOpen: true,
    reasoning: '',
    reasoningOpen: true,
    pending: true,
    stage: '继续执行',
    error: '',
    elapsed: 0,
    createdAt: now,
  }) - 1
  const setStage = (value: string) => {
    stage.value = value
    const message = messages.value[replyIndex]
    if (message) message.stage = value
  }
  loading.value = true
  startRunClock()
  runId.value = rid
  scrollBottom()
  try {
    await consumeRun(rid, replyIndex, setStage)
  } catch (e: any) {
    ElMessage.error(e.message || '继续执行失败')
  } finally {
    const message = messages.value[replyIndex]
    if (message) {
      message.pending = false
      if (!message.elapsed) message.elapsed = elapsed.value
    }
    loading.value = false
    stopRunClock()
    stage.value = ''
    runId.value = null
    scrollBottom()
  }
}

async function send(reuseUser = false) {
  const text = input.value.trim()
  if (!text || loading.value) return
  input.value = ''
  const now = new Date().toISOString()
  if (!reuseUser) {
    messages.value.push({
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
      steps: [],
      stepsOpen: false,
      reasoning: '',
      reasoningOpen: false,
      pending: false,
      stage: '',
      error: '',
      elapsed: 0,
      createdAt: now,
    })
  }
  const replyIndex = messages.value.push({
    id: `a-${Date.now()}`,
    role: 'assistant',
    content: '',
    steps: [],
    stepsOpen: true,
    reasoning: '',
    reasoningOpen: true,
    pending: true,
    stage: '正在思考',
    error: '',
    elapsed: 0,
    createdAt: now,
  }) - 1
  const replyMessage = messages.value[replyIndex]
  loading.value = true
  startRunClock()
  scrollBottom()

  const setStage = (value: string) => {
    stage.value = value
    const message = messages.value[replyIndex]
    if (message) message.stage = value
  }

  try {
    const token = localStorage.getItem('token') || ''
    const resp = await fetch(apiUrl('/chat/runs'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        message: text,
        session_id: sessionId.value,
        bot_id: botId.value || undefined,
        client_kind: 'web',
        context_refs: contextRefs.value.length
          ? contextRefs.value.map((ref) => ({ type: ref.type, id: ref.id }))
          : undefined,
        context_comment_id: contextCommentId.value || undefined,
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => null)
      throw new Error(err?.detail || `请求失败 (${resp.status})`)
    }
    const run = await resp.json()
    runId.value = run.run_id || null
    await consumeRun(run.run_id, replyIndex, setStage)
  } catch (e: any) {
    const message = messages.value[replyIndex]
    if (message) {
      message.error = e.message || '发送失败'
      message.content = message.content || ''
    }
    ElMessage.error(e.message || '发送失败')
  } finally {
    const message = messages.value[replyIndex]
    if (message) {
      message.pending = false
      if (!message.elapsed) message.elapsed = elapsed.value
    }
    loading.value = false
    stopRunClock()
    stage.value = ''
    runId.value = null
    scrollBottom()
  }
}

function scrollBottom() {
  nextTick(() => {
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  })
}

function formatTime(value: any) {
  return value ? formatBackendDate(value) : ''
}

onMounted(async () => {
  await applyRouteContext()
  await Promise.all([loadSessions(), loadBots(), loadApprovals()])
  await loadHistory()
})

onUnmounted(() => {
  stopRunClock()
})
</script>

<style scoped>
.chat-page { height: 100%; }
.chat-layout { display: grid; grid-template-columns: 230px 1fr; gap: 14px; height: calc(100vh - 110px); }
.session-pane { padding: 12px; display: flex; flex-direction: column; min-height: 0; }
.session-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.pane-title { font-size: 13px; font-weight: 600; color: #1a1a2e; }
.session-row { display: flex; align-items: center; gap: 6px; padding: 9px 10px; border-radius: 8px; cursor: pointer; }
.session-row:hover { background: #f5f7fa; }
.session-row.active { background: #ecf5ff; }
.session-main { min-width: 0; flex: 1; }
.session-title { font-size: 13px; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-time { font-size: 11px; color: #a0a4ad; margin-top: 2px; }
.pane-empty { padding: 30px 8px; text-align: center; color: #909399; font-size: 12px; }
.message-pane { display: flex; flex-direction: column; min-height: 0; padding: 12px 16px; }
.chat-toolbar { display: flex; align-items: center; gap: 10px; padding-bottom: 10px; border-bottom: 1px solid #f0f2f5; }
.session-hint { font-size: 12px; color: #909399; }
.message-body { flex: 1; overflow-y: auto; padding: 16px 4px; }
.chat-empty { text-align: center; color: #909399; padding-top: 80px; }
.chat-empty-icon { font-size: 40px; color: #c7d2fe; margin-bottom: 10px; }
.bubble-row { display: flex; margin-bottom: 14px; }
.bubble-row.user { justify-content: flex-end; }
.bubble-row.assistant { justify-content: flex-start; }
.bubble { max-width: 76%; padding: 10px 14px; border-radius: 12px; background: #f5f7fa; color: #303133; font-size: 14px; line-height: 1.7; }
.bubble-row.user .bubble { background: #409eff; color: #fff; }
.bubble-text { white-space: pre-wrap; word-break: break-word; }
.typing { color: #909399; font-size: 13px; }
.composer { display: flex; gap: 10px; align-items: flex-end; padding-top: 10px; border-top: 1px solid #f0f2f5; }
.composer .el-input { flex: 1; }
.context-bar { display: flex; align-items: center; gap: 8px; padding-top: 10px; flex-wrap: wrap; }
.context-hint { font-size: 11.5px; color: #a0a4ad; }
.context-chips { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; min-width: 0; }
.context-chip {
  display: inline-flex; align-items: center; gap: 5px; max-width: 320px;
  padding: 3px 8px; border-radius: 999px; background: #eef2ff; color: #4338ca;
  font-size: 11.5px;
}
.chip-type { font-weight: 600; flex-shrink: 0; }
.chip-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip-remove {
  border: none; background: transparent; color: #818cf8; cursor: pointer;
  font-size: 14px; line-height: 1; padding: 0 1px;
}
.chip-remove:hover { color: #dc2626; }

.session-search { margin-bottom: 8px; }
.chat-empty p { font-size: 13px; line-height: 1.6; }
.starter-prompts { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 16px; }
.starter-prompts button {
  border: 1px solid #e0e7ff; background: #f5f7ff; color: #4338ca;
  padding: 7px 13px; border-radius: 999px; font-size: 12px; cursor: pointer;
}
.starter-prompts button:hover { background: #eef2ff; border-color: #a5b4fc; }
.message-row { display: flex; gap: 10px; margin-bottom: 20px; align-items: flex-start; }
.message-row.user { flex-direction: row-reverse; }
.msg-avatar {
  width: 30px; height: 30px; border-radius: 9px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
}
.message-row.user .msg-avatar { background: linear-gradient(135deg, #0ea5e9, #2563eb); }
.msg-main { max-width: min(780px, 82%); display: flex; flex-direction: column; min-width: 0; }
.message-row.user .msg-main { align-items: flex-end; }
.bubble {
  max-width: 100%; padding: 11px 15px; border-radius: 4px 14px 14px 14px;
  background: #f7f8fb; border: 1px solid #eef0f4; color: #303133;
  font-size: 13.5px; line-height: 1.7; min-width: 0;
}
.message-row.user .bubble {
  border-radius: 14px 4px 14px 14px; border-color: transparent;
  background: linear-gradient(135deg, #4f46e5, #6366f1); color: #fff;
}
.bubble.streaming { border-color: #c7d2fe; box-shadow: 0 0 0 3px rgba(99, 102, 241, .06); }
.md-body { word-break: break-word; }
.md-body :deep(p) { margin: 0 0 8px; }
.md-body :deep(p:last-child) { margin-bottom: 0; }
.md-body :deep(pre) { margin: 8px 0; padding: 10px 12px; border-radius: 8px; background: #0f172a; color: #e2e8f0; overflow-x: auto; font-size: 12px; }
.md-body :deep(code) { font-family: 'Cascadia Code', Consolas, monospace; font-size: 12px; }
.md-body :deep(:not(pre) > code) { background: #eef2ff; color: #4338ca; padding: 1px 5px; border-radius: 4px; }
.md-body :deep(ul), .md-body :deep(ol) { padding-left: 20px; margin: 6px 0; }
.md-body :deep(a) { color: #4f46e5; }
.run-pill { margin-top: 3px; display: inline-flex; align-items: center; gap: 6px; padding: 3px 9px 3px 7px; border-radius: 999px; background: linear-gradient(90deg,#eef2ff,#f5f3ff,#eef2ff); background-size: 200% 100%; animation: shimmer 2.2s linear infinite; font-size: 11px; color: #4338ca; max-width: 420px; }
.run-pulse { width: 7px; height: 7px; border-radius: 50%; background: #6366f1; box-shadow: 0 0 0 0 rgba(99,102,241,.5); animation: pulse 1.6s infinite; flex-shrink: 0; }
.run-stage-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-time { color: #818cf8; font-variant-numeric: tabular-nums; }
@keyframes shimmer { 0% { background-position: 0 0; } 100% { background-position: 200% 0; } }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(99,102,241,.45); } 70% { box-shadow: 0 0 0 6px rgba(99,102,241,0); } 100% { box-shadow: 0 0 0 0 rgba(99,102,241,0); } }
@keyframes spin { to { transform: rotate(360deg); } }

.approval-strip { display: flex; flex-direction: column; gap: 8px; margin: 4px 0 10px; }
.approval-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid #fde68a; background: linear-gradient(90deg,#fffbeb,#fefce8); border-radius: 12px; }
.approval-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.approval-tool { font-size: 12px; font-weight: 700; color: #92400e; }
.approval-reason { font-size: 11px; color: #a16207; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.approval-actions { display: flex; gap: 6px; flex-shrink: 0; }
.approval-actions button { border: 1px solid transparent; border-radius: 8px; padding: 4px 10px; font-size: 11.5px; cursor: pointer; background: #fff; color: #4b5563; }
.approval-actions .ok { background: #4f46e5; color: #fff; }
.approval-actions .ok.ghost { background: #eef2ff; color: #4338ca; }
.approval-actions .no { background: #fff; color: #dc2626; border-color: #fecaca; }
.approval-actions button:hover { filter: brightness(.96); }

.reasoning-box { margin-bottom: 9px; border: 1px solid #e6e9f5; border-radius: 10px; background: linear-gradient(180deg,#fbfcff,#f7f8ff); overflow: hidden; }
.reasoning-box.open { border-color: #dbe2ff; }
.reasoning-hd { width: 100%; display: flex; align-items: center; gap: 6px; border: none; background: transparent; cursor: pointer; padding: 7px 10px; color: #6b7280; font-size: 11.5px; text-align: left; }
.reasoning-hd:hover { color: #4f46e5; }
.reasoning-hd .chev { font-size: 10px; color: #a5b4fc; }
.reasoning-title { font-weight: 600; }
.reasoning-len { margin-left: auto; color: #a0a6b3; font-size: 10px; }
.reasoning-text { padding: 8px 12px 10px; font-size: 11.5px; line-height: 1.7; color: #6b7280; white-space: pre-wrap; max-height: 220px; overflow: auto; border-top: 1px dashed #e5e9f7; }

.thinking { display: flex; align-items: center; gap: 8px; color: #6b7280; font-size: 12px; padding: 2px 0 4px; }
.typing-dots { display: inline-flex; align-items: center; gap: 3px; }
.typing-dots i { width: 5px; height: 5px; border-radius: 50%; background: #818cf8; animation: blink 1.2s infinite; }
.typing-dots i:nth-child(2) { animation-delay: .2s; }
.typing-dots i:nth-child(3) { animation-delay: .4s; }
.typing-dots.small i { width: 4px; height: 4px; }
.stream-cursor { display: inline-block; width: 6px; height: 14px; margin-left: 2px; vertical-align: -2px; background: #6366f1; border-radius: 2px; animation: blink 1s infinite; }
.error-box { margin-top: 8px; padding: 7px 10px; border-radius: 8px; background: #fef2f2; color: #dc2626; font-size: 11.5px; border: 1px solid #fecaca; }
.assistant-body { position: relative; }
.message-row.live .bubble { border-color: #c7d2fe; box-shadow: 0 0 0 3px rgba(99,102,241,.05); }

.tool-panel { margin-top: 10px; border: 1px solid #e8ebf5; border-radius: 12px; background: #fbfcff; overflow: hidden; transition: border-color .2s, box-shadow .2s; }
.tool-panel.running { border-color: #c7d2fe; box-shadow: 0 0 0 3px rgba(99,102,241,.06); }
.tool-panel.failed { border-color: #fecaca; }
.tool-panel-toggle { width: 100%; border: none; background: transparent; cursor: pointer; display: flex; align-items: center; gap: 8px; padding: 9px 11px; color: #4b5563; font-size: 11.5px; text-align: left; }
.tool-panel-toggle:hover { background: #f5f7ff; }
.tool-spinner { color: #6366f1; font-size: 13px; width: 14px; text-align: center; }
.tool-spinner.spin { animation: spin 1s linear infinite; }
.tool-panel-title { font-weight: 600; color: #374151; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-badge { margin-left: auto; padding: 1px 7px; border-radius: 999px; font-size: 10px; background: #ecfdf5; color: #059669; flex-shrink: 0; }
.tool-badge.running { background: #eef2ff; color: #4f46e5; }
.tool-badge.err { background: #fef2f2; color: #dc2626; }
.tool-chev { color: #a0a6b3; font-size: 14px; transition: transform .2s; }
.tool-chev.open { transform: rotate(90deg); }
.tool-steps { display: flex; flex-direction: column; gap: 7px; padding: 0 9px 9px; }
.tool-step { border: 1px solid #e9edf7; border-radius: 9px; background: #fff; padding: 8px 9px; }
.tool-step.running { border-color: #c7d2fe; background: #fafbff; }
.tool-step.error { border-color: #fecaca; }
.tool-step-head { display: flex; align-items: center; gap: 6px; }
.tool-step-icon { font-size: 12px; color: #6366f1; width: 15px; text-align: center; }
.tool-step-name { font-size: 11.5px; color: #374151; font-family: 'Cascadia Code', Consolas, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-step-duration { margin-left: auto; font-size: 10px; color: #9ca3af; font-variant-numeric: tabular-nums; }
.tool-step-status { padding: 1px 6px; border-radius: 999px; font-size: 10px; background: #ecfdf5; color: #059669; }
.tool-step-status.running { background: #eef2ff; color: #4f46e5; }
.tool-step-status.error { background: #fef2f2; color: #dc2626; }
.tool-sec { margin-top: 7px; }
.tool-sec-hd { display: flex; align-items: center; justify-content: space-between; font-size: 10px; color: #9ca3af; margin-bottom: 3px; }
.tool-sec-hd button { border: none; background: transparent; color: #818cf8; font-size: 10px; cursor: pointer; padding: 0 2px; }
.tool-sec-hd button:hover { color: #4f46e5; }
.tool-pre { margin: 0; padding: 7px 8px; border-radius: 6px; background: #f8fafc; color: #475569; font-size: 10.5px; line-height: 1.5; max-height: 180px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
.tool-pre.err { color: #dc2626; background: #fef2f2; }
.tool-running { display: flex; align-items: center; gap: 6px; margin-top: 6px; font-size: 10.5px; color: #6366f1; }
.msg-elapsed { color: #a5b4fc; }
.msg-meta { display: flex; gap: 10px; align-items: center; margin-top: 5px; font-size: 10.5px; color: #b0b5bd; opacity: .85; }
.msg-meta button { border: none; background: transparent; color: #9ca3af; font-size: 10.5px; cursor: pointer; padding: 1px 4px; border-radius: 4px; }
.msg-meta button:hover { color: #4f46e5; background: #eef2ff; }
.typing { display: flex; align-items: center; gap: 4px; }
.dot { width: 5px; height: 5px; border-radius: 50%; background: #818cf8; animation: blink 1.2s infinite; }
.dot:nth-child(2) { animation-delay: .2s; }
.dot:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%, 80%, 100% { opacity: .25; } 40% { opacity: 1; } }

.chat-layout { grid-template-columns: 252px 1fr; }
.session-pane { border-radius: 16px; background: linear-gradient(180deg, #fff, #fbfcff); box-shadow: 0 8px 24px -20px rgba(30,41,59,.45); }
.session-row { margin-bottom: 2px; transition: background .15s, border-color .15s; border: 1px solid transparent; }
.session-row.active { border-color: #c7d2fe; box-shadow: inset 3px 0 0 #6366f1; }
.session-search :deep(.el-input__wrapper) { border-radius: 9px; background: #f7f9fc; }
.message-pane { border-radius: 18px; background: radial-gradient(900px 400px at 80% -20%, #eef2ff 0, transparent 60%), #fff; box-shadow: 0 12px 34px -28px rgba(30,41,59,.5); }
.chat-toolbar { padding: 2px 2px 12px; }
.current-conv { min-width: 0; }
.current-title { font-size: 14px; font-weight: 700; color: #111827; display: flex; align-items: center; gap: 2px; max-width: 420px; }
.current-title > span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.current-sub { margin-top: 2px; font-size: 11px; color: #9aa3b2; }
.toolbar-spacer { flex: 1; }
.message-body { padding: 22px 12px 8px; }
.message-row { max-width: 920px; margin-left: auto; margin-right: auto; width: 100%; }
.bubble { box-shadow: 0 3px 12px -10px rgba(30,41,59,.28); }
.message-row.assistant .bubble { background: #fff; border-color: #edf0f5; }
.chat-empty { padding-top: 12vh; }
.chat-empty-icon { width: 56px; height: 56px; margin: 0 auto 12px; border-radius: 16px; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg,#eef2ff,#e0f2fe); color: #6366f1; font-size: 26px; }
.composer { position: relative; margin-top: 12px; padding: 10px; border: 1px solid #e8ecf4; border-radius: 16px; background: #fbfcff; box-shadow: 0 8px 24px -22px rgba(30,41,59,.5); }
.composer .el-input { flex: 1; }
.composer :deep(.el-textarea__inner) { border: none; box-shadow: none; background: transparent; padding: 4px 6px; font-size: 13.5px; }
.context-bar { padding-top: 8px; }

.session-row { position: relative; padding-right: 54px; }
.session-actions {
  position: absolute; right: 5px; top: 50%; transform: translateY(-50%);
  display: flex; align-items: center; gap: 2px;
  opacity: 0; transition: opacity .15s;
}
.session-row:hover .session-actions, .session-row.active .session-actions { opacity: 1; }
.session-act, .session-del {
  width: 20px; height: 20px; border: none; border-radius: 6px;
  background: transparent; color: #b0b7c3; font-size: 15px; line-height: 18px;
  cursor: pointer; transition: background .15s, color .15s;
}
.session-act:hover { background: #e0e7ff; color: #4f46e5; }
.session-del:hover { background: #fee2e2; color: #dc2626; }
.session-editing { padding-right: 0; }
.session-editing :deep(.el-input__wrapper) { border-radius: 7px; }
.title-edit {
  border: none; background: transparent; color: #a0a6b3;
  cursor: pointer; font-size: 12px; opacity: 0; transition: opacity .15s, color .15s;
}
.current-title:hover .title-edit { opacity: 1; }
.title-edit:hover { color: #4f46e5; }
.session-row.active .session-title { color: #3730a3; font-weight: 600; }
.message-row { margin-bottom: 26px; }
.bubble { font-size: 13.5px; line-height: 1.8; padding: 12px 16px; }
.message-row.assistant .bubble { background: #fff; border-color: #e8edf5; }
.md-body :deep(h1), .md-body :deep(h2), .md-body :deep(h3), .md-body :deep(h4) { margin: 14px 0 7px; line-height: 1.4; color: #111827; }
.md-body :deep(h1) { font-size: 17px; }
.md-body :deep(h2) { font-size: 15.5px; }
.md-body :deep(h3) { font-size: 14.5px; }
.md-body :deep(blockquote) { margin: 8px 0; padding: 6px 12px; border-left: 3px solid #c7d2fe; color: #6b7280; background: #f8faff; }
.md-body :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 12px; }
.md-body :deep(th), .md-body :deep(td) { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; }
.md-body :deep(th) { background: #f8fafc; }
.md-body :deep(hr) { border: none; border-top: 1px solid #eef0f4; margin: 12px 0; }
.msg-meta { opacity: 0; transition: opacity .15s; }
.message-row:hover .msg-meta { opacity: 1; }
@media (max-width: 900px) {
  .chat-layout { grid-template-columns: 1fr; height: auto; }
  .session-pane { display: none; }
  .message-pane { min-height: calc(100vh - 120px); }
  .msg-main { max-width: 92%; }
}
</style>
