# OmniAide Phase 0 — 基础设施搭建实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 从零搭建项目的完整骨架——Monorepo 结构、Docker 基础设施、后端和前端脚手架、用户认证。

**Architecture:** 领域模块化单体。后端 FastAPI 按 domain 分包，前端 Vue 3 + Element Plus，所有服务 Docker Compose 编排。

**Tech Stack:** Python FastAPI, Vue 3 + Vite + Element Plus, MySQL 8.0, MinIO, Qdrant, Redis, Docker Compose

---

### Task 1: 初始化 Monorepo 根目录结构

**Files:**
- Create: `omniamon/` 根目录和工作区配置文件
- Create: `omniamon/.gitignore`
- Create: `omniamon/.env.example`
- Create: `omniamon/README.md`

**Step 1: 创建根目录结构和 .gitignore**

在当前工作目录 `E:\workspace_ominaide` 中创建 `omniamon/` 作为项目根目录。

```bash
mkdir -p omniamon/{backend/{core/{auth,config,database,minio},domains/{file,todo,media,agent,event,notification}},frontend/src/{views,components,stores,api,router},desktop,browser-ext,docker/nginx,docs,scripts}
```

**.gitignore 内容：**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
*.egg

# Node
node_modules/
dist/
.vite/

# IDE
.vscode/
.idea/
*.swp

# Environment
.env
*.local

# OS
.DS_Store
Thumbs.db

# Docker
docker/volumes/

# Logs
*.log
```

**.env.example 内容：**

```
# Database
DATABASE_URL=mysql+aiomysql://omniaide:omniaide_pass@mysql:3306/omniaide

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=omniaide_minio
MINIO_SECRET_KEY=omniaide_minio_secret

# Qdrant
QDRANT_URL=http://qdrant:6333

# Redis
REDIS_URL=redis://redis:6379/0

# LLM (初期使用云端 API)
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# JWT
JWT_SECRET=change-this-to-a-random-secret
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# Server
API_HOST=0.0.0.0
API_PORT=8000
```

**Step 2: 创建根目录 README.md**

```markdown
# OmniAide

> Your Omni-present Aide.

一个完全私有化部署的个人 AI 助手平台。

## 快速开始

```bash
# 启动全部服务
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d

# 初始化数据库
docker compose exec backend python manage.py init

# 访问 http://localhost:3000
```

## 项目结构

- `frontend/` — Vue 3 前端
- `backend/` — FastAPI 后端
- `desktop/` — Electron 桌面客户端
- `browser-ext/` — Chrome 浏览器扩展
- `docker/` — Docker Compose 编排
```
```

**Step 3: Commit**

```bash
git init
git add .
git commit -m "chore: initialize monorepo structure"
```

---

### Task 2: Docker Compose 编排基础设施服务

**Files:**
- Create: `omniamon/docker/docker-compose.yml`
- Create: `omniamon/docker/docker-compose.dev.yml`
- Create: `omniamon/docker/nginx/nginx.conf`
- Create: `omniamon/scripts/wait-for-it.sh`

**Step 1: 编写主 docker-compose.yml**

```yaml
version: "3.8"

services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root_pass
      MYSQL_DATABASE: omniaide
      MYSQL_USER: omniaide
      MYSQL_PASSWORD: omniaide_pass
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./mysql/init:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: omniaide_minio
      MINIO_ROOT_PASSWORD: omniaide_minio_secret
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

volumes:
  mysql_data:
  minio_data:
  qdrant_data:
  redis_data:
```

**Step 2: 编写开发用 docker-compose.dev.yml**

```yaml
version: "3.8"

services:
  backend:
    build:
      context: ../backend
      dockerfile: Dockerfile.dev
    ports:
      - "8000:8000"
    volumes:
      - ../backend:/app
    environment:
      - DATABASE_URL=mysql+aiomysql://omniaide:omniaide_pass@mysql:3306/omniaide
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=omniaide_minio
      - MINIO_SECRET_KEY=omniaide_minio_secret
      - QDRANT_URL=http://qdrant:6333
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET=dev-secret-key
    depends_on:
      mysql:
        condition: service_healthy
      minio:
        condition: service_healthy
      qdrant:
        condition: service_started
      redis:
        condition: service_healthy

  frontend:
    build:
      context: ../frontend
      dockerfile: Dockerfile.dev
    ports:
      - "3000:80"
    volumes:
      - ../frontend:/app
    depends_on:
      - backend
```

**Step 3: 编写 Nginx 配置**

```nginx
server {
    listen 80;
    server_name localhost;

    # 前端静态文件
    location / {
        proxy_pass http://frontend:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API 代理
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket 代理 (AI 对话)
    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

**Step 4: 验证 Docker Compose 启动**

```bash
docker compose -f docker/docker-compose.yml up -d
docker ps
# 预期: mysql, minio, qdrant, redis 都在运行
```

**Step 5: Commit**

---

### Task 3: 后端脚手架 — Core 模块

**Files:**
- Create: `omniamon/backend/requirements.txt`
- Create: `omniamon/backend/Dockerfile`
- Create: `omniamon/backend/Dockerfile.dev`
- Create: `omniamon/backend/core/__init__.py`
- Create: `omniamon/backend/core/config/__init__.py` + `settings.py`
- Create: `omniamon/backend/core/database/__init__.py` + `session.py` + `base.py`
- Create: `omniamon/backend/core/auth/__init__.py` + `jwt.py` + `password.py` + `dependencies.py`
- Create: `omniamon/backend/core/minio/__init__.py` + `client.py`
- Create: `omniamon/backend/main.py`
- Create: `omniamon/backend/manage.py`

**Step 1: 编写 requirements.txt**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy[asyncio]==2.0.30
aiomysql==0.2.0
pydantic==2.7.0
pydantic-settings==2.3.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
minio==7.2.3
qdrant-client==1.9.0
redis==5.0.0
celery==5.4.0
langchain==0.2.0
langchain-openai==0.1.0
httpx==0.27.0
python-dotenv==1.0.1
alembic==1.13.0
```

**Step 3: 编写核心模块**

`core/config/settings.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "mysql+aiomysql://omniaide:omniaide_pass@mysql:3306/omniaide"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "omniaide_minio"
    minio_secret_key: str = "omniaide_minio_secret"
    qdrant_url: str = "http://qdrant:6333"
    redis_url: str = "redis://redis:6379/0"
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    jwt_secret: str = "dev-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

`core/database/session.py`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from core.config.settings import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

`core/database/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

`core/auth/jwt.py`:

```python
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from core.config.settings import settings


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
```

`core/auth/password.py`:

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)
```

`core/auth/dependencies.py`:

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.auth.jwt import decode_access_token
from core.database.session import get_db

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return {"id": int(user_id)}
```

`core/minio/client.py`:

```python
from minio import Minio
from core.config.settings import settings

minio_client = Minio(
    endpoint=settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=False,
)


async def ensure_buckets():
    buckets = ["user-files", "music", "videos", "documents", "thumbnails", "backups"]
    for bucket in buckets:
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)
```

`main.py`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.minio.client import ensure_buckets
    await ensure_buckets()
    yield


app = FastAPI(title="OmniAide API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

`manage.py` (CLI 工具):

```python
import asyncio
from core.database.session import engine
from core.database.base import Base


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created.")


async def drop_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("Database tables dropped.")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "init":
        asyncio.run(init_db())
    elif cmd == "drop":
        asyncio.run(drop_db())
    else:
        print("Usage: python manage.py [init|drop]")
```

**Step 4: 编写 Dockerfile**

`Dockerfile` (生产):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`Dockerfile.dev` (开发):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Step 5: 验证后端启动**

```bash
cd backend
pip install -r requirements.txt
python manage.py init
# 预期: "Database tables created."
uvicorn main:app --reload
# 访问 http://localhost:8000/health → {"status": "ok"}
```

**Step 6: Commit**

---

### Task 4: 用户模块 — User Model & Auth API

**Files:**
- Create (或修改): `omniamon/backend/domains/auth/__init__.py`
- Create: `omniamon/backend/domains/auth/models.py`
- Create: `omniamon/backend/domains/auth/schemas.py`
- Create: `omniamon/backend/domains/auth/service.py`
- Create: `omniamon/backend/domains/auth/router.py`
- 修改: `omniamon/backend/main.py`

**Step 1: User SQLAlchemy 模型**

`domains/auth/models.py`:

```python
from sqlalchemy import Column, Integer, String, DateTime, func
from core.database.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
```

**Step 2: Pydantic Schemas**

`domains/auth/schemas.py`:

```python
from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    avatar_url: str | None = None

    model_config = {"from_attributes": True}
```

**Step 3: Service 层**

`domains/auth/service.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from domains.auth.models import User
from domains.auth.schemas import RegisterRequest
from core.auth.password import hash_password, verify_password
from core.auth.jwt import create_access_token


async def register(db: AsyncSession, req: RegisterRequest) -> User:
    existing = await db.execute(select(User).where(
        (User.username == req.username) | (User.email == req.email)
    ))
    if existing.scalar_one_or_none():
        raise ValueError("Username or email already exists")
    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.flush()
    return user


async def login(db: AsyncSession, username: str, password: str) -> str:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("Invalid username or password")
    return create_access_token({"sub": str(user.id)})
```

**Step 4: Router**

`domains/auth/router.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from domains.auth.schemas import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from domains.auth.service import register, login
from core.database.session import get_db
from core.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_endpoint(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register(db, req)
        return {"message": "User created", "user_id": user.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login_endpoint(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        token = await login(db, req.username, req.password)
        return TokenResponse(access_token=token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from domains.auth.models import User as UserModel
    result = await db.execute(select(UserModel).where(UserModel.id == user["id"]))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(u)
```

**Step 5: 注册到 main.py**

```python
from domains.auth.router import router as auth_router
app.include_router(auth_router)
```

**Step 6: 验证**

```bash
# 注册
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@test.com","password":"test123"}'
# 预期: {"message":"User created","user_id":1}

# 登录
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"test123"}'
# 预期: {"access_token":"...","token_type":"bearer"}
```

**Step 7: Commit**

---

### Task 5: 前端脚手架 — Vue 3 + Element Plus

**Files:**
- Create: `omniamon/frontend/package.json`
- Create: `omniamon/frontend/vite.config.ts`
- Create: `omniamon/frontend/tsconfig.json`
- Create: `omniamon/frontend/index.html`
- Create: `omniamon/frontend/src/main.ts`
- Create: `omniamon/frontend/src/App.vue`
- Create: `omniamon/frontend/src/router/index.ts`
- Create: `omniamon/frontend/src/stores/auth.ts`
- Create: `omniamon/frontend/src/api/client.ts`
- Create: `omniamon/frontend/src/views/Login.vue`
- Create: `omniamon/frontend/src/views/Home.vue`
- Create: `omniamon/frontend/Dockerfile.dev`

**Step 1: 生成 Vue 项目**

建议手动创建而非 `create-vue`，以精确控制文件内容。

`package.json`:
```json
{
  "name": "omniaide-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "vue-router": "^4.3.0",
    "pinia": "^2.1.0",
    "element-plus": "^2.7.0",
    "@element-plus/icons-vue": "^2.3.0",
    "axios": "^1.7.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.2.0",
    "vue-tsc": "^2.0.0",
    "typescript": "^5.4.0"
  }
}
```

**Step 2: 核心文件**

`vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') }
  },
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true }
    }
  }
})
```

`src/main.ts`:
```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(ElementPlus)
app.use(router)
app.mount('#app')
```

`src/App.vue`:
```vue
<template>
  <router-view />
</template>
```

`src/router/index.ts`:
```typescript
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/Login.vue') },
    { path: '/', component: () => import('@/views/Home.vue'), meta: { requiresAuth: true } }
  ]
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else {
    next()
  }
})

export default router
```

`src/api/client.ts`:
```typescript
import axios from 'axios'

const client = axios.create({ baseURL: '/api/v1' })

client.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client
```

`src/stores/auth.ts`:
```typescript
import { defineStore } from 'pinia'
import client from '@/api/client'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    user: null as any
  }),
  actions: {
    async login(username: string, password: string) {
      const res = await client.post('/auth/login', { username, password })
      this.token = res.data.access_token
      localStorage.setItem('token', this.token)
      await this.fetchUser()
    },
    async fetchUser() {
      const res = await client.get('/auth/me')
      this.user = res.data
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('token')
    }
  }
})
```

`src/views/Login.vue`:
```vue
<template>
  <el-container class="login-container">
    <el-card class="login-card">
      <h2>OmniAide</h2>
      <el-form @submit.prevent="handleLogin">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" style="width:100%">
            登录
          </el-button>
        </el-form-item>
      </el-form>
      <p v-if="error" style="color:red">{{ error }}</p>
    </el-card>
  </el-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    router.push('/')
  } catch (e: any) {
    error.value = e.response?.data?.detail || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container { height: 100vh; display: flex; align-items: center; justify-content: center; background: #f0f2f5; }
.login-card { width: 400px; }
</style>
```

`src/views/Home.vue`:
```vue
<template>
  <el-container style="height:100vh">
    <el-header>
      <span>OmniAide</span>
      <el-button @click="auth.logout()" style="float:right">退出</el-button>
    </el-header>
    <el-main>
      <h1>欢迎回来{{ auth.user?.username }}</h1>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
onMounted(() => auth.fetchUser())
</script>
```

`Dockerfile.dev`:
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json .
RUN npm install
CMD ["npm", "run", "dev", "--", "--host"]
```

**Step 3: 验证前端**

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:3000 → 应跳转到 /login
```

**Step 4: Commit**

---

### Task 6: 整合验证 — 完整启动流程

**Step 1: 从零启动全部服务**

```bash
# 1. 启动基础设施
docker compose -f docker/docker-compose.yml up -d

# 2. 启动后端 (开发模式)
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d backend

# 3. 初始化数据库
docker compose exec backend python manage.py init

# 4. 启动前端 (开发模式)
cd frontend && npm run dev

# 5. 验证注册和登录
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","email":"admin@test.com","password":"test123"}'

# 6. 验证前端登录页面可用
# 浏览器打开 http://localhost:3000
```

**Step 2: 验证完成后的清理脚本**

创建 `scripts/reset-dev.sh`:
```bash
#!/bin/bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d
docker compose exec backend python manage.py init
echo "Dev environment reset complete"
```

**Step 3: Final commit**

```bash
git add .
git commit -m "feat: complete Phase 0 infrastructure scaffold"
```

---

## 验证清单

| 检查项 | 命令 | 预期 |
|--------|------|------|
| Docker 服务运行 | `docker ps` | mysql/minio/qdrant/redis 在运行 |
| 后端健康检查 | `curl localhost:8000/health` | `{"status":"ok"}` |
| 用户注册 | `curl -X POST ... /auth/register` | 201 返回 |
| 用户登录 | `curl -X POST ... /auth/login` | 返回 token |
| 前端可访问 | 浏览器打开 localhost:3000 | 显示登录页 |
| 前后端联调 | 登录成功后跳转主页 | 显示 "欢迎回来" |
