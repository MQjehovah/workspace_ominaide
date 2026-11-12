<template>
  <div class="sessions-page">
    <div class="sessions-toolbar">
      <div class="agent-tabs">
        <button
          v-for="a in agents"
          :key="a.id"
          :class="['agent-tab', agent === a.id && 'active', !a.available && 'off']"
          :disabled="!a.available"
          :title="a.available ? a.hint : `${a.label} 未安装`"
          @click="selectAgent(a.id)"
        >
          {{ a.label }}
          <span class="agent-hint">{{ a.available ? a.hint : '未安装' }}</span>
        </button>
      </div>
      <select v-model="project" class="proj-select" title="新会话使用的项目">
        <option value="">选择项目…</option>
        <option v-for="p in projects" :key="p.path" :value="p.path">{{ p.name }}</option>
      </select>
      <button class="btn primary" @click="openCreate">＋ 新建会话</button>
      <button class="btn" @click="refreshAll">刷新</button>
    </div>

    <div class="sessions-layout">
      <aside class="session-list">
        <div
          v-for="s in sessions"
          :key="s.id"
          :class="['session-item', activeId === s.id && 'active']"
          @click="openSession(s)"
        >
          <div class="session-title">
            <span v-if="s.running" class="run-dot"></span>
            {{ s.title }}
          </div>
          <div class="session-meta">
            {{ projectName(s.project) }} · {{ timeAgo(s.updated) }}
          </div>
          <button class="session-del" title="删除会话" @click.stop="deleteSession(s)">🗑</button>
        </div>
        <div v-if="!sessions.length" class="session-empty">
          {{ loading ? '加载中…' : '还没有会话' }}
        </div>
      </aside>

      <section class="chat-pane">
        <template v-if="active">
          <div class="chat-head">
            <div class="chat-head-text">
              <div class="chat-title">{{ active.session.title || '会话' }}</div>
              <div class="chat-sub">{{ active.session.project || project || '未指定项目' }}</div>
            </div>
            <span v-if="active.session.running" class="running-badge">执行中</span>
            <button v-if="active.session.running" class="btn danger sm" @click="stop">■ 停止</button>
          </div>

          <div ref="messagesEl" class="chat-messages">
            <div v-if="!active.messages.length && !active.streaming" class="chat-empty">
              这个会话还没有消息，直接在下面输入继续。
            </div>
            <div
              v-for="(m, i) in active.messages"
              :key="i"
              :class="['msg', m.role]"
            >
              <div class="bubble">
                <div v-if="m.tools && m.tools.length" class="msg-tools">
                  <span v-for="(t, ti) in m.tools" :key="ti">🛠 {{ t }}</span>
                </div>
                <pre v-if="m.text">{{ m.text }}</pre>
              </div>
            </div>
            <div v-if="active.streaming" class="msg assistant">
              <div class="bubble streaming">
                <pre>{{ active.streaming }}</pre>
              </div>
            </div>
          </div>

          <div class="chat-composer">
            <textarea
              v-model="input"
              class="chat-input"
              rows="3"
              placeholder="继续这个会话…（Ctrl+Enter 发送）"
              @keydown.ctrl.enter.prevent="send"
              @keydown.meta.enter.prevent="send"
            ></textarea>
            <div class="composer-actions">
              <span class="composer-hint">{{ agentHint }}</span>
              <button
                class="btn primary"
                :disabled="!input.trim() || sending"
                @click="send"
              >
                {{ sending ? '发送中…' : '发送' }}
              </button>
            </div>
          </div>
        </template>
        <div v-else class="chat-empty">
          从左侧选择一个会话，或点「新建会话」开始。
        </div>
      </section>
    </div>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal">
        <h3>新建 {{ agentLabel }} 会话</h3>
        <label class="field-label">项目目录</label>
        <select v-model="project" class="proj-select wide">
          <option value="">选择项目…</option>
          <option v-for="p in projects" :key="p.path" :value="p.path">{{ p.name }} — {{ p.path }}</option>
        </select>
        <label class="field-label">会话标题（可选）</label>
        <input v-model="createTitle" class="text-input" placeholder="例如：修复登录空指针" />
        <div class="modal-actions">
          <button class="btn" @click="showCreate = false">取消</button>
          <button class="btn primary" :disabled="creating || !project" @click="createSession">
            {{ creating ? '创建中…' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{ execute: Function; projects: any[] }>()

const agents = ref<any[]>([])
const agent = ref('opencode')
const project = ref('')
const sessions = ref<any[]>([])
const activeId = ref('')
const active = ref<any>(null)
const input = ref('')
const loading = ref(false)
const sending = ref(false)
const showCreate = ref(false)
const createTitle = ref('')
const creating = ref(false)
const messagesEl = ref<HTMLElement | null>(null)
let pollTimer: any = null
let tick = 0

const agentLabel = computed(
  () => agents.value.find((a: any) => a.id === agent.value)?.label || agent.value,
)
const agentHint = computed(
  () => agents.value.find((a: any) => a.id === agent.value)?.hint || '',
)

function projectName(path: string) {
  if (!path) return '未指定项目'
  const hit = (props.projects || []).find((p: any) => p.path === path)
  if (hit) return hit.name
  const parts = String(path).split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] || path
}

function timeAgo(ms: number) {
  if (!ms) return ''
  const diff = Date.now() - Number(ms)
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return `${Math.floor(diff / 86_400_000)} 天前`
}

async function loadAgents() {
  agents.value = (await props.execute('listCodingAgents').catch(() => [])) || []
  if (!agents.value.some((a: any) => a.id === agent.value && a.available)) {
    const first = agents.value.find((a: any) => a.available)
    if (first) agent.value = first.id
  }
}

async function loadSessions() {
  loading.value = true
  sessions.value =
    (await props.execute('listAgentSessions', { agent: agent.value }).catch(() => [])) || []
  loading.value = false
}

async function refreshAll() {
  await loadSessions()
  if (activeId.value) await loadActive()
}

async function selectAgent(id: string) {
  if (agent.value === id) return
  agent.value = id
  activeId.value = ''
  active.value = null
  await loadSessions()
}

async function openSession(session: any) {
  activeId.value = session.id
  await loadActive()
}

async function loadActive() {
  if (!activeId.value) return
  const session = sessions.value.find((s: any) => s.id === activeId.value)
  const result = await props
    .execute('getAgentSession', {
      agent: agent.value,
      sessionId: activeId.value,
      title: session?.title || active.value?.session?.title || '',
      project: session?.project || '',
    })
    .catch(() => null)
  if (!result || result.ok === false) return
  const previous = active.value?.messages?.length || 0
  active.value = result
  if (
    result.session?.running ||
    (result.messages?.length || 0) !== previous ||
    result.streaming
  ) {
    await nextTick()
    scrollToBottom()
  }
}

function scrollToBottom() {
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

async function createSession() {
  if (creating.value) return
  const target = project.value || props.projects?.[0]?.path || ''
  if (!target) {
    alert('请先选择项目')
    return
  }
  creating.value = true
  const result = await props
    .execute('createAgentSession', {
      agent: agent.value,
      project: target,
      title: createTitle.value,
    })
    .catch((e: any) => ({ ok: false, error: String(e) }))
  creating.value = false
  if (!result?.ok) {
    alert(result?.error || '创建失败')
    return
  }
  showCreate.value = false
  createTitle.value = ''
  await loadSessions()
  const created = result.session
  if (created?.id) {
    sessions.value = [created, ...sessions.value.filter((s: any) => s.id !== created.id)]
    await openSession(created)
  }
}

async function deleteSession(session: any) {
  if (!confirm(`删除会话「${session.title}」？`)) return
  const result = await props
    .execute('deleteAgentSession', { agent: agent.value, sessionId: session.id })
    .catch((e: any) => ({ ok: false, error: String(e) }))
  if (!result?.ok) {
    alert(result?.error || '删除失败')
    return
  }
  if (activeId.value === session.id) {
    activeId.value = ''
    active.value = null
  }
  await loadSessions()
}

async function send() {
  const text = input.value.trim()
  if (!text || !activeId.value || sending.value) return
  sending.value = true
  const result = await props
    .execute('sendAgentMessage', {
      agent: agent.value,
      sessionId: activeId.value,
      text,
    })
    .catch((e: any) => ({ ok: false, error: String(e) }))
  sending.value = false
  if (!result?.ok) {
    alert(result?.error || '发送失败')
    return
  }
  input.value = ''
  await loadActive()
  await loadSessions()
}

async function stop() {
  if (!activeId.value) return
  await props
    .execute('stopAgentMessage', { agent: agent.value, sessionId: activeId.value })
    .catch(() => null)
  await loadActive()
}

function openCreate() {
  if (!project.value) {
    project.value = props.projects?.[0]?.path || ''
  }
  createTitle.value = ''
  showCreate.value = true
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!activeId.value) return
    await loadActive()
    tick += 1
    if (tick % 5 === 0) await loadSessions()
  }, 1200)
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}

onMounted(async () => {
  await loadAgents()
  project.value = props.projects?.[0]?.path || ''
  await loadSessions()
  startPolling()
})

onUnmounted(stopPolling)
</script>

<style scoped>
.sessions-page { display:flex; flex-direction:column; gap:12px; }
.sessions-toolbar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.agent-tabs { display:flex; gap:4px; background:#f1f5f9; border-radius:8px; padding:3px; }
.agent-tab { border:none; background:transparent; color:#64748b; border-radius:6px; padding:5px 10px; font-size:12px; cursor:pointer; display:flex; flex-direction:column; align-items:flex-start; line-height:1.3; }
.agent-tab.active { background:#fff; color:#4f46e5; box-shadow:0 1px 4px rgba(15,23,42,.08); }
.agent-tab.off { opacity:.45; cursor:not-allowed; }
.agent-hint { font-size:9px; color:#94a3b8; }
.proj-select { flex:1; min-width:160px; max-width:320px; padding:6px 8px; border:1px solid #e2e8f0; border-radius:6px; font-size:12px; background:#fff; }
.proj-select.wide { width:100%; max-width:none; margin-bottom:10px; }
.sessions-layout { display:grid; grid-template-columns:300px 1fr; gap:12px; min-height:calc(100vh - 220px); }
.session-list { border:1px solid #e2e8f0; border-radius:10px; background:#fff; overflow-y:auto; max-height:calc(100vh - 220px); }
.session-item { position:relative; padding:10px 34px 10px 12px; border-bottom:1px solid #f1f5f9; cursor:pointer; }
.session-item:hover { background:#f8fafc; }
.session-item.active { background:#eef2ff; border-left:3px solid #6366f1; }
.session-title { font-size:12.5px; font-weight:600; color:#1e293b; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.session-meta { font-size:10px; color:#94a3b8; margin-top:3px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.run-dot { display:inline-block; width:6px; height:6px; border-radius:50%; background:#22c55e; margin-right:5px; }
.session-del { position:absolute; right:4px; top:10px; border:none; background:transparent; cursor:pointer; opacity:0; font-size:12px; }
.session-item:hover .session-del { opacity:.6; }
.session-del:hover { opacity:1; }
.session-empty { padding:24px 12px; font-size:11px; color:#94a3b8; text-align:center; }
.chat-pane { border:1px solid #e2e8f0; border-radius:10px; background:#fff; display:flex; flex-direction:column; max-height:calc(100vh - 220px); }
.chat-head { display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid #f1f5f9; }
.chat-head-text { flex:1; min-width:0; }
.chat-title { font-size:13px; font-weight:700; color:#1e293b; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.chat-sub { font-size:10px; color:#94a3b8; margin-top:2px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.running-badge { font-size:10px; color:#15803d; background:#dcfce7; border-radius:4px; padding:2px 7px; }
.chat-messages { flex:1; overflow-y:auto; padding:14px; display:flex; flex-direction:column; gap:10px; background:#f8fafc; }
.chat-empty { margin:auto; color:#94a3b8; font-size:12px; text-align:center; padding:30px; }
.msg { display:flex; }
.msg.user { justify-content:flex-end; }
.bubble { max-width:78%; border-radius:12px; padding:9px 12px; background:#fff; border:1px solid #e2e8f0; }
.msg.user .bubble { background:#eef2ff; border-color:#c7d2fe; }
.bubble.streaming { border-style:dashed; }
.bubble pre { margin:0; white-space:pre-wrap; word-break:break-word; font-family:inherit; font-size:12px; line-height:1.65; color:#334155; }
.msg-tools { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:6px; }
.msg-tools span { font-size:9.5px; color:#4f46e5; background:#eef2ff; border-radius:4px; padding:1px 5px; }
.chat-composer { border-top:1px solid #f1f5f9; padding:10px 12px; }
.chat-input { width:100%; box-sizing:border-box; resize:vertical; border:1px solid #e2e8f0; border-radius:8px; padding:8px 10px; font-size:12px; font-family:inherit; outline:none; }
.chat-input:focus { border-color:#6366f1; }
.composer-actions { display:flex; align-items:center; justify-content:flex-end; gap:10px; margin-top:8px; }
.composer-hint { font-size:10px; color:#94a3b8; margin-right:auto; }
.modal-mask { position:fixed; inset:0; background:rgba(15,23,42,.4); display:flex; align-items:center; justify-content:center; z-index:60; }
.modal { width:420px; max-width:92vw; background:#fff; border-radius:12px; padding:18px 20px; box-shadow:0 12px 40px rgba(15,23,42,.25); }
.modal h3 { margin:0 0 12px; font-size:15px; color:#1e293b; }
.field-label { display:block; font-size:11px; color:#64748b; margin:8px 0 4px; }
.text-input { width:100%; box-sizing:border-box; border:1px solid #e2e8f0; border-radius:8px; padding:7px 9px; font-size:12px; outline:none; }
.text-input:focus { border-color:#6366f1; }
.modal-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:16px; }
.btn { padding:6px 12px; border:1px solid #e2e8f0; border-radius:6px; background:#fff; color:#475569; font-size:12px; cursor:pointer; }
.btn.primary { background:#4f46e5; border-color:#4f46e5; color:#fff; }
.btn.primary:disabled { opacity:.5; cursor:default; }
.btn.danger { background:#ef4444; border-color:#ef4444; color:#fff; }
.btn.sm { padding:4px 9px; font-size:11px; }
</style>
