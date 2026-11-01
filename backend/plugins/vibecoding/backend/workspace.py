import asyncio
import os
import re
from pathlib import Path

from core.config.settings import settings

SKIP_DIRS = {
    "node_modules", ".git", ".ssh", "dist", "build", "dist-electron", "out", "target",
    "__pycache__", ".venv", "venv", ".next", ".nuxt", "coverage", ".idea", ".vscode",
}
MAX_FILE_BYTES = 1024 * 1024
MAX_READ_CHARS = 200_000
MAX_TOOL_RESULT_CHARS = 20_000
MAX_DIR_ENTRIES = 400
MAX_COMMAND_OUTPUT = 30_000


def _is_sensitive_name(name: str) -> bool:
    n = name.lower()
    if n == ".env":
        return True
    if n.startswith(".env.") and n != ".env.example":
        return True
    if n in {"id_rsa", "id_ed25519", "id_dsa", "id_ecdsa"}:
        return True
    if n.endswith((".pem", ".key", ".p12", ".pfx")):
        return True
    return False


def _is_sensitive(rel: Path) -> bool:
    parts = [p.lower() for p in rel.parts]
    if ".git" in parts or ".ssh" in parts:
        return True
    if any(_is_sensitive_name(part) for part in parts):
        return True
    return False


def is_sensitive_path(path: str) -> bool:
    """Check a repo-relative path (as produced by `git`) for secrets."""
    return _is_sensitive(Path(path))


def git_env(identity: dict | None = None, ssh_key: str | None = None) -> dict:
    """Environment for git subprocesses: commit identity + non-interactive SSH."""
    env = os.environ.copy()
    if identity:
        if identity.get("name"):
            env["GIT_AUTHOR_NAME"] = identity["name"]
            env["GIT_COMMITTER_NAME"] = identity["name"]
        if identity.get("email"):
            env["GIT_AUTHOR_EMAIL"] = identity["email"]
            env["GIT_COMMITTER_EMAIL"] = identity["email"]
    key = ssh_key or settings.coding_ssh_key_path or "/root/.ssh/id_rsa"
    env.setdefault("GIT_SSH_COMMAND", (
        f"ssh -i {key} -o IdentitiesOnly=yes "
        "-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/omniaide_known_hosts"
    ))
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    # The workspace is bind-mounted from the host (uid 1000) while the backend
    # runs as root, which makes git refuse every repo as "dubious ownership".
    count = int(env.get("GIT_CONFIG_COUNT") or 0)
    env[f"GIT_CONFIG_KEY_{count}"] = "safe.directory"
    env[f"GIT_CONFIG_VALUE_{count}"] = "*"
    env["GIT_CONFIG_COUNT"] = str(count + 1)
    return env


def safe_path(root: str, p: str | None) -> Path:
    base = Path(root).expanduser().resolve()
    target = (base / (p or ".")).expanduser().resolve()
    try:
        rel = target.relative_to(base)
    except ValueError:
        raise ValueError(f"path escapes project root: {p}")
    if _is_sensitive(rel):
        raise ValueError(f"sensitive path is blocked: {p}")
    return target


def rel_path(root: str, target: Path) -> str:
    try:
        rel = target.resolve().relative_to(Path(root).resolve())
    except ValueError:
        return str(target)
    return rel.as_posix() or "."


def clamp(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(4096)
        return b"\x00" in chunk
    except OSError:
        return True


def _project_type(path: Path) -> str:
    if (path / ".git").exists():
        return "git"
    if (path / "package.json").exists():
        return "node"
    if (path / "pyproject.toml").exists() or (path / "requirements.txt").exists():
        return "python"
    if (path / "Cargo.toml").exists():
        return "rust"
    if (path / "go.mod").exists():
        return "go"
    return "dir"


def list_projects(root: str) -> list[dict]:
    base = Path(root).expanduser().resolve()
    if not base.exists() or not base.is_dir():
        return []
    projects = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        projects.append({
            "name": child.name,
            "path": str(child),
            "type": _project_type(child),
            "lastModified": int(stat.st_mtime * 1000),
        })
    return projects


def list_dir(root: str, args: dict) -> dict:
    base = safe_path(root, args.get("path") or ".")
    if not base.exists() or not base.is_dir():
        return {"error": f"not a directory: {args.get('path') or '.'}"}
    depth = min(max(int(args.get("depth") or 2), 1), 4)
    entries: list[str] = []

    def walk(directory: Path, level: int):
        if len(entries) >= MAX_DIR_ENTRIES:
            return
        try:
            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return
        for child in children:
            if len(entries) >= MAX_DIR_ENTRIES:
                break
            if child.is_dir():
                if child.name in SKIP_DIRS:
                    continue
                entries.append(rel_path(root, child) + "/")
                if level < depth:
                    walk(child, level + 1)
            elif child.is_file():
                if _is_sensitive_name(child.name):
                    continue
                entries.append(rel_path(root, child))

    walk(base, 1)
    return {
        "root": str(Path(root).resolve()),
        "path": rel_path(root, base),
        "entries": entries,
        "truncated": len(entries) >= MAX_DIR_ENTRIES,
    }


def read_file(root: str, args: dict) -> dict:
    path = safe_path(root, args.get("path"))
    if not path.exists() or not path.is_file():
        return {"error": f"not a file: {args.get('path')}"}
    if path.stat().st_size > MAX_FILE_BYTES:
        return {"error": f"file too large (>{MAX_FILE_BYTES} bytes): {args.get('path')}"}
    if _is_binary(path):
        return {"error": f"binary file is not readable as text: {args.get('path')}"}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    offset = max(int(args.get("offset") or 0), 0)
    limit = min(max(int(args.get("limit") or 400), 1), 2000)
    content = "\n".join(lines[offset:offset + limit])
    truncated = offset + limit < len(lines)
    if len(content) > MAX_READ_CHARS:
        content = content[:MAX_READ_CHARS]
        truncated = True
    return {
        "path": args.get("path"),
        "offset": offset,
        "total_lines": len(lines),
        "content": content,
        "truncated": truncated,
    }


def write_file(root: str, args: dict) -> dict:
    path = safe_path(root, args.get("path"))
    content = str(args.get("content") or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": args.get("path"), "bytes": len(content.encode("utf-8"))}


def edit_file(root: str, args: dict) -> dict:
    path = safe_path(root, args.get("path"))
    if not path.exists() or not path.is_file():
        return {"error": f"not a file: {args.get('path')}"}
    old = str(args.get("old_string") or "")
    if not old:
        return {"error": "old_string is required"}
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        return {"error": "old_string not found", "path": args.get("path")}
    if count > 1 and not args.get("replace_all"):
        return {
            "error": f"old_string matched {count} times; provide more context or set replace_all=true",
            "path": args.get("path"),
        }
    new = str(args.get("new_string") or "")
    next_text = text.replace(old, new) if args.get("replace_all") else text.replace(old, new, 1)
    path.write_text(next_text, encoding="utf-8")
    return {"path": args.get("path"), "replaced": count, "bytes": len(next_text.encode("utf-8"))}


def search_text(root: str, args: dict) -> dict:
    base = safe_path(root, args.get("path") or ".")
    pattern = str(args.get("pattern") or "")
    if not pattern:
        return {"error": "pattern is required"}
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return {"error": f"invalid regex: {e}"}
    max_results = min(max(int(args.get("max_results") or 50), 1), 200)
    include = [x.strip().lower() for x in str(args.get("include") or "").split(",") if x.strip()]
    matches = []
    for current, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if len(matches) >= max_results:
                break
            if _is_sensitive_name(name):
                continue
            path = Path(current) / name
            if include and not any(str(path).lower().endswith(suffix) for suffix in include):
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES or _is_binary(path):
                    continue
            except OSError:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for index, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append({
                        "path": rel_path(root, path),
                        "line": index,
                        "text": line.strip()[:240],
                    })
                    if len(matches) >= max_results:
                        break
        if len(matches) >= max_results:
            break
    return {"matches": matches, "truncated": len(matches) >= max_results}


async def run_command(root: str, args: dict, *, allow_push: bool = False, allow_commit: bool = False,
                      identity: dict | None = None, ssh_key: str | None = None) -> dict:
    cwd = safe_path(root, args.get("cwd") or ".")
    if not cwd.exists() or not cwd.is_dir():
        return {"error": f"working directory not found: {args.get('cwd') or '.'}"}
    command = str(args.get("command") or "")
    if not command.strip():
        return {"error": "command is required"}
    timeout = min(max(int(args.get("timeout_ms") or 120000), 1000), 600000)

    is_push = re.search(r"(^|[;&|]\s*)git\s+push\b", command)
    is_commit = re.search(r"(^|[;&|]\s*)git\s+commit\b", command)
    if is_push and not allow_push:
        return {"error": "git push is not allowed by the developer profile"}
    if is_commit and not allow_commit:
        return {"error": "git commit is not allowed by the developer profile"}
    if is_push and re.search(r"--force(?!-with-lease)\b|(^|\s)-f\b", command):
        return {"error": "force push is blocked"}
    if re.search(r"(^|[\s/])\.env(?!\.example)(\s|$|[;&|])", command):
        return {"error": "sensitive file is blocked"}

    env = git_env(identity, ssh_key)

    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout / 1000)
        code = proc.returncode
        timed_out = False
    except asyncio.TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        stdout_b, stderr_b = await proc.communicate()
        code = -1
    stdout = clamp(stdout_b.decode("utf-8", errors="replace"), MAX_COMMAND_OUTPUT)
    stderr = clamp(stderr_b.decode("utf-8", errors="replace"), MAX_COMMAND_OUTPUT)
    return {"code": code, "timed_out": timed_out, "stdout": stdout, "stderr": stderr}


async def execute_tool(root: str, name: str, args: dict, *, allow_push: bool = False,
                       allow_commit: bool = False, identity: dict | None = None,
                       ssh_key: str | None = None) -> dict:
    args = args or {}
    try:
        if name == "list_dir":
            return list_dir(root, args)
        if name == "read_file":
            return read_file(root, args)
        if name == "write_file":
            return write_file(root, args)
        if name == "edit_file":
            return edit_file(root, args)
        if name == "search_text":
            return search_text(root, args)
        if name == "run_command":
            return await run_command(root, args, allow_push=allow_push, allow_commit=allow_commit,
                                     identity=identity, ssh_key=ssh_key)
        return {"error": f"unknown tool: {name}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}
