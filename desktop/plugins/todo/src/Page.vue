<script setup lang="ts">
import { ref, computed } from 'vue'

interface Todo {
  id: string
  text: string
  priority: 'high' | 'medium' | 'low'
  dueDate: string | null
  completed: boolean
  createdAt: number
}

interface Props {
  data: {
    todos: Todo[]
    newTodoText: string
  }
  execute: (action: string, args?: unknown) => Promise<unknown>
  close: () => void
}

const props = defineProps<Props>()
const newTodoText = ref(props.data.newTodoText || '')

const pendingTodos = computed(() => props.data.todos.filter(t => !t.completed))
const completedTodos = computed(() => props.data.todos.filter(t => t.completed))

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

const handleAdd = () => {
  if (newTodoText.value.trim()) {
    props.execute('add', { content: newTodoText.value })
    newTodoText.value = ''
  }
}
</script>

<template>
  <div class="todo-page flex flex-col h-full">
    <div class="p-4 bg-gray-100 border-b border-gray-200">
      <div class="flex items-center gap-2">
        <input 
          v-model="newTodoText"
          class="flex-1 h-10 rounded-lg border border-gray-200 px-3 text-sm"
          placeholder="添加待办... !high/@明天"
          @keyup.enter="handleAdd"
        />
        <button 
          class="w-20 h-10 rounded-lg bg-orange-500 text-white text-sm hover:bg-orange-600"
          @click="handleAdd"
        >添加</button>
      </div>
    </div>
    
    <div class="flex-1 overflow-auto p-2">
      <div v-if="pendingTodos.length === 0" class="flex flex-col items-center justify-center h-full text-gray-400">
        <svg class="w-10 h-10 mb-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
        </svg>
        <span class="text-sm">暂无待办事项</span>
      </div>
      
      <div v-else class="flex flex-col gap-2">
        <div 
          v-for="todo in pendingTodos"
          :key="todo.id"
          class="flex items-center gap-3 p-3 rounded-lg bg-gray-100 hover:bg-gray-200"
        >
          <button 
            class="w-6 h-6 rounded-full border-2 flex items-center justify-center hover:bg-orange-500"
            :style="{ borderColor: getPriorityColor(todo.priority) }"
            @click="execute('done', { id: todo.id })"
          ></button>
          <span class="flex-1 text-sm text-gray-800">{{ todo.text }}</span>
          <span v-if="todo.dueDate" class="text-xs text-orange-500">{{ formatDueDate(todo.dueDate) }}</span>
          <button 
            class="w-6 h-6 rounded flex items-center justify-center hover:bg-orange-100"
            @click="execute('delete', { id: todo.id })"
          >
            <svg class="w-3.5 h-3.5 text-gray-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
          </button>
        </div>
      </div>
      
      <div v-if="completedTodos.length > 0" class="mt-4">
        <div class="text-xs text-gray-500 mb-2">已完成</div>
        <div 
          v-for="todo in completedTodos"
          :key="todo.id"
          class="flex items-center gap-3 p-2 rounded-lg bg-gray-200 opacity-60"
        >
          <div class="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center">
            <svg class="w-3.5 h-3.5 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
            </svg>
          </div>
          <span class="flex-1 text-sm text-gray-500">{{ todo.text }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.todo-page {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
</style>