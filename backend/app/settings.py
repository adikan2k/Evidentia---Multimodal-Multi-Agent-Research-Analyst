from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    pg_url: str = os.getenv("PG_URL", "postgresql://postgres:postgres@localhost:5432/research")
    qdrant_url: str = os.getenv("QDRANT_URL", "")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "")

settings = Settings()
