from pydantic_settings import BaseSettings


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
    jwt_secret: str = "dev-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    jwt_refresh_secret: str = "dev-refresh-secret-key"
    jwt_refresh_expire_days: int = 7
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    webrtc_ice_servers: str = '[{"urls":"stun:stun.l.google.com:19302"}]'

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
