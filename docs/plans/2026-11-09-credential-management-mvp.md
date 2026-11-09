# OmniAide 简单凭据管理方案（MVP）

## 1. 目标

给 Agent 提供一个简单、可直接使用的凭据管理能力：

- 用户在 Web 端维护凭据
- 凭据加密存储
- Agent 可以列出凭据、获取凭据
- 提供通用 HTTP 工具，让 Agent 使用凭据访问外部系统
- 不做系统适配、不做域名绑定、不做审批流

核心原则：

> 先让模型能拿到凭据并使用；安全增强放到后续版本。

## 2. 非目标（MVP 不做）

- GitLab / Jira / Gerrit 专用适配器
- 域名绑定、Host allowlist
- MCP env/headers 引用改造
- OAuth 自动刷新
- 多用户共享、Bot 级作用域
- 凭据审批、二次验证、审计表
- 外部密码管理器 / Vault 集成
- SSH Key 临时落地执行

## 3. 使用方式

### 3.1 Agent 工具

```text
list_credentials()
```

返回凭据元数据，不返回 secret：

```json
[
  {
    "name": "gitlab-main",
    "type": "username_password",
    "username": "alice",
    "description": "GitLab 主账号"
  }
]
```

```text
get_credential(name)
```

返回明文：

```json
{
  "name": "gitlab-main",
  "type": "username_password",
  "username": "alice",
  "secret": "xxxxx"
}
```

```text
http_request(credential, method, url, headers?, body?)
```

工具内部解密并注入认证信息，不把 secret 返回给模型。

示例：

```json
{
  "credential": "gitlab-main",
  "method": "GET",
  "url": "https://gitlab.example.com/api/v4/projects"
}
```

### 3.2 Web 管理

入口：

```text
设置 → 凭据
```

功能：

- 列表
- 新增
- 编辑
- 删除
- 搜索
- 查看明文
- 复制

## 4. 数据模型

表名：`credentials`

| 字段 | 类型 | 说明 |
|---|---|---|
| id | Integer PK | |
| user_id | Integer FK users.id | 按用户隔离 |
| name | String(100) | 凭据名称，用户内唯一 |
| type | String(30) | text / username_password / ssh_key |
| username | String(200) | 可选 |
| secret_encrypted | Text | 加密后的 secret |
| description | String(500) | 可选 |
| auth_header | String(100) | 默认 `Authorization` |
| auth_prefix | String(50) | 默认 `Bearer ` |
| last_used_at | DateTime | 最近使用时间 |
| created_at | DateTime | |
| updated_at | DateTime | |

约束：

```text
UNIQUE(user_id, name)
```

类型定义：

```text
text                API Token、Secret Text
username_password   用户名 + 密码 / Token
ssh_key             SSH 私钥文本
```

`auth_header` / `auth_prefix` 用于 `http_request`：

```text
Authorization: Bearer <secret>
X-API-Key: <secret>
PRIVATE-TOKEN: <secret>
```

## 5. 加密

MVP 直接复用：

```text
backend/core/crypto.py
encrypt_secret()
decrypt_secret()
```

风险：

- 当前密钥来自 `mail_encryption_key` 或 `jwt_secret`
- `jwt_secret` 变化会导致历史密文无法解密

要求：

- 生产环境固定 `JWT_SECRET` 和 `MAIL_ENCRYPTION_KEY`
- 后续引入独立 `OMNIAIDE_MASTER_KEY`
- 本 MVP 不改现有加密实现

## 6. 后端接口

前缀：`/api/credentials`

### 列表

```text
GET /api/credentials
```

返回：

```json
[
  {
    "id": 1,
    "name": "gitlab-main",
    "type": "username_password",
    "username": "alice",
    "description": "GitLab 主账号",
    "auth_header": "Authorization",
    "auth_prefix": "Bearer ",
    "last_used_at": "2026-11-09T12:00:00",
    "created_at": "2026-11-09T12:00:00",
    "updated_at": "2026-11-09T12:00:00",
    "has_secret": true
  }
]
```

不返回 `secret`。

### 新增

```text
POST /api/credentials
```

请求：

```json
{
  "name": "gitlab-main",
  "type": "username_password",
  "username": "alice",
  "secret": "xxxxx",
  "description": "GitLab 主账号",
  "auth_header": "Authorization",
  "auth_prefix": "Bearer "
}
```

### 修改

```text
PATCH /api/credentials/{id}
```

`secret` 留空表示不修改。

### 删除

```text
DELETE /api/credentials/{id}
```

### 查看明文

```text
POST /api/credentials/{id}/reveal
```

返回：

```json
{ "secret": "xxxxx" }
```

仅允许本人凭据。

## 7. Agent 工具实现

新增文件：

```text
backend/ai/mcp/tools/credentials.py
```

工具清单：

```python
TOOLS = [
    (list_credentials_tool, list_credentials),
    (get_credential_tool, get_credential),
    (http_request_tool, http_request),
]
```

注册：

```text
backend/ai/mcp/tools/register_core.py
```

工具要求：

- 从当前用户上下文取 `user_id`
- 只能访问本人凭据
- `get_credential` 更新 `last_used_at`
- `http_request` 更新 `last_used_at`
- 错误信息不包含 secret
- `http_request` 只允许 `http` / `https`
- 设置超时，避免长时间挂起
- 限制返回内容长度

认证注入规则：

```text
type=text:
  <auth_header>: <auth_prefix><secret>

type=username_password:
  Authorization: Basic base64(username:secret)

type=ssh_key:
  http_request 不支持；仅 get_credential 返回
```

## 8. 前端实现

新增页面：

```text
frontend/src/views/Credentials.vue
```

挂载方式二选一：

1. 在 `Settings.vue` 增加“凭据”Tab
2. 新增 `/settings/credentials` 页面

推荐方案 1，改动小。

页面结构：

```text
凭据
├── 搜索框
├── 新增凭据按钮
└── 表格
    ├── 名称
    ├── 类型
    ├── 用户名
    ├── 描述
    ├── 最近使用
    └── 操作：编辑 / 查看 / 复制 / 删除
```

新增/编辑弹窗字段：

```text
名称
类型（text / username_password / ssh_key）
用户名（type=username_password 时显示）
Secret（type=password，编辑时留空表示不修改）
描述
认证 Header（默认 Authorization）
认证前缀（默认 Bearer ）
```

注意：

- 列表不显示 secret
- 查看明文走 reveal 接口
- 不把 secret 写入 localStorage
- 删除前二次确认

## 9. 文件改动清单

### 后端

```text
backend/core/credentials/__init__.py
backend/core/credentials/models.py
backend/core/credentials/schemas.py
backend/core/credentials/service.py
backend/core/credentials/router.py

backend/ai/mcp/tools/credentials.py
backend/ai/mcp/tools/register_core.py

backend/main.py
```

### 前端

```text
frontend/src/views/Credentials.vue
frontend/src/views/Settings.vue
```

### 数据库

```text
随 Base.metadata 自动建表
如生产环境依赖迁移函数，则补 credentials 表迁移
```

## 10. 测试计划

### API

1. 新增凭据
2. 列表不包含 secret
3. 修改凭据，secret 留空保持原值
4. reveal 返回明文
5. 删除凭据
6. 用户 A 不能访问用户 B 的凭据

### Web

1. 新增、编辑、删除
2. 搜索
3. 查看明文
4. 复制
5. 刷新页面后仍存在

### Agent

1. `list_credentials` 只返回元数据
2. `get_credential("gitlab-main")` 返回明文
3. `http_request` 使用 text 类型凭据
4. `http_request` 使用 username_password 类型凭据
5. 请求失败时错误信息不包含 secret
6. `last_used_at` 更新

## 11. 安全说明

MVP 接受以下风险：

- `get_credential` 会把明文返回给模型
- 明文可能进入模型上下文、运行记录或日志
- `http_request` 没有域名绑定，理论上可被提示注入利用
- 没有审批和细粒度权限

适用场景：

```text
单用户、可信模型、内网自托管环境
```

如果后续需要加强，按顺序补：

1. `allowed_hosts` 可选域名绑定
2. 工具结果脱敏 / 不持久化 secret
3. 独立 `OMNIAIDE_MASTER_KEY`
4. 使用审计表
5. 写操作审批
6. MCP env/headers 使用凭据引用
7. OAuth / SSH Key 临时落地

## 12. 实施顺序

1. 数据库模型 + 加密服务
2. CRUD 接口
3. Agent 工具（list / get / http_request）
4. Web 凭据页面
5. 后端构建部署
6. 前端构建部署
7. 端到端验证

预计改动量：

```text
后端：约 400-600 行
前端：约 250-350 行
```

## 13. 验收标准

- Web 可以新增一条 GitLab 凭据
- 列表看不到明文
- 查看按钮能看到明文
- 对话中 Agent 能列出凭据
- Agent 能通过 `get_credential` 获取凭据
- Agent 能通过 `http_request` 使用凭据访问外部系统
- secret 不出现在普通列表接口和错误日志中
