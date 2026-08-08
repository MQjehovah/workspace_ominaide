<template>
  <div class="notes-page">
    <div class="sidebar">
      <div class="sidebar-hd">
        <span class="sidebar-title">笔记</span>
        <button class="new-btn" title="新建笔记" @click="createNote">+</button>
      </div>
      <div class="quick-capture">
        <input
          v-model="quickText"
          class="quick-input"
          placeholder="快速记录… Enter 保存"
          @keyup.enter="quickAdd"
        />
        <button v-if="quickText" class="quick-ai" title="AI 扩写成完整笔记" @click="quickAi">✨</button>
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
        <input v-model="title" class="title-input" placeholder="无标题" @input="markDirty" />
        <div class="header-actions">
          <span class="save-status" :class="{ dirty: saveStatus === '未保存' }">{{ saveStatus }}</span>
          <button class="save-btn" :disabled="!currentId" @click="exportMarkdown" title="导出为 Markdown">导出</button>
          <button class="save-btn" :disabled="!currentId" @click="openHistory" title="版本历史">历史</button>
          <button class="save-btn" :disabled="!currentId" @click="doSave">保存 (Ctrl+S)</button>
          <button class="del-btn" @click="deleteNote">删除</button>
        </div>
      </div>
      <TipTapEditor ref="editorRef" :key="currentId" v-model="content" @update:model-value="markDirty" @open-note="openEmbeddedNote" />
    </div>
    <div class="empty-area" v-else>
      <p>选择或创建一篇笔记</p>
    </div>

    <div v-if="historyOpen" class="history-overlay" @click.self="historyOpen = false">
      <div class="history-modal">
        <div class="history-hd">
          <span>版本历史</span>
          <button class="history-close" @click="historyOpen = false">✕</button>
        </div>
        <div class="history-body">
          <div v-if="versions.length === 0" class="history-empty">暂无历史版本</div>
          <div v-for="v in versions" :key="v.id" class="history-item" :class="{ active: v.id === selectedVersion?.id }" @click="loadVersion(v)">
            <div class="history-ver">v{{ v.version }}</div>
            <div class="history-main">
              <div class="history-title">{{ v.title || '无标题' }}</div>
              <div class="history-time">{{ fmtVersionTime(v.created_at) }}</div>
            </div>
            <button class="history-restore" @click.stop="restoreVersion(v)">恢复</button>
          </div>
        </div>
        <div v-if="selectedVersion" class="history-preview">
          <div class="history-preview-hd">预览 v{{ selectedVersion.version }} <button class="history-restore" @click="restoreVersion(selectedVersion)">恢复此版本</button></div>
          <div class="history-preview-body">{{ selectedVersion.text }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import TipTapEditor from './TipTapEditor.vue'
import TreeNode from './TreeNode.vue'

const tree = ref<any[]>([])
const currentId = ref<number | null>(null)
const title = ref('')
const content = ref('')
const editorRef = ref<any>(null)
const saveStatus = ref('')
let hideSaveTimer: any = null
let suppressDirty = false
const historyOpen = ref(false)
const versions = ref<any[]>([])
const selectedVersion = ref<any>(null)

function fmtVersionTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function openHistory() {
  if (!currentId.value) return
  historyOpen.value = true
  selectedVersion.value = null
  try {
    const res = await window.mqbox?.api.get(`/plugins/notes/${currentId.value}/versions`) || { versions: [] }
    versions.value = res.versions || []
  } catch (e) {
    console.error('[notes] load versions failed:', e)
    versions.value = []
  }
}

async function loadVersion(v: any) {
  if (!currentId.value) return
  try {
    const res = await window.mqbox?.api.get(`/plugins/notes/${currentId.value}/versions/${v.id}`) || {}
    selectedVersion.value = { ...res, version: v.version, text: res.content || '' }
  } catch (e) {
    console.error('[notes] load version failed:', e)
  }
}

async function restoreVersion(v: any) {
  if (!currentId.value || !confirm(`确定恢复到 v${v.version}?当前内容会先保存为历史版本。`)) return
  try {
    const res = await window.mqbox?.api.post(`/plugins/notes/${currentId.value}/versions/${v.id}/restore`, {})
    if (res?.content !== undefined) {
      title.value = res.title || ''
      content.value = res.content || ''
      historyOpen.value = false
      showSaved()
    }
  } catch (e) {
    console.error('[notes] restore version failed:', e)
  }
}

function showSaved() {
  saveStatus.value = '已保存'
  if (hideSaveTimer) clearTimeout(hideSaveTimer)
  hideSaveTimer = setTimeout(() => { saveStatus.value = '' }, 2000)
}

async function doSave() {
  if (!currentId.value) return
  const mq = (window as any).mqbox
  if (!mq?.api) {
    console.error('[notes] mqbox.api unavailable')
    saveStatus.value = '保存失败: API 不可用'
    return
  }
  // Authoritative content source: native TipTap JSON read directly from the editor.
  let toSave = content.value
  try {
    if (editorRef.value?.getJSONContent) {
      const fromEditor = editorRef.value.getJSONContent()
      if (fromEditor || !content.value) toSave = fromEditor
    }
  } catch (e) {
    console.warn('[notes] getJSONContent failed, using content.value:', e)
  }
  try {
    const res = await mq.api.put(`/plugins/notes/${currentId.value}`, { title: title.value, content: toSave })
    console.log('[notes] save OK, resp:', res?.id || res)
    if (editorRef.value?.getJSONContent) content.value = toSave
    showSaved()
    await loadTree()
  } catch (e) {
    console.error('[notes] save failed:', e)
    saveStatus.value = '保存失败: ' + ((e as any)?.message || String(e))
  }
}

function exportMarkdown() {
  if (!editorRef.value?.getMarkdown) return
  const md = editorRef.value.getMarkdown()
  if (!md) { saveStatus.value = '内容为空'; return }
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = (title.value || '笔记') + '.md'
  a.click()
  URL.revokeObjectURL(url)
  showSaved()
}

function scheduleSave() {
  // kept for compat: just marks dirty, manual save via button / Ctrl+S
  markDirty()
}

function markDirty() {
  if (suppressDirty) return
  saveStatus.value = '未保存'
}

function handleKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    doSave()
  }
}

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
      suppressDirty = true
      currentId.value = res.id
      title.value = ''; content.value = ''
      saveStatus.value = ''
      setTimeout(() => { suppressDirty = false }, 300)
    }
    await loadTree()
  } catch {}
}

// ---- Quick capture (merged from quick-notes) ----
const quickText = ref('')
const quickLoading = ref(false)

async function quickAdd() {
  const text = quickText.value.trim()
  if (!text || quickLoading.value) return
  quickLoading.value = true
  try {
    const res = await window.mqbox?.api.post('/plugins/notes', { title: text, content: '' })
    if (res?.id) {
      await openNote(res.id)
      quickText.value = ''
    }
    await loadTree()
  } catch (e) {
    console.error('[notes] quick add failed:', e)
  }
  quickLoading.value = false
}

async function quickAi() {
  const text = quickText.value.trim()
  if (!text || quickLoading.value) return
  quickLoading.value = true
  try {
    const chat = await window.mqbox?.api.post('/chat', {
      message: `请把下面这条灵感/想法扩写成一篇有条理、内容充实的笔记（用中文，Markdown 格式，包含小标题）。\n\n灵感：${text}`,
    })
    const content = chat?.reply || text
    const res = await window.mqbox?.api.post('/plugins/notes', { title: text.slice(0, 30), content })
    if (res?.id) {
      await openNote(res.id)
      quickText.value = ''
    }
    await loadTree()
  } catch (e) {
    console.error('[notes] AI expand failed:', e)
    // Fallback: save as plain note
    await quickAdd()
  }
  quickLoading.value = false
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
  suppressDirty = true
  currentId.value = id
  try {
    const res = await window.mqbox?.api.get(`/plugins/notes/${id}`) || {}
    title.value = res.title || ''
    content.value = res.content || ''
    saveStatus.value = ''
  } catch (e) {
    console.error('[notes] open note failed:', e)
    saveStatus.value = '加载失败'
  } finally {
    // allow dirty marking again after the editor finished applying content
    setTimeout(() => { suppressDirty = false }, 300)
  }
}

function flattenTree(nodes: any[]): any[] {
  const result: any[] = []
  for (const n of nodes) {
    result.push(n)
    if (n.children?.length) result.push(...flattenTree(n.children))
  }
  return result
}

function openEmbeddedNote(id: number) {
  const all = flattenTree(tree.value)
  const note = all.find((n: any) => n.id === id)
  if (note) {
    openNote(id)
  } else {
    // note not in tree (folder or missing) — still try to open
    openNote(id)
  }
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

window.addEventListener('beforeunload', () => {
  if (currentId.value && saveStatus.value === '未保存') {
    // Do not auto-save; rely on manual save. (Auto-save was causing lost content.)
  }
})

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

onMounted(() => {
  loadTree()
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.notes-page { display:flex; height:100vh; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }
.sidebar { width:220px; border-right:1px solid #e8e8e8; display:flex; flex-direction:column; flex-shrink:0; }
.sidebar-hd { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid #e8e8e8; }
.new-btn { width:28px; height:28px; border-radius:6px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; font-size:14px; display:flex; align-items:center; justify-content:center; }
.new-btn:hover { background:#f5f5f5; }
.quick-capture { display:flex; align-items:center; gap:6px; padding:8px 12px; }
.quick-input { flex:1; min-width:0; padding:6px 10px; border:1px solid #e0e0e0; border-radius:6px; font-size:12px; outline:none; }
.quick-input:focus { border-color:#6366f1; }
.quick-ai { flex-shrink:0; width:26px; height:26px; border:none; border-radius:6px; background:linear-gradient(135deg,#6366f1,#a855f7); color:#fff; cursor:pointer; font-size:13px; display:flex; align-items:center; justify-content:center; }
.quick-ai:hover { filter:brightness(1.1); }
.notes-list { flex:1; overflow-y:auto; }
.editor-area { flex:1; display:flex; flex-direction:column; padding:12px 20px; min-width:0; }
.editor-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; gap:12px; }
.title-input { flex:1; font-size:22px; font-weight:700; border:none; outline:none; padding:4px 0; }
.header-actions { display:flex; align-items:center; gap:8px; flex-shrink:0; }
.save-status { font-size:11px; color:#67c23a; transition:opacity 0.3s; }
.save-status.dirty { color:#e6a23c; }
.save-btn { padding:4px 12px; border-radius:6px; border:1px solid #409eff; background:#ecf5ff; color:#409eff; cursor:pointer; font-size:12px; }
.save-btn:hover { background:#d9ecff; }
.del-btn { padding:4px 12px; border-radius:6px; border:1px solid #f56c6c; background:#fff; color:#f56c6c; cursor:pointer; font-size:12px; }
.del-btn:hover { background:#fef0f0; }
.history-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.35); z-index:100; display:flex; align-items:center; justify-content:center; }
.history-modal { width:560px; max-width:90vw; max-height:80vh; background:#fff; border-radius:12px; display:flex; flex-direction:column; overflow:hidden; box-shadow:0 12px 40px rgba(0,0,0,0.2); }
.history-hd { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid #e5e7eb; font-weight:600; }
.history-close { border:none; background:transparent; cursor:pointer; font-size:16px; color:#9ca3af; }
.history-body { flex:1; overflow-y:auto; padding:8px; min-height:120px; }
.history-empty { text-align:center; color:#9ca3af; padding:30px; font-size:13px; }
.history-item { display:flex; align-items:center; gap:10px; padding:8px 10px; border-radius:8px; cursor:pointer; }
.history-item:hover { background:#f3f4f6; }
.history-item.active { background:#e0f2fe; }
.history-ver { font-size:11px; font-weight:700; color:#3b82f6; background:#eff6ff; border-radius:6px; padding:2px 6px; flex-shrink:0; }
.history-main { flex:1; min-width:0; }
.history-title { font-size:13px; color:#374151; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.history-time { font-size:11px; color:#9ca3af; margin-top:2px; }
.history-restore { padding:4px 10px; border:1px solid #3b82f6; background:#eff6ff; color:#3b82f6; border-radius:6px; font-size:12px; cursor:pointer; flex-shrink:0; }
.history-restore:hover { background:#dbeafe; }
.history-preview { border-top:1px solid #e5e7eb; max-height:240px; display:flex; flex-direction:column; }
.history-preview-hd { display:flex; justify-content:space-between; align-items:center; padding:8px 16px; font-size:12px; color:#6b7280; }
.history-preview-body { flex:1; overflow-y:auto; padding:8px 16px 16px; font-size:13px; color:#374151; white-space:pre-wrap; word-break:break-word; }
.empty-area { flex:1; display:flex; align-items:center; justify-content:center; color:#ccc; font-size:14px; }
</style>
