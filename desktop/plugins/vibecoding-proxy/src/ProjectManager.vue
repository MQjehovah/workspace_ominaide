<template>
  <div class="mask" @click.self="$emit('close')">
    <div class="dialog">
      <div class="dialog-head">
        <h3>项目管理</h3>
        <button class="close" @click="$emit('close')">✕</button>
      </div>
      <p class="hint">
        会话需要项目目录。这里只负责添加 / 扫描 / 移除目录，不再绑定飞书或启动常驻 Agent。
      </p>
      <div class="actions">
        <button class="btn primary" @click="addDirectory">＋ 添加目录</button>
        <button class="btn" :disabled="scanning" @click="scanCommon">
          {{ scanning ? '扫描中…' : '🔍 扫描常用目录' }}
        </button>
      </div>
      <div class="list">
        <div v-for="p in projects" :key="p.path" class="row">
          <div class="row-text">
            <div class="row-name">{{ p.name }}</div>
            <div class="row-path">{{ p.path }}</div>
          </div>
          <button class="row-del" title="移除" @click="removeProject(p)">🗑</button>
        </div>
        <div v-if="!projects.length" class="empty">
          还没有项目，先添加目录或扫描常用目录。
        </div>
      </div>
      <div class="dialog-foot">
        <span class="foot-hint">共 {{ projects.length }} 个项目</span>
        <button class="btn" @click="$emit('close')">完成</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

const props = defineProps<{ execute: Function }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const projects = ref<any[]>([])
const scanning = ref(false)

async function load() {
  projects.value = (await props.execute('getProjects').catch(() => [])) || []
}

async function addDirectory() {
  const win = window as any
  let dir = ''
  if (win.mqbox?.dialog?.selectFolder) {
    dir = await win.mqbox.dialog.selectFolder()
  }
  if (!dir) return
  await props.execute('addProject', { dir }).catch(() => null)
  await load()
}

async function scanCommon() {
  scanning.value = true
  try {
    const result = await props.execute('scanDir').catch(() => null)
    if (Array.isArray(result)) projects.value = result
    else await load()
  } finally {
    scanning.value = false
  }
}

async function removeProject(project: any) {
  if (!confirm(`从列表移除「${project.name}」？不会删除磁盘上的文件。`)) return
  await props.execute('removeProject', { path: project.path }).catch(() => null)
  await load()
}

onMounted(load)
</script>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 70;
}
.dialog {
  width: 560px;
  max-width: 92vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: 0 16px 48px rgba(15, 23, 42, 0.25);
}
.dialog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.dialog-head h3 {
  margin: 0;
  font-size: 15px;
  color: #1e293b;
}
.close {
  border: none;
  background: transparent;
  font-size: 16px;
  color: #94a3b8;
  cursor: pointer;
}
.hint {
  font-size: 11px;
  color: #94a3b8;
  line-height: 1.6;
  margin: 4px 0 12px;
}
.actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
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
.btn.primary {
  background: #4f46e5;
  border-color: #4f46e5;
  color: #fff;
}
.btn:disabled {
  opacity: 0.6;
  cursor: default;
}
.list {
  flex: 1;
  overflow-y: auto;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  min-height: 120px;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-bottom: 1px solid #f1f5f9;
}
.row:last-child {
  border-bottom: none;
}
.row-text {
  flex: 1;
  min-width: 0;
}
.row-name {
  font-size: 12.5px;
  font-weight: 600;
  color: #1e293b;
}
.row-path {
  font-size: 10.5px;
  color: #94a3b8;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-del {
  border: none;
  background: transparent;
  cursor: pointer;
  opacity: 0.5;
}
.row-del:hover {
  opacity: 1;
}
.empty {
  padding: 26px 12px;
  text-align: center;
  font-size: 11px;
  color: #94a3b8;
}
.dialog-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}
.foot-hint {
  font-size: 10.5px;
  color: #94a3b8;
}
</style>
