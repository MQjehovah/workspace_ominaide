import secrets
from pydantic_settings import BaseSettings


# Random fallback secret so the app never runs with a known hardcoded key.
# Provide JWT_SECRET / JWT_REFRESH_SECRET via .env for stable tokens across restarts.
_RANDOM_SECRET = secrets.token_urlsafe(48)


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://omniaide:omniaide_pass@postgres:5432/omniaide"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "omniaide_minio"
    minio_secret_key: str = "omniaide_minio_secret"
    minio_public: bool = False
    # Public base URL used to rewrite presigned MinIO URLs, e.g.
    # https://mqgeek.com/minio (nginx strips /minio and keeps Host=minio:9000).
    minio_public_url: str = ""
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
    # Speech services (ASR / TTS). Defaults wrap Zhipu bigmodel, which is what the
    # SmartAssistant firmware calls directly today. Keys fall back to llm_api_key.
    asr_api_key: str = ""
    asr_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    asr_model: str = "glm-asr"
    tts_api_key: str = ""
    tts_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    tts_model: str = "glm-tts"
    tts_voice: str = "tongtong"
    tts_format: str = "wav"
    # Personal-assistant agent persona + conversation memory
    assistant_system_prompt: str = (
        "你是 OmniAide，一个私有化部署的个人 AI 助手，只服务于当前用户。"
        "你可以访问并使用用户的个人数据（文件、笔记、日程、邮件、通知、活动记录等），"
        "也能调用工具替用户完成查询与操作。\n"
        "行为准则：\n"
        "1. 主动、简洁、准确地用中文回答；语音场景下尽量简短口语化。\n"
        "2. 需要用户数据时优先调用工具检索，不要凭空猜测。\n"
        "3. 涉及创建、修改或删除等操作时先确认关键参数，不确定时向用户澄清。\n"
        "4. 保护隐私，不泄露与请求无关的信息。"
    )
    chat_history_limit: int = 20
    jwt_secret: str = _RANDOM_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30
    jwt_refresh_secret: str = _RANDOM_SECRET
    jwt_refresh_expire_days: int = 7
    ha_base_url: str = ""          # Home Assistant 地址，例 http://192.168.2.10:8123
    device_firmware_dir: str = "data/device_firmware"   # 设备固件下发目录（version.txt + firmware.bin）
    weather_lat: str = ""          # 天气经纬度（Open-Meteo，无 key），例 "31.23"
    weather_lon: str = ""          # 例 "121.47"；留空 = 不下发天气
    ha_token: str = ""             # HA 长期访问令牌
    mail_encryption_key: str = ""
    data_layer_enabled: bool = True
    memory_layer_enabled: bool = True
    intelligence_layer_enabled: bool = True
    coding_workspace_root: str = "/workspace"
    coding_max_turns: int = 40
    coding_command_timeout_ms: int = 120000
    # One-shot delivery: after the agent finishes, verify -> branch -> commit -> push.
    # When enabled the agent tools themselves cannot commit/push; delivery owns git.
    coding_auto_deliver: bool = True
    # Safe default: commit to a bot branch, but do not push until explicitly enabled.
    coding_auto_push: bool = False
    coding_verify_command: str = ""      # e.g. "pytest -q" or "npm run build"
    coding_branch_prefix: str = "feature/"
    coding_context_max_chars: int = 12000
    coding_ssh_key_path: str = "/root/.ssh/id_rsa"
    # Untrusted repo commands run as this unprivileged user with a scrubbed env.
    coding_sandbox_enabled: bool = True
    coding_sandbox_user: str = "agent"
    coding_sandbox_home: str = "/home/agent"
    coding_max_concurrency: int = 2
    # Notes RAG: chunking + hybrid retrieval (vector + BM25 + RRF + MMR)
    notes_rag_enabled: bool = True
    notes_chunk_size: int = 600
    notes_chunk_overlap: int = 80
    notes_rag_top_k: int = 8
    notes_rag_recall_k: int = 30
    notes_rag_mmr_lambda: float = 0.7
    # Only rewrite sufficiently complex queries (saves an LLM call on short asks).
    notes_rag_query_rewrite_min_len: int = 20
    # Agentic retrieval: judge sufficiency and run follow-up searches.
    notes_rag_agentic_enabled: bool = True
    notes_rag_agentic_hops: int = 2
    # Web access (Bing search + page fetching). No API key required.
    web_search_url: str = "https://cn.bing.com/search"
    web_search_max_results: int = 5
    web_fetch_max_bytes: int = 2_000_000
    web_fetch_max_chars: int = 12_000
    # Proactive morning briefing (server local time).
    morning_brief_enabled: bool = True
    morning_brief_hour: int = 7
    morning_brief_minute: int = 30
    # Bot runs: persistent execution, heartbeat and recovery.
    bot_run_concurrency: int = 2
    bot_run_max_turns: int = 20
    bot_run_timeout_seconds: int = 1800
    bot_run_heartbeat_seconds: int = 15
    bot_run_poll_seconds: float = 0.4
    bot_run_auto_summary: bool = True
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
