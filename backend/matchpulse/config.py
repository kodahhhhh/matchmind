"""Central configuration; environment variables override backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Shared settings; secrets are optional for database-only work."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    analyst_model: str = "gpt-6.1-sol"
    bulk_model: str = "gpt-6-luna"
    embed_provider: str = "azure"  # "azure" | "cloudflare"
    embed_deployment: str = ""
    embed_dim: int = Field(default=1536, ge=1, le=2000)
    embed_query_instruction: str = ""
    cf_account_id: str = ""
    cf_ai_api_token: SecretStr = SecretStr("")
    database_url: str = "postgresql://matchmind:matchmind@localhost:5432/matchmind"
    data_dir: Path = BACKEND_DIR.parent / "data"


@lru_cache
def get_settings() -> Settings:
    """Return process-local settings."""
    return Settings()
