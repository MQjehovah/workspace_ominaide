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
        for plugin_dir in PLUGINS_DIR.iterdir():
            if not plugin_dir.is_dir():
                continue
            manifest_path = plugin_dir / "manifest.json"
            if not manifest_path.exists():
                continue

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            name = manifest.get("name", plugin_dir.name)

            # Check if registered in DB
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
                await db.flush()

            if record.enabled:
                await _register_plugin_routes(app, name, plugin_dir)

        await db.commit()


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


async def uninstall_plugin(db: AsyncSession, app: FastAPI, name: str):
    result = await db.execute(select(PluginRegistry).where(PluginRegistry.name == name))
    record = result.scalar_one_or_none()
    if not record:
        raise ValueError(f"Plugin {name} not found")

    # Remove from DB
    await db.delete(record)

    # Remove plugin directory
    plugin_dir = PLUGINS_DIR / name
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)
