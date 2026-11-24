"""Print a run: one line per finished node, then the claims, the costs and the trace.

Nothing here is decorative. Every line is built from what a node actually returned.
"""

import json
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from rich.console import Console
from rich.table import Table
from rich.text import Text

from evidentia.cost import Ledger
from evidentia.schemas import CheckedClaim, RunState

STATUS_STYLE = {"verified": "bold green", "unverified": "bold yellow"}


def _plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {many or word + 's'}"


def describe(node: str, update: dict[str, Any]) -> str:
    """One plain sentence about what a node just did."""
    if node == "plan":
        return f"wrote {_plural(len(update['queries']), 'search query', 'search queries')}"
    if node == "search":
        sites = {urlsplit(h.url).netloc for h in update["hits"]}
        return f"found {_plural(len(update['hits']), 'page')} on {_plural(len(sites), 'site')}"
    if node == "fetch":
        line = f"read {_plural(len(update['sources']), 'page')}"
        reasons = Counter(s.reason for s in update["skipped"])
        if reasons:
            why = ", ".join(f"{n} {reason}" for reason, n in reasons.most_common())
            line += f", skipped {len(update['skipped'])} ({why})"
        return line
    if node == "index":
        return f"indexed {_plural(update['passages_indexed'], 'passage')} (dense + BM25)"
    if node == "retrieve":
        return f"kept the best {_plural(len(update['passages']), 'passage')} after reranking"
    if node == "write":
        return f"wrote {_plural(len(update['claims']), 'claim')}"
    if node == "quote_check":
        verified = sum(c.status == "verified" for c in update["checked"])
        return f"{verified} verified, {len(update['checked']) - verified} unverified"
    return ""


def to_json(state: RunState, ledger: Ledger) -> str:
    result = {
        "run_id": state.run_id,
        "question": state.question,
        "queries": state.queries,
        "sources": [
            {"id": s.id, "url": s.url, "title": s.title, "chars": len(s.text)}
            for s in state.sources
        ],
        "skipped": [s.model_dump() for s in state.skipped],
        "claims": [c.model_dump() for c in state.checked],
        "cost": {
            "cap_usd": ledger.cap_usd,
            "total_usd": round(ledger.spent, 6),
            "by_node": [t.model_dump() for t in ledger.by_node()],
        },
        "trace_id": state.trace_id,
        "trace_url": state.trace_url,
    }
    return json.dumps(result, indent=2)


class Reporter:
    def __init__(self, console: Console) -> None:
        self.console = console

    def on_update(self, node: str, update: dict[str, Any]) -> None:
        line = Text(f"  {node:<12}", style="cyan")
        line.append(describe(node, update), style="default")
        self.console.print(line)
        if node == "plan":
            for query in update["queries"]:
                self.console.print(Text(f"{'':<16}{query}", style="dim"))

    def final(self, state: RunState, ledger: Ledger) -> None:
        self.console.print()
        self.console.print(Text(state.question, style="bold"))
        if not state.checked:
            self.console.print(Text(self._why_empty(state), style="yellow"))
        for number, claim in enumerate(state.checked, start=1):
            self._claim(number, claim)
        self.console.print()
        self.console.print(
            Text(
                "Verified means the quote is an exact span of the fetched page. Whether the "
                "quote supports the claim is not checked yet; that is the checker in M2.",
                style="dim",
            )
        )
        self.costs(ledger)
        if state.trace_url or state.trace_id:
            self.console.print(Text(f"Trace: {state.trace_url or state.trace_id}", style="dim"))

    def _why_empty(self, state: RunState) -> str:
        if not state.sources:
            return "No page could be read, so there is nothing to quote."
        return "The pages that were read did not support any claim."

    def _claim(self, number: int, claim: CheckedClaim) -> None:
        head = Text(f"\n{number:>2}. ")
        head.append(claim.status.upper(), style=STATUS_STYLE[claim.status])
        head.append(f"  {claim.text}")
        self.console.print(head)
        self.console.print(Text(f'    "{claim.quote}"', style="italic"))
        if claim.reason:
            self.console.print(Text(f"    Why unverified: {claim.reason}", style="yellow"))
        if claim.url:
            self.console.print(Text(f"    {claim.url}", style="blue"))

    def costs(self, ledger: Ledger) -> None:
        table = Table(title="Cost of this run", title_justify="left", show_edge=False)
        table.add_column("node")
        for column in ("calls", "tokens in", "tokens out", "USD"):
            table.add_column(column, justify="right")
        for t in ledger.by_node():
            table.add_row(
                t.node, str(t.calls), f"{t.input_tokens:,}", f"{t.output_tokens:,}", f"{t.usd:.4f}"
            )
        table.add_section()
        table.add_row("total", "", "", "", f"{ledger.spent:.4f}")
        self.console.print()
        self.console.print(table)
        self.console.print(Text(f"Cap per run: ${ledger.cap_usd:.2f}", style="dim"))
