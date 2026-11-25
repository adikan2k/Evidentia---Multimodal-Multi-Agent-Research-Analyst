"""Where the day's spend is kept, so a server restart does not reset the daily cap (D-051).

Only the day's dollar total is stored, one point per UTC day. No visitor address is ever
written: the per-address counts stay in memory.
"""

import uuid
from datetime import date
from typing import Any, Protocol

from qdrant_client import AsyncQdrantClient, models

from evidentia.config import Settings

COLLECTION = "evidentia_spend"


class SpendStore(Protocol):
    async def load(self, day: date) -> float: ...

    async def save(self, day: date, usd: float) -> None: ...


def point_id(day: date) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"evidentia-spend:{day.isoformat()}"))


class QdrantSpend:
    def __init__(self, settings: Settings, client: Any = None) -> None:
        self.client = client or AsyncQdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), timeout=10
        )
        self._ready = False

    async def _ensure(self) -> None:
        if self._ready:
            return
        if not await self.client.collection_exists(COLLECTION):
            # Qdrant wants a vector on every point; a single fixed number is all this needs.
            await self.client.create_collection(
                COLLECTION, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT)
            )
        self._ready = True

    async def load(self, day: date) -> float:
        await self._ensure()
        points = await self.client.retrieve(COLLECTION, ids=[point_id(day)], with_payload=True)
        return float(points[0].payload["usd"]) if points else 0.0

    async def save(self, day: date, usd: float) -> None:
        await self._ensure()
        point = models.PointStruct(
            id=point_id(day), vector=[1.0], payload={"day": day.isoformat(), "usd": round(usd, 6)}
        )
        await self.client.upsert(COLLECTION, points=[point], wait=True)
