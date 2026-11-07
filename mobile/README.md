# OmniAide Mobile

Flutter 客户端，围绕 **AI 对话** 和 **工作台** 组织，所有插件与业务对象集中在「空间」。

## 导航

底部 4 个 tab，进入 App 默认落在「工作台」：

| Tab | 内容 |
|---|---|
| 对话 | 默认打开最新会话；标题处切换会话/新建；全屏聊天 |
| 工作台 | AI 输入、今日日程、信息摘要、今日简报、文件与笔记 |
| 空间 | 收件箱 + 邮件/钉钉/通知/日程/待办/项目/回顾/自动化/文件/笔记/资讯/音乐/设备/实验室 |
| 我的 | AI 角色、记忆审核、外观与主题、通知、设备、MCP、实验室、设置 |

文件与笔记不再占底部 tab：工作台有合并入口，空间里也有独立对象入口。

## 对话与收件箱

- 对话默认打开最近会话，标题处可切换会话或新建。
- 流式输出按 50ms 节流，支持 Markdown、停止生成、复制回复、重新生成、加载更早消息。
- 支持语音输入（系统语音识别），识别结果进入输入框，可编辑后再发送。
- 长按消息可复制、编辑并重发；会话支持重命名、删除和快速切换。
- 流式生成时自动跟随到底部；向上翻看时停止跟随，并出现回到底部按钮。
- 收件箱可回复钉钉消息；通知支持单条已读和稍后提醒。
- 空间支持隐藏低频入口（右上角「管理」），设置保存在本机。
- 笔记支持 Markdown 预览/编辑；兼容旧的 ProseMirror JSON，并统一以 Markdown 保存。
- 文件夹可折叠/展开，点击文件夹不会进入编辑器。

## 外观

- 默认主题：晴空蓝 `#2E7CF6`。
- 预设：晴空蓝 / 薄荷绿 / 暖阳橙 / 樱花粉 + 自定义色相。
- 背景 tint 可开关；深浅模式跟随系统或手动选择；字号 0.9–1.3。
- 设置保存在 `SharedPreferences`，并 best-effort 同步到 `/api/sync/settings/appearance/*`。

## 运行

```bash
flutter pub get
flutter run -d chrome   # 或 Android / iOS 设备
```

服务器地址默认 `https://mqgeek.com/ominaide`，可在登录页右上角齿轮或「我的」→ 设置中修改（不再放在账号密码表单上方）。

## 验证

```bash
flutter analyze
flutter test
flutter build web --release
```

## 设计

- `docs/superpowers/specs/2026-11-06-mobile-redesign-design.md`
- `docs/superpowers/plans/2026-11-06-mobile-redesign.md`
