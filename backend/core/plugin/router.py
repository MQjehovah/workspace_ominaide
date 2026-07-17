from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.plugin.schemas import PluginInfo, PluginToggleResponse
from core.plugin import registry as plugin_registry

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("", response_model=list[PluginInfo])
async def list_plugins(db: AsyncSession = Depends(get_db)):
    plugins = await plugin_registry.get_plugins(db)
    return [PluginInfo.model_validate(p) for p in plugins]


@router.post("/{name}/toggle", response_model=PluginToggleResponse)
async def toggle_plugin(name: str, db: AsyncSession = Depends(get_db)):
    try:
        record = await plugin_registry.toggle_plugin(db, name)
        return PluginToggleResponse(name=record.name, enabled=record.enabled)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{name}")
async def uninstall_plugin(name: str, db: AsyncSession = Depends(get_db)):
    from main import app
    try:
        await plugin_registry.uninstall_plugin(db, app, name)
        return {"message": f"Plugin {name} uninstalled"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
