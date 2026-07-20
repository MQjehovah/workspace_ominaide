<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import type { Note } from './types'

const props = defineProps<{
  note: Note
  execute: (action: string, args?: unknown) => Promise<unknown>
}>()

const emit = defineEmits<{
  close: []
  updated: [note: Note]
  deleted: [id: string]
}>()

// 编辑状态
const isEditing = ref(false)
const editContent = ref('')

// 进入编辑模式
const startEdit = () => {
  editContent.value = props.note.content
  isEditing.value = true
  nextTick(() => {
    document.getElementById('detail-edit-input')?.focus()
  })
}

// 取消编辑
const cancelEdit = () => {
  isEditing.value = false
  editContent.value = ''
}

// 保存编辑
const saveEdit = async () => {
  if (!editContent.value.trim()) return
  try {
    await props.execute('update', {
      id: props.note.id,
      content: editContent.value.trim(),
    })
    isEditing.value = false
    emit('updated', {
      ...props.note,
      content: editContent.value.trim(),
    })
  } catch (e) {
    console.error('保存失败', e)
  }
}

// 删除笔记
const handleDelete = async () => {
  try {
    await props.execute('delete', { id: props.note.id })
    emit('deleted', props.note.id)
  } catch (e) {
    console.error('删除失败', e)
  }
}

// ESC 关闭
const onKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    if (isEditing.value) {
      cancelEdit()
    } else {
      emit('close')
    }
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
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
</script>

<template>
  <div class="note-detail-overlay" @click.self="emit('close')">
    <div class="note-detail-card">
      <!-- 顶部：标题 + 关闭 -->
      <div class="detail-header">
        <div class="detail-title">
          <svg class="w-4 h-4 text-yellow-500" viewBox="0 0 24 24" fill="currentColor">
            <path d="M19 3H4.99c-1.11 0-1.98.89-1.98 2L3 19c0 1.11.88 2 1.99 2H19c1.1 0 2-.89 2-2V5c0-1.11-.9-2-2-2zM19 15H5V5h14v10z"/>
          </svg>
          <span class="text-sm font-semibold text-gray-800">笔记详情</span>
        </div>
        <button class="detail-close-btn" @click="emit('close')" title="关闭 (ESC)">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6 6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <!-- 时间 + 标签 -->
      <div class="detail-meta">
        <span class="text-xs text-gray-400">{{ formatTime(note.time) }}</span>
        <div v-if="note.tags.length > 0" class="detail-tags">
          <span
            v-for="tag in note.tags"
            :key="tag"
            class="text-xs px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-600"
          >
            {{ tag }}
          </span>
        </div>
      </div>

      <!-- 正文内容 / 编辑框 -->
      <div class="detail-body">
        <div v-if="!isEditing" class="detail-content">{{ note.content }}</div>
        <textarea
          v-else
          id="detail-edit-input"
          v-model="editContent"
          class="detail-edit-input"
          placeholder="输入笔记内容..."
        ></textarea>
      </div>

      <!-- 底部操作栏 -->
      <div class="detail-actions">
        <div class="detail-actions-left">
          <button
            v-if="!isEditing"
            class="action-btn action-btn-edit"
            @click="startEdit"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            编辑
          </button>
          <template v-else>
            <button
              class="action-btn action-btn-save"
              @click="saveEdit"
              :disabled="!editContent.trim()"
            >
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 6 9 17l-5-5"/>
              </svg>
              保存
            </button>
            <button
              class="action-btn action-btn-cancel"
              @click="cancelEdit"
            >
              取消
            </button>
          </template>
        </div>
        <button
          class="action-btn action-btn-delete"
          @click="handleDelete"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          </svg>
          删除
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.note-detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.note-detail-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  width: 100%;
  max-width: 480px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 12px;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: 6px;
}

.detail-close-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
}

.detail-close-btn:hover {
  background: #f3f4f6;
  color: #374151;
}

.detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.detail-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.detail-content {
  font-size: 14px;
  line-height: 1.6;
  color: #374151;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-edit-input {
  width: 100%;
  min-height: 120px;
  padding: 10px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
  color: #374151;
  resize: vertical;
  outline: none;
  box-sizing: border-box;
  font-family: inherit;
}

.detail-edit-input:focus {
  border-color: #eab308;
  box-shadow: 0 0 0 2px rgba(234, 179, 8, 0.15);
}

.detail-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid #f3f4f6;
}

.detail-actions-left {
  display: flex;
  gap: 6px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: background 0.15s;
}

.action-btn-edit {
  background: #f3f4f6;
  color: #374151;
}

.action-btn-edit:hover {
  background: #e5e7eb;
}

.action-btn-save {
  background: #eab308;
  color: #fff;
}

.action-btn-save:hover {
  background: #d97706;
}

.action-btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn-cancel {
  background: #f3f4f6;
  color: #6b7280;
}

.action-btn-cancel:hover {
  background: #e5e7eb;
}

.action-btn-delete {
  background: #fef2f2;
  color: #ef4444;
}

.action-btn-delete:hover {
  background: #fee2e2;
}
</style>
