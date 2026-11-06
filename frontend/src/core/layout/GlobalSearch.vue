<template>
  <div class="global-search" v-click-outside="closeResults">
    <el-input
      ref="searchRef"
      v-model="keyword"
      class="search-input"
      placeholder="搜索日程 / 邮件 / 资讯 / 笔记…（Ctrl+K）"
      clearable
      :prefix-icon="Search"
      @focus="open = true"
      @input="onInput"
      @keyup.enter="doSearch"
    />
    <div v-if="open && keyword.trim()" class="search-results">
      <div v-if="loading" class="search-loading">
        <el-icon class="is-loading"><Loading /></el-icon> 搜索中…
      </div>
      <template v-else>
        <div v-for="group in grouped" :key="group.type" class="search-group">
          <div class="search-group-title">{{ group.label }} <span>{{ group.items.length }}</span></div>
          <div v-for="item in group.items" :key="`${item.type}:${item.id}`" class="search-item" @click="openObject(item)">
            <span class="search-badge">{{ item.source_label || group.label }}</span>
            <span class="search-main">
              <span class="search-item-title">{{ item.title }}</span>
              <span class="search-item-sub">{{ item.snippet || item.subtitle }}</span>
            </span>
            <button class="ask-btn" type="button" title="引用并询问助手" @click.stop="ask(item)">问</button>
          </div>
        </div>
        <div v-if="!loading && total === 0" class="search-empty">无匹配结果</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Loading } from '@element-plus/icons-vue'
import client from '@/api/client'

const router = useRouter()
const keyword = ref('')
const open = ref(false)
const loading = ref(false)
const items = ref<any[]>([])
const searchRef = ref<any>(null)
let timer: any = null

const TYPE_ORDER = ['schedule_event', 'mail_message', 'source_item', 'note', 'todo', 'file', 'project']
const TYPE_LABELS: Record<string, string> = {
  schedule_event: '日程',
  mail_message: '邮件',
  source_item: '资讯',
  note: '笔记',
  todo: '待办',
  file: '文件',
  project: '项目',
}

const total = computed(() => items.value.length)
const grouped = computed(() => {
  const groups: Array<{ type: string; label: string; items: any[] }> = []
  for (const type of TYPE_ORDER) {
    const rows = items.value.filter((item) => item.type === type).slice(0, 6)
    if (rows.length) groups.push({ type, label: TYPE_LABELS[type] || type, items: rows })
  }
  return groups
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
  },
}

function closeResults() {
  open.value = false
}

function openObject(item: any) {
  closeResults()
  if (item.url) router.push(item.url)
  else router.push('/')
}

function ask(item: any) {
  closeResults()
  router.push({ path: '/chat', query: { ref: `${item.type}:${item.id}` } })
}

async function doSearch() {
  const q = keyword.value.trim()
  if (!q) {
    items.value = []
    return
  }
  open.value = true
  loading.value = true
  try {
    const { data } = await client.get('/objects/search', { params: { q, limit: 30 } })
    items.value = data.items || []
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

function onInput() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(doSearch, 400)
}

function onHotkey(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    open.value = true
    searchRef.value?.focus?.()
  } else if (event.key === 'Escape') {
    closeResults()
  }
}

onMounted(() => window.addEventListener('keydown', onHotkey))
onUnmounted(() => window.removeEventListener('keydown', onHotkey))
</script>

<style scoped>
.global-search { position: relative; }
.search-input { width: 300px; }
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
  position: absolute; top: 44px; right: 0; width: 420px; max-height: 480px; overflow-y: auto;
  background: #fff; border: 1px solid #e7ebf3; border-radius: 12px;
  box-shadow: 0 24px 50px -24px rgba(16, 24, 40, .45); z-index: 1000;
  padding: 4px 0;
}
.search-loading, .search-empty { text-align: center; padding: 18px; color: #94a3b8; font-size: 12px; }
.search-group { padding: 4px 0; border-bottom: 1px solid #f3f6fb; }
.search-group:last-child { border-bottom: none; }
.search-group-title {
  font-size: 10.5px; color: #94a3b8; padding: 5px 14px; font-weight: 600;
  letter-spacing: .5px; display: flex; gap: 6px;
}
.search-group-title span { color: #c0c7d4; }
.search-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px 8px 14px;
  cursor: pointer; border-radius: 8px; margin: 0 6px;
}
.search-item:hover { background: #f2f5ff; }
.search-badge {
  flex-shrink: 0; font-size: 10px; color: #4f46e5; background: #eef2ff;
  border-radius: 999px; padding: 2px 7px;
}
.search-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.search-item-title {
  font-size: 13px; color: #334155; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.search-item-sub {
  font-size: 11px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ask-btn {
  flex-shrink: 0; border: 1px solid #dbe3f5; background: #fff; color: #4f46e5;
  font-size: 11px; border-radius: 7px; padding: 2px 8px; cursor: pointer;
}
.ask-btn:hover { background: #eef2ff; border-color: #c7d2fe; }
</style>
