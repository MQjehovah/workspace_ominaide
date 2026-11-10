import asyncio
import glob as globlib
import os
import re
import shlex
import shutil
import signal
from pathlib import Path

from core.config.settings import settings

try:  # POSIX only; Windows dev machines fall back to running as the current user
    import grp
    import pwd
except ImportError:  # pragma: no cover
    grp = None
    pwd = None

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
    """Environment for trusted git subprocesses: commit identity + SSH deploy key."""
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


def _euid() -> int:
    return os.geteuid() if hasattr(os, "geteuid") else -1


def sandbox_identity() -> tuple[str, str] | None:
    """(user, group) used to run untrusted repo commands, or None if unavailable."""
    if not settings.coding_sandbox_enabled or _euid() != 0 or pwd is None:
        return None
    try:
        entry = pwd.getpwnam(settings.coding_sandbox_user)
    except KeyError:
        return None
    group = grp.getgrgid(entry.pw_gid).gr_name if grp else str(entry.pw_gid)
    return entry.pw_name, group


def sandbox_env(identity: dict | None = None) -> dict:
    """Minimal environment for model-driven commands.

    Starts from an empty dict on purpose: the backend process holds the LLM key,
    database URL, JWT secrets and MinIO credentials, and none of them may leak
    into a shell that a repository could influence.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin"),
        "HOME": settings.coding_sandbox_home,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "TMPDIR": "/tmp",
        "TERM": "dumb",
        "PAGER": "cat",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
        "PYTHONUNBUFFERED": "1",
        "GIT_CONFIG_KEY_0": "safe.directory",
        "GIT_CONFIG_VALUE_0": "*",
        "GIT_CONFIG_COUNT": "1",
    }
    if identity:
        if identity.get("name"):
            env["GIT_AUTHOR_NAME"] = identity["name"]
            env["GIT_COMMITTER_NAME"] = identity["name"]
        if identity.get("email"):
            env["GIT_AUTHOR_EMAIL"] = identity["email"]
            env["GIT_COMMITTER_EMAIL"] = identity["email"]
    return env


_GIT_WRAPPERS = {"env", "sudo", "nohup", "time", "command", "exec", "stdbuf", "nice", "xargs"}
_GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_RAW_PUSH = re.compile(r"(?:\$\(|`)[^)`]{0,120}?\bgit\b[^)`]{0,80}?\bpush\b")
_RAW_COMMIT = re.compile(r"(?:\$\(|`)[^)`]{0,120}?\bgit\b[^)`]{0,80}?\bcommit\b")
_FORCE_PUSH = re.compile(
    r"--force(?:-with-lease)?\b|(?:^|\s)-f\b|--mirror\b|--delete\b|(?:^|\s)\+[^\s]+"
)
_PROTECTED_REF = re.compile(r"(?:^|[\s:/])(?:main|master)(?:$|\s)")


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def git_invocations(command: str) -> list[list[str]]:
    """Return `[subcommand, *args]` for every git call, including nested shells.

    Handles `git -C dir push`, `git -c k=v push`, `sh -c "git push"`, `sudo git`
    and `env FOO=1 git`, which the previous regex gate let through.
    """
    results: list[list[str]] = []

    def scan(tokens: list[str], depth: int = 0) -> None:
        if depth > 3:
            return
        index = 0
        while index < len(tokens):
            base = os.path.basename(tokens[index]).lower()
            if base in ("sh", "bash", "zsh", "dash", "ksh"):
                probe = index + 1
                while probe < len(tokens):
                    token = tokens[probe]
                    if token.startswith("-") and not token.startswith("--") and "c" in token[1:]:
                        if probe + 1 < len(tokens):
                            scan(_split_command(tokens[probe + 1]), depth + 1)
                        break
                    if not token.startswith("-"):
                        break
                    probe += 1
                index = probe + 1
                continue
            if base in _GIT_WRAPPERS:
                index += 1
                while index < len(tokens) and (
                    tokens[index].startswith("-")
                    or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[index])
                ):
                    index += 1
                continue
            if base == "git":
                probe = index + 1
                while probe < len(tokens) and tokens[probe].startswith("-"):
                    probe += 2 if tokens[probe] in _GIT_OPTS_WITH_VALUE else 1
                if probe < len(tokens):
                    results.append([tokens[probe], *tokens[probe + 1:]])
                index = probe + 1
                continue
            index += 1

    scan(_split_command(command))
    return results


def git_policy_violation(command: str, *, allow_commit: bool, allow_push: bool) -> str | None:
    """Structured git gate. Returns an error string when the command must not run."""
    if re.search(r"(^|\s)-c\s+alias\.[^\s=]+=", command):
        return "git alias overrides are blocked"
    invocations = git_invocations(command)
    subcommands = {item[0] for item in invocations if item}
    is_push = "push" in subcommands or bool(_RAW_PUSH.search(command))
    is_commit = "commit" in subcommands or bool(_RAW_COMMIT.search(command))

    if is_push:
        if not allow_push:
            return "git push is not allowed by the developer profile"
        if _FORCE_PUSH.search(command):
            return "force push / destructive push is blocked"
        if _PROTECTED_REF.search(command):
            return "pushing main/master directly is blocked; use a feature branch"
    if is_commit and not allow_commit:
        return "git commit is not allowed by the developer profile"
    return None


def contains_sensitive_reference(command: str) -> bool:
    """Block commands that name .env / key files, not just plain `cat .env`."""
    for token in _split_command(command):
        if ".env.example" in token:
            continue
        if re.search(r"(^|[/\\=:\"'\s])\.env(?:$|[.\s\"'=:])", token):
            return True
        if re.search(r"(^|[/\\])(id_rsa|id_ed25519|id_dsa|id_ecdsa|\.ssh)(?:$|[/\\\s])", token):
            return True
    return False



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


def _hand_to_sandbox(*paths: Path) -> None:
    """Give root-written files back to the sandbox user so later commands can edit them."""
    if _euid() != 0 or pwd is None:
        return
    try:
        entry = pwd.getpwnam(settings.coding_sandbox_user)
    except KeyError:
        return
    if entry.pw_uid == 0:
        return
    for path in paths:
        try:
            os.chown(path, entry.pw_uid, entry.pw_gid, follow_symlinks=False)
        except (OSError, NotImplementedError):
            pass


def write_file(root: str, args: dict) -> dict:
    path = safe_path(root, args.get("path"))
    content = str(args.get("content") or "")
    created: list[Path] = []
    probe = path.parent
    while not probe.exists() and probe != probe.parent:
        created.append(probe)
        probe = probe.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _hand_to_sandbox(path, *reversed(created))
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
    _hand_to_sandbox(path)
    return {"path": args.get("path"), "replaced": count, "bytes": len(next_text.encode("utf-8"))}


def glob_files(root: str, args: dict) -> dict:
    pattern = str(args.get("pattern") or "").strip()
    if not pattern:
        return {"error": "pattern is required"}
    if ".." in Path(pattern).parts:
        return {"error": "pattern must stay inside the project"}
    base = safe_path(root, args.get("path") or ".")
    if not base.is_dir():
        return {"error": f"not a directory: {args.get('path') or '.'}"}
    try:
        max_results = min(max(int(args.get("max_results") or 200), 1), 1000)
    except (TypeError, ValueError):
        max_results = 200
    root_path = Path(root).resolve()
    matches: list[str] = []
    truncated = False
    for raw in globlib.iglob(str(base / pattern), recursive=True):
        path = Path(raw)
        try:
            rel = path.resolve().relative_to(root_path)
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if _is_sensitive(rel):
            continue
        if not path.is_file():
            continue
        matches.append(rel.as_posix())
        if len(matches) >= max_results:
            truncated = True
            break
    return {"pattern": pattern, "path": rel_path(root, base), "matches": matches, "truncated": truncated}


def apply_patch(root: str, args: dict) -> dict:
    changes = args.get("changes")
    if not isinstance(changes, list) or not changes:
        return {"error": "changes must be a non-empty list"}
    if len(changes) > 100:
        return {"error": "too many changes (max 100)"}
    buffers: dict[Path, str] = {}
    touched: list[str] = []
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            return {"error": f"change #{index + 1} must be an object"}
        path = safe_path(root, change.get("path"))
        if not path.exists() or not path.is_file():
            return {"error": f"change #{index + 1}: file not found: {change.get('path')}"}
        old = str(change.get("old_string") or "")
        if not old:
            return {"error": f"change #{index + 1}: old_string is required"}
        text = buffers.get(path)
        if text is None:
            text = path.read_text(encoding="utf-8")
        count = text.count(old)
        if count == 0:
            return {"error": f"change #{index + 1}: old_string not found", "path": change.get("path")}
        replace_all = bool(change.get("replace_all"))
        if count > 1 and not replace_all:
            return {
                "error": f"change #{index + 1}: old_string matched {count} times",
                "path": change.get("path"),
            }
        new = str(change.get("new_string") or "")
        buffers[path] = text.replace(old, new) if replace_all else text.replace(old, new, 1)
        name = rel_path(root, path)
        if name not in touched:
            touched.append(name)
    for path, text in buffers.items():
        path.write_text(text, encoding="utf-8")
        _hand_to_sandbox(path)
    return {"files": touched, "changes": len(changes), "bytes": sum(len(t.encode("utf-8")) for t in buffers.values())}


def delete_file(root: str, args: dict) -> dict:
    path = safe_path(root, args.get("path"))
    if not path.exists():
        return {"error": f"file not found: {args.get('path')}"}
    if path.is_dir():
        return {"error": "delete_file only removes files; directories are not supported"}
    path.unlink()
    return {"path": args.get("path"), "deleted": True}


def move_file(root: str, args: dict) -> dict:
    source = safe_path(root, args.get("source") or args.get("from"))
    target = safe_path(root, args.get("target") or args.get("to"))
    if not source.exists():
        return {"error": f"source not found: {args.get('source') or args.get('from')}"}
    if source.is_dir():
        return {"error": "move_file only moves files; directories are not supported"}
    if target.exists():
        return {"error": f"target already exists: {args.get('target') or args.get('to')}"}
    created: list[Path] = []
    probe = target.parent
    while not probe.exists() and probe != probe.parent:
        created.append(probe)
        probe = probe.parent
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    _hand_to_sandbox(target, *reversed(created))
    return {
        "source": rel_path(root, source),
        "target": rel_path(root, target),
        "moved": True,
    }


async def git_diff(root: str, args: dict) -> dict:
    command = [
        "git",
        "-c", "core.fsmonitor=false",
        "--no-pager", "diff", "--no-color",
        "--no-ext-diff", "--no-textconv",
    ]
    if bool(args.get("staged")):
        command.append("--cached")
    if bool(args.get("stat")):
        command.append("--stat")
    path_arg = args.get("path")
    if path_arg:
        target = safe_path(root, path_arg)
        command.extend(["--", rel_path(root, target)])
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(root),
            env=git_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
    except (OSError, asyncio.TimeoutError) as exc:
        return {"error": str(exc)}
    text = out.decode("utf-8", errors="replace")
    return {
        "code": proc.returncode or 0,
        "diff": clamp(text, MAX_COMMAND_OUTPUT),
        "stderr": clamp(err.decode("utf-8", errors="replace"), 4000),
        "empty": not text.strip(),
    }


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

    violation = git_policy_violation(command, allow_commit=allow_commit, allow_push=allow_push)
    if violation:
        return {"error": violation}
    if contains_sensitive_reference(command):
        return {"error": "sensitive file (.env / key) is blocked"}

    sandbox = sandbox_identity()
    if sandbox is None and settings.coding_sandbox_enabled and _euid() == 0:
        # Fail closed: silently falling back to root would defeat the sandbox.
        return {"error": f"sandbox user '{settings.coding_sandbox_user}' is unavailable; "
                         "refusing to run repository commands as root"}
    if sandbox:
        env = sandbox_env(identity)
        # extra_groups=[] clears the root supplementary groups inherited from
        # the backend process; without it the child keeps gid 0.
        # uvloop's subprocess implementation rejects user/group/extra_groups,
        # so drop privileges with setpriv before exec instead.
        setpriv = shutil.which("setpriv")
        if not setpriv or pwd is None or grp is None:
            return {"error": "setpriv is unavailable; refusing to run repository commands as root"}
        try:
            user_entry = pwd.getpwnam(sandbox[0])
            group_entry = grp.getgrnam(sandbox[1])
        except KeyError:
            return {"error": f"sandbox identity unavailable: {sandbox[0]}:{sandbox[1]}"}
        proc = await asyncio.create_subprocess_exec(
            setpriv,
            "--reuid", str(user_entry.pw_uid),
            "--regid", str(group_entry.gr_gid),
            "--clear-groups",
            "--",
            "/bin/sh", "-c", command,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    else:
        env = git_env(identity, ssh_key)
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # own process group so a timeout kills children too
        )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout / 1000)
        code = proc.returncode
        timed_out = False
    except asyncio.TimeoutError:
        timed_out = True
        try:
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        stdout_b, stderr_b = await proc.communicate()
        code = -1
    stdout = clamp(stdout_b.decode("utf-8", errors="replace"), MAX_COMMAND_OUTPUT)
    stderr = clamp(stderr_b.decode("utf-8", errors="replace"), MAX_COMMAND_OUTPUT)
    return {
        "code": code,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "sandbox": sandbox[0] if sandbox else None,
    }


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
        if name == "glob":
            return glob_files(root, args)
        if name == "apply_patch":
            return apply_patch(root, args)
        if name == "delete_file":
            return delete_file(root, args)
        if name == "move_file":
            return move_file(root, args)
        if name == "git_diff":
            return await git_diff(root, args)
        if name == "run_command":
            return await run_command(root, args, allow_push=allow_push, allow_commit=allow_commit,
                                     identity=identity, ssh_key=ssh_key)
        return {"error": f"unknown tool: {name}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}
