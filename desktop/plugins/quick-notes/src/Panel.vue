<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Note } from './types'
import NoteDetail from './NoteDetail.vue'

interface Props {
  data: {
    notes: Note[]
  }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage: () => void
  refresh: () => Promise<void>
}

const props = defineProps<Props>()

const recentNotes = computed(() => {
  return props.data.notes.slice(0, 2)
})

// 笔记详情面板
const selectedNote = ref<Note | null>(null)

const handleSelectNote = (note: Note) => {
  selectedNote.value = note
}

const handleCloseDetail = () => {
  selectedNote.value = null
}

const handleNoteUpdated = (updated: Note) => {
  // 同步更新本地数据中的笔记内容
  const idx = props.data.notes.findIndex((n: Note) => n.id === updated.id)
  if (idx !== -1) {
    props.data.notes[idx] = updated
  }
  selectedNote.value = updated
}

const handleNoteDeleted = async (_id: string) => {
  selectedNote.value = null
  await props.refresh()
}

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
</script>

<template>
  <div class="quick-notes-panel rounded-lg bg-white border border-gray-200 p-2.5 flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-yellow-50 flex items-center justify-center">
          <svg class="w-4.5 h-4.5 text-yellow-500" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 3H4.99c-1.11 0-1.98.89-1.98 2L3 19c0 1.11.88 2 1.99 2H19c1.1 0 2-.89 2-2V5c0-1.11-.9-2-2-2zM19 15H5V5h14v10z"/>
          </svg>
        </div>
        <div class="flex flex-col gap-0.5">
          <span class="text-sm text-gray-800 font-semibold">快速笔记</span>
          <span class="text-xs text-gray-400">{{ data.notes.length }} 条笔记</span>
        </div>
      </div>
      <button class="text-gray-400 cursor-pointer" @click="openPage">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="m9 18 6-6-6-6"/>
        </svg>
      </button>
    </div>

    <div v-if="recentNotes.length > 0" class="flex flex-col gap-1.5">
      <div
        v-for="note in recentNotes"
        :key="note.id"
        class="p-2 rounded-md bg-gray-50 hover:bg-gray-100 cursor-pointer"
        @click="handleSelectNote(note)"
      >
        <div class="text-xs text-gray-800 line-clamp-2">{{ note.content }}</div>
        <div class="flex items-center gap-1 mt-1">
          <span class="text-xs text-gray-400">{{ formatTime(note.time) }}</span>
          <div v-if="note.tags.length > 0" class="flex gap-0.5">
            <span
              v-for="tag in note.tags.slice(0, 2)"
              :key="tag"
              class="text-xs px-1 py-0.5 rounded bg-yellow-100 text-yellow-600"
            >
              {{ tag }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="flex items-center justify-center py-3">
      <span class="text-xs text-gray-400">暂无笔记</span>
    </div>

    <button
      class="w-full h-7 rounded-md bg-yellow-500 text-white text-xs font-medium hover:bg-yellow-600 flex items-center justify-center gap-1"
      @click="execute('add', { content: '', tags: [] })"
    >
      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 5v14M5 12h14"/>
      </svg>
      添加笔记
    </button>
  </div>

  <!-- 笔记详情弹窗 -->
  <NoteDetail
    v-if="selectedNote"
    :note="selectedNote"
    :execute="execute"
    @close="handleCloseDetail"
    @updated="handleNoteUpdated"
    @deleted="handleNoteDeleted"
  />
</template>

<style scoped>
.quick-notes-panel {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>