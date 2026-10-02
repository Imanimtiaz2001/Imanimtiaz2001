from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLEARCV_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/clearcv.db"
    provider: Literal["local", "openai"] = "local"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4.1-mini"
    api_key: SecretStr = SecretStr("")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    max_pages: int = Field(default=10, ge=1, le=30)
    max_chars: int = Field(default=60000, ge=1000, le=120000)
    pdf_timeout_seconds: int = Field(default=60, ge=1, le=180)
    provider_timeout_seconds: int = Field(default=40, ge=1, le=120)
    concurrent_parses: int = Field(default=2, ge=1, le=8)
    retention_hours: int = Field(default=24, ge=1, le=24 * 365)
    ocr_language: str = Field(default="eng", pattern=r"^[a-z_]+(?:\+[a-z_]+)*$")
    web_dist: Path = Path("web/dist")

    @model_validator(mode="after")
    def credentials(self):
        if self.provider == "openai" and not self.openai_api_key.get_secret_value():
            raise ValueError("OpenAI mode requires CLEARCV_OPENAI_API_KEY")
        if self.api_key.get_secret_value() and len(self.api_key.get_secret_value()) < 24:
            raise ValueError("CLEARCV_API_KEY must contain at least 24 characters")
        return self
