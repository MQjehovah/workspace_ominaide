<template>
  <div class="page-wrapper">
    <div class="page-header">
      <h2>笔记</h2>
      <div class="header-actions">
        <el-button size="small" @click="openRag('search')">语义搜索</el-button>
        <el-button size="small" type="primary" @click="openRag('ask')">知识库问答</el-button>
        <el-button size="small" plain :loading="reindexing" @click="reindexNotes">重建索引</el-button>
      </div>
    </div>
    <div class="page-card">
      <div class="page-card-body" style="padding:0">
        <div class="notes-layout">
          <div class="sidebar-panel">
            <div class="sidebar-header">
              <span class="sidebar-title">全部笔记</span>
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
            <TipTapEditor :key="currentId" v-model="noteContent" @update:model-value="autoSave" placeholder="开始写点什么..." min-height="400px" />
          </div>
          <div v-else class="empty-state">
            <el-empty description="选择或创建一篇笔记" :image-size="80" />
          </div>
        </div>
      </div>
    </div>

    <el-drawer v-model="ragOpen" :title="ragMode === 'ask' ? '知识库问答' : '语义搜索'" size="480px">
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
              <span class="rag-index">[{{ s.index }}]</span>
              <span class="rag-source-title">{{ s.title }}</span>
              <span class="rag-score">{{ Math.round((s.score || 0) * 100) }}%</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import client from '@/api/client'
import TipTapEditor from './TipTapEditor.vue'
import TreeNode from './TreeNode.vue'

const tree = ref<any[]>([])
const currentId = ref<number | null>(null)
const noteTitle = ref('')
const noteContent = ref('')
const loading = ref(true)
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
.page-header { display: flex; align-items: center; justify-content: space-between; }
.header-actions { display: flex; gap: 8px; }
.rag-panel { display: flex; flex-direction: column; gap: 12px; }
.rag-answer { white-space: pre-wrap; line-height: 1.7; padding: 12px; background: #f5f7fa; border-radius: 8px; }
.rag-section-title { font-size: 13px; font-weight: 600; color: #606266; margin-bottom: 8px; }
.rag-sources { display: flex; flex-direction: column; gap: 6px; }
.rag-source, .rag-result { cursor: pointer; border: 1px solid #ebeef5; border-radius: 8px; padding: 10px 12px; transition: border-color .15s, background .15s; }
.rag-source:hover, .rag-result:hover { border-color: #409eff; background: #f5f9ff; }
.rag-index { color: #409eff; margin-right: 6px; }
.rag-source-title { font-weight: 600; }
.rag-score { float: right; color: #909399; font-size: 12px; }
.rag-results { display: flex; flex-direction: column; gap: 10px; }
.rag-result-head { display: flex; justify-content: space-between; gap: 8px; }
.rag-snippet { color: #606266; font-size: 13px; line-height: 1.6; margin-top: 6px; }
.rag-tags { display: flex; gap: 6px; margin-top: 8px; }

.notes-layout { display: flex; height: calc(100vh - 180px); gap: 16px; }
.sidebar-panel { width: 240px; flex-shrink: 0; border: 1px solid #dcdfe6; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
.sidebar-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid #dcdfe6; }
.sidebar-title { font-size: 14px; font-weight: 600; }
.note-list { flex: 1; overflow-y: auto; }
.editor-panel { flex: 1; display: flex; flex-direction: column; gap: 12px; }
.editor-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.title-input :deep(.el-input__inner) { font-size: 24px; font-weight: 700; border: none; padding-left: 0; box-shadow: none; }
.title-input :deep(.el-input__wrapper) { border: none; box-shadow: none !important; padding: 0; }
.empty-state { flex: 1; display: flex; align-items: center; justify-content: center; }
</style>
