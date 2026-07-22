<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()
const today = new Date()
const events = ref<any[]>([])
const loading = ref(true)
let timer: any = null
async function load() {
  const s = new Date(today.getFullYear(), today.getMonth(), 1)
  const e = new Date(today.getFullYear(), today.getMonth() + 1, 0)
  try {
    const r = await (window as any).mqbox.api.get(`/schedule?start=${s.toISOString()}&end=${e.toISOString()}`)
    events.value = r || []
  } catch { events.value = [] }
  finally { loading.value = false }
}
onMounted(() => { load(); timer = setInterval(load, 60000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
function todayEvents() { return events.value.filter((e:any) => { const d = new Date(e.start_time); return d.getDate() === today.getDate() && d.getMonth() === today.getMonth() && d.getFullYear() === today.getFullYear() }) }
</script>
<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">日程</span><button class="panel-arrow" @click="openPage">›</button></div>
    <div style="font-size:11px;color:#adb5bd;margin-bottom:6px">{{ today.getMonth()+1 }}月{{ today.getDate() }}日 · {{ ['日','一','二','三','四','五','六'][today.getDay()] }}</div>
    <div v-if="loading" style="font-size:11px;color:#909399">加载中…</div>
    <div v-else-if="todayEvents().length === 0" style="font-size:11px;color:#909399">今日无日程</div>
    <div v-for="e in todayEvents().slice(0,3)" :key="e.id" class="event-item" :style="{ borderLeftColor: e.color }">{{ e.title }}</div>
    <div v-if="todayEvents().length > 3" style="font-size:11px;color:#909399;margin-top:4px">还有 {{ todayEvents().length - 3 }} 项</div>
  </div>
</template>
<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
.title { font-size:13px; font-weight:600; }
.panel-arrow { width:24px;height:24px;border:none;border-radius:6px;background:transparent;color:#ccc;cursor:pointer;font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center; }
.panel-arrow:hover { background:#f5f5f5;color:#666; }
.event-item { font-size:12px; padding:4px 6px; border-left:3px solid; margin-bottom:2px; border-radius:0 4px 4px 0; background:#f8f9fa; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
</style>
