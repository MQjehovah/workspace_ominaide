import shutil
import tempfile
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.database.session import get_db
from core.plugin.schemas import PluginInfo, PluginToggleResponse
from core.plugin import registry as plugin_registry
from core.plugin.models import PluginRegistry
from core.plugin.distributor import extract_plugin_zip, get_plugin_frontend_dir, get_plugin_main_path

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
    """Install a plugin from a zip archive. Supports both unified (manifest.json)
    and legacy (package.json) formats."""
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

    name = manifest.get("id") or manifest.get("name", "unknown")
    result = await db.execute(
        select(PluginRegistry).where(PluginRegistry.name == name)
    )
    record = result.scalar_one_or_none()
    if record is None:
        record = PluginRegistry(
            name=name,
            version=manifest.get("version", "0.0.0"),
            title=manifest.get("displayName", name),
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
    """Serve built plugin frontend assets from the unified plugin structure."""
    try:
        frontend_dir = get_plugin_frontend_dir(name)
    except HTTPException:
        # fallback to legacy paths
        plugin_dir = PLUGINS_DIR / name
        if not plugin_dir.exists():
            raise HTTPException(status_code=404, detail="Plugin not found")
        legacy_candidates = [
            plugin_dir / "frontend" / "dist",
            plugin_dir / "dist",
        ]
        frontend_dir = None
        for d in legacy_candidates:
            if d.exists():
                frontend_dir = d
                break
        if not frontend_dir:
            raise HTTPException(status_code=404, detail="Frontend not found")

    target = frontend_dir / file_path
    if not target.exists() or not target.is_relative_to(frontend_dir):
        target = frontend_dir / "index.html"
    if target.exists():
        return FileResponse(str(target))
    raise HTTPException(status_code=404, detail="Frontend not found")


@router.get("/{name}/main.js")
async def serve_plugin_main(name: str):
    """Serve the plugin's desktop main process entry point (dist/index.js)
    for download by the desktop app."""
    try:
        main_path = get_plugin_main_path(name)
        return FileResponse(str(main_path), media_type="application/javascript")
    except HTTPException:
        return JSONResponse(
            content={"error": "No desktop entry point for this plugin"},
            status_code=404,
        )


@router.get("/{name}/panel-data")
async def get_plugin_panel_data(name: str):
    """Return panel data for the widget view in the main panel.

    Plugins can override this by providing their own /panel-data endpoint.
    Returns basic metadata from manifest as fallback.
    """
    plugin_dir = PLUGINS_DIR / name
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail="Plugin not found")

    manifest_file = plugin_dir / "manifest.json"
    if not manifest_file.exists():
        pkg_file = plugin_dir / "package.json"
        if not pkg_file.exists():
            raise HTTPException(status_code=404, detail="Plugin manifest not found")
        pkg = _read_json(pkg_file)
        ns = pkg.get("omniaide") or pkg.get("mqbox") or {}
        display_name = ns.get("displayName", pkg.get("displayName", name))
        icon = ns.get("icon", "")
    else:
        manifest = _read_json(manifest_file)
        display_name = manifest.get("displayName", name)
        icon = manifest.get("icon", "")

    return {
        "title": display_name,
        "summary": None,
        "items": [],
        "actions": [{"label": "打开", "command": "openPage"}],
        "status": None,
        "statusText": None,
        "icon": icon,
    }


def _read_json(path: Path) -> dict:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


@router.delete("/{name}")
async def uninstall_plugin(name: str, db: AsyncSession = Depends(get_db)):
    from main import app
    try:
        await plugin_registry.uninstall_plugin(db, app, name)
        return {"message": f"Plugin {name} uninstalled"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
