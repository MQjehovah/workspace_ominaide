<template>
  <div class="page-wrapper">
    <div class="page-header">
      <h2>邮件</h2>
      <div class="header-actions">
        <el-select v-model="filter" size="small" style="width:120px" @change="loadMessages">
          <el-option label="全部" value="all" />
          <el-option label="未读" value="unread" />
          <el-option label="重要" value="important" />
          <el-option label="星标" value="starred" />
        </el-select>
        <el-button size="small" :icon="Refresh" :loading="syncing" @click="syncAll">同步全部</el-button>
        <el-button size="small" type="primary" @click="showAdd = true">添加邮箱</el-button>
      </div>
    </div>

    <div class="mail-layout">
      <div class="account-pane page-card">
        <div class="pane-title">邮箱账号</div>
        <div
          class="account-row"
          :class="{ active: activeAccount === null }"
          @click="activeAccount = null; page = 1; loadMessages()"
        >
          <span>全部邮件</span>
        </div>
        <div
          v-for="a in accounts"
          :key="a.id"
          class="account-row"
          :class="{ active: activeAccount === a.id }"
          @click="activeAccount = a.id; page = 1; loadMessages()"
        >
          <div class="account-main">
            <span class="account-name">{{ a.name || a.email }}</span>
            <span class="account-mail">{{ a.email }}</span>
          </div>
          <el-button
            link size="small" :loading="syncingId === a.id"
            @click.stop="syncOne(a.id)"
          >同步</el-button>
        </div>
        <div v-if="accounts.length === 0" class="pane-empty">
          还没有邮箱账号。<br />添加后由后端定时收取，无需打开桌面端。
        </div>
        <div v-if="lastSyncError" class="sync-error">{{ lastSyncError }}</div>
      </div>

      <div class="message-pane page-card">
        <div class="message-toolbar">
          <span class="pane-title">{{ currentAccountName }} · {{ total }} 封</span>
          <el-button size="small" :icon="Refresh" :loading="loading" @click="loadMessages">刷新</el-button>
        </div>

        <div v-if="!loading && messages.length === 0" class="pane-empty">
          暂无邮件。点“同步全部”从后端拉取，或等待后台定时同步。
        </div>

        <div
          v-for="m in messages"
          :key="m.id"
          class="message-row"
          :class="{ unread: !m.read }"
          @click="openMessage(m)"
        >
          <div class="message-top">
            <span class="message-from">{{ m.from_address || '未知发件人' }}</span>
            <span class="message-time">{{ formatTime(m.date || m.created_at) }}</span>
          </div>
          <div class="message-subject">
            <el-tag v-if="m.important" size="small" type="danger" effect="plain">重要</el-tag>
            <el-tag v-if="m.starred" size="small" type="warning" effect="plain">星标</el-tag>
            {{ m.subject || '(无主题)' }}
          </div>
          <div class="message-summary">{{ m.ai_summary || m.preview }}</div>
        </div>

        <div v-if="total > pageSize" class="pager">
          <el-pagination
            v-model:current-page="page" :page-size="pageSize" :total="total"
            layout="prev,pager,next" small @current-change="loadMessages"
          />
        </div>
      </div>
    </div>

    <el-drawer v-model="showDetail" size="560px" :title="detail?.subject || '邮件详情'">
      <div v-if="detail" class="detail">
        <div class="detail-meta">
          <div><b>发件人：</b>{{ detail.from_address || '-' }}</div>
          <div><b>收件人：</b>{{ detail.to_addresses || '-' }}</div>
          <div><b>时间：</b>{{ formatTime(detail.date || detail.created_at) }}</div>
        </div>
        <div v-if="detail.ai_summary" class="detail-summary">
          <div class="detail-label">AI 摘要</div>
          {{ detail.ai_summary }}
        </div>
        <div v-if="detail.ai_actions?.length" class="detail-summary">
          <div class="detail-label">建议动作</div>
          <div v-for="(a, i) in detail.ai_actions" :key="i">· {{ a.text || a }}</div>
        </div>
        <div class="detail-label">正文</div>
        <pre class="detail-body">{{ detail.content || detail.preview || '(无正文)' }}</pre>
      </div>
    </el-drawer>

    <el-dialog v-model="showAdd" title="添加邮箱" width="520px">
      <el-form label-width="90px">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="工作邮箱" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" placeholder="me@example.com" /></el-form-item>
        <el-form-item label="用户名"><el-input v-model="form.username" placeholder="通常与邮箱相同" /></el-form-item>
        <el-form-item label="密码/授权码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
        <el-form-item label="IMAP"><el-input v-model="form.imap_host" placeholder="imap.example.com" /></el-form-item>
        <el-form-item label="IMAP 端口"><el-input-number v-model="form.imap_port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="SMTP"><el-input v-model="form.smtp_host" placeholder="smtp.example.com" /></el-form-item>
        <el-form-item label="SMTP 端口"><el-input-number v-model="form.smtp_port" :min="1" :max="65535" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createAccount">保存并同步</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import client from '@/api/client'
import { parseBackendDate } from '@/utils/date'

const accounts = ref<any[]>([])
const messages = ref<any[]>([])
const activeAccount = ref<number | null>(null)
const filter = ref('all')
const page = ref(1)
const pageSize = 20
const total = ref(0)
const loading = ref(false)
const syncing = ref(false)
const syncingId = ref<number | null>(null)
const lastSyncError = ref('')
const showDetail = ref(false)
const detail = ref<any>(null)
const showAdd = ref(false)
const creating = ref(false)

const form = ref({
  name: '', email: '', username: '', password: '',
  imap_host: '', imap_port: 993, smtp_host: '', smtp_port: 465,
})

const currentAccountName = computed(() => {
  if (!activeAccount.value) return '全部邮件'
  const a = accounts.value.find(x => x.id === activeAccount.value)
  return a?.name || a?.email || '邮箱'
})

async function loadAccounts() {
  try {
    const { data } = await client.get('/plugins/mail/accounts')
    accounts.value = data || []
  } catch {
    accounts.value = []
  }
}

async function loadMessages() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize }
    if (activeAccount.value) params.account_id = activeAccount.value
    if (filter.value === 'unread') params.unread = true
    if (filter.value === 'important') params.important = true
    if (filter.value === 'starred') params.starred = true
    const { data } = await client.get('/plugins/mail/messages', { params })
    messages.value = data.items || []
    total.value = data.total || 0
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '加载邮件失败')
  } finally {
    loading.value = false
  }
}

async function syncAll() {
  syncing.value = true
  lastSyncError.value = ''
  try {
    const { data } = await client.post('/plugins/mail/sync')
    ElMessage.success(`同步完成，新增 ${data.new || 0} 封`)
    await Promise.all([loadAccounts(), loadMessages()])
  } catch (e: any) {
    lastSyncError.value = e?.response?.data?.detail || '同步失败，请检查邮箱配置'
  } finally {
    syncing.value = false
  }
}

async function syncOne(id: number) {
  syncingId.value = id
  lastSyncError.value = ''
  try {
    const { data } = await client.post(`/plugins/mail/accounts/${id}/sync`)
    if (data.error) lastSyncError.value = data.error
    else ElMessage.success(`新增 ${data.new || 0} 封`)
    await Promise.all([loadAccounts(), loadMessages()])
  } catch (e: any) {
    lastSyncError.value = e?.response?.data?.detail || '同步失败'
  } finally {
    syncingId.value = null
  }
}

async function openMessage(m: any) {
  detail.value = m
  showDetail.value = true
  if (!m.read) {
    try {
      await client.put(`/plugins/mail/messages/${m.id}/read`)
      m.read = true
    } catch { /* ignore */ }
  }
  try {
    const { data } = await client.get(`/plugins/mail/messages/${m.id}`)
    detail.value = data
  } catch { /* ignore */ }
}

async function createAccount() {
  if (!form.value.email || !form.value.username || !form.value.password || !form.value.imap_host || !form.value.smtp_host) {
    ElMessage.warning('请填写邮箱、用户名、密码和服务器地址')
    return
  }
  creating.value = true
  try {
    const { data } = await client.post('/plugins/mail/accounts', {
      ...form.value,
      imap_tls: form.value.imap_port === 993,
      smtp_tls: form.value.smtp_port === 465,
    })
    showAdd.value = false
    await loadAccounts()
    await syncOne(data.id)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    creating.value = false
  }
}

function formatTime(value: any) {
  if (!value) return ''
  const d = parseBackendDate(value)
  if (!d) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(async () => {
  await loadAccounts()
  await loadMessages()
})
</script>

<style scoped>
.header-actions { display: flex; gap: 8px; align-items: center; }
.mail-layout { display: grid; grid-template-columns: 240px 1fr; gap: 14px; min-height: 520px; }
.account-pane { padding: 12px; }
.message-pane { padding: 12px 16px; }
.pane-title { font-size: 13px; font-weight: 600; color: #1a1a2e; }
.account-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 9px 10px; margin-top: 6px; border-radius: 8px; cursor: pointer; }
.account-row:hover { background: #f5f7fa; }
.account-row.active { background: #ecf5ff; }
.account-main { display: flex; flex-direction: column; min-width: 0; }
.account-name { font-size: 13px; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-mail { font-size: 11px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pane-empty { padding: 30px 8px; text-align: center; color: #909399; font-size: 12px; line-height: 1.8; }
.sync-error { margin-top: 10px; color: #f56c6c; font-size: 12px; word-break: break-all; }
.message-toolbar { display: flex; align-items: center; justify-content: space-between; padding-bottom: 10px; border-bottom: 1px solid #f0f2f5; }
.message-row { padding: 12px 6px; border-bottom: 1px solid #f5f7fa; cursor: pointer; }
.message-row:hover { background: #fafbfc; }
.message-row.unread .message-subject { font-weight: 600; }
.message-top { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; color: #909399; }
.message-from { color: #606266; font-weight: 500; }
.message-subject { margin: 5px 0; font-size: 14px; color: #1a1a2e; display: flex; gap: 6px; align-items: center; }
.message-summary { font-size: 12px; color: #909399; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pager { text-align: center; padding-top: 12px; }
.detail-meta { font-size: 13px; color: #606266; line-height: 2; margin-bottom: 14px; }
.detail-label { font-size: 12px; font-weight: 600; color: #1a1a2e; margin: 14px 0 6px; }
.detail-summary { background: #f5f7fa; border-radius: 8px; padding: 10px 12px; font-size: 13px; color: #606266; line-height: 1.8; }
.detail-body { white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; line-height: 1.8; color: #303133; background: #fafbfc; border-radius: 8px; padding: 12px; }

@media (max-width: 860px) {
  .mail-layout { grid-template-columns: 1fr; gap: 10px; min-height: 0; }
  .account-pane { max-height: 168px; overflow-y: auto; }
  .message-pane { padding: 10px 12px; }
  .header-actions { flex-wrap: wrap; }
  .message-subject { font-size: 13.5px; }
  .detail-body { font-size: 13.5px; }
}
</style>
