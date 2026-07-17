<template>
  <el-container style="height:100vh">
    <CoreSidebar :collapsed="sidebarCollapsed" @toggle="sidebarCollapsed = !sidebarCollapsed" />
    <el-container>
      <CoreHeader @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed" />
      <el-main style="background:#f5f7fa; padding:20px">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import CoreSidebar from './CoreSidebar.vue'
import CoreHeader from './CoreHeader.vue'
import { usePluginStore } from '@/stores/core/plugin'
import { fetchPlugins } from '@/api/plugin'

const sidebarCollapsed = ref(false)
const pluginStore = usePluginStore()

onMounted(async () => {
  try {
    const plugins = await fetchPlugins()
    for (const p of plugins) {
      pluginStore.register({
        name: p.name,
        title: p.title,
        icon: p.icon || 'Connection',
        description: p.description || undefined,
        version: p.version,
        routes: { main: `/apps/${p.name}` }
      })
    }
  } catch (e) {
    console.warn('Failed to fetch plugins:', e)
  }
})
</script>
