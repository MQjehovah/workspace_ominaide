# WebRTC 远程控制插件 - 设计文档

日期: 2026-07-21
状态: 已确认

## 背景

OmniAide 桌面端（Electron + Vue3 插件架构）需要一个类似 TeamViewer 的远程控制能力：被控端采集整台电脑桌面，主控端查看画面并注入鼠标键盘，实现远程操作。

用户需求：
- 控制目标：**整个电脑桌面**（全屏采集 + 鼠标键盘注入）
- 控制方：两台都装 OmniAide 的电脑互控为主；同时支持手机/浏览器临时访问
- 连接方式：同账号设备列表 + 配对码（都要）
- 输入注入：接受原生模块（nut-js）依赖

## 关键架构约束

WebRTC（`RTCPeerConnection`）、屏幕采集（`getUserMedia`）、视频渲染是**渲染进程** API；输入注入（nut-js）和被控状态管理需要 OS 权限，必须在**主进程**。当前插件逻辑跑在主进程 sandbox。因此本插件**跨进程协作**：

| 能力 | 运行位置 | 文件 |
|---|---|---|
| WebRTC 连接、信令 WS、屏幕采集、视频渲染、本地输入采集、坐标换算 | 渲染进程 | `Page.vue` |
| 鼠标/键盘注入（nut-js）、被控端上下线、被控同意确认 | 主进程 | `index.ts` |
| 桥接（desktopCapturer 源、input 注入 IPC、屏幕尺寸查询） | preload | `preload/index.ts` 扩展 |

渲染进程**直连后端 WebSocket** 做信令，绕开主进程中转，降低延迟。

## 目标

- 被控端：采集桌面画面经 WebRTC 推流；接收主控输入并经 nut-js 注入操作系统
- 主控端：渲染远端 `<video>`；采集本地鼠标键盘经 data channel 上行
- 信令：后端 WebSocket 房间中转 SDP/ICE
- 发现：同账号在线设备列表 + 6 位配对码（TTL）
- 临时访问：后端托管独立 viewer HTML 页，手机/浏览器扫码/输码即用
- 安全：被控端显式开关 + 首次连接弹窗确认；配对码短 TTL

## 非目标（分阶段外）

- 阶段 3 之外的多路并发、文件传输、剪贴板同步、音频
- 录制/回放

## 数据模型

### WebRTC
- `RTCPeerConnection`（渲染进程）配 `iceServers`（先用 Google 公共 STUN，后续按需加 coturn TURN）
- 视频：被控 `desktopCapturer` → `getUserMedia({video:{chromeMediaSource:'desktop', chromeMediaSourceId}})` → addTrack
- data channel 名 `input`：主控→被控的输入事件 JSON

### 输入事件协议（data channel JSON）
```ts
{ type: 'mouseMove', x: number, y: number }            // 绝对坐标（已换算到被控屏幕分辨率）
{ type: 'mouseDown', button: 'left'|'right'|'middle' }
{ type: 'mouseUp',   button: 'left'|'right'|'middle' }
{ type: 'wheel',     deltaX: number, deltaY: number }
{ type: 'keyDown',   keyCode: number, code?: string }
{ type: 'keyUp',     keyCode: number, code?: string }
{ type: 'clipboard', text: string }   // 阶段3 可选
```
主控在 `Page.vue` 捕获事件 → 按视频显示尺寸/被控屏幕尺寸比例换算坐标 → data channel 发送。

### 房间与配对码（后端）
- `room_id` = `{host_user_id}_{host_device_id}`（同账号）；配对码场景 `room_id` 由后端随机生成并映射
- 配对码：6 位数字，TTL 5 分钟，一次性（连入即失效），存内存/Redis

## 组件

### 1. 桌面插件 `desktop/plugins/remote/`
- `src/index.ts`（主进程）：
  - 注册命令：`startHost`/`stopHost`（上下线）、`injectInput(event)`（调 nut-js）、`getScreenSize`、`confirmConnect`（弹窗）
  - 暴露 `context.registerIpc` 或经现有 IPC：渲染进程通过 `window.mqbox.remote.injectInput` 调主进程注入
  - 被控状态：hosting on/off，当前连接的 peer
- `src/Panel.vue`（渲染进程）：
  - 被控开关、在线状态指示、配对码显示、一键停止、被控请求确认弹窗
- `src/Page.vue`（渲染进程，主控全屏窗口）：
  - `<video>` 渲染远端画面；鼠标键盘监听；坐标换算；WebRTC + 信令 WS；连接设备列表/配对码输入
- `package.json`：依赖 `@nut-tree-fork/nut-js`（vite external），`webrtc-adapter`（可选兼容）
- `vite.config.ts`：external `@nut-tree-fork/nut-js`

### 2. 后端 `backend/plugins/remote/`
- `router.py`：
  - `POST /api/remote/online` — 被控上线注册（device_id, room_id）
  - `DELETE /api/remote/online` — 下线
  - `GET /api/remote/devices` — 列同账号在线被控
  - `POST /api/remote/pair` — 生成配对码 → room_id
  - `GET /remote/viewer?code=XXX` — 返回独立 viewer HTML（临时设备）
- `ws.py` / 路由 `GET /ws/remote/{room_id}`：
  - 房间管理：join/leave；中继 `{type:'offer'|'answer'|'ice'|'requestControl'}` 消息给房内对端
  - 鉴权：token query（同 WS sync 模式）
- `service.py`：在线设备表（内存或 Redis）、配对码表、房间→连接池

### 3. preload 扩展 `desktop/src/preload/index.ts`
新增 `window.mqbox.remote`：
- `getDesktopSources()` → 调 `desktopCapturer.getSources({types:['screen']})`
- `injectInput(event)` → `ipcRenderer.invoke('remote:inject', event)`
- `getScreenSize()` → 主进程 `screen.getPrimaryScreen().size`
- `onControlRequest(cb)` → 监听主控连接请求（被控确认）

主进程 `desktop/src/main/ipc/index.ts` 注册 `remote:inject` handler 调插件的 nut-js 注入；sandbox 暴露 `remote` capability（按 permissions 控制）。

## 连接流程

### 同账号
1. 被控端 Panel 开启"允许控制" → `startHost` → POST `/api/remote/online`
2. 主控端 Page 加载 → GET `/api/remote/devices` 看到被控 → 点击连接
3. 双方 WS 入房 `{user}_{device}`
4. 主控发 `requestControl` → 被控弹窗确认 → 同意
5. 主控 createOffer → 被控 createAnswer + ICE 互换（WS 中继）
6. 被控 addTrack（屏幕流）+ 开 data channel；主控 onTrack 拿 video 渲染
7. 主控输入 → data channel → 被控渲染进程 → IPC → nut-js 注入

### 配对码（临时设备）
1. 被控 Panel 点"生成配对码" → POST `/api/remote/pair` → 拿 6 位码 + room_id
2. 手机/浏览器打开 `{server}/remote/viewer?code=XXX` → 后端校验码 → 返回 viewer HTML
3. viewer 页 WS 入 room_id → 发 requestControl → 被控确认 → WebRTC 建立
4. 后续同上

## 安全
- 被控端"允许控制"开关默认关；每次新 peer 连接弹窗确认（显示来源：同账号设备 / 配对码）
- 配对码 TTL 5 分钟，连入失效
- WS 鉴权用 token query（复用现有模式）
- data channel 只传输入事件，不接受任意命令
- viewer HTML 页 XSS 防护：code 仅服务端校验，不内嵌到 HTML

## 主要风险与对策

1. **原生模块（nut-js）构建**：插件 vite 打包需 external；Electron 需 electron-rebuild 对齐 ABI。对策：nut-js 放插件 `node_modules`，vite external，构建脚本调 electron-rebuild；loader.ts 解析时允许 native require。若 loader 不支持外部 native 模块，回退方案 B：放主工程依赖，sandbox context 暴露 `injectInput`。
2. **NAT 穿透**：公网部署需 STUN/TURN。起步用 `stun:stun.l.google.com:19302`；NAT 对称型失败时提示需 TURN（后续加 coturn）。
3. **性能**：1080p 屏幕流带宽高。对策：desktopCapturer 限制 `maxFrameRate: 30`，分辨率按需缩放；data channel 输入事件合并/节流（mousemove 节流到 ~60Hz）。
4. **权限**：macOS 需"屏幕录制"和"辅助功能"权限；Windows 注入一般无障碍。首启检测并提示。

## 分阶段实施

- **阶段 1（打通画面）**：被控采集→主控查看。含：插件骨架、后端 WS 信令、desktopCapturer、WebRTC video、同账号设备列表、preload getDesktopSources。**无输入**。验收：主控能看到被控桌面实时画面。
- **阶段 2（输入注入）**：data channel + nut-js 鼠标键盘 + 坐标换算 + 主控输入采集。preload injectInput + IPC。验收：主控能操作被控桌面。
- **阶段 3（临时访问）**：配对码 + 后端 viewer HTML 页 + 被控确认弹窗 + STUN 配置化。验收：手机浏览器输码即连即控。

## 验收标准（全量）
1. 两台装 OmniAide 的电脑同账号互连，主控实时看到被控桌面并可操作鼠标键盘
2. 被控端 Panel 可开关"允许控制"，首次连接弹窗确认
3. 手机/浏览器通过配对码临时连接，可查看（阶段3可操作）
4. 后端 WS 信令稳定，掉线可重连
5. 原生模块 nut-js 正确 rebuild 并在 Electron 主进程注入生效
6. 无输入阶段不依赖原生模块（阶段1可独立验证）
