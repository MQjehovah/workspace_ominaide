<template>
  <div class="clipboard-page">
    <div class="header">
      <span class="title">剪贴板历史</span>
      <button class="clear-btn" @click="handleClear">清空</button>
    </div>
    <div class="history-list">
      <div
        v-for="(item, index) in data.history"
        :key="index"
        class="item"
        @click="handleCopy(item.content)"
      >
        <div class="content">{{ item.content }}</div>
        <div class="time">{{ formatTime(item.time) }}</div>
      </div>
      <div v-if="data.history.length === 0" class="empty">暂无记录</div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface HistoryItem {
  content: string
  time: number
}

interface PageData {
  history: HistoryItem[]
}

const props = defineProps<{
  data: PageData
  execute: (action: string, args?: unknown) => Promise<unknown>
  close: () => void
}>()

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

async function handleClear() {
  await props.execute('clear')
}
</script>

<style scoped>
.clipboard-page {
  padding: 16px;
  max-width: 600px;
  margin: 0 auto;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.title {
  font-weight: 600;
  font-size: 18px;
}
.clear-btn {
  padding: 6px 12px;
  background: #ff4d4f;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.clear-btn:hover {
  background: #ff7875;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.item {
  padding: 12px;
  background: #f5f5f5;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}
.item:hover {
  background: #e8e8e8;
}
.content {
  font-size: 14px;
  color: #333;
  margin-bottom: 6px;
  word-break: break-all;
}
.time {
  font-size: 12px;
  color: #999;
}
.empty {
  text-align: center;
  color: #999;
  font-size: 14px;
  padding: 40px 0;
}
</style>