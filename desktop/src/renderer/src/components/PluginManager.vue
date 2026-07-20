<template>
  <div class="overlay">
    <div class="card">
      <div class="card-hd">
        <div class="tabs">
          <button :class="{ active: tab === 'plugins' }" @click="tab = 'plugins'">已安装</button>
          <button :class="{ active: tab === 'marketplace' }" @click="tab = 'marketplace'; loadMarketplace()">插件市场</button>
          <button :class="{ active: tab === 'shortcuts' }" @click="tab = 'shortcuts'">快捷键</button>
        </div>
        <button class="close-btn" @click="close">✕</button>
      </div>

      <div v-if="tab === 'plugins'" class="card-body">
        <div v-for="p in plugins" :key="p.id" class="plugin-item">
          <div class="plugin-icon" :style="{ background: getColor(p.id) + '20' }">
            <div class="plugin-dot" :style="{ background: p.enabled ? '#28A745' : '#ccc' }"></div>
          </div>
          <div class="plugin-info">
            <span class="plugin-name">{{ p.manifest?.displayName || p.id }}</span>
            <span class="plugin-desc">{{ p.manifest?.description || '' }}</span>
          </div>
          <div class="plugin-actions">
            <button class="cfg-btn" title="配置" @click="openConfig(p)">⚙</button>
            <label class="switch"><input type="checkbox" :checked="p.enabled" @change="togglePlugin(p)" /><span class="slider"></span></label>
          </div>
        </div>
        <button class="import-btn" @click="importPlugin">+ 导入插件</button>
      </div>

      <div v-if="tab === 'marketplace'" class="card-body">
        <div v-if="marketplaceLoading" style="text-align:center;padding:40px;color:#999">加载中...</div>
        <div v-else-if="marketplacePlugins.length === 0" style="text-align:center;padding:40px;color:#999">
          暂无可用插件<br>
          <span style="font-size:12px">请先在后端构建并上传插件</span>
        </div>
        <div v-for="p in marketplacePlugins" :key="p.id" class="plugin-item">
          <div class="plugin-icon" :style="{ background: getColor(p.id) + '20' }">
            <div class="plugin-dot" :style="{ background: isInstalled(p.id) ? '#28A745' : '#ccc' }"></div>
          </div>
          <div class="plugin-info">
            <span class="plugin-name">{{ p.displayName }}</span>
            <span class="plugin-desc">{{ p.description }} · v{{ p.version }}</span>
          </div>
          <div class="plugin-actions">
            <button v-if="isInstalled(p.id)" class="key-badge" disabled style="color:#28A745;border-color:#28A745">已安装</button>
            <button v-else class="key-badge install-btn" @click="installFromMarket(p)">安装</button>
          </div>
        </div>
      </div>

      <div v-if="tab === 'shortcuts'" class="card-body">
        <div class="section-title">系统快捷键</div>
        <div v-for="s in builtinShortcuts" :key="s.key" class="shortcut-item">
          <span>{{ s.label }}</span>
          <button class="key-badge" @click="recordBuiltin(s)">{{ editingBuiltin === s.key ? '按下快捷键...' : s.accelerator }}</button>
        </div>
        <div class="section-title" style="margin-top:16px">插件快捷键</div>
        <div v-for="(s, i) in customShortcuts" :key="i" class="shortcut-item">
          <div class="shortcut-info">
            <span class="shortcut-cmd">{{ s.pluginId }}: {{ s.command }}</span>
            <span v-if="s.label" class="shortcut-label">{{ s.label }}</span>
          </div>
          <button class="key-badge" @click="removeShortcut(s.accelerator)">✕ {{ s.accelerator }}</button>
        </div>
        <div v-if="showAddForm" class="add-form">
          <select v-model="newBinding.pluginId">
            <option value="">选择插件</option>
            <option v-for="p in plugins" :key="p.id" :value="p.id">{{ p.manifest?.displayName || p.id }}</option>
          </select>
          <select v-model="newBinding.command">
            <option value="">选择命令</option>
            <option v-for="c in getCommands(newBinding.pluginId)" :key="c" :value="c">{{ c }}</option>
          </select>
          <button class="key-badge record-btn" @click="recording = true; recordTarget = 'custom'">
            {{ recording && recordTarget === 'custom' ? '按下快捷键...' : (newBinding.accelerator || '点击设置快捷键') }}
          </button>
          <button class="btn primary sm" @click="saveShortcut">添加</button>
        </div>
        <button v-else class="add-btn" @click="showAddForm = true">+ 添加快捷键</button>
      </div>
    </div>

    <PluginConfig v-if="configPluginId" :plugin-id="configPluginId" @close="configPluginId = ''" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import PluginConfig from './PluginConfig.vue'

const tab = ref('plugins')
const plugins = ref<any[]>([])
const marketplacePlugins = ref<any[]>([])
const marketplaceLoading = ref(false)
const builtinShortcuts = ref<any[]>([])
const showAddForm = ref(false)
const recording = ref(false)
const recordTarget = ref('')
const editingBuiltin = ref('')
const newBinding = ref<any>({ pluginId: '', command: '', accelerator: '' })
const configPluginId = ref('')

const pluginColors: Record<string, string> = { screenshot: '#28A745', 'quick-notes': '#DC3545', 'clipboard-history': '#0078D4', todo: '#FF9800', player: '#E91E63', files: '#2196F3', notes: '#FF9800', calculator: '#9C27B0', everything: '#666' }
function getColor(id: string) { return pluginColors[id] || '#666' }

async function load() {
  plugins.value = await window.mqbox.plugin.listAll()
  builtinShortcuts.value = await window.mqbox.shortcut.getBuiltin()
  customShortcuts.value = await window.mqbox.shortcut.list()
}

function getCommands(pluginId: string): string[] {
  const cmds: Record<string, string[]> = { screenshot: ['region', 'fullscreen', 'open'], todo: ['add', 'done'], player: ['play', 'pause', 'next', 'prev'], 'clipboard-history': ['copy'], 'quick-notes': ['add'] }
  return cmds[pluginId] || ['run']
}

async function togglePlugin(p: any) {
  p.enabled = !p.enabled
  await window.mqbox.plugin.setEnabled(p.id, p.enabled)
}

async function importPlugin() {
  const result = await window.mqbox.plugin.importPlugin()
  if (result?.success) {
    await load()
  }
}

async function loadMarketplace() {
  marketplaceLoading.value = true
  try {
    marketplacePlugins.value = await window.mqbox.plugin.listMarketplace()
  } catch { marketplacePlugins.value = [] }
  marketplaceLoading.value = false
}

function isInstalled(id: string) {
  return plugins.value.some(p => p.id === id)
}

async function installFromMarket(p: any) {
  const result = await window.mqbox.plugin.installFromMarket(p.id)
  if (result?.success) {
    await load()
  }
}

function openConfig(p: any) {
  configPluginId.value = p.id
}

window.mqbox?.plugin?.onUpdated(() => load())

async function removeShortcut(accelerator: string) {
  await window.mqbox.shortcut.remove(accelerator)
  customShortcuts.value = await window.mqbox.shortcut.list()
}

async function saveShortcut() {
  if (!newBinding.value.pluginId || !newBinding.value.command || !newBinding.value.accelerator) return
  await window.mqbox.shortcut.add(newBinding.value)
  customShortcuts.value = await window.mqbox.shortcut.list()
  showAddForm.value = false
  newBinding.value = { pluginId: '', command: '', accelerator: '' }
}

function recordBuiltin(s: any) {
  editingBuiltin.value = s.key
  recording.value = true
  recordTarget.value = 'builtin'
}

function onKeydown(e: KeyboardEvent) {
  if (!recording.value) return
  e.preventDefault()
  const mods: string[] = []
  if (e.ctrlKey) mods.push('Ctrl')
  if (e.altKey) mods.push('Alt')
  if (e.shiftKey) mods.push('Shift')
  if (e.metaKey) mods.push('Cmd')
  const key = e.key === ' ' ? 'Space' : e.key.length === 1 ? e.key.toUpperCase() : e.key
  const acc = [...mods, key].join('+')
  if (recordTarget.value === 'builtin') {
    window.mqbox.shortcut.updateBuiltin(editingBuiltin.value, acc)
    builtinShortcuts.value = window.mqbox.shortcut.getBuiltin()
    editingBuiltin.value = ''
  } else {
    newBinding.value.accelerator = acc
  }
  recording.value = false
}

function close() { window.close() }

onMounted(() => { load(); document.addEventListener('keydown', onKeydown) })
onUnmounted(() => { document.removeEventListener('keydown', onKeydown) })
</script>

<style scoped>
.overlay { height:100vh; display:flex; flex-direction:column; background:#fff; }
.card { flex:1; display:flex; flex-direction:column; overflow:hidden; }
.card-hd { display:flex; align-items:center; padding:12px 16px; border-bottom:1px solid #e8e8e8; }
.tabs { display:flex; gap:4px; flex:1; justify-content:center;  -webkit-app-region:drag; }
.tabs button { padding:4px 16px; border-radius:6px; border:none; background:transparent; cursor:pointer; font-size:13px; color:#666; -webkit-app-region:no-drag; }
.tabs button.active { background:#e8f4fd; color:#0078D4; font-weight:500; }
.close-btn { border:none; background:transparent; cursor:pointer; color:#999; font-size:16px; -webkit-app-region:no-drag; }
.card-body { flex:1; overflow-y:auto; padding:12px 16px; }
.plugin-item { display:flex; align-items:center; gap:10px; padding:10px 0; border-bottom:1px solid #f5f5f5; }
.plugin-icon { width:32px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; position:relative; }
.plugin-dot { width:8px; height:8px; border-radius:4px; }
.plugin-info { flex:1; }
.plugin-name { font-size:13px; font-weight:500; display:block; }
.plugin-desc { font-size:11px; color:#999; }
.plugin-actions { display:flex; align-items:center; gap:8px; }
.cfg-btn { border:none; background:transparent; cursor:pointer; font-size:16px; color:#999; padding:2px 4px; border-radius:4px; }
.cfg-btn:hover { background:#f0f0f0; color:#333; }
.switch { position:relative; width:36px; height:20px; flex-shrink:0; }
.switch input { opacity:0; width:0; height:0; }
.slider { position:absolute; cursor:pointer; inset:0; background:#ddd; border-radius:20px; transition:0.2s; }
.slider::before { content:''; position:absolute; height:16px; width:16px; left:2px; bottom:2px; background:#fff; border-radius:50%; transition:0.2s; }
.switch input:checked + .slider { background:#0078D4; }
.switch input:checked + .slider::before { transform:translateX(16px); }
.import-btn { width:100%; padding:10px; border:1px dashed #d0d0d0; border-radius:8px; background:transparent; cursor:pointer; font-size:13px; color:#999; margin-top:12px; }
.import-btn:hover { border-color:#0078D4; color:#0078D4; }
.section-title { font-size:11px; font-weight:600; color:#999; text-transform:uppercase; margin-bottom:8px; }
.shortcut-item { display:flex; justify-content:space-between; align-items:center; padding:8px 0; font-size:13px; }
.shortcut-info { }
.shortcut-cmd { font-size:13px; display:block; }
.shortcut-label { font-size:11px; color:#999; }
.key-badge { padding:4px 10px; border-radius:6px; border:1px solid #e0e0e0; background:#f5f5f5; font-size:12px; cursor:pointer; font-family:monospace; }
.key-badge:hover { border-color:#0078D4; }
.record-btn { background:#fff8e1; border-color:#FF9800; color:#FF9800; }
.add-form { display:flex; flex-direction:column; gap:8px; padding:12px; background:#f8f9fa; border-radius:8px; margin-top:8px; }
.add-form select, .add-form input { padding:6px 10px; border:1px solid #e0e0e0; border-radius:6px; font-size:12px; }
.add-btn { padding:8px; border:1px dashed #e0e0e0; border-radius:8px; background:transparent; cursor:pointer; font-size:13px; color:#999; width:100%; margin-top:8px; }
.add-btn:hover { border-color:#0078D4; color:#0078D4; }
.btn { padding:6px 16px; border-radius:6px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; font-size:12px; }
.btn.primary { background:#0078D4; color:#fff; border-color:#0078D4; }
.btn.sm { padding:4px 12px; font-size:11px; }
</style>
