
# 个人AI助手平台——系统设计文档

文档版本	1.0
日期	2026-07-17
作者	个人开发者
对应PRD	个人AI助手平台 PRD v1.0

1. 引言
   1.1 设计目标
   本文档详细描述个人AI助手平台的系统架构、模块划分、接口协议、数据流转及部署方案。平台采用薄工具层 + 厚AI层架构，通过持续的事件采集与智能分析，实现主动式、情境感知的个人数字助手。

1.2 核心设计原则
隐私优先：敏感数据本地处理，云端仅存脱敏特征，端到端加密。

模块解耦：服务间通过API/消息队列异步通信，易于扩展。

弹性伸缩：初期单机部署，架构预留分布式扩展能力。

用户完全掌控：提供数据可视、遗忘机制、细粒度权限控制。

1.3 术语表
术语	说明
情境快照 (Context Snapshot)	每5分钟生成的用户当前活动、状态的自然语言摘要及其向量表示
用户画像 (User Profile)	存储在MySQL中的结构化兴趣、习惯等长期特征
语义记忆 (Semantic Memory)	存储在知识图谱中的事实性、关系性长期记忆
情景记忆 (Episodic Memory)	存储在向量库中的对话、事件片段，具时效性
2. 总体架构
2.1 架构全景图
text
┌─────────────────────────────────────────────────────────────────────┐
│                         客户端层                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │ Web 前端    │  │ 桌面客户端   │  │ 浏览器扩展  │                  │
│  │ (React)     │  │ (Electron)  │  │ (Chrome)    │                  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                  │
│         │                │                │                          │
│         │ HTTPS/WS       │ HTTPS/WS       │ HTTPS                    │
│         │                │                │                          │
└─────────┼────────────────┼────────────────┼──────────────────────────┘
          │                │                │
┌─────────▼────────────────▼────────────────▼──────────────────────────┐
│                       API 网关层 (Nginx / Traefik)                    │
└─────────┬────────────────┬────────────────┬──────────────────────────┘
          │                │                │
┌─────────▼────────────────▼────────────────▼──────────────────────────┐
│                       核心服务层 (FastAPI 服务组)                      │
│  ┌───────────┐ ┌───────────┐ ┌────────────┐ ┌──────────────────┐    │
│  │ 文件服务   │ │ 待办服务   │ │ 媒体服务    │ │ 事件接收服务      │    │
│  │ (File)    │ │ (Todo)    │ │ (Media)    │ │ (Event Ingestion)│    │
│  └─────┬─────┘ └─────┬─────┘ └─────┬──────┘ └────────┬─────────┘    │
│        │              │              │                 │               │
│  ┌─────▼──────────────▼──────────────▼─────────────────▼──────────┐  │
│  │                    AI Agent 服务 (厚 AI 核心)                   │  │
│  │  ┌────────────┐  ┌──────────────┐  ┌───────────────────────┐  │  │
│  │  │ 意图识别    │  │ 推荐引擎     │  │ 任务规划器             │  │  │
│  │  │ Intent     │  │ Recommend    │  │ Task Planner          │  │  │
│  │  └─────┬──────┘  └──────┬───────┘  └───────────┬───────────┘  │  │
│  │        │                │                      │               │  │
│  │  ┌─────▼────────────────▼──────────────────────▼───────────┐  │  │
│  │  │  情境构建器 Context Builder  │ 记忆管理器 Memory Mgr   │  │  │
│  │  │  模式挖掘器 Pattern Miner    │ 主动触发器 Proactive     │  │  │
│  │  └─────────────────────────────┴──────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────────┐
│                        数据与中间件层                                  │
│  ┌───────┐ ┌───────┐ ┌──────────┐ ┌───────┐ ┌────────┐ ┌─────────┐ │
│  │ MinIO │ │ MySQL │ │ Qdrant   │ │ Redis │ │ Neo4j  │ │ Celery  │ │
│  │       │ │ 8.0   │ │(向量库)  │ │       │ │(可选)  │ │ Workers │ │
│  └───────┘ └───────┘ └──────────┘ └───────┘ └────────┘ └─────────┘ │
└─────────────────────────────────────────────────────────────────────┘
2.2 物理部署视图
所有组件通过 Docker Compose 编排在同一主机（或集群）内网，通过服务名互相访问。客户端与服务端之间通过公网 HTTPS（Nginx 反向代理）连接，WebSocket 用于 AI 对话流式输出和实时通知推送。

3. 模块详细设计
   3.1 后端服务模块
   3.1.1 文件服务 (File Service)
   职责：管理文件元数据 CRUD，生成 MinIO 预签名 URL，处理上传完成回调，标签管理，文件搜索。

关键API：

POST /api/files/upload-url – 获取上传预签名 URL 和文件 ID。

GET /api/files/{id}/download-url – 获取下载预签名 URL。

GET /api/files – 文件列表查询（支持过滤、排序、分页、标签筛选）。

PUT /api/files/{id}/tags – 更新文件标签。

DELETE /api/files/{id} – 软删除，移入回收站。

内部逻辑：

上传流程：客户端请求上传 URL → 服务生成 object_key = user_{id}/{uuid}.ext，调用 MinIO SDK 生成预签名 PUT URL 返回 → 客户端直传 MinIO → 上传成功后回调 /api/files/confirm-upload，服务写入 MySQL files 表。

异步任务：上传确认后，根据文件类型发送任务到 Redis Queue（如文档摘要提取、音乐元数据解析、视频缩略图生成）。

3.1.2 待办服务 (Todo Service)
职责：待办事项 CRUD，自然语言解析创建，提醒管理。

关键API：

POST /api/todos – 创建待办，支持传入 raw_text 由 AI 解析时间/优先级。

GET /api/todos – 列表查询，支持状态/优先级/时间筛选。

PUT /api/todos/{id} – 更新待办（标题、状态等）。

DELETE /api/todos/{id} – 删除。

POST /api/todos/{id}/remind – 设置提醒。

AI 辅助：调用 Agent 服务的 /agent/parse-todo 解析自然语言，返回结构化数据。

3.1.3 媒体服务 (Media Service)
职责：歌单、视频、文档的特定业务逻辑。

歌单子服务：

POST /api/playlists – 创建歌单。

PUT /api/playlists/{id}/items – 添加/排序歌曲。

GET /api/playlists/{id} – 详情。

POST /api/playlists/{id}/ai-fill – AI 自动根据主题/心情填充歌曲。

文档/视频子服务：复用文件服务元数据，额外提供在线预览、AI 摘要接口（实际由 Agent 服务处理）。

3.1.4 事件接收服务 (Event Ingestion Service)
职责：接收客户端加密事件流，解密、初步校验、写入 Redis Streams。

接口：POST /api/events/ingest，body 为加密的事件 batch（protobuf/msgpack 压缩）。

流程：

收到密文，使用用户专属密钥解密。
验证数据格式，写入 Redis Stream user:{user_id}:events。
返回成功。
安全性：密钥在客户端生成，服务端通过用户密码派生密钥解密，绝不明文存储。

3.1.5 AI Agent 服务 (核心厚AI)
意图识别模块：

输入用户消息 + 当前上下文，输出工具调用链（Function Call）或直接回复。

使用 LangChain 的 Agent 框架，支持多步推理。

推荐引擎：

协同过滤（用户行为相似性）+ 内容推荐（向量相似度）+ 情境规则。

实现为定时任务或按需调用。

任务规划器：

对于复杂指令，分解为子任务并逐步执行，支持用户确认回调。

情境构建器：

监听 Redis Streams，每5分钟聚合最近事件，生成情境描述文本，向量化存入 Qdrant。

模式挖掘器：

日终批量处理：读取 MySQL user_events，使用规则+聚类发现频繁模式，写入知识图谱。

主动触发器：

结合规则引擎（如 Drools 或 Python 规则库）和情境快照，生成通知卡片推送到前端。

记忆管理器：

对话历史存入 Qdrant（短期），定期总结并抽取实体关系写入 Neo4j（长期）。

3.2 数据库设计
3.2.1 MySQL 表结构（关键表）
表名	字段概要	说明
users	id, username, password_hash, email, avatar_url, created_at	用户账户
files	id, user_id, bucket, object_key, original_name, size, mime_type, tags (JSON), is_favorite, status, created_at, updated_at	统一文件元数据，status: 'active', 'trash'
playlists	id, user_id, name, description, cover_file_id, created_at	歌单基本信息
playlist_items	playlist_id, file_id, sort_order, added_at	歌单-文件关联
todos	id, user_id, title, description, status, priority, due_date, reminder_at, related_file_ids (JSON), created_at, updated_at	待办事项
user_events	id, user_id, session_id, event_type, payload (JSON), recorded_at	聚合后的用户行为事件
user_profile	user_id, interests (JSON), work_pattern (JSON), response_style, updated_at	动态画像
automation_rules	id, user_id, name, trigger_event, conditions (JSON), actions (JSON), enabled	自动化规则
conversation_history	id, user_id, role, content, tokens, created_at	原始对话记录（可定期归档）
索引示例：

sql
-- files 表
INDEX idx_user_bucket_status (user_id, bucket, status);
-- 对 tags 使用虚拟列索引
ALTER TABLE files ADD COLUMN tags_search TEXT GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(tags, '$[*]'))) STORED;
CREATE INDEX idx_tags_fulltext ON files(tags_search);
-- user_events 表
INDEX idx_user_time (user_id, recorded_at);
INDEX idx_session (user_id, session_id);
3.2.2 向量数据库 (Qdrant)
集合设计：

集合名称	向量尺寸	用途	典型 Payload
file_embeddings	1024	文件内容的语义向量，用于语义搜索	{file_id, user_id, summary, tags}
conversation_memory	1024	近期对话片段	{user_id, role, text, timestamp, importance}
context_snapshots	1024	用户情境快照	{user_id, snapshot_text, timestamp, activity_tag}
user_interest_vectors	1024	用户兴趣的动态嵌入	{user_id, version, updated_at}
相似性搜索示例：

语义搜索文件：在 file_embeddings 中按 user_id 过滤，使用查询文本向量进行搜索，返回 top_k。

推荐：聚合用户最近交互的几个实体向量，在 file_embeddings 中搜索相似项，排除已交互的。

3.2.3 知识图谱 (Neo4j 可选，初期可用图结构表替代)
节点类型：User, File, Todo, Project, Tag, Interest, Habit。

关系类型：OWNS, RELATED_TO, HAS_INTEREST, FREQUENTLY_USES, REMINDED_OF。

应用场景：检索“我上次编辑的有关‘机器学习’的文档”，图谱查询可快速找到二阶关联。

3.3 对象存储 (MinIO)
Bucket 策略：

user-files：用户通用文件，如照片、压缩包。

music：音频文件。

videos：视频文件。

documents：文档类文件（PDF、Office、Markdown）。

thumbnails：自动生成的缩略图，生命周期7天自动删除。

backups：数据库备份文件。

权限控制：所有 bucket 设为 private，仅通过后端生成预签名 URL 访问，有效期可配置（上传10分钟，下载30分钟）。

文件组织：{bucket}/{user_id}/{uuid}.{ext}，唯一 ID 避免冲突。

3.4 API 设计（部分端点）
3.4.1 认证
所有 API 需在 Header 中携带 Authorization: Bearer <JWT></jwt>。

方法	路径	描述
POST	/auth/login	用户名密码登录，返回 JWT
POST	/auth/register	注册
POST	/auth/refresh	刷新令牌
3.4.2 AI 助手
方法	路径	描述
POST	/api/agent/chat	发送消息，返回 SSE 流式回复；支持上下文注入
WS	/ws/agent/chat	WebSocket 版本，双向通信，支持实时推送提醒
请求体示例：

json
{
  "message": "帮我找一下上个月的项目文档",
  "context": {
    "current_page": "files",
    "selected_file_ids": []
  },
  "conversation_id": "uuid"
}
响应流：

text
data: {"type": "thought", "content": "正在搜索上个月的文档..."}
data: {"type": "tool_call", "tool": "search_files", "args": {...}}
data: {"type": "result", "files": [...]}
data: {"type": "done"}
3.4.3 事件采集
方法	路径	描述
POST	/api/events/ingest	批量上传加密事件
请求体为 protobuf 序列化后的加密数据，减少传输体积。

3.4.4 主动服务
方法	路径	描述
GET	/api/notifications	获取未读通知列表
POST	/api/notifications/{id}/action	用户对通知卡片执行动作（确认、忽略）
3.5 事件采集客户端设计
3.5.1 桌面客户端 (Electron)
系统事件监听（主进程）：

Windows: SetWinEventHook 监听窗口切换、GetForegroundWindow。

macOS: NSWorkspace 通知。

Linux: 通过 X11 库或 dbus 获取活跃窗口。

输入监控（渲染进程）：

键盘事件统计：记录按键时间戳，计算 WPM、删除键频率，不记录具体字母。

鼠标活动：移动距离、点击热区（可选）。

文件监控：利用 chokidar 库监听用户指定目录的文件创建、修改事件。

数据缓冲：所有原始事件先写入本地 SQLite（加密），每 30 秒或 50 条事件批量加密上传。

隐私开关：系统托盘菜单提供“暂停采集”、“查看今日摘要”、“清除本地数据”选项。

3.5.2 浏览器扩展
使用 Chrome API：tabs.onUpdated, tabs.onActivated, idle.onStateChanged 获取 URL 变化和停留时间。

搜索行为：监听 Google/Bing 等搜索页面的 URL 参数，提取查询词（脱敏：仅保留长度、语言）。

与桌面客户端通过 Native Messaging 通信，统一上传。

3.5.3 数据加密方案
客户端生成 AES-256 密钥，并用服务端 RSA 公钥加密该密钥，密文在首次连接时发送给后端。

后续事件均使用 AES-GCM 加密，保证完整性。

服务端使用对应私钥解密出 AES 密钥，进行事件解密。

3.6 前端组件设计
基于 React + Ant Design，主要页面和组件：

路由结构：

/ 重定向到 /files

/files – 文件管理

/music – 歌单

/docs – 文档中心

/videos – 视频库

/todos – 待办事项

/recommend – 智能推荐

/memories – 记忆地图

/settings – 设置（包括事件采集控制）

核心组件：

GlobalAIChat：悬浮按钮和对话面板，使用 WebSocket 流式显示，支持 Markdown 渲染和交互卡片。

FileManager：包含 FolderTree, FileGrid, FilePreview，集成上传拖拽。

MusicPlayer：底部迷你播放器，全局状态管理（Redux/Zustand）。

TodoBoard：看板组件，可拖拽，集成快速创建框（支持自然语言）。

NotificationCenter：铃铛图标下拉，展示主动推送卡片。

MemoryGraph：使用 vis.js 或 d3 绘制知识图谱，支持交互。

状态管理：采用 Zustand 或 Redux Toolkit，集中管理用户信息、播放器状态、通知、当前情境感知数据。

4. 关键数据流设计
   4.1 用户上传文件并自动生成摘要
   用户点击上传，前端请求 /api/files/upload-url。

文件服务生成预签名 URL，返回给前端，同时创建一个 status=uploading 的记录。

前端直传 MinIO。

上传完成，前端调用 /api/files/confirm-upload。

文件服务更新状态为 active，发送任务 {type: "file.process", file_id: 123} 到 Redis Queue。

Celery Worker 消费任务：下载文件 → 提取文本（Apache Tika）→ 调用本地 Embedding 服务生成向量 → 存入 Qdrant file_embeddings 集合。

同时，AI Agent 中的文档摘要工具被调用，生成摘要写入 MySQL 或直接存为文件属性。

4.2 主动休息提醒
事件采集客户端每30秒发送一批事件，包含窗口切换、键入统计。

事件接收服务解密后写入 Redis Stream。

情境构建器消费者实时读取，聚合数据，每5分钟生成情境快照：“用户连续使用 IDE 50 分钟，键入速度下降15%”。

快照向量化后存入 Qdrant context_snapshots，原始描述发给主动触发器。

主动触发器规则 IF focus_time > 45min AND fatigue_indicator > 0.2 THEN suggest_break 被触发。

触发器调用通知服务，生成一条通知记录，并通过 WebSocket 推送到前端。

前端通知中心弹出卡片：“你已连续工作45分钟，需要休息一下吗？[休息一下] [继续工作]”

用户点击“休息一下”，触发自动化：暂停待办提醒，播放放松音乐，进入休息状态。

4.3 自然语言创建待办并关联文件
用户在文档页面对话框输入：“帮我创建一个下周三前完成的待办，关联这个文档”。

前端将消息 + 当前上下文（current_page: docs, selected_file: {id: 456}）发送至 /api/agent/chat。

Agent 意图识别模块解析出 add_todo(title='...', due_date='2026-07-23', related_file_ids=[456])。

Agent 调用待办服务的 /api/todos，传入参数。

待办服务创建成功，返回结果。

Agent 将回复通过 SSE 流返回给前端：“已创建待办：XXX，关联了当前文档”。

前端待办列表自动刷新。

5. 技术选型与理由
   组件	技术	说明
   后端框架	Python FastAPI	异步性能优异，生态丰富，与 AI/ML 库无缝集成
   ORM	SQLAlchemy 2.0 (async)	支持异步，成熟稳定
   AI 编排	LangChain + LangGraph	提供 Agent、Chain、记忆、工具调用抽象，支持本地模型
   LLM	Ollama (Llama 3 8B)	本地运行，数据不出域；也可用 OpenAI 作为备选
   嵌入模型	BGE-M3 (BAAI)	多语言，性能好，本地部署
   向量数据库	Qdrant	Rust编写，性能高，过滤强，资源占用低
   消息队列	Redis Streams + Celery	事件流处理和异步任务
   对象存储	MinIO	S3 兼容，可私有部署
   关系数据库	MySQL 8.0	成熟，支持 JSON 和全文索引
   图数据库	Neo4j Community (可选初期可用MySQL图结构表)	用于语义记忆
   前端	React 18 + Ant Design 5 + Zustand	组件丰富，状态管理轻量
   桌面客户端	Electron + React (或 Tauri)	跨平台，可使用前端技术栈
   浏览器扩展	Chrome Extension Manifest V3	标准 WebExtension
   部署	Docker Compose	一键部署，隔离环境
6. 部署方案
   6.1 Docker Compose 服务编排
   所有服务定义在一个 docker-compose.yml 中，主要服务包括：

minio : 对象存储，暴露9000(API)/9001(控制台)

mysql : 数据库，挂载数据卷

qdrant : 向量数据库，暴露6333

redis : 缓存和消息队列

neo4j : 可选，图数据库

backend : FastAPI 应用，依赖上述服务，通过环境变量配置连接信息

celery_worker : 异步任务工作者，可扩展

frontend : Nginx 静态服务器或 Node 开发服务器

nginx : 反向代理，配置 SSL，将 API 和前端流量路由到内部服务

6.2 环境变量示例（后端）
text
DATABASE_URL=mysql+aiomysql://user:pass@mysql:3306/personal_ai
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=xxx
MINIO_SECRET_KEY=xxx
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379
OLLAMA_BASE_URL=http://ollama:11434
JWT_SECRET=your-secret
ENCRYPTION_PRIVATE_KEY_PATH=/run/secrets/private_key.pem
6.3 硬件建议（单机）
CPU: 8 核以上（若运行本地 LLM 则推荐 16 核）

内存: 32 GB（本地 Llama 8B 约需 16GB）

磁盘: SSD 500GB 以上

可配置 GPU（如 RTX 3060 12GB）加速推理

7. 安全设计
   传输安全：所有对外服务通过 Nginx 提供 HTTPS，内部服务通过 Docker 网络隔离。

认证授权：JWT + refresh token 机制，API 级别鉴权，敏感操作二次确认。

数据加密：MinIO 服务端加密（SSE-S3），事件采集端到端加密，数据库敏感字段（如密码）哈希加盐存储。

依赖安全：定期更新基础镜像，使用 Trivy 扫描漏洞。

隐私控制：用户可查看所有被采集的数据，并提供一键删除功能；前端提供数据导出（GDPR 风格）。

密钥管理：使用 Docker secrets 或环境变量文件（受限制访问），不将密钥提交到代码仓库。

8. 附录
   8.1 事件 Payload 示例（解密后）
   json
   {
   "events": [
   {
   "type": "app_switch",
   "timestamp": 1621234567890,
   "app_name": "VS Code",
   "window_title_hash": "sha256:abc...",
   "duration_sec": 120
   },
   {
   "type": "input_stats",
   "timestamp": 1621234688000,
   "wpm": 35,
   "delete_ratio": 0.1,
   "activity_level": "high"
   }
   ]
   }
   8.2 情境快照示例
   json
   {
   "user_id": 1,
   "snapshot": "用户正在使用VS Code编辑Python文件，窗口标题包含'personal_ai_backend'，已连续工作55分钟，输入速度下降至20 WPM，可能有疲劳迹象。",
   "vector": [0.12, -0.34, ...],
   "timestamp": "2026-07-17T14:30:00Z",
   "tags": ["coding", "high_focus", "fatigue_risk"]
   }
