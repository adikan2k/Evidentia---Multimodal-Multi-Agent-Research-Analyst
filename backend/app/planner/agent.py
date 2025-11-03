# backend/app/planner/agent.py
from typing import List, Dict, Any

def generate_subqueries(query: str, max_sources: int = 12, recent: bool = False, include_youtube: bool = False) -> List[Dict[str, Any]]:
    # Placeholder: in real system, use LLM to decompose query into subqueries
    # For demo, return the original query plus a few variants
    base = {"q": query, "type": "web"}
    subqueries = [base]
    # Simple heuristics for demo
    if " vs " in query.lower() or " compare " in query.lower():
        parts = query.lower().replace(" vs ", " vs ").replace(" compare ", " vs ").split(" vs ")
        if len(parts) == 2:
            subqueries.append({"q": parts[0].strip(), "type": "web"})
            subqueries.append({"q": parts[1].strip(), "type": "web"})
    if include_youtube:
        subqueries.append({"q": query, "type": "youtube"})
    # Limit to max_sources
    return subqueries[: max_sources]
