<script setup lang="ts">
import { ref } from 'vue'
import { loadConfig, sendMessage } from './chat'
defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()
const input = ref('')
const loading = ref(false)
const reply = ref('')
async function send() {
  const msg = input.value.trim(); if (!msg || loading.value) return
  loading.value = true; reply.value = ''
  try {
    reply.value = await sendMessage(msg, [], loadConfig())
  } catch (e: any) { reply.value = 'Error: ' + (e?.message || e) }
  finally { input.value = ''; loading.value = false }
}
</script>
<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">AI 对话</span><button class="panel-arrow" @click="openPage">›</button></div>
    <div v-if="reply" class="reply">{{ reply.slice(0, 200) }}{{ reply.length > 200 ? '...' : '' }}</div>
    <div class="row"><input v-model="input" class="input" placeholder="问 AI…" @keyup.enter="send" /><button class="btn" @click="send" :disabled="loading">{{ loading ? '…' : '>' }}</button></div>
  </div>
</template>
<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
.title { font-size:13px; font-weight:600; }
.panel-arrow { width:24px;height:24px;border:none;border-radius:6px;background:transparent;color:#ccc;cursor:pointer;font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center; }
.panel-arrow:hover { background:#f5f5f5;color:#666; }
.reply { font-size:11px; color:#495057; margin-bottom:8px; padding:8px; background:#f8f9fa; border-radius:6px; line-height:1.4; max-height:100px; overflow-y:auto; }
.row { display:flex; gap:6px; }
.input { flex:1; height:30px; padding:0 8px; border:1px solid #dee2e6; border-radius:6px; font-size:12px; outline:none; }
.input:focus { border-color:#e91e63; }
.btn { width:36px;height:30px;border:none;border-radius:6px;background:#fce4ec;color:#e91e63;font-size:14px;cursor:pointer;flex-shrink:0; }
.btn:hover { background:#f8bbd0; }
.btn:disabled { opacity:.5; }
</style>
