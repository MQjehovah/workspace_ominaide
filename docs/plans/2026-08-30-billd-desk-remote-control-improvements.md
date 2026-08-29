# 远控插件优化清单：billd-desk 借鉴 + 功能演进

日期：2026-08-30
状态：P0 + P1 已实现（2026-08-30）；P2/P3 待安排

> 关联：`desktop/plugins/remote/`（WebrtcAccept.vue host / ViewerSession.vue viewer / webrtc.ts）
> 参照：github.com/galaxy-s10/billd-desk（Vue3 + WebRTC 远控，开源版）

## 0. 已落地成果（勿重复）

- H.264 偏好 → 已回退（VP8 默认，软编更稳）；`preferCodec`/`applySenderParams` 工具保留
- 动态码率：`setParameters().maxBitrate`（billd-desk 手法）
- 三档自适应控制器（540p/720p/1080p）+ 滞回（升级 3 采样 / 降级 1 采样 / 10s 冷却）
- DataChannel `ordered:false, maxRetransmits:3`（低延迟 + 输入可恢复）
- `playoutDelayHint = 0.1`（接收端低抖动缓冲）
- `iceCandidatePoolSize:4` + `bundlePolicy:'max-bundle'`（建连提速）
- ICE 直连（移除 200ms 轮询 hack）
- 输入合流（鼠标 8ms 合流 / 滚轮 16ms）
- 采集原生分辨率（去 maxWidth/maxHeight 防裁切）+ 自动重采集兜底
- `contentHint:'detail'` + `degradationPreference:'maintain-resolution'`
- 首帧渲染（videoReady 遮罩）+ 规范 flex 排版 + normVideo 除零防护
- 诊断卡：网络状态（直连/中转 relay 判定）

---

## 1. P0：性能/流畅度（直接压卡顿）

### 1.1 画质切换改为 applyConstraints（不再重采）——【已实现】

**现状问题**：`setQuality → applyQualityChange` 走整条 `getUserMedia` 重采 + `replaceTrack`，每次画质切换都有一闪顿挫；档位切换频繁时尤其明显。

**方案**（billd-desk `handlConstraints`）：
```ts
track.applyConstraints({ height: { ideal: 720 }, frameRate: { ideal: 30 } })
```
在现有轨道上平滑改采集分辨率/帧率，无需重采。采集仍是原生源，applyConstraints 是等比缩放的 ideal 约束（不会裁切）。

- `WebrtcAccept.vue`：`applyQualityChange()` 改为对 `currentDataChannel` 收到 `setQuality` 时，对现有 video track 调 `applyConstraints`（并同步调 `applySenderParams` 的 maxFramerate）；删除重采分支
- 与档位自适应联动：tier 变化也走 applyConstraints（`height:{ideal:tierHeight}`），比改 `scaleResolutionDownBy` 更平滑
- 保留 `reinitCapture`（只用于首帧异常兜底，不再用于调质）

**涉及**：`WebrtcAccept.vue`；工作量：小

### 1.2 静态画面自动降帧（帧率模式）——【已实现】

**问题**：远控大部分时间是静态桌面，却持续按 30fps 编码，浪费带宽/CPU，弱网下反而引发拥塞卡顿。

**方案**（billd-desk Pro「帧率模式」低成本版）：
- host 记录最近输入活动：`lastInputAt`
- 自适应控制器内：`若 now - lastInputAt > 5s → maxFramerate = 6；否则 maxFramerate = 30`，随 `applySenderParams` 下发
- 输入一来（handleInput 里更新时间戳）立刻恢复满帧
- 额外加分：结合 `getStats` 帧字节变化判断画面是否真在动（可选 v2）

**涉及**：`WebrtcAccept.vue`（handleInput + startAdaptiveController）；工作量：小

### 1.3 videoFullBox 显式盒模型（可选）——【已实现·轻量版：resolution-* 属性 + ResizeObserver】

**现状**：`object-fit:contain` 已能正确 letterbox；可选替换为 billd-desk 的 `computeBox` 显式宽高像素 + `resize` 监听 + `resolution-*` 属性，normVideo 直接读属性免算 letterbox。属于加固项，非必需。

---

## 2. P1：功能改进（高价值）

### 2.1 剪贴板双向同步——【已实现】

**现状**：无。
**方案**：datachannel 新增 `clipboard` 消息（复用可靠 input 通道）。
- host→viewer：host 主进程轮询 `clipboard.readText()`（2s 去重）→ bridge → accept 窗口 → dc 发送；viewer 收到写本地剪贴板
- viewer→host：viewer 剪贴板变化（poll/文档剪贴板事件）→ dc → host 桥接 `clipboard.writeText`
- 注意只在会话内同步，避免循环（比对上次值）
**涉及**：host.ts/ipc（剪贴板桥接已有 `clipboard:writeText/readText`）、WebrtcAccept.vue、ViewerSession.vue、preload；工作量：中

### 2.2 快捷操作面板（特殊按键）——【已实现】

**现状**：viewer 屏蔽 F5/F11/F12，无系统级快捷键。
**方案**：viewer 工具栏加按钮，经 datachannel 发 `specialKey` 命令，host 用 nut-js 注入：
- 显示桌面 `Win+D`、任务管理器 `Ctrl+Shift+Esc`、锁定 `Win+L`、资源管理器 `Win+E`、`Ctrl+Alt+Del`（nut-js 尽力，winlogon 层可能需额外处理）、重启/注销（host 侧命令）
- 复用现有 `remote:inject` IPC + keyMap 扩展
**涉及**：ViewerSession.vue（工具栏）、WebrtcAccept.vue、ipc/index.ts keyMap；工作量：小-中

### 2.3 画质手动档位 + 自适应开关——【已实现】

**现状**：分辨率完全由 viewer 窗口尺寸 `determineQuality` 决定，用户不可控。
**方案**：viewer 加质量档位选择（自动/540p/720p/1080p + 帧率），覆盖时暂停自适应，发 `setQuality`；host 端自适应控制器尊重手动锁定。
**涉及**：ViewerSession.vue、WebrtcAccept.vue；工作量：中

### 2.4 分辨率同步——【已实现】

**现状**：仅初始 `determineQuality` + 手动自适应，窗口 resize 后不跟随。
**方案**：viewer 监听 `ResizeObserver`，窗口尺寸变化（防抖 500ms）重新 `setQuality`。
**涉及**：ViewerSession.vue；工作量：小

### 2.5 文件传输（datachannel 分片可靠通道）——【已实现】

**现状**：无。
**方案**：新建**可靠有序** datachannel（`createDataChannel('file', { ordered: true })`），与 input 不可靠通道分离：
- **分片**：每片 ~64KB，带序号 + 校验；利用 `bufferedAmount` / `bufferedamountlow` 做背压（Chrome 单通道缓冲约 16MB），避免一次塞爆
- **重组**：接收端按序号重组 + 哈希校验，完成后落盘
- **双向**：viewer→host（本机文件放到被控端）与 host→viewer（从被控端拉文件）均支持
- **UI**：传输进度条 + 取消
- **为何走 datachannel 而非后端**：P2P 直连时零中转、不占服务器带宽、延迟低；TURN 中转场景也只在 UDP 上传，不经过 MinIO/后端存储
- 文件选择/落盘用既有 file_picker / Electron 对话框桥
**涉及**：ViewerSession.vue、WebrtcAccept.vue（新增可靠通道 + 分片/重组/进度）、preload（文件读写）；工作量：中-大

---

## 3. P2：功能改进（中价值）

### 3.1 被控事件上报手机（复用 host channel）

**现状**：远控状态只在本机。
**方案**：复用我们刚建的通用 host channel 架构（`channel:"remote"`）：
- 被控开始/结束、配对码生成 → host 上报 → 后端 fanout → 手机通知（复用 `notify_user`/notifications channel）
- 手机也能查「本机是否正被控制」
**涉及**：backend（remote 注册 channel handler）、host.ts/backendChannel、remote 插件、手机端；工作量：中

### 3.2 被控端光标模式

**现状**：viewer 一直显示自己的鼠标。
**方案**：billd-desk 的「使用被控端鼠标」：host 隐藏本地光标（系统 API/注册表或截获），把被控光标位置随帧发 viewer 渲染 overlay；「智能鼠标」= 静止时跟随被控光标。工作量：中-大，体验细节多，可后置。

### 3.3 隐私屏

**现状**：无。
**方案**：被控开始时在 host 全屏盖一层自定义遮挡（图片/文字），结束自动移除；防被控端有人偷看。Electron 透明全屏窗 + 置顶。
**涉及**：WebrtcAccept.vue/host.ts；工作量：中

### 3.4 会话历史

**现状**：无记录。
**方案**：被控会话（时间、控制方、时长）写后端（可并入 remote 插件后端表），远端页面可查。工作量：小-中

---

## 4. P3：进阶（量大，按需）

- 屏幕墙/群控（多台 viewer 同看一台，或一控多）
- 系统音频回传（Electron 需 WASAPI loopback 原生模块，成本高）
- 虚拟屏（被控端虚拟显示器）
- 远控会话重连恢复（peer 重建保会话）

---

## 5. 备注

- 功能方向与 billd-desk 对齐，但**优先复用 OmniAide 既有能力**：host channel 通知体系、nut-js 注入桥、file_picker/对话框桥。文件传输特意走 datachannel 而非后端，以充分利用 P2P 直连、零服务器带宽。
- 每项实现时需回归验证：真机双端、弱网（可加 `--simulate-loss` 或用诊断卡观察丢包/帧率）。
