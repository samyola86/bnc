from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bnc:bnc_local@localhost:5432/bnc"
    redis_url: str = "redis://localhost:6379/0"
    app_timezone: str = "Asia/Dhaka"
    cors_origins: list[str] = ["http://localhost:3000"]
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "bnc-media"
    ingestion_api_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
