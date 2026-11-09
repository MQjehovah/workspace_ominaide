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
        >
          <div class="session-main">
            <div class="session-title">{{ s.title || '未命名对话' }}</div>
            <div class="session-time">{{ formatTime(s.updated_at) }}</div>
          </div>
          <el-button link size="small" @click.stop="removeSession(s.session_id)">删</el-button>
        </div>
        <div v-if="sessions.length === 0" class="pane-empty">还没有会话</div>
      </aside>

      <section class="message-pane page-card">
        <div class="chat-toolbar">
          <div class="current-conv">
            <div class="current-title">{{ currentTitle }}</div>
            <div class="current-sub">{{ messages.length }} 条消息 · {{ botName }}</div>
          </div>
          <div class="toolbar-spacer"></div>
          <el-select v-model="botId" size="small" clearable placeholder="默认助手" style="width:180px">
            <el-option v-for="b in bots" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
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
            :class="m.role"
          >
            <div class="msg-avatar">{{ m.role === 'user' ? '我' : '✦' }}</div>
            <div class="msg-main">
              <div class="bubble" :class="{ streaming: loading && i === messages.length - 1 && m.role === 'assistant' }">
                <div v-if="m.role === 'assistant' && !m.content && loading" class="typing">
                  <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                  正在思考…
                </div>
                <template v-else>
                  <details v-if="m.reasoning" class="reasoning-box">
                    <summary>思考过程</summary>
                    <div class="reasoning-text">{{ m.reasoning }}</div>
                  </details>
                  <div v-if="m.role === 'assistant'" class="md-body" v-html="renderMarkdown(m.content)"></div>
                  <div v-else class="bubble-text">{{ m.content }}</div>
                  <div v-if="m.steps?.length" class="tool-panel">
                    <button type="button" class="tool-panel-toggle" @click="m.stepsOpen = !m.stepsOpen">
                      ⚙ {{ m.steps.length }} 个工具调用
                      <span>{{ m.stepsOpen ? '收起' : '展开' }}</span>
                    </button>
                    <div v-if="m.stepsOpen" class="tool-steps">
                      <div v-for="(step, si) in m.steps" :key="si" class="tool-step">
                        <div class="tool-step-name">
                          <span>{{ step.status === 'running' ? '◌' : step.status === 'error' ? '×' : '✓' }}</span>
                          {{ step.name }}
                        </div>
                        <pre v-if="step.args" class="tool-pre">{{ step.args }}</pre>
                        <pre v-if="step.result" class="tool-pre" :class="{ err: step.status === 'error' }">{{ step.result }}</pre>
                      </div>
                    </div>
                  </div>
                </template>
              </div>
              <div class="msg-meta">
                <span>{{ m.role === 'user' ? '你' : 'AI 助手' }} · {{ formatTime(m.createdAt) }}</span>
                <button v-if="m.content" type="button" @click="copyMessage(m)">复制</button>
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
          <el-button type="primary" :loading="loading" :disabled="!input.trim()" @click="send">发送</el-button>
        </div>
      </section>
    </div>

    <ObjectPicker v-model="pickerVisible" @select="addContextRef" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
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
const sessions = ref<any[]>([])
const bots = ref<any[]>([])
const messages = ref<any[]>([])
const sessionId = ref<string>(newSessionId())
const botId = ref<number | null>(null)
const input = ref('')
const loading = ref(false)
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
    messages.value = (data || [])
      .filter((m: any) => m.content)
      .map((m: any, index: number) => ({
        id: `history-${index}-${m.created_at || ''}`,
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content,
        steps: [] as any[],
        stepsOpen: false,
        reasoning: '',
        createdAt: m.created_at || '',
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
  await client.delete(`/chat/sessions/${id}`)
  if (sessionId.value === id) newSession()
  await loadSessions()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  send()
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  input.value = ''
  const now = new Date().toISOString()
  messages.value.push({
    id: `u-${Date.now()}`,
    role: 'user',
    content: text,
    steps: [],
    stepsOpen: false,
    reasoning: '',
    createdAt: now,
  })
  const replyIndex = messages.value.push({
    id: `a-${Date.now()}`,
    role: 'assistant',
    content: '',
    steps: [],
    stepsOpen: false,
    reasoning: '',
    createdAt: now,
  }) - 1
  loading.value = true
  scrollBottom()

  try {
    const token = localStorage.getItem('token') || ''
    const resp = await fetch(apiUrl('/chat/runs'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        message: text,
        session_id: sessionId.value,
        bot_id: botId.value || undefined,
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
    const streamResp = await fetch(apiUrl(`/runs/${run.run_id}/stream`), {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!streamResp.ok) throw new Error(`读取结果失败 (${streamResp.status})`)

    const reader = streamResp.body?.getReader()
    const decoder = new TextDecoder()
    let reply = ''
    let buffer = ''
    if (reader) {
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
            if (payload.type === 'token') {
              reply += payload.content || ''
              messages.value[replyIndex].content = reply
              scrollBottom()
            } else if (payload.type === 'reasoning') {
              messages.value[replyIndex].reasoning += payload.content || ''
            } else if (payload.type === 'tool_call') {
              messages.value[replyIndex].steps.push({
                name: payload.name || 'tool',
                args: payload.arguments ? JSON.stringify(payload.arguments, null, 2) : '',
                result: '',
                status: 'running',
              })
            } else if (payload.type === 'tool_result') {
              const steps = messages.value[replyIndex].steps
              for (let si = steps.length - 1; si >= 0; si -= 1) {
                if (steps[si].status === 'running') {
                  steps[si].status = payload.error ? 'error' : 'done'
                  steps[si].result = String(payload.content || '').slice(0, 4000)
                  break
                }
              }
            } else if (payload.type === 'done') {
              messages.value[replyIndex].content = payload.reply || reply || '（无回复）'
              if (payload.error) ElMessage.error(payload.error)
              await loadSessions()
            } else if (payload.type === 'approval_required') {
              ElMessage.warning(`需要确认：${payload.tool || '工具调用'}`)
            } else if (payload.type === 'error') {
              ElMessage.error(payload.content || 'AI 请求出错')
            }
          } catch { /* ignore */ }
        }
      }
    }
    if (!messages.value[replyIndex].content) messages.value[replyIndex].content = '（无回复）'
  } catch (e: any) {
    messages.value[replyIndex].content = `⚠️ ${e.message || '发送失败'}`
  } finally {
    loading.value = false
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
  await Promise.all([loadSessions(), loadBots()])
  await loadHistory()
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
.reasoning-box { margin-bottom: 8px; border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; overflow: hidden; }
.reasoning-box summary { cursor: pointer; padding: 6px 10px; font-size: 11.5px; color: #6b7280; background: #fafafa; }
.reasoning-text { padding: 8px 10px; font-size: 11.5px; line-height: 1.6; color: #6b7280; white-space: pre-wrap; max-height: 180px; overflow: auto; }
.tool-panel { margin-top: 9px; border-top: 1px solid #eef0f4; padding-top: 7px; }
.tool-panel-toggle {
  width: 100%; border: none; background: transparent; color: #6b7280;
  font-size: 11.5px; cursor: pointer; display: flex; justify-content: space-between; padding: 2px 0;
}
.tool-panel-toggle:hover { color: #4f46e5; }
.tool-steps { display: flex; flex-direction: column; gap: 6px; margin-top: 5px; }
.tool-step { border: 1px solid #f0f2f5; border-radius: 7px; padding: 6px 8px; background: #fff; }
.tool-step-name { display: flex; gap: 6px; align-items: center; font-size: 11.5px; color: #4b5563; font-family: 'Cascadia Code', Consolas, monospace; }
.tool-pre { margin: 4px 0 0; padding: 7px 8px; border-radius: 5px; background: #f8fafc; color: #475569; font-size: 10.5px; line-height: 1.5; max-height: 140px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
.tool-pre.err { color: #dc2626; background: #fef2f2; }
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
.current-title { font-size: 14px; font-weight: 700; color: #111827; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 420px; }
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
</style>
