"""Show an audit: each claim with its label and the words it rests on, then the scorecard.

Every number here is counted from the audit's own results.
"""

import json
from collections import Counter
from typing import Any

from rich.console import Console
from rich.text import Text

from evidentia.audit.schemas import (
    DEAD,
    LABEL_TEXT,
    AuditLabel,
    AuditState,
    PageResult,
    claim_label,
    disputed,
)
from evidentia.cost import Ledger
from evidentia.report import Reporter, page_label

ORDER: list[AuditLabel] = list(LABEL_TEXT)  # type: ignore[arg-type]
STYLE = {
    "supported": "bold green",
    "partial": "bold yellow",
    "contradicted": "bold magenta",
    "needs_human": "bold cyan",
    "not_found": "bold red",
    "dead_link": "bold red",
    "unchecked": "bold blue",
    "uncited": "bold white",
}


def results_by_claim(state: AuditState) -> list[list[PageResult]]:
    grouped: list[list[PageResult]] = [[] for _ in state.claims]
    for r in state.results:
        grouped[r.claim].append(r)
    return grouped


def claim_views(state: AuditState) -> list[dict[str, Any]]:
    views = []
    for claim, results in zip(state.claims, results_by_claim(state), strict=True):
        views.append(
            claim.model_dump()
            | {
                "label": claim_label(claim, results),
                "disputed": disputed(results),
                "pages": [
                    r.model_dump(exclude={"offered", "claim"})
                    | {"label": r.label, "quote_label": r.quote_label}
                    for r in results
                ],
            }
        )
    return views


def scorecard(state: AuditState, ledger: Ledger) -> dict[str, Any]:
    labels = Counter(v["label"] for v in claim_views(state))
    cited = len(state.claims) - labels["uncited"]
    dead = {s.url for s in state.skipped if s.reason in DEAD}
    # D-039: a failed citation is "not on the cited page" or "contradicted". Partial (the main
    # point backed, a detail not) is counted apart and never as a failure.
    failed = labels["not_found"] + labels["contradicted"]
    with_verdict = failed + labels["supported"] + labels["partial"]
    return {
        "claims": len(state.claims),
        "labels": {label: labels[label] for label in ORDER},
        "cited_claims": cited,
        "claims_with_a_verdict": with_verdict,
        "failed_citations": failed,
        "failed_share_of_verdicts": round(failed / with_verdict, 4) if with_verdict else None,
        "partly_backed": labels["partial"],
        "supported_share_of_cited": round(labels["supported"] / cited, 4) if cited else None,
        "pages_cited": len(state.sources) + len(state.skipped),
        "pages_read": len(state.sources),
        "dead_links": len(dead),
        "sentences_not_located": len(state.not_located),
        "claims_over_limit": state.claims_over_limit,
        "usd": round(ledger.spent, 6),
        "usd_per_claim": round(ledger.spent / len(state.claims), 6) if state.claims else None,
    }


def to_json(state: AuditState, ledger: Ledger) -> str:
    body = {
        "run_id": state.run_id,
        "answer_text": state.parsed.text if state.parsed else "",
        "citations": [c.model_dump() for c in state.parsed.citations] if state.parsed else [],
        "claims": claim_views(state),
        "skipped": [s.model_dump() for s in state.skipped],
        "scorecard": scorecard(state, ledger),
        "cost": {
            "cap_usd": ledger.cap_usd,
            "by_node": [t.model_dump() for t in ledger.by_node()],
        },
        "trace_id": state.trace_id,
        "trace_url": state.trace_url,
    }
    return json.dumps(body, indent=2, ensure_ascii=False)


def describe(node: str, update: dict[str, Any]) -> str:
    if node == "parse":
        parsed = update["parsed"]
        return f"found {len(parsed.citations)} cited addresses"
    if node == "split":
        line = f"split the answer into {len(update['claims'])} claims"
        if update.get("not_located"):
            line += f" ({len(update['not_located'])} dropped: sentence not in the answer)"
        return line
    if node == "fetch":
        reasons = Counter(s.reason for s in update["skipped"])
        line = f"read {len(update['sources'])} pages"
        if reasons:
            line += ", not read: " + ", ".join(f"{n} {r}" for r, n in reasons.most_common())
        return line
    if node == "find":
        offered = sum(bool(r.offered) for r in update["results"])
        return f"found candidate quotes for {offered} of {len(update['results'])} claim-page pairs"
    if node == "quote_check":
        exact = sum(bool(r.quotes) for r in update["results"])
        return f"{exact} pairs have quotes that are word for word on the page"
    if node == "check":
        labels = Counter(r.quote_label for r in update["results"])
        return "quote judge: " + ", ".join(
            f"{n} {LABEL_TEXT[label]}" for label, n in labels.most_common()
        )
    if node == "page_check":
        if "page_verdicts" not in update:
            return "one judge only"
        verdicts = update["page_verdicts"]
        if not verdicts:
            return "no page was read, so nothing to judge"
        calls = Counter(v["page_judged"] for v in verdicts.values())
        return "page judge: " + ", ".join(f"{n} {call}" for call, n in calls.most_common())
    if node == "combine":
        labels = Counter(r.label for r in update["results"])
        return "both judges: " + ", ".join(
            f"{n} {LABEL_TEXT[label]}" for label, n in labels.most_common()
        )
    return ""


class AuditReporter:
    def __init__(self, console: Console) -> None:
        self.console = console

    def on_update(self, node: str, update: dict[str, Any]) -> None:
        line = Text(f"  {node:<12}", style="cyan")
        line.append(describe(node, update))
        self.console.print(line)

    def final(self, state: AuditState, ledger: Ledger) -> None:
        for number, view in enumerate(claim_views(state), start=1):
            self._claim(number, view)
        card = scorecard(state, ledger)
        self.console.print()
        counts = ", ".join(f"{n} {LABEL_TEXT[label]}" for label, n in card["labels"].items() if n)
        self.console.print(Text(f"{card['claims']} claims: {counts}", style="bold"))
        if card["failed_share_of_verdicts"] is not None:
            self.console.print(
                f"Failed outright (not on the cited page, or contradicted): "
                f"{card['failed_citations']} of {card['claims_with_a_verdict']} claims with a "
                f"verdict ({card['failed_share_of_verdicts']:.0%}). Partly backed: "
                f"{card['partly_backed']}."
            )
        if card["supported_share_of_cited"] is not None:
            share = card["supported_share_of_cited"]
            self.console.print(f"Supported, of the claims that cite a page: {share:.0%}")
        self.console.print(
            f"Pages cited: {card['pages_cited']}, read: {card['pages_read']}, "
            f"dead links: {card['dead_links']}"
        )
        Reporter(self.console).costs(ledger)
        read = sum(t.cache_read for t in ledger.by_node())
        written = sum(t.cache_write for t in ledger.by_node())
        if read or written:
            self.console.print(
                Text(f"Prompt cache: {read:,} tokens read, {written:,} written", style="dim")
            )
        if state.trace_url or state.trace_id:
            self.console.print(Text(f"Trace: {state.trace_url or state.trace_id}", style="dim"))

    def _claim(self, number: int, view: dict[str, Any]) -> None:
        head = Text(f"\n{number:>2}. ")
        head.append(LABEL_TEXT[view["label"]].upper(), style=STYLE[view["label"]])
        if view["disputed"]:
            head.append("  (another cited page contradicts it)", style="magenta")
        head.append(f"  {view['sentence']}")
        self.console.print(head)
        if view["claim"] != view["sentence"]:
            self.console.print(Text(f"    Checked as: {view['claim']}", style="dim"))
        for page in view["pages"]:
            where = ""
            if page["quotes"] and page["quotes"][0]["pages"]:
                where = f"  ({page_label(page['quotes'][0]['pages'])})"
            line = Text(f"    [{LABEL_TEXT[page['label']]}] ", style=STYLE[page["label"]])
            line.append(f"{page['url']}{where}", style="blue")
            self.console.print(line)
            for quote in page["quotes"]:
                self.console.print(Text(f'      "{quote["text"]}"', style="italic"))
            why = page["skipped"] or page["reason"]
            if why:
                self.console.print(Text(f"      Quote judge: {why}", style="yellow"))
            if page["page_reason"]:
                score = page["page_score"]
                shown = "" if score is None else f" (score {score:.2f})"
                text = f"      Page judge{shown}: {page['page_reason']}"
                self.console.print(Text(text, style="yellow"))
