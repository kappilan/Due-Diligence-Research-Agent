from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="DD_")

    sec_user_agent: str          # required: no default, so a missing value fails at startup
    aws_region: str = "ap-south-1"
    http_timeout_s: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()