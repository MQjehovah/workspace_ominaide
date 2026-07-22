<script setup lang="ts">
import { ref, onMounted } from 'vue'
const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; close?:()=>void }>()
const msgs = ref<{role:string;text:string}[]>([])
const input = ref('')
const loading = ref(false)
const showSettings = ref(false)
const config = ref({ mode:'backend', apiKey:'', baseUrl:'https://api.openai.com/v1', model:'gpt-4o-mini' })
const cfgMode = ref('backend')
const cfgKey = ref('')
const cfgUrl = ref('https://api.openai.com/v1')
const cfgModel = ref('gpt-4o-mini')

function loadConfig() {
  try { const raw = localStorage.getItem('ai_chat_config'); if (raw) { const c = JSON.parse(raw); config.value = c; cfgMode.value = c.mode; cfgKey.value = c.apiKey; cfgUrl.value = c.baseUrl; cfgModel.value = c.model } } catch {}
}

async function serverUrl(): Promise<string> {
  try { return await (window as any).mqbox?.config?.get('serverUrl') || 'http://localhost:8000' } catch { return 'http://localhost:8000' }
}

async function sendMessage(message: string, history: {role:string;content:string}[]): Promise<string> {
  const cfg = config.value
  if (cfg.mode === 'backend') {
    const tk = (await (window as any).mqbox?.config?.get('token')) || localStorage.getItem('token') || ''
    const su = await serverUrl()
    const r = await fetch(`${su}/api/chat`, { method:'POST', headers:{'Content-Type':'application/json',Authorization:'Bearer '+tk}, body:JSON.stringify({message, history}) }).then(r=>{if(!r.ok)throw new Error(r.statusText);return r.json()})
    return r.reply || '(no response)'
  } else {
    const messages = [...history, {role:'user',content:message}]
    const r = await fetch(`${cfg.baseUrl}/chat/completions`, { method:'POST', headers:{'Content-Type':'application/json',Authorization:'Bearer '+cfg.apiKey}, body:JSON.stringify({model:cfg.model, messages, temperature:0.7}) }).then(r=>{if(!r.ok)throw new Error(r.statusText);return r.json()})
    if (r.error) throw new Error(r.error.message || JSON.stringify(r.error))
    return r.choices?.[0]?.message?.content || '(no response)'
  }
}

async function send() {
  const msg = input.value.trim(); if (!msg || loading.value) return
  msgs.value.push({role:'user',text:msg}); input.value = ''
  loading.value = true
  try {
    const history = msgs.value.slice(0,-1).map(m => ({role:m.role,content:m.text}))
    msgs.value.push({role:'assistant',text:await sendMessage(msg, history)})
  } catch(e:any){ msgs.value.push({role:'assistant',text:'Error: '+(e?.message||e)}) }
  finally { loading.value=false }
}

function applySettings() {
  config.value = { mode: cfgMode.value as 'backend'|'direct', apiKey: cfgKey.value, baseUrl: cfgUrl.value.replace(/\/+$/,''), model: cfgModel.value }
  localStorage.setItem('ai_chat_config', JSON.stringify(config.value))
  showSettings.value = false
}

onMounted(loadConfig)
</script>
<template>
  <div class="chat-page">
    <div class="header">
      <h2>AI 助理</h2>
      <div class="header-actions">
        <button class="gear-btn" @click="showSettings = !showSettings">⚙</button>
        <button class="close" @click="close">×</button>
      </div>
    </div>
    <div v-if="showSettings" class="settings">
      <div class="field"><label>模式</label><select v-model="cfgMode" class="s-input"><option value="backend">后端代理</option><option value="direct">前端直连</option></select></div>
      <div v-if="cfgMode==='direct'">
        <div class="field"><label>API Key</label><input v-model="cfgKey" type="password" class="s-input" placeholder="sk-..." /></div>
        <div class="field"><label>Base URL</label><input v-model="cfgUrl" class="s-input" placeholder="https://api.openai.com/v1" /></div>
        <div class="field"><label>模型</label><input v-model="cfgModel" class="s-input" placeholder="gpt-4o-mini" /></div>
      </div>
      <button class="apply-btn" @click="applySettings">应用</button>
    </div>
    <div class="msgs">
      <div v-for="(m,i) in msgs" :key="i" class="msg" :class="m.role"><div class="bubble">{{ m.text }}</div></div>
      <div v-if="loading" class="msg assistant"><div class="bubble thinking">…</div></div>
      <div v-if="msgs.length===0 && !loading" class="hint">问我任何事</div>
    </div>
    <div class="input-row">
      <input v-model="input" class="input" placeholder="输入消息…" @keyup.enter="send" :disabled="loading" />
      <button class="send-btn" @click="send" :disabled="loading||!input.trim()">{{ loading ? '…' : '发送' }}</button>
    </div>
  </div>
</template>
<style scoped>
.chat-page { height:100vh; display:flex; flex-direction:column; background:#f8f9fa; font-family:-apple-system,sans-serif; }
.header { display:flex; align-items:center; justify-content:space-between; padding:16px 24px; border-bottom:1px solid #e9ecef; }
.header h2 { margin:0; font-size:18px; font-weight:600; }
.header-actions { display:flex; gap:6px; }
.gear-btn { width:32px;height:32px;border:none;border-radius:8px;background:transparent;font-size:16px;cursor:pointer;color:#868e96;display:flex;align-items:center;justify-content:center; }
.gear-btn:hover { background:#f1f3f5;color:#495057; }
.close { width:32px;height:32px;border:none;border-radius:8px;background:transparent;font-size:20px;cursor:pointer;color:#868e96; }
.close:hover { background:#ffebee;color:#e91e63; }
.settings { padding:12px 24px; border-bottom:1px solid #e9ecef; background:#fafafa; }
.field { display:flex;align-items:center;gap:8px;margin-bottom:8px; }
.field label { width:65px;font-size:12px;color:#495057;flex-shrink:0; }
.s-input { flex:1;height:32px;padding:0 8px;border:1px solid #dee2e6;border-radius:6px;font-size:12px;outline:none; }
.apply-btn { height:30px;padding:0 14px;border:none;border-radius:6px;background:#fce4ec;color:#e91e63;font-size:12px;cursor:pointer; }
.apply-btn:hover { background:#f8bbd0; }
.msgs { flex:1; overflow-y:auto; padding:16px 24px; }
.msg { margin-bottom:12px; display:flex; }
.msg.user { justify-content:flex-end; }
.msg.assistant { justify-content:flex-start; }
.bubble { max-width:75%; padding:10px 14px; border-radius:12px; font-size:13px; line-height:1.5; color:#212529; white-space:pre-wrap; word-break:break-word; }
.msg.user .bubble { background:#fce4ec; }
.msg.assistant .bubble { background:#fff; border:1px solid #e9ecef; }
.thinking { color:#adb5bd; }
.hint { text-align:center; color:#adb5bd; font-size:12px; padding:40px 20px; }
.input-row { display:flex; gap:8px; padding:12px 24px; border-top:1px solid #e9ecef; background:#fff; }
.input { flex:1; height:38px; padding:0 12px; border:1px solid #dee2e6; border-radius:8px; font-size:13px; outline:none; }
.input:focus { border-color:#e91e63; }
.send-btn { height:38px; padding:0 20px; border:none; border-radius:8px; background:#fce4ec; color:#e91e63; font-size:12px; font-weight:500; cursor:pointer; }
.send-btn:hover { background:#f8bbd0; }
.send-btn:disabled { opacity:.5; }
</style>
