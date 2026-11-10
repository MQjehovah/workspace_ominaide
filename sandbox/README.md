# OmniAide Sandbox Runner

Template-driven Docker workspace service. It is the OmniAide equivalent of a
Codespaces control plane: create a workspace from a template, exec commands in
it, stream output, and let the reaper stop idle sandboxes.

The backend never talks to the Docker socket. Only this service does.

## Concepts

- **Template**: JSON file describing image, workdir, user, ports, resource
  limits and first-start setup commands.
- **Workspace**: one container created from a template, plus a persistent home
  volume and a bind-mounted project directory.
- **Exec**: run a command inside the workspace as the template user.
- **Reaper**: stops workspaces that have been idle longer than their TTL.

## API

All `/api` routes require `Authorization: Bearer $SANDBOX_RUNNER_TOKEN` when a
token is configured.

```text
GET    /api/health
GET    /api/templates
GET    /api/templates/{id}

POST   /api/workspaces
GET    /api/workspaces?owner_id=1
GET    /api/workspaces/{id}
POST   /api/workspaces/{id}/start
POST   /api/workspaces/{id}/stop
DELETE /api/workspaces/{id}

POST   /api/workspaces/{id}/exec
POST   /api/workspaces/{id}/exec/stream
POST   /api/workspaces/{id}/setup
GET    /api/workspaces/{id}/logs

POST   /api/templates/{id}/build
GET    /api/templates/{id}/build

ANY    /api/workspaces/{id}/proxy/{port}/{path}
WS     /api/workspaces/{id}/proxy/{port}/{path}
WS     /api/workspaces/{id}/terminal
```

The port proxy and terminal are internal. The backend exposes them under
`/api/sandbox/...` with user auth; the browser never sees the runner token.

Create:

```json
{
  "template": "fullstack",
  "owner_id": "1",
  "name": "workspace_ominaide",
  "project_path": "/data/workspace/1/projects/workspace_ominaide",
  "ttl_seconds": 1800
}
```

Exec:

```json
{
  "command": "pytest -q",
  "cwd": "backend",
  "timeout_seconds": 600
}
```

Streaming exec returns SSE:

```text
data: {"type": "chunk", "stream": "stdout", "text": "..."}
data: {"type": "done"}
```

## Security model

- Workspaces are mounted only the project directory at `/workspace`.
- Each workspace gets a dedicated `/home/agent` volume.
- `cap_drop=ALL`, `no-new-privileges`, non-root user, pids/memory/cpu limits.
- The Docker socket is mounted only into the runner, never into workspaces.
- `project_path` must be under `SANDBOX_ALLOWED_ROOTS`.
- No backend secrets, `/config`, or `/data` are exposed to workspaces.

## Template builds

A template may build its own image instead of referencing a prebuilt one:

```json
{
  "id": "my-project",
  "name": "My Project",
  "image": "omniaide/my-project:latest",
  "build": {
    "context": "/data/sandbox/builds/my-project",
    "dockerfile": "Dockerfile",
    "args": {"NODE_VERSION": "20"}
  },
  "workdir": "/workspace"
}
```

The build context must be under `SANDBOX_ALLOWED_ROOTS`. Trigger a build with
`POST /api/templates/my-project/build` and poll
`GET /api/templates/my-project/build`. Creating a workspace also builds the
image automatically when it is missing.

## OpenCode

The base image installs `@opencode/cli@2.2.6`. When the backend runs with
`CODING_SANDBOX_MODE=docker`, OpenCode executes inside the workspace container,
writes its provider config to `/home/agent/.config/opencode/opencode.json`, and
keeps its session state in the workspace home volume.

## Build and run

```bash
docker build -f sandbox/images/base.Dockerfile -t omniaide/sandbox-base:latest sandbox/images
docker compose -f docker/docker-compose.sandbox.yml up -d --build
curl -s http://127.0.0.1:8010/api/health
```

Docker resolves bind-mount sources on the host, not inside the runner. The
runner therefore mounts the backend data volume at `/data` and translates it
back to the host path before creating a workspace:

```text
SANDBOX_DATA_MOUNT=/data/docker/omniaide/data
SANDBOX_HOST_DATA_ROOT=/data/docker/omniaide/data
```

In this deployment the backend sees the project at
`/data/workspace/<uid>/projects/...`; the runner accepts that path and mounts
the host path `/data/docker/omniaide/data/workspace/<uid>/projects/...` into the
workspace. Set `SANDBOX_HOST_DATA_ROOT` to the host-side path whenever the
runner's `/data` is itself a bind mount.
