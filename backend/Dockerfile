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

# All persistent runtime data lives under one host directory mounted at
# /data/omniaide (workspace, skills, DWS credentials, SSH key, plugins).
ENV DWS_CONFIG_DIR=/data/omniaide/dws \
    SKILLS_DIR=/data/omniaide/skills \
    CODING_WORKSPACE_ROOT=/data/omniaide/workspace \
    CODING_SSH_KEY_PATH=/data/omniaide/ssh/id_rsa \
    DESKTOP_PLUGINS_DIR=/data/omniaide/desktop_plugins
RUN mkdir -p /data/omniaide/dws /data/omniaide/skills /data/omniaide/workspace \
    /data/omniaide/ssh /data/omniaide/desktop_plugins

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

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-ping-interval", "20", "--ws-ping-timeout", "30"]
