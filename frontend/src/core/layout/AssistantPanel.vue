<template>
  <div class="assistant-root" :class="{ 'panel-open': open }">
    <div v-if="open" class="assistant-panel">
      <div class="assistant-header">
        <div class="assistant-head-left">
          <span class="assistant-title">AI 助理</span>
          <el-select
            v-if="bots.length"
            v-model="currentBotId"
            size="small"
            class="bot-select"
            placeholder="默认 Bot"
          >
            <el-option
              v-for="b in bots"
              :key="b.id"
              :label="`${b.avatar || '🤖'} ${b.name}`"
              :value="b.id"
            />
          </el-select>
        </div>
        <div class="assistant-head-actions">
          <button class="assistant-icon-btn" title="清空对话" @click="clearHistory">
            <el-icon><Delete /></el-icon>
          </button>
          <button class="assistant-icon-btn" title="关闭" @click="open = false">
            <el-icon><Close /></el-icon>
          </button>
        </div>
      </div>
      <div v-if="approvals.length" class="approval-bar">
        <div v-for="a in approvals" :key="a.id" class="approval-row">
          <span class="approval-text" :title="a.reason || ''">🔐 {{ a.tool_name }}</span>
          <button class="approval-btn ok" @click="decide(a.id, true)">允许</button>
          <button class="approval-btn no" @click="decide(a.id, false)">拒绝</button>
        </div>
      </div>
      <div ref="bodyRef" class="assistant-body">
        <div v-if="messages.length === 0" class="assistant-empty">
          <div class="assistant-empty-icon">✨</div>
          <p>试试问："帮我创建一个明天下午 3 点的日程"</p>
          <p>或"搜索一下关于 AI 的文件"</p>
        </div>
        <div
          v-for="(m, i) in messages"
          :key="i"
          class="msg-row"
          :class="m.role"
        >
          <div class="msg-avatar" v-if="m.role === 'assistant'">🤖</div>
          <div class="msg-bubble">{{ m.content }}</div>
        </div>
        <div v-if="loading" class="msg-row assistant">
          <div class="msg-avatar">🤖</div>
          <div class="msg-bubble typing"><span></span><span></span><span></span></div>
        </div>
      </div>
      <div class="assistant-input-row">
        <el-input
          v-model="input"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 4 }"
          resize="none"
          placeholder="输入指令，Enter 发送，Shift+Enter 换行"
          :disabled="loading"
          @keydown="onInputKeydown"
        />
        <el-button type="primary" class="send-btn" :loading="loading" :icon="Promotion" @click="send" />
      </div>
    </div>
    <button v-show="!open" class="assistant-fab" @click="open = true">
      <el-icon><ChatDotRound /></el-icon>
      <span v-if="approvals.length" class="approval-badge">{{ approvals.length }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { Delete, Close, Promotion, ChatDotRound } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { apiUrl } from '@/api/base'

const open = ref(false)
const loading = ref(false)
const input = ref('')
const messages = ref<{ role: string; content: string }[]>([])
const bodyRef = ref<HTMLDivElement | null>(null)
const bots = ref<{ id: number; name: string; avatar?: string; is_default?: boolean }[]>([])
const currentBotId = ref<number | null>(null)
const BOT_KEY = 'assistant_bot_id'
const approvals = ref<{ id: number; tool_name: string; reason?: string }[]>([])
let approvalTimer: ReturnType<typeof setInterval> | null = null

async function loadApprovals() {
  try {
    const token = localStorage.getItem('token') || ''
    const r = await fetch(apiUrl('/approvals?status=pending'), {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (r.ok) approvals.value = await r.json()
  } catch { /* ignore */ }
}

async function decide(id: number, approved: boolean) {
  try {
    const token = localStorage.getItem('token') || ''
    const r = await fetch(apiUrl(`/approvals/${id}/decision`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ approved }),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => null)
      throw new Error(err?.detail || `审批失败 (${r.status})`)
    }
    await loadApprovals()
  } catch (e: any) {
    ElMessage.error(e.message || '审批失败')
  }
}

async function loadBots() {
  try {
    const token = localStorage.getItem('token') || ''
    const r = await fetch(apiUrl('/bots'), { headers: { Authorization: `Bearer ${token}` } })
    if (!r.ok) return
    bots.value = await r.json()
    const saved = Number(localStorage.getItem(BOT_KEY) || 0)
    const found = bots.value.find(b => b.id === saved)
      || bots.value.find(b => b.is_default)
      || bots.value[0]
    if (found) currentBotId.value = found.id
  } catch { /* ignore */ }
}

watch(currentBotId, (val, old) => {
  if (val) localStorage.setItem(BOT_KEY, String(val))
  if (old != null && val !== old) messages.value = []
})

onMounted(() => {
  loadBots()
  loadApprovals()
  approvalTimer = setInterval(loadApprovals, 10000)
  window.addEventListener('omniaide:approval', loadApprovals)
  window.addEventListener('omniaide:chat-reply', onChatReply)
})

onUnmounted(() => {
  if (approvalTimer) clearInterval(approvalTimer)
  window.removeEventListener('omniaide:approval', loadApprovals)
  window.removeEventListener('omniaide:chat-reply', onChatReply)
})

function onChatReply(event: Event) {
  const data = (event as CustomEvent).detail || {}
  if (!data.content) return
  if (data.bot_id && currentBotId.value && data.bot_id !== currentBotId.value) return
  if (data.session_id && data.session_id !== 'default') return
  messages.value.push({ role: 'assistant', content: data.content })
  scrollBottom()
}

function onInputKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  send()
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: text })
  loading.value = true
  scrollBottom()
  try {
    const token = localStorage.getItem('token') || ''
    const resp = await fetch(apiUrl('/chat/stream'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message: text, bot_id: currentBotId.value || undefined }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => null)
      throw new Error(err?.detail || `请求失败 (${resp.status})`)
    }
    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    let reply = ''
    if (reader) {
      const replyIndex = messages.value.push({ role: 'assistant', content: '' }) - 1
      let buffer = ''
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
              reply += payload.content
              messages.value[replyIndex].content = reply
              scrollBottom()
            } else if (payload.type === 'error') {
              ElMessage.error(payload.content || 'AI 请求出错')
            }
          } catch { /* ignore */ }
        }
      }
      if (!reply) messages.value.splice(replyIndex, 1)
    }
  } catch (e: any) {
    messages.value.pop()
    ElMessage.error(e.message || 'AI 请求失败')
  } finally {
    loading.value = false
    scrollBottom()
  }
}

function clearHistory() {
  messages.value = []
}

function scrollBottom() {
  nextTick(() => {
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  })
}
</script>

<style scoped>
.assistant-root { position: fixed; right: 24px; bottom: 24px; z-index: 2000; }
.assistant-fab {
  width: 54px; height: 54px; border-radius: 50%; border: none; cursor: pointer;
  background: linear-gradient(135deg, #6366f1, #a855f7); color: #fff; font-size: 22px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 20px rgba(99,102,241,0.4); transition: transform .15s, box-shadow .15s;
}
.assistant-fab:hover { transform: scale(1.06); box-shadow: 0 8px 26px rgba(99,102,241,.5); }
.approval-badge {
  position: absolute; top: -4px; right: -4px; min-width: 18px; height: 18px;
  padding: 0 5px; border-radius: 9px; background: #f56c6c; color: #fff;
  font-size: 11px; line-height: 18px; text-align: center; font-weight: 600;
  box-shadow: 0 2px 6px rgba(245,108,108,.5);
}
.assistant-panel {
  position: absolute; right: 0; bottom: 68px; width: 400px; height: 560px;
  background: #fff; border-radius: 16px; border: 1px solid #e6e8ef;
  box-shadow: 0 16px 48px rgba(15, 23, 42, 0.18);
  display: flex; flex-direction: column; overflow: hidden;
}
.assistant-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 14px 12px 16px;
  background: linear-gradient(135deg, #6366f1, #a855f7); color: #fff;
  font-size: 14px; font-weight: 600; flex-shrink: 0;
}
.assistant-title { white-space: nowrap; }
.assistant-head-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.assistant-head-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.bot-select { width: 140px; }
.bot-select :deep(.el-select__wrapper) {
  background: rgba(255,255,255,.2);
  box-shadow: none;
  min-height: 26px;
  border-radius: 8px;
}
.bot-select :deep(.el-select__placeholder) { color: #fff; }
.bot-select :deep(.el-select__caret) { color: #fff; }
.approval-bar {
  padding: 8px 12px; background: #fff7e6; border-bottom: 1px solid #ffe0a3;
  display: flex; flex-direction: column; gap: 6px; flex-shrink: 0;
}
.approval-row { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #8a5a00; }
.approval-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.approval-btn {
  border: 1px solid #e0b25a; background: #fff; color: #8a5a00;
  border-radius: 6px; padding: 3px 9px; cursor: pointer; font-size: 12px;
}
.approval-btn.ok { border-color: #67c23a; color: #3f8f1f; }
.approval-btn.no { border-color: #f56c6c; color: #c45656; }
.assistant-icon-btn {
  border: none; background: rgba(255,255,255,0.16); color: #fff; border-radius: 8px;
  width: 30px; height: 30px; cursor: pointer; display: flex; align-items: center;
  justify-content: center; font-size: 15px; transition: background .15s;
}
.assistant-icon-btn:hover { background: rgba(255,255,255,0.32); }
.assistant-body {
  flex: 1; overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch;
  padding: 16px 14px; display: flex; flex-direction: column; gap: 12px;
  background: linear-gradient(180deg, #fafbff 0%, #f5f7fb 100%);
}
.assistant-empty {
  margin: auto; text-align: center; color: #9aa1ad; font-size: 12px; line-height: 1.8;
  padding: 24px 12px;
}
.assistant-empty-icon { font-size: 30px; margin-bottom: 10px; }
.assistant-empty p { margin: 2px 0; }
.msg-row { display: flex; align-items: flex-end; gap: 6px; animation: bubble-in .18s ease-out; }
.msg-row.user { justify-content: flex-end; }
.msg-row.assistant { justify-content: flex-start; }
.msg-avatar {
  width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: #eef1ff; font-size: 14px;
}
.msg-bubble {
  max-width: min(82%, 520px); padding: 10px 14px; border-radius: 14px;
  font-size: 14px; line-height: 1.65; white-space: pre-wrap; word-break: break-word;
  user-select: text;
}
.msg-row.user .msg-bubble {
  background: linear-gradient(135deg, #6366f1, #7c6cf5); color: #fff;
  border-bottom-right-radius: 4px; box-shadow: 0 3px 10px rgba(99,102,241,.22);
}
.msg-row.assistant .msg-bubble {
  background: #fff; color: #2b3345; border: 1px solid #e9ecf3;
  border-bottom-left-radius: 4px; box-shadow: 0 2px 8px rgba(15,23,42,.05);
}
.typing { display: flex; gap: 5px; align-items: center; padding: 14px 16px; }
.typing span { width: 6px; height: 6px; border-radius: 50%; background: #a0a7b4; animation: blink 1.2s infinite; }
.typing span:nth-child(2) { animation-delay: .2s; }
.typing span:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%,80%,100% { opacity: .3; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-2px); } }
@keyframes bubble-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.assistant-input-row {
  display: flex; align-items: flex-end; gap: 8px; padding: 10px 12px 12px;
  border-top: 1px solid #eef0f5; background: #fff; flex-shrink: 0;
}
.assistant-input-row :deep(.el-textarea__inner) {
  border-radius: 12px; border-color: #e3e6ee; box-shadow: none;
  padding: 9px 12px; font-size: 14px; line-height: 1.5;
  resize: none; transition: border-color .15s, box-shadow .15s;
}
.assistant-input-row :deep(.el-textarea__inner:focus) {
  border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99,102,241,.12);
}
.send-btn { width: 42px; height: 40px; border-radius: 11px; flex-shrink: 0; }
@media (max-width: 768px) {
  .assistant-root { right: 14px; bottom: calc(14px + env(safe-area-inset-bottom)); }
  .assistant-panel {
    position: fixed; inset: 0; width: 100%; height: 100vh; max-height: 100vh;
    height: 100dvh; max-height: 100dvh;
    border-radius: 0; border: none; bottom: 0;
  }
  .assistant-header {
    padding: calc(10px + env(safe-area-inset-top)) 12px 10px;
  }
  .assistant-head-left { gap: 6px; }
  .assistant-title { font-size: 15px; }
  .bot-select { width: 104px; }
  .assistant-icon-btn { width: 34px; height: 34px; }

  .assistant-body {
    padding: 12px 10px;
    gap: 10px;
  }
  .msg-avatar { width: 24px; height: 24px; font-size: 13px; }
  .msg-bubble {
    max-width: 82%; padding: 10px 13px; font-size: 15px; line-height: 1.65;
  }
  .assistant-input-row {
    padding: 8px 10px calc(8px + env(safe-area-inset-bottom));
    gap: 6px;
  }
  .assistant-input-row :deep(.el-textarea__inner) {
    font-size: 16px; padding: 9px 11px; min-height: 40px !important;
  }
  .send-btn { width: 44px; height: 42px; }
  .approval-bar { padding: 7px 10px; }
}
</style>
