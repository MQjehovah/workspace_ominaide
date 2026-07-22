<script setup lang="ts">
import { ref, nextTick } from 'vue'

const msgs = ref<{role:string;text:string}[]>([])
const input = ref('')
const loading = ref(false)
const msgsRef = ref<HTMLDivElement|null>(null)

async function send() {
  const msg = input.value.trim(); if (!msg || loading.value) return
  msgs.value.push({role:'user',text:msg}); input.value = ''
  loading.value = true
  // Try natural language action first
  const actionResult = await executeAction(msg)
  if (actionResult) {
    msgs.value.push({role:'assistant',text:actionResult})
    loading.value = false; return
  }
  try {
    const w = window as any
    const su = (await w.mqbox?.config?.get('serverUrl')) || 'http://localhost:8000'
    const tk = (await w.mqbox?.config?.get('token')) || ''
    const history = msgs.value.slice(0,-1).map(m => ({role:m.role,content:m.text}))
    const r = await fetch(`${su}/api/chat`, {
      method:'POST', headers:{'Content-Type':'application/json',Authorization:'Bearer '+tk},
      body: JSON.stringify({message:msg, history}),
    }).then(r=>r.ok?r.json():Promise.reject())
    msgs.value.push({role:'assistant',text:r.reply||'(no response)'})
  } catch(e:any){ msgs.value.push({role:'assistant',text:'Error: '+(e?.message||e)}) }
  finally { loading.value=false; nextTick(()=>scroll()) }
}

async function executeAction(text: string): Promise<string | null> {
  const api = (window as any).mqbox?.api; if (!api) return null
  const t = text.trim()
  // Create event: "明天下午3点开会" or "添加日程 标题 时间"
  const createMatch = t.match(/^(添加日程|创建日程|安排|Add event|create event)\s+(.+)/i) || t.match(/^(明天|今天|后天|周[一二三四五六日]|\d{1,2}月\d{1,2}日).+?(\d{1,2}[点时]).+/)
  if (createMatch) {
    try {
      // For simplicity, use AI to parse — but we can do basic date extraction
      // Quick parse: if contains time keywords, just ask AI via chat
      return null // Let AI handle via normal chat
    } catch { return null }
  }
  // Open page: "打开日程" "打开设置" "打开文件管理"
  const openMatch = t.match(/^打开(.+)/)
  if (openMatch) {
    const pageMap: Record<string,string> = { '日程':'schedule','设置':'settings','文件':'files','文件管理':'files','笔记':'notes','工作区':'workspaces','用户':'admin/users','插件':'admin/plugins','资讯':'rss' }
    const key = openMatch[1].trim()
    if (pageMap[key]) {
      const w = window as any
      w.mqbox?.window?.openPage?.('remote') // fallback — openPage only works for plugin pages
      // For web pages, use window.open
      // Since we're in electron renderer, we can use ipc
      return `正在打开 ${key}…（桌面端页面导航需后续实现）`
    }
  }
  // Search: "搜索xxx" "查找xxx"
  const searchMatch = t.match(/^(搜索|查找|找一下|search)\s+(.+)/i)
  if (searchMatch) {
    const query = searchMatch[2].trim()
    try {
      const r = await api.get(`/rss/search?q=${encodeURIComponent(query)}&page_size=3`)
      const items = r?.items || []
      if (items.length > 0) {
        return `找到 ${items.length} 条相关结果：\n${items.slice(0,3).map((i:any) => `• ${i.title}`).join('\n')}`
      }
    } catch {}
    return `未搜索到 "${query}" 相关内容`
  }
  return null // fall through to AI chat
}

function scroll() { nextTick(()=>{ const el = msgsRef.value; if (el) el.scrollTop = el.scrollHeight }) }

let recognition: any = null
const listening = ref(false)
function toggleVoice() {
  const w = window as any
  const SR = w.SpeechRecognition || w.webkitSpeechRecognition
  if (!SR) return
  if (listening.value) { recognition?.stop(); listening.value = false; return }
  recognition = new SR()
  recognition.lang = 'zh-CN'; recognition.interimResults = false
  recognition.onresult = (e: any) => { input.value += e.results[0][0].transcript; listening.value = false }
  recognition.onerror = () => { listening.value = false }
  recognition.start(); listening.value = true
}

const hideWindow = () => window.close()
</script>
<template>
  <div class="assistant">
    <div class="title-bar">
      <span class="title-text">AI 助理</span>
      <button class="title-btn" @click="hideWindow">_</button>
    </div>
    <div class="msgs" ref="msgsRef">
      <div v-for="(m,i) in msgs" :key="i" class="msg" :class="m.role">
        <div class="bubble">{{ m.text }}</div>
      </div>
      <div v-if="loading" class="msg assistant"><div class="bubble thinking">…</div></div>
      <div v-if="msgs.length===0 && !loading" class="msg hint">问我任何事，或试试「明天下午3点开会」「打开日程」「搜索预算表」</div>
    </div>
    <div class="input-row">
      <button class="voice-btn" :class="{ active: listening }" @click="toggleVoice">🎤</button>
      <input v-model="input" class="input" placeholder="输入消息…" @keyup.enter="send" :disabled="loading" />
      <button class="send-btn" @click="send" :disabled="loading||!input.trim()">{{ loading ? '…' : '>' }}</button>
    </div>
  </div>
</template>
<style scoped>
.assistant { height:100vh; display:flex; flex-direction:column; background:#fff; font-family:-apple-system,sans-serif; }
.title-bar { display:flex; align-items:center; justify-content:space-between; padding:8px 12px; background:#1a1a2e; color:#fff; cursor:move; -webkit-app-region:drag; user-select:none; }
.title-text { font-size:13px; font-weight:600; }
.title-btn { width:20px;height:20px;border:none;border-radius:4px;background:transparent;color:rgba(255,255,255,.6);cursor:pointer;font-size:14px;line-height:1;display:flex;align-items:center;justify-content:center; }
.title-btn:hover { background:rgba(255,255,255,.1); }
.msgs { flex:1; overflow-y:auto; padding:12px; }
.msg { margin-bottom:10px; }
.msg.user { text-align:right; }
.msg.assistant .bubble { background:#f1f3f5; border-radius:12px 12px 12px 4px; display:inline-block; text-align:left; }
.msg.user .bubble { background:#fce4ec; border-radius:12px 12px 4px 12px; display:inline-block; text-align:left; }
.bubble { max-width:85%; padding:8px 12px; font-size:13px; line-height:1.5; color:#333; white-space:pre-wrap; word-break:break-word; }
.thinking { color:#adb5bd; }
.hint { text-align:center; color:#adb5bd; font-size:12px; padding:20px; }
.input-row { display:flex; gap:6px; padding:8px 12px; border-top:1px solid #e9ecef; background:#fff; }
.voice-btn { width:32px;height:32px;border:none;border-radius:8px;background:transparent;cursor:pointer;font-size:16px;flex-shrink:0;display:flex;align-items:center;justify-content:center; }
.voice-btn.active { background:#fce4ec; }
.voice-btn:hover { background:#f1f3f5; }
.input { flex:1; height:32px; padding:0 10px; border:1px solid #dee2e6; border-radius:8px; font-size:13px; outline:none; }
.input:focus { border-color:#e91e63; }
.send-btn { width:32px;height:32px;border:none;border-radius:8px;background:#fce4ec;color:#e91e63;cursor:pointer;font-size:16px;flex-shrink:0;display:flex;align-items:center;justify-content:center; }
.send-btn:hover { background:#f8bbd0; }
.send-btn:disabled { opacity:.5; }
</style>
