<template>
  <div class="assistant-root">
    <div v-if="open" class="assistant-panel">
      <div class="assistant-header">
        <span>AI 助理</span>
        <div style="display:flex;gap:4px">
          <button class="assistant-icon-btn" title="清空对话" @click="clearHistory">
            <el-icon><Delete /></el-icon>
          </button>
          <button class="assistant-icon-btn" title="关闭" @click="open = false">
            <el-icon><Close /></el-icon>
          </button>
        </div>
      </div>
      <div ref="bodyRef" class="assistant-body">
        <div v-if="messages.length === 0" style="text-align:center;color:#909399;font-size:12px;padding:30px 10px">
          试试问："帮我创建一个明天下午 3 点的日程"<br/>或"搜索一下关于 AI 的文件"
        </div>
        <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
          <div class="msg-bubble">{{ m.content }}</div>
        </div>
        <div v-if="loading" class="msg-row assistant">
          <div class="msg-bubble typing"><span></span><span></span><span></span></div>
        </div>
      </div>
      <div class="assistant-input-row">
        <el-input
          v-model="input"
          placeholder="输入指令，Enter 发送 (支持自然语言创建日程/搜索)"
          :disabled="loading"
          @keyup.enter="send"
        />
        <el-button type="primary" :loading="loading" :icon="Promotion" @click="send" />
      </div>
    </div>
    <button class="assistant-fab" @click="open = !open">
      <el-icon><ChatDotRound /></el-icon>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { Delete, Close, Promotion, ChatDotRound } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const open = ref(false)
const loading = ref(false)
const input = ref('')
const messages = ref<{ role: string; content: string }[]>([])
const bodyRef = ref<HTMLDivElement | null>(null)

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: text })
  loading.value = true
  scrollBottom()
  try {
    const token = localStorage.getItem('token') || ''
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message: text }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => null)
      throw new Error(err?.detail || `请求失败 (${resp.status})`)
    }
    const reader = resp.body?.getReader()
    const decoder = new TextDecoder()
    let reply = ''
    if (reader) {
      messages.value.push({ role: 'assistant', content: '' })
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        const events = chunk.split('\n\n').filter(Boolean)
        for (const ev of events) {
          if (!ev.startsWith('data: ')) continue
          try {
            const payload = JSON.parse(ev.slice(6))
            if (payload.type === 'token') {
              reply += payload.content
              messages.value[messages.value.length - 1].content = reply
              scrollBottom()
            } else if (payload.type === 'error') {
              ElMessage.error(payload.content || 'AI 请求出错')
            }
          } catch { /* ignore */ }
        }
      }
      if (!reply) messages.value.pop()
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
  width: 52px; height: 52px; border-radius: 50%; border: none; cursor: pointer;
  background: linear-gradient(135deg, #6366f1, #a855f7); color: #fff; font-size: 22px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 20px rgba(99,102,241,0.4); transition: transform .15s;
}
.assistant-fab:hover { transform: scale(1.06); }
.assistant-panel {
  position: absolute; right: 0; bottom: 64px; width: 380px; height: 520px;
  background: #fff; border-radius: 14px; border: 1px solid #e0e0e0;
  box-shadow: 0 12px 40px rgba(0,0,0,0.18); display: flex; flex-direction: column; overflow: hidden;
}
.assistant-header {
  display: flex; justify-content: space-between; align-items: center; padding: 12px 16px;
  background: linear-gradient(135deg, #6366f1, #a855f7); color: #fff; font-size: 14px; font-weight: 600;
}
.assistant-icon-btn { border: none; background: rgba(255,255,255,0.15); color: #fff; border-radius: 6px; width: 26px; height: 26px; cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 14px; }
.assistant-icon-btn:hover { background: rgba(255,255,255,0.3); }
.assistant-body { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.msg-row { display: flex; }
.msg-row.user { justify-content: flex-end; }
.msg-row.assistant { justify-content: flex-start; }
.msg-bubble { max-width: 85%; padding: 9px 13px; border-radius: 10px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.msg-row.user .msg-bubble { background: #6366f1; color: #fff; border-bottom-right-radius: 2px; }
.msg-row.assistant .msg-bubble { background: #f3f4f6; color: #333; border-bottom-left-radius: 2px; }
.typing { display: flex; gap: 4px; align-items: center; padding: 12px 14px; }
.typing span { width: 6px; height: 6px; border-radius: 50%; background: #909399; animation: blink 1.2s infinite; }
.typing span:nth-child(2) { animation-delay: .2s; }
.typing span:nth-child(3) { animation-delay: .4s; }
@keyframes blink { 0%,80%,100% { opacity: .3; } 40% { opacity: 1; } }
.assistant-input-row { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #f0f0f0; }
</style>
