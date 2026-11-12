<template>
  <div class="vibe-page">
    <header class="vibe-header">
      <div class="vibe-title">
        <h1>VibeCoding</h1>
        <p>多 Agent 会话 · OpenCode 2 / Codex / Claude Code</p>
      </div>
      <button class="btn" @click="showProjects = true">
        📂 项目管理
        <span v-if="projects.length" class="count">{{ projects.length }}</span>
      </button>
    </header>

    <SessionsPanel
      :key="projectVersion"
      :execute="execute"
      :projects="projects"
    />

    <ProjectManager
      v-if="showProjects"
      :execute="execute"
      @close="closeProjectManager"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import SessionsPanel from './SessionsPanel.vue'
import ProjectManager from './ProjectManager.vue'

const { execute } = defineProps<{ data: any; execute: Function; close: Function }>()

const projects = ref<any[]>([])
const showProjects = ref(false)
const projectVersion = ref(0)

async function loadProjects() {
  projects.value = (await execute('getProjects').catch(() => [])) || []
}

async function closeProjectManager() {
  showProjects.value = false
  await loadProjects()
  projectVersion.value += 1
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
.btn {
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #fff;
  color: #475569;
  font-size: 12px;
  cursor: pointer;
}
.btn:hover {
  background: #f8fafc;
}
.count {
  display: inline-block;
  margin-left: 4px;
  padding: 0 5px;
  border-radius: 7px;
  background: #eef2ff;
  color: #4f46e5;
  font-size: 10px;
}
</style>
