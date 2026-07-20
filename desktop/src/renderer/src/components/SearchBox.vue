<template>
  <div class="search-box" @keydown="handleKey">
    <el-input
      ref="inputRef"
      v-model="store.query"
      placeholder="搜索..."
      :prefix-icon="Search"
      size="large"
      clearable
      @input="doSearch"
    />
    <div class="results" v-if="store.results.length">
      <div
        v-for="(r, i) in store.results"
        :key="i"
        :class="['result-item', { active: i === selectedIndex }]"
        @click="executeResult(r)"
        @mouseenter="selectedIndex = i"
      >
        <span class="r-icon">{{ r.icon === 'plus' ? '+' : '•' }}</span>
        <div class="r-body">
          <div class="r-title">{{ r.title }}</div>
          <div class="r-subtitle" v-if="r.subtitle">{{ r.subtitle }}</div>
        </div>
      </div>
    </div>
    <div class="hint" v-else-if="store.query && !store.loading">无结果</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { useSearchStore } from '../stores/search'

const store = useSearchStore()
const inputRef = ref<any>(null)
const selectedIndex = ref(0)

onMounted(async () => {
  await store.loadProviders()
  nextTick(() => inputRef.value?.focus())
})

function doSearch() {
  const parts = store.query.split(' ')
  const firstWord = parts[0]
  const rest = parts.slice(1).join(' ')
  const matched = store.providers.find(p => p.keyword === firstWord)
  store.search(matched ? firstWord : '', matched ? rest : store.query)
  selectedIndex.value = 0
}

function handleKey(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') { e.preventDefault(); selectedIndex.value = Math.min(selectedIndex.value + 1, store.results.length - 1) }
  if (e.key === 'ArrowUp') { e.preventDefault(); selectedIndex.value = Math.max(selectedIndex.value - 1, 0) }
  if (e.key === 'Enter' && store.results[selectedIndex.value]) executeResult(store.results[selectedIndex.value])
}

function executeResult(r: any) {
  if (r.pluginId && r.action) {
    store.$reset()
    window.mqbox.plugin.execute(r.pluginId, r.action, r.actionArgs)
  }
}
</script>

<style scoped>
.search-box { padding:16px; background:transparent; }
.results { margin-top:8px; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,0.12); }
.result-item { display:flex; align-items:center; gap:10px; padding:10px 14px; cursor:pointer; transition:background 0.1s; }
.result-item.active, .result-item:hover { background:#ecf5ff; }
.r-icon { width:20px; text-align:center; color:#409EFF; }
.r-body { flex:1; min-width:0; }
.r-title { font-size:13px; color:#303133; }
.r-subtitle { font-size:11px; color:#909399; }
.hint { text-align:center; padding:20px; color:#909399; font-size:13px; }
</style>
