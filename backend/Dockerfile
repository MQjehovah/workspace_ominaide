FROM python:3.12-slim
ENV TZ=Asia/Shanghai
WORKDIR /app

# git/ssh are required by the coding agent (delivery + deploy-key push).
# node/npm run the DingTalk Workspace CLI (`dws`) used by the MCP hub.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git openssh-client ca-certificates nodejs npm tar unzip && \
    rm -rf /var/lib/apt/lists/*

RUN npm config set registry https://registry.npmmirror.com && \
    npm install -g dingtalk-workspace-cli@1.0.62

# Two standard mounts:
#   /data   - mutable per-user data (workspace, skills, uploads, desktop plugins)
#   /config - server-level credentials (SSH key)
# DingTalk config/tokens are per-user under /data/workspace/<uid>/dingtalk, so
# there is no global DWS_CONFIG_DIR anymore.
ENV WORKSPACE_ROOT=/data/workspace \
    SKILLS_DIR=/data/skills \
    CODING_SSH_KEY_PATH=/config/ssh/id_rsa \
    DESKTOP_PLUGINS_DIR=/data/desktop_plugins
RUN mkdir -p /data/skills /data/workspace /data/desktop_plugins /config/ssh /root/.local/share

COPY requirements.txt .
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install --no-cache-dir -r requirements.txt

# Unprivileged user for model-driven repo commands (CODING_SANDBOX_USER).
# gid 1000 matches the bind-mounted workspace group; uid 1001 keeps root out.
RUN (groupadd -g 1000 omniaide || true) && \
    (useradd -u 1001 -g 1000 -m -d /home/agent -s /bin/bash agent || true)

COPY . .
RUN find /app -name '__pycache__' -type d -prune -exec rm -rf {} + || true

# Root only: the sandbox user (agent, uid 1001) must not read backend sources or
# the mounted uploads under /app. Matches the runtime hardening; keeps it baked
# into the image instead of relying on a post-start chmod.
RUN chmod 700 /app

# Access logs are emitted by TraceMiddleware with query strings stripped, so
# tokens used by media/WebSocket URLs never end up in Uvicorn logs.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--ws-ping-interval", "20", "--ws-ping-timeout", "30"]
