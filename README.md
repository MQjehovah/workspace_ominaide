# OmniAide

> Your Omni-present Aide.

一个完全私有化部署的个人 AI 助手平台。融合全栈存储、事务管理与 AI 智能体，能感知你的情境，预判你的意图，并主动为你打点数字生活。你的文件、音乐、笔记、日程、资讯，以及每一天的行为足迹，都在这座由你完全掌控的私有服务器上，由一个懂你的 AI 管家打理。

## 核心能力

📁 **文件管理** — MinIO 对象存储，统一上传/预览/搜索，支持音视频在线播放

🎵 **智能播放器** — 桌面端音乐播放器，云端歌单管理

📝 **笔记系统 + 知识库 RAG** — 富文本 / Markdown 编辑器，保存即分块索引；向量 + BM25 混合检索、带引用来源的笔记问答（`/api/plugins/notes/rag/*`）

📅 **日程管理** — 日历视图，创建/编辑/提醒，自然语言创建

📡 **资讯源** — RSS/Atom、GitHub Trending（RSSHub），来源管理、内容列表 + 阅读视图、全文搜索

👁️ **桌面远程控制** — WebRTC 屏幕共享 + 鼠标键盘注入 + 多屏切换

🤖 **AI 助理** — 桌面端全局热键 `Ctrl+Shift+A` 呼出浮动对话窗，语音输入，自然语言操作（打开页面、搜索、创建日程）；Web 端内置右下角浮动 AI 助理，均可通过 MCP function calling 调用所有后端 API（含自然语言创建日程）。设备端支持 ESP-SR 唤醒词 “Hi ESP”、流式语音与播报打断

🔍 **统一语义搜索** — 顶部全局搜索框，一条接口检索文件/笔记/资讯/日程，语义 + 关键词双通道，支持 Qdrant 向量检索

💬 **AI 对话历史** — 聊天记录持久化到 MySQL，Web / 桌面 / 移动端共享上下文

🔔 **通知中心** — WebSocket 实时推送，未读计数 + 下拉列表，日程提醒（到点自动推送）；硬件设备通过 `/api/device/events` 长轮询秒级接收

🔐 **完全自托管** — 所有组件通过 Docker Compose 运行在你的机器上，数据主权不妥协

## 智能架构

```
┌─────────────────────────────────────────────┐
│              智能层                          │
│  规律发现 · 主动简报 · 主动安排             │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│              记忆层                          │
│  个人画像 · 活动日志 · 实体图谱             │
│  让 AI「认识你」                            │
└──────────────────┬──────────────────────────┘
                   │ 全部向量化
┌──────────────────▼──────────────────────────┐
│              数据层                          │
│  统一索引 → pgvector → 统一语义搜索         │
│  文件/笔记/资讯/日程/活动，一个接口查全部    │
└─────────────────────────────────────────────┘
```

## 架构

```
┌─────────────┐  ┌──────────────┐  ┌───────────────┐
│  Web 前端    │  │ 桌面客户端    │  │ 手机端        │
│  (Vue 3)     │  │ (Electron)   │  │ (Flutter)     │
└──────┬───────┘  └──────┬───────┘  └──────┬────────┘
       │                 │                  │
       └─────────────────┼──────────────────┘
                         │ HTTPS + WebSocket
                  ┌──────▼──────────────────┐
                  │   FastAPI 后端            │
                  │   · 13 个业务插件         │
                  │   · MCP 工具注册中心      │
                  │   · WebSocket 通知        │
                  └──────┬──────────────────┘
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
    ▼                    ▼                    ▼
┌────────┐    ┌──────────────┐    ┌─────────────────┐
│ MinIO  │    │ PostgreSQL   │    │ pgvector        │
│ 对象存储│    │  结构化数据   │    │ 语义搜索+记忆   │
└────────┘    └──────────────┘    └─────────────────┘
                         │
                  ┌──────▼──────────────────┐
                  │   AI 引擎               │
                  │  OpenAI / DeepSeek      │
                  │  MCP Function Calling   │
                  └─────────────────────────┘
```

## 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Element Plus + Pinia |
| 桌面端 | Electron + Vue 3 + Vite |
| 移动端 | Flutter |
| 后端 | Python FastAPI + SQLAlchemy |
| AI API | OpenAI / DeepSeek / 任意兼容接口 |
| 对象存储 | MinIO |
| 关系数据库 | PostgreSQL 16 |
| 向量检索 | pgvector |
| 部署 | Docker Compose |

## 桌面端插件

桌面端插件系统支持热加载，当前内置插件：

`player` `remote` `schedule` `sources` `assistant` `screenshot` `todo` `files` `notes` `calculator` `clipboard-history` `everything` `vibecoding-proxy` `activity` `translator` `sysmonitor` `pomodoro` `quicklinks`

> `quicklinks`（快捷指令）以手机式图标网格展示，点击即可一键打开软件 / 网页 / 文件夹，或运行脚本与命令；面板支持 `itemsLayout: 'grid'` 布局。

## 快速开始

> 前置要求：Docker & Docker Compose

```bash
# 克隆仓库
git clone https://github.com/yourname/OmniAide.git
cd OmniAide

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY（可选，AI 对话需要）
# 数据库默认使用 PostgreSQL 16 + pgvector

# 启动全部服务
docker compose -f docker/docker-compose.yml up -d

# 初始化数据库
docker compose -f docker/docker-compose.yml exec backend python manage.py init
```

启动后访问 `http://localhost:3000`（Web 管理界面）或用桌面端连接。

### 账号与注册

- 空库启动时，第一个注册账号会自动成为管理员
- 之后公开注册默认关闭，由管理员在「用户管理」中创建账号
- 如需临时开放注册，设置 `ALLOW_REGISTRATION=true`
- Web 和移动端会使用 refresh token 自动续期，不需要每 30 分钟重新登录

### 插件清单

后端插件使用统一的 `backend/plugins/<id>/manifest.json`：

```json
{
  "id": "files",
  "version": "1.0.0",
  "title": "文件",
  "description": "文件管理与网盘",
  "icon": "Folder",
  "permissions": [],
  "routes": { "main": "/files" },
  "tools": []
}
```

`id` 必须与插件目录名一致。后端会在启动时自动挂载插件导出的所有 `APIRouter`。

### 日志

```env
LOG_LEVEL=INFO
LOG_JSON=false
```

日志会带 `trace_id` 和 `user_id`，并自动脱敏 `token`、密码和 Bearer token。

## 桌面端开发

```bash
cd desktop
npm run dev
```

## 项目结构

```
├── backend/           # FastAPI 后端
│   ├── core/          # 核心模块（auth / mcp / ai / database / plugin）
│   ├── plugins/       # 后端业务插件
│   │   ├── chat/      # AI 对话
│   │   ├── files/     # 文件管理
│   │   ├── music/     # 歌单
│   │   ├── notes/     # 笔记
│   │   ├── sources/    # 资讯源（RSS / GitHub Trending）
│   │   ├── schedule/  # 日程
│   │   ├── sync/      # 同步
│   │   └── ...
│   └── desktop_plugins/ # 桌面端插件市场仓库
├── desktop/           # Electron 桌面端
│   ├── plugins/       # 内置桌面插件
│   │   ├── assistant/  # AI 助理
│   │   ├── remote/     # 远程控制
│   │   ├── player/     # 音乐播放器
│   │   ├── schedule/   # 日程
│   │   ├── sources/     # 资讯
│   │   └── ...
│   └── src/           # Electron 主进程 + 渲染进程
├── frontend/          # Web 管理后台（Vue 3）
├── mobile/            # Flutter 移动端
└── docker/            # Docker Compose 配置
```
