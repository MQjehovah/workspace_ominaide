<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{
  data: { lastCapture: any; captureCount: number }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage?: () => void; refresh: () => Promise<void>
}>()
const captureCount = computed(() => props.data?.captureCount || 0)
</script>

<template>
  <div class="panel">
    <div class="panel-hd">
      <div class="panel-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21,15 16,10 5,21"/>
        </svg>
      </div>
      <div class="panel-info">
        <span class="panel-title">截图工具</span>
        <span class="panel-meta">{{ captureCount }} 张截图</span>
      </div>
      <button v-if="openPage" class="panel-btn" @click="openPage">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
      </button>
    </div>
    <div class="actions">
      <button class="btn primary" @click="execute('region')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18M3 9h18"/></svg>
        区域截图
      </button>
      <button class="btn secondary" @click="execute('fullscreen')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="2"/></svg>
        全屏截图
      </button>
    </div>
    <div v-if="data?.lastCapture" class="capture-preview" @click="execute('open', { dataUrl: data.lastCapture.dataUrl })">
      <img :src="data.lastCapture.dataUrl" class="thumb" />
      <div class="capture-info">
        <span class="capture-type">{{ data.lastCapture.type === 'fullscreen' ? '全屏' : '区域' }}</span>
        <span class="capture-time">{{ data.lastCapture.width }}×{{ data.lastCapture.height }}</span>
      </div>
    </div>
    <div v-else class="empty">暂无截图</div>
  </div>
</template>

<style scoped>
.panel { background:#fff; border-radius:10px; border:1px solid #e8e8e8; padding:12px; }
.panel-hd { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
.panel-icon { width:32px; height:32px; border-radius:8px; background:#e3f2fd; display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.panel-icon svg { width:16px; height:16px; color:#2196F3; }
.panel-info { flex:1; }
.panel-title { font-size:13px; font-weight:600; color:#1e1e1e; display:block; }
.panel-meta { font-size:11px; color:#999; }
.panel-btn { border:none; background:transparent; cursor:pointer; color:#ccc; padding:4px; border-radius:4px; }
.panel-btn:hover { background:#f5f5f5; color:#666; }
.actions { display:flex; gap:8px; margin-bottom:8px; }
.btn { flex:1; height:36px; border-radius:8px; border:none; font-size:12px; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:6px; }
.btn.primary { background:#2196F3; color:#fff; }
.btn.primary:hover { background:#1976D2; }
.btn.secondary { background:#f0f0f0; color:#333; }
.btn.secondary:hover { background:#e0e0e0; }
.capture-preview { display:flex; align-items:center; gap:8px; padding:4px; border-radius:6px; cursor:pointer; }
.capture-preview:hover { background:#f5f5f5; }
.thumb { width:48px; height:32px; border-radius:4px; object-fit:cover; border:1px solid #e0e0e0; }
.capture-info { display:flex; flex-direction:column; }
.capture-type { font-size:11px; color:#666; }
.capture-time { font-size:10px; color:#999; }
.empty { text-align:center; padding:8px; color:#ccc; font-size:12px; }
</style>
