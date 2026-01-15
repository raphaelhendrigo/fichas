from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql+psycopg://fichas:fichas@db:5432/fichas"
    SECRET_KEY: str = "change-me"
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_PATH: str = "./data/uploads"
    GCS_BUCKET: str | None = None

    ADMIN_SEED_EMAIL: str = "admin@tcm.sp.gov.br"
    ADMIN_SEED_PASSWORD: str = "admin123"

    LOG_LEVEL: str = "INFO"
    COOKIE_SECURE: bool = False
    SESSION_EXPIRES_SECONDS: int = 60 * 60 * 12
    PAGINATION_PAGE_SIZE: int = 20


settings = Settings()
