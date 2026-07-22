import json, shutil, zipfile, tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

MARKETPLACE_DIR = Path(__file__).resolve().parent.parent.parent / "desktop_plugins"
router = APIRouter(prefix="/api/plugins/marketplace", tags=["marketplace"])


def resolve_plugin_dir(plugin_id: str) -> Path | None:
    if not MARKETPLACE_DIR.exists():
        return None
    for entry in MARKETPLACE_DIR.iterdir():
        if not entry.is_dir() or not (entry / "package.json").exists():
            continue
        pkg = json.loads((entry / "package.json").read_text(encoding="utf-8"))
        manifest = pkg.get("omniaide") or pkg.get("mqbox") or {}
        if manifest.get("id") == plugin_id or entry.name == plugin_id:
            return entry
    return None


def scan_packages() -> list[dict]:
    if not MARKETPLACE_DIR.exists():
        MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)
        return []
    packages = []
    for entry in MARKETPLACE_DIR.iterdir():
        if entry.is_dir() and (entry / "package.json").exists():
            pkg = json.loads((entry / "package.json").read_text(encoding="utf-8"))
            manifest = pkg.get("omniaide") or pkg.get("mqbox") or {}
            plugin_id = manifest.get("id", entry.name)
            zip_path = entry / "plugin.zip"
            packages.append({
                "id": plugin_id,
                "name": pkg.get("name", entry.name),
                "displayName": manifest.get("displayName", pkg.get("displayName", entry.name)),
                "description": pkg.get("description", ""),
                "version": pkg.get("version", "0.0.0"),
                "icon": manifest.get("icon", ""),
                "keywords": manifest.get("keywords", []),
                "permissions": manifest.get("permissions", []),
                "builtin": manifest.get("builtin", False),
                "downloadUrl": f"/api/plugins/marketplace/{plugin_id}/download",
                "hasBuild": zip_path.exists(),
            })
    return packages


@router.get("")
async def list_marketplace():
    return scan_packages()


@router.post("/upload")
async def upload_plugin(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")
    content = await file.read()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_zip = Path(tmp) / "plugin.zip"
        tmp_zip.write_bytes(content)
        try:
            with zipfile.ZipFile(tmp_zip, 'r') as zf:
                if 'package.json' not in zf.namelist():
                    raise ValueError("Missing package.json")
                pkg = json.loads(zf.read('package.json'))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    name = pkg.get("name", file.filename.replace(".zip", ""))
    plugin_dir = MARKETPLACE_DIR / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "package.json").write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    (plugin_dir / "plugin.zip").write_bytes(content)
    manifest = pkg.get("omniaide") or pkg.get("mqbox") or {}
    return {"id": manifest.get("id", name), "name": name, "displayName": manifest.get("displayName", name), "version": pkg.get("version", "0.0.0")}


@router.get("/{plugin_id}/download")
async def download_plugin(plugin_id: str):
    plugin_dir = resolve_plugin_dir(plugin_id)
    if not plugin_dir:
        raise HTTPException(status_code=404, detail="Plugin not found")
    zip_path = plugin_dir / "plugin.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Plugin build not found")
    return FileResponse(str(zip_path), media_type="application/zip", filename=f"{plugin_id}.zip")


@router.delete("/{plugin_id}")
async def delete_plugin(plugin_id: str):
    plugin_dir = resolve_plugin_dir(plugin_id)
    if not plugin_dir:
        raise HTTPException(status_code=404, detail="Plugin not found")
    shutil.rmtree(plugin_dir)
    return {"message": "Plugin deleted"}
