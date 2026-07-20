<script setup lang="ts">
defineProps<{
  data: { notes: any[]; count: number }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage: () => void; refresh: () => Promise<void>
}>()
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <div class="panel-icon yellow">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
      </div>
      <div class="panel-info">
        <span class="panel-title">笔记</span>
        <span class="panel-meta">{{ data.count }} 篇</span>
      </div>
      <button class="panel-btn" @click="openPage"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg></button>
    </div>
    <div v-if="data.notes?.length" class="notes-list">
      <div v-for="n in data.notes.slice(0,3)" :key="n.id" class="note-item">
        <div class="note-title">{{ n.title || '无标题' }}</div>
        <div class="note-date">{{ n.updated_at ? n.updated_at.slice(0,10) : '' }}</div>
      </div>
    </div>
    <div v-else class="empty">暂无笔记</div>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.panel-icon { width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.panel-icon.yellow { background:#fff8e1; }
.panel-icon svg { width:16px; height:16px; color:#FF9800; }
.panel-info { flex:1; }
.panel-title { font-size:13px; font-weight:600; color:#1e1e1e; display:block; }
.panel-meta { font-size:11px; color:#999; }
.panel-btn { border:none; background:transparent; cursor:pointer; color:#ccc; padding:4px; border-radius:4px; }
.panel-btn:hover { background:#f5f5f5; color:#666; }
.notes-list { display:flex; flex-direction:column; gap:4px; }
.note-item { padding:6px 8px; border-radius:6px; }
.note-item:hover { background:#f5f7fa; }
.note-title { font-size:12px; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.note-date { font-size:10px; color:#999; margin-top:2px; }
.empty { text-align:center; padding:8px; color:#ccc; font-size:12px; }
</style>
