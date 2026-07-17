import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from plugins.workspaces.backend.models import Workspace
from plugins.workspaces.backend.schemas import WorkspaceCreate, WorkspaceUpdate
from core.minio.client import minio_client


async def create_workspace(
    db: AsyncSession, user_id: int, req: WorkspaceCreate
) -> Workspace:
    bucket = f"ws-{user_id}-{uuid.uuid4().hex[:8]}"

    if minio_client:
        try:
            if not minio_client.bucket_exists(bucket):
                minio_client.make_bucket(bucket)
        except Exception:
            pass  # MinIO unavailable, workspace still created

    workspace = Workspace(
        user_id=user_id,
        name=req.name,
        description=req.description,
        bucket=bucket,
        sync_enabled=req.sync_enabled,
    )
    db.add(workspace)
    await db.flush()
    return workspace


async def get_workspaces(
    db: AsyncSession, user_id: int
) -> list[Workspace]:
    result = await db.execute(
        select(Workspace)
        .where(Workspace.user_id == user_id)
        .order_by(Workspace.created_at.desc())
    )
    return list(result.scalars().all())


async def get_workspace(
    db: AsyncSession, user_id: int, workspace_id: int
) -> Workspace | None:
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def update_workspace(
    db: AsyncSession, user_id: int, workspace_id: int, req: WorkspaceUpdate
) -> Workspace:
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == user_id,
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise ValueError("Workspace not found")

    if req.name is not None:
        workspace.name = req.name
    if req.description is not None:
        workspace.description = req.description
    if req.sync_enabled is not None:
        workspace.sync_enabled = req.sync_enabled

    await db.flush()
    return workspace


async def delete_workspace(
    db: AsyncSession, user_id: int, workspace_id: int
):
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.user_id == user_id,
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise ValueError("Workspace not found")

    if minio_client:
        try:
            minio_client.remove_bucket(workspace.bucket)
        except Exception:
            pass

    await db.delete(workspace)
    await db.flush()
