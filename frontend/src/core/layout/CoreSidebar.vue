<template>
  <div class="sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <div class="brand-mark">O</div>
      <div class="brand-text" v-if="!collapsed">
        <span class="logo-text">OmniAide</span>
        <span class="logo-sub">SELF-HOSTED</span>
      </div>
    </div>

    <el-menu
      ref="menuRef"
      :default-active="route.path"
      :collapse="collapsed"
      :router="true"
      :default-openeds="defaultOpeneds"
      class="sidebar-menu"
    >
      <el-sub-menu index="workspace">
        <template #title>
          <el-icon><HomeFilled /></el-icon>
          <span>工作台</span>
        </template>
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatLineRound /></el-icon>
          <span>对话</span>
        </el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="info">
        <template #title>
          <el-icon><Message /></el-icon>
          <span>信息</span>
        </template>
        <el-menu-item index="/mail">
          <el-icon><Message /></el-icon>
          <span>邮件</span>
        </el-menu-item>
        <el-menu-item index="/rss">
          <el-icon><Promotion /></el-icon>
          <span>资讯</span>
        </el-menu-item>
        <el-menu-item index="/schedule">
          <el-icon><Calendar /></el-icon>
          <span>日程</span>
        </el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="content">
        <template #title>
          <el-icon><Folder /></el-icon>
          <span>内容与项目</span>
        </template>
        <el-menu-item index="/notes">
          <el-icon><Document /></el-icon>
          <span>笔记</span>
        </el-menu-item>
        <el-menu-item index="/files">
          <el-icon><FolderOpened /></el-icon>
          <span>文件</span>
        </el-menu-item>
        <el-menu-item index="/projects">
          <el-icon><Cpu /></el-icon>
          <span>项目</span>
        </el-menu-item>
        <el-menu-item index="/device">
          <el-icon><Cellphone /></el-icon>
          <span>设备</span>
        </el-menu-item>
      </el-sub-menu>

      <el-sub-menu index="mine">
        <template #title>
          <el-icon><UserFilled /></el-icon>
          <span>我的与管理</span>
        </template>
        <el-menu-item index="/about">
          <el-icon><User /></el-icon>
          <span>关于我</span>
        </el-menu-item>
        <el-menu-item index="/insights">
          <el-icon><Sunrise /></el-icon>
          <span>每日回顾</span>
        </el-menu-item>
        <el-menu-item index="/activities">
          <el-icon><TrendCharts /></el-icon>
          <span>活动</span>
        </el-menu-item>
        <div class="sub-divider"></div>
        <div class="sub-label" v-if="!collapsed">系统管理</div>
        <el-menu-item index="/bots">
          <el-icon><ChatDotRound /></el-icon>
          <span>助手管理</span>
        </el-menu-item>
        <el-menu-item index="/mcp">
          <el-icon><Connection /></el-icon>
          <span>MCP 管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/plugins">
          <el-icon><Monitor /></el-icon>
          <span>插件市场</span>
        </el-menu-item>
        <el-menu-item index="/admin/users">
          <el-icon><Setting /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
      </el-sub-menu>
    </el-menu>

    <div class="sidebar-footer">
      <el-dropdown v-if="auth.user" trigger="click" @command="handleCmd">
        <div class="user-btn">
          <el-avatar :size="30">{{ displayName[0]?.toUpperCase() }}</el-avatar>
          <div class="user-meta" v-if="!collapsed">
            <span class="user-name">{{ displayName }}</span>
            <span class="user-role">本地私有化部署</span>
          </div>
        </div>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="settings"><el-icon><Setting /></el-icon>设置</el-dropdown-item>
            <el-dropdown-item command="logout" divided><el-icon><SwitchButton /></el-icon>退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Folder, FolderOpened, Document, User, UserFilled, Monitor, Setting, SwitchButton,
  DataAnalysis, Calendar, Promotion, TrendCharts, Cellphone, Cpu, ChatDotRound,
  Sunrise, Message, ChatLineRound, Connection, HomeFilled,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

defineProps<{ collapsed: boolean }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const displayName = computed(() => auth.user?.username || auth.user?.email || '用户')

const menuRef = ref<any>(null)
const defaultOpeneds = ref<string[]>(['workspace'])
const parentGroups: Record<string, string> = {
  '/dashboard': 'workspace', '/chat': 'workspace',
  '/mail': 'info', '/rss': 'info', '/schedule': 'info',
  '/notes': 'content', '/files': 'content', '/projects': 'content', '/device': 'content',
  '/about': 'mine', '/insights': 'mine', '/activities': 'mine',
  '/bots': 'mine', '/mcp': 'mine', '/admin/plugins': 'mine', '/admin/users': 'mine',
}

watch(() => route.path, (path) => {
  const group = parentGroups[path]
  if (!group) return
  if (!defaultOpeneds.value.includes(group)) defaultOpeneds.value.push(group)
  nextTick(() => menuRef.value?.open?.(group))
}, { immediate: true })

function handleCmd(cmd: string) {
  if (cmd === 'settings') router.push('/settings')
  else if (cmd === 'logout') { auth.logout(); router.push('/login') }
}
</script>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  background:
    radial-gradient(600px 240px at 20% -10%, rgba(99, 102, 241, .22), transparent 60%),
    linear-gradient(180deg, #0b1220 0%, #0e1629 55%, #111c33 100%);
  border-right: 1px solid rgba(255, 255, 255, .05);
  display: flex;
  flex-direction: column;
  transition: width .2s ease;
  overflow: hidden;
  flex-shrink: 0;
}
.sidebar.collapsed { width: var(--sidebar-collapsed-width); }

.sidebar-header {
  height: var(--header-height);
  display: flex; align-items: center; gap: 10px;
  padding: 0 16px; flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, .05);
}
.sidebar.collapsed .sidebar-header { justify-content: center; padding: 0; }
.brand-mark {
  width: 30px; height: 30px; border-radius: 9px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 800; color: #fff;
  background: linear-gradient(135deg, #6366f1, #a855f7);
  box-shadow: 0 6px 16px -8px rgba(99, 102, 241, .9);
}
.brand-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.logo-text { font-size: 15px; font-weight: 700; color: #fff; letter-spacing: .3px; }
.logo-sub { font-size: 9px; letter-spacing: 1.6px; color: #64748b; }

.sidebar-menu { flex: 1; background: transparent; border-right: none; padding: 10px 0; overflow-y: auto; overflow-x: hidden; }
.sidebar-menu::-webkit-scrollbar { width: 4px; }

.sidebar-menu :deep(.el-sub-menu__title) {
  color: #cbd5e1;
  height: 42px; line-height: 42px;
  margin: 3px 10px; border-radius: 9px;
  font-size: 13px; font-weight: 500;
  transition: background .15s, color .15s;
}
.sidebar-menu :deep(.el-sub-menu__title:hover) { background: rgba(255, 255, 255, .06); color: #f1f5f9; }
.sidebar-menu :deep(.el-sub-menu.is-active > .el-sub-menu__title) { color: #fff; }
.sidebar-menu :deep(.el-sub-menu.is-active > .el-sub-menu__title .el-icon) { color: #a5b4fc; }

.sidebar-menu :deep(.el-menu-item) {
  position: relative;
  color: var(--color-sidebar-text);
  height: 36px; line-height: 36px;
  margin: 1px 10px; border-radius: 8px;
  font-size: 12.5px;
  transition: background .15s, color .15s;
}
.sidebar-menu :deep(.el-sub-menu .el-menu-item) { padding-left: 40px !important; }
.sidebar-menu :deep(.el-menu-item:hover) { background: rgba(255, 255, 255, .06); color: #e2e8f0; }
.sidebar-menu :deep(.el-menu-item.is-active) {
  background: rgba(99, 102, 241, .18);
  color: #fff; font-weight: 500;
}
.sidebar-menu :deep(.el-menu-item.is-active::before) {
  content: '';
  position: absolute; left: -10px; top: 50%; transform: translateY(-50%);
  width: 3px; height: 16px; border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg, #818cf8, #a855f7);
}
.sidebar-menu :deep(.el-menu-item .el-icon),
.sidebar-menu :deep(.el-sub-menu__title .el-icon) {
  font-size: 16px; margin-right: 10px; color: #7c8aa5;
  transition: color .15s;
}
.sidebar-menu :deep(.el-menu-item:hover .el-icon),
.sidebar-menu :deep(.el-sub-menu__title:hover .el-icon) { color: #c7d2fe; }
.sidebar-menu :deep(.el-menu-item.is-active .el-icon) { color: #a5b4fc; }
.sidebar-menu :deep(.el-sub-menu .el-menu) { background: transparent; }
.sidebar-menu :deep(.el-sub-menu__icon-arrow) { font-size: 11px; opacity: .45; }

.sidebar.collapsed .sidebar-menu :deep(.el-menu-item),
.sidebar.collapsed .sidebar-menu :deep(.el-sub-menu__title) { margin: 3px 9px; }
.sidebar.collapsed .sidebar-menu :deep(.el-menu-item .el-icon),
.sidebar.collapsed .sidebar-menu :deep(.el-sub-menu__title .el-icon) { margin-right: 0; }

.sub-divider { height: 1px; background: rgba(255, 255, 255, .07); margin: 8px 18px; }
.sub-label {
  font-size: 10px; font-weight: 600; letter-spacing: 1px;
  color: #5b6b85; padding: 4px 24px 6px;
}

.sidebar-footer {
  border-top: 1px solid rgba(255, 255, 255, .06);
  padding: 10px;
  flex-shrink: 0;
}
.sidebar-footer :deep(.el-dropdown) { display: block; width: 100%; }
.user-btn {
  display: flex; align-items: center; gap: 10px; cursor: pointer;
  padding: 7px 8px; border-radius: 10px;
  transition: background .15s;
}
.user-btn:hover { background: rgba(255, 255, 255, .06); }
.user-btn :deep(.el-avatar) {
  background: linear-gradient(135deg, #4f46e5, #7c3aed);
  font-size: 12px; flex-shrink: 0;
}
.user-meta { display: flex; flex-direction: column; min-width: 0; gap: 1px; }
.user-name { font-size: 12.5px; color: #e2e8f0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.user-role { font-size: 10px; color: #64748b; white-space: nowrap; }
.sidebar.collapsed .user-btn { justify-content: center; padding: 6px 0; }
</style>
