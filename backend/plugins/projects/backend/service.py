import asyncio
import re
import shutil
from pathlib import Path

from sqlalchemy import delete, select

from core.paths import ensure_user_workspace, projects_root
from ai.bots.models import Run
from ai.coding import workspace
from core.database.session import async_session
from plugins.projects.backend.models import Project, ProjectRepo


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


_GIT_URL = re.compile(r"^(?:https?://|ssh://|git@)[^\s]+$")


def _repo_path(value: str | None, fallback: str) -> str:
    raw = (value or fallback or "").strip().strip("/")
    if not raw:
        raise ValueError("仓库目录不能为空")
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"仓库目录必须是项目内相对路径：{raw}")
    return candidate.as_posix()


def _validate_repo_url(url: str) -> str:
    value = (url or "").strip()
    if not _GIT_URL.match(value):
        raise ValueError(f"不支持的仓库地址：{value}")
    return value


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

    requested_repos = list(getattr(data, "repos", None) or [])
    normalized: list[dict] = []
    seen_paths: set[str] = set()
    for item in requested_repos:
        repo_name = (getattr(item, "name", "") or "").strip()
        if not repo_name:
            raise ValueError("仓库名称不能为空")
        repo_path = _repo_path(getattr(item, "path", None), repo_name)
        if repo_path in seen_paths:
            raise ValueError(f"仓库目录重复：{repo_path}")
        seen_paths.add(repo_path)
        normalized.append(
            {
                "name": repo_name,
                "url": _validate_repo_url(getattr(item, "url", "")),
                "path": repo_path,
                "default_branch": (
                    (getattr(item, "default_branch", None) or "").strip()
                    or "master"
                ),
            }
        )

    repo_url = (data.repo_url or "").strip() or None
    if normalized:
        repo_url = normalized[0]["url"]
        default_branch = normalized[0]["default_branch"]
        is_git = True
    else:
        is_git = bool(data.is_git)
        default_branch = ((data.default_branch or "").strip() or "master") if is_git else None
        if is_git and not repo_url:
            raise ValueError("Git 项目必须填写仓库地址，或提供 repos 列表")

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
            is_git=is_git,
            repo_url=repo_url if is_git else None,
            default_branch=default_branch if is_git else None,
            description=data.description,
        )
        db.add(project)
        await db.flush()
        for item in normalized:
            db.add(
                ProjectRepo(
                    project_id=project.id,
                    name=item["name"],
                    url=item["url"],
                    path=item["path"],
                    default_branch=item["default_branch"],
                    status="pending",
                )
            )
        await db.commit()
        await db.refresh(project)

    return project


async def list_project_repos(project_id: int) -> list[ProjectRepo]:
    async with async_session() as db:
        return list(
            (
                await db.execute(
                    select(ProjectRepo)
                    .where(ProjectRepo.project_id == project_id)
                    .order_by(ProjectRepo.id.asc())
                )
            ).scalars().all()
        )


async def clone_project_repos(project_id: int) -> None:
    async with async_session() as db:
        repos = list(
            (
                await db.execute(
                    select(ProjectRepo)
                    .where(
                        ProjectRepo.project_id == project_id,
                        ProjectRepo.status.in_(("pending", "error", "cloning")),
                    )
                    .order_by(ProjectRepo.id.asc())
                )
            ).scalars().all()
        )
    for repo in repos:
        await clone_repo(repo.id)


async def clone_repo(repo_id: int) -> ProjectRepo | None:
    async with async_session() as db:
        repo = (
            await db.execute(select(ProjectRepo).where(ProjectRepo.id == repo_id))
        ).scalar_one_or_none()
        if repo is None:
            return None
        project = (
            await db.execute(select(Project).where(Project.id == repo.project_id))
        ).scalar_one_or_none()
        if project is None:
            return None
        root = Path(project.path).expanduser().resolve()
        target = (root / repo.path).resolve()
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
            repo.error = f"目录已存在且非空：{repo.path}"
            await db.commit()
            return repo
        repo.status = "cloning"
        repo.error = None
        await db.commit()
        url = repo.url
        branch = repo.default_branch or "master"
        repo_path = repo.path

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
                await db.execute(select(ProjectRepo).where(ProjectRepo.id == repo_id))
            ).scalar_one_or_none()
            if repo is not None:
                repo.status = "error"
                repo.error = f"克隆失败：{exc}"
                await db.commit()
                return repo
        return None

    async with async_session() as db:
        repo = (
            await db.execute(select(ProjectRepo).where(ProjectRepo.id == repo_id))
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
        if not project.is_git:
            project.repo_url = None
            project.default_branch = None
        else:
            project.repo_url = (project.repo_url or "").strip() or None
            if not project.repo_url:
                raise ValueError("Git 项目必须填写仓库地址")
            project.default_branch = (project.default_branch or "").strip() or "master"
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
            delete(ProjectRepo).where(ProjectRepo.project_id == project.id)
        )
        await db.delete(project)
        await db.commit()
        return True


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
