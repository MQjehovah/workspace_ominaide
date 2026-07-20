<template>
  <div class="notes-page">
    <div class="sidebar">
      <div class="sidebar-hd">
        <span class="sidebar-title">笔记</span>
        <button class="new-btn" @click="createNote">+</button>
      </div>
      <div class="notes-list">
        <div v-for="n in notes" :key="n.id" :class="['note-item', { active: n.id === currentId }]" @click="openNote(n.id)">
          <div class="note-icon">📄</div>
          <div class="note-info">
            <div class="note-title">{{ n.title || '无标题' }}</div>
            <div class="note-date">{{ n.updated_at ? n.updated_at.slice(0, 10) : '' }}</div>
          </div>
        </div>
      </div>
    </div>
    <div class="editor-area" v-if="currentId">
      <input v-model="title" class="title-input" placeholder="无标题" @input="autoSave" />
      <textarea v-model="content" class="content-input" placeholder="开始写点什么..." @input="autoSave"></textarea>
      <div class="editor-footer">
        <span class="save-status">{{ saveStatus }}</span>
        <button class="del-btn" @click="deleteNote">删除</button>
      </div>
    </div>
    <div class="empty-area" v-else>
      <p>选择或创建一篇笔记</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

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
    await window.mqbox?.api.post('/plugins/notes', { title: '无标题', content: '' })
    await loadNotes()
  } catch {}
}

async function openNote(id: number) {
  currentId.value = id
  try {
    const res = await window.mqbox?.api.get(`/plugins/notes/${id}`) || {}
    title.value = res.title || ''
    content.value = res.content || ''
  } catch {}
}

function autoSave() {
  saveStatus.value = '未保存'
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    if (!currentId.value) return
    try {
      await window.mqbox?.api.put(`/plugins/notes/${currentId.value}`, { title: title.value, content: content.value })
      saveStatus.value = '已保存'
      await loadNotes()
    } catch { saveStatus.value = '保存失败' }
  }, 1000)
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
.sidebar { width:220px; border-right:1px solid #e8e8e8; display:flex; flex-direction:column; }
.sidebar-hd { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid #e8e8e8; }
.sidebar-title { font-size:14px; font-weight:600; }
.new-btn { width:28px; height:28px; border-radius:6px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; font-size:18px; display:flex; align-items:center; justify-content:center; }
.new-btn:hover { background:#f5f5f5; }
.notes-list { flex:1; overflow-y:auto; }
.note-item { display:flex; align-items:center; gap:8px; padding:10px 16px; cursor:pointer; border-bottom:1px solid #f5f5f5; }
.note-item:hover { background:#f5f7fa; }
.note-item.active { background:#e3f2fd; }
.note-icon { font-size:16px; }
.note-info { flex:1; min-width:0; }
.note-title { font-size:13px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.note-date { font-size:11px; color:#999; margin-top:2px; }
.editor-area { flex:1; display:flex; flex-direction:column; padding:16px 24px; }
.title-input { font-size:22px; font-weight:700; border:none; outline:none; padding:8px 0; margin-bottom:12px; width:100%; }
.content-input { flex:1; border:none; outline:none; resize:none; font-size:14px; line-height:1.8; font-family:monospace; width:100%; }
.editor-footer { display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-top:1px solid #e8e8e8; margin-top:8px; }
.save-status { font-size:11px; color:#999; }
.del-btn { padding:4px 12px; border-radius:6px; border:1px solid #f56c6c; background:#fff; color:#f56c6c; cursor:pointer; font-size:12px; }
.del-btn:hover { background:#fef0f0; }
.empty-area { flex:1; display:flex; align-items:center; justify-content:center; color:#ccc; font-size:14px; }
</style>
