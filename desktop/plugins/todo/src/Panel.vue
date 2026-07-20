<script setup lang="ts">
interface Todo {
  id: string
  text: string
  priority: 'high' | 'medium' | 'low'
  dueDate: string | null
  completed: boolean
}

interface Props {
  data: {
    pendingCount: number
    todos: Todo[]
    items: Todo[]
  }
  execute: (action: string, args?: unknown) => Promise<unknown>
  openPage: () => void
  refresh: () => Promise<void>
}

defineProps<Props>()

function getPriorityColor(priority: string) {
  if (priority === 'high') return '#E53935'
  if (priority === 'low') return '#4CAF50'
  return '#FF9800'
}

function formatDueDate(dueDate: string | null) {
  if (!dueDate) return ''
  const today = new Date().toISOString().split('T')[0]
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const tomorrowStr = tomorrow.toISOString().split('T')[0]
  
  if (dueDate === today) return '今天'
  if (dueDate === tomorrowStr) return '明天'
  
  const due = new Date(dueDate)
  const now = new Date()
  const diff = Math.ceil((due.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  
  if (diff < 0) return `已过期${Math.abs(diff)}天`
  if (diff === 0) return '今天'
  if (diff === 1) return '明天'
  return `${diff}天后`
}
</script>

<template>
  <div class="todo-panel rounded-lg bg-white border border-gray-200 p-2.5 flex flex-col gap-2">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-orange-50 flex items-center justify-center">
          <svg class="w-4.5 h-4.5 text-orange-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
          </svg>
        </div>
        <div class="flex flex-col gap-0.5">
          <span class="text-sm text-gray-800 font-semibold">待办事项</span>
          <span class="text-xs text-gray-400">{{ data.pendingCount }} 个待完成</span>
        </div>
      </div>
      <button class="text-gray-400 cursor-pointer" @click="openPage">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="m9 18 6-6-6-6"/>
        </svg>
      </button>
    </div>
    
    <div v-if="data.items.length > 0" class="flex flex-col gap-1">
      <div 
        v-for="item in data.items.slice(0, 3)" 
        :key="item.id"
        class="flex items-center gap-1.5 py-1 px-2 rounded bg-gray-100 cursor-pointer hover:bg-gray-200"
        @click="execute('done', { id: item.id })"
      >
        <div class="w-1.5 h-1.5 rounded-full" :style="{ background: getPriorityColor(item.priority) }"></div>
        <span class="text-xs text-gray-800 truncate flex-1">{{ item.text }}</span>
        <span v-if="item.dueDate" class="text-xs text-orange-500">{{ formatDueDate(item.dueDate) }}</span>
      </div>
    </div>
    <div v-else class="text-xs text-gray-500 text-center py-2">暂无待办</div>
  </div>
</template>

<style scoped>
.todo-panel {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
</style>