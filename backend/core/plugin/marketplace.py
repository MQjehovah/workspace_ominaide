import json
import shutil
import zipfile
import tempfile
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

MARKETPLACE_DIR = Path(__file__).resolve().parent.parent.parent / "desktop_plugins"
router = APIRouter(prefix="/api/plugins/marketplace", tags=["marketplace"])


def scan_packages() -> list[dict]:
    """Scan marketplace directory for built plugin packages."""
    if not MARKETPLACE_DIR.exists():
        MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)
        return []

    packages = []
    for entry in MARKETPLACE_DIR.iterdir():
        if entry.is_dir() and (entry / "package.json").exists():
            pkg = json.loads((entry / "package.json").read_text())
            manifest = pkg.get("omniaide") or pkg.get("mqbox") or {}
            zip_path = entry / "plugin.zip"
            packages.append({
                "id": manifest.get("id", entry.name),
                "name": pkg.get("name", entry.name),
                "displayName": manifest.get("displayName", pkg.get("displayName", entry.name)),
                "description": pkg.get("description", ""),
                "version": pkg.get("version", "0.0.0"),
                "icon": manifest.get("icon", ""),
                "keywords": manifest.get("keywords", []),
                "permissions": manifest.get("permissions", []),
                "builtin": manifest.get("builtin", False),
                "downloadUrl": f"/api/plugins/marketplace/{entry.name}/download",
                "hasBuild": zip_path.exists(),
            })
    return packages


@router.get("")
async def list_marketplace():
    return scan_packages()


@router.get("/{plugin_id}/download")
async def download_plugin(plugin_id: str):
    plugin_dir = MARKETPLACE_DIR / plugin_id
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail="Plugin not found")

    zip_path = plugin_dir / "plugin.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Plugin build not found. Build it first.")

    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"{plugin_id}.zip",
    )


@router.post("/{plugin_id}/install")
async def install_from_marketplace(plugin_id: str):
    from sqlalchemy import select
    from core.plugin.models import PluginRegistry
    from core.plugin.registry import install_plugin_from_zip
    from core.database.session import async_session

    plugin_dir = MARKETPLACE_DIR / plugin_id
    zip_path = plugin_dir / "plugin.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Plugin build not found")

    manifest = install_plugin_from_zip(zip_path)
    name = manifest["name"]

    async with async_session() as db:
        result = await db.execute(select(PluginRegistry).where(PluginRegistry.name == name))
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
        return {"name": record.name, "title": record.title, "enabled": record.enabled}
