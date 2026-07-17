<template>
  <div class="notes-layout">
    <div class="sidebar-panel">
      <div class="sidebar-header">
        <span class="sidebar-title">笔记</span>
        <el-button size="small" circle :icon="Plus" @click="createNote" />
      </div>
      <div v-if="loading" v-loading="true" style="height:100%" />
      <div v-else class="note-list">
        <div v-for="note in notes" :key="note.id"
          class="note-item"
          :class="{ active: note.id === currentId }"
          @click="openNote(note.id)">
          <div class="note-item-title">{{ note.title || '无标题' }}</div>
          <div class="note-item-date">{{ formatDate(note.updated_at) }}</div>
        </div>
        <el-empty v-if="!notes.length" description="暂无笔记" :image-size="60" />
      </div>
    </div>
    <div class="editor-panel" v-if="currentId">
      <div class="editor-header">
        <el-input v-model="noteTitle" placeholder="无标题" class="title-input" @input="autoSave" />
        <div style="display:flex;gap:8px">
          <el-button size="small" type="primary" @click="saveNote">保存</el-button>
          <el-popconfirm title="确定删除？" @confirm="deleteNote">
            <template #reference>
              <el-button size="small" type="danger" plain>删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>
      <TipTapEditor v-model="noteContent" @update:model-value="autoSave" placeholder="开始写点什么..." min-height="400px" />
    </div>
    <div v-else class="empty-state">
      <el-empty description="选择或创建一篇笔记" :image-size="80" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import client from '@/api/client'
import TipTapEditor from './TipTapEditor.vue'

interface Note {
  id: number; title: string; content: string | null
  updated_at: string; created_at: string
}

const notes = ref<Note[]>([])
const currentId = ref<number | null>(null)
const noteTitle = ref('')
const noteContent = ref('')
const loading = ref(true)
let saveTimer: ReturnType<typeof setTimeout> | null = null

async function loadNotes() {
  try {
    const res = await client.get('/plugins/notes')
    notes.value = res.data
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

async function createNote() {
  try {
    const res = await client.post('/plugins/notes', { title: '无标题', content: '' })
    const note = res.data as Note
    currentId.value = note.id
    noteTitle.value = ''
    noteContent.value = ''
    await loadNotes()
  } catch (e) { console.error(e) }
}

async function openNote(id: number) {
  currentId.value = id
  try {
    const res = await client.get(`/plugins/notes/${id}`)
    const note = res.data as Note
    noteTitle.value = note.title || ''
    noteContent.value = note.content || ''
  } catch (e) { console.error(e) }
}

async function saveNote() {
  if (!currentId.value) return
  try {
    await client.put(`/plugins/notes/${currentId.value}`, {
      title: noteTitle.value, content: noteContent.value,
    })
    await loadNotes()
  } catch (e) { console.error(e) }
}

function autoSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(saveNote, 2000)
}

async function deleteNote() {
  if (!currentId.value) return
  try {
    await client.delete(`/plugins/notes/${currentId.value}`)
    currentId.value = null
    await loadNotes()
  } catch (e) { console.error(e) }
}

function formatDate(date: string) {
  if (!date) return ''
  return new Date(date).toLocaleDateString()
}

onMounted(loadNotes)
</script>

<style scoped>
.notes-layout { display: flex; height: calc(100vh - 120px); gap: 16px; }
.sidebar-panel { width: 240px; flex-shrink: 0; border: 1px solid #dcdfe6; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #dcdfe6; }
.sidebar-title { font-size: 14px; font-weight: 600; }
.note-list { flex: 1; overflow-y: auto; }
.note-item { padding: 10px 16px; cursor: pointer; border-bottom: 1px solid #f0f0f0; transition: background 0.15s; }
.note-item:hover { background: #f5f7fa; }
.note-item.active { background: #ecf5ff; }
.note-item-title { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.note-item-date { font-size: 11px; color: #c0c4cc; margin-top: 2px; }
.editor-panel { flex: 1; display: flex; flex-direction: column; gap: 12px; }
.editor-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.title-input :deep(.el-input__inner) { font-size: 24px; font-weight: 700; border: none; padding-left: 0; }
.empty-state { flex: 1; display: flex; align-items: center; justify-content: center; }
</style>
