import shutil
import tempfile
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import get_db
from core.plugin.schemas import PluginInfo, PluginToggleResponse
from core.plugin import registry as plugin_registry
from core.plugin.models import PluginRegistry

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


@router.post("/install")
async def install_plugin(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Install a plugin from a zip archive."""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        manifest = plugin_registry.install_plugin_from_zip(tmp_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)

    name = manifest["name"]
    result = await db.execute(
        select(PluginRegistry).where(PluginRegistry.name == name)
    )
    record = result.scalar_one_or_none()
    if record is None:
        record = PluginRegistry(
            name=name,
            version=manifest.get("version", "0.0.0"),
            title=manifest.get("title", name),
            description=manifest.get("description", ""),
            icon=manifest.get("icon", ""),
            enabled=True,
            manifest=manifest,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

    return PluginInfo.model_validate(record)


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
