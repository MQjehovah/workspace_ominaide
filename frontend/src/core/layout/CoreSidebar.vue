<template>
  <el-menu
    :default-active="route.path"
    :collapse="collapsed"
    :router="true"
    style="height:100vh; border-right:1px solid #dcdfe6; overflow-y:auto; display:flex; flex-direction:column"
  >
    <div style="padding:16px; text-align:center; font-weight:700; font-size:16px; border-bottom:1px solid #ebeef5">
      <span v-if="!collapsed">OmniAide</span>
      <span v-else>OA</span>
    </div>

    <!-- Plugin Apps (dynamic from store) -->
    <template v-if="pluginStore.installed.length">
      <el-divider style="margin:8px 0">
        <span style="font-size:12px; color:#909399">应用</span>
      </el-divider>
      <el-menu-item
        v-for="p in pluginStore.installed"
        :key="p.name"
        :index="p.routes.main"
      >
        <el-icon><component :is="p.icon" /></el-icon>
        <span>{{ p.title }}</span>
      </el-menu-item>
    </template>

    <!-- Admin group -->
    <template v-if="auth.user">
      <el-divider style="margin:8px 0">
        <span style="font-size:12px; color:#909399">管理</span>
      </el-divider>
      <el-menu-item index="/admin/users">
        <el-icon><User /></el-icon>
        <span>用户管理</span>
      </el-menu-item>
      <el-menu-item index="/admin/plugins">
        <el-icon><Grid /></el-icon>
        <span>插件管理</span>
      </el-menu-item>
    </template>

    <!-- Spacer + User + Settings at bottom -->
    <div style="flex:1"></div>
    <el-dropdown v-if="auth.user" trigger="click" @command="handleUserCmd">
      <el-menu-item style="cursor:pointer">
        <el-icon><User /></el-icon>
        <span>{{ auth.user.username }}</span>
      </el-menu-item>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="profile"><el-icon><Setting /></el-icon>个人中心</el-dropdown-item>
          <el-dropdown-item command="logout" divided style="color:#f56c6c"><el-icon><SwitchButton /></el-icon>退出登录</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
    <el-menu-item index="/settings" v-else>
      <el-icon><Setting /></el-icon>
      <span>设置</span>
    </el-menu-item>
  </el-menu>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { Setting, User, SwitchButton, Grid } from '@element-plus/icons-vue'
import { usePluginStore } from '@/stores/core/plugin'
import { useAuthStore } from '@/stores/auth'

defineProps<{ collapsed: boolean }>()
const route = useRoute()
const router = useRouter()
const pluginStore = usePluginStore()
const auth = useAuthStore()

function handleUserCmd(cmd: string) {
  if (cmd === 'profile') router.push('/settings')
  else if (cmd === 'logout') { auth.logout(); router.push('/login') }
}
</script>
