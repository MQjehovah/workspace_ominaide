<template>
  <div class="page-wrapper chat-page">
    <div class="chat-layout">
      <aside class="session-pane page-card">
        <div class="session-head">
          <span class="pane-title">会话</span>
          <el-button size="small" type="primary" @click="newSession">新对话</el-button>
        </div>
        <div
          v-for="s in sessions"
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
          <el-select v-model="botId" size="small" clearable placeholder="默认助手" style="width:180px">
            <el-option v-for="b in bots" :key="b.id" :label="b.name" :value="b.id" />
          </el-select>
          <span class="session-hint">{{ botId ? '使用所选助手' : '默认助手' }}</span>
        </div>

        <div ref="bodyRef" class="message-body">
          <div v-if="messages.length === 0" class="chat-empty">
            <div class="chat-empty-icon">✦</div>
            <p>问点什么，或让助手帮你查日程、待办、邮件和笔记。</p>
          </div>
          <div
            v-for="(m, i) in messages"
            :key="i"
            class="bubble-row"
            :class="m.role"
          >
            <div class="bubble">
              <div v-if="m.role === 'assistant' && !m.content && loading" class="typing">正在思考…</div>
              <div v-else class="bubble-text">{{ m.content }}</div>
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
import { nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import client from '@/api/client'
import { apiUrl } from '@/api/base'
import { formatBackendDate } from '@/utils/date'
import ObjectPicker from '@/components/ObjectPicker.vue'

const route = useRoute()
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

const typeLabels: Record<string, string> = {
  schedule_event: '日程',
  mail_message: '邮件',
  rss_entry: '资讯',
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
    ['rss_entry', route.query.entry],
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
      .map((m: any) => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }))
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
  messages.value.push({ role: 'user', content: text })
  const replyIndex = messages.value.push({ role: 'assistant', content: '' }) - 1
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
            } else if (payload.type === 'done') {
              messages.value[replyIndex].content = payload.reply || reply || '（无回复）'
              if (payload.error) ElMessage.error(payload.error)
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
    await loadSessions()
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
</style>
