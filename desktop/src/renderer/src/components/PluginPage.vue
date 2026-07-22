<script setup lang="ts">
import { ref, onMounted } from 'vue'

const params = new URLSearchParams(window.location.search)
const pluginId = ref(params.get('pluginId') || '')

function openInNewWindow() {
  window.mqbox?.window.openPluginWindow(pluginId.value)
}

onMounted(() => {
  // Auto-navigate to the plugin window
  if (pluginId.value) {
    window.mqbox?.window.openPluginWindow(pluginId.value)
    window.close()
  }
})
</script>

<template>
  <div class="page">
    <div class="empty" v-if="pluginId">
      <h2>{{ pluginId }}</h2>
      <p>正在打开插件窗口...</p>
      <button @click="openInNewWindow">手动打开</button>
    </div>
    <div class="empty" v-else>
      <h2>插件页面</h2>
      <p>未指定插件 ID</p>
    </div>
  </div>
</template>

<style scoped>
.page { height:100vh; display:flex; align-items:center; justify-content:center; }
.empty { text-align:center; color:#909399; }
.empty button { margin-top:12px; padding:6px 16px; border-radius:6px; border:1px solid #e0e0e0; background:#fff; cursor:pointer; }
.empty button:hover { background:#f5f5f5; }
</style>
