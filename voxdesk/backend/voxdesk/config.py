from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    provider: Literal["openai", "local", "fixture"] = "local"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./voxdesk.db"
    redis_url: str = ""
    openai_api_key: str = ""
    chat_model: str = "gpt-4.1-mini"
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    embedding_model: str = "text-embedding-3-small"
    ollama_url: str = "http://localhost:11434"
    local_chat_model: str = "qwen2.5:3b"
    local_embedding_model: str = "nomic-embed-text"
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    cookie_secure: bool = False
    public_origin: str = "http://localhost:8000"
    frontend_dir: Path = Path("frontend/dist")
    max_audio_bytes: int = 10 * 1024 * 1024
    max_audio_seconds: int = 60
    provider_timeout: float = Field(default=90, ge=1, le=180)
    turn_timeout: float = Field(default=240, ge=5, le=600)
    requests_per_minute: int = 30
    max_documents: int = 20
    max_chunks: int = 200

    @model_validator(mode="after")
    def production_rules(self):
        if self.provider == "fixture" and self.environment != "test":
            raise ValueError("The fixture provider is exclusively for automated tests")
        if self.environment == "production":
            if not self.cookie_secure or not self.public_origin.startswith("https://"):
                raise ValueError("Production requires HTTPS public_origin and secure cookies")
            if not self.database_url.startswith("postgresql") or not self.redis_url:
                raise ValueError("Production requires PostgreSQL and Redis")
            if "voxdesk_dev_only" in self.database_url:
                raise ValueError("Production requires a unique database password")
        return self
