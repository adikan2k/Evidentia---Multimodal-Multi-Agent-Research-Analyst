# backend/app/services/reranker.py
from sentence_transformers import CrossEncoder
from typing import List, Dict, Any, Tuple
import numpy as np

# Lazy-load reranker
_reranker_model = None

def get_reranker():
    global _reranker_model
    if _reranker_model is None:
        _reranker_model = CrossEncoder("BAAI/bge-reranker-base")
    return _reranker_model

def rerank(query: str, passages: List[Dict[str, Any]], top_k: int = 20) -> List[Dict[str, Any]]:
    model = get_reranker()
    pairs = [(query, p["text"]) for p in passages]
    scores = model.predict(pairs)
    # Sort by score descending
    sorted_indices = np.argsort(scores)[::-1][:top_k]
    return [passages[i] for i in sorted_indices]
