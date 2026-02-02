from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+psycopg://fichas:fichas@db:5432/fichas"
    SECRET_KEY: str = "change-me"
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "./data/uploads"
    GCS_BUCKET: str | None = None
    OCR_UPLOAD_DIR: str = "./data/ocr_uploads"
    MAX_UPLOAD_MB: int = 10
    REDIS_URL: str = "redis://redis:6379/0"
    OCR_LANG: str = "pt"
    GCP_OCR_PROVIDER: str = "google_vision"
    GCP_PROJECT_ID: str | None = None
    GCP_REGION: str | None = None
    GCS_OCR_BUCKET: str | None = None
    OCR_MAX_PAGES: int | None = 10
    OCR_TIMEOUT_SECONDS: int = 180
    OCR_RETRY: int = 2
    OCR_LANGUAGE_HINTS: str | None = "pt"

    ADMIN_SEED_EMAIL: str = "admin@tcm.sp.gov.br"
    ADMIN_SEED_PASSWORD: str = "admin123"

    LOG_LEVEL: str = "INFO"
    COOKIE_SECURE: bool = False
    SESSION_EXPIRES_SECONDS: int = 60 * 60 * 12
    PAGINATION_PAGE_SIZE: int = 20
    APP_BASE_PATH: str = ""

    @field_validator("APP_BASE_PATH", mode="before")
    @classmethod
    def normalize_base_path(cls, v):
        if v is None:
            return ""
        value = str(v).strip()
        if value in ("", "/"):
            return ""
        if not value.startswith("/"):
            value = "/" + value
        return value.rstrip("/")


settings = Settings()
