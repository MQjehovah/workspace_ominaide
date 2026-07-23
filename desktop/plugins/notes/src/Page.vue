<template>
  <div class="notes-page">
    <div class="sidebar">
      <div class="sidebar-hd">
        <span class="sidebar-title">笔记</span>
        <button class="new-btn" title="新建笔记" @click="createNote">+</button>
      </div>
      <div class="notes-list">
        <TreeNode
          v-for="node in tree"
          :key="node.id"
          :node="node"
          :current-id="currentId"
          :depth="0"
          @select="openNote"
          @create-child="(id) => createChildNote(id)"
          @delete="deleteNode"
          @move="handleMove"
        />
        <div v-if="tree.length === 0" style="padding:16px;color:#999;font-size:12px">暂无笔记</div>
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
      <TipTapEditor :key="currentId" v-model="content" @update:model-value="scheduleSave" />
    </div>
    <div class="empty-area" v-else>
      <p>选择或创建一篇笔记</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TipTapEditor from './TipTapEditor.vue'
import TreeNode from './TreeNode.vue'

const tree = ref<any[]>([])
const currentId = ref<number | null>(null)
const title = ref('')
const content = ref('')
const saveStatus = ref('')
let saveTimer: any = null

async function loadTree() {
  try {
    const res = await window.mqbox?.api.get('/plugins/notes/tree') || []
    tree.value = Array.isArray(res) ? res : []
  } catch { tree.value = [] }
}

async function createNote() {
  try {
    const res = await window.mqbox?.api.post('/plugins/notes', {
      title: '无标题', content: '',
    })
    if (res?.id) {
      currentId.value = res.id
      title.value = ''; content.value = ''
    }
    await loadTree()
  } catch {}
}

async function createChildNote(parentId: number) {
  try {
    const res = await window.mqbox?.api.post('/plugins/notes', {
      title: '无标题', content: '', parent_id: parentId,
    })
    console.log('createChild response:', res)
    await loadTree()
  } catch (e) { console.error('createChild error:', e) }
}

async function openNote(id: number) {
  const allNotes = flattenTree(tree.value)
  const note = allNotes.find((n: any) => n.id === id)
  if (note?.is_folder) return
  currentId.value = id
  try {
    const res = await window.mqbox?.api.get(`/plugins/notes/${id}`) || {}
    title.value = res.title || ''
    content.value = res.content || ''
    saveStatus.value = ''
  } catch {}
}

function flattenTree(nodes: any[]): any[] {
  const result: any[] = []
  for (const n of nodes) {
    result.push(n)
    if (n.children?.length) result.push(...flattenTree(n.children))
  }
  return result
}

function findNodePath(nodes: any[], id: number): any[] {
  for (const n of nodes) {
    if (n.id === id) return [n]
    if (n.children?.length) {
      const path = findNodePath(n.children, id)
      if (path.length) return [n, ...path]
    }
  }
  return []
}

async function handleMove(sourceId: number, targetId: number, position: 'before' | 'after' | 'inside') {
  const all = flattenTree(tree.value)
  const target = all.find((n: any) => n.id === targetId)
  if (!target) return
  const source = all.find((n: any) => n.id === sourceId)
  if (!source) return

  let parentId: number | null = null
  let sortOrder = 0

  if (position === 'inside') {
    parentId = target.id
    const siblings = (target.children || [])
    sortOrder = siblings.length > 0 ? Math.max(...siblings.map((s: any) => s.sort_order || 0)) + 1 : 0
  } else if (position === 'before') {
    parentId = target.parent_id
    const siblings = findSiblings(tree.value, target.parent_id) || []
    const idx = siblings.indexOf(target)
    if (idx > 0) {
      sortOrder = siblings[idx - 1].sort_order + Math.round((target.sort_order - siblings[idx - 1].sort_order) / 2)
    } else {
      sortOrder = (target.sort_order || 0) - 1
    }
  } else {
    parentId = target.parent_id
    const siblings = findSiblings(tree.value, target.parent_id) || []
    const idx = siblings.indexOf(target)
    if (idx < siblings.length - 1) {
      sortOrder = target.sort_order + Math.round((siblings[idx + 1].sort_order - target.sort_order) / 2)
    } else {
      sortOrder = (target.sort_order || 0) + 1
    }
  }

  try {
    await window.mqbox?.api.post(`/plugins/notes/${sourceId}/move`, { parent_id: parentId, sort_order: sortOrder })
    await loadTree()
  } catch (e) {
    console.error('move failed', e)
  }
}

function findSiblings(nodes: any[], parentId: number | null): any[] | null {
  if (parentId === null) return tree.value
  for (const n of nodes) {
    if (n.id === parentId) return n.children || []
    if (n.children?.length) {
      const found = findSiblings(n.children, parentId)
      if (found !== null) return found
    }
  }
  return null
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
    await loadTree()
  } catch { saveStatus.value = '保存失败' }
}

async function deleteNote() {
  if (!currentId.value || !confirm('确定删除？')) return
  try {
    await window.mqbox?.api.delete(`/plugins/notes/${currentId.value}`)
    currentId.value = null; title.value = ''; content.value = ''
    await loadTree()
  } catch {}
}

async function deleteNode(id: number) {
  if (!confirm('确定删除？')) return
  try {
    await window.mqbox?.api.delete(`/plugins/notes/${id}`)
    if (currentId.value === id) { currentId.value = null; title.value = ''; content.value = '' }
    await loadTree()
  } catch {}
}

onMounted(loadTree)
</script>

<style scoped>
.notes-page { display:flex; height:100vh; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
.sidebar { width:220px; border-right:1px solid #e8e8e8; display:flex; flex-direction:column; flex-shrink:0; }
.sidebar-hd { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid #e8e8e8; }
.sidebar-title { font-size:14px; font-weight:600; }
.new-btn { width:28px; height:28px; border-radius:6px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; font-size:14px; display:flex; align-items:center; justify-content:center; }
.new-btn:hover { background:#f5f5f5; }
.notes-list { flex:1; overflow-y:auto; }
.editor-area { flex:1; display:flex; flex-direction:column; padding:12px 20px; min-width:0; }
.editor-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; gap:12px; }
.title-input { flex:1; font-size:22px; font-weight:700; border:none; outline:none; padding:4px 0; }
.header-actions { display:flex; align-items:center; gap:8px; flex-shrink:0; }
.save-status { font-size:11px; color:#999; }
.del-btn { padding:4px 12px; border-radius:6px; border:1px solid #f56c6c; background:#fff; color:#f56c6c; cursor:pointer; font-size:12px; }
.del-btn:hover { background:#fef0f0; }
.empty-area { flex:1; display:flex; align-items:center; justify-content:center; color:#ccc; font-size:14px; }
</style>
