"""Turn what an audit did into small JSON events the audit page can draw (D-041).

Used twice, like `evidentia/events.py`: saved to a file as a recorded audit, and streamed live
by the API. A fetched page's full text never leaves the server: each quote goes out with a few
hundred characters either side. The pasted answer itself is sent back, because the page shows
it with its claims marked.
"""

from typing import Any

from evidentia.audit.report import claim_views, scorecard
from evidentia.audit.report import describe as describe_step
from evidentia.audit.schemas import AuditClaim, AuditState
from evidentia.cost import Ledger
from evidentia.events import context_window, host_of, page_bounds
from evidentia.schemas import Source


def page_view(page: dict[str, Any], source: Source | None) -> dict[str, Any]:
    """One claim-page result as the page sees it: quotes with their context, no page text."""
    quotes = []
    for q in page["quotes"]:
        context = None
        if source is not None:
            pages = tuple(q["pages"]) if q["pages"] else None
            bounds = page_bounds(source, pages)
            context = context_window(source.text, q["start"], q["end"], bounds=bounds)
        quotes.append({"text": q["text"], "pages": q["pages"], "context": context})
    return {
        "citation_id": page["citation_id"],
        "url": page["url"],
        "host": host_of(page["url"]),
        "title": source.title if source else "",
        "kind": source.kind if source else "html",
        "label": page["label"],
        "quote_label": page["quote_label"],
        "skipped": page["skipped"],
        "quotes": quotes,
        "quote_reason": page["reason"],
        "page_judged": page["page_judged"],
        "page_reason": page["page_reason"],
    }


class AuditEventBuilder:
    """Remembers the pages once they are fetched, so later events can show quotes in context."""

    def __init__(self, ledger: Ledger) -> None:
        self.ledger = ledger
        self.sources: dict[str, Source] = {}
        self._claims: list[AuditClaim] = []

    def node_event(self, node: str, update: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if node == "parse":
            parsed = update["parsed"]
            data["answer_text"] = parsed.text
            data["citations"] = [
                {"id": c.id, "url": c.url, "host": host_of(c.url)} for c in parsed.citations
            ]
        if node == "split":
            self._claims = list(update["claims"])
            data["claims"] = [
                {
                    "index": i,
                    "sentence": c.sentence,
                    "start": c.start,
                    "end": c.end,
                    "claim": c.claim,
                    "citation_ids": c.citation_ids,
                    "cited_by": c.cited_by,
                }
                for i, c in enumerate(update["claims"])
            ]
            data["not_located"] = len(update.get("not_located", []))
        if node == "fetch":
            self.sources = {s.url: s for s in update["sources"]}
            data["read"] = [
                {"url": s.url, "host": host_of(s.url), "title": s.title, "kind": s.kind}
                for s in update["sources"]
            ]
            data["skipped"] = [
                {"url": s.url, "host": host_of(s.url), "reason": s.reason}
                for s in update["skipped"]
            ]
        if node == "check":
            data["quote_labels"] = [
                {"claim": r.claim, "citation_id": r.citation_id, "quote_label": r.quote_label}
                for r in update["results"]
            ]
        if node == "page_check":
            data["judged"] = len(update.get("page_verdicts", {}))
        if node == "combine":  # both judges are done: every claim's label is final
            state = AuditState(run_id="", answer="", claims=self._claims, results=update["results"])
            data["claims"] = self.claims(state)
        return {
            "node": node,
            "summary": describe_step(node, update),
            "cost_usd": round(self.ledger.spent, 4),
            "data": data,
        }

    def claims(self, state: AuditState) -> list[dict[str, Any]]:
        views = []
        for view in claim_views(state):
            pages = [page_view(p, self.sources.get(p["url"])) for p in view["pages"]]
            views.append(
                {
                    "sentence": view["sentence"],
                    "start": view["start"],
                    "end": view["end"],
                    "claim": view["claim"],
                    "citation_ids": view["citation_ids"],
                    "cited_by": view["cited_by"],
                    "label": view["label"],
                    "disputed": view["disputed"],
                    "pages": pages,
                }
            )
        return views

    def report(self, state: AuditState) -> dict[str, Any]:
        return {
            "answer_text": state.parsed.text if state.parsed else "",
            "claims": self.claims(state),
            "scorecard": scorecard(state, self.ledger),
            "cost": {
                "total_usd": round(self.ledger.spent, 4),
                "cap_usd": self.ledger.cap_usd,
                "by_node": [
                    {"node": t.node, "calls": t.calls, "usd": round(t.usd, 4)}
                    for t in self.ledger.by_node()
                ],
            },
        }
