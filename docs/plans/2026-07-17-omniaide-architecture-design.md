# OmniAide 架构设计方案 (v2)

日期: 2026-07-17
状态: 已确认

## 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 项目结构 | Monorepo | 统一管理，单一个人开发者 |
| 前端框架 | Vue 3 + Element Plus + Pinia | 开发效率高，组件库丰富 |
| 后端框架 | FastAPI + SQLAlchemy (async) | AI 生态集成好，异步高性能 |
| AI 策略 | 初期云端 API，后续迁移 Ollama | 快速启动 MVP，后期保证隐私 |
| 桌面客户端 | Electron | 成熟稳定，文件同步 + 事件采集 |
| 架构模式 | 核心平台 + 插件生态 | 核心提供文件/工作空间/同步/AI，功能为可安装插件 |
| 插件风格 | Nextcloud 式嵌入 | 插件共享核心的用户/数据库/服务，独立路由和前端 |
| 向量数据库 | Qdrant | 轻量高性能，过滤能力强 |
| 消息队列 | Redis Streams + Celery | 事件流 + 异步任务一体化 |
| 对象存储 | MinIO | S3 兼容，私有化部署 |

## 架构总览

```
┌──────────────────────────────────────────────────────────┐
│                     核心平台 (Core)                        │
│  ┌──────┐ ┌──────┐ ┌──────────┐ ┌──────────────────┐    │
│  │ 认证  │ │ 文件  │ │ 工作空间  │ │  插件注册表       │    │
│  │ Auth │ │ File │ │Workspace │ │ Plugin Registry  │    │
│  └──────┘ └──┬───┘ └────┬─────┘ └────────┬─────────┘    │
│  ┌───────────▼───────────▼────────────────▼───────────┐  │
│  │          AI 引擎 (语义搜索/推荐/工具调用)            │  │
│  └────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │            同步引擎 (Sync Engine)                   │  │
│  │  文件变更检测 / 增量同步 / 冲突解决                  │  │
│  └──────────────────────┬─────────────────────────────┘  │
└─────────────────────────┼────────────────────────────────┘
                          │
    ┌─────────────────────┼─────────────────────┐
    │                     │                     │
    ▼                     ▼                     ▼
┌──────────┐       ┌──────────┐         ┌──────────┐
│ 待办插件  │       │ 歌单插件  │         │ 文档插件  │   ← 可安装/卸载
│ Todo App │       │ Music App│         │ Docs App │
└──────────┘       └──────────┘         └──────────┘

                          │ 双向同步 (WebSocket + Watcher)
                          ▼
               ┌─────────────────────┐
               │ 桌面客户端 (Electron) │
               │ 文件同步 + 事件采集   │
               │ 本地文件夹 ↔ 工作空间  │
               └─────────────────────┘
```

## 目录结构

```
backend/
├── core/                          # 核心基础设施
│   ├── auth/                      # JWT 认证
│   ├── config/                    # pydantic-settings 配置
│   ├── database/                  # SQLAlchemy engine/session
│   ├── minio/                     # MinIO 客户端
│   └── plugin/                    # 插件注册与加载引擎
├── domains/                       # 核心业务域
│   ├── file/                      # 文件管理 (核心)
│   ├── workspace/                 # 工作空间管理 (核心)
│   ├── sync/                      # 同步引擎 (核心)
│   ├── agent/                     # AI 引擎 (核心能力)
│   └── notification/              # 通知 (核心)
├── plugins/                       # 已安装的插件 (每个为独立包)
│   └── .gitkeep
├── main.py
├── celery_app.py
└── Dockerfile

frontend/
├── src/
│   ├── core/                      # 核心框架
│   │   ├── layout/                # Shell 布局 (侧边栏/顶栏)
│   │   ├── plugin-host/           # 插件容器
│   │   └── ai-chat/               # AI 对话 (核心功能)
│   ├── views/                     # 核心页面 (文件/工作空间/设置)
│   ├── stores/                    # Pinia 状态管理
│   ├── api/                       # API 请求层
│   └── router/                    # 路由 (核心路由 + 插件动态注册)
└── Dockerfile
```

## 插件系统设计

### 插件目录结构

```
plugins/todo/
├── manifest.json          # 插件元数据
├── backend/
│   ├── __init__.py
│   ├── router.py          # 自动注册到 /api/plugins/todo/
│   ├── models.py          # SQLAlchemy 模型 (表前缀 plugin_todo_)
│   ├── schemas.py
│   └── service.py
└── frontend/
    ├── views/             # Vue 页面
    ├── components/        # Vue 组件
    └── index.js           # 前端入口 (路由/菜单注册)
```

### manifest.json 规范

```json
{
  "name": "todo",
  "version": "1.0.0",
  "title": "待办事项",
  "description": "看板式待办管理",
  "icon": "Check",
  "permissions": ["files.read"],
  "routes": {
    "main": "/apps/todo",
    "settings": "/apps/todo/settings"
  }
}
```

### 插件生命周期

1. **安装**: 上传插件 zip → 解压至 `plugins/<name>/` → 执行数据库迁移 → 注册路由和菜单
2. **激活/停用**: 更新 `plugin_registry` 表状态，动态加载/卸载路由
3. **卸载**: 移除路由和菜单 → 删除数据表 (可选) → 删除插件目录

### 核心 API

```
# 插件管理
POST   /api/v1/plugins/install           # 安装插件 (上传 zip)
POST   /api/v1/plugins/{name}/toggle     # 启用/停用
DELETE /api/v1/plugins/{name}            # 卸载
GET    /api/v1/plugins                   # 已安装插件列表

# 核心业务
POST   /api/v1/auth/login
POST   /api/v1/auth/register
GET    /api/v1/files                     # 文件列表
POST   /api/v1/files/upload-url          # 预签名上传 URL
POST   /api/v1/files/confirm             # 确认上传
DELETE /api/v1/files/{id}                # 软删除
GET    /api/v1/workspaces                # 工作空间列表
POST   /api/v1/workspaces                # 创建工作空间
GET    /api/v1/workspaces/{id}/sync      # 同步状态
POST   /api/v1/workspaces/{id}/sync      # 触发同步
POST   /api/v1/agent/chat                # AI 对话 (SSE)
WS     /ws/agent/chat                    # WebSocket 对话

# 插件路由自动注册到
/api/plugins/{plugin_name}/...
```

## 同步引擎设计

同步引擎负责服务端工作空间 ↔ 桌面本地文件夹的双向文件同步。

### 核心机制

1. **服务端**: Linux `inotify` / Windows `ReadDirectoryChanges` 监听文件变更
2. **客户端 (Electron)**: `chokidar` 监听本地文件夹变更
3. **通信**: WebSocket 长连接，推送文件变更事件
4. **冲突解决**: 最后写入者胜出 (LWW) + 冲突文件备份

### 同步数据流

```
本地文件变更
  → chokidar 检测到 change/rename/unlink
  → Electron 客户端通过 WebSocket 发送 sync event
  → 服务端 Sync Engine 接收
  → 写入事件到 Redis Stream
  → Celery Worker 消费: 读取文件 → 存入 MinIO → 更新 DB
  → 通知其他客户端 (如有) 拉取更新

服务端文件变更 (网页上传/其他客户端)
  → Sync Engine 检测变更
  → 通过 WebSocket 推送到关联的桌面客户端
  → 客户端下载文件到本地工作空间目录
```

## 前端架构

### 核心布局

```
App.vue
├── CoreSidebar.vue          ← 左侧导航 (核心菜单 + 插件菜单动态注册)
├── CoreHeader.vue            ← 顶部栏 + 全局搜索 + 通知
├── <router-view />          ← 核心页面 / 插件页面
├── GlobalAIChat.vue          ← AI 对话浮窗
└── SyncStatusBar.vue         ← 同步状态指示条
```

### 路由结构

```
/                          → 仪表盘
/files                     → 文件管理 (核心)
/workspaces                → 工作空间管理 (核心)
/settings                  → 系统设置
/apps/todo                 → 待办插件 (由插件动态注册)
/apps/music                → 歌单插件
/apps/docs                 → 文档插件
```

### 状态管理 (Pinia)

```
stores/
├── core/
│   ├── auth.ts             # 认证
│   ├── file.ts             # 文件
│   ├── workspace.ts        # 工作空间
│   ├── sync.ts             # 同步状态
│   └── notification.ts     # 通知
├── plugins/                # 插件自己的 store (动态加载)
```

## Docker 服务编排

- minio (9000/9001)
- mysql:8.0 (3306)
- qdrant (6333)
- redis (6379)
- backend (FastAPI + uvicorn)
- celery_worker
- frontend (Nginx)
- nginx (反向代理 + HTTPS)

## 实施路线图

### Phase 0 — 基础设施 ✅ (已完成)
- Docker Compose 编排
- 后端脚手架 + 核心模块
- 前端脚手架 (Vue 3)
- 用户认证

### Phase 1 — 核心平台 (网盘 + 工作空间)
- 文件管理完整 CRUD + MinIO 预签名直传
- 工作空间 CRUD (创建/删除/文件浏览)
- 插件架构基础 (plugin registry, manifest 加载, 动态路由注册)
- 重构前端为核心布局 + 插件容器
- Web 端文件管理界面

### Phase 2 — 桌面同步客户端
- Electron 桌面客户端 (文件同步)
- 双向同步引擎 (chokidar + WebSocket)
- 工作空间 ↔ 本地文件夹绑定
- 冲突处理 & 同步状态 UI
- 安装/卸载向导

### Phase 3 — AI 引擎
- AI Agent domain (LangChain)
- 语义文件搜索 (Qdrant)
- SSE 流式对话
- AI 对话面板 (核心 UI)
- 工具调用 (文件操作等)

### Phase 4 — 插件生态 + 示例应用
- 插件安装/卸载/管理 UI
- 待办插件 (作为参考示例)
- 插件开发文档
- 插件市场 (可选)

### Phase 5 — 扩展应用
- 歌单/音乐插件
- 文档中心插件
- 视频库插件
- 事件采集插件
- 主动智能插件
