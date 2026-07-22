<template>
  <div class="page" v-if="component">
    <component :is="component" :data="pageData" :execute="execute" :close="close" :refresh="refresh" />
  </div>
  <div v-else class="empty">
    <h2>{{ pluginId }}</h2>
    <p>插件页面加载中...</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, defineAsyncComponent } from 'vue'

const params = new URLSearchParams(window.location.search)
const pluginId = ref(params.get('pluginId') || '')
const pageData = ref<any>({})
const component = ref<any>(null)

const pageComponents: Record<string, any> = {
  'todo': defineAsyncComponent(() => import('@plugins/todo/src/Page.vue')),
  'quick-notes': defineAsyncComponent(() => import('@plugins/quick-notes/src/Page.vue')),
  'clipboard-history': defineAsyncComponent(() => import('@plugins/clipboard-history/src/Page.vue')),
  'player': defineAsyncComponent(() => import('@plugins/player/src/Page.vue')),
  'remote': defineAsyncComponent(() => import('@plugins/remote/src/Page.vue')),
  'schedule': defineAsyncComponent(() => import('@plugins/schedule/src/Page.vue')),
  'screenshot': defineAsyncComponent(() => import('@plugins/screenshot/src/Page.vue')),
  'calculator': defineAsyncComponent(() => import('@plugins/calculator/src/Page.vue')),
  'ai-chat': defineAsyncComponent(() => import('@plugins/ai-chat/src/Page.vue')),
  'files': defineAsyncComponent(() => import('@plugins/files/src/Page.vue')),
  'notes': defineAsyncComponent(() => import('@plugins/notes/src/Page.vue')),
}

async function load() {
  component.value = pageComponents[pluginId.value] || null
  if (!component.value) return
  try {
    const data = await window.mqbox?.plugin.execute(pluginId.value, 'getPageData') || {}
    pageData.value = data
  } catch {}
}

function execute(command: string, args?: unknown) {
  return window.mqbox?.plugin.execute(pluginId.value, command, args || {})
}

function refresh() { load() }
function close() { window.close() }

onMounted(load)
</script>

<style scoped>
.page { height:100vh; }
.empty { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; color:#909399; }
</style>
