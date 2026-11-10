# OmniAide sandbox base image: Python + Node + git, non-root agent user.
# Build: docker build -f sandbox/images/base.Dockerfile -t omniaide/sandbox-base:latest sandbox/images
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    HOME=/home/agent \
    PATH=/home/agent/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin

ARG NODE_VERSION=20
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash ca-certificates curl gnupg git openssh-client \
        build-essential pkg-config ripgrep jq less procps \
        python3-dev libpq-dev && \
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN npm config set registry https://registry.npmmirror.com && \
    npm install -g pnpm@9 && \
    npm cache clean --force

# Agent identity must match CODING_SANDBOX_HOME conventions and the bind-mounted
# project group on the host.
RUN (groupadd -g 1000 agent || true) && \
    (useradd -u 1001 -g 1000 -m -d /home/agent -s /bin/bash agent || true) && \
    mkdir -p /workspace /home/agent/.cache /home/agent/.config /home/agent/.local/share && \
    chown -R agent:agent /workspace /home/agent && \
    su agent -c "git config --global --add safe.directory '*'"

USER agent
WORKDIR /workspace

# Keep the container alive; the runner execs commands into it.
CMD ["sleep", "infinity"]
