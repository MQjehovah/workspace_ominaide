<template>
  <div class="global-search" v-click-outside="closeResults">
    <el-input
      v-model="keyword"
      class="search-input"
      placeholder="搜索文件 / 笔记 / 资讯"
      clearable
      :prefix-icon="Search"
      @focus="open = true"
      @input="onInput"
      @keyup.enter="doSearch"
    />
    <div v-if="open && keyword.trim()" class="search-results">
      <div v-if="loading" style="text-align:center;padding:16px;color:#909399;font-size:12px">
        <el-icon class="is-loading"><Loading /></el-icon> 搜索中...
      </div>
      <template v-else>
        <div v-if="grouped.files.length" class="search-group">
          <div class="search-group-title">文件</div>
          <div v-for="f in grouped.files" :key="'f' + f.id" class="search-item" @click="go('/files')">
            <el-icon><Document /></el-icon>
            <span class="search-item-title">{{ f.original_name }}</span>
            <span class="search-item-meta">{{ f.mime_type || '文件' }}</span>
          </div>
        </div>
        <div v-if="grouped.notes.length" class="search-group">
          <div class="search-group-title">笔记</div>
          <div v-for="n in grouped.notes" :key="'n' + n.id" class="search-item" @click="go('/notes')">
            <el-icon><Memo /></el-icon>
            <span class="search-item-title">{{ n.title }}</span>
          </div>
        </div>
        <div v-if="grouped.articles.length" class="search-group">
          <div class="search-group-title">资讯</div>
          <div v-for="a in grouped.articles" :key="'a' + a.id" class="search-item" @click="go('/rss')">
            <el-icon><Promotion /></el-icon>
            <span class="search-item-title">{{ a.title }}</span>
          </div>
        </div>
        <div v-if="grouped.semantic.length" class="search-group">
          <div class="search-group-title">语义搜索</div>
          <div v-for="(s, i) in grouped.semantic" :key="'s' + i" class="search-item" @click="go(mapLink(s.type))">
            <el-icon><MagicStick /></el-icon>
            <span class="search-item-title">{{ s.title }}</span>
            <span class="search-item-meta">{{ s.type }}</span>
          </div>
        </div>
        <div v-if="!loading && total === 0" style="text-align:center;padding:16px;color:#909399;font-size:12px">无匹配结果</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Loading, Document, Memo, Promotion, MagicStick } from '@element-plus/icons-vue'
import client from '@/api/client'

const router = useRouter()
const keyword = ref('')
const open = ref(false)
const loading = ref(false)
const total = ref(0)
let timer: any = null

const grouped = reactive<{ files: any[]; notes: any[]; articles: any[]; semantic: any[] }>({
  files: [], notes: [], articles: [], semantic: []
})

const vClickOutside = {
  mounted(el: any, binding: any) {
    el._clickOutside = (e: Event) => {
      if (!el.contains(e.target)) binding.value()
    }
    document.addEventListener('click', el._clickOutside)
  },
  unmounted(el: any) {
    document.removeEventListener('click', el._clickOutside)
  }
}

function closeResults() {
  open.value = false
}

function mapLink(type: string): string {
  const map: Record<string, string> = { file: '/files', note: '/notes', rss_entry: '/rss', event: '/schedule' }
  return map[type] || '/'
}

function go(path: string) {
  closeResults()
  router.push(path)
}

async function doSearch() {
  const q = keyword.value.trim()
  if (!q) return
  open.value = true
  loading.value = true
  grouped.files = []
  grouped.notes = []
  grouped.articles = []
  grouped.semantic = []
  total.value = 0
  try {
    const [filesRes, notesRes, rssRes, semRes] = await Promise.allSettled([
      client.get('/files', { params: { search: q, page_size: 5 } }),
      client.get('/plugins/notes/search', { params: { q } }),
      client.get('/rss/search', { params: { q, page_size: 5 } }),
      client.post('/search', { q, top_k: 5 }).catch(() => null)
    ])
    if (filesRes.status === 'fulfilled') grouped.files = (filesRes.value.data?.files || []).filter((f: any) => !f.is_folder)
    if (notesRes.status === 'fulfilled') {
      grouped.notes = (Array.isArray(notesRes.value.data) ? notesRes.value.data : []).slice(0, 5)
    }
    if (rssRes.status === 'fulfilled') grouped.articles = (rssRes.value.data?.items || [])
    if (semRes.status === 'fulfilled' && semRes.value) grouped.semantic = (semRes.value.data?.results || [])
    total.value = grouped.files.length + grouped.notes.length + grouped.articles.length + grouped.semantic.length
  } finally {
    loading.value = false
  }
}

function onInput() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(doSearch, 500)
}
</script>

<style scoped>
.global-search { position: relative; }
.search-input { width: 260px; }
.search-input :deep(.el-input__wrapper) {
  background: #f2f5fa;
  box-shadow: none;
  border-radius: 9px;
  padding: 1px 12px;
  transition: background .15s, box-shadow .15s;
}
.search-input :deep(.el-input__wrapper:hover) { background: #edf1f8; }
.search-input :deep(.el-input__wrapper.is-focus) {
  background: #fff;
  box-shadow: 0 0 0 1px #c7d2fe inset, 0 6px 18px -12px rgba(79, 70, 229, .6) !important;
}
.search-input :deep(.el-input__inner) { font-size: 12.5px; }
.search-input :deep(.el-input__prefix-inner) { color: #94a3b8; }
.search-results {
  position: absolute; top: 44px; right: 0; width: 360px; max-height: 420px; overflow-y: auto;
  background: #fff; border: 1px solid #e7ebf3; border-radius: 12px;
  box-shadow: 0 24px 50px -24px rgba(16, 24, 40, .45); z-index: 1000;
  padding: 4px 0;
}
.search-group { padding: 5px 0; border-bottom: 1px solid #f3f6fb; }
.search-group:last-child { border-bottom: none; }
.search-group-title {
  font-size: 10.5px; color: #94a3b8; padding: 5px 14px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .6px;
}
.search-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 14px;
  cursor: pointer; font-size: 13px; color: #334155; border-radius: 8px; margin: 0 6px;
}
.search-item:hover { background: #f2f5ff; color: var(--brand-600); }
.search-item-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.search-item-meta { font-size: 11px; color: #909399; flex-shrink: 0; }
</style>
