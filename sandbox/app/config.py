"""Standalone sandbox runner: template-driven Docker workspace service."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SANDBOX_",
        env_file=".env",
        extra="ignore",
    )

    runner_token: str = ""
    templates_dir: str = "/app/templates"
    state_db: str = "/data/sandbox/workspaces.db"
    data_root: str = "/data/sandbox/workspaces"
    allowed_roots: str = "/data"
    network: str = "omniaide-sandbox"
    name_prefix: str = "omniaide-sbx"
    default_image: str = "omniaide/sandbox-base:latest"
    default_ttl_seconds: int = 1800
    reaper_interval_seconds: int = 60
    max_workspaces_per_owner: int = 5
    exec_timeout_seconds: int = 600
    setup_timeout_seconds: int = 900
    docker_host: str = ""
    # Host path that is bind-mounted at /data inside this runner. Sibling
    # containers need host paths, not paths inside this container.
    host_data_root: str = ""

    @property
    def allowed_root_paths(self) -> list[Path]:
        roots = []
        for raw in self.allowed_roots.split(","):
            raw = raw.strip()
            if raw:
                roots.append(Path(raw).expanduser().resolve())
        return roots

    @property
    def data_root_path(self) -> Path:
        return Path(self.data_root).expanduser().resolve()


settings = Settings()
