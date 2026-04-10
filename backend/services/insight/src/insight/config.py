from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""
    rabbitmq_url: str = "amqp://fw:fw_secret@rabbitmq:5672/"
    redis_url: str = "redis://redis:6379/0"

    # Embedding service
    embedding_service_url: str = "http://embedding:8080"

    # Gemini LLM (phase 2)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # RAG tuning
    rag_top_k: int = 8
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64

    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_service_name: str = "insight-service"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()