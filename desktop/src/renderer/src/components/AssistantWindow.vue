<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'

const msgs = ref<{role:string;text:string}[]>([])
const input = ref('')
const loading = ref(false)
const msgsRef = ref<HTMLDivElement|null>(null)
const showSettings = ref(false)
const config = ref({ mode:'backend', apiKey:'', baseUrl:'https://api.openai.com/v1', model:'gpt-4o-mini' })
const cfgMode = ref('backend')
const cfgKey = ref('')
const cfgUrl = ref('https://api.openai.com/v1')
const cfgModel = ref('gpt-4o-mini')

function loadConfig() {
  try {
    const raw = localStorage.getItem('ai_chat_config')
    if (raw) { const c = JSON.parse(raw); config.value = c; cfgMode.value = c.mode; cfgKey.value = c.apiKey; cfgUrl.value = c.baseUrl; cfgModel.value = c.model }
  } catch {}
}

async function sendMessage(message: string, history: {role:string;content:string}[]): Promise<string> {
  const cfg = config.value
  if (cfg.mode === 'backend') {
    const tk = localStorage.getItem('token') || ''
    const r = await fetch('/api/chat', {
      method:'POST', headers:{'Content-Type':'application/json',Authorization:'Bearer '+tk},
      body: JSON.stringify({message, history}),
    }).then(r=>{if(!r.ok)throw new Error(r.statusText);return r.json()})
    return r.reply || '(no response)'
  } else {
    const messages = [...history, {role:'user',content:message}]
    const r = await fetch(`${cfg.baseUrl}/chat/completions`, {
      method:'POST', headers:{'Content-Type':'application/json',Authorization:'Bearer '+cfg.apiKey},
      body: JSON.stringify({model:cfg.model, messages, temperature:0.7}),
    }).then(r=>{if(!r.ok)throw new Error(r.statusText);return r.json()})
    if (r.error) throw new Error(r.error.message || JSON.stringify(r.error))
    return r.choices?.[0]?.message?.content || '(no response)'
  }
}

async function send() {
  const msg = input.value.trim(); if (!msg || loading.value) return
  msgs.value.push({role:'user',text:msg}); input.value = ''
  loading.value = true
  const actionResult = await executeAction(msg)
  if (actionResult) { msgs.value.push({role:'assistant',text:actionResult}); loading.value = false; return }
  try {
    const history = msgs.value.slice(0,-1).map(m => ({role:m.role,content:m.text}))
    const reply = await sendMessage(msg, history)
    msgs.value.push({role:'assistant',text:reply})
  } catch(e:any){ msgs.value.push({role:'assistant',text:'Error: '+(e?.message||e)}) }
  finally { loading.value=false; nextTick(()=>scroll()) }
}

function applySettings() {
  config.value = { mode: cfgMode.value as 'backend'|'direct', apiKey: cfgKey.value, baseUrl: cfgUrl.value.replace(/\/+$/,''), model: cfgModel.value }
  localStorage.setItem('ai_chat_config', JSON.stringify(config.value))
  showSettings.value = false
}

onMounted(loadConfig)

async function executeAction(text: string): Promise<string | null> {
  const t = text.trim()
  const tk = localStorage.getItem('token') || ''
  const auth = { 'Content-Type':'application/json', Authorization:'Bearer '+tk }
  // Open page: "打开日程" "打开设置" "打开文件管理"
  const openMatch = t.match(/^打开(.+)/)
  if (openMatch) {
    const pageMap: Record<string,string> = { '日程':'schedule','设置':'settings','文件':'files','文件管理':'files','笔记':'notes','工作区':'workspaces','用户':'admin/users','插件':'admin/plugins','资讯':'rss' }
    const key = openMatch[1].trim()
    if (pageMap[key]) { return `正在打开 ${key}…` }
  }
  // Search: "搜索xxx" "查找xxx"
  const searchMatch = t.match(/^(搜索|查找|找一下|search)\s+(.+)/i)
  if (searchMatch) {
    const query = searchMatch[2].trim()
    try {
      const r = await fetch(`/api/rss/search?q=${encodeURIComponent(query)}&page_size=3`, { headers: auth }).then(r=>r.ok?r.json():null)
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
      <div>
        <button class="title-btn" @click="showSettings = !showSettings">⚙</button>
        <button class="title-btn" @click="hideWindow">_</button>
      </div>
    </div>
    <!-- Settings panel -->
    <div v-if="showSettings" class="settings">
      <div class="field"><label>模式</label><select v-model="cfgMode" class="s-input"><option value="backend">后端代理</option><option value="direct">前端直连</option></select></div>
      <div v-if="cfgMode==='direct'">
        <div class="field"><label>API Key</label><input v-model="cfgKey" type="password" class="s-input" placeholder="sk-..." /></div>
        <div class="field"><label>Base URL</label><input v-model="cfgUrl" class="s-input" placeholder="https://api.openai.com/v1" /></div>
        <div class="field"><label>模型</label><input v-model="cfgModel" class="s-input" placeholder="gpt-4o-mini" /></div>
      </div>
      <button class="apply-btn" @click="applySettings">应用</button>
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
.settings { padding:10px 12px; border-bottom:1px solid #e9ecef; background:#fafafa; }
.field { display:flex;align-items:center;gap:6px;margin-bottom:6px; }
.field label { width:60px;font-size:11px;color:#666;flex-shrink:0; }
.s-input { flex:1;height:28px;padding:0 8px;border:1px solid #dee2e6;border-radius:5px;font-size:12px;outline:none; }
.apply-btn { height:28px;padding:0 12px;border:none;border-radius:5px;background:#fce4ec;color:#e91e63;font-size:11px;cursor:pointer; }
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
