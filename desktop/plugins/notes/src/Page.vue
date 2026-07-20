<template>
  <div class="notes-page">
    <div class="sidebar">
      <div class="sidebar-hd">
        <span class="sidebar-title">笔记</span>
        <button class="new-btn" @click="createNote">+</button>
      </div>
      <div class="notes-list">
        <div v-for="n in notes" :key="n.id" :class="['note-item', { active: n.id === currentId }]" @click="openNote(n.id)">
          <div class="note-title">{{ n.title || '无标题' }}</div>
          <div class="note-date">{{ n.updated_at ? n.updated_at.slice(0, 10) : '' }}</div>
        </div>
      </div>
    </div>
    <div class="editor-area" v-if="currentId">
      <div class="editor-header">
        <input v-model="title" class="title-input" placeholder="无标题" @input="scheduleSave" />
        <div class="header-actions">
          <span class="save-status">{{ saveStatus }}</span>
          <button class="del-btn" @click="deleteNote">删除</button>
        </div>
      </div>
      <TipTapEditor v-model="content" @update:model-value="scheduleSave" />
    </div>
    <div class="empty-area" v-else>
      <p>选择或创建一篇笔记</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TipTapEditor from './TipTapEditor.vue'

const notes = ref<any[]>([])
const currentId = ref<number | null>(null)
const title = ref('')
const content = ref('')
const saveStatus = ref('')
let saveTimer: any = null

async function loadNotes() {
  try {
    const res = await window.mqbox?.api.get('/plugins/notes') || []
    notes.value = Array.isArray(res) ? res : []
  } catch { notes.value = [] }
}

async function createNote() {
  try {
    const res = await window.mqbox?.api.post('/plugins/notes', { title: '无标题', content: '' })
    if (res?.id) currentId.value = res.id
    title.value = ''
    content.value = ''
    await loadNotes()
  } catch {}
}

async function openNote(id: number) {
  currentId.value = id
  try {
    const res = await window.mqbox?.api.get(`/plugins/notes/${id}`) || {}
    title.value = res.title || ''
    content.value = res.content || ''
    saveStatus.value = ''
  } catch {}
}

function scheduleSave() {
  saveStatus.value = '未保存'
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(doSave, 1500)
}

async function doSave() {
  if (!currentId.value) return
  try {
    await window.mqbox?.api.put(`/plugins/notes/${currentId.value}`, { title: title.value, content: content.value })
    saveStatus.value = '已保存'
    await loadNotes()
  } catch { saveStatus.value = '保存失败' }
}

async function deleteNote() {
  if (!currentId.value || !confirm('确定删除？')) return
  try {
    await window.mqbox?.api.delete(`/plugins/notes/${currentId.value}`)
    currentId.value = null
    title.value = ''
    content.value = ''
    await loadNotes()
  } catch {}
}

onMounted(loadNotes)
</script>

<style scoped>
.notes-page { display:flex; height:100vh; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
.sidebar { width:220px; border-right:1px solid #e8e8e8; display:flex; flex-direction:column; flex-shrink:0; }
.sidebar-hd { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid #e8e8e8; }
.sidebar-title { font-size:14px; font-weight:600; }
.new-btn { width:28px; height:28px; border-radius:6px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; font-size:18px; display:flex; align-items:center; justify-content:center; }
.new-btn:hover { background:#f5f5f5; }
.notes-list { flex:1; overflow-y:auto; }
.note-item { padding:10px 16px; cursor:pointer; border-bottom:1px solid #f5f5f5; }
.note-item:hover { background:#f5f7fa; }
.note-item.active { background:#e3f2fd; }
.note-title { font-size:13px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.note-date { font-size:11px; color:#999; margin-top:2px; }
.editor-area { flex:1; display:flex; flex-direction:column; padding:12px 20px; min-width:0; }
.editor-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; gap:12px; }
.title-input { flex:1; font-size:22px; font-weight:700; border:none; outline:none; padding:4px 0; }
.header-actions { display:flex; align-items:center; gap:8px; flex-shrink:0; }
.save-status { font-size:11px; color:#999; }
.del-btn { padding:4px 12px; border-radius:6px; border:1px solid #f56c6c; background:#fff; color:#f56c6c; cursor:pointer; font-size:12px; }
.del-btn:hover { background:#fef0f0; }
.empty-area { flex:1; display:flex; align-items:center; justify-content:center; color:#ccc; font-size:14px; }
</style>
