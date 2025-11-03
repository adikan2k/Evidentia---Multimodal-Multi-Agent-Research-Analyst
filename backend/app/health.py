from fastapi import APIRouter
from app.settings import settings
import asyncpg
import httpx

PG_URL = "postgresql://postgres:postgres@postgres:5432/research"
QDRANT_URL = "http://qdrant:6333"

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok",
    }

@router.get("/health/db")
async def check_db():
    try:
        conn = await asyncpg.connect(settings.pg_url)
        await conn.execute("SELECT 1")
        await conn.close()
        return {"postgres": "ok"}
    except Exception as e:
        return {"postgres": "error", "detail": str(e)}

@router.get("/health/qdrant")
async def check_qdrant():
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.qdrant_url}/readyz")
            if resp.status_code == 200:
                return {"qdrant": "ok"}
            return {"qdrant": "not ready"}
    except Exception as e:
        return {"qdrant": "error", "detail": str(e)}
