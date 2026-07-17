<template>
  <el-menu
    :default-active="route.path"
    :collapse="collapsed"
    :router="true"
    style="height:100vh; border-right:1px solid #dcdfe6; overflow-y:auto"
  >
    <div style="padding:16px; text-align:center; font-weight:700; font-size:16px; border-bottom:1px solid #ebeef5">
      <span v-if="!collapsed">OmniAide</span>
      <span v-else>OA</span>
    </div>

    <!-- Core Navigation -->
    <el-menu-item index="/files">
      <el-icon><Folder /></el-icon>
      <span>文件</span>
    </el-menu-item>
    <el-menu-item index="/workspaces">
      <el-icon><Management /></el-icon>
      <span>工作空间</span>
    </el-menu-item>

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

    <!-- Settings at bottom -->
    <div style="position:absolute; bottom:0; width:100%">
      <el-menu-item index="/settings">
        <el-icon><Setting /></el-icon>
        <span>设置</span>
      </el-menu-item>
    </div>
  </el-menu>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import { Folder, Management, Setting } from '@element-plus/icons-vue'
import { usePluginStore } from '@/stores/core/plugin'

defineProps<{ collapsed: boolean }>()
const route = useRoute()
const pluginStore = usePluginStore()
</script>
