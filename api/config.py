"""Central configuration for Lebne. Values are production-oriented defaults."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEBNE_", env_file=".env", extra="ignore")

    env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # LLM — production long-term default is vLLM (OpenAI-compatible).
    llm_provider: Literal["vllm", "ollama", "openai_compatible"] = "vllm"
    llm_base_url: str = "http://localhost:8001/v1"
    llm_model: str = "lebne-qwen2.5-3b"
    llm_api_key: str = "EMPTY"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024

    # Base model identity (fine-tune source of truth for docs/training).
    base_model_name: str = "Qwen/Qwen2.5-3B-Instruct"

    # RAG
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "lebne_faq"
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    rag_top_k: int = 5
    rag_score_threshold: float = 0.55
    chunk_size: int = 256
    chunk_overlap: int = 32

    # Guardrail
    guardrail_enabled: bool = True
    guardrail_threshold: float = 0.62

    # Security / auth
    require_auth: bool = True
    redact_pii_in_logs: bool = True
    jwt_secret: str = "CHANGE_ME_DEV_ONLY_lebne_jwt_secret_32b"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "lebne"
    jwt_audience: str = "lebne-api"
    access_token_ttl_seconds: int = 3600
    step_up_token_ttl_seconds: int = 300
    service_jwt_secret: str = "CHANGE_ME_DEV_ONLY_lebne_service_secret_32b"
    # local = HS256 mint/login; oidc = IdP JWKS only; hybrid = IdP then local fallback
    auth_mode: Literal["local", "oidc", "hybrid"] = "local"
    oidc_jwks_url: str | None = None
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_algorithms: str = "RS256"

    # Embeddings: sentence_transformers in prod; hash for fast tests
    embedding_backend: Literal["sentence_transformers", "hash"] = "sentence_transformers"

    # Sessions
    redis_url: str | None = "redis://localhost:6379/0"
    session_ttl_seconds: int = 86400
    session_backend: Literal["memory", "redis"] = "memory"

    # Rate limit
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # Wallet backend (same FastAPI process long-term; URL kept for split deploy)
    backend_api_base_url: str = "http://localhost:8000"
    wallet_internal_mode: bool = True  # agent calls in-process WalletService

    # Database — Postgres in docker/prod; SQLite for local tests by default
    database_url: str = "sqlite:///./lebne_wallet.db"

    # Crowdsourcing (Mauritanian rewrite of imported banking prompts)
    contrib_database_url: str | None = None  # default: same as database_url
    contrib_admin_password: str = "CHANGE_ME_CONTRIB_ADMIN"
    # Legacy HTML /contrib + cookie admin — OFF by default (use Next.js + /crowd/v1)
    contrib_legacy_enabled: bool = False
    # When True (recommended on public Render): only /crowd/v1 + /health are served.
    # Wallet/chat/legacy routes return 404 so a public API cannot be abused for those surfaces.
    crowd_surface_only: bool = False
    admin_bootstrap_email: str | None = None
    cors_origins: str = "http://localhost:3000"
    crowd_auth_rate_limit: int = 20
    crowd_stt_rate_limit: int = 30
    # Crowd JWT absolute lifetime (hours). Idle timeout is separate (web cookie).
    crowd_token_ttl_days: int = 1  # legacy; prefer crowd_token_ttl_hours
    crowd_token_ttl_hours: int = 12
    # Not used by API JWT mint; documented for web idle cookie (seconds).
    crowd_idle_seconds: int = 600
    openai_api_key: str | None = None
    whisper_api_key: str | None = None
    whisper_api_base: str = "https://api.openai.com/v1"
    whisper_model: str = "whisper-1"
    public_base_url: str = "http://localhost:8000"

    # Cloudflare R2 (S3-compatible). When unset, audio bytes fall back to Neon payloads.
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str | None = None
    r2_endpoint: str | None = None  # default: https://{account_id}.r2.cloudflarestorage.com
    r2_public_base: str | None = None  # optional CDN / public URL prefix
    audio_max_bytes: int = 8_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
