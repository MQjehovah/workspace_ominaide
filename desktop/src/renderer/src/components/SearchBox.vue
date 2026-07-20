<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const query = ref('')
const results = ref<any[]>([])
const selectedIndex = ref(0)
const isLoading = ref(false)
const providers = ref<{ keyword: string; name: string }[]>([])

let debounceTimer: number | null = null
const inputRef = ref<HTMLInputElement>()

async function loadProviders() {
  try { providers.value = await window.mqbox?.search.getProviders() || [] }
  catch { providers.value = [] }
}

function handleInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  const q = query.value.trim()
  if (!q) { results.value = []; isLoading.value = false; return }
  isLoading.value = true
  debounceTimer = window.setTimeout(async () => {
    const parts = q.split(/\s+/)
    const firstWord = parts[0]
    const rest = parts.slice(1).join(' ')
    let searchKeyword = ''
    let searchQuery = q
    const matched = providers.value.find(p => p.keyword === firstWord)
    if (matched) { searchKeyword = firstWord; searchQuery = rest || '' }
    try {
      const pluginResults = await window.mqbox?.search?.plugin(searchKeyword, searchQuery) || []
      results.value = pluginResults.map((r: any) => ({
        type: 'plugin', title: r.title, subtitle: r.subtitle || '',
        icon: r.icon, action: r.action, actionArgs: r.actionArgs, pluginId: r.pluginId,
      }))
      selectedIndex.value = 0
    } catch { results.value = [] }
    isLoading.value = false
  }, 200)
}

function selectNext() { if (selectedIndex.value < results.value.length - 1) selectedIndex.value++ }
function selectPrev() { if (selectedIndex.value > 0) selectedIndex.value-- }

async function executeSelected() {
  const r = results.value[selectedIndex.value]
  if (!r) return
  if (r.action && r.pluginId) {
    const action = r.action.includes(':') ? r.action.split(':').slice(1).join(':') : r.action
    await window.mqbox?.plugin.execute(r.pluginId, action, r.actionArgs || {})
  }
  window.mqbox?.window.hide()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') { e.preventDefault(); selectNext() }
  else if (e.key === 'ArrowUp') { e.preventDefault(); selectPrev() }
  else if (e.key === 'Enter') { e.preventDefault(); executeSelected() }
  else if (e.key === 'Escape') { window.mqbox?.window.hide() }
}

function clearSearch() { query.value = ''; results.value = []; selectedIndex.value = 0; isLoading.value = false }

onMounted(() => {
  loadProviders()
  nextTick(() => inputRef.value?.focus())
})

onUnmounted(() => { if (debounceTimer) clearTimeout(debounceTimer) })
</script>

<template>
  <div class="search-overlay" @click.self="window.mqbox?.window.hide()">
    <div class="search-box">
      <div class="input-wrap">
        <svg v-if="!isLoading" class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <svg v-else class="search-icon spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12a9 9 0 1 1-6.22-8.56"/>
        </svg>
        <input ref="inputRef" v-model="query" type="text" placeholder="输入关键词搜索..." @input="handleInput" @keydown="handleKeydown" />
        <button v-if="query" class="clear-btn" @click="clearSearch">✕</button>
      </div>
      <div v-if="results.length" class="results">
        <div v-for="(r, i) in results" :key="i" :class="['result-item', { active: i === selectedIndex }]" @click="selectedIndex = i; executeSelected()" @mouseenter="selectedIndex = i">
          <div class="result-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14 2z"/></svg>
          </div>
          <div class="result-body">
            <div class="result-title">{{ r.title }}</div>
            <div v-if="r.subtitle" class="result-subtitle">{{ r.subtitle }}</div>
          </div>
        </div>
      </div>
      <div v-else-if="query && !isLoading" class="no-results">无结果</div>
      <div v-if="!query" class="hint">输入关键词搜索插件和命令</div>
    </div>
  </div>
</template>

<style scoped>
.search-overlay { width:100vw; height:100vh; display:flex; justify-content:center; padding-top:48px; background:transparent; }
.search-box { width:640px; background:#fff; border-radius:12px; box-shadow:0 4px 24px rgba(0,0,0,0.15); overflow:hidden; }
.input-wrap { display:flex; align-items:center; gap:10px; padding:14px 18px; background:#f5f7fa; margin:12px; border-radius:10px; }
.search-icon { width:20px; height:20px; color:#c0c4cc; flex-shrink:0; }
.spin { animation:spin 0.8s linear infinite; }
@keyframes spin { to { transform:rotate(360deg) } }
.input-wrap input { flex:1; border:none; outline:none; font-size:16px; background:transparent; color:#303133; }
.input-wrap input::placeholder { color:#c0c4cc; }
.clear-btn { border:none; background:transparent; color:#c0c4cc; cursor:pointer; font-size:16px; padding:2px 6px; border-radius:4px; }
.clear-btn:hover { background:#e4e7ed; color:#909399; }
.results { max-height:300px; overflow-y:auto; padding:0 8px 8px; }
.result-item { display:flex; align-items:center; gap:10px; padding:10px 14px; border-radius:8px; cursor:pointer; transition:background 0.1s; }
.result-item.active, .result-item:hover { background:#ecf5ff; }
.result-icon { width:20px; height:20px; display:flex; align-items:center; justify-content:center; color:#409EFF; flex-shrink:0; }
.result-icon svg { width:18px; height:18px; }
.result-body { flex:1; min-width:0; }
.result-title { font-size:14px; color:#303133; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.result-subtitle { font-size:12px; color:#909399; margin-top:2px; }
.no-results { text-align:center; padding:20px; color:#c0c4cc; font-size:13px; }
.hint { text-align:center; padding:8px 0 16px; color:#c0c4cc; font-size:12px; }
</style>
