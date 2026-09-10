from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://challenge:challenge@localhost:5432/challenge"
    )

    # Guards the endpoints that change data. No default: an unset key disables
    # writes rather than leaving them open. See app/security.py.
    api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
