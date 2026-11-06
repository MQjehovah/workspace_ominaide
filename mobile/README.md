# OmniAide Mobile

Flutter 客户端，围绕 **AI 对话** 和 **工作台** 组织，所有插件与业务对象集中在「空间」。

## 导航

底部 4 个 tab，进入 App 默认落在「工作台」：

| Tab | 内容 |
|---|---|
| 对话 | 默认打开最新会话；标题处切换会话/新建；全屏聊天 |
| 工作台 | AI 输入、今日日程、信息摘要、幕僚长简报、文件与笔记 |
| 空间 | 统一收件箱 + 邮件/钉钉/通知/日程/待办/项目/幕僚长/文件/笔记/资讯/音乐/设备/实验室 |
| 我的 | 记忆审核、外观与主题、通知、设备、MCP、音乐、实验室、设置 |

文件与笔记不再占底部 tab：工作台有合并入口，空间里也有独立对象入口。

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

服务器地址在登录页填写，默认 `http://mqgeek.com:8000`。

## 验证

```bash
flutter analyze
flutter test
flutter build web --release
```

## 设计

- `docs/superpowers/specs/2026-11-06-mobile-redesign-design.md`
- `docs/superpowers/plans/2026-11-06-mobile-redesign.md`
