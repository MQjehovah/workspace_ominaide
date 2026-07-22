import json
import shutil
import zipfile
import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

PLUGINS_DIR = Path(__file__).resolve().parent.parent.parent / "plugins"

router = APIRouter(prefix="/api/plugins/distributor", tags=["distributor"])


def extract_plugin_zip(zip_path: Path, target_name: str | None = None) -> dict:
    """Extract a unified plugin zip. Returns manifest dict.

    Expected zip structure:
        manifest.json
        dist/index.js          (optional, desktop main process code)
        frontend/              (frontend static files, served by backend)
        backend/               (optional, Python backend code)
    """
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        # validate manifest
        manifest_path = Path(tmp) / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("Missing manifest.json in plugin archive")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        plugin_id = target_name or manifest.get("id") or manifest.get("name", "unknown")

        target = PLUGINS_DIR / plugin_id
        if target.exists():
            shutil.rmtree(target)

        # copy everything
        shutil.copytree(str(Path(tmp)), str(target), dirs_exist_ok=True)

    return manifest


def get_plugin_frontend_dir(plugin_id: str) -> Path:
    plugin_dir = PLUGINS_DIR / plugin_id
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")
    frontend_dir = plugin_dir / "frontend"
    if not frontend_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} has no frontend")
    return frontend_dir


def get_plugin_main_path(plugin_id: str) -> Path:
    """Return path to plugin's desktop main process code (dist/index.js)."""
    plugin_dir = PLUGINS_DIR / plugin_id
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")
    main_path = plugin_dir / "dist" / "index.js"
    if not main_path.exists():
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} has no desktop entry point")
    return main_path


def get_plugin_backend_dir(plugin_id: str) -> Path:
    plugin_dir = PLUGINS_DIR / plugin_id
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")
    backend_dir = plugin_dir / "backend"
    if not backend_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} has no backend code")
    return backend_dir
