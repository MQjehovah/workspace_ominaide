# OmniAide

> Your Omni-present Aide.

一个完全私有化部署的个人 AI 助手平台。融合全栈存储、事务管理与 AI 智能体，能感知你的情境，预判你的意图，并主动为你打点数字生活。你的文件、音乐、笔记、日程、RSS，以及每一天的行为足迹，都在这座由你完全掌控的私有服务器上，由一个懂你的 AI 管家打理。

## 核心能力

📁 **文件管理** — MinIO 对象存储，统一上传/预览/搜索，支持音视频在线播放

🎵 **智能播放器** — 桌面端音乐播放器，云端歌单管理

📝 **笔记系统** — 富文本 / Markdown 编辑器，支持图片、表格

📅 **日程管理** — 日历视图，创建/编辑/提醒，自然语言创建

📡 **RSS 订阅** — 订阅源管理，文章列表 + 阅读视图，全文搜索

👁️ **桌面远程控制** — WebRTC 屏幕共享 + 鼠标键盘注入 + 多屏切换

🤖 **AI 助理** — 全局热键 `Ctrl+Shift+A` 呼出浮动对话窗，语音输入，自然语言操作（打开页面、搜索、创建日程），支持后端代理 / 前端直连双模式，MCP function calling 可调用所有后端 API

🔔 **通知中心** — WebSocket 实时推送，未读计数 + 下拉列表

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
│  统一索引 → Qdrant → 统一语义搜索           │
│  文件/笔记/RSS/日程/活动，一个接口查全部    │
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
                  │   · 13+ 业务插件          │
                  │   · MCP 工具注册中心      │
                  │   · WebSocket 通知        │
                  └──────┬──────────────────┘
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
    ▼                    ▼                    ▼
┌────────┐    ┌──────────────┐    ┌─────────────────┐
│ MinIO  │    │  MySQL 8.0   │    │ Qdrant 向量库    │
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
| 关系数据库 | MySQL 8.0 |
| 向量数据库 | Qdrant |
| 部署 | Docker Compose |

## 桌面端插件

桌面端插件系统支持热加载，当前内置插件：

`player` `remote` `schedule` `rss` `notifications` `assistant` `screenshot` `todo` `files` `notes` `calculator` `clipboard-history` `quick-notes`

## 快速开始

> 前置要求：Docker & Docker Compose

```bash
# 克隆仓库
git clone https://github.com/yourname/OmniAide.git
cd OmniAide

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY（可选，AI 对话需要）

# 启动全部服务
docker compose up -d

# 初始化数据库 & 创建管理员用户
docker compose exec backend python manage.py init
```

启动后访问 `http://localhost:3000`（Web 管理界面）或用桌面端连接。

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
│   │   ├── rss/       # RSS 订阅
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
│   │   ├── rss/        # 资讯
│   │   └── ...
│   └── src/           # Electron 主进程 + 渲染进程
├── frontend/          # Web 管理后台（Vue 3）
├── mobile/            # Flutter 移动端
└── docker/            # Docker Compose 配置
```
