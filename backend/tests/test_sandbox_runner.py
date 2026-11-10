import pytest

from ai.coding import sandbox_runner


def test_relative_cwd_rejects_escape(tmp_path):
    with pytest.raises(ValueError):
        sandbox_runner._relative_cwd(str(tmp_path), "../outside")


def test_relative_cwd_maps_project_subdir(tmp_path):
    (tmp_path / "backend").mkdir()
    assert sandbox_runner._relative_cwd(str(tmp_path), "backend") == "backend"
    assert sandbox_runner._relative_cwd(str(tmp_path), None) == "."


@pytest.mark.asyncio
async def test_run_command_blocks_git_push(tmp_path):
    result = await sandbox_runner.run_command_in_sandbox(
        1, str(tmp_path), {"command": "git push --force origin main"}
    )
    assert "not allowed" in result["error"]


@pytest.mark.asyncio
async def test_run_command_blocks_sensitive_files(tmp_path):
    result = await sandbox_runner.run_command_in_sandbox(
        1, str(tmp_path), {"command": "cat .env"}
    )
    assert "sensitive file" in result["error"]
