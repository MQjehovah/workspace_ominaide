<template>
  <div class="devops-page">
    <header class="header">
      <h1>DevOps 管理</h1>
      <div class="tabs">
        <button :class="['tab', tab === 'projects' && 'active']" @click="tab = 'projects'">📂 项目</button>
        <button :class="['tab', tab === 'terminal' && 'active']" @click="tab = 'terminal'">💻 终端</button>
        <button :class="['tab', tab === 'feishu' && 'active']" @click="tab = 'feishu'">✈️ 飞书</button>
      </div>
    </header>

    <!-- Projects Tab -->
    <div v-if="tab === 'projects'" class="content">
      <div class="toolbar">
        <button class="btn primary" @click="pickAndScan">🔍 扫描目录</button>
        <button class="btn" @click="addProjectDir">➕ 添加项目</button>
        <input v-model="projectFilter" class="search-input" placeholder="过滤项目..." />
      </div>
      <div class="project-grid scrollable">
        <div v-for="p in filteredProjects" :key="p.path" class="project-card">
          <div class="card-header">
            <span class="card-type">{{ typeIcon(p.type) }}</span>
            <span class="card-name">{{ p.name }}</span>
            <span v-if="acpRunning(p.path)" class="acp-badge">ACP 🟢</span>
          </div>
          <div class="card-meta">
            <span>{{ p.type }}</span>
            <span :class="{ bound: binding === p.path }">{{ binding === p.path ? '📌 已绑定' : '' }}</span>
            <span>{{ new Date(p.lastModified).toLocaleDateString() }}</span>
          </div>
          <div class="card-desc">{{ p.description || p.path }}</div>
          <div class="card-actions">
            <button v-if="!acpRunning(p.path)" class="btn sm accent" @click="doStartAcp(p)">🚀 opencode ACP</button>
            <button v-else class="btn sm danger" @click="doStopAcp(p)">■ 停止 ACP</button>
            <button v-if="acpRunning(p.path) && binding !== p.path" class="btn sm" @click="doBindFeishu(p)">📌 绑定飞书</button>
            <button v-else-if="binding === p.path" class="btn sm bound-btn" @click="doUnbindFeishu">📌 已绑定飞书</button>
            <button class="btn sm" @click="openFolder(p.path)">📂 文件夹</button>
            <button class="btn sm" @click="openVSCode(p.path)">💻 VS Code</button>
            <button class="btn sm" @click="removeProject(p)">🗑 移除</button>
          </div>
        </div>
      </div>
      <div v-if="filteredProjects.length === 0" class="empty">
        <p v-if="projects.length === 0">未找到项目，请点击"扫描项目"</p>
        <p v-else>无匹配项目</p>
      </div>
    </div>

    <!-- Terminal Tab -->
    <div v-if="tab === 'terminal'" class="content">
      <div class="session-bar">
        <div class="form-row">
          <label>项目路径</label>
          <input v-model="termProjectPath" class="input" placeholder="选择项目目录..." />
          <button class="btn sm" @click="pickProject">选择</button>
        </div>
        <div class="form-row">
          <label>AI 工具</label>
          <select v-model="termTool" class="input">
            <option value="opencode">opencode</option>
            <option value="claude">claude</option>
          </select>
        </div>
        <button v-if="!sessionActive" class="btn primary" @click="startAiSession">▶ 连接 {{ termTool }}</button>
        <button v-else class="btn danger" @click="stopAiSession">■ 断开</button>
        <span v-if="sessionActive" class="session-badge">● 已连接 (opencode -p)</span>
      </div>

      <div class="terminal-output" ref="terminalRef">
        <div v-for="(line, i) in sessionLog" :key="i" class="term-line" :class="line.role">
          <span class="term-prompt">{{ line.role === 'user' ? '>>>' : '🤖' }}</span>
          <span class="term-text">{{ line.text }}</span>
        </div>
        <div v-if="sessionActive && waitingResponse" class="term-line thinking">
          <span class="term-prompt">🤖</span>
          <span class="term-text">思考中...</span>
        </div>
      </div>

      <div v-if="sessionActive" class="session-input-bar">
        <input v-model="sessionInput" class="input" placeholder="输入消息，回车发送..." @keyup.enter="sendSessionInput" :disabled="waitingResponse" />
        <button class="btn primary" @click="sendSessionInput" :disabled="waitingResponse || !sessionInput.trim()">发送</button>
      </div>

      <div v-if="aiResult" class="result-box">
        <h4>上次 AI 响应</h4>
        <pre>{{ aiResult }}</pre>
      </div>
    </div>

    <!-- Feishu Tab -->
    <div v-if="tab === 'feishu'" class="content">
      <div class="settings-card">
        <h3>飞书机器人配置</h3>
        <p class="card-hint">直连飞书 WebSocket，无需公网地址</p>
        <div class="form-row">
          <label>App ID</label>
          <input v-model="feishuCfg.appId" class="input" placeholder="飞书开放平台 App ID" />
        </div>
        <div class="form-row">
          <label>App Secret</label>
          <input v-model="feishuCfg.appSecret" class="input" type="password" placeholder="飞书开放平台 App Secret" />
        </div>
        <div class="form-row">
          <label>启用</label>
          <label class="switch">
            <input type="checkbox" v-model="feishuCfg.enabled" />
            <span class="slider"></span>
          </label>
        </div>
        <div class="form-row">
          <label>状态</label>
          <span :class="['feishu-state', feishuConnStatus]">{{ feishuConnLabel }}</span>
        </div>
        <button class="btn primary" @click="saveFeishuConfig">💾 保存并连接</button>
        <button v-if="feishuConnStatus === 'connected'" class="btn danger" @click="disconnectFeishu">■ 断开</button>
        <button class="btn" @click="testFeishu">📨 发送测试消息</button>
        <div v-if="feishuStatus" class="status-msg" :class="feishuStatus.ok ? 'ok' : 'err'">{{ feishuStatus.msg }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const { execute } = defineProps<{ data: any; execute: Function; close: Function }>()

const tab = ref('projects')
const projects = ref<any[]>([])
const projectFilter = ref('')
const termProjectPath = ref('')
const termTool = ref('opencode')
const termPrompt = ref('')
const aiResult = ref('')
const sessionActive = ref(false)
const sessionInput = ref('')
const sessionLog = ref<Array<{ role: string; text: string }>>([])
const waitingResponse = ref(false)
const terminalRef = ref<HTMLElement | null>(null)
const feishuCfg = ref({ appId: '', appSecret: '', enabled: false, webhookUrl: '', secret: '' })
const feishuStatus = ref<{ ok: boolean; msg: string } | null>(null)
const feishuConnStatus = ref('stopped')
const acpStatus = ref<any[]>([])
const binding = ref('')
let acpPollTimer: any = null
const feishuConnLabel = computed(() => {
  const map: Record<string, string> = { connected: '✅ 已连接', connecting: '⏳ 连接中...', reconnecting: '🔄 重连中...', stopped: '⏹ 未连接', disconnected: '⏹ 已断开' }
  return map[feishuConnStatus.value] || feishuConnStatus.value
})

const filteredProjects = computed(() => {
  if (!projectFilter.value) return projects.value
  const q = projectFilter.value.toLowerCase()
  return projects.value.filter((p: any) => p.name.toLowerCase().includes(q) || p.path.toLowerCase().includes(q))
})

onMounted(async () => {
  const [proj, cfg, acp, bind] = await Promise.all([
    execute('getProjects'),
    execute('getFeishuConfig'),
    execute('getAcpStatus'),
    execute('getBinding'),
  ])
  projects.value = proj || []
  feishuCfg.value = cfg || { appId: '', appSecret: '', enabled: false, webhookUrl: '', secret: '' }
  acpStatus.value = acp || []
  binding.value = bind || ''
  startAcpPolling()
})

function acpRunning(path: string): boolean {
  return acpStatus.value.some((a: any) => a.path === path && a.running)
}

function startAcpPolling() {
  stopAcpPolling()
  acpPollTimer = setInterval(async () => {
    acpStatus.value = await execute('getAcpStatus') || []
  }, 3000)
}

function stopAcpPolling() {
  if (acpPollTimer) { clearInterval(acpPollTimer); acpPollTimer = null }
}

async function doStartAcp(p: any) {
  const r = await execute('startAcp', { path: p.path })
  if (r?.success) {
    acpStatus.value = await execute('getAcpStatus') || []
  }
}

async function doStopAcp(p: any) {
  await execute('stopAcp', { path: p.path })
  acpStatus.value = await execute('getAcpStatus') || []
}

async function doBindFeishu(p: any) {
  binding.value = p.path
  await execute('bindProject', { path: p.path })
}

async function doUnbindFeishu() {
  binding.value = ''
  await execute('bindProject', { path: '' })
}

async function removeProject(p: any) {
  await execute('removeProject', { path: p.path })
  projects.value = await execute('getProjects') || []
  acpStatus.value = await execute('getAcpStatus') || []
}

function typeIcon(type: string) {
  const map: Record<string, string> = { node: '🟢', python: '🐍', rust: '🦀', go: '🔵', dotnet: '🟣', other: '📁' }
  return map[type] || '📁'
}

async function addProjectDir() {
  const win = window as any
  let dir = ''
  if (win.mqbox?.dialog?.selectFolder) {
    dir = await win.mqbox.dialog.selectFolder()
  } else {
    dir = await execute('pickProject')
  }
  if (!dir) return
  await execute('addProject', { dir })
  projects.value = await execute('getProjects') || []
}

async function pickAndScan() {
  const win = window as any
  let dir = ''
  if (win.mqbox?.dialog?.selectFolder) {
    dir = await win.mqbox.dialog.selectFolder()
  } else {
    dir = await execute('pickProject')
  }
  if (!dir) return
  const proj = await execute('scanCustomDir', { dir })
  if (proj) projects.value = proj
}

async function pickProject() {
  const win = window as any
  let dir = ''
  if (win.mqbox?.dialog?.selectFolder) {
    dir = await win.mqbox.dialog.selectFolder()
  } else {
    dir = await execute('pickProject')
  }
  if (dir) termProjectPath.value = dir
}

function openTerminal(path: string, tool: string) {
  execute('launchTerminal', { path, tool })
}

function openFolder(path: string) {
  execute('openFolder', { path })
}

function openVSCode(path: string) {
  execute('openVSCode', { path })
}

function doLaunchTerminal() {
  execute('launchTerminal', { path: termProjectPath.value, tool: termTool.value, prompt: termPrompt.value })
}

async function startAiSession() {
  if (!termProjectPath.value) return
  sessionLog.value = []
  // Reset session on new connection (first run won't use -c)
  await execute('resetSession')
  sessionActive.value = true
  sessionLog.value.push({ role: 'system', text: `已连接 ${termTool.value}（opencode run -c），输入消息后回车` })
}

async function stopAiSession() {
  sessionActive.value = false
  waitingResponse.value = false
  sessionLog.value.push({ role: 'system', text: '已断开' })
}

async function sendSessionInput() {
  const text = sessionInput.value.trim()
  if (!text || waitingResponse.value || !termProjectPath.value) return
  sessionInput.value = ''
  sessionLog.value.push({ role: 'user', text })
  waitingResponse.value = true
  scrollTerminal()

  try {
    const result = await execute('spawnAiProcess', {
      tool: termTool.value,
      path: termProjectPath.value,
      input: text,
    })
    if (result?.error) {
      sessionLog.value.push({ role: 'system', text: `进程错误: ${result.error}` })
    } else {
      const output = result?.combined?.trim() || result?.stdout?.trim() || result?.stderr?.trim()
      if (output) {
        sessionLog.value.push({ role: 'assistant', text: output })
      } else {
        sessionLog.value.push({ role: 'system', text: `(模型无输出, exit code: ${result?.code ?? '?'})` })
      }
    }
  } catch (e: any) {
    sessionLog.value.push({ role: 'system', text: `错误: ${e.message || e}` })
  }
  waitingResponse.value = false
  scrollTerminal()
}

function scrollTerminal() {
  setTimeout(() => {
    if (terminalRef.value) terminalRef.value.scrollTop = terminalRef.value.scrollHeight
  }, 50)
}

async function saveFeishuConfig() {
  const ok = await execute('saveFeishuConfig', JSON.parse(JSON.stringify(feishuCfg.value)))
  if (ok) {
    feishuStatus.value = { ok: true, msg: '配置已保存，正在连接飞书...' }
    const started = await execute('startFeishu')
    if (started) {
      feishuConnStatus.value = 'connecting'
      feishuStatus.value = { ok: true, msg: '飞书客户端已启动' }
      startFeishuPolling()
    }
  } else {
    feishuStatus.value = { ok: false, msg: '保存失败' }
  }
  setTimeout(() => { feishuStatus.value = null }, 3000)
}

async function disconnectFeishu() {
  await execute('stopFeishu')
  feishuConnStatus.value = 'stopped'
  stopFeishuPolling()
}

async function testFeishu() {
  const ok = await execute('testFeishu')
  feishuStatus.value = ok ? { ok: true, msg: '测试消息已发送 ✓' } : { ok: false, msg: '发送失败，请检查配置' }
  setTimeout(() => { feishuStatus.value = null }, 3000)
}

let feishuPollTimer: any = null
async function startFeishuPolling() {
  const status = await execute('feishuStatus')
  feishuConnStatus.value = status
  feishuPollTimer = setTimeout(startFeishuPolling, 3000)
}
function stopFeishuPolling() {
  if (feishuPollTimer) { clearTimeout(feishuPollTimer); feishuPollTimer = null }
}

onUnmounted(() => {
  stopAcpPolling()
  stopFeishuPolling()
})
</script>

<style scoped>
.devops-page{padding:20px;font-family:'Segoe UI',sans-serif;color:#333;max-width:1200px;margin:0 auto}
.header{margin-bottom:20px}
.header h1{font-size:20px;font-weight:600;margin:0 0 12px 0}
.tabs{display:flex;gap:4px;border-bottom:1px solid #eee}
.tab{padding:8px 16px;border:none;background:transparent;font-size:13px;color:#666;cursor:pointer;border-bottom:2px solid transparent;transition:all 0.2s}
.tab:hover{color:#333}
.tab.active{color:#409EFF;border-bottom-color:#409EFF}
.content{padding:16px 0}
.toolbar{display:flex;gap:8px;margin-bottom:16px;align-items:center}
.search-input{flex:1;padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:12px;outline:none}
.search-input:focus{border-color:#409EFF}
.project-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.project-grid.scrollable{max-height:calc(100vh - 140px);overflow-y:auto;padding-bottom:20px}
.project-card{border:1px solid #eee;border-radius:8px;padding:12px;transition:box-shadow 0.2s}
.project-card:hover{box-shadow:0 2px 12px rgba(0,0,0,0.06)}
.card-header{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.card-type{font-size:16px}
.card-name{font-weight:600;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card-meta{display:flex;gap:12px;font-size:10px;color:#999;margin-bottom:6px}
.card-desc{font-size:11px;color:#666;margin-bottom:10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card-actions{display:flex;flex-wrap:wrap;gap:4px}
.btn{padding:6px 12px;border:1px solid #ddd;border-radius:5px;background:#fff;color:#444;font-size:11px;cursor:pointer}
.btn:hover{background:#f5f5f5}
.btn.primary{background:#409EFF;color:#fff;border-color:#409EFF}
.btn.primary:hover{background:#66b1ff}
.btn.sm{padding:4px 8px;font-size:10px}
.empty{text-align:center;padding:40px;color:#999;font-size:13px}
.settings-card{border:1px solid #eee;border-radius:8px;padding:20px;max-width:600px}
.settings-card h3{margin:0 0 16px;font-size:15px}
.form-row{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.form-row label{min-width:80px;font-size:12px;color:#666}
.input{flex:1;padding:7px 10px;border:1px solid #ddd;border-radius:5px;font-size:12px;outline:none}
.input:focus{border-color:#409EFF}
textarea.input{font-family:monospace;resize:vertical}
.result-box{border:1px solid #e0e0e0;border-radius:6px;padding:12px;margin-top:12px;background:#fafafa}
.result-box h4{margin:0 0 8px;font-size:12px;color:#666}
.result-box pre{font-size:11px;white-space:pre-wrap;word-break:break-all;margin:0;color:#333}
.status-msg{padding:8px 12px;border-radius:5px;margin-top:8px;font-size:12px}
.status-msg.ok{background:#e8f5e9;color:#2e7d32}
.status-msg.err{background:#ffebee;color:#c62828}
.switch{position:relative;display:inline-block;width:36px;height:20px}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background:#ccc;transition:0.3s;border-radius:20px}
.slider::before{content:'';position:absolute;height:16px;width:16px;left:2px;bottom:2px;background:#fff;transition:0.3s;border-radius:50%}
.switch input:checked+.slider{background:#409EFF}
.switch input:checked+.slider::before{transform:translateX(16px)}
.btn.danger{background:#e74c3c;color:#fff;border-color:#e74c3c}
.btn.danger:hover{background:#c0392b}
.btn.accent{background:#8B5CF6;color:#fff;border-color:#8B5CF6}
.btn.accent:hover{background:#7C3AED}
.acp-badge{font-size:10px;color:#8B5CF6;margin-left:auto;font-weight:600}
.bound{color:#8B5CF6;font-weight:500}
.bound-btn{color:#8B5CF6;border-color:#8B5CF6}
.session-badge{font-size:11px;color:#27ae60;margin-left:8px}
.session-bar{border:1px solid #eee;border-radius:8px;padding:16px;margin-bottom:12px;max-width:600px}
.terminal-output{border:1px solid #ddd;border-radius:6px;padding:10px;height:300px;overflow-y:auto;background:#1a1a2e;color:#e0e0e0;font-family:'Cascadia Code','Fira Code',monospace;font-size:12px;line-height:1.5;margin-bottom:8px}
.term-line{margin-bottom:2px;word-break:break-word}
.term-line.system{color:#888;font-style:italic}
.term-line.thinking{color:#888;animation:pulse 1.5s infinite}
.term-prompt{color:#4CAF50;margin-right:8px;user-select:none}
.term-line.user .term-prompt{color:#64B5F6}
.term-line.assistant .term-prompt{color:#FFD54F}
.term-text{white-space:pre-wrap}
.session-input-bar{display:flex;gap:8px}
@keyframes pulse{0%{opacity:0.4}50%{opacity:1}100%{opacity:0.4}}
</style>
