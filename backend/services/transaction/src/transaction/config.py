from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    rabbitmq_url: str = "amqp://fw:fw_secret@rabbitmq:5672/"

    # JWT verify — only needs public key
    public_key_path: Path = Path(".")
    jwt_algorithm: str = "RS256"

    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "transaction-service"
    debug: bool = False

    @property
    def public_key(self) -> str:
        return self.public_key_path.read_text()


@lru_cache
def get_settings() -> Settings:
    return Settings()