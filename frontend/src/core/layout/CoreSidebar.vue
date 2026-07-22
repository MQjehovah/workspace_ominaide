<template>
  <div class="sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <span class="logo-text" v-if="!collapsed">OmniAide</span>
      <span class="logo-text" v-else>OA</span>
    </div>

    <el-menu
      :default-active="route.path"
      :collapse="collapsed"
      :router="true"
      class="sidebar-menu"
    >
      <el-menu-item index="/files">
        <el-icon><Folder /></el-icon>
        <span>文件</span>
      </el-menu-item>
      <el-menu-item index="/notes">
        <el-icon><Document /></el-icon>
        <span>笔记</span>
      </el-menu-item>
      <el-menu-item index="/workspaces">
        <el-icon><Grid /></el-icon>
        <span>工作区</span>
      </el-menu-item>

      <div class="menu-divider"></div>
      <div class="menu-label" v-if="!collapsed">管理</div>
      <el-menu-item index="/admin/users">
        <el-icon><User /></el-icon>
        <span>用户管理</span>
      </el-menu-item>
      <el-menu-item index="/admin/plugins">
        <el-icon><Monitor /></el-icon>
        <span>插件市场</span>
      </el-menu-item>
    </el-menu>

    <div class="sidebar-footer">
      <el-dropdown v-if="auth.user" trigger="click" @command="handleCmd">
        <div class="user-btn">
          <el-avatar :size="32">{{ auth.user.username[0]?.toUpperCase() }}</el-avatar>
          <span class="user-name" v-if="!collapsed">{{ auth.user.username }}</span>
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
import { useRoute, useRouter } from 'vue-router'
import { Folder, Document, Grid, User, Monitor, Setting, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

defineProps<{ collapsed: boolean }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

function handleCmd(cmd: string) {
  if (cmd === 'settings') router.push('/settings')
  else if (cmd === 'logout') { auth.logout(); router.push('/login') }
}
</script>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  background: var(--color-sidebar);
  display: flex;
  flex-direction: column;
  transition: width .2s;
  overflow: hidden;
  flex-shrink: 0;
}
.sidebar.collapsed { width: var(--sidebar-collapsed-width); }
.sidebar-header { height: var(--header-height); display: flex; align-items: center; justify-content: center; border-bottom: 1px solid rgba(255,255,255,.06); }
.logo-text { font-size: 18px; font-weight: 700; color: #fff; letter-spacing: 1px; }
.sidebar-menu { flex: 1; background: transparent; border-right: none; padding: 8px 0; }
.sidebar-menu :deep(.el-menu-item) { color: var(--color-sidebar-text); height: 44px; line-height: 44px; margin: 2px 8px; border-radius: 8px; font-size: 13px; }
.sidebar-menu :deep(.el-menu-item:hover) { background: var(--color-sidebar-hover); color: #fff; }
.sidebar-menu :deep(.el-menu-item.is-active) { background: var(--color-sidebar-active); color: var(--color-sidebar-active-text); }
.sidebar-menu :deep(.el-menu-item .el-icon) { font-size: 18px; margin-right: 10px; }
.sidebar.collapsed :deep(.el-menu-item .el-icon) { margin-right: 0; }
.menu-divider { height: 1px; background: rgba(255,255,255,.06); margin: 8px 12px; }
.menu-label { font-size: 11px; font-weight: 600; color: var(--color-sidebar-text); text-transform: uppercase; letter-spacing: .5px; padding: 8px 16px 4px; }
.sidebar-footer { border-top: 1px solid rgba(255,255,255,.06); padding: 12px; }
.user-btn { display: flex; align-items: center; gap: 10px; cursor: pointer; padding: 4px; border-radius: 8px; }
.user-btn:hover { background: var(--color-sidebar-hover); }
.user-name { font-size: 13px; color: var(--color-sidebar-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sidebar.collapsed .user-name { display: none; }
</style>
