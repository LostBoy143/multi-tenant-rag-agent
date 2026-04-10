from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    environment: str = "development" # "development" or "production"

    database_url: str
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    gemini_api_key: str
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimensions: int = 384
    llm_model: str = "gemini-2.0-flash"
    cors_origins: list[str] = ["*"]
    max_upload_size_mb: int = 20
    chunk_size: int = 500
    chunk_overlap: int = 50
    rag_top_k: int = 5
    rag_score_threshold: float = 0.3

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    refresh_token_expire_days: int = 7

    # Redis
    redis_url: str

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@bolchat.ai"

    # App
    app_url: str = "http://localhost:3000"

    # Admin
    admin_secret: str
    superadmin_email: str
    superadmin_password: str


settings = Settings()
