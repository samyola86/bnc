import re
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bnc:bnc_local@localhost:5432/bnc"
    redis_url: str = "redis://localhost:6379/0"
    app_timezone: str = "Asia/Dhaka"
    cors_origins: list[str] = ["http://localhost:3000"]
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "bnc-media"
    s3_access_key: str = "bnc_local"
    s3_secret_key: str = "bnc_local_storage_password"
    ingestion_api_token: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    openai_classification_model: str = ""
    openai_classification_input_per_million: float = 0
    openai_classification_output_per_million: float = 0
    meta_instagram_token: str = ""
    meta_instagram_account_id: str = ""
    meta_graph_version: str = "v25.0"
    ai_hourly_limit: int = 20
    auth_cookie_secure: bool = True
    auth_origin: str = "http://localhost:3000"
    auth_additional_origins: list[str] = []
    auth_encryption_key: str = ""
    auth_session_hours: int = 8
    auth_require_editor_mfa: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    @field_validator("auth_origin")
    @classmethod
    def validate_auth_origin(cls, value):
        parts = urlsplit(value)
        if (
            not re.fullmatch(r"https?://[a-z0-9.-]+(?::[0-9]+)?", value)
            or not parts.hostname
            or "*" in value
            or parts.port == 0
            or (parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1"})
        ):
            raise ValueError("Use an exact HTTPS origin, or HTTP localhost origin, without a path")
        return value

    @field_validator("auth_additional_origins")
    @classmethod
    def validate_auth_additional_origins(cls, values):
        return list(dict.fromkeys(cls.validate_auth_origin(value) for value in values))

    @property
    def auth_trusted_origins(self):
        return {self.auth_origin, *self.auth_additional_origins}


@lru_cache
def get_settings() -> Settings:
    return Settings()
