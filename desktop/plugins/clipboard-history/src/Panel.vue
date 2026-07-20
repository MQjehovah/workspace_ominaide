<template>
  <div class="clipboard-panel">
    <div class="header">
      <span class="title">剪贴板历史</span>
      <span class="count">{{ data.history.length }} 条</span>
    </div>
    <div class="recent-list">
      <div
        v-for="(item, index) in recentItems"
        :key="index"
        class="item"
        @click="handleCopy(item.content)"
      >
        <div class="content">{{ truncate(item.content, 30) }}</div>
        <div class="time">{{ formatTime(item.time) }}</div>
      </div>
      <div v-if="recentItems.length === 0" class="empty">暂无记录</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface HistoryItem {
  content: string
  time: number
}

interface PanelData {
  history: HistoryItem[]
}

const props = defineProps<{
  data: PanelData
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage?: () => void
  refresh: () => Promise<void>
}>()

const recentItems = computed(() => props.data.history.slice(0, 3))

function truncate(str: string, maxLen: number) {
  if (!str) return ''
  return str.length > maxLen ? str.slice(0, maxLen) + '...' : str
}

function formatTime(timestamp: number) {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - timestamp
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`
}

async function handleCopy(content: string) {
  await props.execute('copy', { content })
}
</script>

<style scoped>
.clipboard-panel {
  background: #fff;
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.title {
  font-weight: 600;
  font-size: 14px;
}
.count {
  font-size: 12px;
  color: #999;
}
.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.item {
  padding: 8px;
  background: #f5f5f5;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.2s;
}
.item:hover {
  background: #e8e8e8;
}
.content {
  font-size: 13px;
  color: #333;
  margin-bottom: 4px;
}
.time {
  font-size: 11px;
  color: #999;
}
.empty {
  text-align: center;
  color: #999;
  font-size: 12px;
  padding: 20px 0;
}
</style>