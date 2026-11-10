from pathlib import Path

import pytest

from ai.coding import workspace
from core.config.settings import settings


def test_glob_and_apply_patch(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("alpha = 1\nbeta = 2\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("gamma = 3\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("docs\n", encoding="utf-8")

    found = workspace.glob_files(str(tmp_path), {"pattern": "**/*.py"})
    assert sorted(found["matches"]) == ["src/a.py", "src/b.py"]

    result = workspace.apply_patch(str(tmp_path), {"changes": [
        {"path": "src/a.py", "old_string": "alpha = 1", "new_string": "alpha = 10"},
        {"path": "src/a.py", "old_string": "beta = 2", "new_string": "beta = 20"},
        {"path": "src/b.py", "old_string": "gamma = 3", "new_string": "gamma = 30"},
    ]})
    assert result["changes"] == 3
    assert (tmp_path / "src" / "a.py").read_text() == "alpha = 10\nbeta = 20\n"
    assert (tmp_path / "src" / "b.py").read_text() == "gamma = 30\n"


def test_apply_patch_is_atomic_on_failure(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("one\ntwo\n", encoding="utf-8")
    result = workspace.apply_patch(str(tmp_path), {"changes": [
        {"path": "a.txt", "old_string": "one", "new_string": "ONE"},
        {"path": "a.txt", "old_string": "missing", "new_string": "x"},
    ]})
    assert "old_string not found" in result["error"]
    assert path.read_text() == "one\ntwo\n"


def test_delete_and_move_file(tmp_path):
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "a.txt").write_text("hello", encoding="utf-8")

    moved = workspace.move_file(str(tmp_path), {"source": "old/a.txt", "target": "new/b.txt"})
    assert moved["moved"] is True
    assert (tmp_path / "new" / "b.txt").read_text() == "hello"

    deleted = workspace.delete_file(str(tmp_path), {"path": "new/b.txt"})
    assert deleted["deleted"] is True
    assert not (tmp_path / "new" / "b.txt").exists()


@pytest.mark.asyncio
async def test_project_file_lists_reads_and_searches_server_workspace(tmp_path, monkeypatch):
    from ai.mcp.tools.coding import project_file

    monkeypatch.setattr(settings, "coding_workspace_root", str(tmp_path))
    project = tmp_path / "demo"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.py").write_text("import os\nprint('hello')\n", encoding="utf-8")
    (project / "README.md").write_text("# Demo\n", encoding="utf-8")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("secret\n", encoding="utf-8")

    listed = await project_file(1, {"op": "list", "project": "demo", "depth": 2})
    text = listed.content[0].text
    assert "src/" in text
    assert "README.md" in text
    assert ".git/" not in text

    read = await project_file(
        1, {"op": "read", "project": "demo", "path": "src/main.py"}
    )
    assert "2: print('hello')" in read.content[0].text

    found = await project_file(
        1, {"op": "grep", "project": "demo", "query": "hello"}
    )
    assert "src/main.py:2" in found.content[0].text

    escaped = await project_file(
        1, {"op": "read", "project": "demo", "path": "../outside.txt"}
    )
    assert escaped.isError is True
