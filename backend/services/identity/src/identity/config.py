from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = ""

    # JWT — paths injected via Docker secrets
    private_key_path: Path = Path(".")
    public_key_path: Path = Path(".")
    jwt_algorithm: str = "RS256"
    access_token_expire_minutes: int = 60

    # Observability
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "identity-service"

    # App
    debug: bool = False

    @property
    def private_key(self) -> str:
        return self.private_key_path.read_text()

    @property
    def public_key(self) -> str:
        return self.public_key_path.read_text()


@lru_cache
def get_settings() -> Settings:
    return Settings()