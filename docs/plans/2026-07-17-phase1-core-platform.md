# OmniAide Phase 1 — 核心平台 (网盘 + 工作空间 + 插件架构)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 搭建核心平台：文件管理、工作空间、插件系统架构、前端核心布局

**Architecture:** 核心平台 + 插件生态。核心 = auth + 文件 + 工作空间 + 插件注册表 + AI 引擎。所有功能型模块（待办、歌单等）为可安装插件。

**Tech Stack:** Python FastAPI, Vue 3 + Element Plus, MinIO, MySQL 8.0

---

### Task 1: 前端重构 — 核心布局 + 插件容器

**目标:** 重构前端为"核心 Shell"架构——侧边栏核心菜单 + 动态插件菜单区，内容区为核心页面容器

**Files:**
- 修改: `frontend/src/App.vue`
- 创建: `frontend/src/core/layout/CoreLayout.vue`
- 创建: `frontend/src/core/layout/CoreSidebar.vue`
- 创建: `frontend/src/core/layout/CoreHeader.vue`
- 创建: `frontend/src/core/layout/PluginHost.vue`
- 创建: `frontend/src/stores/core/plugin.ts`
- 创建: `frontend/src/router/plugin-routes.ts`
- 修改: `frontend/src/router/index.ts`
- 修改: `frontend/src/views/Home.vue`

**Step 1: CoreLayout.vue — 主布局框架**

核心布局采用 Element Plus 的 Container 布局：
- 左侧可折叠侧边栏 (菜单)
- 顶部栏 (搜索 / 通知 / 用户)
- 主内容区 (router-view)
- AI 对话浮窗
- 底部同步状态条

**Step 2: CoreSidebar.vue**

菜单结构分为两个区域：
1. **核心菜单** (硬编码)：文件、工作空间、设置
2. **插件菜单** (动态)：从 plugin store 读取已安装插件的菜单项

使用 `el-menu` 组件，插件菜单项在 `onMounted` 时动态注册。

**Step 3: Plugin Host**

核心页面：PluginHost.vue 组件是一个路由容器，用于渲染插件页面。

路由匹配规则：`/apps/:pluginName/*` 映射到 PluginHost，由前端插件注册表决定渲染哪个组件。

**Step 4: Plugin Store**

```typescript
// stores/core/plugin.ts
interface PluginManifest {
  name: string
  title: string
  icon: string
  routes: { main: string }
}

export const usePluginStore = defineStore('plugin', {
  state: () => ({
    installed: [] as PluginManifest[],
    componentMap: {} as Record<string, any>
  }),
  actions: {
    register(manifest: PluginManifest, component: any) {
      this.installed.push(manifest)
      this.componentMap[manifest.name] = component
    }
  }
})
```

**Step 5: 路由器重构**

```typescript
// router/index.ts
const coreRoutes = [
  { path: '/login', component: Login },
  { path: '/', component: CoreLayout, children: [
    { path: '', redirect: '/files' },
    { path: 'files', component: FileManager },
    { path: 'workspaces', component: WorkspaceManager },
    { path: 'settings', component: Settings },
    { path: 'apps/:pluginName/:pathMatch(.*)*', component: PluginHost }
  ]}
]
```

**Step 6: 页面文件**

创建/修改核心页面：
- `views/Files.vue` — 文件管理页 (占位)
- `views/Workspaces.vue` — 工作空间页 (占位)
- `views/Settings.vue` — 设置页 (占位)

---

### Task 2: 后端 — 插件注册表核心

**目标:** 实现插件注册表基础能力：插件元数据模型、安装/列表/启停 API、动态路由注册

**Files:**
- 创建: `backend/core/plugin/__init__.py`
- 创建: `backend/core/plugin/models.py`
- 创建: `backend/core/plugin/registry.py`
- 创建: `backend/core/plugin/router.py`
- 创建: `backend/core/plugin/schemas.py`
- 修改: `backend/main.py`

**Step 1: Plugin 模型**

plugin_registry 表：
```python
class PluginRegistry(Base):
    __tablename__ = "plugin_registry"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    version = Column(String(20), nullable=False)
    title = Column(String(200))
    description = Column(Text)
    icon = Column(String(50))
    enabled = Column(Boolean, default=True)
    manifest = Column(JSON)  # 完整 manifest.json
    installed_at = Column(DateTime, server_default=func.now())
```

**Step 2: Registry 核心逻辑**

`registry.py`:
```python
class PluginRegistryService:
    """管理插件的安装、加载、路由注册"""

    async def discover_plugins(self) -> list[PluginInfo]:
        """扫描 plugins/ 目录，读取 manifest.json"""

    async def install_from_zip(self, zip_path: str) -> PluginInfo:
        """解压 zip 到 plugins/<name>/, 注册路由, 创建表"""

    async def register_routes(self, plugin_name: str, app: FastAPI):
        """动态 import 插件的 backend/router.py, include_router"""

    async def unregister_routes(self, plugin_name: str, app: FastAPI):
        """移除插件路由"""
```

**Step 3: 启动时自动发现**

修改 `main.py` 的 `lifespan`，在启动时扫描 `plugins/` 目录，自动注册已安装且启用的插件路由。

**Step 4: API 端点**

```
POST /api/v1/plugins/install        # 安装插件 (multipart upload zip)
GET  /api/v1/plugins                # 插件列表
POST /api/v1/plugins/{name}/toggle  # 启停
DELETE /api/v1/plugins/{name}       # 卸载
```

---

### Task 3: 后端 — 文件管理模块

**目标:** 完整的文件管理核心——元数据 CRUD、MinIO 预签名上传/下载、标签、回收站

**Files:**
- 创建: `backend/domains/file/__init__.py`
- 创建: `backend/domains/file/models.py`
- 创建: `backend/domains/file/schemas.py`
- 创建: `backend/domains/file/service.py`
- 创建: `backend/domains/file/router.py`
- 修改: `backend/main.py`

**Step 1: File Model**

```python
class File(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True)
    bucket = Column(String(50), nullable=False)       # user-files, music, etc.
    object_key = Column(String(500), nullable=False)
    original_name = Column(String(255))
    size = Column(BigInteger)
    mime_type = Column(String(100))
    tags = Column(JSON)
    is_favorite = Column(Boolean, default=False)
    status = Column(String(20), default="active")     # active, trash
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)
```

**Step 2: Upload Flow**

1. 前端请求 `POST /api/v1/files/upload-url` → 服务端生成预签名 PUT URL + 写入 DB (status=uploading)
2. 前端直传 MinIO
3. 前端调用 `POST /api/v1/files/confirm` → 更新 status=active
4. 异步任务：提取内容 → 向量化 → 存入 Qdrant

**Step 3: API Endpoints**

```
GET    /api/v1/files                   # 列表 (filter/sort/page)
POST   /api/v1/files/upload-url        # 获取预签名上传 URL
POST   /api/v1/files/confirm           # 确认上传完成
GET    /api/v1/files/{id}/download-url # 获取下载预签名 URL
GET    /api/v1/files/{id}              # 详情
PUT    /api/v1/files/{id}/tags         # 更新标签
PUT    /api/v1/files/{id}/favorite     # 收藏/取消
DELETE /api/v1/files/{id}              # 移入回收站
POST   /api/v1/files/{id}/restore      # 还原
DELETE /api/v1/files/{id}/permanent    # 彻底删除
```

---

### Task 4: 后端 — 工作空间模块

**目标:** 工作空间 CRUD，工作空间与文件的关联

**Files:**
- 创建: `backend/domains/workspace/__init__.py`
- 创建: `backend/domains/workspace/models.py`
- 创建: `backend/domains/workspace/schemas.py`
- 创建: `backend/domains/workspace/service.py`
- 创建: `backend/domains/workspace/router.py`
- 修改: `backend/main.py`

**Step 1: Workspace Model**

```python
class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    bucket = Column(String(50), nullable=False)       # MinIO bucket for this workspace
    sync_enabled = Column(Boolean, default=False)     # 是否启用桌面同步
    local_path = Column(String(500), nullable=True)    # 桌面端本地路径 (仅客户端使用)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

**Step 2: API Endpoints**

```
GET    /api/v1/workspaces              # 列表
POST   /api/v1/workspaces              # 创建
GET    /api/v1/workspaces/{id}         # 详情
PUT    /api/v1/workspaces/{id}         # 更新
DELETE /api/v1/workspaces/{id}         # 删除
GET    /api/v1/workspaces/{id}/files   # 工作空间内文件列表
```

工作空间的文件操作复用文件模块的 API，通过 `workspace_id` 过滤。

---

### Task 5: 前端 — 文件管理页面

**目标:** 核心文件管理界面——网格/列表视图、上传、预览、标签

**Files:**
- 修改: `frontend/src/views/Files.vue`
- 创建: `frontend/src/components/file/FileGrid.vue`
- 创建: `frontend/src/components/file/FileList.vue`
- 创建: `frontend/src/components/file/FileUploader.vue`
- 创建: `frontend/src/components/file/FilePreview.vue`
- 修改: `frontend/src/stores/core/file.ts`

**Step 1: File Store**

```typescript
// stores/core/file.ts
export const useFileStore = defineStore('file', {
  state: () => ({
    files: [],
    currentFolder: null,
    viewMode: 'grid', // grid | list
    selected: []
  }),
  actions: {
    async fetchFiles(params) { /* GET /api/v1/files */ },
    async getUploadUrl(filename) { /* POST /api/v1/files/upload-url */ },
    async confirmUpload(fileId) { /* POST /api/v1/files/confirm */ },
    async deleteFiles(ids) { /* DELETE /api/v1/files/{id} */ }
  }
})
```

**Step 2: Files.vue**

主页面：顶部工具栏 (新建文件夹/上传/视图切换/搜索) + 内容区 (FileGrid 或 FileList)

**Step 3: FileUploader.vue**

拖拽/点击上传：请求预签名 URL → 直传 MinIO → 回调确认 → 显示进度

**Step 4: FilePreview.vue**

文件预览：图片直接显示、视频/音频用 HTML5 player、文档用 iframe/嵌入

---

### Task 6: 前端 — 工作空间管理页面

**目标:** 工作空间创建/管理界面

**Files:**
- 修改: `frontend/src/views/Workspaces.vue`
- 创建: `frontend/src/components/workspace/WorkspaceCard.vue`
- 创建: `frontend/src/components/workspace/WorkspaceDialog.vue`
- 修改: `frontend/src/stores/core/workspace.ts`

**Step 1: Workspace Store**

```typescript
export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    workspaces: [],
    current: null
  }),
  actions: {
    async fetchWorkspaces() { /* GET /api/v1/workspaces */ },
    async create(data) { /* POST /api/v1/workspaces */ },
    async delete(id) { /* DELETE /api/v1/workspaces/{id} */ }
  }
})
```

**Step 2: Workspaces.vue**

卡片列表展示所有工作空间，每个卡片显示名称、文件数、同步状态。
点击进入工作空间内部文件浏览（复用 Files.vue 带 workspace_id 过滤）。

**Step 3: WorkspaceDialog.vue**

创建/编辑工作空间的对话框：名称、描述、是否启用同步。

---

### 验证清单

| 检查项 | 方法 | 预期 |
|--------|------|------|
| 前端布局重构 | 浏览器访问 /files | 显示完整侧边栏 + 顶部栏 + 内容区 |
| 插件列表 API | `GET /api/v1/plugins` | 返回空列表或已安装插件 |
| 文件上传 | 拖拽文件到上传区 | 直传 MinIO → 确认 → 列表显示 |
| 文件列表 | `GET /api/v1/files` | 返回文件分页数据 |
| 工作空间 CRUD | `POST /api/v1/workspaces` | 创建成功，返回 workspace |
| 工作空间文件 | `GET /api/v1/workspaces/{id}/files` | 仅返回该空间文件 |
| 回收站 | 删除文件 → 列表 | 文件移入回收站，可还原 |
