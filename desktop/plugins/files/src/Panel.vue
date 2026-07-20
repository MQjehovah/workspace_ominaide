<script setup lang="ts">
defineProps<{
  data: { recentFiles: any[]; total: number }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage: () => void; refresh: () => Promise<void>
}>()
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <div class="panel-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>
      <div class="panel-info">
        <span class="panel-title">文件</span>
        <span class="panel-meta">{{ data.total }} 个文件</span>
      </div>
      <button class="panel-btn" @click="openPage"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg></button>
    </div>
    <div v-if="data.recentFiles.length" class="file-list">
      <div v-for="f in data.recentFiles.slice(0,3)" :key="f.id" class="file-item">
        <div class="file-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </div>
        <div class="file-info">
          <div class="file-name">{{ f.original_name }}</div>
          <div class="file-meta">{{ f.size ? (f.size / 1024).toFixed(1) + ' KB' : '' }}</div>
        </div>
      </div>
    </div>
    <div v-else class="empty">暂无文件</div>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.panel-icon { width:32px; height:32px; border-radius:8px; background:#e3f2fd; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.panel-icon svg { width:16px; height:16px; color:#2196F3; }
.panel-info { flex:1; }
.panel-title { font-size:13px; font-weight:600; color:#1e1e1e; display:block; }
.panel-meta { font-size:11px; color:#999; }
.panel-btn { border:none; background:transparent; cursor:pointer; color:#ccc; padding:4px; border-radius:4px; }
.panel-btn:hover { background:#f5f5f5; color:#666; }
.file-list { display:flex; flex-direction:column; gap:4px; }
.file-item { display:flex; align-items:center; gap:8px; padding:6px 8px; border-radius:6px; }
.file-item:hover { background:#f5f7fa; }
.file-icon { flex-shrink:0; color:#2196F3; }
.file-icon svg { width:16px; height:16px; }
.file-info { flex:1; min-width:0; }
.file-name { font-size:12px; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.file-meta { font-size:10px; color:#999; }
.empty { text-align:center; padding:8px; color:#ccc; font-size:12px; }
</style>
