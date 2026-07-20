<template>
  <div class="todo-page">
    <div class="header">
      <div class="header-row">
        <input v-model="newText" class="input" placeholder="添加待办，支持 #标签 @日期" @keyup.enter="handleCreate" />
        <button class="btn btn-primary" @click="handleCreate">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
          添加
        </button>
      </div>
    </div>
    <div class="board">
      <div v-for="col in columns" :key="col.key" class="column" @dragover.prevent @drop="onDrop($event, col.key)">
        <div class="col-header" :class="col.key">
          <div class="col-title-row">
            <div class="col-dot" :class="col.key"></div>
            <span class="col-title">{{ col.label }}</span>
          </div>
          <span class="col-count">{{ grouped[col.key]?.length || 0 }}</span>
        </div>
        <div class="col-body" :class="{ 'drag-over': dragOverCol === col.key }" @dragover="dragOverCol = col.key" @dragleave="dragOverCol = null">
          <div v-for="item in grouped[col.key]" :key="item.id" class="card" :class="[draggedId === item.id ? 'dragging' : '', 'pri-border-' + Math.min(item.priority, 3)]" draggable="true" @dragstart="onDragStart($event, item)" @dragend="onDragEnd">
            <div class="card-text">{{ item.text }}</div>
            <div class="card-meta">
              <span v-if="item.priority > 0" class="tag pri" :class="'pri-' + item.priority">P{{ item.priority }}</span>
              <span v-if="item.due_date" class="tag due" :class="{ urgent: isUrgent(item.due_date) }">{{ formatDue(item.due_date) }}</span>
              <button class="del-btn" @click="handleDelete(item.id)" title="删除">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
          </div>
          <div v-if="!grouped[col.key]?.length" class="empty">暂无</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface Todo {
  id: string
  text: string
  status: 'pending' | 'in_progress' | 'done'
  priority: number
  due_date: string | null
}

interface Props {
  data: { todos: Todo[] }
  execute: (action: string, args?: unknown) => Promise<unknown>
  refresh?: () => void
}

const props = defineProps<Props>()
const newText = ref('')
const dragOverCol = ref<string | null>(null)

const columns = [
  { key: 'pending', label: '待处理' },
  { key: 'in_progress', label: '进行中' },
  { key: 'done', label: '已完成' },
]

const grouped = computed(() => {
  const map: Record<string, Todo[]> = { pending: [], in_progress: [], done: [] }
  for (const t of props.data.todos || []) {
    if (map[t.status]) map[t.status].push(t)
  }
  return map
})

let draggedId: string | null = null

function onDragStart(e: DragEvent, item: Todo) {
  draggedId = item.id
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

function onDragEnd() {
  draggedId = null
  dragOverCol.value = null
}

async function onDrop(e: DragEvent, targetStatus: string) {
  dragOverCol.value = null
  if (!draggedId) return
  const item = props.data.todos?.find(t => t.id === draggedId)
  if (!item || item.status === targetStatus) return
  await props.execute('update', { id: draggedId, status: targetStatus })
  props.refresh?.()
}

function isUrgent(due: string) {
  if (!due) return false
  const diff = Math.ceil((new Date(due).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
  return diff <= 2
}

function formatDue(due: string) {
  if (!due) return ''
  const d = new Date(due)
  const now = new Date()
  const diff = Math.ceil((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  if (diff < 0) return `超期${Math.abs(diff)}天`
  if (diff === 0) return '今天'
  if (diff === 1) return '明天'
  return `剩${diff}天`
}

async function handleCreate() {
  if (!newText.value.trim()) return
  await props.execute('create', { content: newText.value })
  newText.value = ''
  props.refresh?.()
}

async function handleDelete(id: string) {
  if (!confirm('确定删除？')) return
  await props.execute('delete', { id })
  props.refresh?.()
}

onMounted(() => {
  window.mqbox?.todo?.onUpdated(() => props.refresh?.())
})
</script>

<style scoped>
.todo-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f5f6fa;
}

.header {
  padding: 20px 28px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
}

.header-row {
  display: flex;
  gap: 10px;
  max-width: 640px;
}

.input {
  flex: 1;
  height: 42px;
  border-radius: 10px;
  border: 2px solid #e8e8e8;
  padding: 0 16px;
  font-size: 14px;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.input:focus {
  border-color: #FF9800;
}

.btn {
  height: 42px;
  border-radius: 10px;
  border: none;
  padding: 0 22px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s;
}

.btn-primary {
  background: #FF9800;
  color: #fff;
}

.btn-primary:hover {
  background: #f57c00;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(255, 152, 0, 0.3);
}

.board {
  flex: 1;
  display: flex;
  gap: 16px;
  padding: 20px 28px;
  min-height: 0;
  overflow-x: auto;
}

.column {
  flex: 1;
  min-width: 260px;
  display: flex;
  flex-direction: column;
  background: #f0f1f5;
  border-radius: 12px;
  overflow: hidden;
}

.col-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
}

.col-header.pending { border-bottom: 3px solid #FF9800; }
.col-header.in_progress { border-bottom: 3px solid #2196F3; }
.col-header.done { border-bottom: 3px solid #4CAF50; }

.col-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.col-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.col-dot.pending { background: #FF9800; }
.col-dot.in_progress { background: #2196F3; }
.col-dot.done { background: #4CAF50; }

.col-title {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.col-count {
  font-size: 11px;
  font-weight: 500;
  color: #999;
  background: #fff;
  padding: 2px 10px;
  border-radius: 12px;
}

.col-body {
  flex: 1;
  padding: 8px;
  overflow-y: auto;
  min-height: 80px;
  transition: background 0.2s;
}

.col-body.drag-over {
  background: rgba(255, 152, 0, 0.08);
}

.card {
  background: #fff;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 8px;
  cursor: grab;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  transition: all 0.2s;
  border-left: 3px solid transparent;
  position: relative;
}

.card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  transform: translateY(-1px);
}

.card.dragging {
  opacity: 0.4;
  transform: rotate(3deg);
}

.card.pri-border-1 { border-left-color: #4CAF50; }
.card.pri-border-2 { border-left-color: #FF9800; }
.card.pri-border-3 { border-left-color: #f44336; }

.card-text {
  font-size: 13px;
  color: #333;
  line-height: 1.5;
  margin-bottom: 8px;
  word-break: break-word;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
  letter-spacing: 0.2px;
}

.tag.pri-1 { background: #e8f5e9; color: #2e7d32; }
.tag.pri-2 { background: #fff3e0; color: #e65100; }
.tag.pri-3 { background: #fce4ec; color: #c62828; }

.tag.due { background: #f0f0f0; color: #666; }
.tag.due.urgent { background: #fff3e0; color: #e65100; font-weight: 600; }

.del-btn {
  margin-left: auto;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  color: #ddd;
  flex-shrink: 0;
  transition: all 0.15s;
}

.del-btn:hover {
  background: #fee2e2;
  color: #c62828;
}

.empty {
  text-align: center;
  padding: 24px 8px;
  color: #ccc;
  font-size: 12px;
}

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #ddd; border-radius: 2px; }
</style>
