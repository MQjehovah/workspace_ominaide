<script setup lang="ts">
interface CaptureRecord {
  id: string
  dataUrl: string
  time: number
  type: string
  width: number
  height: number
}

interface Props {
  data: {
    captures: CaptureRecord[]
  }
  execute: (action: string, args?: unknown) => Promise<unknown>
  close: () => void
  refresh: () => Promise<void>
}

const props = defineProps<Props>()

const formatTime = (time: number) => {
  if (!time) return ''
  return new Date(time).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
const del = async (id: string) => {
  await props.execute('delete', { id })
  await props.refresh()
}
const clear = async () => {
  await props.execute('clear')
  await props.refresh()
}
</script>

<template>
  <div class="page">
    <!-- 头部 -->
    <div class="header">
      <div class="header-top">
        <div class="title-row">
          <div class="icon-wrap">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/>
              <circle cx="12" cy="13" r="3"/>
            </svg>
          </div>
          <span class="title">截图历史</span>
        </div>
        <span class="count">{{ data?.captures?.length || 0 }} 张</span>
      </div>

      <div class="actions">
        <button class="action-btn primary" @click="execute('region')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path d="M9 3v18M3 9h18"/>
          </svg>
          <span>区域截图</span>
        </button>
        <button class="action-btn" @click="execute('fullscreen')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/>
          </svg>
          <span>全屏截图</span>
        </button>
      </div>
    </div>

    <!-- 列表 -->
    <div class="list-area">
      <div v-if="!data?.captures || data.captures.length === 0" class="empty">
        <div class="empty-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <path d="M21 15l-5-5L5 21"/>
          </svg>
        </div>
        <span class="empty-text">还没有截图</span>
        <span class="empty-hint">点击上方按钮开始</span>
      </div>

      <div v-else class="grid">
        <div
          v-for="cap in data.captures"
          :key="cap.id"
          class="card"
          @click="execute('open', { dataUrl: cap.dataUrl })"
        >
          <div class="thumb">
            <img :src="cap.dataUrl" />
          </div>
          <div class="overlay">
            <span class="time">{{ formatTime(cap.time) }}</span>
            <button class="del" @click.stop="del(cap.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部 -->
    <div v-if="data?.captures?.length" class="footer">
      <button class="clear-btn" @click="clear">清空历史</button>
    </div>
  </div>
</template>

<style scoped>
.page {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: #f5f5f7;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* —— 头部 —— */
.header {
  padding: 20px 24px 16px;
  background: #fff;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.icon-wrap {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #e3f2fd;
  display: flex;
  align-items: center;
  justify-content: center;
}
.icon-wrap svg { width: 18px; height: 18px; color: #007aff; }

.title { font-size: 16px; font-weight: 600; color: #1d1d1f; }
.count { font-size: 13px; color: #86868b; }

.actions { display: flex; gap: 10px; }

.action-btn {
  flex: 1;
  height: 56px;
  border: none;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  background: rgba(0, 0, 0, 0.05);
  color: #1d1d1f;
}
.action-btn svg { width: 20px; height: 20px; }
.action-btn:hover { background: rgba(0, 0, 0, 0.08); }
.action-btn.primary { background: #007aff; color: #fff; }
.action-btn.primary:hover { background: #0066d6; }

/* —— 列表 —— */
.list-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 6px;
}
.empty-icon { color: #c7c7cc; margin-bottom: 8px; }
.empty-icon svg { width: 48px; height: 48px; }
.empty-text { font-size: 15px; color: #86868b; }
.empty-hint { font-size: 13px; color: #c7c7cc; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.card {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  transition: box-shadow 0.2s, transform 0.2s;
}
.card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}

.thumb {
  aspect-ratio: 16 / 10;
  overflow: hidden;
  background: #f5f5f7;
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 8px;
  opacity: 0;
  transition: opacity 0.2s;
  background: linear-gradient(180deg, rgba(0,0,0,0.4) 0%, transparent 40%, transparent 60%, rgba(0,0,0,0.4) 100%);
}
.card:hover .overlay { opacity: 1; }

.time {
  color: #fff;
  font-size: 11px;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.3);
}

.del {
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
  flex-shrink: 0;
}
.del svg { width: 14px; height: 14px; }
.del:hover { background: #ff3b30; }

/* —— 底部 —— */
.footer {
  padding: 12px 24px;
  background: #fff;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.clear-btn {
  width: 100%;
  height: 38px;
  border: none;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.05);
  color: #86868b;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.clear-btn:hover { background: rgba(255, 59, 48, 0.1); color: #ff3b30; }
</style>
