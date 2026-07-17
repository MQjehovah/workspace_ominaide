# OmniAide 架构设计方案

日期: 2026-07-17
状态: 已确认

## 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 项目结构 | Monorepo | 统一管理，单一个人开发者 |
| 前端框架 | Vue 3 + Element Plus + Pinia | 开发效率高，组件库丰富 |
| 后端框架 | FastAPI + SQLAlchemy (async) | AI 生态集成好，异步高性能 |
| AI 策略 | 初期云端 API，后续迁移 Ollama | 快速启动 MVP，后期保证隐私 |
| 桌面客户端 | Electron | 成熟稳定，生态丰富 |
| 架构模式 | 领域模块化单体 (Modular Monolith) | 领域边界清晰，未来可拆微服务 |
| 向量数据库 | Qdrant | 轻量高性能，过滤能力强 |
| 消息队列 | Redis Streams + Celery | 事件流 + 异步任务一体化 |
| 对象存储 | MinIO | S3 兼容，私有化部署 |

## 目录结构

```
omniamon/
├── frontend/                  # Vue 3 + Vite + Element Plus
│   ├── src/
│   │   ├── views/             # 页面 Files/Todos/Music/Docs/Videos
│   │   ├── components/        # 通用组件
│   │   ├── stores/            # Pinia 状态管理
│   │   ├── api/               # API 请求层 (Axios)
│   │   └── router/            # Vue Router
│   └── Dockerfile
├── backend/
│   ├── core/                  # 共享基础设施
│   │   ├── auth/              # JWT 认证
│   │   ├── config/            # pydantic-settings 配置
│   │   ├── database/          # SQLAlchemy engine/session
│   │   └── minio/             # MinIO 客户端
│   ├── domains/
│   │   ├── file/              # 文件服务
│   │   ├── todo/              # 待办服务
│   │   ├── media/             # 歌单/音乐/文档/视频
│   │   ├── agent/             # AI Agent (核心)
│   │   ├── event/             # 事件采集处理
│   │   └── notification/      # 通知/主动提醒
│   ├── main.py                # FastAPI 入口
│   ├── celery_app.py          # Celery 应用
│   └── Dockerfile
├── desktop/                   # Electron 桌面客户端
├── browser-ext/               # Chrome 扩展 (MV3)
├── docker/
│   ├── docker-compose.yml     # 服务编排
│   ├── docker-compose.dev.yml # 开发覆盖配置
│   └── nginx/                 # Nginx 配置
├── docs/                      # 设计文档
├── scripts/                   # 开发/部署脚本
└── Makefile                   # 常用命令
```

## 后端 Domain 内部约定

```
domains/<name>/
├── __init__.py
├── router.py       # FastAPI router (endpoints)
├── schemas.py      # Pydantic 请求/响应模型
├── service.py      # 业务逻辑
├── models.py       # SQLAlchemy 模型
├── dependencies.py # 依赖注入
└── tests/
```

Domain 间通过 core 层注册的工具/接口通信，不直接 import 其他 domain。

## API 端点设计

```
POST   /api/v1/auth/login
POST   /api/v1/auth/register
POST   /api/v1/auth/refresh
GET    /api/v1/files                    # 列表(过滤/排序/分页)
POST   /api/v1/files/upload-url         # 预签名上传 URL
POST   /api/v1/files/confirm            # 确认上传
GET    /api/v1/files/{id}               # 详情
PUT    /api/v1/files/{id}/tags          # 更新标签
DELETE /api/v1/files/{id}               # 软删除
GET    /api/v1/todos                    # 列表
POST   /api/v1/todos                    # 创建(支持 raw_text)
PUT    /api/v1/todos/{id}               # 更新
DELETE /api/v1/todos/{id}               # 删除
POST   /api/v1/todos/{id}/remind        # 设置提醒
POST   /api/v1/agent/chat               # AI 对话(SSE)
WS     /ws/agent/chat                   # WebSocket 对话
POST   /api/v1/events/ingest            # 事件批量上传
GET    /api/v1/notifications            # 通知列表
POST   /api/v1/notifications/{id}/action# 通知操作
```

## 前端架构

路由: `/files`, `/todos`, `/music`, `/docs`, `/videos`, `/recommend`, `/memories`, `/settings`

布局: AppSidebar + AppHeader + router-view + GlobalAIChat + MusicPlayer

状态管理 (Pinia): auth, file, todo, player, notification, chat

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

### Phase 0 — 基础设施 (第 1-2 周)
- Docker Compose 编排 (MinIO/MySQL/Qdrant/Redis)
- 后端脚手架 (FastAPI + core: auth/config/db)
- 前端脚手架 (Vue 3 + Vite + Element Plus + Pinia)
- 用户认证 (登录/注册/JWT)

### Phase 1 — 文件 + 待办 (第 3-5 周, P0 核心)
- 文件 CRUD + 预签名 URL + MinIO 集成
- 待办 CRUD + 自然语言创建
- 前端文件管理页 + 待办看板

### Phase 2 — AI 对话 (第 6-8 周, P0 核心)
- AI Agent domain (LangChain)
- 意图识别 + 工具调用
- SSE 流式对话 + 前端对话面板
- LLM 配置 (云端 API)

### Phase 3 — 媒体模块 (第 9-12 周, P1)
- 音乐歌单 + 播放器
- 文档中心 + AI 摘要
- 视频库 + 流播放
- AI 推荐引擎

### Phase 4 — 事件采集 + 主动智能 (第 13-16 周, P2)
- 事件采集 API + Redis Streams
- Electron 桌面客户端
- Chrome 浏览器扩展
- 情境构建器 + 主动触发器
- 记忆地图可视化

### Phase 5+ — 持续迭代
- 多步任务规划 + 自动化规则引擎
- 移动端适配 / 语音交互
- 本地模型迁移 (Ollama)
- 性能优化 & 稳定性
