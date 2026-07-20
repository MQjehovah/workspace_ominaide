<script setup lang="ts">
interface Props {
  data: { pendingCount: number; items: { id: string; text: string; priority: string }[] }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage: () => void
  refresh: () => Promise<void>
}
defineProps<Props>()
function getPriorityColor(p: string) { return p === 'high' ? '#E53935' : p === 'low' ? '#4CAF50' : '#FF9800' }
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div class="panel-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
      </div>
      <div class="panel-info">
        <span class="panel-title">待办事项</span>
        <span class="panel-meta">{{ data.pendingCount }} 个待完成</span>
      </div>
      <button class="panel-arrow" @click="openPage">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
      </button>
    </div>
    <div class="panel-body">
      <div v-if="data.items.length" class="item-list">
        <div v-for="item in data.items.slice(0,4)" :key="item.id" class="item-row" @click="execute('done', { id: item.id })">
          <div class="item-dot" :style="{ background: getPriorityColor(item.priority) }"></div>
          <span class="item-text">{{ item.text }}</span>
        </div>
      </div>
      <div v-else class="empty">暂无待办</div>
    </div>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-header { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.panel-icon { width:32px; height:32px; border-radius:8px; background:#fff3e0; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.panel-icon svg { width:16px; height:16px; color:#FF9800; }
.panel-info { flex:1; }
.panel-title { font-size:13px; font-weight:600; color:#1e1e1e; display:block; }
.panel-meta { font-size:11px; color:#999; }
.panel-arrow { border:none; background:transparent; cursor:pointer; color:#ccc; padding:4px; border-radius:4px; }
.panel-arrow:hover { background:#f5f5f5; color:#666; }
.panel-body { }
.item-list { display:flex; flex-direction:column; gap:4px; }
.item-row { display:flex; align-items:center; gap:8px; padding:6px 8px; border-radius:6px; cursor:pointer; }
.item-row:hover { background:#f8f9fa; }
.item-dot { width:6px; height:6px; border-radius:3px; flex-shrink:0; }
.item-text { font-size:12px; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.empty { text-align:center; padding:8px; color:#ccc; font-size:12px; }
</style>
