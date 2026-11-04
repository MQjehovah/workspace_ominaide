FROM python:3.12-slim
ENV TZ=Asia/Shanghai
WORKDIR /app

# git/ssh are required by the coding agent (delivery + deploy-key push).
RUN apt-get update && \
    apt-get install -y --no-install-recommends git openssh-client ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip install --no-cache-dir -r requirements.txt

# Unprivileged user for model-driven repo commands (CODING_SANDBOX_USER).
# gid 1000 matches the bind-mounted workspace group; uid 1001 keeps root out.
RUN (groupadd -g 1000 omniaide || true) && \
    (useradd -u 1001 -g 1000 -m -d /home/agent -s /bin/bash agent || true)

COPY . .
RUN find /app -name '__pycache__' -type d -prune -exec rm -rf {} + || true

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-ping-interval", "20", "--ws-ping-timeout", "30"]
