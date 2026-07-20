<script setup lang="ts">
import { computed } from 'vue'
interface Props {
  data: { notes: { id: string; content: string; time: number; tags: string[] }[] }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage: () => void; refresh: () => Promise<void>
}
const props = defineProps<Props>()
const recentNotes = computed(() => props.data.notes.slice(0, 2))
function formatTime(t: number) {
  const d = new Date(t), n = new Date()
  const diff = n.getTime() - t
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <div class="panel-icon yellow">
        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 3H4.99c-1.11 0-1.98.89-1.98 2L3 19c0 1.11.88 2 1.99 2H19c1.1 0 2-.89 2-2V5c0-1.11-.9-2-2-2zM19 15H5V5h14v10z"/></svg>
      </div>
      <div class="panel-info">
        <span class="panel-title">快速笔记</span>
        <span class="panel-meta">{{ data.notes.length }} 条笔记</span>
      </div>
      <button class="panel-btn" @click="openPage">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
      </button>
    </div>
    <div v-if="recentNotes.length" class="notes-list">
      <div v-for="note in recentNotes" :key="note.id" class="note-item">
        <div class="note-text">{{ note.content }}</div>
        <div class="note-meta">
          <span>{{ formatTime(note.time) }}</span>
          <span v-for="tag in note.tags.slice(0,2)" :key="tag" class="tag">{{ tag }}</span>
        </div>
      </div>
    </div>
    <div v-else class="empty">暂无笔记</div>
    <button class="add-btn" @click="execute('add', { content: '', tags: [] })">+ 添加笔记</button>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; display:flex; flex-direction:column; gap:8px; }
.panel-hd { display:flex; align-items:center; gap:10px; }
.panel-icon { width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.panel-icon.yellow { background:#fff8e1; }
.panel-icon svg { width:16px; height:16px; color:#FF9800; }
.panel-info { flex:1; }
.panel-title { font-size:13px; font-weight:600; color:#1e1e1e; display:block; }
.panel-meta { font-size:11px; color:#999; }
.panel-btn { border:none; background:transparent; cursor:pointer; color:#ccc; padding:4px; border-radius:4px; }
.panel-btn:hover { background:#f5f5f5; color:#666; }
.notes-list { display:flex; flex-direction:column; gap:6px; }
.note-item { padding:8px; background:#f8f9fa; border-radius:6px; }
.note-text { font-size:12px; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.note-meta { display:flex; align-items:center; gap:4px; margin-top:4px; font-size:10px; color:#999; }
.tag { padding:1px 6px; background:#fff3e0; color:#FF9800; border-radius:4px; }
.empty { text-align:center; padding:8px; color:#ccc; font-size:12px; }
.add-btn { height:28px; border-radius:6px; border:none; background:#FF9800; color:#fff; font-size:12px; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:4px; }
.add-btn:hover { background:#f57c00; }
</style>
