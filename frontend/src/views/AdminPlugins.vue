<template>
  <div class="page-wrapper">
    <div class="page-header"><h2>插件管理</h2></div>
    <div class="page-card">
      <div class="page-card-body">
        <el-tabs v-model="tab">
          <el-tab-pane label="已安装" name="installed">
            <div style="display:flex;gap:12px;margin-bottom:16px;align-items:center">
              <el-input v-model="installedSearch" placeholder="搜索插件" prefix-icon="Search" style="max-width:280px" clearable />
              <el-upload :http-request="handleUpload" :show-file-list="false" accept=".zip">
                <el-button type="primary">上传安装</el-button>
              </el-upload>
            </div>
            <el-table :data="filteredInstalled" stripe v-loading="installedLoading">
              <el-table-column prop="title" label="标题" min-width="160" />
              <el-table-column prop="name" label="名称" min-width="140" />
              <el-table-column prop="version" label="版本" width="80" />
              <el-table-column label="启用" width="70">
                <template #default="{ row }">
                  <el-switch :model-value="row.enabled" :loading="toggling === row.name" @change="(v: boolean) => toggleEnabled(row,v)" />
                </template>
              </el-table-column>
              <el-table-column prop="installed_at" label="安装时间" width="170" />
              <el-table-column label="操作" width="80" fixed="right">
                <template #default="{ row }">
                  <el-popconfirm title="确定卸载？" @confirm="uninstallPlugin(row.name)">
                    <template #reference><el-button link type="danger" size="small">卸载</el-button></template>
                  </el-popconfirm>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="插件市场" name="marketplace">
            <div style="display:flex;gap:12px;margin-bottom:16px;align-items:center">
              <el-input v-model="mktSearch" placeholder="搜索" prefix-icon="Search" style="max-width:280px" clearable />
            </div>
            <el-row :gutter="16">
              <el-col v-for="p in filteredMarketplace" :key="p.id" :span="8" :xs="24" :sm="12" :md="8" style="margin-bottom:16px">
                <el-card shadow="hover" style="border-radius:10px">
                  <div style="padding:8px">
                    <div style="font-size:15px;font-weight:600;color:#1a1a2e;margin-bottom:4px">{{ p.displayName }}</div>
                    <div style="font-size:12px;color:#909399;margin-bottom:8px;min-height:32px">{{ p.description }}</div>
                    <div style="display:flex;align-items:center;justify-content:space-between">
                      <span style="font-size:11px;color:#adb5bd">v{{ p.version }}</span>
                      <el-button v-if="isInstalled(p.name)" size="small" disabled>已安装</el-button>
                      <el-button v-else size="small" type="primary" :loading="installing === p.id" @click="installMarket(p.id)">安装</el-button>
                    </div>
                  </div>
                </el-card>
              </el-col>
            </el-row>
            <p v-if="filteredMarketplace.length === 0 && !mktSearch" style="text-align:center;color:#909399;padding:40px">暂无可用插件</p>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'
import { ElMessage } from 'element-plus'

const tab = ref('installed')
const installedSearch = ref('')
const mktSearch = ref('')

// Installed
const plugins = ref<any[]>([])
const installedLoading = ref(false)
const toggling = ref<string | null>(null)
const filteredInstalled = computed(() => {
  const q = installedSearch.value.toLowerCase()
  return q ? plugins.value.filter((p:any) => p.title?.toLowerCase().includes(q) || p.name?.toLowerCase().includes(q)) : plugins.value
})

async function fetchInstalled() { installedLoading.value = true; try { const r = await client.get('/plugins'); plugins.value = r.data } finally { installedLoading.value = false } }
async function toggleEnabled(row: any, val: boolean) { toggling.value = row.name; try { const r = await client.post(`/plugins/${row.name}/toggle`); row.enabled = r.data.enabled; ElMessage.success(r.data.enabled ? '已启用' : '已禁用') } catch { ElMessage.error('操作失败') } finally { toggling.value = null } }
async function uninstallPlugin(name: string) {
  try { await client.delete(`/plugins/${name}`); ElMessage.success('已卸载'); fetchInstalled() }
  catch { ElMessage.error('卸载失败') }
}

// Upload
async function handleUpload(options: any) {
  const form = new FormData(); form.append('file', options.file)
  try { await client.post('/plugins/install', form, { headers: { 'Content-Type': 'multipart/form-data' } }); ElMessage.success('安装成功'); fetchInstalled() }
  catch (e: any) { ElMessage.error(e.response?.data?.detail || '安装失败') }
}

// Marketplace
const marketplace = ref<any[]>([])
const installing = ref<string | null>(null)
const filteredMarketplace = computed(() => {
  const q = mktSearch.value.toLowerCase()
  return q ? marketplace.value.filter((p:any) => p.displayName?.toLowerCase().includes(q) || p.name?.toLowerCase().includes(q)) : marketplace.value
})

async function fetchMarketplace() { try { const r = await client.get('/plugins/marketplace'); marketplace.value = r.data } catch { /* ignore */ } }
function isInstalled(name: string) { return plugins.value.some((p:any) => p.name === name) }
async function installMarket(id: string) {
  installing.value = id
  try { await client.post(`/plugins/marketplace/${id}/install`); ElMessage.success('安装成功'); fetchInstalled() }
  catch (e: any) { ElMessage.error(e.response?.data?.detail || '安装失败') }
  finally { installing.value = null }
}

onMounted(() => { fetchInstalled(); fetchMarketplace() })
</script>
