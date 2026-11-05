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
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '@/api/client'
import { apiUrl } from '@/api/base'
import { formatBackendDate } from '@/utils/date'

const sessions = ref<any[]>([])
const bots = ref<any[]>([])
const messages = ref<any[]>([])
const sessionId = ref<string>(newSessionId())
const botId = ref<number | null>(null)
const input = ref('')
const loading = ref(false)
const bodyRef = ref<HTMLElement | null>(null)

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
.composer { display: flex; gap: 10px; align-items: flex-end; padding-top: 12px; border-top: 1px solid #f0f2f5; }
.composer .el-input { flex: 1; }
</style>
