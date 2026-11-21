from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    sarvam_api_key: SecretStr = SecretStr("")
    sarvam_model: str = "sarvam-105b"
    sarvam_timeout_seconds: float = 60.0
    # Sandbox Cashfree Relay "Invoice Intake" inbound webhook. The full URL is a credential.
    relay_intake_webhook_url: SecretStr = SecretStr("")
    agent_max_tool_rounds: int = 5
    agent_max_tool_calls: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
