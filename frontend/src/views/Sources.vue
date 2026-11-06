<template>
  <div class="page-wrapper" style="padding:0">
    <div class="rss-layout">
      <div class="rss-sidebar">
        <div style="padding:16px">
          <el-button type="primary" size="small" style="width:100%;margin-bottom:12px" @click="showAdd=true">添加资讯源</el-button>
          <el-input v-model="searchQ" placeholder="搜索内容…" size="small" clearable style="margin-bottom:12px" />
          <div class="filter-item" :class="{active:filter==='all'}" @click="filter='all';page=1;loadEntries()">全部内容</div>
          <div class="filter-item" :class="{active:filter==='unread'}" @click="filter='unread';page=1;loadEntries()">未读</div>
          <div class="filter-item" :class="{active:filter==='starred'}" @click="filter='starred';page=1;loadEntries()">收藏</div>
        </div>
        <div style="border-top:1px solid var(--color-border);padding:8px 16px;font-size:12px;font-weight:600;color:#909399">资讯源</div>
        <div class="feed-list">
          <div v-for="s in sources" :key="s.id" class="feed-item" :class="{active:activeSource===s.id}" @click="activeSource=s.id;page=1;loadEntries()">
            <span class="feed-name">{{ s.title || s.url }}</span>
            <span class="provider-badge">{{ providerLabel(s.provider) }}</span>
            <el-button link size="small" type="danger" @click.stop="deleteSource(s.id)">&times;</el-button>
          </div>
          <p v-if="sources.length===0" style="text-align:center;color:#909399;font-size:12px;padding:20px">暂无资讯源</p>
        </div>
      </div>

      <div class="rss-main">
        <div v-if="!selectedEntry" class="entry-list">
          <div class="entry-toolbar">
            <span style="font-size:13px;font-weight:600;color:#1a1a2e">{{ pageTitle }}</span>
            <div style="display:flex;gap:8px;align-items:center">
              <el-button size="small" type="primary" plain @click="loadDigest" :loading="digestLoading">今日摘要</el-button>
              <el-button size="small" @click="refreshActiveSource" :loading="refreshing">刷新</el-button>
              <span style="font-size:12px;color:#909399">共 {{ total }} 条</span>
            </div>
          </div>
          <div v-for="e in entries" :key="e.id" class="entry-row" :class="{unread:!e.read}" @click="openEntry(e)">
            <div class="entry-row-title">{{ e.title }}</div>
            <div class="entry-row-meta">{{ e.author || '' }}{{ e.author && e.published ? ' · ' : '' }}{{ formatTime(e.published) }}</div>
          </div>
          <p v-if="!loading && entries.length===0" style="text-align:center;padding:40px;color:#909399">暂无内容</p>
          <div v-if="total>pageSize" style="text-align:center;padding:12px">
            <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev,pager,next" small @current-change="loadEntries" />
          </div>
        </div>

        <div v-else class="reader">
          <div class="reader-header">
            <button class="back-btn" @click="selectedEntry=null">← 返回</button>
            <el-button size="small" type="primary" plain @click="askAssistant(selectedEntry)">让助手处理</el-button>
            <el-button :type="selectedEntry.starred ? 'warning' : 'default'" size="small" text @click="toggleStar(selectedEntry)">{{ selectedEntry.starred ? '★' : '☆' }}</el-button>
          </div>
          <h2 class="reader-title">{{ selectedEntry.title }}</h2>
          <div class="reader-meta">
            <a v-if="selectedEntry.link" :href="selectedEntry.link" target="_blank" rel="noopener">查看原文</a>
            <span v-if="selectedEntry.source_title">{{ selectedEntry.source_title }}</span>
            <span v-if="selectedEntry.author">作者: {{ selectedEntry.author }}</span>
            <span>{{ formatTime(selectedEntry.published) }}</span>
          </div>
          <div class="reader-body" v-html="selectedEntry.content || selectedEntry.summary || ''"></div>
          <div class="reader-comments">
            <ObjectComments type="source_item" :object-id="selectedEntry.id" :title="selectedEntry.title" />
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="showDigest" title="今日资讯摘要" width="520px">
      <p class="digest-summary">{{ digest?.summary || '暂无未读资讯' }}</p>
      <div v-if="digest?.items?.length" class="digest-list">
        <div v-for="item in digest.items" :key="item.id" class="digest-item">
          <span class="digest-feed">{{ item.source }}</span>
          <span class="digest-title">{{ item.title }}</span>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="showAdd" title="添加资讯源" width="460px">
      <el-form label-position="top">
        <el-form-item label="类型">
          <el-select v-model="addForm.provider" style="width:100%">
            <el-option v-for="p in providers" :key="p.key" :label="p.label" :value="p.key" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="addForm.provider==='rss'" label="RSS / Atom 地址">
          <el-input v-model="addForm.url" placeholder="https://example.com/feed.xml" />
        </el-form-item>
        <template v-else>
          <el-form-item label="时间范围">
            <el-select v-model="addForm.since" style="width:100%">
              <el-option label="今日" value="daily" />
              <el-option label="本周" value="weekly" />
              <el-option label="本月" value="monthly" />
            </el-select>
          </el-form-item>
          <el-form-item label="语言">
            <el-input v-model="addForm.language" placeholder="any / python / typescript / go" />
          </el-form-item>
          <el-alert type="info" :closable="false" title="GitHub Trending 通过 RSSHub 获取" />
        </template>
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
import { useRoute, useRouter } from 'vue-router'
import client from '@/api/client'
import { ElMessage } from 'element-plus'
import { parseBackendDate } from '@/utils/date'
import ObjectComments from '@/components/ObjectComments.vue'

const sources = ref<any[]>([])
const activeSource = ref<number | null>(null)
const entries = ref<any[]>([])
const selectedEntry = ref<any>(null)
const route = useRoute()
const router = useRouter()
const filter = ref('all')
const searchQ = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const loading = ref(false)
const refreshing = ref(false)
const showAdd = ref(false)
const adding = ref(false)
const providers = ref<any[]>([])
const addForm = ref({ provider: 'rss', url: '', since: 'daily', language: 'any' })
const showDigest = ref(false)
const digestLoading = ref(false)
const digest = ref<any>(null)

function providerLabel(key: string) {
  const found = providers.value.find((p) => p.key === key)
  if (found) return found.label
  if (key === 'github_trending') return 'GitHub Trending'
  return 'RSS'
}

async function loadDigest() {
  digestLoading.value = true
  try {
    const { data } = await client.get('/sources/digest', { params: { hours: 24 } })
    digest.value = data
    showDigest.value = true
  } catch {
    ElMessage.error('生成摘要失败')
  } finally {
    digestLoading.value = false
  }
}

const pageTitle = computed(() => {
  if (searchQ.value) return `搜索: ${searchQ.value}`
  const filters: Record<string,string> = { all:'全部内容', unread:'未读', starred:'收藏' }
  const base = filters[filter.value] || '内容'
  if (activeSource.value) {
    const s = sources.value.find(s=>s.id===activeSource.value)
    return s ? `${s.title||'资讯源'} — ${base}` : base
  }
  return base
})

async function loadProviders() {
  try {
    const r = await client.get('/sources/providers')
    providers.value = r.data || []
  } catch {
    providers.value = [
      { key: 'rss', label: 'RSS / Atom' },
      { key: 'github_trending', label: 'GitHub Trending' },
    ]
  }
}
async function loadSources() {
  try { const r = await client.get('/sources'); sources.value = r.data || [] } catch { /* ignore */ }
}
async function loadEntries() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (activeSource.value) params.source_id = activeSource.value
    if (filter.value === 'unread') params.unread = true
    if (filter.value === 'starred') params.starred = true
    if (searchQ.value) {
      const r = await client.get('/sources/search', { params: { q: searchQ.value, page: page.value, page_size: pageSize.value } })
      entries.value = r.data.items || []; total.value = r.data.total || 0
    } else {
      const r = await client.get('/sources/items', { params })
      entries.value = r.data.items || []; total.value = r.data.total || 0
    }
  } catch { entries.value = []; total.value = 0 }
  finally { loading.value = false }
}
async function handleAdd() {
  const provider = addForm.value.provider
  let payload: any
  if (provider === 'rss') {
    if (!addForm.value.url.trim()) return
    payload = { provider: 'rss', url: addForm.value.url.trim() }
  } else {
    payload = {
      provider,
      config: {
        since: addForm.value.since,
        language: addForm.value.language.trim() || 'any',
      },
    }
  }
  adding.value = true
  try {
    await client.post('/sources', payload)
    ElMessage.success('已添加')
    showAdd.value = false
    addForm.value = { provider: 'rss', url: '', since: 'daily', language: 'any' }
    loadSources()
  } catch (e:any) { ElMessage.error(e.response?.data?.detail || '添加失败') }
  finally { adding.value = false }
}
async function deleteSource(id: number) {
  try {
    await client.delete(`/sources/${id}`)
    if (activeSource.value === id) activeSource.value = null
    loadSources(); loadEntries()
  } catch { ElMessage.error('删除失败') }
}
async function refreshActiveSource() {
  if (!activeSource.value) return
  refreshing.value = true
  try { await client.post(`/sources/${activeSource.value}/fetch`); loadEntries() }
  catch { ElMessage.error('刷新失败') }
  finally { refreshing.value = false }
}
function askAssistant(entry: any) {
  if (!entry?.id) return
  router.push({ path: '/chat', query: { ref: `source_item:${entry.id}` } })
}

async function openEntry(e: any) {
  selectedEntry.value = e
  if (!e.read) {
    try { await client.put(`/sources/items/${e.id}/read`); e.read = true } catch { /* ignore */ }
  }
}
async function toggleStar(e: any) {
  try { const r = await client.put(`/sources/items/${e.id}/star`); e.starred = r.data.starred } catch { /* ignore */ }
}
function formatTime(iso: string) {
  if (!iso) return ''
  const d = parseBackendDate(iso)
  if (isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}
onMounted(async () => {
  await Promise.all([loadProviders(), loadSources(), loadEntries()])
  const id = Number(route.query.item)
  if (Number.isFinite(id) && id > 0) {
    try {
      const { data } = await client.get(`/sources/items/${id}`)
      await openEntry(data)
    } catch { /* ignore invalid deep link */ }
  }
})
</script>

<style scoped>
.rss-layout { display:flex; height:calc(100vh - var(--header-height) - 2px); }
.rss-sidebar { width:220px; border-right:1px solid var(--color-border); background:#fafbfc; flex-shrink:0; overflow-y:auto; }
.filter-item { padding:6px 16px; font-size:13px; cursor:pointer; border-radius:6px; margin:2px 0; }
.filter-item:hover { background:#e8ecf1; }
.filter-item.active { background:#e8ecf1; font-weight:600; color:#1a1a2e; }
.feed-item { display:flex; align-items:center; gap:6px; justify-content:space-between; padding:6px 16px; font-size:13px; cursor:pointer; }
.feed-item:hover { background:#e8ecf1; }
.feed-item.active { background:#dce3ed; font-weight:600; }
.feed-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.provider-badge { font-size:10px; color:#909399; background:#f0f2f5; border-radius:8px; padding:1px 5px; flex-shrink:0; }
.rss-main { flex:1; overflow-y:auto; }
.entry-toolbar { display:flex; align-items:center; justify-content:space-between; padding:12px 20px; border-bottom:1px solid var(--color-border); }
.entry-row { padding:12px 20px; cursor:pointer; border-bottom:1px solid #f5f5f5; }
.entry-row:hover { background:#f8f9fa; }
.entry-row.unread { border-left:3px solid #409EFF; }
.entry-row-title { font-size:14px; font-weight:500; color:#1a1a2e; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.entry-row-meta { font-size:12px; color:#909399; margin-top:2px; }
.reader { padding:20px 32px; max-width:800px; }
.reader-comments { margin-top: 22px; padding-top: 16px; border-top: 1px solid #eef1f7; }
.reader-header { display:flex; align-items:center; gap:12px; margin-bottom:16px; }
.back-btn { border:none;background:transparent;cursor:pointer;font-size:14px;color:#409EFF;padding:0; }
.reader-title { font-size:22px; font-weight:700; color:#1a1a2e; margin:0 0 8px; }
.reader-meta { display:flex; gap:16px; font-size:13px; color:#909399; margin-bottom:20px; }
.digest-summary { font-size: 14px; line-height: 1.8; color: #303133; margin: 0 0 14px; }
.digest-list { border-top: 1px solid #f0f2f5; padding-top: 10px; }
.digest-item { display: flex; gap: 8px; font-size: 13px; line-height: 1.9; color: #606266; }
.digest-feed { flex-shrink: 0; color: #909399; font-size: 12px; }
.digest-title { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reader-body { font-size:15px; line-height:1.8; color:#333; }
.reader-body img { max-width:100%; }

@media (max-width: 860px) {
  .rss-layout { flex-direction: column; height: auto; }
  .rss-sidebar {
    width: 100%; max-height: 210px; overflow-y: auto;
    border-right: none; border-bottom: 1px solid var(--color-border);
  }
  .reader { padding: 16px; max-width: 100%; }
  .reader-body { font-size: 14.5px; line-height: 1.75; }
  .entry-row-meta { flex-wrap: wrap; }
}
</style>
