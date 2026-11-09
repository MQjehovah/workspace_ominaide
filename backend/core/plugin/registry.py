import json
import sys
import zipfile
import shutil
import importlib.util
from pathlib import Path
from fastapi import APIRouter, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.database.session import async_session
from core.logging import get_logger
from core.plugin.manifest import load_manifest
from core.plugin.models import PluginRegistry

log = get_logger(__name__)

PLUGINS_DIR = Path(__file__).resolve().parent.parent.parent / "plugins"


async def discover_plugins(app: FastAPI):
    """Scan plugins/ directory, register enabled plugins at startup."""
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        return

    discovered: list[tuple[str, Path, bool]] = []
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
                    title=manifest.get("title") or plugin_id,
                    description=manifest.get("description", ""),
                    icon=manifest.get("icon", ""),
                    enabled=True,
                    manifest=manifest,
                )
                db.add(record)
                await db.flush()
            else:
                record.version = version
                record.title = manifest.get("title") or record.title
                record.description = manifest.get("description", "") or record.description
                record.icon = manifest.get("icon", "") or record.icon
                record.manifest = manifest

            discovered.append((plugin_id, plugin_dir, bool(record.enabled)))
        await db.commit()

    # Run hooks outside the registry session so plugin startup can safely
    # enqueue jobs or open its own database sessions (SQLite included).
    for plugin_id, plugin_dir, enabled in discovered:
        if not enabled:
            from core.scheduler import scheduler

            scheduler.unregister_owner(plugin_id)
            continue
        manifest = _load_manifest(plugin_dir) or {}
        await _register_plugin_routes(app, plugin_id, plugin_dir)
        _register_plugin_tools(manifest, plugin_id)
        _register_plugin_jobs(plugin_id, plugin_dir)
        await _run_plugin_lifecycle(plugin_id, plugin_dir, "startup")


def _load_manifest(plugin_dir: Path) -> dict | None:
    """Load and validate manifest.json (or legacy package.json)."""
    try:
        return load_manifest(plugin_dir, expected_id=plugin_dir.name)
    except Exception as exc:
        log.warning("skip plugin %s: %s", plugin_dir.name, exc)
        return None


async def _register_plugin_routes(app: FastAPI, name: str, plugin_dir: Path):
    """Import a plugin router module and mount every APIRouter it exports."""
    router_path = plugin_dir / "backend" / "router.py"
    if not router_path.exists():
        return

    module_name = f"plugins.{name}.backend.router"
    spec = importlib.util.spec_from_file_location(module_name, router_path)
    if not (spec and spec.loader):
        return
    module = importlib.util.module_from_spec(spec)
    # Keep one module instance per plugin so imports and the mounted router
    # share the same objects (monkeypatching, module-level state, etc.).
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    mounted: set[int] = set()
    for attr, value in vars(module).items():
        if not isinstance(value, APIRouter) or id(value) in mounted:
            continue
        mounted.add(id(value))
        has_api_prefix = any(
            getattr(r, "path", "").startswith(("/api/", "/ws/"))
            for r in getattr(value, "routes", [])
        )
        if has_api_prefix:
            app.include_router(value)
        else:
            app.include_router(value, prefix=f"/api/plugins/{name}")


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


async def _run_plugin_lifecycle(plugin_name: str, plugin_dir: Path, hook: str) -> None:
    path = plugin_dir / "backend" / "lifecycle.py"
    if not path.exists():
        return
    module_name = f"plugins.{plugin_name}.backend.lifecycle"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not (spec and spec.loader):
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    fn = getattr(module, hook, None)
    if callable(fn):
        result = fn()
        if hasattr(result, "__await__"):
            await result


def _register_plugin_jobs(plugin_name: str, plugin_dir: Path) -> None:
    """Load optional ``backend/jobs.py`` and register its periodic jobs."""
    jobs_path = plugin_dir / "backend" / "jobs.py"
    if not jobs_path.exists():
        return
    module_name = f"plugins.{plugin_name}.backend.jobs"
    spec = importlib.util.spec_from_file_location(module_name, jobs_path)
    if not (spec and spec.loader):
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    from core.scheduler import scheduler

    for job in getattr(module, "JOBS", []):
        job.owner = plugin_name
        scheduler.register(job)


def _register_plugin_tools(manifest: dict, plugin_name: str):
    from core.ai.mcp.tools.plugin_tools import register_plugin_tools_from_manifest

    register_plugin_tools_from_manifest(manifest, plugin_name)
    tools_path = PLUGINS_DIR / plugin_name / "backend" / "tools.py"
    if tools_path.exists():
        module_name = f"plugins.{plugin_name}.backend.tools"
        spec = importlib.util.spec_from_file_location(module_name, tools_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if callable(register):
                register()


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
    """Extract a unified plugin zip into ``plugins/<manifest.id>``."""
    import tempfile

    from core.plugin.manifest import find_plugin_source

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        source, manifest = find_plugin_source(Path(tmp))
        plugin_id = manifest["id"]
        if plugin_name and plugin_name != plugin_id:
            raise ValueError(
                f"插件目录名 '{plugin_name}' 与 manifest id '{plugin_id}' 不一致"
            )

        target = PLUGINS_DIR / plugin_id
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(str(source), str(target), dirs_exist_ok=True)
    return manifest
