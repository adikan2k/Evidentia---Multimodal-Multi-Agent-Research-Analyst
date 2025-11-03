from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    pg_url: str = os.getenv("PG_URL", "postgresql://postgres:postgres@localhost:5432/research")
    qdrant_url: str = os.getenv("QDRANT_URL", "https://fbc91e86-3390-4dd8-a064-40537249c4ae.us-east-1-1.aws.cloud.qdrant.io")
    qdrant_api_key: str = os.getenv("QDRANT_API_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.rSeAp-7MINLM4SpUCS0l4HCHUbF_auQYPU94Za6PftQ")

settings = Settings()
