# 远程控制 UI 重构 + 多屏 - 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把远程控制 Page 重构成 TeamViewer 式管理页 + 独立 viewer 会话窗口；Panel 独立做被控；加多屏切换与精确坐标。

**Architecture:** host(WebRTC/采集/注入)留 Panel 渲染进程；Page 改派发器按 URL `mode` 参数渲染 ManagementDashboard 或 ViewerSession；viewer 经 `openPage(pluginId, query)` 独立开窗；多屏走 data channel 控制消息 + replaceTrack 热切换 + 按 display bounds/scaleFactor 算坐标。

**Tech Stack:** Electron + Vue3 + WebRTC + nut-js（已有）。

**参考设计:** `docs/plans/2026-07-22-remote-redesign-design.md`

---

## 关键约定

- openPage 现有两条路径都要加 query 支持：
  - 渲染进程：`window.mqbox.window.openPage` → preload → IPC `window:open-page`（desktop/src/main/index.ts:113）
  - 插件 sandbox：`context.openPage`（sandbox.ts:145）
- Page 读 URL：`new URLSearchParams(window.location.search)`（PluginPage.vue 已这么读 pluginId）
- data channel 既是输入通道，也承载多屏控制消息（host↔viewer 双向）
- 项目无注释风格 + 规范禁止加注释
- 工作目录 `E:\workspace_ominaide`，分支 `feat/remote-redesign`

---

### Task 1: openPage 支持 query 参数

**Files:**
- Modify: `desktop/src/preload/index.ts`（openPage 签名加 query）
- Modify: `desktop/src/main/index.ts:113`（window:open-page handler 接 query 拼 URL）
- Modify: `desktop/src/main/plugin/sandbox.ts:145`（context.openPage 接 query 拼 URL）
- Modify: `desktop/src/shared/types.ts`（Window/PluginContext openPage 类型加 query）

**Step 1: preload**
```ts
openPage: (pluginId: string, query?: string) => ipcRenderer.invoke('window:open-page', pluginId, query || ''),
```

**Step 2: main/index.ts handler**
```ts
ipcMain.handle('window:open-page', async (_, pluginId: string, query: string = '') => {
  const cfg = await getConfig()
  if (!cfg.token) return
  const win = new BrowserWindow({ width: 900, height: 700, webPreferences: { preload: preloadPath, contextIsolation: true } })
  const extra = query ? '&' + query : ''
  const url = process.env.VITE_DEV_SERVER_URL
    ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-page&pluginId=${pluginId}${extra}`
    : `file://${join(__dirname, '../../dist/index.html').replace(/\\/g, '/')}?view=plugin-page&pluginId=${pluginId}${extra}`
  win.loadURL(url)
})
```

**Step 3: sandbox context.openPage**（同样加 extra 拼接）
```ts
openPage: (pluginId: string, query?: string) => {
  const extra = query ? '&' + query : ''
  // ... 现有 BrowserWindow 创建 ...
  const url = process.env.VITE_DEV_SERVER_URL
    ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-page&pluginId=${pluginId}${extra}`
    : `file://${...}?view=plugin-page&pluginId=${pluginId}${extra}`
  win.loadURL(url)
}
```

**Step 4: types.ts** openPage 类型加 `query?: string`（Window 的 mqbox.window.openPage 和 PluginContext.openPage 都加）

**Step 5: 验证** `cd desktop && npx vue-tsc --noEmit`（pre-existing 错忽略，确认新改无新错）

**Step 6: 提交** `git commit -m "feat(remote): openPage 支持 query 参数（viewer 独立开窗基础）"`

---

### Task 2: remote:get-all-displays IPC + 暴露

**Files:**
- Modify: `desktop/src/main/ipc/index.ts`（加 handler）
- Modify: `desktop/src/main/plugin/sandbox.ts`（remote capability 加 getAllDisplays）
- Modify: `desktop/src/preload/index.ts`（mqbox.remote 加 getAllDisplays）

**Step 1: ipc handler**
```ts
ipcMain.handle('remote:get-all-displays', async () => {
  try {
    const { screen } = require('electron')
    return screen.getAllDisplays().map((d: any) => ({
      id: d.id, name: `${d.bounds.width}x${d.bounds.height}`,
      bounds: { x: d.bounds.x, y: d.bounds.y, width: d.bounds.width, height: d.bounds.height },
      scaleFactor: d.scaleFactor || 1,
    }))
  } catch { return [] }
})
```

**Step 2: sandbox remote** 加 `getAllDisplays: () => { 类似，返回 screen.getAllDisplays() map }`

**Step 3: preload** `getAllDisplays: () => ipcRenderer.invoke('remote:get-all-displays'),`

**Step 4: 验证 + 提交** `git commit -m "feat(remote): remote:get-all-displays IPC（多屏坐标基础）"`

---

### Task 3: 插件 syncHostState + getPageData 扩展

**Files:**
- Modify: `desktop/plugins/remote/src/index.ts`

**Step 1: index.ts 加 hostState + syncHostState 命令**
```ts
let hostState = { enabled: false, code: '', status: '', peerConnected: false }

function getState() {
  return { hosting: hostState.enabled, hostState }
}

// 在 activate 里加：
context.registerCommand('syncHostState', async (args: any) => {
  if (args) hostState = { ...hostState, ...args }
  return getState()
})
```
（getPanelData/getPageData 现有调 getState()，自动带 hostState）

**Step 2: 验证** `cd desktop/plugins/remote && npm run build`

**Step 3: 提交** `git commit -m "feat(remote): syncHostState 命令 + getPageData 带 hostState"`

---

### Task 4: Panel.vue 自动配对码 + 推状态 + 开管理页 + 多屏 host 端

**Files:**
- Modify: `desktop/plugins/remote/src/Panel.vue`

这是大改。分几部分：

**4a. 自动配对码**：startHost 成功后自动 POST /pair 生成码，定时 4 分钟刷新，stopHost 清码。把 code/status 经 `props.execute('syncHostState', {...})` 推到主进程。
```ts
let codeTimer: any = null
async function genPairAuto(deviceId: string) {
  try {
    const { serverUrl } = await getServer(); const headers = await getAuthHeaders()
    const r = await fetch(`${serverUrl}/api/remote/pair`, { method:'POST', headers, body: JSON.stringify({ device_id: deviceId, room_id: currentRoomId }) }).then(r=>r.json())
    pairCode.value = r.code; status.value = `配对码: ${r.code}`
    await props.execute('syncHostState', { enabled: true, code: r.code, status: '允许控制中' })
    if (codeTimer) clearInterval(codeTimer)
    codeTimer = setInterval(() => genPairAuto(deviceId), 240000)
  } catch (e:any) { status.value = '生成配对码失败: ' + (e?.message||e) }
}
```
startHost 末尾调 `genPairAuto(deviceId)`；stopHost 清 codeTimer + `props.execute('syncHostState', {enabled:false, code:'', status:'', peerConnected:false})`。建连后推 `{peerConnected:true}`，断开推 false。

**4b. 开管理页按钮**：模板顶部加
```html
<button class="btn ghost" @click="(props as any).openPage?.('remote')">管理页</button>
```
（Panel props 已有 openPage；若类型无则用 `(window as any).mqbox.window.openPage('remote')`）

**4c. 多屏 host 端**：
- 模块级：`let currentDisplay: any = null`（当前共享屏的 display bounds+scaleFactor）
- 建连后（offer 处理里 getUserMedia 后）：枚举屏 + 发屏幕列表给 viewer
```ts
const allDisplays = await (window as any).mqbox.remote.getAllDisplays()
const sources = ... (已有)
// 匹配主屏或 sources[0]
currentDisplay = matchDisplay(sources[0], allDisplays)
// 发屏幕列表给 viewer（data channel 已开）
dc.send(JSON.stringify({ type:'screens', list: sources.map(s => ({id:s.id, name:s.name})) }))
dc.send(JSON.stringify({ type:'activeScreen', id: sources[0].id }))
```
- dc.onmessage 里加 switchScreen 处理（在 handleInput 之前判断 control 消息）：
```ts
dc.onmessage = async (msg) => {
  const ev = JSON.parse(msg.data)
  if (ev.type === 'switchScreen') { await switchScreen(ev.sourceId); return }
  await handleInput(ev)
}
async function switchScreen(sourceId: string) {
  const newStream = await navigator.mediaDevices.getUserMedia({ audio:false, video:{ mandatory:{ chromeMediaSource:'desktop', chromeMediaSourceId:sourceId, maxFrameRate:30 } } as any })
  const sender = pc!.getSenders().find(s => s.track && s.track.kind === 'video')
  if (sender) { await sender.replaceTrack(newStream.getVideoTracks()[0]) }
  if (stream) stream.getTracks().forEach(t=>t.stop())
  stream = newStream
  const allDisplays = await (window as any).mqbox.remote.getAllDisplays()
  const src = (await (window as any).mqbox.remote.getDesktopSources()).find((s:any)=>s.id===sourceId)
  currentDisplay = matchDisplay(src, allDisplays)
  dc.send(JSON.stringify({ type:'activeScreen', id: sourceId }))
}
function matchDisplay(src:any, displays:any[]) {
  if (!src) return displays[0]
  return displays.find(d => String(d.id) === String(src.display_id)) || displays[0]
}
```
- 坐标换算改：flushMove 和其他注入用 currentDisplay 的 bounds+x/y 偏移 + scaleFactor
```ts
async function flushMove() {
  if (!pendingMove || !currentDisplay) return
  const m = pendingMove; pendingMove = null
  const d = currentDisplay; const sf = d.scaleFactor || 1
  const x = Math.round((d.bounds.x + (Number(m.x)||0) * d.bounds.width) * sf)
  const y = Math.round((d.bounds.y + (Number(m.y)||0) * d.bounds.height) * sf)
  await (window as any).mqbox.remote.injectInput({ type:'mouseMove', x, y })
}
```
（getScreen/getScreenSize 缓存可移除，改用 currentDisplay）

**Step: 验证** `npm run build`；**提交** `git commit -m "feat(remote): Panel 自动配对码 + 推状态 + 多屏 host（屏幕列表/热切换/精确坐标）"`

---

### Task 5: Page.vue 改派发器

**Files:**
- Modify: `desktop/plugins/remote/src/Page.vue`（改成派发器，逻辑移到 ViewerSession）

**Step 1: Page.vue 改成**
```vue
<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
const params = new URLSearchParams(window.location.search)
const mode = params.get('mode')
const room = params.get('room')
const ViewerSession = defineAsyncComponent(() => import('./ViewerSession.vue'))
const ManagementDashboard = defineAsyncComponent(() => import('./ManagementDashboard.vue'))
defineProps<{ data: any; execute: (a:string,args?:any)=>Promise<any>; refresh?: ()=>void; close: ()=>void }>()
</script>
<template>
  <component :is="mode === 'viewer' ? ViewerSession : ManagementDashboard" :room="room" />
</template>
```
（ViewerSession/Dashboard 需要 execute/data/close 等 props；用 v-bind="$attrs" 或显式传。简化：Page 用 `<component :is=... :data=... :execute=... :close=... :refresh=... :room="room" />`，但 setup 里没拿 props 变量。改用：Page 接 props 并全透传给子组件）

实际实现：Page 接 props，模板里把所有 props + room 传给子组件。

**Step 2: 提交** `git commit -m "refactor(remote): Page 改派发器（mode=viewer→ViewerSession，否则→ManagementDashboard）"`

---

### Task 6: ViewerSession.vue（独立会话窗口）

**Files:**
- Create: `desktop/plugins/remote/src/ViewerSession.vue`

从当前 Page.vue 的 viewer 逻辑（connect/startOffering/onSignal/sendInput/normVideo/输入捕获/cleanup/backToMenu）搬过来，加：
- props: room（从 URL）
- 屏幕切换器：收 `{type:'screens',list}` → 渲染按钮；选屏发 `{type:'switchScreen',sourceId}`；收 `{type:'activeScreen',id}` 高亮
- connect(room) 用 props.room（URL 来的）而非设备列表点击

```vue
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { openSignal, newPeer, getServer, getAuthHeaders, getIceServers } from './webrtc'
const props = defineProps<{ data:any; execute:(a:string,args?:any)=>Promise<any>; refresh?:()=>void; close:()=>void; room?:string }>()
const videoRef = ref<HTMLVideoElement|null>(null)
const status = ref(''); const connected = ref(false)
const screens = ref<any[]>([]); const activeScreen = ref<string>('')
let ws:any=null, pc:any=null, dc:any=null, pendingIce:any[]=[], connectionEnded=false

async function connect(roomId:string){ /* 同原 Page connect，用 props.room */ 
  // ... openSignal, requestControl, newPeer(await getIceServers()) ...
}
async function startOffering(){ /* createDataChannel + addTransceiver video recvonly + ontrack + createOffer + send offer */ }
async function onSignal(m:any){ /* controlAllowed→startOffering; answer→setRemoteDesc+flush ice; ice→buffer/add; error/revoked/controlDenied */ }
function onInput(ev:any){ /* normVideo/sendInput */ }
function switchScreen(id:string){ if(dc&&dc.readyState==='open') dc.send(JSON.stringify({type:'switchScreen',sourceId:id})) }
// dc.onmessage 也要处理 host 发来的 screens/activeScreen（在 ViewerSession 里 dc 是自己创建的，host 经 dc.send 发过来——onmessage 处理）
onMounted(()=>{ if(props.room) connect(props.room) })
onUnmounted(()=>{ cleanup() })
</script>
```
（注意：ViewerSession 创建的 dc，host 经同一条 dc 发 screens/activeScreen；ViewerSession 的 dc.onmessage 要分流：输入消息 vs 控制消息。但 ViewerSession 是 dc 创建方，它只发输入；host 是 dc 接收方用 ondatachannel。host→viewer 的消息（screens/activeScreen）走同一条 dc 反向——dc 双向，ViewerSession 设 dc.onmessage 收 host 的控制消息）

**Step 1: 创建 ViewerSession.vue（搬 viewer 逻辑 + 屏幕切换器 UI + dc.onmessage 分流控制消息）**

**Step 2: 验证 build + 提交** `git commit -m "feat(remote): ViewerSession 独立会话窗口 + 屏幕切换器"`

---

### Task 7: ManagementDashboard.vue（管理页）

**Files:**
- Create: `desktop/plugins/remote/src/ManagementDashboard.vue`

```vue
<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { getServer, getAuthHeaders } from './webrtc'
const props = defineProps<{ data:any; execute:(a:string,args?:any)=>Promise<any>; refresh?:()=>void; close:()=>void }>()
const devices = ref<any[]>([])
const hostState = ref<any>({ enabled:false, code:'', status:'' })
const pairInput = ref('')
let pollTimer: any = null

async function loadDevices(){ /* fetch /api/remote/devices */ }
async function loadHostState(){ hostState.value = props.data?.hostState || { enabled:false, code:'', status:'' } }
function controlDevice(roomId:string){ (window as any).mqbox.window.openPage('remote', `mode=viewer&room=${roomId}`) }
async function connectByCode(){ /* fetch /api/remote/pair/{code} → controlDevice(room_id) */ }
onMounted(()=>{ loadDevices(); loadHostState(); pollTimer = setInterval(()=>{ loadDevices(); props.refresh?.(); loadHostState() }, 5000) })
onUnmounted(()=>{ if(pollTimer) clearInterval(pollTimer) })
</script>
<template>
  <!-- 顶部本机状态+配对码（hostState.code 或提示去面板开被控）
       中部设备列表（点控制→controlDevice）
       底部配对码输入→connectByCode -->
</template>
```

**Step 1: 创建 ManagementDashboard.vue**

**Step 2: build + 提交** `git commit -m "feat(remote): ManagementDashboard 管理页（设备列表+配对码镜像+开viewer）"`

---

### Task 8: 集成验证

1. `npm run dev`
2. Panel 开被控 → 自动显示配对码 + 推状态
3. 打开管理页（Panel 按钮 / openPage remote）→ 看到本机码 + 设备列表
4. 管理页点设备"控制" → 开独立 viewer 窗口 → 看到画面 + 能控制
5. 多屏：viewer 切换器切屏 → 画面切换 + 鼠标在新屏精确
6. 关管理页 → Panel 仍被控
7. 提交修复（如有）

---

## 完成标志

1. Panel 独立被控，配对码自动显示，管理页镜像本机码
2. 管理页列设备，点控制开独立 viewer 窗口
3. 多屏切换器工作，每屏鼠标精确
4. 关管理页不影响 Panel host
5. openPage query + get-all-displays IPC 可用
