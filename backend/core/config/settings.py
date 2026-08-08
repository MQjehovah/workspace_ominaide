import secrets
from pydantic_settings import BaseSettings


# Random fallback secret so the app never runs with a known hardcoded key.
# Provide JWT_SECRET / JWT_REFRESH_SECRET via .env for stable tokens across restarts.
_RANDOM_SECRET = secrets.token_urlsafe(48)


class Settings(BaseSettings):
    database_url: str = "mysql+aiomysql://omniaide:omniaide_pass@mysql:3306/omniaide"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "omniaide_minio"
    minio_secret_key: str = "omniaide_minio_secret"
    minio_public: bool = False
    qdrant_url: str = "http://qdrant:6333"
    redis_url: str = "redis://redis:6379/0"
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    jwt_secret: str = _RANDOM_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    jwt_refresh_secret: str = _RANDOM_SECRET
    jwt_refresh_expire_days: int = 7
    mail_encryption_key: str = ""
    data_layer_enabled: bool = True
    memory_layer_enabled: bool = True
    intelligence_layer_enabled: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = '["*","http://localhost:3000","http://localhost:5173","http://localhost:5000","http://localhost:8080","app://."]'
    webrtc_ice_servers: str = '[{"urls":"stun:mqgeek.com:3478"},{"urls":"turn:mqgeek.com:3478","username":"guest","credential":"guest"},{"urls":"turn:mqgeek.com:3478?transport=tcp","username":"guest","credential":"guest"}]'

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def cors_origins_list(self) -> list[str]:
        import json
        try:
            val = json.loads(self.cors_origins)
            return val if isinstance(val, list) else [self.cors_origins]
        except Exception:
            return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
