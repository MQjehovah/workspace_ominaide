from pathlib import Path

from sqlalchemy import select

from core.config.settings import settings
from core.coding.models import CodingRun
from core.bots.models import BotRun
from core.database.session import async_session
from plugins.projects.backend.models import Project


def _normalize_path(value: str) -> str:
    return str(Path(value).expanduser().resolve())


def _validate_path(value: str) -> str:
    root = Path(settings.coding_workspace_root).expanduser().resolve()
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
    path = _validate_path(data.path)
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
            name=data.name,
            path=path,
            is_git=data.is_git,
            repo_url=data.repo_url if data.is_git else None,
            default_branch=(data.default_branch or "main") if data.is_git else None,
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
            fields["path"] = _validate_path(fields["path"])
        for key, value in fields.items():
            setattr(project, key, value)
        if not project.is_git:
            project.repo_url = None
            project.default_branch = None
        elif not project.default_branch:
            project.default_branch = "main"
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
        await db.delete(project)
        await db.commit()
        return True


async def scan_workspace(user_id: int) -> list[Project]:
    from core.coding.workspace import list_projects as scan

    found = scan(settings.coding_workspace_root)
    async with async_session() as db:
        existing = {
            p.path
            for p in (
                await db.execute(select(Project).where(Project.user_id == user_id))
            ).scalars().all()
        }
        created = []
        for item in found:
            path = _normalize_path(item["path"])
            if path in existing:
                continue
            is_git = item.get("type") == "git"
            project = Project(
                user_id=user_id,
                name=item["name"],
                path=path,
                is_git=is_git,
                default_branch="main" if is_git else None,
                description=f"从工作区扫描：{item.get('type', 'project')}",
            )
            db.add(project)
            created.append(project)
        await db.commit()
        for p in created:
            await db.refresh(p)
        return created


async def list_project_runs(
    user_id: int, project_path: str, limit: int = 50
) -> list[dict]:
    async with async_session() as db:
        rows = (
            await db.execute(
                select(BotRun, CodingRun)
                .join(CodingRun, CodingRun.run_id == BotRun.id)
                .where(
                    BotRun.user_id == user_id,
                    CodingRun.project_path == project_path,
                )
                .order_by(BotRun.id.desc())
                .limit(limit)
            )
        ).all()
        return [_run_dict(run, coding) for run, coding in rows]


async def list_all_coding_runs(user_id: int, limit: int = 20) -> list[dict]:
    async with async_session() as db:
        rows = (
            await db.execute(
                select(BotRun, CodingRun)
                .join(CodingRun, CodingRun.run_id == BotRun.id)
                .where(BotRun.user_id == user_id)
                .order_by(BotRun.id.desc())
                .limit(limit)
            )
        ).all()
        return [_run_dict(run, coding) for run, coding in rows]


def _run_dict(run: BotRun, coding: CodingRun) -> dict:
    return {
        "id": run.id,
        "status": run.status,
        "input": run.input,
        "output": run.output,
        "error": run.error,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "branch": coding.branch,
        "engine": coding.engine,
        "project_path": coding.project_path,
    }
