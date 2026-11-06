<template>
  <div class="notes-page">
    <header class="notes-topbar">
      <div class="notes-heading">
        <el-button class="notes-list-toggle" text circle :icon="Menu" @click="mobileListOpen = true" />
        <div>
          <div class="notes-title">笔记</div>
          <div class="notes-sub">{{ treeCount }} 个节点 · 拖动可排序/分层</div>
        </div>
      </div>
      <div class="notes-actions">
        <el-dropdown trigger="click" @command="handleImportCommand">
          <el-button :icon="Upload">导入</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="file">上传文档 / 音频</el-dropdown-item>
              <el-dropdown-item command="url">从网页导入</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button :icon="Search" @click="openRag('search')">语义搜索</el-button>
        <el-button type="primary" :icon="ChatDotRound" @click="openRag('ask')">知识库问答</el-button>
        <el-dropdown trigger="click" @command="handleMoreCommand">
          <el-button :icon="MoreFilled" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="reindex" :icon="Refresh">重建索引</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <div class="notes-body">
      <div v-if="isMobile && mobileListOpen" class="notes-backdrop" @click="mobileListOpen = false" />
      <aside class="notes-sidebar" :class="{ 'mobile-open': isMobile && mobileListOpen }">
        <div class="sidebar-top">
          <div class="sidebar-title-row">
            <span>全部笔记</span>
            <div class="sidebar-tools">
              <el-tooltip content="新建文件夹" placement="bottom">
                <el-button text circle :icon="FolderAdd" @click="createFolder" />
              </el-tooltip>
              <el-tooltip content="新建笔记" placement="bottom">
                <el-button text circle :icon="Plus" @click="createNote" />
              </el-tooltip>
            </div>
          </div>
          <el-input
            v-model="sidebarQuery"
            placeholder="搜索标题或内容"
            clearable
            :prefix-icon="Search"
            @input="onSidebarSearch"
          />
        </div>

        <div class="note-list" v-loading="loading || noteSearchLoading">
          <template v-if="sidebarQuery.trim()">
            <div
              v-for="n in noteSearchResults"
              :key="n.id"
              class="search-result"
              :class="{ active: currentId === n.id }"
              @click="openSearchResult(n)"
            >
              <div class="search-result-title">{{ n.title || '无标题' }}</div>
              <div class="search-result-meta">{{ fmtDate(n.updated_at) }}</div>
            </div>
            <el-empty v-if="!noteSearchLoading && !noteSearchResults.length" description="没有匹配的笔记" :image-size="50" />
          </template>
          <template v-else>
            <TreeNode
              v-for="node in tree"
              :key="node.id"
              :node="node"
              :current-id="currentId"
              :depth="0"
              @select="openNote"
              @create-child="createChildNote"
              @delete="deleteNode"
              @move="handleMove"
            />
            <el-empty v-if="!tree.length" description="暂无笔记" :image-size="60" />
          </template>
        </div>

        <div class="sidebar-foot">{{ treeCount }} 个节点 · 拖动可排序/分层</div>
      </aside>

      <main class="notes-main" v-if="currentId">
        <div class="note-head">
          <div class="note-title-block">
            <el-input v-model="noteTitle" placeholder="无标题" class="title-input" @input="autoSave" />
            <div class="note-meta">
              <span>{{ saveStatus }}</span>
              <span>{{ noteCharCount }} 字</span>
            </div>
          </div>
          <div class="note-actions">
            <el-button text :icon="ChatDotRound" @click="commentsOpen = true">评论</el-button>
            <el-button text :icon="Clock" @click="openHistory">历史</el-button>
            <el-button text :icon="Download" @click="exportMarkdown">导出</el-button>
            <el-button type="primary" @click="saveNote">保存</el-button>
            <el-dropdown trigger="click" @command="(cmd: string) => handleMoreCommand(cmd, true)">
              <el-button text :icon="MoreFilled" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="rag-ask" :icon="ChatDotRound">知识库问答</el-dropdown-item>
                  <el-dropdown-item command="rag-search" :icon="Search">语义搜索</el-dropdown-item>
                  <el-dropdown-item command="delete" :icon="Delete" divided>删除笔记</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
        <div class="note-editor-shell">
          <div v-if="noteLoading" class="note-loading">
            <span class="note-spinner"></span>
            加载笔记…
          </div>
          <TipTapEditor ref="editorRef" :key="currentId" v-model="noteContent" @update:model-value="autoSave" />
        </div>
      </main>

      <main v-else class="notes-empty">
        <el-empty description="选择一篇笔记，或新建开始">
          <el-button type="primary" :icon="Plus" @click="createNote">新建笔记</el-button>
        </el-empty>
      </main>
    </div>

    <input
      ref="fileInputRef"
      type="file"
      class="hidden-file"
      accept=".pdf,.docx,.xlsx,.xlsm,.pptx,.txt,.md,.markdown,.html,.htm,.mp3,.wav,.m4a,.aac,.flac,.ogg,.webm,.mp4"
      @change="onFileInput"
    />

    <el-drawer v-model="ragOpen" :title="ragMode === 'ask' ? '知识库问答' : '语义搜索'" size="520px">
      <div class="rag-panel">
        <el-input
          v-model="ragQuery"
          :type="ragMode === 'ask' ? 'textarea' : 'text'"
          :rows="ragMode === 'ask' ? 3 : 1"
          :placeholder="ragMode === 'ask' ? '问一个问题，例如：Q3 预算的结论是什么？' : '输入关键词或自然语言描述'"
          @keyup.enter.exact="runRag"
        />
        <el-button type="primary" :loading="ragLoading" style="width:100%" @click="runRag">
          {{ ragMode === 'ask' ? '基于我的笔记回答' : '搜索笔记' }}
        </el-button>

        <template v-if="ragMode === 'ask'">
          <div v-if="ragAnswer" class="rag-answer">{{ ragAnswer }}</div>
          <div v-if="ragSources.length" class="rag-sources">
            <div class="rag-section-title">参考来源</div>
            <div v-for="s in ragSources" :key="s.index" class="rag-source" @click="openSource(s.note_id)">
              <div style="display:flex;gap:6px">
                <span class="rag-index">[{{ s.index }}]</span>
                <span class="rag-source-title">{{ s.title }}</span>
                <span class="rag-score">{{ Math.round((s.score || 0) * 100) }}%</span>
              </div>
              <div class="rag-quote" :title="s.context || ''">{{ s.content || s.snippet }}</div>
            </div>
          </div>
        </template>

        <template v-else>
          <div v-if="ragResults.length" class="rag-results">
            <div v-for="r in ragResults" :key="r.note_id" class="rag-result" @click="openSource(r.note_id)">
              <div class="rag-result-head">
                <span class="rag-source-title">{{ r.title }}</span>
                <span class="rag-score">{{ Math.round((r.score || 0) * 100) }}%</span>
              </div>
              <div class="rag-snippet">{{ r.snippet }}</div>
              <div class="rag-tags">
                <el-tag v-for="t in r.sources" :key="t" size="small">{{ t }}</el-tag>
              </div>
            </div>
          </div>
          <el-empty v-else-if="ragSearched" description="没有找到相关笔记" :image-size="60" />
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="urlOpen" title="从网页导入" width="520px">
      <el-input v-model="urlInput" placeholder="https://example.com/article" clearable />
      <div style="color:#909399;font-size:12px;margin-top:8px">
        支持普通网页和 PDF 链接；正文会保存为笔记并自动进入知识库索引。
      </div>
      <template #footer>
        <el-button @click="urlOpen = false">取消</el-button>
        <el-button type="primary" :loading="urlImporting" @click="importUrl">导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="historyOpen" title="历史版本" width="640px">
      <el-table :data="versions" v-loading="versionLoading" size="small" max-height="420">
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column prop="title" label="标题" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" width="180" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" text @click="previewVersion(row)">查看</el-button>
            <el-button size="small" text type="warning" @click="restoreVersion(row)">恢复</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!versionLoading && !versions.length" description="还没有历史版本" :image-size="60" />
    </el-dialog>

    <el-dialog v-model="versionPreviewOpen" :title="versionPreview ? '版本 ' + versionPreview.version : '版本预览'" width="720px">
      <div v-if="versionPreview" style="max-height:65vh;overflow:auto">
        <div style="font-weight:600;margin-bottom:8px">{{ versionPreview.title }}</div>
        <pre class="version-pre">{{ versionPreview.content }}</pre>
      </div>
    </el-dialog>

    <ObjectCommentsDrawer
      v-model="commentsOpen"
      type="note"
      :object-id="currentId || 0"
      :title="noteTitle || '笔记评论'"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ChatDotRound, Clock, Delete, Download, FolderAdd, Link, Menu, MoreFilled, Plus, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'
import TipTapEditor from './TipTapEditor.vue'
import TreeNode from './TreeNode.vue'
import ObjectCommentsDrawer from '@/components/ObjectCommentsDrawer.vue'

function fmtDate(value?: string | null) {
  return value ? formatBackendDate(value) : ''
}

const tree = ref<any[]>([])
const currentId = ref<number | null>(null)
const noteTitle = ref('')
const noteContent = ref('')
const commentsOpen = ref(false)
const loading = ref(true)
const noteLoading = ref(false)
const noteCache = new Map<number, { title: string; content: string }>()
let openSeq = 0
const saveStatus = ref('已保存')
const editorRef = ref<any>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const sidebarQuery = ref('')
const noteSearchResults = ref<any[]>([])
const noteSearchLoading = ref(false)
const isMobile = ref(false)
const mobileListOpen = ref(false)
let sidebarSearchTimer: ReturnType<typeof setTimeout> | null = null
let saveTimer: ReturnType<typeof setTimeout> | null = null

// ---- Notes RAG ----
const ragOpen = ref(false)
const ragMode = ref<'search' | 'ask'>('search')
const ragQuery = ref('')
const ragLoading = ref(false)
const ragAnswer = ref('')
const ragSources = ref<any[]>([])
const ragResults = ref<any[]>([])
const ragSearched = ref(false)
const reindexing = ref(false)
const urlOpen = ref(false)
const urlInput = ref('')
const urlImporting = ref(false)
const historyOpen = ref(false)
const versionLoading = ref(false)
const versions = ref<any[]>([])
const versionPreviewOpen = ref(false)
const versionPreview = ref<any | null>(null)

function openRag(mode: 'search' | 'ask') {
  ragMode.value = mode
  ragOpen.value = true
}

async function runRag() {
  const q = ragQuery.value.trim()
  if (!q) return
  ragLoading.value = true
  ragAnswer.value = ''
  ragSources.value = []
  ragResults.value = []
  ragSearched.value = false
  try {
    if (ragMode.value === 'ask') {
      const res = await client.post('/plugins/notes/rag/ask', { question: q })
      ragAnswer.value = res.data.answer || ''
      ragSources.value = res.data.sources || []
    } else {
      const res = await client.post('/plugins/notes/rag/search', { q })
      ragResults.value = res.data.results || []
      ragSearched.value = true
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '检索失败')
  } finally {
    ragLoading.value = false
  }
}

async function reindexNotes() {
  reindexing.value = true
  try {
    const res = await client.post('/plugins/notes/rag/reindex', { limit: 500 })
    const d = res.data || {}
    ElMessage.success(`已索引 ${d.notes || 0} 篇笔记、${d.chunks || 0} 个片段`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '重建索引失败')
  } finally {
    reindexing.value = false
  }
}

function openSource(noteId: number) {
  if (!noteId) return
  ragOpen.value = false
  openNote(noteId)
}

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
  if (currentId.value === id && !noteLoading.value) return
  currentId.value = id
  if (isMobile.value) mobileListOpen.value = false

  const seq = ++openSeq
  const cached = noteCache.get(id)
  if (cached) {
    noteTitle.value = cached.title
    noteContent.value = cached.content
  }
  noteLoading.value = !cached
  try {
    const res = await client.get(`/plugins/notes/${id}`)
    if (seq !== openSeq) return
    const n = res.data
    if (!cached || n.title !== cached.title || n.content !== cached.content) {
      noteTitle.value = n.title || ''
      noteContent.value = n.content || ''
    }
    noteCache.set(id, { title: n.title || '', content: n.content || '' })
    saveStatus.value = '已保存'
  } catch (e) { console.error(e) }
  finally {
    if (seq === openSeq) noteLoading.value = false
  }
}

async function saveNote() {
  if (!currentId.value) return
  saveStatus.value = '保存中...'
  try {
    await client.put(`/plugins/notes/${currentId.value}`, {
      title: noteTitle.value, content: noteContent.value,
    })
    // Update the tree node in place: reloading the whole tree on every autosave
    // was the main cause of the notes page feeling slow.
    const node = flattenTree(tree.value).find((n: any) => n.id === currentId.value)
    if (node) node.title = noteTitle.value
    noteCache.set(currentId.value, { title: noteTitle.value, content: noteContent.value })
    saveStatus.value = '已保存'
  } catch (e) {
    saveStatus.value = '保存失败'
    console.error(e)
  }
}

function autoSave() {
  saveStatus.value = '编辑中...'
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

async function doImportFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await client.post('/plugins/notes/import/file', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000,
    })
    ElMessage.success(`已导入：${res.data?.title || file.name}`)
    await loadTree()
    if (res.data?.id) await openNote(res.data.id)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  }
}

function triggerFileImport() {
  fileInputRef.value?.click()
}

async function onFileInput(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (file) await doImportFile(file)
}

function handleImportCommand(cmd: string) {
  if (cmd === 'file') triggerFileImport()
  else if (cmd === 'url') urlOpen.value = true
}

async function importUrl() {
  const url = urlInput.value.trim()
  if (!url) return
  urlImporting.value = true
  try {
    const res = await client.post('/plugins/notes/import/url', { url }, { timeout: 120000 })
    ElMessage.success(`已导入：${res.data?.title || '网页'}`)
    urlOpen.value = false
    urlInput.value = ''
    await loadTree()
    if (res.data?.id) await openNote(res.data.id)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '网页导入失败')
  } finally {
    urlImporting.value = false
  }
}

async function openHistory() {
  if (!currentId.value) return
  historyOpen.value = true
  versionLoading.value = true
  versions.value = []
  try {
    const res = await client.get(`/plugins/notes/${currentId.value}/versions`)
    versions.value = res.data?.versions || []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '读取历史版本失败')
  } finally {
    versionLoading.value = false
  }
}

async function previewVersion(v: any) {
  if (!currentId.value) return
  try {
    const res = await client.get(`/plugins/notes/${currentId.value}/versions/${v.id}`)
    versionPreview.value = res.data
    versionPreviewOpen.value = true
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '读取版本失败')
  }
}

async function restoreVersion(v: any) {
  if (!currentId.value) return
  try {
    await ElMessageBox.confirm(`恢复到版本 ${v.version}？当前内容会先保存为一个新版本。`, '恢复历史版本', { type: 'warning' })
    await client.post(`/plugins/notes/${currentId.value}/versions/${v.id}/restore`)
    historyOpen.value = false
    await loadTree()
    await openNote(currentId.value)
    ElMessage.success('已恢复')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.response?.data?.detail || '恢复失败')
  }
}

const treeCount = computed(() => flattenTree(tree.value).length)
const noteCharCount = computed(() => (noteContent.value || '').replace(/\s/g, '').length)

async function handleMove(sourceId: number, targetId: number, position: 'before' | 'after' | 'inside') {
  if (sourceId === targetId) return
  const all = flattenTree(tree.value)
  const source = all.find((n: any) => n.id === sourceId)
  const target = all.find((n: any) => n.id === targetId)
  if (!source || !target) return

  const descendants = flattenTree([source]).map((n: any) => n.id)
  if (descendants.includes(targetId)) {
    ElMessage.warning('不能移动到自己的子级')
    return
  }

  let parentId: number | null
  let index: number
  if (position === 'inside') {
    parentId = target.id
    index = (target.children || []).filter((n: any) => n.id !== sourceId).length
  } else {
    parentId = target.parent_id ?? null
    const siblings = all
      .filter((n: any) => (n.parent_id ?? null) === parentId && n.id !== sourceId)
      .sort((a: any, b: any) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id)
    const ti = siblings.findIndex((n: any) => n.id === targetId)
    index = (ti >= 0 ? ti : 0) + (position === 'after' ? 1 : 0)
  }

  if (source.is_folder && parentId !== null) {
    ElMessage.warning('文件夹只能作为顶层工作空间，不能嵌套')
    return
  }

  try {
    await client.post(`/plugins/notes/${sourceId}/move`, { parent_id: parentId, sort_order: index })
    await loadTree()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '移动失败')
  }
}

async function createFolder() {
  try {
    const { value } = await ElMessageBox.prompt('文件夹名称', '新建文件夹', {
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    await client.post('/plugins/notes', { title: value.trim(), content: '', is_folder: true })
    await loadTree()
    ElMessage.success('文件夹已创建')
  } catch { /* cancelled */ }
}

function onSidebarSearch() {
  if (sidebarSearchTimer) clearTimeout(sidebarSearchTimer)
  sidebarSearchTimer = setTimeout(async () => {
    const q = sidebarQuery.value.trim()
    if (!q) {
      noteSearchResults.value = []
      return
    }
    noteSearchLoading.value = true
    try {
      const res = await client.get('/plugins/notes/search', { params: { q } })
      noteSearchResults.value = Array.isArray(res.data) ? res.data : []
    } catch {
      noteSearchResults.value = []
    } finally {
      noteSearchLoading.value = false
    }
  }, 350)
}

async function openSearchResult(n: any) {
  sidebarQuery.value = ''
  noteSearchResults.value = []
  await openNote(n.id)
}

function exportMarkdown() {
  const text = editorRef.value?.getMarkdown?.() || noteContent.value || ''
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${(noteTitle.value || 'note').replace(/[\\/:*?"<>|]+/g, '_')}.md`
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

async function handleMoreCommand(cmd: string, inEditor = false) {
  if (cmd === 'reindex') {
    await reindexNotes()
  } else if (cmd === 'rag-ask') {
    openRag('ask')
  } else if (cmd === 'rag-search') {
    openRag('search')
  } else if (cmd === 'delete' && inEditor) {
    await deleteNote()
  }
}

function syncNotesViewport() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) mobileListOpen.value = false
}

onMounted(() => {
  syncNotesViewport()
  window.addEventListener('resize', syncNotesViewport)
  loadTree()
})

onUnmounted(() => {
  window.removeEventListener('resize', syncNotesViewport)
})
</script>

<style scoped>
.notes-page {
  height: calc(100vh - var(--header-height) - 40px);
  margin: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--color-content-bg);
  color: #1f2937;
}
.notes-topbar {
  height: 64px;
  flex: 0 0 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 22px;
  border-bottom: 1px solid #e8ecf1;
  background: rgba(255, 255, 255, 0.96);
}
.notes-heading { min-width: 0; display: flex; align-items: center; gap: 8px; }
.notes-list-toggle { display: none; }
.notes-title { font-size: 19px; font-weight: 700; letter-spacing: .2px; }
.notes-sub { font-size: 12px; color: #8b95a5; margin-top: 2px; }
.notes-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; min-width: 0; }
.notes-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
  padding: 16px 20px 20px;
}
.notes-sidebar {
  width: 260px;
  flex: 0 0 260px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #e5eaf1;
  border-radius: 14px;
  overflow: hidden;
}
.sidebar-top { padding: 14px 14px 12px; border-bottom: 1px solid #eef2f6; }
.sidebar-title-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 13px; font-weight: 600; color: #4b5563; }
.sidebar-tools { display: flex; gap: 2px; }
.note-list { flex: 1; min-height: 0; overflow-y: auto; padding: 8px; }
.sidebar-foot { padding: 10px 14px; border-top: 1px solid #eef2f6; color: #9aa3b2; font-size: 11px; }
.search-result { padding: 10px 10px; border-radius: 9px; cursor: pointer; }
.search-result:hover { background: #f3f7fc; }
.search-result.active { background: #eaf3ff; }
.search-result-title { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.search-result-meta { font-size: 11px; color: #9aa3b2; margin-top: 3px; }
.notes-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #e5eaf1;
  border-radius: 14px;
  overflow: hidden;
}
.note-head {
  flex: 0 0 auto;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px 18px;
  padding: 18px 24px 12px;
  border-bottom: 1px solid #eef2f6;
}
.note-title-block { flex: 1; min-width: 0; }
.title-input :deep(.el-input__inner) { font-size: 26px; font-weight: 700; border: none; padding: 0; line-height: 1.35; color: #111827; }
.title-input :deep(.el-input__wrapper) { border: none; box-shadow: none !important; padding: 0; background: transparent; }
.note-meta { display: flex; gap: 10px; margin-top: 6px; color: #9aa3b2; font-size: 12px; }
.note-actions { display: flex; align-items: center; justify-content: flex-end; gap: 4px; flex: 0 1 auto; flex-wrap: wrap; padding-top: 4px; }
.note-editor-shell { position: relative; flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; padding: 0 20px 8px; }
.note-loading {
  position: absolute; inset: 0; z-index: 5;
  display: flex; align-items: center; justify-content: center; gap: 9px;
  background: rgba(255, 255, 255, .86);
  backdrop-filter: blur(2px);
  color: #64748b; font-size: 13px;
}
.note-spinner {
  width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid #dbe3f5; border-top-color: var(--brand-500);
  animation: note-spin .7s linear infinite;
}
@keyframes note-spin { to { transform: rotate(360deg); } }
.notes-empty { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; background: #fff; border: 1px solid #e5eaf1; border-radius: 14px; }
.hidden-file { display: none; }
.rag-panel { display: flex; flex-direction: column; gap: 12px; }
.rag-answer { white-space: pre-wrap; line-height: 1.75; padding: 14px; background: #f7f9fc; border: 1px solid #edf1f6; border-radius: 10px; }
.rag-section-title { font-size: 13px; font-weight: 600; color: #606266; margin-bottom: 8px; }
.rag-sources, .rag-results { display: flex; flex-direction: column; gap: 8px; }
.rag-source, .rag-result { cursor: pointer; border: 1px solid #edf1f6; border-radius: 10px; padding: 10px 12px; transition: border-color .15s, background .15s; }
.rag-source:hover, .rag-result:hover { border-color: #b9d6ff; background: #f7fbff; }
.rag-index { color: #2f80ed; margin-right: 6px; }
.rag-source-title { font-weight: 600; }
.rag-score { float: right; color: #9aa3b2; font-size: 12px; }
.rag-result-head { display: flex; justify-content: space-between; gap: 8px; }
.rag-snippet { color: #606266; font-size: 13px; line-height: 1.6; margin-top: 6px; }
.rag-quote { color: #606266; font-size: 12px; line-height: 1.55; margin-top: 6px; max-height: 72px; overflow: hidden; border-left: 3px solid #dce6f2; padding-left: 8px; }
.rag-tags { display: flex; gap: 6px; margin-top: 8px; }
.version-pre { white-space: pre-wrap; word-break: break-word; line-height: 1.6; font-size: 13px; background: #f7f8fa; padding: 12px; border-radius: 8px; }
@media (max-width: 980px) {
  .notes-sidebar { width: 220px; flex-basis: 220px; }
  .notes-actions .el-button span { display: none; }
  .note-actions .el-button span { display: none; }
}
@media (max-width: 768px) {
  .notes-page { height: calc(100vh - var(--header-height) - 20px); }
  .notes-topbar {
    height: auto; flex: 0 0 auto; padding: 10px 12px;
    flex-wrap: wrap; gap: 8px; align-items: center;
  }
  .notes-title { font-size: 17px; }
  .notes-sub { display: none; }
  .notes-list-toggle { display: inline-flex; }
  .notes-actions { gap: 4px; flex: 1 1 auto; justify-content: flex-end; }
  .notes-actions .el-button { padding: 6px; }
  .notes-body { padding: 10px; gap: 0; position: relative; }
  .notes-sidebar {
    position: fixed; left: 0; top: 0; bottom: 0; z-index: 2200;
    width: 84vw; max-width: 320px; flex-basis: auto;
    border-radius: 0; transform: translateX(-100%);
    transition: transform .2s ease;
  }
  .notes-sidebar.mobile-open { transform: translateX(0); }
  .notes-backdrop {
    position: fixed; inset: 0; background: rgba(0, 0, 0, .45); z-index: 2199;
  }
  .notes-main, .notes-empty { border-radius: 12px; }
  .note-head { padding: 12px; gap: 8px; }
  .title-input :deep(.el-input__inner) { font-size: 20px; }
  .note-editor-shell { padding: 0 10px 8px; }
}
</style>
