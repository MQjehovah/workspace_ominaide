<template>
  <div class="main-panel">
    <div class="header" style="-webkit-app-region:drag">
      <span class="title">OmniAide</span>
      <el-button text circle @click="openSearch" title="搜索">
        <el-icon><Search /></el-icon>
      </el-button>
    </div>

    <div class="panels">
      <div v-for="p in panels" :key="p.id" class="panel-item">
        <div class="panel-header">
          <span class="panel-title">{{ p.manifest?.displayName || p.pluginId }}</span>
          <el-button text size="small" @click="openPage(p.pluginId)">›</el-button>
        </div>
        <div class="panel-body">
          <component
            :is="getComponent(p.pluginId)"
            :data="panelData[p.pluginId]"
            :execute="(cmd: string, args?: any) => execute(p.pluginId, cmd, args)"
            :open-page="() => openPage(p.pluginId)"
            :refresh="() => loadPanels()"
          />
        </div>
      </div>
      <div v-if="!panels.length" class="empty">暂无面板</div>
    </div>

    <div class="footer">
      <el-button text size="small" @click="openSearch"><el-icon><Search /></el-icon> 搜索</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, defineAsyncComponent } from 'vue'
import { Search } from '@element-plus/icons-vue'

const panels = ref<any[]>([])
const panelData = ref<Record<string, any>>({})

const pluginComponents: Record<string, any> = {
  todo: defineAsyncComponent(() => import('@plugins/todo/src/Panel.vue')),
  'quick-notes': defineAsyncComponent(() => import('@plugins/quick-notes/src/Panel.vue')),
  'clipboard-history': defineAsyncComponent(() => import('@plugins/clipboard-history/src/Panel.vue')),
  player: defineAsyncComponent(() => import('@plugins/player/src/Panel.vue')),
  screenshot: defineAsyncComponent(() => import('@plugins/screenshot/src/Panel.vue')),
  calculator: defineAsyncComponent(() => import('@plugins/calculator/src/Panel.vue')),
}

function getComponent(pluginId: string) {
  return pluginComponents[pluginId]
}

async function loadPanels() {
  const list = await window.mqbox.plugin.list()
  const panelList = await window.mqbox.plugin.getPanels()
  panels.value = panelList.map((p: any) => ({ ...p, manifest: list.find((l: any) => l.id === p.pluginId)?.manifest }))
  for (const p of panelList) {
    const data = await window.mqbox.plugin.execute(p.pluginId, 'getPanelData')
    if (data) panelData.value[p.pluginId] = data
  }
}

function openSearch() { window.mqbox.window.openSearch() }
function openPage(pluginId: string) { window.mqbox.window.openPage(pluginId) }
async function execute(pluginId: string, cmd: string, args?: unknown) {
  await window.mqbox.plugin.execute(pluginId, cmd, args)
  loadPanels()
}

onMounted(loadPanels)
</script>

<style scoped>
.main-panel { height:100vh; display:flex; flex-direction:column; background:#f5f7fa; }
.header { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; background:#fff; border-bottom:1px solid #e4e7ed; }
.title { font-size:16px; font-weight:700; }
.panels { flex:1; overflow-y:auto; padding:12px; display:flex; flex-direction:column; gap:12px; }
.panel-item { background:#fff; border-radius:10px; padding:12px; box-shadow:0 1px 3px rgba(0,0,0,0.06); }
.panel-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.panel-title { font-size:13px; font-weight:600; color:#303133; }
.panel-body { font-size:12px; }
.empty { text-align:center; padding:40px; color:#c0c4cc; }
.footer { padding:8px 16px; border-top:1px solid #e4e7ed; background:#fff; }
</style>
