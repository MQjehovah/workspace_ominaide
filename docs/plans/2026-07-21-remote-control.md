# WebRTC 远程控制插件 - 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 OmniAide 增加 TeamViewer 式远程控制：被控端采集整台桌面经 WebRTC 推流，主控端查看画面并（阶段2起）注入鼠标键盘。支持同账号设备互连 + 配对码临时访问。

**Architecture:** WebRTC/屏幕采集/视频渲染在渲染进程（`Panel.vue` 主控被控、`Page.vue` 主控窗口）；nut-js 输入注入和被控状态在主进程（`index.ts`）；信令经后端 WebSocket 直连（渲染进程 → 后端 WS）。preload 桥接 desktopCapturer / injectInput / screenSize。

**Tech Stack:** 后端 FastAPI WebSocket；前端 Electron desktopCapturer + 浏览器 RTCPeerConnection + Vue3；输入注入 `@nut-tree-fork/nut-js`（阶段2）。

**参考设计:** `docs/plans/2026-07-21-remote-control-design.md`

**分阶段：** 本计划详细到阶段1（打通画面，无输入），阶段2/3 给任务大纲。每阶段结束可独立验收。

---

## 关键约定

- 房间号 `room_id`：同账号场景 = `u{user_id}_d{device_id}`；配对码场景 = 后端随机生成。
- 信令消息 JSON：`{type: 'join'|'leave'|'offer'|'answer'|'ice'|'requestControl'|'allow'|'deny', from, to?, payload?}`
- WS 鉴权：`ws://server/ws/remote/{room_id}?token=XXX`（复用 `decode_access_token`）
- `device_id`：桌面端首次生成一个 uuid 存 `config.json`（`window.mqbox.config.set('deviceId', ...)`）
- STUN 起步：`[{ urls: 'stun:stun.l.google.com:19302' }]`
- 渲染进程直接 `new WebSocket(...)`，不经主进程
- 项目无注释风格 + 规范禁止加注释

---

## 阶段 1：打通画面（仅查看，无输入）

### Task 1: 后端 — 信令 WS + 设备注册 + 配对码 + viewer 页

**Files:**
- Create: `backend/plugins/remote/__init__.py`
- Create: `backend/plugins/remote/router.py`
- Create: `backend/plugins/remote/service.py`
- Modify: `backend/main.py`（include router + WS）

**Step 1: service.py — 在线设备表 + 配对码表（内存）**

```python
import random
import time
from fastapi import WebSocket

_online: dict[str, dict] = {}     # device_id -> {user_id, room_id, name, ts}
_pairs: dict[str, dict] = {}      # code -> {room_id, user_id, device_id, expire_ts}
_rooms: dict[str, set] = {}       # room_id -> set[WebSocket]


def register_device(user_id: int, device_id: str, name: str, room_id: str):
    _online[device_id] = {"user_id": user_id, "room_id": room_id, "name": name, "ts": time.time()}


def unregister_device(device_id: str):
    _online.pop(device_id, None)


def list_devices(user_id: int):
    return [{"device_id": d, "name": v["name"], "room_id": v["room_id"]}
            for d, v in _online.items() if v["user_id"] == user_id]


def create_pair(user_id: int, device_id: str, room_id: str, ttl: int = 300):
    code = str(random.randint(100000, 999999))
    _pairs[code] = {"room_id": room_id, "user_id": user_id, "device_id": device_id, "expire_ts": time.time() + ttl}
    return code


def consume_pair(code: str):
    v = _pairs.get(code)
    if not v:
        return None
    if time.time() > v["expire_ts"]:
        _pairs.pop(code, None)
        return None
    room_id = v["room_id"]
    _pairs.pop(code, None)
    return room_id


async def room_join(room_id: str, ws: WebSocket):
    _rooms.setdefault(room_id, set()).add(ws)


async def room_leave(room_id: str, ws: WebSocket):
    if room_id in _rooms:
        _rooms[room_id].discard(ws)
        if not _rooms[room_id]:
            del _rooms[room_id]


async def room_broadcast(room_id: str, ws: WebSocket, message: dict):
    for peer in list(_rooms.get(room_id, set())):
        if peer is not ws:
            try:
                await peer.send_json(message)
            except Exception:
                pass
```

**Step 2: router.py — REST 端点 + WS + viewer HTML**

```python
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.auth.dependencies import get_current_user
from core.auth.jwt import decode_access_token
from plugins.remote import service as remote_service

router = APIRouter(prefix="/api/remote", tags=["remote"])


class OnlineRequest(__import__("pydantic").BaseModel):
    device_id: str
    name: str
    room_id: str


@router.post("/online")
async def go_online(req: OnlineRequest, user: dict = Depends(get_current_user)):
    remote_service.register_device(user["id"], req.device_id, req.name, req.room_id)
    return {"ok": True}


@router.delete("/online")
async def go_offline(user: dict = Depends(get_current_user)):
    # 按 user 清（简化：清该用户所有）
    for d in [k for k, v in remote_service._online.items() if v["user_id"] == user["id"]]:
        remote_service.unregister_device(d)
    return {"ok": True}


@router.get("/devices")
async def devices(user: dict = Depends(get_current_user)):
    return {"devices": remote_service.list_devices(user["id"])}


class PairRequest(__import__("pydantic").BaseModel):
    device_id: str
    room_id: str


@router.post("/pair")
async def make_pair(req: PairRequest, user: dict = Depends(get_current_user)):
    code = remote_service.create_pair(user["id"], req.device_id, req.room_id)
    return {"code": code}


@router.get("/pair/{code}")
async def check_pair(code: str):
    room_id = remote_service.consume_pair(code)
    if not room_id:
        raise HTTPException(status_code=410, detail="code invalid or expired")
    return {"room_id": room_id}


ws_router = APIRouter(tags=["remote"])


@ws_router.websocket("/ws/remote/{room_id}")
async def signaling_ws(websocket: WebSocket, room_id: str):
    token = websocket.query_params.get("token")
    payload = decode_access_token(token) if token else None
    if not payload:
        await websocket.close(code=4001)
        return
    await websocket.accept()
    await remote_service.room_join(room_id, websocket)
    try:
        while True:
            msg = await websocket.receive_json()
            await remote_service.room_broadcast(room_id, websocket, msg)
    except WebSocketDisconnect:
        pass
    finally:
        await remote_service.room_leave(room_id, websocket)


VIEWER_HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>OmniAide Remote</title><style>body{margin:0;background:#000}video{width:100vw;height:100vh;object-fit:contain}#bar{position:fixed;top:8px;left:8px;color:#fff;font:13px sans-serif;background:rgba(0,0,0,.5);padding:4px 8px;border-radius:6px}</style></head><body><div id='bar'>连接中…</div><video id='v' autoplay playsinline></video><script>
const params=new URLSearchParams(location.search);const code=params.get('code');
const v=document.getElementById('v'),bar=document.getElementById('bar');
const pc=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
pc.ontrack=e=>{v.srcObject=e.streams[0];bar.textContent='已连接'};
pc.onicecandidate=e=>{if(e.candidate)ws.send(JSON.stringify({type:'ice',payload:e.candidate.toJSON()}))};
let ws;
fetch('/api/remote/pair/'+code).then(r=>r.ok?r.json():Promise.reject()).then(d=>{
  ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws/remote/'+d.room_id+'?token='+encodeURIComponent(params.get('token')||''));
  ws.onmessage=async ev=>{const m=JSON.parse(ev.data);if(m.type==='offer'){await pc.setRemoteDescription(m.payload);ws.send(JSON.stringify({type:'answer',payload:(await pc.createAnswer()).toJSON()}));const ws2=ws;pc.onicecandidate=e=>{if(e.candidate)ws2.send(JSON.stringify({type:'ice',payload:e.candidate.toJSON()}))};}else if(m.type==='ice'){await pc.addIceCandidate(m.payload)}};
  ws.onopen=()=>bar.textContent='等待被控端…';
});
</script></body></html>"""


@router.get("/viewer", response_class=HTMLResponse)
async def viewer_page(code: str = Query(...)):
    return VIEWER_HTML
```

注意：上面 `__import__("pydantic").BaseModel` 是占位，实现时在文件顶部正规 `from pydantic import BaseModel`。WS 用单独 `ws_router` 因为 prefix 不同（WS 路径 `/ws/remote/...` 不带 `/api`）。

**Step 3: main.py — include 两个 router**

在 `backend/main.py` 现有 router include 附近追加：
```python
from plugins.remote.router import router as remote_router
app.include_router(remote_router)
from plugins.remote.router import ws_router as remote_ws_router
app.include_router(remote_ws_router)
```

**Step 4: 验证**
```bash
python -m py_compile backend/plugins/remote/router.py backend/plugins/remote/service.py
```
重启后端，curl 测：
```bash
# 登录拿 token
# GET /api/remote/devices 应返回 {"devices":[]}
# GET /api/remote/viewer?code=000000 应返回 HTML（200）
```

**Step 5: 提交**
```bash
git add backend/plugins/remote backend/main.py
git commit -m "feat(remote): 后端信令 WS + 设备注册 + 配对码 + viewer 页"
```

---

### Task 2: preload + 主进程 IPC — remote capability

**Files:**
- Modify: `desktop/src/preload/index.ts`（加 `mqbox.remote`）
- Modify: `desktop/src/main/ipc/index.ts`（加 `remote:get-sources`/`remote:screen-size`/`remote:inject` 占位）
- Modify: `desktop/src/main/plugin/sandbox.ts`（暴露 `remote` capability，按 permission）
- Modify: `desktop/src/shared/types.ts`（加 RemoteCapability 类型，可选）

**Step 1: preload 加 mqbox.remote**

在 `contextBridge.exposeInMainWorld('mqbox', {...})` 内追加：
```ts
  remote: {
    getDesktopSources: () => ipcRenderer.invoke('remote:get-sources'),
    getScreenSize: () => ipcRenderer.invoke('remote:screen-size'),
    injectInput: (event: any) => ipcRenderer.invoke('remote:inject', event),
    onControlRequest: (cb: (info: any) => void) => {
      ipcRenderer.on('remote:control-request', (_e, info) => cb(info))
    },
  },
```

**Step 2: main/ipc/index.ts 加 handler**

在现有 ipcMain.handle 区追加：
```ts
ipcMain.handle('remote:get-sources', async () => {
  const { desktopCapturer } = require('electron')
  const sources = await desktopCapturer.getSources({ types: ['screen'], fetchWindowIcons: false })
  return sources.map((s: any) => ({ id: s.id, name: s.name, display_id: s.display_id }))
})

ipcMain.handle('remote:screen-size', async () => {
  const { screen } = require('electron')
  const b = screen.getPrimaryDisplay().bounds
  return { width: b.width, height: b.height }
})

ipcMain.handle('remote:inject', async (_e, event: any) => {
  // 阶段1 不实现，阶段2 接 nut-js。返回 ok 占位
  return { ok: true, note: 'inject not implemented in phase 1' }
})
```

（确认 ipcMain 已在文件内 import；若用别的方式注册 handler 对齐现有风格）

**Step 3: sandbox 暴露 remote（按 permission）**

在 `desktop/src/main/plugin/sandbox.ts` 的 context 对象里，参照 `screenshotApi` 模式加：
```ts
    remote: perms.includes('remote') ? {
      getDesktopSources: () => require('electron').desktopCapturer.getSources({ types: ['screen'] }),
      getScreenSize: () => { const b = require('electron').screen.getPrimaryDisplay().bounds; return { width: b.width, height: b.height } },
    } : null,
```
（插件 index.ts 主进程可直接用；渲染进程经 preload `window.mqbox.remote`）

**Step 4: shared/types.ts 加类型（可选，保持类型完整）**

在 `PluginContext` 接口加 `remote?: RemoteCapability`，定义：
```ts
export interface RemoteCapability {
  getDesktopSources: () => Promise<any[]>
  getScreenSize: () => { width: number; height: number }
}
```

**Step 5: 构建验证**
```bash
cd desktop && npx vue-tsc --noEmit    # 若 pre-existing 报错忽略相关
```
（确认新加的 preload/IPC 无新 TS 错误）

**Step 6: 提交**
```bash
git add desktop/src/preload/index.ts desktop/src/main/ipc/index.ts desktop/src/main/plugin/sandbox.ts desktop/src/shared/types.ts
git commit -m "feat(remote): preload + 主进程 IPC 桥接 desktopCapturer/screenSize/inject"
```

---

### Task 3: 插件骨架 `desktop/plugins/remote/`

**Files:**
- Create: `desktop/plugins/remote/package.json`
- Create: `desktop/plugins/remote/vite.config.ts`
- Create: `desktop/plugins/remote/tsconfig.json`
- Create: `desktop/plugins/remote/src/index.ts`
- Create: `desktop/plugins/remote/src/Panel.vue`
- Create: `desktop/plugins/remote/src/Page.vue`
- Create: `desktop/plugins/remote/src/vite-env.d.ts`

**Step 1: package.json**（参照 player 插件）
```json
{
  "name": "omniaide-remote",
  "version": "1.0.0",
  "displayName": "远程控制",
  "description": "WebRTC 远程桌面控制",
  "main": "dist/index.js",
  "scripts": { "dev": "vite", "build": "vite build" },
  "omniaide": {
    "id": "remote",
    "displayName": "远程控制",
    "icon": "Monitor",
    "keywords": ["remote", "control", "screen"],
    "permissions": ["storage", "notification", "shell", "remote"],
    "builtin": true
  },
  "devDependencies": {
    "vite": "^5.2.0",
    "@vitejs/plugin-vue": "^5.2.4",
    "vue": "^3.5.40",
    "typescript": "~5.6.0"
  }
}
```

**Step 2: vite.config.ts / tsconfig.json / vite-env.d.ts** — 复制 player 插件同名文件，`name` 改 `RemotePlugin`、entry 不变。

**Step 3: src/index.ts（主进程，阶段1最小）**
```ts
import Panel from './Panel.vue'
import Page from './Page.vue'

let pluginCtx: any = null
let deviceId: string | null = null

async function getDeviceId(context: any): Promise<string> {
  if (deviceId) return deviceId
  let id = await context.storage?.get('deviceId')
  if (!id) {
    id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
    await context.storage?.set('deviceId', id)
  }
  deviceId = id
  return id
}

function getState() {
  return { hosting: false }
}

export default {
  panel: Panel,
  page: Page,
  async activate(context: any) {
    pluginCtx = context
    await getDeviceId(context)
    context.registerCommand('getPanelData', async () => getState())
    context.registerCommand('getPageData', async () => getState())
    context.registerCommand('open', async () => { context.openPage('remote') })
    context.registerCommand('getDeviceId', async () => deviceId)
    context.registerCommand('getServerConfig', async () => {
      const c = await context.api?.get('/health').catch(() => null)
      return null  // 渲染进程用 window.mqbox.config 拿 serverUrl/token
    })
  },
  deactivate() {},
}
```
（serverUrl/token 渲染进程经 `window.mqbox.config.get('serverUrl')` / `get('token')` 拿；主进程不直接参与信令）

**Step 4: Panel.vue（被控端开关 + 状态）** — 阶段1先放占位 UI：
```vue
<script setup lang="ts">
const props = defineProps<{ data: any; execute: (a: string, args?: any) => Promise<any>; openPage: () => void; refresh: () => Promise<void> }>()
</script>
<template>
  <div class="panel">
    <div class="panel-hd"><span class="title">远程控制</span></div>
    <button @click="openPage">打开远程控制</button>
  </div>
</template>
```

**Step 5: Page.vue（阶段1：被控推流 + 主控查看，先写框架）** — 完整 WebRTC 在 Task 4/5 填充，这里先建文件 + 两个模式切换骨架。

**Step 6: 构建验证**
```bash
cd desktop/plugins/remote && npm install && npm run build
```
确认 `dist/index.js` 生成。

**Step 7: 提交**
```bash
git add desktop/plugins/remote
git commit -m "feat(remote): 插件骨架（package/vite/index/Panel/Page）"
```

---

### Task 4: 被控端推流（Panel.vue + 共享 webrtc 模块）

**Files:**
- Create: `desktop/plugins/remote/src/webrtc.ts`（共享 WebRTC + 信令逻辑）
- Modify: `desktop/plugins/remote/src/Panel.vue`（被控开关 → 上线 → 建连推流）

**Step 1: webrtc.ts — 信令 WS + RTCPeerConnection 封装**

```ts
export async function getServer(): Promise<{ serverUrl: string; token: string }> {
  const serverUrl = await (window as any).mqbox.config.get('serverUrl')
  const token = await (window as any).mqbox.config.get('token')
  return { serverUrl: serverUrl || 'http://localhost:8000', token: token || '' }
}

export function openSignal(roomId: string, onMsg: (m: any) => void): Promise<WebSocket> {
  return getServer().then(({ serverUrl, token }) => {
    const wsUrl = serverUrl.replace(/^http/, 'ws') + `/ws/remote/${roomId}?token=${encodeURIComponent(token)}`
    const ws = new WebSocket(wsUrl)
    ws.onmessage = (e) => { try { onMsg(JSON.parse(e.data)) } catch {} }
    return new Promise<WebSocket>(res => { ws.onopen = () => res(ws) })
  })
}

export function newPeer(): RTCPeerConnection {
  return new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] })
}
```

**Step 2: Panel.vue — 被控上线 + 收到 offer 建连推流**

被控点"允许控制"时：
1. `await execute('getDeviceId')` 拿 deviceId
2. room_id = `u{userId}_d{deviceId}`（userId 经 `window.mqbox.config` 或 api 拿，简化：从 `/api/auth/me`；若无则 Panel 传 username）
3. POST `/api/remote/online`（body `{device_id, name, room_id}`）
4. `openSignal(roomId)` 建信令 WS，发 `{type:'join'}`
5. onMsg 收到 `{type:'offer', payload}` → 新建 peer → `desktopCapturer`+`getUserMedia` 拿屏幕流 → addTrack → setRemoteDescription(offer) → createAnswer → setLocalDescription → ws.send `{type:'answer', payload}` → onicecandidate 发 ice

```ts
// Panel.vue 被控核心（伪代码，实现时补全错误处理）
import { openSignal, newPeer } from './webrtc'
const hosting = ref(false)
let ws: WebSocket | null = null
const peerMap = new Map<string, RTCPeerConnection>()

async function startHost() {
  const deviceId = await props.execute('getDeviceId')
  const { serverUrl, token } = await getServer()
  const me = await fetch(`${serverUrl}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json())
  const roomId = `u${me.id}_d${deviceId}`
  await fetch(`${serverUrl}/api/remote/online`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ device_id: deviceId, name: '我的电脑', room_id: roomId }) })
  ws = await openSignal(roomId, onSignal)
  ws.send(JSON.stringify({ type: 'join' }))
  hosting.value = true
}

async function onSignal(m: any) {
  if (m.type === 'offer') {
    const sources = await (window as any).mqbox.remote.getDesktopSources()
    const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { mandatory: { chromeMediaSource: 'desktop', chromeMediaSourceId: sources[0].id, maxFrameRate: 30 } } } as any)
    const pc = newPeer()
    stream.getTracks().forEach(t => pc.addTrack(t, stream))
    peerMap.set(m.from || 'v', pc)
    await pc.setRemoteDescription({ type: 'offer', sdp: m.payload.sdp })
    const answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    ws!.send(JSON.stringify({ type: 'answer', payload: answer.toJSON() }))
    pc.onicecandidate = e => { if (e.candidate) ws!.send(JSON.stringify({ type: 'ice', payload: e.candidate.toJSON() })) }
  } else if (m.type === 'ice') {
    for (const pc of peerMap.values()) { try { await pc.addIceCandidate(m.payload) } catch {} }
  }
}
```
（`/api/auth/me` 若不存在，用现有任意已鉴权端点反推 user，或后端加 `/api/auth/me`。实现时确认。）

**Step 3: 构建验证 + 提交**
```bash
npm run build && git add -A && git commit -m "feat(remote): 被控端上线 + desktopCapturer 推流 + 信令 offer/answer"
```

---

### Task 5: 主控端查看（Page.vue）

**Files:**
- Modify: `desktop/plugins/remote/src/Page.vue`

主控 Page 打开后：
1. 列在线设备：`fetch('/api/remote/devices')` → 列表
2. 点设备 → room_id = 设备的 room_id → `openSignal(room_id)` → 发 join → 建 peer → createOffer → setLocalDescription → ws.send offer → onTrack 渲染 `<video>` → onicecandidate 发 ice → 收 answer setRemoteDescription → 收 ice addIceCandidate

```ts
// Page.vue 主控核心
import { openSignal, newPeer } from './webrtc'
const devices = ref<any[]>([])
const videoRef = ref<HTMLVideoElement | null>(null)
let ws: WebSocket | null = null
let pc: RTCPeerConnection | null = null

async function loadDevices() {
  const { serverUrl, token } = await getServer()
  const d = await fetch(`${serverUrl}/api/remote/devices`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json())
  devices.value = d.devices || []
}

async function connect(roomId: string) {
  ws = await openSignal(roomId, onSignal)
  ws.send(JSON.stringify({ type: 'join' }))
  pc = newPeer()
  pc.ontrack = e => { if (videoRef.value) videoRef.value.srcObject = e.streams[0] }
  pc.onicecandidate = e => { if (e.candidate) ws!.send(JSON.stringify({ type: 'ice', payload: e.candidate.toJSON() })) }
  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  ws.send(JSON.stringify({ type: 'offer', payload: offer.toJSON() }))
}

async function onSignal(m: any) {
  if (m.type === 'answer' && pc) { await pc.setRemoteDescription({ type: 'answer', sdp: m.payload.sdp }) }
  else if (m.type === 'ice' && pc) { try { await pc.addIceCandidate(m.payload) } catch {} }
}

onMounted(loadDevices)
```

模板：设备列表 + `<video autoplay playsinline ref="videoRef">`。

**构建验证 + 提交**
```bash
npm run build && git add -A && git commit -m "feat(remote): 主控端设备列表 + WebRTC 接收渲染"
```

---

### Task 6: 阶段1 集成验证

1. 重启后端、重启桌面 `npm run dev`
2. A 机：Panel "允许控制"上线
3. B 机（同账号）：打开 remote Page → 看到 A 机设备 → 点击 → 看到 A 机桌面实时画面
4. 浏览器：`{server}/api/remote/viewer?code=XXX`（先生成码）→ 输码页 → 看到 A 机画面
5. 掉线重连基本可用

**提交（如有修复）**
```bash
git add -A && git commit -m "fix(remote): 阶段1集成修复"
```

**阶段1 验收：** 主控实时看到被控桌面画面，浏览器配对码也能看。无输入。

---

## 阶段 2：输入注入（大纲）

- Task 7: 安装 `@nut-tree-fork/nut-js` 到插件，vite external，electron-rebuild
- Task 8: 主进程 IPC `remote:inject` 接 nut-js（mouse.move/press/release，keyboard.press/release，坐标换算）
- Task 9: 主控 Page.vue 采集 mouse/key 事件 → data channel → 被控 Panel.vue 接收 → `window.mqbox.remote.injectInput` → IPC → nut-js
- Task 10: 坐标换算（视频尺寸 ↔ 屏幕尺寸）、节流（mousemove 60Hz）
- Task 11: 验证：主控能操作被控桌面

## 阶段 3：配对码 + 被控确认 + TURN（大纲）

- Task 12: Panel 显示配对码、被控首次连接弹窗确认（preload `onControlRequest`）
- Task 13: viewer HTML 完善（移动端触屏→鼠标映射）
- Task 14: STUN/TURN 配置化（settings），macOS 权限提示检测
- Task 15: 全量验收

---

## 完成标志（全量）

1. 两台 OmniAide 同账号互连，主控看到并操作被控桌面
2. 被控 Panel 可开关，首次连接确认
3. 手机/浏览器配对码临时连接可查看并可操作（阶段3）
4. 后端 WS 信令稳定
5. nut-js 在 Electron 主进程注入生效（阶段2）
6. 阶段1 不依赖原生模块即可独立验证
