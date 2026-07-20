<script setup lang="ts">
import { ref, onMounted } from 'vue'

const { data, execute, close, refresh } = defineProps<{
  data: any; execute: Function; close: Function; refresh: Function
}>()

const files = ref<any[]>([])
const folders = ref<any[]>([])
const currentPath = ref('/')
const breadcrumb = ref<string[]>([])

async function loadFiles(path: string) {
  currentPath.value = path
  breadcrumb.value = path.split('/').filter(Boolean)
  try {
    const res = await window.mqbox?.api.get(`/files?page_size=200&folder_path=${encodeURIComponent(path)}`) || { files: [] }
    folders.value = (res.files || []).filter((f: any) => f.is_folder)
    files.value = (res.files || []).filter((f: any) => !f.is_folder)
  } catch {}
}

function enterFolder(f: any) {
  const p = (f.folder_path.replace(/\/+$/, '') || '') + '/' + f.original_name + '/'
  loadFiles(p)
}

function goToRoot() { loadFiles('/') }
function goToBreadcrumb(idx: number) {
  const p = '/' + breadcrumb.value.slice(0, idx + 1).join('/') + '/'
  loadFiles(p)
}

onMounted(() => loadFiles('/'))
</script>

<template>
  <div class="page">
    <div class="header">
      <h2>文件</h2>
    </div>
    <div class="breadcrumb">
      <span class="crumb" @click="goToRoot">根目录</span>
      <span v-for="(c, i) in breadcrumb" :key="i" class="crumb" @click="goToBreadcrumb(i)">/ {{ c }}</span>
    </div>
    <div class="grid">
      <div v-for="f in folders" :key="f.id" class="item folder" @click="enterFolder(f)">
        <div class="item-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
        </div>
        <div class="item-name">{{ f.original_name }}</div>
      </div>
      <div v-for="f in files" :key="f.id" class="item">
        <div class="item-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </div>
        <div class="item-name">{{ f.original_name }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { padding:20px; }
.header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.header h2 { margin:0; font-size:18px; }
.breadcrumb { font-size:12px; color:#999; margin-bottom:16px; }
.crumb { cursor:pointer; color:#409EFF; }
.crumb:hover { text-decoration:underline; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(120px,1fr)); gap:12px; }
.item { padding:16px 8px; border:1px solid #e8e8e8; border-radius:8px; text-align:center; cursor:pointer; }
.item:hover { border-color:#409EFF; }
.item.folder .item-icon { color:#FF9800; }
.item-icon { font-size:28px; margin-bottom:8px; color:#666; }
.item-icon svg { width:32px; height:32px; }
.item-name { font-size:12px; color:#333; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
</style>
