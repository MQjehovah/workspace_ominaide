<template>
  <div class="page-wrapper mcp-page">
    <div class="page-header">
      <div>
        <h2>MCP 管理</h2>
        <p class="sub">统一管理 Home Assistant、钉钉、浏览器等 MCP Server；工具会自动进入 Bot 目录。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">添加 Server</el-button>
      </div>
    </div>

    <el-row :gutter="12" class="stats-row">
      <el-col :span="8"><div class="stat-card"><div class="stat-value">{{ servers.length }}</div><div class="stat-label">MCP Server</div></div></el-col>
      <el-col :span="8"><div class="stat-card"><div class="stat-value">{{ connectedCount }}</div><div class="stat-label">已连接</div></div></el-col>
      <el-col :span="8"><div class="stat-card"><div class="stat-value">{{ totalTools }}</div><div class="stat-label">已发现工具</div></div></el-col>
    </el-row>

    <div class="page-card">
      <div class="page-card-body">
        <el-table :data="servers" v-loading="loading" size="small" empty-text="还没有 MCP Server">
          <el-table-column label="名称" min-width="180">
            <template #default="{ row }">
              <div class="server-name">
                <el-tag size="small" :type="statusType(row.last_status)">{{ row.last_status }}</el-tag>
                <span>{{ row.name }}</span>
              </div>
              <div class="server-slug">{{ row.slug }} · {{ row.transport }}</div>
            </template>
          </el-table-column>
          <el-table-column label="地址/命令" min-width="220">
            <template #default="{ row }">
              <span class="mono">{{ row.transport === 'http' ? row.url : [row.command, ...(row.args || [])].join(' ') }}</span>
            </template>
          </el-table-column>
          <el-table-column label="工具" width="90">
            <template #default="{ row }">{{ row.tools_count || 0 }}</template>
          </el-table-column>
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" @change="toggleServer(row, $event)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="connect(row)">{{ row.last_status === 'connected' ? '重连' : '连接' }}</el-button>
              <el-button link @click="openTools(row)">工具</el-button>
              <el-button link @click="openCalls(row)">调用记录</el-button>
              <el-button link @click="openEdit(row)">编辑</el-button>
              <el-popconfirm title="删除这个 MCP Server？" @confirm="removeServer(row)">
                <template #reference><el-button link type="danger">删除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="lastError" class="server-error">{{ lastError }}</div>
      </div>
    </div>

    <el-dialog v-model="formOpen" :title="editing ? '编辑 MCP Server' : '添加 MCP Server'" width="620px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="模板" v-if="!editing">
          <el-select v-model="templateKey" placeholder="从模板开始（可选）" clearable style="width:100%" @change="applyTemplate">
            <el-option v-for="t in templates" :key="t.key" :label="`${t.name} · ${t.description}`" :value="t.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="Home Assistant" /></el-form-item>
        <el-form-item label="Slug"><el-input v-model="form.slug" placeholder="home-assistant（全局唯一）" /></el-form-item>
        <el-form-item label="传输">
          <el-radio-group v-model="form.transport">
            <el-radio-button label="stdio">stdio</el-radio-button>
            <el-radio-button label="http">http</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <template v-if="form.transport === 'stdio'">
          <el-form-item label="命令"><el-input v-model="form.command" placeholder="python / npx / uvx" /></el-form-item>
          <el-form-item label="参数"><el-input v-model="argsText" type="textarea" :rows="3" placeholder='每行一个参数，例如 -m\nmcp_servers.dingtalk' /></el-form-item>
          <el-form-item label="环境变量"><el-input v-model="envText" type="textarea" :rows="2" placeholder='JSON，例如 {"DWS_CONFIG_DIR":"/data/dws"}；编辑时留空保持不变' /></el-form-item>
        </template>
        <template v-else>
          <el-form-item label="URL"><el-input v-model="form.url" placeholder="http://homeassistant.local:8123/mcp" /></el-form-item>
          <el-form-item label="Headers"><el-input v-model="headersText" type="textarea" :rows="2" placeholder='JSON，例如 {"Authorization":"Bearer ..."}；编辑时留空保持不变' /></el-form-item>
        </template>
        <el-form-item label="默认风险">
          <el-select v-model="form.risk_default" style="width:160px">
            <el-option label="read" value="read" />
            <el-option label="write" value="write" />
            <el-option label="external" value="external" />
            <el-option label="dangerous" value="dangerous" />
          </el-select>
        </el-form-item>
        <el-form-item label="自动连接"><el-switch v-model="form.auto_start" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formOpen = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveServer">保存并连接</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="toolsOpen" :title="`工具 · ${activeServer?.name || ''}`" size="720px">
      <el-table :data="tools" size="small" empty-text="还没有发现工具">
        <el-table-column prop="name" label="工具" min-width="180">
          <template #default="{ row }"><span class="mono">{{ row.name }}</span></template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
        <el-table-column label="风险" width="140">
          <template #default="{ row }">
            <el-select v-model="row.risk" size="small" @change="updateTool(row)">
              <el-option label="read" value="read" />
              <el-option label="write" value="write" />
              <el-option label="external" value="external" />
              <el-option label="dangerous" value="dangerous" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="updateTool(row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-drawer v-model="callsOpen" :title="`调用记录 · ${activeServer?.name || ''}`" size="760px">
      <el-table :data="calls" size="small" empty-text="还没有调用记录">
        <el-table-column prop="id" label="#" width="60" />
        <el-table-column prop="tool_name" label="工具" min-width="180" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-tag size="small" :type="row.status === 'ok' ? 'success' : 'danger'">{{ row.status }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="错误" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error || '' }}</template>
        </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import client from '@/api/client'
import { formatBackendDate } from '@/utils/date'

const loading = ref(false)
const saving = ref(false)
const servers = ref<any[]>([])
const templates = ref<any[]>([])
const lastError = ref('')
const formOpen = ref(false)
const editing = ref<any>(null)
const templateKey = ref('')
const argsText = ref('')
const envText = ref('')
const headersText = ref('')
const toolsOpen = ref(false)
const tools = ref<any[]>([])
const callsOpen = ref(false)
const calls = ref<any[]>([])
const activeServer = ref<any>(null)

const form = reactive({
  name: '', slug: '', transport: 'stdio', command: '', url: '',
  risk_default: 'read', auto_start: true,
})

const connectedCount = computed(() => servers.value.filter(s => s.last_status === 'connected').length)
const totalTools = computed(() => servers.value.reduce((n, s) => n + (s.tools_count || 0), 0))

function statusType(status: string) {
  return status === 'connected' ? 'success' : status === 'error' ? 'danger' : 'info'
}
function fmt(value: string) { return value ? formatBackendDate(value) : '' }

async function loadAll() {
  loading.value = true
  try {
    const [s, t] = await Promise.all([
      client.get('/mcp/servers'),
      client.get('/mcp/templates'),
    ])
    servers.value = s.data.servers || []
    templates.value = t.data.templates || []
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    name: '', slug: '', transport: 'stdio', command: '', url: '',
    risk_default: 'read', auto_start: true,
  })
  argsText.value = ''
  envText.value = ''
  headersText.value = ''
  templateKey.value = ''
}

function openCreate() {
  editing.value = null
  resetForm()
  formOpen.value = true
}

function openEdit(row: any) {
  editing.value = row
  Object.assign(form, {
    name: row.name, slug: row.slug, transport: row.transport,
    command: row.command || '', url: row.url || '',
    risk_default: row.risk_default || 'read', auto_start: !!row.auto_start,
  })
  argsText.value = (row.args || []).join('\n')
  envText.value = ''
  headersText.value = ''
  formOpen.value = true
}

function applyTemplate(key: string) {
  const t = templates.value.find(x => x.key === key)
  if (!t) return
  form.name = t.name
  form.slug = t.key
  form.transport = t.transport || 'stdio'
  form.command = t.command || ''
  form.url = t.url || ''
  form.risk_default = t.risk_default || 'read'
  argsText.value = (t.args || []).join('\n')
}

function parseJson(text: string, label: string): any {
  if (!text.trim()) return undefined
  try { return JSON.parse(text) } catch { throw new Error(`${label} 不是合法 JSON`) }
}

async function saveServer() {
  if (!form.name.trim()) { ElMessage.warning('名称必填'); return }
  saving.value = true
  lastError.value = ''
  try {
    const payload: any = {
      name: form.name.trim(),
      slug: form.slug.trim() || undefined,
      transport: form.transport,
      risk_default: form.risk_default,
      auto_start: form.auto_start,
    }
    if (form.transport === 'stdio') {
      payload.command = form.command.trim()
      payload.args = argsText.value.split('\n').map(x => x.trim()).filter(Boolean)
      const env = parseJson(envText.value, '环境变量')
      if (env) payload.env = env
    } else {
      payload.url = form.url.trim()
      const headers = parseJson(headersText.value, 'Headers')
      if (headers) payload.headers = headers
    }
    if (editing.value) {
      await client.patch(`/mcp/servers/${editing.value.id}`, payload)
    } else {
      await client.post('/mcp/servers', payload)
    }
    formOpen.value = false
    await loadAll()
    ElMessage.success('已保存')
  } catch (e: any) {
    lastError.value = e?.response?.data?.detail || e.message || '保存失败'
    ElMessage.error(lastError.value)
  } finally {
    saving.value = false
  }
}

async function toggleServer(row: any, enabled: boolean) {
  try {
    await client.patch(`/mcp/servers/${row.id}`, { enabled })
    await loadAll()
  } catch (e: any) {
    row.enabled = !enabled
    ElMessage.error(e?.response?.data?.detail || '更新失败')
  }
}

async function connect(row: any) {
  lastError.value = ''
  try {
    await client.post(`/mcp/servers/${row.id}/connect`)
    await loadAll()
    ElMessage.success('已连接')
  } catch (e: any) {
    lastError.value = e?.response?.data?.detail || '连接失败'
    ElMessage.error(lastError.value)
  }
}

async function removeServer(row: any) {
  await client.delete(`/mcp/servers/${row.id}`)
  await loadAll()
}

async function openTools(row: any) {
  activeServer.value = row
  toolsOpen.value = true
  const r = await client.get(`/mcp/servers/${row.id}/tools`)
  tools.value = r.data.tools || []
}

async function updateTool(row: any) {
  await client.patch(`/mcp/servers/${activeServer.value.id}/tools/${encodeURIComponent(row.name)}`, {
    risk: row.risk, enabled: row.enabled,
  })
  await loadAll()
}

async function openCalls(row: any) {
  activeServer.value = row
  callsOpen.value = true
  const r = await client.get('/mcp/calls', { params: { server_id: row.id, limit: 100 } })
  calls.value = r.data.calls || []
}

onMounted(loadAll)
</script>

<style scoped>
.mcp-page .sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.header-actions { display: flex; gap: 8px; }
.stats-row { margin-bottom: 12px; }
.stat-card { background: #fff; border: 1px solid #edf0f5; border-radius: 10px; padding: 14px 16px; }
.stat-value { font-size: 22px; font-weight: 700; color: #1a1a2e; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }
.server-name { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: #2c3550; }
.server-slug { font-size: 11px; color: #909399; margin-top: 3px; }
.server-error { margin-top: 10px; color: #f56c6c; font-size: 12px; word-break: break-all; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: #606266; word-break: break-all; }
</style>
