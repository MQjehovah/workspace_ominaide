import secrets
from pydantic_settings import BaseSettings


# Random fallback secret so the app never runs with a known hardcoded key.
# Provide JWT_SECRET / JWT_REFRESH_SECRET via .env for stable tokens across restarts.
_RANDOM_SECRET = secrets.token_urlsafe(48)


class Settings(BaseSettings):
    # Logging. JSON is optional for log collectors; text is the default.
    log_level: str = "INFO"
    log_json: bool = False
    database_url: str = "postgresql+asyncpg://omniaide:omniaide_pass@postgres:5432/omniaide"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "omniaide_minio"
    minio_secret_key: str = "omniaide_minio_secret"
    minio_public: bool = False
    # Public base URL used to rewrite presigned MinIO URLs, e.g.
    # https://mqgeek.com/minio (nginx strips /minio and keeps Host=minio:9000).
    minio_public_url: str = ""
    redis_url: str = "redis://redis:6379/0"
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    # Speech services (ASR / TTS). Defaults target the xzrobot OpenAI-compatible
    # gateway. Keys fall back to llm_api_key.
    asr_api_key: str = ""
    asr_base_url: str = "https://ai.xzrobot.com/v1"
    asr_model: str = "voice-asr"
    asr_verbose_json: bool = False
    # 0 means no application-level size limit (meeting audio goes through MinIO).
    asr_max_audio_mb: int = 0
    # Long meeting recordings are sent to ASR as one stream from MinIO; these
    # controls are intentionally independent of the 25MB voice-note limit.
    asr_timeout_seconds: int = 3600
    asr_diarize: bool = False
    meeting_asr_concurrency: int = 1
    tts_api_key: str = ""
    tts_base_url: str = "https://ai.xzrobot.com/v1"
    tts_model: str = "voice-tts"
    tts_voice: str = "default"
    tts_format: str = "wav"
    # Some gateways (e.g. xzrobot) reject response_format entirely.
    tts_send_format: bool = False
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
    # Public self-registration. The first user can always be created to bootstrap
    # an empty deployment; afterwards only admins may add accounts.
    allow_registration: bool = False
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
    # Backend-first mail: pull IMAP incrementally and analyse new messages.
    # IMAP fetching only. Analysis is done by a mail.received Bot routine.
    mail_sync_enabled: bool = True
    mail_sync_interval_seconds: int = 300
    mail_max_per_sync: int = 20
    # Backend-first information sources: refresh even when no client is online.
    sources_refresh_enabled: bool = True
    sources_refresh_interval_seconds: int = 1800
    # RSSHub base URL used by providers such as GitHub Trending.
    rsshub_base_url: str = ""
    data_layer_enabled: bool = True
    memory_layer_enabled: bool = True
    # Runtime data. Production mounts one host directory at /data/omniaide and
    # points every persistent path below at a subdirectory of it.
    # Agent Skills: built-in skills live under backend/skills/builtin; user/bot
    # skills are discovered under skills_dir (relative to the backend cwd).
    skills_dir: str = "data/skills"
    desktop_plugins_dir: str = "desktop_plugins"
    # Daily memory agent auto-approves candidates at or above this confidence.
    memory_auto_approve_threshold: int = 85
    # Lightweight DingTalk message sync (no LLM) feeding the daily memory agent.
    dingtalk_sync_enabled: bool = True
    dingtalk_sync_hour: int = 1
    dingtalk_sync_minute: int = 45
    dingtalk_sync_hours: int = 24
    dingtalk_sync_max_messages: int = 200
    # DingTalk calendar mirror (no LLM). Keeps external source metadata.
    dingtalk_calendar_sync_enabled: bool = True
    dingtalk_calendar_sync_minutes: int = 15
    dingtalk_calendar_days_before: int = 7
    dingtalk_calendar_days_after: int = 90
    intelligence_layer_enabled: bool = True
    # Every user gets an isolated runtime directory: <workspace_root>/<user_id>.
    # projects/ holds coding projects, dingtalk/ holds that user's DWS config and
    # token store. Keep workspace_root on the mounted data volume.
    workspace_root: str = "/data/workspace"
    # Legacy/test override. When set, projects use this directory directly
    # instead of <workspace_root>/<user_id>/projects. Leave empty in production.
    coding_workspace_root: str = ""
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
    # Scheduled AI jobs live in Bot routines, not here.
    # Bot runs: persistent execution, heartbeat and recovery.
    bot_run_concurrency: int = 2
    bot_run_max_turns: int = 20
    bot_run_timeout_seconds: int = 1800
    bot_run_heartbeat_seconds: int = 15
    bot_run_poll_seconds: float = 0.4
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # General shell tool for the bot (approval required). Runs in the backend
    # container as the backend user, with a scrubbed environment.
    shell_enabled: bool = True
    # The shell tool runs as root inside the container. In a multi-user
    # deployment only operators may use it, otherwise any user could read other
    # users' data and server secrets.
    shell_admin_only: bool = True
    shell_default_cwd: str = "/app"
    shell_timeout_seconds: int = 600
    shell_max_output_chars: int = 30_000
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
