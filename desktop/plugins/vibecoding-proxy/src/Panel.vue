<template>
  <div class="devops-panel">
    <div v-if="!data" class="loading">加载中...</div>
    <template v-else>
      <div class="section">
        <div class="section-title">快速操作</div>
        <button class="action-btn" @click="execute('scanDir')">
          <span class="icon">🔍</span> 扫描项目
        </button>
        <button class="action-btn" @click="execute('open')">
          <span class="icon">📂</span> 项目管理器
        </button>
      </div>

      <div class="section">
        <div class="section-title">最近项目</div>
        <div v-for="p in data.recentProjects" :key="p.path" class="project-item" @click="execute('openProject', { path: p.path })">
          <span class="project-type">{{ typeIcon(p.type) }}</span>
          <div class="project-info">
            <div class="project-name">{{ p.name }}</div>
            <div class="project-meta">{{ p.type }} · {{ p.hasGit ? '✓ git' : 'no git' }}</div>
          </div>
        </div>
        <div v-if="!data.recentProjects?.length" class="empty-hint">暂无项目，点击扫描</div>
      </div>

      <div class="section">
        <div class="section-title">AI 工具</div>
        <div class="tool-status">
          <span :class="['dot', data.tools?.opencode ? 'online' : 'offline']"></span>
          opencode {{ data.tools?.opencode ? '可用' : '未安装' }}
        </div>
        <div class="tool-status">
          <span :class="['dot', data.tools?.claude ? 'online' : 'offline']"></span>
          claude {{ data.tools?.claude ? '可用' : '未安装' }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{ data: any; execute: Function; openPage: Function; refresh: Function }>()

function typeIcon(type: string) {
  const map: Record<string, string> = { node: '🟢', python: '🐍', rust: '🦀', go: '🔵', dotnet: '🟣', other: '📁' }
  return map[type] || '📁'
}
</script>

<style scoped>
.devops-panel{padding:8px;font-size:12px;color:#333}
.loading{text-align:center;padding:20px;color:#999}
.section{margin-bottom:12px}
.section-title{font-weight:600;font-size:11px;color:#666;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px}
.action-btn{display:flex;align-items:center;gap:6px;width:100%;padding:8px 10px;border:none;border-radius:6px;background:transparent;color:#444;font-size:12px;cursor:pointer;margin-bottom:4px;text-align:left}
.action-btn:hover{background:#f0f4ff;color:#333}
.icon{font-size:14px}
.project-item{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:6px;cursor:pointer}
.project-item:hover{background:#f0f4ff}
.project-type{font-size:14px}
.project-info{flex:1;min-width:0}
.project-name{font-size:12px;font-weight:500;color:#333;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.project-meta{font-size:10px;color:#999;margin-top:1px}
.empty-hint{font-size:11px;color:#bbb;text-align:center;padding:8px}
.tool-status{display:flex;align-items:center;gap:6px;padding:4px 0;font-size:11px;color:#666}
.dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.dot.online{background:#4CAF50}
.dot.offline{background:#ccc}
</style>
