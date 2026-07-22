import json
import zipfile
import shutil
import importlib.util
from pathlib import Path
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import async_session
from core.plugin.models import PluginRegistry

PLUGINS_DIR = Path(__file__).resolve().parent.parent.parent / "plugins"


async def discover_plugins(app: FastAPI):
    """Scan plugins/ directory, register enabled plugins at startup."""
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        return

    async with async_session() as db:
        for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
            if not plugin_dir.is_dir():
                continue

            manifest = _load_manifest(plugin_dir)
            if manifest is None:
                continue

            plugin_id = manifest.get("id") or manifest.get("name", plugin_dir.name)
            version = manifest.get("version", "0.0.0")

            result = await db.execute(
                select(PluginRegistry).where(PluginRegistry.name == plugin_id)
            )
            record = result.scalar_one_or_none()

            if record is None:
                record = PluginRegistry(
                    name=plugin_id,
                    version=version,
                    title=manifest.get("displayName", plugin_id),
                    description=manifest.get("description", ""),
                    icon=manifest.get("icon", ""),
                    enabled=True,
                    manifest=manifest,
                )
                db.add(record)
                await db.flush()

            if record.enabled:
                await _register_plugin_routes(app, plugin_id, plugin_dir)
                _register_plugin_tools(manifest, plugin_id)

        await db.commit()


def _load_manifest(plugin_dir: Path) -> dict | None:
    """Load manifest from either manifest.json or package.json (legacy)."""
    manifest_path = plugin_dir / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    pkg_path = plugin_dir / "package.json"
    if pkg_path.exists():
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        ns = pkg.get("omniaide") or pkg.get("mqbox") or {}
        return {
            "id": ns.get("id", pkg.get("name")),
            "name": pkg.get("name"),
            "displayName": ns.get("displayName", pkg.get("displayName", pkg.get("name"))),
            "description": pkg.get("description", ""),
            "version": pkg.get("version", "0.0.0"),
            "icon": ns.get("icon"),
            "permissions": ns.get("permissions", []),
            "main": pkg.get("main", "dist/index.js"),
            "builtin": True,
        }

    return None


async def _register_plugin_routes(app: FastAPI, name: str, plugin_dir: Path):
    """Dynamically import and register plugin's backend router."""
    router_path = plugin_dir / "backend" / "router.py"
    if not router_path.exists():
        return

    spec = importlib.util.spec_from_file_location(
        f"plugins.{name}.backend.router", router_path
    )
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "router"):
            app.include_router(module.router, prefix=f"/api/plugins/{name}")


async def get_plugins(db: AsyncSession) -> list[PluginRegistry]:
    result = await db.execute(select(PluginRegistry).order_by(PluginRegistry.installed_at))
    return list(result.scalars().all())


async def toggle_plugin(db: AsyncSession, name: str) -> PluginRegistry:
    result = await db.execute(select(PluginRegistry).where(PluginRegistry.name == name))
    record = result.scalar_one_or_none()
    if not record:
        raise ValueError(f"Plugin {name} not found")
    record.enabled = not record.enabled
    await db.flush()
    return record


def _register_plugin_tools(manifest: dict, plugin_name: str):
    from core.ai.mcp.tools.plugin_tools import register_plugin_tools_from_manifest
    register_plugin_tools_from_manifest(manifest, plugin_name)


async def uninstall_plugin(db: AsyncSession, app: FastAPI, name: str):
    result = await db.execute(select(PluginRegistry).where(PluginRegistry.name == name))
    record = result.scalar_one_or_none()
    if not record:
        raise ValueError(f"Plugin {name} not found")

    await db.delete(record)

    plugin_dir = PLUGINS_DIR / name
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)


def install_plugin_from_zip(zip_path: Path, plugin_name: str | None = None) -> dict:
    """Extract a plugin zip into the plugins directory and return its manifest.

    Supports both new unified format (manifest.json) and legacy format (package.json).
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        # try new unified format first
        manifest_paths = list(Path(tmp).rglob("manifest.json"))
        if not manifest_paths:
            # fallback to legacy format
            pkg_paths = list(Path(tmp).rglob("package.json"))
            if not pkg_paths:
                raise ValueError("No manifest.json or package.json found in plugin archive")
            pkg = json.loads(pkg_paths[0].read_text(encoding="utf-8"))
            ns = pkg.get("omniaide") or pkg.get("mqbox") or {}
            manifest = {
                "id": ns.get("id", pkg.get("name")),
                "name": pkg.get("name"),
                "displayName": ns.get("displayName", pkg.get("displayName", pkg.get("name"))),
                "description": pkg.get("description", ""),
                "version": pkg.get("version", "0.0.0"),
                "icon": ns.get("icon"),
                "permissions": ns.get("permissions", []),
                "main": pkg.get("main", "dist/index.js"),
                "builtin": False,
            }
            source = pkg_paths[0].parent
        else:
            manifest = json.loads(manifest_paths[0].read_text(encoding="utf-8"))
            source = manifest_paths[0].parent

        name = plugin_name or manifest.get("id") or manifest.get("name", source.name)

        target = PLUGINS_DIR / name
        if target.exists():
            shutil.rmtree(target)

        shutil.copytree(str(source), str(target), dirs_exist_ok=True)

    return manifest
