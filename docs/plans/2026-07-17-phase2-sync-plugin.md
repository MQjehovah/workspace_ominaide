# OmniAide Phase 2 — 桌面同步客户端 + 示例插件

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现桌面端双向文件同步（Dropbox 风格）+ 开发一个待办插件验证插件架构

**Architecture:**
- 同步引擎：服务端 WebSocket + Redis Streams + Celery Worker 处理文件变更事件
- 桌面客户端：Electron + chokidar 监听本地文件变更，WebSocket 与服务端通信
- 示例插件：Nextcloud 风格嵌入，完整的前端+后端，可安装到核心平台

---

### Task 1: 后端同步引擎

**目标:** 实现工作空间文件变更的 WebSocket 通知、同步事件管理

**Files:**
- 创建: `backend/domains/sync/__init__.py`
- 创建: `backend/domains/sync/models.py` — SyncEvent 表
- 创建: `backend/domains/sync/schemas.py`
- 创建: `backend/domains/sync/service.py` — 事件发布/查询
- 创建: `backend/domains/sync/websocket.py` — WebSocket 连接管理
- 创建: `backend/domains/sync/router.py`
- 修改: `backend/main.py`

**Step 1: SyncEvent Model**

```python
class SyncEvent(Base):
    __tablename__ = "sync_events"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    event_type = Column(String(20))       # create, modify, delete, rename
    file_id = Column(Integer, ForeignKey("files.id"), nullable=True)
    file_path = Column(String(500))        # relative path in workspace
    file_size = Column(BigInteger)
    checksum = Column(String(64))          # sha256 for conflict detection
    status = Column(String(20), default="pending")  # pending, synced, conflicted
    created_at = Column(DateTime, server_default=func.now())
```

**Step 2: WebSocket Manager**

```python
# websocket.py
# 管理每个用户/工作空间的 WebSocket 连接
# 用于服务端 → 客户端推送文件变更通知

class ConnectionManager:
    """活跃 WebSocket 连接管理"""
    
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}  # ws_{user_id}_{workspace_id} -> [ws]
    
    async def connect(self, ws: WebSocket, user_id: int, workspace_id: int):
        await ws.accept()
        key = f"{user_id}_{workspace_id}"
        if key not in self.active:
            self.active[key] = []
        self.active[key].append(ws)
    
    async def disconnect(self, ws: WebSocket, user_id: int, workspace_id: int):
        key = f"{user_id}_{workspace_id}"
        if key in self.active:
            self.active[key].remove(ws)
    
    async def notify_workspace(self, user_id: int, workspace_id: int, event: dict):
        """向工作空间的所有连接广播变更事件"""
        key = f"{user_id}_{workspace_id}"
        if key in self.active:
            for ws in self.active[key]:
                try:
                    await ws.send_json(event)
                except:
                    pass
```

**Step 3: Sync Service**

```python
# service.py
# 发布同步事件到 Redis Streams
async def publish_file_change(user_id, workspace_id, event_type, file_path, file_id=None):
    """文件变更时发布事件"""
    event_data = {
        "user_id": user_id,
        "workspace_id": workspace_id,
        "event_type": event_type,
        "file_path": file_path,
        "file_id": file_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    # Push to Redis Stream
    redis_client.xadd(f"sync:{workspace_id}", event_data)
    return event_data
```

**Step 4: WebSocket Endpoint**

```
WS /ws/sync/{workspace_id}  — 客户端连接同步通道
  → 服务端推送文件变更事件
  → 客户端可发送 sync_ack / conflict_resolved

POST /api/v1/sync/events    — 查询同步事件历史
```

**Step 5: 注册到 main.py**

```
from domains.sync.router import router as sync_router
app.include_router(sync_router)

# WebSocket endpoint
@app.websocket("/ws/sync/{workspace_id}")
async def sync_websocket(websocket: WebSocket, workspace_id: int):
    ...
```

---

### Task 2: Electron 桌面客户端

**目标:** 创建 Electron 桌面客户端，具备文件同步能力

**Files:**
- 创建: `desktop/package.json`
- 创建: `desktop/electron/main.js`
- 创建: `desktop/electron/preload.js`
- 创建: `desktop/src/App.vue` (或 renderer)
- 创建: `desktop/src/main.ts`
- 创建: `desktop/src/sync/sync-engine.ts`
- 创建: `desktop/src/stores/sync.ts`
- 创建: `desktop/vite.config.ts`
- 创建: `desktop/index.html`

**Step 1: Electron 入口**

```javascript
// electron/main.js
const { app, BrowserWindow, ipcMain, Tray, Menu } = require('electron')
const path = require('path')
const { SyncEngine } = require('./sync-engine')

let mainWindow
let syncEngine

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 400, height: 600,
    webPreferences: { preload: path.join(__dirname, 'preload.js') }
  })
  mainWindow.loadURL('http://localhost:5173')  // Vue dev server
}

app.whenReady().then(() => {
  createWindow()
  syncEngine = new SyncEngine()
  syncEngine.start()
})
```

**Step 2: 同步引擎 (主进程)**

```javascript
// electron/main.js 中内联或单独文件
const chokidar = require('chokidar')
const WebSocket = require('ws')
const fs = require('fs')
const path = require('path')

class SyncEngine {
  constructor() {
    this.watcher = null
    this.ws = null
    this.localPath = ''
    this.workspaceId = null
  }

  async connect(serverUrl, token, workspaceId, localPath) {
    this.workspaceId = workspaceId
    this.localPath = localPath
    
    // Connect WebSocket
    this.ws = new WebSocket(`${serverUrl}/ws/sync/${workspaceId}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    
    // Start file watcher
    this.watcher = chokidar.watch(localPath, {
      ignoreInitial: true,
      awaitWriteFinish: { stabilityThreshold: 200 }
    })
    
    this.watcher.on('add', p => this.onLocalChange('create', p))
    this.watcher.on('change', p => this.onLocalChange('modify', p))
    this.watcher.on('unlink', p => this.onLocalChange('delete', p))
    
    // Listen for remote changes
    this.ws.on('message', data => {
      const event = JSON.parse(data)
      this.onRemoteChange(event)
    })
  }

  onLocalChange(eventType, filePath) {
    const relativePath = path.relative(this.localPath, filePath)
    // Upload to server via MinIO presigned URL or API
    // Send event via WebSocket
    this.ws?.send(JSON.stringify({
      type: 'file_change',
      event_type: eventType,
      file_path: relativePath
    }))
  }

  onRemoteChange(event) {
    const targetPath = path.join(this.localPath, event.file_path)
    // Download file from server
    // Write to local filesystem
  }

  stop() {
    this.watcher?.close()
    this.ws?.close()
  }
}
```

**Step 3: Vue 渲染进程**

简单的设置界面：
- 服务器地址配置
- 登录/认证
- 工作空间列表 → 选择 → 关联本地文件夹
- 同步状态指示

**Step 4: 托盘图标**

系统托盘显示同步状态（绿色=同步中，红色=断开，黄色=有冲突）

---

### Task 3: 示例插件 — 待办 App

**目标:** 创建一个完整的待办插件，验证插件架构全流程

**Files:**
- 创建: `backend/plugins/todo/manifest.json`
- 创建: `backend/plugins/todo/backend/__init__.py`
- 创建: `backend/plugins/todo/backend/models.py`
- 创建: `backend/plugins/todo/backend/schemas.py`
- 创建: `backend/plugins/todo/backend/service.py`
- 创建: `backend/plugins/todo/backend/router.py`
- 创建: `backend/plugins/todo/frontend/views/TodoBoard.vue`
- 创建: `backend/plugins/todo/frontend/components/TodoCard.vue`
- 创建: `backend/plugins/todo/frontend/index.js`

**Step 1: manifest.json**

```json
{
  "name": "todo",
  "version": "1.0.0",
  "title": "待办事项",
  "description": "看板式待办管理，支持自然语言创建",
  "icon": "Check",
  "permissions": ["files.read"],
  "routes": {
    "main": "/apps/todo"
  }
}
```

**Step 2: Backend model**

```python
class PluginTodo(Base):
    __tablename__ = "plugin_todo_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, in_progress, done
    priority = Column(Integer, default=0)
    due_date = Column(DateTime, nullable=True)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

**Step 3: Backend API**

```
自动注册到: /api/plugins/todo/
GET    /api/plugins/todo/items       — 列表
POST   /api/plugins/todo/items       — 创建
PUT    /api/plugins/todo/items/{id}  — 更新
DELETE /api/plugins/todo/items/{id}  — 删除
```

**Step 4: Frontend**

TodoBoard.vue 渲染看板视图（未开始/进行中/已完成三列），支持拖拽改变状态。
通过 axios 调用 `/api/plugins/todo/items` API。

当插件安装后：
1. 后端自动注册路由到 `/api/plugins/todo/`
2. 前端侧边栏自动出现"待办事项"菜单项（因为插件 store 注册了 manifest）
3. 点击后 PluginHost 渲染 TodoBoard.vue

---

### Task 4: 验证

**Backend:**
```bash
# 后端所有路由验证
python -c "from main import app; print(len([r for r in app.routes if hasattr(r,'path')]))"

# 验证插件目录可发现
# 重启后端后检查 /api/v1/plugins 返回 todo
curl http://localhost:8000/api/v1/plugins
# 预期: 包含 todo 插件信息
```

**Frontend:**
```bash
cd frontend && npx vue-tsc --noEmit
# 0 errors
```

**Desktop:**
```bash
cd desktop && npm install && npm run dev
# Electron 窗口打开
```
