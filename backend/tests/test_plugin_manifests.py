"""Plugin manifest schema and route mounting."""

import json
from pathlib import Path

PLUGINS = Path(__file__).resolve().parents[1] / "plugins"


def _manifest_dirs():
    return [
        d for d in sorted(PLUGINS.iterdir())
        if d.is_dir() and not d.name.startswith("__")
    ]


def test_every_plugin_has_a_valid_manifest():
    from core.plugin.manifest import load_manifest

    for plugin_dir in _manifest_dirs():
        manifest = load_manifest(plugin_dir, expected_id=plugin_dir.name)
        assert manifest["id"] == plugin_dir.name
        assert manifest["version"]
        assert manifest["title"]


def test_manifest_tool_names_are_unique_within_plugin():
    for plugin_dir in _manifest_dirs():
        data = json.loads((plugin_dir / "manifest.json").read_text(encoding="utf-8"))
        names = [t.get("name") for t in data.get("tools", [])]
        assert len(names) == len(set(names)), plugin_dir.name


async def test_manifest_backed_routes_are_mounted(client):
    import main

    paths = {getattr(route, "path", "") for route in main.app.routes}
    expected = (
        "/api/chat",
        "/api/music",
        "/api/remote",
        "/api/schedule",
        "/api/projects",
        "/api/notifications",
    )
    for prefix in expected:
        assert any(path == prefix or path.startswith(prefix + "/") for path in paths), prefix
    assert "/ws/remote" in paths
