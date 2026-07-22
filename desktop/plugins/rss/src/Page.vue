<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
const props = defineProps<{ data?: any; execute?: (a: string, args?: any) => Promise<any>; close?: () => void }>()
const api = (window as any).mqbox?.api

const feeds = ref<any[]>([])
const entries = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(30)
const filter = ref<'all' | 'unread' | 'starred'>('all')
const selectedFeedId = ref<number | null>(null)
const selectedEntry = ref<any>(null)
const searchQuery = ref('')
const loadingFeeds = ref(false)
const loadingEntries = ref(false)
const showAddDialog = ref(false)
const addUrl = ref('')
const showDeleteConfirm = ref(false)
const deletingFeed = ref<any>(null)
const addingFeed = ref(false)

async function loadFeeds() {
  loadingFeeds.value = true
  try {
    const r = await api?.get('/rss/feeds')
    feeds.value = r || []
  } catch {} finally { loadingFeeds.value = false }
}

async function loadEntries() {
  loadingEntries.value = true
  selectedEntry.value = null
  try {
    const params = new URLSearchParams()
    if (selectedFeedId.value) params.set('feed_id', String(selectedFeedId.value))
    if (filter.value === 'unread') params.set('unread', 'true')
    if (filter.value === 'starred') params.set('starred', 'true')
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize.value))
    const r = await api?.get(`/rss/entries?${params.toString()}`)
    entries.value = r?.items || []
    total.value = r?.total || 0
  } catch {} finally { loadingEntries.value = false }
}

async function searchEntries() {
  if (!searchQuery.value.trim()) { loadEntries(); return }
  loadingEntries.value = true
  selectedEntry.value = null
  try {
    const r = await api?.get(`/rss/search?q=${encodeURIComponent(searchQuery.value)}`)
    entries.value = r?.items || []
    total.value = r?.total || 0
  } catch {} finally { loadingEntries.value = false }
}

function selectFeed(id: number | null) {
  selectedFeedId.value = id
  page.value = 1
  searchQuery.value = ''
  loadEntries()
}

function setFilter(f: 'all' | 'unread' | 'starred') {
  filter.value = f
  page.value = 1
  loadEntries()
}

function selectEntry(e: any) {
  selectedEntry.value = e
  if (!e.read) markRead(e)
}

async function markRead(e: any) {
  try {
    await api?.put(`/rss/entries/${e.id}/read`)
    e.read = true
  } catch {}
}

async function toggleStar(e: any) {
  try {
    await api?.put(`/rss/entries/${e.id}/star`)
    e.starred = !e.starred
  } catch {}
}

async function addFeed() {
  if (!addUrl.value.trim()) return
  addingFeed.value = true
  try {
    await api?.post('/rss/feeds', { url: addUrl.value.trim() })
    showAddDialog.value = false
    addUrl.value = ''
    await loadFeeds()
  } catch (e: any) {
    alert('添加失败: ' + (e.message || ''))
  } finally { addingFeed.value = false }
}

function confirmDelete(feed: any) {
  deletingFeed.value = feed
  showDeleteConfirm.value = true
}

async function deleteFeed() {
  if (!deletingFeed.value) return
  try {
    await api?.delete(`/rss/feeds/${deletingFeed.value.id}`)
    showDeleteConfirm.value = false
    deletingFeed.value = null
    if (selectedFeedId.value === deletingFeed.value?.id) selectedFeedId.value = null
    await loadFeeds()
    await loadEntries()
  } catch {}
}

async function fetchFeed(feed: any) {
  try {
    await api?.post(`/rss/feeds/${feed.id}/fetch`)
    await loadEntries()
  } catch {}
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const paginationPages = computed(() => {
  const p = page.value; const total = totalPages.value
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages: (number | string)[] = [1]
  if (p > 3) pages.push('...')
  for (let i = Math.max(2, p - 1); i <= Math.min(total - 1, p + 1); i++) pages.push(i)
  if (p < total - 2) pages.push('...')
  if (total > 1) pages.push(total)
  return pages
})

function goPage(p: number | string) {
  if (typeof p !== 'number') return
  page.value = p
  loadEntries()
}

function formatDate(d: string) {
  if (!d) return ''
  const dt = new Date(d)
  const now = new Date()
  const diff = (now.getTime() - dt.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  if (diff < 259200) return `${Math.floor(diff / 86400)}天前`
  return dt.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

onMounted(() => { loadFeeds(); loadEntries() })

watch(searchQuery, (val) => {
  if (!val) { page.value = 1; loadEntries() }
})
</script>
<template>
  <div class="rss-page">
    <!-- Header -->
    <div class="header">
      <h2>资讯</h2>
      <div class="header-actions">
        <button class="btn btn-primary" @click="showAddDialog = true">+ 添加订阅</button>
        <button class="btn-close" @click="close">×</button>
      </div>
    </div>

    <div class="body">
      <!-- Left Sidebar -->
      <div class="sidebar">
        <div class="sidebar-section">
          <div class="filter-group">
            <button :class="['filter-btn', { active: filter === 'all' }]" @click="setFilter('all')">所有</button>
            <button :class="['filter-btn', { active: filter === 'unread' }]" @click="setFilter('unread')">未读</button>
            <button :class="['filter-btn', { active: filter === 'starred' }]" @click="setFilter('starred')">收藏</button>
          </div>
        </div>

        <div class="sidebar-section">
          <div class="sidebar-label">订阅源</div>
          <div v-if="loadingFeeds" class="loading-text">加载中…</div>
          <div v-else-if="feeds.length === 0" class="loading-text">暂无订阅</div>
          <div v-for="feed in feeds" :key="feed.id" :class="['feed-item', { active: selectedFeedId === feed.id }]">
            <span class="feed-name" @click="selectFeed(feed.id)">{{ feed.title || feed.url }}</span>
            <div class="feed-actions">
              <button class="feed-btn" title="刷新" @click.stop="fetchFeed(feed)">↻</button>
              <button class="feed-btn danger" title="删除" @click.stop="confirmDelete(feed)">×</button>
            </div>
          </div>
        </div>

        <div class="sidebar-section" style="border-top:1px solid #e9ecef;padding-top:10px">
          <div class="search-box">
            <input v-model="searchQuery" class="search-input" placeholder="搜索文章…" @keyup.enter="searchEntries" />
            <button v-if="searchQuery" class="search-clear" @click="searchQuery='';searchEntries()">×</button>
          </div>
        </div>
      </div>

      <!-- Right Main -->
      <div class="main">
        <!-- Entry List -->
        <div class="entry-list" :class="{ collapsed: selectedEntry }">
          <div v-if="loadingEntries" class="loading-text" style="padding:40px;text-align:center">加载中…</div>
          <template v-else>
            <div v-for="e in entries" :key="e.id" :class="['entry-item', { active: selectedEntry?.id === e.id, unread: !e.read }]" @click="selectEntry(e)">
              <div class="entry-title">{{ e.title }}</div>
              <div class="entry-meta">
                <span class="entry-feed">{{ e.feed_title }}</span>
                <span class="entry-date">{{ formatDate(e.pub_date || e.created_at) }}</span>
                <button :class="['star-btn', { starred: e.starred }]" @click.stop="toggleStar(e)">★</button>
              </div>
            </div>
            <div v-if="entries.length === 0" class="loading-text" style="padding:40px;text-align:center">暂无文章</div>
          </template>
        </div>

        <!-- Reader -->
        <div v-if="selectedEntry" class="reader">
          <div class="reader-header">
            <h3 class="reader-title">{{ selectedEntry.title }}</h3>
            <div class="reader-meta">
              <a v-if="selectedEntry.link" :href="selectedEntry.link" target="_blank" class="reader-link">查看原文</a>
              <span v-if="selectedEntry.author" class="reader-author">{{ selectedEntry.author }}</span>
              <span class="reader-date">{{ selectedEntry.pub_date ? new Date(selectedEntry.pub_date).toLocaleString('zh-CN') : '' }}</span>
            </div>
          </div>
          <div class="reader-content" v-html="selectedEntry.content || selectedEntry.description || ''"></div>
        </div>
        <div v-else-if="!loadingEntries && entries.length > 0" class="reader-empty">
          选择一篇文章阅读
        </div>

        <!-- Pagination -->
        <div v-if="totalPages > 1" class="pagination">
          <button :disabled="page === 1" class="page-btn" @click="goPage(page - 1)">‹</button>
          <template v-for="p in paginationPages" :key="p">
            <span v-if="p === '...'" class="page-dots">…</span>
            <button v-else :class="['page-btn', { active: p === page }]" @click="goPage(p)">{{ p }}</button>
          </template>
          <button :disabled="page === totalPages" class="page-btn" @click="goPage(page + 1)">›</button>
        </div>
      </div>
    </div>

    <!-- Add Feed Dialog -->
    <div v-if="showAddDialog" class="modal-overlay" @click.self="showAddDialog = false">
      <div class="modal">
        <h3>添加订阅</h3>
        <input v-model="addUrl" class="input" placeholder="输入 RSS 订阅地址…" @keyup.enter="addFeed" />
        <div class="modal-actions">
          <button class="btn ghost" @click="showAddDialog = false">取消</button>
          <button class="btn btn-primary" @click="addFeed" :disabled="addingFeed">{{ addingFeed ? '添加中…' : '添加' }}</button>
        </div>
      </div>
    </div>

    <!-- Delete Confirm -->
    <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
      <div class="modal">
        <h3>删除订阅</h3>
        <p style="font-size:13px;color:#666">确定删除「{{ deletingFeed?.title || deletingFeed?.url }}」？</p>
        <div class="modal-actions">
          <button class="btn ghost" @click="showDeleteConfirm = false">取消</button>
          <button class="btn btn-danger" @click="deleteFeed">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.rss-page { height:100vh; background:#f8f9fa; font-family:-apple-system,sans-serif; display:flex; flex-direction:column; }
.header { display:flex; align-items:center; justify-content:space-between; padding:12px 20px; border-bottom:1px solid #e9ecef; background:#fff; flex-shrink:0; }
.header h2 { margin:0; font-size:18px; font-weight:600; }
.header-actions { display:flex; align-items:center; gap:10px; }
.btn-close { width:32px; height:32px; border:none; border-radius:8px; background:transparent; font-size:20px; cursor:pointer; color:#868e96; }
.btn-close:hover { background:#ffebee; color:#e91e63; }
.body { display:flex; flex:1; min-height:0; }

/* Sidebar */
.sidebar { width:220px; min-width:220px; background:#fff; border-right:1px solid #e9ecef; display:flex; flex-direction:column; overflow-y:auto; padding:12px; }
.sidebar-section { margin-bottom:10px; }
.sidebar-label { font-size:11px; font-weight:600; color:#909399; text-transform:uppercase; margin-bottom:6px; padding:0 4px; }
.filter-group { display:flex; gap:4px; }
.filter-btn { flex:1; height:30px; border:1px solid #dee2e6; border-radius:6px; background:#fff; font-size:12px; color:#555; cursor:pointer; }
.filter-btn:hover { background:#f1f3f5; }
.filter-btn.active { background:#fce4ec; color:#e91e63; border-color:#f8bbd0; }
.feed-item { display:flex; align-items:center; justify-content:space-between; padding:6px 8px; border-radius:6px; cursor:pointer; margin-bottom:1px; }
.feed-item:hover { background:#f1f3f5; }
.feed-item.active { background:#fce4ec; }
.feed-name { font-size:12px; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.feed-actions { display:flex; gap:2px; opacity:0; }
.feed-item:hover .feed-actions { opacity:1; }
.feed-btn { width:20px; height:20px; border:none; border-radius:4px; background:transparent; cursor:pointer; font-size:12px; color:#999; display:flex; align-items:center; justify-content:center; }
.feed-btn:hover { background:#dee2e6; color:#333; }
.feed-btn.danger:hover { background:#ffebee; color:#e91e63; }
.search-box { position:relative; }
.search-input { width:100%; height:32px; padding:0 28px 0 10px; border:1px solid #dee2e6; border-radius:6px; font-size:12px; outline:none; box-sizing:border-box; }
.search-input:focus { border-color:#e91e63; }
.search-clear { position:absolute; right:4px; top:50%; transform:translateY(-50%); width:20px; height:20px; border:none; background:transparent; color:#999; cursor:pointer; font-size:14px; }

/* Main area */
.main { flex:1; display:flex; flex-direction:column; overflow:hidden; min-width:0; }
.entry-list { overflow-y:auto; flex-shrink:0; }
.entry-list.collapsed { max-height:280px; border-bottom:1px solid #e9ecef; }
.entry-item { padding:10px 16px; cursor:pointer; border-bottom:1px solid #f5f5f5; }
.entry-item:hover { background:#f8f9fa; }
.entry-item.active { background:#fce4ec; }
.entry-item.unread { border-left:3px solid #e91e63; padding-left:13px; }
.entry-title { font-size:13px; color:#1a1a1a; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-bottom:3px; }
.entry-meta { display:flex; align-items:center; gap:8px; font-size:11px; color:#909399; }
.entry-feed { max-width:100px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.star-btn { width:20px; height:20px; border:none; background:transparent; cursor:pointer; font-size:14px; color:#ccc; margin-left:auto; }
.star-btn:hover { color:#f59f00; }
.star-btn.starred { color:#f59f00; }

/* Reader */
.reader { flex:1; overflow-y:auto; padding:20px 24px; min-height:0; }
.reader-empty { flex:1; display:flex; align-items:center; justify-content:center; color:#909399; font-size:13px; }
.reader-header { margin-bottom:16px; }
.reader-title { margin:0 0 8px; font-size:18px; font-weight:600; color:#1a1a1a; line-height:1.4; }
.reader-meta { display:flex; align-items:center; gap:12px; font-size:12px; color:#909399; flex-wrap:wrap; }
.reader-link { color:#e91e63; text-decoration:none; }
.reader-link:hover { text-decoration:underline; }
.reader-author::before { content:'作者: '; }
.reader-content { font-size:14px; line-height:1.75; color:#333; }
.reader-content :deep(img) { max-width:100%; height:auto; border-radius:6px; margin:8px 0; }
.reader-content :deep(a) { color:#e91e63; }
.reader-content :deep(blockquote) { border-left:3px solid #e91e63; margin:12px 0; padding:6px 12px; background:#f8f9fa; color:#666; }
.reader-content :deep(pre) { background:#f1f3f5; border-radius:6px; padding:12px; overflow-x:auto; font-size:13px; }
.reader-content :deep(code) { background:#f1f3f5; padding:2px 4px; border-radius:3px; font-size:12px; }
.reader-content :deep(pre code) { background:transparent; padding:0; }
.reader-content :deep(h1),.reader-content :deep(h2),.reader-content :deep(h3) { margin:16px 0 8px; }

/* Pagination */
.pagination { display:flex; align-items:center; justify-content:center; gap:4px; padding:12px; border-top:1px solid #e9ecef; background:#fff; flex-shrink:0; }
.page-btn { min-width:30px; height:30px; border:1px solid #dee2e6; border-radius:6px; background:#fff; font-size:12px; color:#555; cursor:pointer; }
.page-btn:hover { background:#f1f3f5; }
.page-btn.active { background:#fce4ec; color:#e91e63; border-color:#f8bbd0; }
.page-btn:disabled { opacity:0.4; cursor:default; }
.page-dots { width:20px; text-align:center; color:#adb5bd; font-size:12px; }

/* Buttons */
.btn { height:34px; padding:0 16px; border:none; border-radius:8px; font-size:12px; font-weight:500; cursor:pointer; }
.btn.ghost { background:transparent; color:#666; }
.btn.ghost:hover { background:#f1f3f5; }
.btn-primary { background:#fce4ec; color:#e91e63; }
.btn-primary:hover { background:#f8bbd0; }
.btn-danger { background:#ffebee; color:#e53935; }
.btn-danger:hover { background:#ffcdd2; }

/* Modal */
.modal-overlay { position:fixed; inset:0; background:rgba(0,0,0,.4); display:flex; align-items:center; justify-content:center; z-index:100; }
.modal { background:#fff; border-radius:12px; padding:24px; width:400px; max-width:90vw; box-shadow:0 20px 60px rgba(0,0,0,.2); }
.modal h3 { margin:0 0 16px; font-size:16px; font-weight:600; }
.modal p { margin:0 0 16px; }
.input { width:100%; height:36px; padding:0 10px; border:1px solid #dee2e6; border-radius:6px; font-size:13px; margin-bottom:10px; outline:none; font-family:inherit; box-sizing:border-box; }
.input:focus { border-color:#e91e63; }
.modal-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:16px; }

.loading-text { font-size:12px; color:#909399; }
</style>
