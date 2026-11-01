"""One-shot delivery pipeline: verify -> branch -> commit -> push.

Run after the agent loop finishes. Keeping git out of the model's hands makes
the outcome predictable: verification has to pass, work always lands on a
dedicated branch, and force-push is never used.
"""

import asyncio
import re
import time
from pathlib import Path
from typing import Awaitable, Callable

from plugins.vibecoding.backend import workspace
from plugins.vibecoding.backend.context import invalidate_context

Emit = Callable[..., Awaitable[None]]
PROTECTED_BRANCHES = {"main", "master"}


def _slug(text: str, limit: int = 32) -> str:
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    if not ascii_part:
        ascii_part = "task"
    return ascii_part[:limit].strip("-") or "task"


def _commit_message(instruction: str) -> str:
    first = " ".join((instruction or "").strip().splitlines()[:1]) or "agent changes"
    first = re.sub(r"\s+", " ", first)[:72]
    if re.search(r"新增|添加|实现|支持|增加|add|implement|support|feat", instruction or "", re.I):
        kind = "feat"
    elif re.search(r"修复|解决|错误|异常|bug|fix|broken", instruction or "", re.I):
        kind = "fix"
    elif re.search(r"重构|整理|优化|refactor|cleanup|perf", instruction or "", re.I):
        kind = "refactor"
    else:
        kind = "chore"
    return f"{kind}: {first}\n\n由 OmniAide 后端 Coding Agent 自动提交。"


def _tail(text: str, limit: int = 600) -> str:
    text = (text or "").strip()
    return text[-limit:] if len(text) > limit else text


def _github_pr_url(remote: str, branch: str, base: str) -> str | None:
    match = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", (remote or "").strip())
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    return f"https://github.com/{owner}/{repo}/compare/{base}...{branch}?expand=1"


async def _git(root: str, args: list[str], *, identity: dict | None, ssh_key: str | None,
               timeout: float = 120.0) -> tuple[int, str, str]:
    env = workspace.git_env(identity, ssh_key)
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(root),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        return -1, "", f"cannot start git: {e}"

    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.communicate()
        return -1, "", f"git {' '.join(args)} timed out after {int(timeout)}s"

    return (
        proc.returncode or 0,
        out.decode("utf-8", errors="replace").strip(),
        err.decode("utf-8", errors="replace").strip(),
    )


async def _shell(root: str, command: str, *, identity: dict | None, ssh_key: str | None,
                 timeout: float) -> tuple[int, str, str]:
    env = workspace.git_env(identity, ssh_key)
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=str(root),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.communicate()
        return -1, "", f"command timed out after {int(timeout)}s"
    return (
        proc.returncode or 0,
        out.decode("utf-8", errors="replace"),
        err.decode("utf-8", errors="replace"),
    )


async def deliver(root: str, instruction: str, *, developer: dict | None = None,
                  allow_commit: bool = True, allow_push: bool = True,
                  verify_command: str = "", branch_prefix: str = "agent/",
                  timeout_ms: int = 600_000,
                  emit: Emit | None = None) -> dict:
    """Verify, branch, commit and (optionally) push the working tree.

    Returns a summary dict; never raises for expected git/verify failures so the
    agent task can still finish and report what happened.
    """

    async def notify(stage: str, ok: bool | None, detail: str = "", **extra):
        if emit is None:
            return
        try:
            await emit(stage, ok, detail, extra)
        except Exception:
            pass

    developer = developer or {}
    identity = {
        "name": developer.get("github_username"),
        "email": developer.get("github_email"),
    }
    ssh_key = developer.get("ssh_key_path")
    base_branch = (developer.get("default_branch") or "main").strip() or "main"

    if not allow_commit:
        await notify("skipped", False, "开发者档案未授予 commit 权限")
        return {"ok": False, "skipped": True, "reason": "commit_not_allowed"}

    code, status, err = await _git(root, ["status", "--porcelain"], identity=identity, ssh_key=ssh_key)
    if code != 0:
        await notify("skipped", False, f"不是可用的 git 仓库：{_tail(err, 200)}")
        return {"ok": False, "skipped": True, "reason": "not_a_repo"}
    if not status.strip():
        await notify("skipped", True, "没有文件改动，无需交付")
        return {"ok": True, "skipped": True, "reason": "no_changes"}

    verify_result = None
    if verify_command.strip():
        await notify("verify", None, verify_command.strip())
        v_code, v_out, v_err = await _shell(
            root, verify_command.strip(), identity=identity, ssh_key=ssh_key,
            timeout=min(max(timeout_ms, 30_000), 1_800_000) / 1000,
        )
        verify_result = {"command": verify_command.strip(), "code": v_code}
        if v_code != 0:
            detail = _tail(v_err or v_out)
            await notify("verify_failed", False, detail or f"退出码 {v_code}")
            return {"ok": False, "stage": "verify", "verify": verify_result, "detail": detail}
        await notify("verify_passed", True, "验证通过")

    code, current, _ = await _git(root, ["rev-parse", "--abbrev-ref", "HEAD"],
                                  identity=identity, ssh_key=ssh_key)
    current = current if code == 0 else ""

    if current.startswith(branch_prefix) and current not in PROTECTED_BRANCHES:
        branch = current
    else:
        branch = f"{branch_prefix}{_slug(instruction)}-{time.strftime('%m%d%H%M')}"
        code, _, err = await _git(root, ["checkout", "-b", branch], identity=identity, ssh_key=ssh_key)
        if code != 0:
            await notify("branch_failed", False, _tail(err))
            return {"ok": False, "stage": "branch", "detail": _tail(err)}
        await notify("branch", True, branch)

    code, _, err = await _git(root, ["add", "-A"], identity=identity, ssh_key=ssh_key)
    if code != 0:
        await notify("stage_failed", False, _tail(err))
        return {"ok": False, "stage": "stage", "detail": _tail(err)}

    _, staged_text, _ = await _git(root, ["diff", "--cached", "--name-only"],
                                   identity=identity, ssh_key=ssh_key)
    staged = [line for line in staged_text.splitlines() if line.strip()]
    blocked = [path for path in staged if workspace.is_sensitive_path(path)]
    if blocked:
        await _git(root, ["reset", "-q", "--", *blocked], identity=identity, ssh_key=ssh_key)
        await notify("sensitive_skipped", True, "已排除敏感文件：" + ", ".join(blocked[:10]))
        staged = [path for path in staged if path not in blocked]

    if not staged:
        await notify("skipped", True, "没有可提交的改动（仅敏感文件）")
        return {"ok": True, "skipped": True, "reason": "only_sensitive", "branch": branch}

    code, out, err = await _git(root, ["commit", "-m", _commit_message(instruction)],
                                identity=identity, ssh_key=ssh_key)
    if code != 0:
        if "nothing to commit" in (out + err):
            await notify("skipped", True, "没有可提交的改动")
            return {"ok": True, "skipped": True, "reason": "no_changes", "branch": branch}
        await notify("commit_failed", False, _tail(err or out))
        return {"ok": False, "stage": "commit", "detail": _tail(err or out), "branch": branch}

    _, sha, _ = await _git(root, ["rev-parse", "--short", "HEAD"], identity=identity, ssh_key=ssh_key)
    await notify("commit", True, f"{sha} · {len(staged)} 个文件", sha=sha, files=len(staged))

    summary = {
        "ok": True,
        "branch": branch,
        "commit": sha,
        "files": len(staged),
        "verify": verify_result,
        "pushed": False,
        "pr_url": None,
    }

    if not allow_push:
        await notify("push_skipped", False, "开发者档案未授予 push 权限")
        invalidate_context(root)
        return summary

    code, out, err = await _git(root, ["push", "-u", "origin", branch],
                                identity=identity, ssh_key=ssh_key, timeout=180)
    if code != 0:
        await notify("push_failed", False, _tail(err or out))
        summary["push_error"] = _tail(err or out)
        invalidate_context(root)
        return summary

    _, remote, _ = await _git(root, ["remote", "get-url", "origin"], identity=identity, ssh_key=ssh_key)
    pr_url = _github_pr_url(remote, branch, base_branch)
    summary["pushed"] = True
    summary["pr_url"] = pr_url
    await notify("push", True, branch, branch=branch)
    if pr_url:
        await notify("pr", True, pr_url, url=pr_url)
    invalidate_context(root)
    return summary
