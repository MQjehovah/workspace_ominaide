<template>
  <div class="page-wrapper" style="padding:0">
    <div class="rss-layout">
      <div class="rss-sidebar">
        <div style="padding:16px">
          <el-button type="primary" size="small" style="width:100%;margin-bottom:12px" @click="showAdd=true">添加订阅</el-button>
          <el-input v-model="searchQ" placeholder="搜索文章…" size="small" clearable style="margin-bottom:12px" />
          <div class="filter-item" :class="{active:filter==='all'}" @click="filter='all';page=1;loadEntries()">所有文章</div>
          <div class="filter-item" :class="{active:filter==='unread'}" @click="filter='unread';page=1;loadEntries()">未读</div>
          <div class="filter-item" :class="{active:filter==='starred'}" @click="filter='starred';page=1;loadEntries()">收藏</div>
        </div>
        <div style="border-top:1px solid var(--color-border);padding:8px 16px;font-size:12px;font-weight:600;color:#909399">订阅源</div>
        <div class="feed-list">
          <div v-for="f in feeds" :key="f.id" class="feed-item" :class="{active:activeFeed===f.id}" @click="activeFeed=f.id;page=1;loadEntries()">
            <span class="feed-name">{{ f.title || f.url.slice(0,30) }}</span>
            <el-button link size="small" type="danger" @click.stop="deleteFeed(f.id)">&times;</el-button>
          </div>
          <p v-if="feeds.length===0" style="text-align:center;color:#909399;font-size:12px;padding:20px">暂无订阅</p>
        </div>
      </div>

      <div class="rss-main">
        <div v-if="!selectedEntry" class="entry-list">
          <div class="entry-toolbar">
            <span style="font-size:13px;font-weight:600;color:#1a1a2e">{{ pageTitle }}</span>
            <div>
              <el-button size="small" @click="refreshActiveFeed" :loading="refreshing">刷新</el-button>
              <span style="font-size:12px;color:#909399;margin-left:8px">共 {{ total }} 条</span>
            </div>
          </div>
          <div v-for="e in entries" :key="e.id" class="entry-row" :class="{unread:!e.read}" @click="openEntry(e)">
            <div class="entry-row-title">{{ e.title }}</div>
            <div class="entry-row-meta">{{ e.author || '' }}{{ e.author && e.published ? ' · ' : '' }}{{ formatTime(e.published) }}</div>
          </div>
          <p v-if="!loading && entries.length===0" style="text-align:center;padding:40px;color:#909399">暂无文章</p>
          <div v-if="total>pageSize" style="text-align:center;padding:12px">
            <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev,pager,next" small @current-change="loadEntries" />
          </div>
        </div>

        <div v-else class="reader">
          <div class="reader-header">
            <button class="back-btn" @click="selectedEntry=null">← 返回</button>
            <el-button :type="selectedEntry.starred ? 'warning' : 'default'" :icon="selectedEntry.starred ? 'star-filled' : 'star'" size="small" text @click="toggleStar(selectedEntry)" />
          </div>
          <h2 class="reader-title">{{ selectedEntry.title }}</h2>
          <div class="reader-meta">
            <a v-if="selectedEntry.link" :href="selectedEntry.link" target="_blank" rel="noopener">查看原文</a>
            <span v-if="selectedEntry.author">作者: {{ selectedEntry.author }}</span>
            <span>{{ formatTime(selectedEntry.published) }}</span>
          </div>
          <div class="reader-body" v-html="selectedEntry.content || selectedEntry.summary || ''"></div>
        </div>
      </div>
    </div>

    <el-dialog v-model="showAdd" title="添加订阅" width="420px">
      <el-form @submit.prevent="handleAdd" :model="addForm">
        <el-input v-model="addForm.url" placeholder="输入 RSS 订阅地址" />
      </el-form>
      <template #footer>
        <el-button @click="showAdd=false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'
import { ElMessage } from 'element-plus'

const feeds = ref<any[]>([])
const activeFeed = ref<number | null>(null)
const entries = ref<any[]>([])
const selectedEntry = ref<any>(null)
const filter = ref('all')
const searchQ = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const loading = ref(false)
const refreshing = ref(false)
const showAdd = ref(false)
const adding = ref(false)
const addForm = ref({ url: '' })

const pageTitle = computed(() => {
  if (searchQ.value) return `搜索: ${searchQ.value}`
  const filters: Record<string,string> = { all:'所有文章', unread:'未读', starred:'收藏' }
  const base = filters[filter.value] || '文章'
  if (activeFeed.value) {
    const f = feeds.value.find(f=>f.id===activeFeed.value)
    return f ? `${f.title||'订阅'} — ${base}` : base
  }
  return base
})

async function loadFeeds() {
  try { const r = await client.get('/rss/feeds'); feeds.value = r.data || [] } catch { /* ignore */ }
}
async function loadEntries() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (activeFeed.value) params.feed_id = activeFeed.value
    if (filter.value === 'unread') params.unread = true
    if (filter.value === 'starred') params.starred = true
    if (searchQ.value) {
      const r = await client.get('/rss/search', { params: { q: searchQ.value, page: page.value, page_size: pageSize.value } })
      entries.value = r.data.items || []; total.value = r.data.total || 0
    } else {
      const r = await client.get('/rss/entries', { params })
      entries.value = r.data.items || []; total.value = r.data.total || 0
    }
  } catch { entries.value = []; total.value = 0 }
  finally { loading.value = false }
}
async function handleAdd() {
  if (!addForm.value.url.trim()) return
  adding.value = true
  try {
    await client.post('/rss/feeds', addForm.value)
    ElMessage.success('已添加'); showAdd.value = false; addForm.value = { url: '' }; loadFeeds()
  } catch (e:any) { ElMessage.error(e.response?.data?.detail || '添加失败') }
  finally { adding.value = false }
}
async function deleteFeed(id: number) {
  try { await client.delete(`/rss/feeds/${id}`); if (activeFeed.value === id) activeFeed.value = null; loadFeeds(); loadEntries() }
  catch { ElMessage.error('删除失败') }
}
async function refreshActiveFeed() {
  if (!activeFeed.value) return
  refreshing.value = true
  try { await client.post(`/rss/feeds/${activeFeed.value}/fetch`); loadEntries() } catch { ElMessage.error('刷新失败') }
  finally { refreshing.value = false }
}
async function openEntry(e: any) {
  selectedEntry.value = e
  if (!e.read) {
    try { await client.put(`/rss/entries/${e.id}/read`); e.read = true } catch { /* ignore */ }
  }
}
async function toggleStar(e: any) {
  try { const r = await client.put(`/rss/entries/${e.id}/star`); e.starred = r.data.starred } catch { /* ignore */ }
}
function formatTime(iso: string) {
  if (!iso) return ''; const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}
onMounted(() => { loadFeeds(); loadEntries() })
</script>

<style scoped>
.rss-layout { display:flex; height:calc(100vh - var(--header-height) - 2px); }
.rss-sidebar { width:220px; border-right:1px solid var(--color-border); background:#fafbfc; flex-shrink:0; overflow-y:auto; }
.filter-item { padding:6px 16px; font-size:13px; cursor:pointer; border-radius:6px; margin:2px 0; }
.filter-item:hover { background:#e8ecf1; }
.filter-item.active { background:#e8ecf1; font-weight:600; color:#1a1a2e; }
.feed-item { display:flex; align-items:center; justify-content:space-between; padding:6px 16px; font-size:13px; cursor:pointer; }
.feed-item:hover { background:#e8ecf1; }
.feed-item.active { background:#dce3ed; font-weight:600; }
.feed-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.rss-main { flex:1; overflow-y:auto; }
.entry-toolbar { display:flex; align-items:center; justify-content:space-between; padding:12px 20px; border-bottom:1px solid var(--color-border); }
.entry-row { padding:12px 20px; cursor:pointer; border-bottom:1px solid #f5f5f5; }
.entry-row:hover { background:#f8f9fa; }
.entry-row.unread { border-left:3px solid #409EFF; }
.entry-row-title { font-size:14px; font-weight:500; color:#1a1a2e; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.entry-row-meta { font-size:12px; color:#909399; margin-top:2px; }
.reader { padding:20px 32px; max-width:800px; }
.reader-header { display:flex; align-items:center; gap:12px; margin-bottom:16px; }
.back-btn { border:none;background:transparent;cursor:pointer;font-size:14px;color:#409EFF;padding:0; }
.reader-title { font-size:22px; font-weight:700; color:#1a1a2e; margin:0 0 8px; }
.reader-meta { display:flex; gap:16px; font-size:13px; color:#909399; margin-bottom:20px; }
.reader-body { font-size:15px; line-height:1.8; color:#333; }
.reader-body img { max-width:100%; }
</style>
