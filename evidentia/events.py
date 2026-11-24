"""Turn what the pipeline did into small JSON events a web page can draw.

The same events are used twice: saved to a file as a replay, and (in the API) streamed live.
They carry only what the page shows. In particular a source's full text never leaves the
server: each claim gets its quote plus a few hundred characters either side (D-027).
"""

from typing import Any
from urllib.parse import urlsplit

from evidentia.cost import Ledger
from evidentia.report import describe
from evidentia.schemas import CheckedClaim, RunState, Source

CONTEXT_CHARS = 400


def context_window(text: str, start: int, end: int, size: int = CONTEXT_CHARS) -> dict[str, str]:
    """The text just before and after a quote, cut at word boundaries."""
    left = max(0, start - size)
    right = min(len(text), end + size)
    if left > 0:  # do not start in the middle of a word
        left = text.find(" ", left, start) + 1 or start
    if right < len(text):
        right = max(text.rfind(" ", end, right), end)
    return {"before": text[left:start], "after": text[end:right]}


def host_of(url: str) -> str:
    return urlsplit(url).netloc.removeprefix("www.")


def claim_view(claim: CheckedClaim, sources: dict[str, Source]) -> dict[str, Any]:
    """One claim as the page sees it at this moment of the run."""
    source = sources.get(claim.source_id)
    view: dict[str, Any] = {
        "text": claim.text,
        "quote": claim.quote,
        "source_id": claim.source_id,
        "url": source.url if source else "",
        "host": host_of(source.url) if source else "",
        "title": source.title if source else "",
        "quote_found": claim.quote_found,
        "verdict": claim.verdict,
        # A label only exists once both checks have had their say.
        "label": claim.label if claim.quote_found is False or claim.verdict else None,
        "reason": claim.reason,
        "revised": claim.revised,
        "context": None,
    }
    if source and claim.start is not None and claim.end is not None:
        view["quote"] = source.text[claim.start : claim.end]  # exactly as it is on the page
        view["context"] = context_window(source.text, claim.start, claim.end)
    return view


class EventBuilder:
    """Remembers the sources once they are fetched, so later events can show quotes in context."""

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
        self.sources: dict[str, Source] = {}

    def node_event(self, node: str, update: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if "queries" in update:
            data["queries"] = update["queries"]
        if "hits" in update:
            data["hosts"] = sorted({host_of(h.url) for h in update["hits"]})
        if "sources" in update:
            self.sources = {s.id: s for s in update["sources"]}
            data["sources"] = [
                {"id": s.id, "url": s.url, "host": host_of(s.url), "title": s.title}
                for s in update["sources"]
            ]
            data["skipped"] = [
                {"host": host_of(s.url), "reason": s.reason} for s in update.get("skipped", [])
            ]
        if "repairs" in update:
            data["repair_queries"] = [r.query for r in update["repairs"]]
        if "checked" in update:
            data["claims"] = [claim_view(c, self.sources) for c in update["checked"]]
        return {
            "node": node,
            "summary": describe(node, update),
            "cost_usd": round(self.ledger.spent, 4),
            "data": data,
        }

    def report(self, state: RunState) -> dict[str, Any]:
        claims = [claim_view(c, self.sources) for c in state.checked]
        labels = [c["label"] for c in claims]
        return {
            "question": state.question,
            "claims": claims,
            "labels": {name: labels.count(name) for name in ("supported", "partial", "unverified")},
            "sources_read": len(state.sources),
            "sources_skipped": len(state.skipped),
            "passages_indexed": state.passages_indexed,
            "repair_rounds": state.round,
            "cost": {
                "total_usd": round(self.ledger.spent, 4),
                "cap_usd": self.ledger.cap_usd,
                "by_node": [
                    {"node": t.node, "calls": t.calls, "usd": round(t.usd, 4)}
                    for t in self.ledger.by_node()
                ],
            },
        }
