from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://postgres:dev@localhost:5432/rag_saas"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    gemini_api_key: str = ""
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 3072
    llm_model: str = "gemini-2.0-flash"
    cors_origins: list[str] = ["*"]
    max_upload_size_mb: int = 20
    chunk_size: int = 500
    chunk_overlap: int = 50
    rag_top_k: int = 5
    rag_score_threshold: float = 0.3


settings = Settings()
