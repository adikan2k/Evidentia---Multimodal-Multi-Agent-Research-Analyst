# backend/app/services/embedding.py
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Dict, Any
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from app.settings import settings

# Lazy-load embedding model
_embedding_model = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("BAAI/bge-large-en-v1.5")
    return _embedding_model

def embed_texts(texts: List[str]) -> List[List[float]]:
    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return embeddings.tolist()

def store_passages(job_id: str, passages: List[Dict[str, Any]]) -> List[str]:
    # Connect to Qdrant Cloud or local instance
    if settings.qdrant_url.startswith("https://"):
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    else:
        client = QdrantClient(host=settings.qdrant_url.split(":")[1].replace("//", ""), port=6333)
    
    collection_name = f"job_{job_id}"
    # Ensure collection exists
    try:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
        )
    except Exception:
        pass  # Collection may already exist
    texts = [p["text"] for p in passages]
    embeddings = embed_texts(texts)
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={"text": txt, "url": p.get("url"), "title": p.get("title"), "kind": p.get("kind")}
        )
        for emb, txt, p in zip(embeddings, texts, passages)
    ]
    ids = [point.id for point in points]
    client.upsert(collection_name=collection_name, points=points)
    return ids
