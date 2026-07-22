# 远程控制 UI 重构 + 多屏 - 设计文档

日期: 2026-07-22
状态: 已确认
分支: feat/remote-redesign

## 背景

远程控制功能已端到端打通（视频/控制/鼠标精确）。现需：
1. UI 重构：管理页（Page）做成 TeamViewer 式主界面（自动配对码 + 设备列表）；远控会话做成独立窗口（非 Page）；Panel 仍能独立做被控
2. 多屏优化：主控端可切换显示器，坐标按实际屏精确换算

## 目标

- Panel 独立被控（关 Page 不影响 host）
- Page = 管理页（镜像本机状态/配对码 + 在线设备列表 + 开 viewer）
- Viewer = 独立会话窗口（画面 + 控制 + 显示器切换）
- 多屏：被控共享屏列表，主控切换，replaceTrack 热切换，坐标按屏精确算

## 架构约束

- 插件系统一个 `page` 入口（`openPage` 开一个 BrowserWindow）
- WebRTC/getUserMedia 只能在渲染进程跑
- host 逻辑留 Panel（避免 Panel/Page 双开时 WebRTC 冲突），Dashboard 只镜像状态

## 组件

### 1. Panel.vue（被控之家，独立，小改）
- 保留完整 host 逻辑（startHost/stopHost/capture/answer/inject/确认弹窗）
- host 启用时自动生成配对码并显示
- 新增：经 `syncHostState` 命令把 {enabled, code, status, peerConnected} 推到插件主进程
- 加"打开管理页"按钮（调 openPage('remote')）

### 2. Page.vue（派发器）
- 读 URL `mode` 参数：无 mode → ManagementDashboard；mode=viewer → ViewerSession
- 传 props（含 roomId 等从 URL 解析）

### 3. ManagementDashboard.vue（管理页，新增）
- 顶部：本机 host 状态镜像 + 配对码（从 getPageData 读，Panel 推送）；host 未开则提示"在面板开启被控"
- 中部：在线设备列表（GET /api/remote/devices）→ 点"控制"开 viewer 窗口（openPage 带 mode=viewer&room=xxx）
- 底部：配对码输入 → 开 viewer 窗口
- 自动刷新（轮询 getPageData + 设备列表）

### 4. ViewerSession.vue（独立会话窗口，新增）
- 从 URL 取 room → connect（requestControl → offer → 收 answer → ontrack 渲染）
- 鼠标/键盘/滚轮捕获 + 发 data channel（含 letterbox 归一化）
- 顶部显示器切换器（收 screens 列表 → 选屏 → 发 switchScreen）
- 断开/返回

### 5. webrtc.ts（扩展）
- 现有 getServer/openSignal/newPeer/getIceServers/getAuthHeaders 保留
- data channel 协议扩展：viewer↔host 新增控制消息
  - host→viewer: `{type:'screens', list:[{id,name}]}`、`{type:'activeScreen', id}`
  - viewer→host: `{type:'switchScreen', sourceId}`
- 输入消息（mouseMove 等）不变

## 多屏数据流

1. host startHost/建连后：`desktopCapturer.getSources({types:['screen']})` 拿所有屏 + `screen.getAllDisplays()` 拿 bounds/scaleFactor
2. host 默认共享主屏（匹配 primaryDisplay 的 source），getUserMedia + addTrack
3. host 经 data channel 发 `{type:'screens', list}` + `{type:'activeScreen', id}` 给 viewer
4. viewer 顶部渲染切换器；选屏 → 发 `{type:'switchScreen', sourceId}`
5. host 收 switchScreen：
   - getUserMedia 新 source
   - `pc.getSenders().find(video).replaceTrack(newTrack)` 热切换
   - 更新 currentScreenId + 当前 display bounds（按 source.display_id 匹配 getAllDisplays）
   - 发 `{type:'activeScreen', id}` 回 viewer
6. 坐标换算（host handleInput mouseMove）：
   - 当前屏 display = getAllDisplays().find(d => d.id === currentSource.display_id)
   - physX = round((display.bounds.x + normX × display.bounds.width) × display.scaleFactor)
   - physY = round((display.bounds.y + normY × display.bounds.height) × display.scaleFactor)
   - nut-js setPosition(physX, physY)

## 机制改动

### openPage 支持 query
- sandbox.ts: `openPage: (pluginId, query?) => ipcRenderer.invoke('window:open-page', pluginId, query || '')`
- preload/index.ts: 同步签名
- main/ipc/index.ts `window:open-page` handler: 接 query，拼到 URL（`&mode=viewer&room=xxx`）
- host.ts/sandbox context.openPage: 透传 query

### 新 IPC: remote:get-all-displays
- 返回 `[{id, name, bounds:{x,y,width,height}, scaleFactor}]`
- host 用来按 source.display_id 匹配屏算坐标

### 新命令: syncHostState + getPageData 扩展
- Panel 调 `execute('syncHostState', {enabled, code, status, peerConnected})` 推状态
- index.ts 缓存 hostState；getPageData/getPanelData 返回 hostState
- Dashboard 读 getPageData.hostState 镜像

## 自动配对码

- Panel startHost 成功后自动 POST /pair 生成码并显示
- 定时在过期前（如 4 分钟）刷新重新生成
- stopHost 时清码
- hostState.code 同步给 Dashboard 镜像

## 文件清单

- 改: `desktop/plugins/remote/src/Panel.vue`（推状态 + 自动码 + 开管理页按钮）
- 改: `desktop/plugins/remote/src/Page.vue`（派发器）
- 改: `desktop/plugins/remote/src/webrtc.ts`（屏幕切换消息，可选 helper）
- 新: `desktop/plugins/remote/src/ManagementDashboard.vue`
- 新: `desktop/plugins/remote/src/ViewerSession.vue`
- 改: `desktop/src/main/plugin/sandbox.ts`（openPage query + remote:get-all-displays）
- 改: `desktop/src/preload/index.ts`（openPage 签名 + remote.get-all-displays）
- 改: `desktop/src/main/ipc/index.ts`（window:open-page query + remote:get-all-displays handler）
- 改: `desktop/plugins/remote/src/index.ts`（syncHostState 命令 + hostState + getPageData 扩展）

## 非目标

- 不改后端（信令/设备/配对 API 够用）
- 不做文件传输/剪贴板/音频
- host 确认弹窗逻辑保留（安全）

## 验收

1. Panel 独立开被控，配对码自动显示，Dashboard 能看到本机码
2. Dashboard 列出在线设备，点"控制"开独立 viewer 窗口看到画面并能操作
3. 多显示器：viewer 切换器切屏，画面切换，鼠标坐标在每屏都精确
4. 关 Dashboard 不影响 Panel 的 host
