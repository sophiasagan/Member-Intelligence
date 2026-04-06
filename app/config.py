from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    anthropic_api_key: str
    database_url: str = "sqlite:///./member_intel.db"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
