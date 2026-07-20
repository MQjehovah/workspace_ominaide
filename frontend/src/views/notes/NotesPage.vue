<template>
  <div class="notes-layout">
    <div class="sidebar-panel">
      <div class="sidebar-header">
        <span class="sidebar-title">笔记</span>
        <el-button size="small" circle :icon="Plus" @click="createNote" />
      </div>
      <div v-if="loading" v-loading="true" style="height:100%" />
      <div v-else class="note-list">
        <TreeNode
          v-for="node in tree"
          :key="node.id"
          :node="node"
          :current-id="currentId"
          :depth="0"
          @select="openNote"
          @create-child="createChildNote"
          @delete="deleteNode"
        />
        <el-empty v-if="!tree.length" description="暂无笔记" :image-size="60" />
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
import TreeNode from './TreeNode.vue'

const tree = ref<any[]>([])
const currentId = ref<number | null>(null)
const noteTitle = ref('')
const noteContent = ref('')
const loading = ref(true)
let saveTimer: ReturnType<typeof setTimeout> | null = null

async function loadTree() {
  try {
    const res = await client.get('/plugins/notes/tree')
    tree.value = res.data
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

function flattenTree(nodes: any[]): any[] {
  const result: any[] = []
  for (const n of nodes) {
    result.push(n)
    if (n.children?.length) result.push(...flattenTree(n.children))
  }
  return result
}

async function createNote() {
  try {
    const res = await client.post('/plugins/notes', { title: '无标题', content: '' })
    if (res.data?.id) {
      currentId.value = res.data.id; noteTitle.value = ''; noteContent.value = ''
    }
    await loadTree()
  } catch (e) { console.error(e) }
}

async function createChildNote(parentId: number) {
  try {
    await client.post('/plugins/notes', { title: '无标题', content: '', parent_id: parentId })
    await loadTree()
  } catch (e) { console.error(e) }
}

async function openNote(id: number) {
  const allNotes = flattenTree(tree.value)
  const note = allNotes.find((n: any) => n.id === id)
  if (note?.is_folder) return
  currentId.value = id
  try {
    const res = await client.get(`/plugins/notes/${id}`)
    const n = res.data
    noteTitle.value = n.title || ''
    noteContent.value = n.content || ''
  } catch (e) { console.error(e) }
}

async function saveNote() {
  if (!currentId.value) return
  try {
    await client.put(`/plugins/notes/${currentId.value}`, {
      title: noteTitle.value, content: noteContent.value,
    })
    await loadTree()
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
    currentId.value = null; noteTitle.value = ''; noteContent.value = ''
    await loadTree()
  } catch (e) { console.error(e) }
}

async function deleteNode(id: number) {
  try {
    await client.delete(`/plugins/notes/${id}`)
    if (currentId.value === id) { currentId.value = null; noteTitle.value = ''; noteContent.value = '' }
    await loadTree()
  } catch (e) { console.error(e) }
}

onMounted(loadTree)
</script>

<style scoped>
.notes-layout { display: flex; height: calc(100vh - 120px); gap: 16px; }
.sidebar-panel { width: 240px; flex-shrink: 0; border: 1px solid #dcdfe6; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #dcdfe6; }
.sidebar-title { font-size: 14px; font-weight: 600; }
.note-list { flex: 1; overflow-y: auto; }
.editor-panel { flex: 1; display: flex; flex-direction: column; gap: 12px; }
.editor-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.title-input :deep(.el-input__inner) { font-size: 24px; font-weight: 700; border: none; padding-left: 0; }
.empty-state { flex: 1; display: flex; align-items: center; justify-content: center; }
</style>
