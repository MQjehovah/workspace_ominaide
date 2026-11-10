import asyncio
import shutil
from pathlib import Path

from sqlalchemy import select

from core.paths import ensure_user_workspace, projects_root
from ai.bots.models import Run
from core.database.session import async_session
from plugins.projects.backend.models import Project


def _validate_path(user_id: int, value: str) -> str:
    root = projects_root(user_id)
    path = Path(value).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"项目不在工作区内：{value}")
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
    path = _validate_path(user_id, raw_path)

    repo_url = (data.repo_url or "").strip() or None
    if data.is_git and not repo_url:
        raise ValueError("Git 项目必须填写仓库地址")

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
            is_git=data.is_git,
            repo_url=repo_url if data.is_git else None,
            default_branch=((data.default_branch or "").strip() or "master")
            if data.is_git
            else None,
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
