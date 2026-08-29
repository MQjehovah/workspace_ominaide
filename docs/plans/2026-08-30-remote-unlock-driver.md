# 远程解锁方案：Windows 锁屏/安全桌面输入注入（驱动方案）

日期：2026-08-30
状态：方案设计，暂未实现

> 关联：`desktop/plugins/remote/`（WebrtcAccept.vue / ViewerSession.vue）、`desktop/src/main/ipc/index.ts`（remote:* 桥接）、`docs/plans/2026-08-30-billd-desk-remote-control-improvements.md`
> 参照：github.com/oblitum/Interception（内核输入过滤驱动，C/C++，MIT）

## 1. 背景与问题

用户实测：被控机**锁屏（Win+L）时**，viewer 上点击鼠标左键 → 会话卡死；解锁后画面不自动恢复。

已确认的根因：
- **输入注入到不了锁屏/安全桌面**：nut-js 用 SendInput（用户态 Win32k 输入），而锁屏/UAC 的输入栈被系统保护，注入不可靠；在锁屏上点击还可能触发会话/显示切换，进一步卡死采集。
- **锁屏期间采集停摆**：DWM 暂停桌面合成，`getUserMedia chromeMediaSource:desktop` 无新帧 → 画面冻结，且部分 Windows 版本解锁后不自动恢复。
- 参考项目（billd-desk）：只处理 `powerMonitor suspend/resume`（`handleCloseAll` 整体拆除重连），**无任何锁屏处理**。

已落地（2026-08-30，非本方案）：
- `powerMonitor` lock-screen / unlock-screen 事件 + `getSystemIdleState` 初始查询（ipc + preload）
- host 锁屏时**丢弃全部输入注入**、解锁事件驱动自动重采、帧生产看门狗
- viewer 锁屏遮罩「🔒 被控端已锁定」
- 远控会话激活时 `powerSaveBlocker('prevent-display-sleep')` 防熄屏

## 2. 目标与约束

**目标**：用户能远程解锁被控机（含锁屏输入密码），且**用户感知最小**——安装程序时一次性完成驱动安装，此后无需任何手动操作。

**约束（物理下限）**：
- Windows 内核驱动**必须管理员安装**：安装时必经一次 UAC，这是系统安全策略的下限，无法绕过。
- x64 内核驱动**必须有效签名**：EV 证书 / WHQL / attestation 签名。
- 驱动与 Windows 版本兼容需要长期维护。
- 驱动安装失败**不得阻塞主程序安装**：必须提供无驱动降级路径。

## 3. 方案对比

| 方案 | 能否解锁 | 用户感知 | 工作量 | 备注 |
|---|---|---|---|---|
| A. 防锁屏 | 无需解锁 | 无 | 已落地 | powerSaveBlocker + 电源设置「从不睡眠/唤醒不登录」 |
| B. RDP 兜底 | 能（RDP 登录界面非安全桌面） | 需启用 RDP、账号 | 中 | 无驱动；`tscon` 接管被锁会话 |
| C. 驱动注入（Interception） | 能（含 UAC/安全桌面） | 安装时一次 UAC | 大 | 商业工具（ToDesk/TeamViewer）同款底层 |
| D. Win+L 盲输测试 | 可能无需驱动 | 无 | 小 | 前置实验，见 §4.1 |

## 4. 首选方案：C（驱动注入），D 为前置验证

### 4.1 前置实验（Phase 0，必做）

Win+L 锁屏与 UAC 安全桌面**不是一回事**：锁屏在**同一会话**（session 1），理论上 SendInput 够得着；UAC/Ctrl+Alt+Del 才是隔离的安全桌面。

实验：锁屏时，viewer 只发**鼠标移动 + 盲输「密码\n」**（焦点默认在密码框），观察能否解锁。
- 能 → Win+L 无需驱动；驱动仅保留给 UAC/Ctrl+Alt+Del 增强（低优先级）。
- 不能 → 驱动方案成立，进入 Phase 2。

### 4.2 架构

```
被控机：
[C++ helper (Interception 封装)]  ←stdin/命名管道←  Electron 主进程 (remote:inject-driver)
        │ interception_send(context, device, stroke)
        ▼
Interception 内核驱动 (interception.sys) → Win32k 输入栈 → LockUI / 安全桌面
```

- **C++ helper**：独立 exe（不依赖 Electron ABI），`interception_create_context()` 常驻，读 stdin 命令：
  `{"type":"key","code":..,"down":..}` / `{"type":"type","text":"密码"}` / `{"type":"move","x":..,"y":..}` / `{"type":"scroll","y":..}`
  用 `KEYBOARD_KEY_UP` 标志区分按下/抬起。
- **主进程接线**：检测 `screenLocked` → 输入注入走 helper；正常态走 nut-js。新增 IPC `remote:inject-driver`。
- **密码盲输流程**：锁屏弹出后焦点默认在密码框 → `type 密码` → `type \n`（Enter）。若锁屏布局变化导致焦点不在密码框，需先 `move+click` 定位（依赖锁屏可见性，见 §5 风险）。

### 4.3 安装分发（用户感知最小化）

- **打包**：electron-builder `extraResources` 打入签名版 `interception.sys` + `interception.dll` + `remote-input-helper.exe`。
- **安装**：NSIS 脚本在 elevated 环境静默执行：
  ```
  sc create interception type= kernel binPath= "...\interception.sys"
  sc start interception
  ```
- **卸载**：`sc stop interception` + `sc delete interception`。
- **降级容错**：驱动安装失败（无管理员/签名被拒/被杀软拦）→ 记录并继续安装主程序，远控保持无驱动模式（现状行为），不阻塞。
- **首次运行检测**：插件检测驱动服务是否存在；不存在则提示「远程解锁能力未启用」但正常可用。

### 4.4 签名（最大风险，须最先验证）

- 首选：Interception 官方**签名版驱动**，在目标 Windows（Win10/11 各版本）上实测能否加载。
- 若加载失败/证书吊销：走 **EV 证书** 或 **attestation 签名**（需要 Windows 开发者账号 + 流程）。
- 结论必须在 Phase 2 开始前确定，避免返工。

## 5. 风险清单

| 风险 | 影响 | 缓解 |
|---|---|---|
| 驱动签名失效/吊销 | 驱动无法加载 | 尽早实测；备选 EV/attestation |
| Windows 更新后驱动不兼容 | 解锁失效 | 驱动随主程序版本维护；检测服务状态 |
| 杀软误报内核驱动 | 装不上/被删 | 白名单说明；降级路径 |
| 锁屏布局/焦点变化 | 盲输失效 | 盲输失败 → 提示本机解锁；显示驱动增强（后续） |
| 多显示器/DPI 坐标错位 | 鼠标定位不准 | helper 注入用虚拟桌面坐标；沿用 display bounds 计算 |
| 驱动版本与宿主 CPU/架构 | 装不上 | x86/x64 双份；安装前架构检测 |

## 6. 分阶段实施计划

- **Phase 0**：Win+L 盲输实验（无驱动，30 秒）→ 决定是否上驱动。
- **Phase 1**：解锁流程接入（若实验成功：锁屏时定向注入 + 解锁自动恢复完善 + 密码框定位）。
- **Phase 2**：C++ helper 脚手架（Interception 封装 + CMake 构建 + Electron 接线 `remote:inject-driver`）。
- **Phase 3**：NSIS 驱动集成（打包/安装/卸载/降级/状态检测）。
- **Phase 4**：签名验证 + 真机验收（Win10/Win11、单/多显示器、UAC 路径）。

## 7. 验收标准

- [ ] 锁屏时 viewer 盲输密码可解锁（或经 UAC 路径）。
- [ ] 解锁后画面 1s 内自动恢复（复用现有 unlock 事件驱动重采）。
- [ ] 安装包单次 UAC，无手动驱动安装步骤；卸载干净。
- [ ] 驱动不可用时不阻塞主程序，远控降级为无驱动模式并明确提示。
- [ ] Phase 0 结论若为「无需驱动」：验收标准改为 Win+L 盲输解锁成功即可，UAC 场景标记为增强项。

## 8. 备注

- 驱动方案仅解决「输入到达锁屏」；**锁屏画面可见性**（能否看到密码框）仍需桌面采集支持，若 WGC/DDA 在锁屏不可用，盲输 + 默认焦点是唯一无需显示驱动的路径。
- 与 P1 已落地项的关系：本方案不影响现有防锁屏/看门狗/锁屏遮罩，是它们的**补充通道**（锁屏时注入从 nut-js 切到 helper）。
