<template>
  <div class="clipboard-page">
    <div class="header">
      <div class="head-left">
        <span class="title">剪贴板历史</span>
        <span class="meta">{{ local.length }} 条 · 已固定 {{ pinnedCount }}</span>
      </div>
      <div class="head-actions">
        <input v-model="query" class="search" placeholder="搜索剪贴板…" />
        <button class="clear-btn" @click="handleClear">清空未固定</button>
      </div>
    </div>

    <div class="hint">历史保存在本机 · 最多 200 条未固定记录 · 30 天后自动清理</div>

    <div class="history-list">
      <div
        v-for="item in filtered"
        :key="item.content + item.time"
        class="item"
        :class="{ pinned: item.pinned }"
      >
        <div class="item-main" @click="handleCopy(item)">
          <div class="content">{{ item.content.length > 400 ? item.content.slice(0, 400) + '…' : item.content }}</div>
          <div class="row">
            <span class="time">{{ formatTime(item.time) }}</span>
            <span v-if="item.pinned" class="pin-tag">已固定</span>
            <span v-if="(item.hits || 1) > 1" class="hits">使用 {{ item.hits }} 次</span>
          </div>
        </div>
        <div class="actions" @click.stop>
          <button :title="item.pinned ? '取消固定' : '固定'" @click="togglePin(item)">
            {{ item.pinned ? '📌' : '📍' }}
          </button>
          <button class="danger" title="删除" @click="removeItem(item)">✕</button>
        </div>
      </div>
      <div v-if="!filtered.length" class="empty">
        {{ query ? '没有匹配的记录' : '暂无记录' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface HistoryItem {
  content: string
  time: number
  pinned?: boolean
  hits?: number
}

interface PageData {
  history: HistoryItem[]
  stats?: { total: number; pinned: number; maxItems: number; maxAgeDays: number }
}

const props = defineProps<{
  data: PageData
  execute: (action: string, args?: unknown) => Promise<unknown>
  close: () => void
}>()

const local = ref<HistoryItem[]>([...(props.data?.history || [])])
const query = ref('')

watch(
  () => props.data?.history,
  (value) => { local.value = [...(value || [])] },
  { deep: true },
)

const pinnedCount = computed(() => local.value.filter(item => item.pinned).length)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return [...local.value]
    .sort((a, b) => (Number(!!b.pinned) - Number(!!a.pinned)) || (b.time - a.time))
    .filter(item => !q || item.content.toLowerCase().includes(q))
})

function formatTime(timestamp: number) {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - timestamp
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`
}

async function reload() {
  try {
    const data: any = await props.execute('getPageData')
    if (data?.history) local.value = data.history
  } catch { /* keep local state */ }
}

async function handleCopy(item: HistoryItem) {
  await props.execute('copy', { content: item.content })
  await reload()
}

async function togglePin(item: HistoryItem) {
  await props.execute('pin', { content: item.content, pinned: !item.pinned })
  await reload()
}

async function removeItem(item: HistoryItem) {
  await props.execute('delete', { content: item.content })
  await reload()
}

async function handleClear() {
  if (!confirm('清空未固定的记录？固定项会保留，此操作不可恢复。')) return
  await props.execute('clear')
  await reload()
}
</script>

<style scoped>
.clipboard-page {
  padding: 16px;
  max-width: 720px;
  margin: 0 auto;
}
.header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.head-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex: 1;
}
.title {
  font-weight: 600;
  font-size: 18px;
}
.meta {
  font-size: 12px;
  color: #999;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.search {
  width: 220px;
  padding: 7px 12px;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
}
.search:focus {
  border-color: #2196F3;
}
.clear-btn {
  padding: 7px 12px;
  background: #fff;
  color: #d32f2f;
  border: 1px solid #f0c4c4;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.clear-btn:hover {
  background: #fff4f4;
}
.hint {
  font-size: 11px;
  color: #aaa;
  margin-bottom: 14px;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.item {
  display: flex;
  align-items: stretch;
  gap: 8px;
  padding: 12px;
  background: #f7f8fa;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: background 0.15s;
}
.item:hover {
  background: #eef6ff;
}
.item.pinned {
  background: #fffaf0;
  border-color: #f2e2b8;
}
.item-main {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.content {
  font-size: 13.5px;
  color: #333;
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 6px;
  max-height: 120px;
  overflow: hidden;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: #999;
}
.pin-tag {
  color: #b26a00;
  background: #fff1d6;
  border-radius: 4px;
  padding: 1px 6px;
}
.hits {
  color: #8a94a8;
}
.actions {
  display: flex;
  align-items: center;
  gap: 2px;
}
.actions button {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: #999;
}
.actions button:hover {
  background: #e3f2fd;
  color: #2196F3;
}
.actions button.danger:hover {
  background: #fdecea;
  color: #c62828;
}
.empty {
  text-align: center;
  color: #999;
  font-size: 14px;
  padding: 40px 0;
}
</style>
