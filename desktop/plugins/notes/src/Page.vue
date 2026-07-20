<script setup lang="ts">
import { ref, onMounted } from 'vue'

const { data, execute, close, refresh } = defineProps<{
  data: any; execute: Function; close: Function; refresh: Function
}>()

const notes = ref<any[]>([])
const content = ref('')
const title = ref('')
const currentId = ref<number | null>(null)

async function loadNotes() {
  try {
    const res = await window.mqbox?.api.get('/plugins/notes') || []
    notes.value = res || []
  } catch { notes.value = [] }
}

async function openNote(id: number) {
  currentId.value = id
  try {
    const res = await window.mqbox?.api.get(`/plugins/notes/${id}`) || {}
    title.value = res.title || ''
    content.value = res.content || ''
  } catch {}
}

async function createNote() {
  try {
    await window.mqbox?.api.post('/plugins/notes', { title: '无标题', content: '' })
    loadNotes()
  } catch {}
}

onMounted(loadNotes)
</script>

<template>
  <div class="page">
    <div class="sidebar">
      <div class="sidebar-hd">
        <h3>笔记</h3>
        <button class="add-btn" @click="createNote">+</button>
      </div>
      <div class="note-list">
        <div v-for="n in notes" :key="n.id" :class="['note-item', { active: n.id === currentId }]" @click="openNote(n.id)">
          <div class="note-title">{{ n.title || '无标题' }}</div>
        </div>
      </div>
    </div>
    <div class="editor">
      <template v-if="currentId">
        <input v-model="title" class="title-input" placeholder="无标题" />
        <textarea v-model="content" class="content-input" placeholder="开始写点什么..."></textarea>
      </template>
      <div v-else class="empty">选择一篇笔记</div>
    </div>
  </div>
</template>

<style scoped>
.page { display:flex; height:100vh; }
.sidebar { width:200px; border-right:1px solid #e8e8e8; display:flex; flex-direction:column; }
.sidebar-hd { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid #e8e8e8; }
.sidebar-hd h3 { margin:0; font-size:14px; }
.add-btn { width:28px; height:28px; border-radius:6px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; font-size:16px; }
.add-btn:hover { background:#f5f5f5; }
.note-list { flex:1; overflow-y:auto; }
.note-item { padding:8px 16px; cursor:pointer; font-size:13px; border-bottom:1px solid #f5f5f5; }
.note-item:hover { background:#f5f7fa; }
.note-item.active { background:#e3f2fd; color:#2196F3; }
.note-title { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.editor { flex:1; display:flex; flex-direction:column; padding:16px 20px; }
.title-input { font-size:22px; font-weight:700; border:none; outline:none; padding:8px 0; margin-bottom:12px; }
.content-input { flex:1; border:none; outline:none; resize:none; font-size:14px; line-height:1.7; font-family:monospace; }
.empty { flex:1; display:flex; align-items:center; justify-content:center; color:#ccc; }
</style>
