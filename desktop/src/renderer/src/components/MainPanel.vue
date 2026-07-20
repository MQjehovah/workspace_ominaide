<template>
  <div class="main-panel">
    <div class="header">
      <span class="title">OmniAide</span>
      <el-button text circle @click="openSearch" title="搜索 (Alt+Space)">
        <el-icon><Search /></el-icon>
      </el-button>
    </div>

    <div class="panels">
      <div v-for="panel in store.panels" :key="panel.id" class="panel-item">
        <div class="panel-header">
          <span class="panel-title">{{ panel.pluginId }}</span>
          <el-button text size="small" @click="openPage(panel.pluginId)">›</el-button>
        </div>
        <div class="panel-body">
          <div v-if="panel.data?.pendingCount !== undefined" class="stat-row">
            <span class="stat-value">{{ panel.data.pendingCount }}</span>
            <span class="stat-label">待处理</span>
          </div>
          <div v-if="panel.data?.items?.length" class="mini-list">
            <div v-for="item in panel.data.items.slice(0,4)" :key="item.id" class="mini-item" @click="execute(panel.pluginId, 'done', { id: item.id })">
              <span class="dot" :style="{ background: getPriorityColor(item.priority) }" />
              <span class="text">{{ item.text || item.title }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-if="!store.panels.length" class="empty">
        <p>暂无面板</p>
      </div>
    </div>

    <div class="footer">
      <el-button text size="small" @click="openSearch">
        <el-icon><Search /></el-icon> 搜索
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { usePluginStore } from '../stores/plugin'

const store = usePluginStore()

onMounted(() => store.loadPlugins())

function openSearch() { window.mqbox.window.openSearch() }
function openPage(pluginId: string) { window.mqbox.window.openPage(pluginId) }
function execute(pluginId: string, cmd: string, args?: unknown) {
  store.executeCommand(pluginId, cmd, args).then(() => store.loadPlugins())
}
function getPriorityColor(p: string) {
  if (p === 'high') return '#E53935'
  if (p === 'low') return '#4CAF50'
  return '#FF9800'
}
</script>

<style scoped>
.main-panel { height:100vh; display:flex; flex-direction:column; background:#f5f7fa; }
.header { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; background:#fff; border-bottom:1px solid #e4e7ed; -webkit-app-region:drag; }
.title { font-size:16px; font-weight:700; }
.panels { flex:1; overflow-y:auto; padding:12px; display:flex; flex-direction:column; gap:12px; }
.panel-item { background:#fff; border-radius:10px; padding:12px; box-shadow:0 1px 3px rgba(0,0,0,0.06); }
.panel-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
.panel-title { font-size:13px; font-weight:600; color:#303133; }
.panel-body { font-size:12px; }
.stat-row { display:flex; align-items:baseline; gap:6px; padding:8px 0; }
.stat-value { font-size:28px; font-weight:700; color:#409EFF; }
.stat-label { color:#909399; }
.mini-list { display:flex; flex-direction:column; gap:4px; }
.mini-item { display:flex; align-items:center; gap:6px; padding:6px 8px; border-radius:6px; cursor:pointer; transition:background 0.15s; }
.mini-item:hover { background:#f5f7fa; }
.dot { width:6px; height:6px; border-radius:50%; flex-shrink:0; }
.text { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; color:#606266; }
.empty { text-align:center; padding:40px; color:#c0c4cc; }
.footer { padding:8px 16px; border-top:1px solid #e4e7ed; background:#fff; display:flex; gap:8px; }
</style>
