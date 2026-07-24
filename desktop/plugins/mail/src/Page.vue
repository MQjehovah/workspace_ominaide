<template>
  <div class="mail-app">
    <!-- Sidebar -->
    <div class="sidebar">
      <div class="sidebar-hd">
        <span class="logo">邮件</span>
        <button class="compose-btn" @click="showCompose = true">写邮件</button>
      </div>

      <div class="section-title">邮箱账号</div>
      <div v-for="a in accounts" :key="a.id" class="account-item" :class="{ active: activeAccount === a.id }" @click="selectAccount(a.id)">
        <span class="acc-dot" :style="{ background: getColor(a.id) }"></span>
        <span class="acc-name">{{ a.name || a.email }}</span>
        <span class="acc-email">{{ a.email }}</span>
        <button class="del-btn" title="删除" @click.stop="removeAccount(a.id)">✕</button>
      </div>

      <button class="add-btn" @click="showAccountForm = true">+ 添加邮箱</button>

      <!-- Settings section -->
      <div class="section-title" style="margin-top:16px">操作</div>
      <button class="action-btn" @click="refreshAll">刷新所有邮箱</button>
    </div>

    <!-- Email List -->
    <div class="email-list">
      <div class="list-hd">
        <span class="list-title">收件箱</span>
        <span class="list-count">{{ filteredEmails.length }} 封</span>
      </div>
      <div v-if="loading" class="status">加载中...</div>
      <div v-else-if="filteredEmails.length === 0" class="status">暂无邮件</div>
      <div v-for="e in filteredEmails" :key="e.uid" class="email-item" :class="{ unread: !e.flags?.includes('\\Seen') }" @click="selectedEmail = e">
        <div class="email-from">{{ e.from || '未知' }}</div>
        <div class="email-subject">{{ e.subject || '(无主题)' }}</div>
        <div class="email-date">{{ formatTime(e.date) }}</div>
        <div class="email-preview">{{ e.preview || '' }}</div>
      </div>
    </div>

    <!-- Email Detail -->
    <div class="email-detail" v-if="selectedEmail">
      <div class="detail-hd">
        <div class="detail-subject">{{ selectedEmail.subject }}</div>
        <div class="detail-meta">
          <span>发件人: {{ selectedEmail.from }}</span>
          <span>时间: {{ new Date(selectedEmail.date).toLocaleString() }}</span>
        </div>
        <div class="detail-body">{{ selectedEmail.preview }}</div>
      </div>
    </div>
    <div class="email-detail empty-detail" v-else>
      <span class="empty-text">选择一封邮件来阅读</span>
    </div>

    <!-- Account Form Dialog -->
    <div v-if="showAccountForm" class="overlay" @click.self="showAccountForm = false">
      <div class="dialog">
        <div class="dialog-hd">添加邮箱</div>
        <div class="dialog-body">
          <input v-model="form.name" placeholder="显示名称（如：工作邮箱）" />
          <input v-model="form.email" placeholder="邮箱地址" />
          <input v-model="form.username" placeholder="用户名（通常和邮箱相同）" />
          <input v-model="form.password" type="password" placeholder="密码/授权码" />

          <div class="field-group">
            <label>IMAP 设置</label>
            <div class="row">
              <input v-model="form.imapHost" placeholder="imap.example.com" style="flex:2" />
              <input v-model.number="form.imapPort" placeholder="993" style="flex:1" />
              <label class="tls-label"><input type="checkbox" v-model="form.imapTls" /> SSL</label>
            </div>
          </div>

          <div class="field-group">
            <label>SMTP 设置</label>
            <div class="row">
              <input v-model="form.smtpHost" placeholder="smtp.example.com" style="flex:2" />
              <input v-model.number="form.smtpPort" placeholder="465" style="flex:1" />
              <label class="tls-label"><input type="checkbox" v-model="form.smtpTls" /> SSL</label>
            </div>
          </div>

          <div v-if="formError" class="error">{{ formError }}</div>
        </div>
        <div class="dialog-ft">
          <button class="btn" @click="showAccountForm = false">取消</button>
          <button class="btn primary" @click="saveAccount">保存</button>
        </div>
      </div>
    </div>

    <!-- Compose Dialog -->
    <div v-if="showCompose" class="overlay" @click.self="showCompose = false">
      <div class="dialog compose-dialog">
        <div class="dialog-hd">写邮件</div>
        <div class="dialog-body">
          <select v-model="compose.fromAccount" class="compose-select">
            <option value="">选择发件邮箱</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.email }}</option>
          </select>
          <input v-model="compose.to" placeholder="收件人（多个用逗号分隔）" />
          <input v-model="compose.subject" placeholder="主题" />
          <textarea v-model="compose.text" placeholder="邮件内容..." rows="8"></textarea>
          <div v-if="composeError" class="error">{{ composeError }}</div>
          <div v-if="composeSuccess" class="success">发送成功！</div>
        </div>
        <div class="dialog-ft">
          <button class="btn" @click="showCompose = false">取消</button>
          <button class="btn primary" @click="sendEmail" :disabled="sending">{{ sending ? '发送中...' : '发送' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

const props = defineProps<{ data: any; execute: Function; close: Function; refresh: Function }>()

const accounts = ref<any[]>([])
const allEmails = ref<any[]>([])
const activeAccount = ref('')
const loading = ref(false)
const selectedEmail = ref<any>(null)

// Account form
const showAccountForm = ref(false)
const formError = ref('')
const form = ref<any>({
  name: '', email: '', username: '', password: '',
  imapHost: '', imapPort: 993, imapTls: true,
  smtpHost: '', smtpPort: 465, smtpTls: true,
})

// Compose
const showCompose = ref(false)
const sending = ref(false)
const composeError = ref('')
const composeSuccess = ref(false)
const compose = ref<any>({ fromAccount: '', to: '', subject: '', text: '' })

const filteredEmails = computed(() => {
  if (!activeAccount.value) return allEmails.value
  return allEmails.value.filter((e: any) => e.accountId === activeAccount.value)
})

async function load() {
  const result = await props.execute('getPageData')
  accounts.value = result?.accounts || []
}

async function selectAccount(id: string) {
  activeAccount.value = id
  loading.value = true
  const result = await props.execute('fetchEmails', { accountId: id })
  if (result?.success) {
    allEmails.value = result.emails || []
  }
  loading.value = false
}

async function refreshAll() {
  loading.value = true
  selectedEmail.value = null
  const all: any[] = []
  for (const acc of accounts.value) {
    const result = await props.execute('fetchEmails', { accountId: acc.id })
    if (result?.success) all.push(...(result.emails || []))
  }
  all.sort((a: any, b: any) => new Date(b.date).getTime() - new Date(a.date).getTime())
  allEmails.value = all
  loading.value = false
}

async function saveAccount() {
  formError.value = ''
  if (!form.value.email || !form.value.password) {
    formError.value = '邮箱和密码为必填'
    return
  }
  try {
    const result = await props.execute('addAccount', JSON.parse(JSON.stringify(form.value)))
    if (result?.success) {
      showAccountForm.value = false
      form.value = { name: '', email: '', username: '', password: '', imapHost: '', imapPort: 993, imapTls: true, smtpHost: '', smtpPort: 465, smtpTls: true }
      await load()
    } else {
      formError.value = result?.error || '添加失败'
    }
  } catch (e: any) {
    formError.value = e?.message || '保存出错'
  }
}

async function removeAccount(id: string) {
  if (!confirm('确定删除此邮箱？')) return
  await props.execute('removeAccount', JSON.parse(JSON.stringify({ id })))
  if (activeAccount.value === id) {
    activeAccount.value = ''
    allEmails.value = []
  }
  await load()
}

async function sendEmail() {
  composeError.value = ''
  composeSuccess.value = false
  if (!compose.value.fromAccount || !compose.value.to) {
    composeError.value = '请选择发件邮箱和填写收件人'
    return
  }
  sending.value = true
  const result = await props.execute('sendEmail', JSON.parse(JSON.stringify(compose.value)))
  sending.value = false
  if (result?.success) {
    composeSuccess.value = true
    setTimeout(() => { showCompose.value = false; composeSuccess.value = false }, 2000)
  } else {
    composeError.value = result?.error || '发送失败'
  }
}

const colors = ['#28A745', '#0078D4', '#DC3545', '#FF9800', '#9C27B0', '#E91E63']
function getColor(id: string) { return colors[Math.abs(hash(id)) % colors.length] }
function hash(s: string) { let h = 0; for (let i = 0; i < s.length; i++) { h = ((h << 5) - h) + s.charCodeAt(i); h |= 0 } return h }

function formatTime(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

onMounted(() => { load() })
</script>

<style scoped>
.mail-app { display: flex; height: 100vh; background: #fff; font-size: 13px; }
.sidebar { width: 240px; border-right: 1px solid #e8e8e8; display: flex; flex-direction: column; padding: 12px; overflow-y: auto; }
.sidebar-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.logo { font-size: 16px; font-weight: 700; color: #1a1a2e; }
.compose-btn { padding: 6px 14px; background: #0078D4; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; }
.compose-btn:hover { background: #005a9e; }
.section-title { font-size: 11px; font-weight: 600; color: #999; text-transform: uppercase; margin: 12px 0 8px; }
.account-item { display: flex; align-items: center; gap: 6px; padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.account-item:hover { background: #f5f5f5; }
.account-item.active { background: #e8f4fd; color: #0078D4; }
.acc-dot { width: 8px; height: 8px; border-radius: 4px; flex-shrink: 0; }
.acc-name { flex: 1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.acc-email { font-size: 11px; color: #999; display: none; }
.del-btn { border: none; background: transparent; color: #DC3545; cursor: pointer; font-size: 12px; opacity: 0; padding: 2px; }
.account-item:hover .del-btn { opacity: 1; }
.add-btn, .action-btn { width: 100%; padding: 8px; border: 1px dashed #d0d0d0; border-radius: 6px; background: transparent; cursor: pointer; font-size: 12px; color: #999; margin-top: 4px; }
.add-btn:hover, .action-btn:hover { border-color: #0078D4; color: #0078D4; }
.email-list { width: 360px; border-right: 1px solid #e8e8e8; overflow-y: auto; }
.list-hd { padding: 12px 16px; border-bottom: 1px solid #e8e8e8; display: flex; justify-content: space-between; align-items: center; }
.list-title { font-weight: 600; font-size: 14px; }
.list-count { font-size: 12px; color: #999; }
.status { text-align: center; padding: 40px; color: #999; font-size: 13px; }
.email-item { padding: 12px 16px; border-bottom: 1px solid #f5f5f5; cursor: pointer; }
.email-item:hover { background: #f8f9fa; }
.email-item.unread { background: #f0f7ff; }
.email-from { font-size: 13px; font-weight: 600; color: #333; }
.email-subject { font-size: 12px; color: #555; margin: 2px 0; }
.email-preview { font-size: 11px; color: #999; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.email-date { font-size: 11px; color: #adb5bd; float: right; }
.email-detail { flex: 1; padding: 24px; overflow-y: auto; }
.empty-detail { display: flex; align-items: center; justify-content: center; }
.empty-text { color: #ccc; font-size: 14px; }
.detail-hd { margin-bottom: 16px; }
.detail-subject { font-size: 18px; font-weight: 600; color: #1a1a2e; margin-bottom: 8px; }
.detail-meta { font-size: 12px; color: #999; margin-bottom: 16px; display: flex; gap: 16px; }
.detail-body { font-size: 13px; line-height: 1.6; color: #333; white-space: pre-wrap; }
/* Dialog */
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.dialog { background: #fff; border-radius: 12px; width: 480px; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.12); }
.compose-dialog { width: 600px; }
.dialog-hd { padding: 16px 20px; font-size: 15px; font-weight: 600; border-bottom: 1px solid #e8e8e8; }
.dialog-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }
.dialog-body input, .dialog-body select, .dialog-body textarea { padding: 8px 12px; border: 1px solid #e0e0e0; border-radius: 6px; font-size: 13px; outline: none; }
.dialog-body input:focus, .dialog-body select:focus, .dialog-body textarea:focus { border-color: #0078D4; }
.dialog-body textarea { resize: vertical; font-family: inherit; }
.compose-select { width: 100%; }
.field-group { display: flex; flex-direction: column; gap: 6px; }
.field-group label { font-size: 12px; font-weight: 500; color: #666; }
.row { display: flex; gap: 8px; align-items: center; }
.tls-label { display: flex; align-items: center; gap: 4px; font-size: 12px; white-space: nowrap; }
.error { color: #DC3545; font-size: 12px; }
.success { color: #28A745; font-size: 12px; }
.dialog-ft { padding: 12px 20px; border-top: 1px solid #e8e8e8; display: flex; justify-content: flex-end; gap: 8px; }
.btn { padding: 6px 16px; border-radius: 6px; border: 1px solid #e0e0e0; background: #fff; cursor: pointer; font-size: 12px; }
.btn.primary { background: #0078D4; color: #fff; border-color: #0078D4; }
.btn.primary:disabled { opacity: 0.5; }
</style>
