import asyncio
import re
import shutil
from pathlib import Path

from sqlalchemy import delete, select

from core.paths import ensure_user_workspace, projects_root
from ai.bots.models import Run
from ai.coding import workspace
from core.database.session import async_session
from plugins.projects.backend.models import GitProject, Project

_GIT_URL = re.compile(r"^(?:https?://|ssh://|git@)[^\s]+$")


def _validate_path(user_id: int, value: str, *, create: bool = False) -> str:
    root = projects_root(user_id)
    path = Path(value).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"项目不在工作区内：{value}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.is_dir():
        raise ValueError(f"项目目录不存在：{value}")
    return str(path)


def _git_project_path(value: str | None, fallback: str | None = None) -> str:
    raw = (value or fallback or "").strip().strip("/")
    if not raw:
        raise ValueError("Git 项目相对路径不能为空")
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Git 项目必须是项目内相对路径：{raw}")
    return candidate.as_posix()


def _validate_git_url(url: str) -> str:
    value = (url or "").strip()
    if not _GIT_URL.match(value):
        raise ValueError(f"不支持的仓库地址：{value}")
    return value


async def list_projects(user_id: int) -> list[Project]:
    async with async_session() as db:
        return list(
            (
                await db.execute(
                    select(Project)
                    .where(Project.user_id == user_id, Project.status == "active")
                    .order_by(Project.name.asc())
                )
            ).scalars().all()
        )


async def get_project(user_id: int, project_id: int) -> Project | None:
    async with async_session() as db:
        return (
            await db.execute(
                select(Project).where(
                    Project.id == project_id, Project.user_id == user_id
                )
            )
        ).scalar_one_or_none()


async def create_project(user_id: int, data) -> Project:
    name = (data.name or "").strip()
    if not name:
        raise ValueError("项目名称不能为空")
    raw_path = (data.path or "").strip()
    if not raw_path:
        ensure_user_workspace(user_id)
        root = projects_root(user_id)
        root.mkdir(parents=True, exist_ok=True)
        target = root / name
        target.mkdir(parents=True, exist_ok=True)
        raw_path = str(target)
    path = _validate_path(user_id, raw_path, create=True)

    async with async_session() as db:
        existing = (
            await db.execute(
                select(Project).where(
                    Project.user_id == user_id, Project.path == path
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise ValueError("该项目路径已存在")
        project = Project(
            user_id=user_id,
            name=name,
            path=path,
            description=data.description,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        return project


async def update_project(user_id: int, project_id: int, data) -> Project | None:
    async with async_session() as db:
        project = (
            await db.execute(
                select(Project).where(
                    Project.id == project_id, Project.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if project is None:
            return None
        fields = data.model_dump(exclude_unset=True)
        if "path" in fields and fields["path"]:
            fields["path"] = _validate_path(user_id, fields["path"])
        for key, value in fields.items():
            setattr(project, key, value)
        await db.commit()
        await db.refresh(project)
        return project


async def delete_project(user_id: int, project_id: int) -> bool:
    async with async_session() as db:
        project = (
            await db.execute(
                select(Project).where(
                    Project.id == project_id, Project.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if project is None:
            return False

        target = Path(project.path).expanduser().resolve()
        root = projects_root(user_id)
        if target == root or root not in target.parents:
            raise ValueError(f"拒绝删除工作区外的目录：{project.path}")
        if target.exists():
            await asyncio.to_thread(shutil.rmtree, target)

        await db.execute(
            delete(GitProject).where(GitProject.project_id == project.id)
        )
        await db.delete(project)
        await db.commit()
        return True


async def list_git_projects(project_id: int) -> list[GitProject]:
    async with async_session() as db:
        return list(
            (
                await db.execute(
                    select(GitProject)
                    .where(GitProject.project_id == project_id)
                    .order_by(GitProject.id.asc())
                )
            ).scalars().all()
        )


async def get_git_project(
    user_id: int, project_id: int, git_project_id: int
) -> GitProject | None:
    project = await get_project(user_id, project_id)
    if project is None:
        return None
    async with async_session() as db:
        return (
            await db.execute(
                select(GitProject).where(
                    GitProject.id == git_project_id,
                    GitProject.project_id == project_id,
                )
            )
        ).scalar_one_or_none()


async def add_git_project(user_id: int, project_id: int, data) -> GitProject:
    project = await get_project(user_id, project_id)
    if project is None:
        raise ValueError("项目不存在")
    name = (data.name or "").strip()
    if not name:
        raise ValueError("Git 项目名称不能为空")
    relative_path = _git_project_path(
        getattr(data, "relative_path", None), name
    )
    url = _validate_git_url(data.url)
    branch = (getattr(data, "default_branch", None) or "").strip() or "master"

    async with async_session() as db:
        existing = (
            await db.execute(
                select(GitProject).where(
                    GitProject.project_id == project_id,
                    GitProject.relative_path == relative_path,
                )
            )
        ).scalar_one_or_none()
        if existing:
            raise ValueError("该相对路径已存在 Git 项目")
        git_project = GitProject(
            project_id=project_id,
            name=name,
            url=url,
            relative_path=relative_path,
            default_branch=branch,
            status="pending",
        )
        db.add(git_project)
        await db.commit()
        await db.refresh(git_project)
        return git_project


async def update_git_project(
    user_id: int, project_id: int, git_project_id: int, data
) -> GitProject | None:
    git_project = await get_git_project(user_id, project_id, git_project_id)
    if git_project is None:
        return None
    fields = data.model_dump(exclude_unset=True)
    if "relative_path" in fields and fields["relative_path"]:
        fields["relative_path"] = _git_project_path(fields["relative_path"])
    if "url" in fields and fields["url"]:
        fields["url"] = _validate_git_url(fields["url"])
    if "default_branch" in fields:
        fields["default_branch"] = (fields["default_branch"] or "").strip() or "master"
    async with async_session() as db:
        row = (
            await db.execute(select(GitProject).where(GitProject.id == git_project.id))
        ).scalar_one()
        for key, value in fields.items():
            setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        return row


async def delete_git_project(
    user_id: int, project_id: int, git_project_id: int
) -> bool:
    git_project = await get_git_project(user_id, project_id, git_project_id)
    if git_project is None:
        return False
    async with async_session() as db:
        row = (
            await db.execute(select(GitProject).where(GitProject.id == git_project.id))
        ).scalar_one()
        await db.delete(row)
        await db.commit()
        return True


async def clone_project_git_projects(project_id: int) -> None:
    async with async_session() as db:
        repos = list(
            (
                await db.execute(
                    select(GitProject)
                    .where(
                        GitProject.project_id == project_id,
                        GitProject.status.in_(("pending", "error", "cloning")),
                    )
                    .order_by(GitProject.id.asc())
                )
            ).scalars().all()
        )
    for repo in repos:
        await clone_git_project(repo.id)


async def clone_git_project(git_project_id: int) -> GitProject | None:
    async with async_session() as db:
        repo = (
            await db.execute(
                select(GitProject).where(GitProject.id == git_project_id)
            )
        ).scalar_one_or_none()
        if repo is None:
            return None
        project = (
            await db.execute(select(Project).where(Project.id == repo.project_id))
        ).scalar_one_or_none()
        if project is None:
            return None
        root = Path(project.path).expanduser().resolve()
        target = (root / repo.relative_path).resolve()
        if target != root and root not in target.parents:
            repo.status = "error"
            repo.error = "仓库目录越界"
            await db.commit()
            return repo
        if (target / ".git").exists():
            repo.status = "cloned"
            repo.error = None
            await db.commit()
            return repo
        if target.exists() and any(target.iterdir()):
            repo.status = "error"
            repo.error = f"目录已存在且非空：{repo.relative_path}"
            await db.commit()
            return repo
        repo.status = "cloning"
        repo.error = None
        await db.commit()
        url = repo.url
        branch = repo.default_branch or "master"

    target.parent.mkdir(parents=True, exist_ok=True)
    command = ["git", "clone", "--branch", branch, url, str(target)]
    env = workspace.git_env()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
    except (OSError, asyncio.TimeoutError) as exc:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        async with async_session() as db:
            repo = (
                await db.execute(
                    select(GitProject).where(GitProject.id == git_project_id)
                )
            ).scalar_one_or_none()
            if repo is not None:
                repo.status = "error"
                repo.error = f"克隆失败：{exc}"
                await db.commit()
                return repo
        return None

    async with async_session() as db:
        repo = (
            await db.execute(
                select(GitProject).where(GitProject.id == git_project_id)
            )
        ).scalar_one_or_none()
        if repo is not None:
            if (proc.returncode or 0) == 0:
                repo.status = "cloned"
                repo.error = None
            else:
                repo.status = "error"
                text = (stderr or stdout).decode("utf-8", errors="replace").strip()
                repo.error = text[-4000:] or f"git clone exited with {proc.returncode}"
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
            await db.commit()
            return repo
    return None


async def list_project_runs(
    user_id: int, project_path: str, limit: int = 50
) -> list[dict]:
    async with async_session() as db:
        rows = list(
            (
                await db.execute(
                    select(Run)
                    .where(Run.user_id == user_id, Run.trigger == "coding")
                    .order_by(Run.id.desc())
                    .limit(max(limit * 3, 100))
                )
            )
            .scalars()
            .all()
        )
        selected = [
            run for run in rows
            if str((run.meta or {}).get("project_path") or "") == project_path
        ][:limit]
        return [_run_dict(run) for run in selected]


async def list_all_coding_runs(user_id: int, limit: int = 20) -> list[dict]:
    async with async_session() as db:
        rows = list(
            (
                await db.execute(
                    select(Run)
                    .where(Run.user_id == user_id, Run.trigger == "coding")
                    .order_by(Run.id.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [_run_dict(run) for run in rows]


def _run_dict(run: Run) -> dict:
    meta = run.meta or {}
    return {
        "id": run.id,
        "session_id": run.session_id,
        "status": run.status,
        "input": run.input,
        "output": run.output,
        "error": run.error,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "branch": meta.get("branch"),
        "engine": run.agent or meta.get("engine"),
        "project_path": meta.get("project_path"),
    }
