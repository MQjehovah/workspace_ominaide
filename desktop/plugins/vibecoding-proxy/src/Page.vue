<template>
  <div class="vibe-page">
    <header class="vibe-header">
      <div class="vibe-title">
        <h1>VibeCoding</h1>
        <p>按项目组织编程会话 · 本机与跨设备</p>
      </div>
    </header>

    <SessionsPanel :execute="execute" :projects="projects" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import SessionsPanel from './SessionsPanel.vue'

const { execute } = defineProps<{ data: any; execute: Function; close: Function }>()

const projects = ref<any[]>([])

async function loadProjects() {
  projects.value = (await execute('getProjects').catch(() => [])) || []
}

onMounted(loadProjects)
</script>

<style scoped>
.vibe-page {
  padding: 18px 20px 24px;
  font-family: 'Segoe UI', sans-serif;
  color: #1e293b;
  max-width: 1280px;
  margin: 0 auto;
}
.vibe-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.vibe-title h1 {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 3px;
}
.vibe-title p {
  margin: 0;
  font-size: 11px;
  color: #94a3b8;
}
</style>
