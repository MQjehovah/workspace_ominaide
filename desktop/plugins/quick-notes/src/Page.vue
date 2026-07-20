<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Note } from './types'

interface Props {
  data: {
    notes: Note[]
  }
  execute: (action: string, args?: unknown) => Promise<unknown>
  close: () => void
}

const props = defineProps<Props>()

const newContent = ref('')
const newTags = ref('')
const isAdding = ref(false)

const sortedNotes = computed(() => {
  return [...props.data.notes].sort((a, b) => b.time - a.time)
})

const formatTime = (timestamp: number) => {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffDays < 7) return `${diffDays}天前`
  return date.toLocaleDateString()
}

const handleAdd = async () => {
  if (!newContent.value.trim()) return

  const tags = newTags.value.split(',').map(t => t.trim()).filter(t => t)
  await props.execute('add', { content: newContent.value.trim(), tags })

  newContent.value = ''
  newTags.value = ''
  isAdding.value = false
}

const handleDelete = async (id: string) => {
  await props.execute('delete', { id })
}
</script>

<template>
  <div class="quick-notes-page flex flex-col h-full">
    <div class="p-4 bg-gray-100 border-b border-gray-200">
      <div class="flex items-center justify-between">
        <span class="text-sm text-gray-800 font-medium">笔记列表 ({{ data.notes.length }})</span>
        <button
          class="h-8 rounded-md bg-yellow-500 text-white text-sm px-3 hover:bg-yellow-600 flex items-center gap-1"
          @click="isAdding = true"
        >
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          添加
        </button>
      </div>
    </div>

    <div v-if="isAdding" class="p-3 bg-yellow-50 border-b border-yellow-200">
      <textarea
        v-model="newContent"
        class="w-full h-20 p-2 rounded-md border border-gray-200 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-yellow-400"
        placeholder="输入笔记内容..."
      ></textarea>
      <input
        v-model="newTags"
        class="w-full mt-2 p-2 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-1 focus:ring-yellow-400"
        placeholder="标签（用逗号分隔）"
      />
      <div class="flex gap-2 mt-2">
        <button
          class="flex-1 h-7 rounded-md bg-yellow-500 text-white text-sm hover:bg-yellow-600"
          @click="handleAdd"
        >
          保存
        </button>
        <button
          class="flex-1 h-7 rounded-md bg-gray-200 text-gray-600 text-sm hover:bg-gray-300"
          @click="isAdding = false; newContent = ''; newTags = ''"
        >
          取消
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-auto p-2">
      <div v-if="sortedNotes.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400">
        <svg class="w-12 h-12 mb-4" viewBox="0 0 24 24" fill="currentColor">
          <path d="M19 3H4.99c-1.11 0-1.98.89-1.98 2L3 19c0 1.11.88 2 1.99 2H19c1.1 0 2-.89 2-2V5c0-1.11-.9-2-2-2zM19 15H5V5h14v10z"/>
        </svg>
        <span class="text-sm">暂无笔记</span>
        <span class="text-xs mt-1">点击添加按钮创建笔记</span>
      </div>

      <div v-else class="flex flex-col gap-2">
        <div
          v-for="note in sortedNotes"
          :key="note.id"
          class="p-3 rounded-lg bg-white border border-gray-200 hover:border-gray-300"
        >
          <div class="text-sm text-gray-800 mb-2">{{ note.content }}</div>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-400">{{ formatTime(note.time) }}</span>
              <div v-if="note.tags.length > 0" class="flex gap-1">
                <span
                  v-for="tag in note.tags"
                  :key="tag"
                  class="text-xs px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-600"
                >
                  {{ tag }}
                </span>
              </div>
            </div>
            <button
              class="w-6 h-6 rounded-md flex items-center justify-center hover:bg-red-50"
              @click="handleDelete(note.id)"
            >
              <svg class="w-3.5 h-3.5 text-gray-400 hover:text-red-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quick-notes-page {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
</style>