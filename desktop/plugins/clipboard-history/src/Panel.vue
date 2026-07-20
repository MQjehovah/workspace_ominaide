<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{
  data: { history: { content: string; time: number }[] }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage?: () => void; refresh: () => Promise<void>
}>()
const items = computed(() => props.data.history.slice(0, 3))
function formatTime(t: number) {
  const n = new Date().getTime() - t
  if (n < 60000) return '刚刚'
  if (n < 3600000) return `${Math.floor(n / 60000)}分钟前`
  if (n < 86400000) return `${Math.floor(n / 3600000)}小时前`
  const d = new Date(t); return `${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <div class="panel-icon blue">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="2" width="8" height="4"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>
      </div>
      <div class="panel-info">
        <span class="panel-title">剪贴板历史</span>
        <span class="panel-meta">{{ data.history.length }} 条</span>
      </div>
    </div>
    <div class="list">
      <div v-for="item in items" :key="item.time" class="list-item" @click="execute('copy', { content: item.content })">
        <div class="item-text">{{ item.content.length > 40 ? item.content.slice(0, 40) + '...' : item.content }}</div>
        <div class="item-time">{{ formatTime(item.time) }}</div>
      </div>
      <div v-if="!items.length" class="empty">暂无记录</div>
    </div>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.panel-icon { width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.panel-icon.blue { background:#e3f2fd; }
.panel-icon svg { width:16px; height:16px; color:#2196F3; }
.panel-info { flex:1; }
.panel-title { font-size:13px; font-weight:600; color:#1e1e1e; display:block; }
.panel-meta { font-size:11px; color:#999; }
.list { display:flex; flex-direction:column; gap:6px; }
.list-item { padding:6px 8px; background:#f8f9fa; border-radius:6px; cursor:pointer; }
.list-item:hover { background:#e3f2fd; }
.item-text { font-size:12px; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.item-time { font-size:10px; color:#999; margin-top:2px; }
.empty { text-align:center; padding:8px; color:#ccc; font-size:12px; }
</style>
