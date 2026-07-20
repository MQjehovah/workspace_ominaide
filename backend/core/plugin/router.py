from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.plugin.schemas import PluginInfo, PluginToggleResponse
from core.plugin import registry as plugin_registry

PLUGINS_DIR = Path(__file__).resolve().parent.parent.parent / "plugins"

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


@router.get("/{name}/frontend/{file_path:path}")
async def serve_plugin_frontend(name: str, file_path: str = "index.html"):
    """Serve built plugin frontend assets."""
    plugin_dir = PLUGINS_DIR / name
    frontend_dir = plugin_dir / "frontend" / "dist"
    if not frontend_dir.exists():
        frontend_dir = plugin_dir / "dist"
    target = frontend_dir / file_path
    if not target.exists() or not target.is_relative_to(frontend_dir):
        target = frontend_dir / "index.html"
    if target.exists():
        return FileResponse(str(target))
    raise HTTPException(status_code=404, detail="Frontend not found")


@router.delete("/{name}")
async def uninstall_plugin(name: str, db: AsyncSession = Depends(get_db)):
    from main import app
    try:
        await plugin_registry.uninstall_plugin(db, app, name)
        return {"message": f"Plugin {name} uninstalled"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
