<template>
  <div class="page-wrapper">
    <div class="page-header" style="display:flex;align-items:center;justify-content:space-between">
      <h2>插件市场</h2>
      <el-upload :http-request="handleUpload" :show-file-list="false" accept=".zip">
        <el-button type="primary">上传插件</el-button>
      </el-upload>
    </div>
    <div class="page-card">
      <div class="page-card-body">
        <div style="display:flex;gap:12px;margin-bottom:16px;align-items:center">
          <el-input v-model="search" placeholder="搜索插件" prefix-icon="Search" style="max-width:300px" clearable />
          <span style="font-size:13px;color:#909399">共 {{ filtered.length }} 个</span>
        </div>
        <el-row :gutter="16">
          <el-col v-for="p in filtered" :key="p.id" :span="8" :xs="24" :sm="12" :md="8" :lg="6" style="margin-bottom:16px">
            <el-card shadow="hover" style="border-radius:10px;height:100%">
              <div style="padding:12px;display:flex;flex-direction:column;height:100%">
                <div style="font-size:15px;font-weight:600;color:#1a1a2e">{{ p.displayName }}</div>
                <div style="font-size:11px;color:#adb5bd;margin:2px 0 6px">{{ p.name }} v{{ p.version }}</div>
                <div style="font-size:12px;color:#666;flex:1;min-height:36px">{{ p.description || '暂无描述' }}</div>
                <div style="display:flex;align-items:center;justify-content:space-between;margin-top:10px;padding-top:10px;border-top:1px solid #f0f0f0">
                  <span v-if="p.hasBuild" style="font-size:11px;color:#67c23a">已构建</span>
                  <span v-else style="font-size:11px;color:#e6a23c">未构建</span>
                  <div style="display:flex;gap:6px">
                    <el-button size="small" :disabled="!p.hasBuild" @click="downloadPlugin(p)">下载</el-button>
                    <el-popconfirm title="确定删除？" @confirm="deletePlugin(p.name)">
                      <template #reference><el-button size="small" type="danger">删除</el-button></template>
                    </el-popconfirm>
                  </div>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>
        <p v-if="loading" style="text-align:center;color:#909399;padding:40px">加载中...</p>
        <p v-else-if="filtered.length === 0" style="text-align:center;color:#909399;padding:40px">暂无插件。点击右上角「上传插件」添加</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'
import { ElMessage } from 'element-plus'

const plugins = ref<any[]>([])
const loading = ref(true)
const search = ref('')

const filtered = computed(() => {
  const q = search.value.toLowerCase()
  return q ? plugins.value.filter((p:any) => p.displayName?.toLowerCase().includes(q) || p.name?.toLowerCase().includes(q) || p.description?.toLowerCase().includes(q)) : plugins.value
})

async function fetchPlugins() {
  loading.value = true
  try { const r = await client.get('/plugins/marketplace'); plugins.value = r.data }
  catch { /* ignore */ }
  finally { loading.value = false }
}

async function handleUpload(options: any) {
  const form = new FormData(); form.append('file', options.file)
  try {
    await client.post('/plugins/marketplace/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
    ElMessage.success('上传成功'); fetchPlugins()
  } catch (e: any) { ElMessage.error(e.response?.data?.detail || '上传失败') }
}

function downloadPlugin(p: any) { window.open(p.downloadUrl, '_blank') }

async function deletePlugin(name: string) {
  try { await client.delete(`/plugins/marketplace/${name}`); ElMessage.success('已删除'); fetchPlugins() }
  catch { ElMessage.error('删除失败') }
}

onMounted(fetchPlugins)
</script>
