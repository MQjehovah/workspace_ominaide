<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()
const unread = ref(0); const latest = ref(''); let timer: any = null
const api = (window as any).mqbox?.api
async function load() {
  try {
    const [r1, r2] = await Promise.all([
      api?.get('/notifications/unread-count'),
      api?.get('/notifications?unread=true&limit=1'),
    ])
    unread.value = r1?.count || 0
    latest.value = r2?.[0]?.title || ''
  } catch {}
}
onMounted(() => { load(); timer = setInterval(load, 15000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">通知</span><button class="panel-arrow" @click="openPage">›</button></div>
    <div class="notif-row">
      <span class="badge" v-if="unread>0">{{ unread }}</span>
      <span class="latest" v-if="latest">{{ latest }}</span>
      <span v-else style="font-size:11px;color:#909399">暂无通知</span>
    </div>
  </div>
</template>
<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
.title { font-size:13px; font-weight:600; }
.panel-arrow { width:24px;height:24px;border:none;border-radius:6px;background:transparent;color:#ccc;cursor:pointer;font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center; }
.panel-arrow:hover { background:#f5f5f5;color:#666; }
.notif-row { display:flex; align-items:center; gap:8px; }
.badge { background:#e91e63; color:#fff; border-radius:10px; padding:1px 7px; font-size:11px; font-weight:700; }
.latest { font-size:12px; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
</style>
