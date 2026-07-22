<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()
const entries = ref<any[]>([]); const loading = ref(true); let timer: any = null
const api = (window as any).mqbox?.api
async function load() {
  try {
    const r = await api?.get('/rss/entries?unread=true&page_size=5')
    entries.value = r?.items || []
  } catch {} finally { loading.value = false }
}
onMounted(() => { load(); timer = setInterval(load, 60000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>
<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">资讯</span><button class="panel-arrow" @click="openPage">›</button></div>
    <div v-if="loading" style="font-size:11px;color:#909399">加载中…</div>
    <div v-else-if="entries.length===0" style="font-size:11px;color:#909399">暂无新文章</div>
    <div v-for="e in entries.slice(0,4)" :key="e.id" class="entry-item">{{ e.title }}</div>
    <div v-if="entries.length>4" style="font-size:11px;color:#909399;margin-top:4px">还有 {{ entries.length-4 }} 条</div>
  </div>
</template>
<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
.title { font-size:13px; font-weight:600; }
.panel-arrow { width:24px;height:24px;border:none;border-radius:6px;background:transparent;color:#ccc;cursor:pointer;font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center; }
.panel-arrow:hover { background:#f5f5f5;color:#666; }
.entry-item { font-size:12px;padding:4px 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border-bottom:1px solid #f5f5f5;color:#333; }
.entry-item:last-child { border-bottom:none; }
</style>
