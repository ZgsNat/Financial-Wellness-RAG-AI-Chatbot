from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    rabbitmq_url: str = "amqp://fw:fw_secret@rabbitmq:5672/"
    redis_url: str = "redis://redis:6379/0"

    # Thresholds for rule-based alerts (phase 1)
    spending_spike_threshold_vnd: int = 500_000   # single transaction > 500k VND
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "notification-service"
    debug: bool = False


def get_settings() -> Settings:
    return Settings()