"""Project snapshot injected into the agent system prompt.

The agent used to spend its first turns on `list_dir` + `read_file` just to
learn what the repository looks like. Building this snapshot up front removes
those turns and makes edits land on the right files much more often.

Kept deliberately cheap: one directory listing, a few small docs and three git
commands, cached per project for a short TTL.
"""

import asyncio
import json
import re
import time
from pathlib import Path

from ai.coding import workspace
from ai.coding.workspace import list_dir

DOC_FILES = ("AGENTS.md", "CLAUDE.md", "README.md", "README.zh-CN.md", "CONTRIBUTING.md")
DOC_CHARS = 1400
CACHE_TTL_SECONDS = 120.0

_CACHE: dict[str, tuple[float, str]] = {}


async def _git(root: str, *args: str, timeout: float = 5.0) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(root),
            env=workspace.git_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return out.decode("utf-8", errors="replace").strip()
    except (OSError, asyncio.TimeoutError):
        return ""


def _repo_dirs(base: Path) -> list[Path]:
    try:
        children = sorted(base.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return []
    return [
        child
        for child in children
        if child.is_dir() and (child / ".git").exists()
    ]


def _detected_commands(root: Path) -> list[str]:
    hints: list[str] = []

    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
            scripts = data.get("scripts") or {}
            for name in list(scripts)[:8]:
                hints.append(f"npm run {name}")
        except (OSError, ValueError):
            pass
        if (root / "pnpm-lock.yaml").exists():
            hints = [h.replace("npm run", "pnpm") for h in hints]

    if (root / "pyproject.toml").is_file() or (root / "pytest.ini").is_file() \
            or (root / "requirements.txt").is_file() or (root / "setup.py").is_file():
        hints.append("pytest -q")
        if (root / "ruff.toml").is_file() or (root / "pyproject.toml").is_file():
            hints.append("ruff check .")

    makefile = root / "Makefile"
    if makefile.is_file():
        try:
            text = makefile.read_text(encoding="utf-8", errors="replace")
            targets = re.findall(r"^([A-Za-z0-9_.-]+):(?!=)", text, flags=re.MULTILINE)
            for target in targets[:5]:
                if target not in ("all", ".PHONY"):
                    hints.append(f"make {target}")
        except OSError:
            pass

    if (root / "Cargo.toml").is_file():
        hints.append("cargo test")
    if (root / "go.mod").is_file():
        hints.append("go test ./...")

    # De-duplicate while keeping order.
    return list(dict.fromkeys(hints))


async def build_project_context(root: str, max_chars: int = 12000) -> str:
    """Return a compact, human-readable snapshot of the project."""
    key = str(Path(root).resolve())
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    base = Path(root)
    parts: list[str] = []

    docs: list[str] = []
    for name in DOC_FILES:
        path = base / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            docs.append(f"--- {name}（节选）---\n{text[:DOC_CHARS]}")
    if docs:
        parts.append("项目文档：\n" + "\n\n".join(docs))

    tree = list_dir(root, {"path": ".", "depth": 2})
    entries = tree.get("entries") or []
    if entries:
        shown = entries[:220]
        suffix = "（已截断）" if len(entries) > len(shown) or tree.get("truncated") else ""
        parts.append("目录结构（深度 2）：\n" + "\n".join(shown) + suffix)

    repos = _repo_dirs(base)
    if repos:
        parts.append(
            "这是多仓库工作区，包含：\n"
            + "\n".join(f"- {repo.name}/" for repo in repos)
        )
        for repo in repos[:8]:
            branch = await _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
            status = await _git(repo, "status", "--short")
            history = await _git(repo, "log", "--oneline", "-5")
            lines = [f"### {repo.name}/"]
            if branch and branch != "HEAD":
                lines.append(f"当前分支：{branch}")
            if history:
                lines.append("最近提交：\n" + history)
            if status:
                status_lines = status.splitlines()
                if len(status_lines) > 20:
                    status_lines = status_lines[:20] + ["...（更多未显示）"]
                lines.append("未提交改动：\n" + "\n".join(status_lines))
            else:
                lines.append("未提交改动：无")
            parts.append("\n".join(lines))

        command_lines: list[str] = []
        for repo in repos[:8]:
            for command in _detected_commands(repo):
                command_lines.append(f"- (cd {repo.name} && {command})")
        if command_lines:
            parts.append("可用验证命令：\n" + "\n".join(command_lines))
    else:
        branch = await _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        status = await _git(root, "status", "--short")
        history = await _git(root, "log", "--oneline", "-8")
        git_lines = []
        if branch and branch != "HEAD":
            git_lines.append(f"当前分支：{branch}")
        if history:
            git_lines.append("最近提交：\n" + history)
        if status:
            status_lines = status.splitlines()
            if len(status_lines) > 40:
                status_lines = status_lines[:40] + ["...（更多未显示）"]
            git_lines.append("未提交改动：\n" + "\n".join(status_lines))
        else:
            git_lines.append("未提交改动：无")
        if git_lines:
            parts.append("Git 状态：\n" + "\n".join(git_lines))

        commands = _detected_commands(base)
        if commands:
            parts.append("可用验证命令：\n" + "\n".join(f"- {c}" for c in commands))

    text = "\n\n".join(parts)[:max_chars]
    _CACHE[key] = (time.time(), text)
    return text


def invalidate_context(root: str) -> None:
    _CACHE.pop(str(Path(root).resolve()), None)
