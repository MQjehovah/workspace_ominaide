<script setup lang="ts">
import { ref, onMounted } from 'vue'
const props = defineProps<{ data?:any; execute?:(a:string,args?:any)=>Promise<any>; close?:()=>void }>()
const api = (window as any).mqbox?.api
const notifications = ref<any[]>([]); const loading = ref(true)
async function load() {
  try { const r = await api?.get('/notifications?limit=100'); notifications.value = r || [] } catch {} finally { loading.value = false }
}
async function markRead(n: any) {
  try { await api?.put(`/notifications/${n.id}/read`); n.read = true } catch {}
}
async function markAllRead() {
  try { await api?.put('/notifications/read-all'); notifications.value.forEach(n => n.read = true) } catch {}
}
function fmt(iso: string) {
  if (!iso) return ''; const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}
onMounted(load)
</script>
<template>
  <div class="page">
    <div class="header"><h2>通知</h2><button class="btn ghost" @click="markAllRead">全部已读</button><button class="close-btn" @click="close">×</button></div>
    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="notifications.length===0" class="empty">暂无通知</div>
    <div v-for="n in notifications" :key="n.id" class="notif" :class="{ unread: !n.read }" :style="{ cursor: n.read?'default':'pointer' }" @click="markRead(n)">
      <div class="notif-title">{{ n.title }}</div>
      <div class="notif-body" v-if="n.body">{{ n.body }}</div>
      <div class="notif-time">{{ fmt(n.created_at) }}</div>
    </div>
  </div>
</template>
<style scoped>
.page { height:100vh; background:#f8f9fa; font-family:-apple-system,sans-serif; overflow-y:auto; }
.header { display:flex;align-items:center;gap:12px;padding:16px 24px;border-bottom:1px solid #e9ecef; }
.header h2 { margin:0;font-size:18px;font-weight:600;flex:1; }
.close-btn { width:32px;height:32px;border:none;border-radius:8px;background:transparent;font-size:20px;cursor:pointer;color:#868e96; }
.close-btn:hover { background:#ffebee;color:#e91e63; }
.btn { height:34px;padding:0 14px;border:none;border-radius:8px;font-size:12px;cursor:pointer; }
.btn.ghost { background:#f1f3f5;color:#495057; }
.btn.ghost:hover { background:#e9ecef; }
.empty { text-align:center;padding:40px;color:#909399;font-size:13px; }
.notif { padding:12px 24px;border-bottom:1px solid #f0f0f0; }
.notif.unread { background:#f0f7ff;border-left:3px solid #409EFF; }
.notif-title { font-size:14px;font-weight:500;color:#333; }
.notif-body { font-size:13px;color:#666;margin-top:4px; }
.notif-time { font-size:11px;color:#909399;margin-top:4px; }
</style>
