<script setup lang="ts">
import { ref } from 'vue'
const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; close?:()=>void }>()
const msgs = ref<{role:string;text:string}[]>([])
const input = ref('')
const loading = ref(false)

async function send() {
  const msg = input.value.trim(); if (!msg || loading.value) return
  msgs.value.push({role:'user',text:msg}); input.value = ''
  loading.value = true
  try {
    const w = window as any
    const su = (await w.mqbox?.config?.get('serverUrl')) || 'http://localhost:8000'
    const tk = (await w.mqbox?.config?.get('token')) || ''
    const history = msgs.value.slice(0,-1).map(m => ({role:m.role,content:m.text}))
    const r = await fetch(`${su}/api/chat`, {
      method:'POST',
      headers:{'Content-Type':'application/json',Authorization:'Bearer '+tk},
      body:JSON.stringify({message:msg, history}),
    }).then(r=>{if(!r.ok)throw new Error(r.statusText);return r.json()})
    msgs.value.push({role:'assistant',text:r.reply||'(no response)'})
  } catch(e:any){ msgs.value.push({role:'assistant',text:'Error: '+(e?.message||e)}) }
  finally { loading.value=false }
}
</script>
<template>
  <div class="chat-page">
    <div class="header">
      <h2>AI 助理</h2>
      <button class="close" @click="close">×</button>
    </div>
    <div class="msgs">
      <div v-for="(m,i) in msgs" :key="i" class="msg" :class="m.role">
        <div class="bubble">{{ m.text }}</div>
      </div>
      <div v-if="loading" class="msg assistant"><div class="bubble thinking">…</div></div>
      <div v-if="msgs.length===0 && !loading" class="hint">问我任何事，或试试「明天下午3点开会」「打开日程」「搜索预算表」</div>
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
.close { width:32px;height:32px;border:none;border-radius:8px;background:transparent;font-size:20px;cursor:pointer;color:#868e96; }
.close:hover { background:#ffebee;color:#e91e63; }
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
