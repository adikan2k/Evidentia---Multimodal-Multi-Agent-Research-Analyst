"""The audit as a LangGraph graph (D-037, D-038).

    parse -> split -> fetch -> find -> quote_check -> check -> page_check

parse and quote_check are code. split, find, check and page_check are model calls. find, quote
check and check are the quote judge; page_check is the page judge. Each node returns only
the fields it filled in, as in the research pipeline.
"""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from evidentia.audit.citations import citations_for, locate, parse_answer
from evidentia.audit.prompts import (
    AUDIT_CHECK_SYSTEM,
    CONTEXT_RULE,
    FIND_SYSTEM,
    PAGE_JUDGE_SYSTEM,
    SPLIT_SYSTEM,
    audit_check_prompt,
    find_prompt,
    page_judge_prompt,
    split_prompt,
)
from evidentia.audit.schemas import (
    AuditClaim,
    AuditJudgement,
    AuditState,
    Evidence,
    PageJudgement,
    PageResult,
    Quote,
    Split,
)
from evidentia.chunk import make_passages
from evidentia.config import Settings
from evidentia.cost import Ledger
from evidentia.embed import Embedder
from evidentia.fetch import Fetcher
from evidentia.llm import LLM, ModelStopped, new_tag
from evidentia.openai_llm import OpenAILLM, is_openai_model
from evidentia.quote_check import collapse_whitespace, find_quote
from evidentia.schemas import Passage, SearchHit, SkippedPage, Source
from evidentia.tracing import Tracer

TIMEOUTS = {
    "parse": 10,
    "split": 180,
    "fetch": 240,
    "find": 420,
    "quote_check": 30,
    "check": 300,
    "page_check": 300,
}
PATH = list(TIMEOUTS)
JUDGED = ("supported", "partial", "contradicted", "not_found")  # quote labels the page judge sees

OVER_LIMIT = "over the page limit for one audit"
NO_FINDER = "the evidence finder did not answer"
NO_CHECKER = "the checker did not return a verdict"
NOT_EXACT = "no quote the finder gave is word for word on the page"
NO_PAGE_JUDGE = "the page judge did not answer"

OnUpdate = Callable[[str, dict[str, Any]], None]


@dataclass
class AuditDeps:
    settings: Settings
    ledger: Ledger
    tracer: Tracer
    llm: LLM
    fetcher: Fetcher
    embedder: Embedder
    openai: OpenAILLM | None = None  # made when a configured model is an OpenAI one


def match_quotes(offered: list[str], source: Source, min_chars: int) -> list[Quote]:
    """The quotes that are exact spans of the page (rule 8), each once."""
    quotes: dict[tuple[int, int], Quote] = {}
    for text in offered:
        if len(collapse_whitespace(text)) < min_chars:
            continue
        span = find_quote(text, source.text)
        if span and span not in quotes:
            start, end = span
            quotes[span] = Quote(
                text=source.text[start:end], start=start, end=end, pages=source.pages_of(*span)
            )
    return list(quotes.values())


def quote_context(source: Source, quote: Quote, limit: int) -> str:
    """The paragraph a quote sits in, cut to about `limit` characters around the quote."""
    text = source.text
    start = text.rfind("\n", 0, quote.start) + 1
    end = text.find("\n", quote.end)
    end = len(text) if end < 0 else end
    if end - start > limit:
        spare = max(limit - (quote.end - quote.start), 0) // 2
        start, end = max(start, quote.start - spare), min(end, quote.end + spare)
    return text[start:end]


class AuditNodes:
    def __init__(self, deps: AuditDeps) -> None:
        self.d = deps
        self.s = deps.settings
        self.gate = asyncio.Semaphore(self.s.audit_concurrency)
        self._passages: dict[tuple[str, str], list[Passage]] = {}  # (claim, url) -> passages

    async def parse(self, state: AuditState) -> dict[str, Any]:
        return {"parsed": parse_answer(state.answer)}

    async def split(self, state: AuditState, config: RunnableConfig) -> dict[str, Any]:
        parsed = state.parsed
        if parsed is None or not parsed.text.strip():
            return {"claims": []}
        tag = new_tag("answer")
        split = await self.d.llm.structured(
            node="split",
            model=self.s.splitter_model,
            effort="low",
            max_tokens=self.s.splitter_max_tokens,
            system=SPLIT_SYSTEM.format(tag=tag),
            user=split_prompt(parsed.text, tag, self.s.audit_max_claims),
            schema=Split,
            config=config,
        )
        claims, not_located = [], []
        for item in split.claims:
            span = locate(item.sentence, parsed.text)
            if span is None or not item.claim.strip():
                not_located.append(item.sentence)
                continue
            start, end = span
            claims.append(
                AuditClaim(
                    sentence=parsed.text[start:end],
                    start=start,
                    end=end,
                    claim=item.claim.strip(),
                    citation_ids=citations_for(parsed, start, end),
                )
            )
        limit = self.s.audit_max_claims
        return {
            "claims": claims[:limit],
            "not_located": not_located,
            "claims_over_limit": max(len(claims) - limit, 0),
        }

    async def fetch(self, state: AuditState) -> dict[str, Any]:
        urls = {c.id: c.url for c in state.parsed.citations} if state.parsed else {}
        cited = [urls[cid] for claim in state.claims for cid in claim.citation_ids]
        wanted = list(dict.fromkeys(cited))
        limit = self.s.audit_max_pages
        sources, skipped = await self.d.fetcher.fetch_all(
            [SearchHit(url=u) for u in wanted[:limit]]
        )
        skipped += [SkippedPage(url=u, reason=OVER_LIMIT) for u in wanted[limit:]]
        why = {s.url: s.reason for s in skipped}
        results = [
            PageResult(claim=i, citation_id=cid, url=urls[cid], skipped=why.get(urls[cid]))
            for i, claim in enumerate(state.claims)
            for cid in claim.citation_ids
        ]
        return {"sources": sources, "skipped": skipped, "results": results}

    async def find(self, state: AuditState, config: RunnableConfig) -> dict[str, Any]:
        by_url = {s.url: s for s in state.sources}
        todo = [i for i, r in enumerate(state.results) if r.skipped is None and r.stance is None]

        async def one(i: int) -> PageResult:
            result = state.results[i]
            source = by_url[result.url]
            claim = state.claims[result.claim].claim
            evidence = await self.find_evidence(claim, source, state.run_id, config)
            if evidence is None:
                return result.model_copy(update={"reason": NO_FINDER})
            return result.model_copy(update=self.offered(evidence))

        found = await asyncio.gather(*(one(i) for i in todo))
        results = list(state.results)
        for i, result in zip(todo, found, strict=True):
            results[i] = result
        return {"results": results}

    async def quote_check(self, state: AuditState) -> dict[str, Any]:
        by_url = {s.url: s for s in state.sources}
        results = []
        for r in state.results:
            if r.offered and not r.quotes:
                quotes = match_quotes(r.offered, by_url[r.url], self.s.min_quote_chars)
                r = r.model_copy(update={"quotes": quotes, "reason": "" if quotes else NOT_EXACT})
            results.append(r)
        return {"results": results}

    async def check(self, state: AuditState, config: RunnableConfig) -> dict[str, Any]:
        todo = [i for i, r in enumerate(state.results) if r.quotes and r.verdict is None]

        by_url = {s.url: s for s in state.sources}

        async def one(i: int) -> PageResult:
            result = state.results[i]
            claim = state.claims[result.claim].claim
            judgement = await self.judge(claim, result.quotes, by_url[result.url], config)
            if judgement is None:
                return result.model_copy(update={"reason": NO_CHECKER})
            return result.model_copy(
                update={"verdict": judgement.label, "reason": judgement.reason}
            )

        judged = await asyncio.gather(*(one(i) for i in todo))
        results = list(state.results)
        for i, result in zip(todo, judged, strict=True):
            results[i] = result
        return {"results": results}

    async def page_check(self, state: AuditState, config: RunnableConfig) -> dict[str, Any]:
        if not self.s.audit_two_judges:
            return {}
        by_url = {s.url: s for s in state.sources}
        todo = [
            i
            for i, r in enumerate(state.results)
            if r.page_judged is None and r.quote_label in JUDGED
        ]

        async def one(i: int) -> PageResult:
            result = state.results[i]
            claim = state.claims[result.claim].claim
            verdict = await self.page_verdict(claim, by_url[result.url], state.run_id, config)
            return result.model_copy(update=verdict)

        judged = await asyncio.gather(*(one(i) for i in todo))
        results = list(state.results)
        for i, result in zip(todo, judged, strict=True):
            results[i] = result
        return {"results": results}

    # The steps for one claim and one page, shared by the graph and the AggreFact eval.

    def model_for(self, model: str) -> LLM | OpenAILLM:
        if not is_openai_model(model):
            return self.d.llm
        if self.d.openai is None:
            self.d.openai = OpenAILLM(self.s, self.d.ledger)
        return self.d.openai

    def offered(self, evidence: Evidence) -> dict[str, Any]:
        quotes = [] if evidence.stance == "neither" else [q for q in evidence.quotes if q.strip()]
        return {"stance": evidence.stance, "offered": quotes[: self.s.audit_max_quotes]}

    async def passages_for(self, claim: str, source: Source, run_id: str) -> list[Passage]:
        """The whole page if it is short, else its best passages for this claim, in page order.

        Both judges see the same passages, so the reranker runs once per claim and page.
        """
        key = (claim, source.url)
        if key not in self._passages:
            self._passages[key] = await self._passages_for(claim, source, run_id)
        return self._passages[key]

    async def _passages_for(self, claim: str, source: Source, run_id: str) -> list[Passage]:
        if len(source.text) <= self.s.audit_page_chars:
            whole = Passage(
                id="whole",
                source_id=source.id,
                url=source.url,
                start=0,
                end=len(source.text),
                text=source.text,
            )
            return [whole]
        passages = make_passages(source, run_id)
        best = await self.d.embedder.rerank("find", claim, passages, self.s.audit_top_passages)
        return sorted(best, key=lambda p: p.start)

    async def find_evidence(
        self, claim: str, source: Source, run_id: str, config: RunnableConfig | None
    ) -> Evidence | None:
        passages = await self.passages_for(claim, source, run_id)
        tag = new_tag("page")
        system = FIND_SYSTEM.format(tag=tag, max_quotes=self.s.audit_max_quotes)
        try:
            async with self.gate:
                return await self.d.llm.structured(
                    node="find",
                    model=self.s.finder_model,
                    effort=self.s.finder_effort,
                    max_tokens=self.s.finder_max_tokens,
                    system=system,
                    user=find_prompt(claim, passages, tag),
                    schema=Evidence,
                    config=config,
                )
        except ModelStopped:
            return None

    async def judge(
        self, claim: str, quotes: list[Quote], source: Source, config: RunnableConfig | None
    ) -> AuditJudgement | None:
        tag = new_tag("quote")
        system = AUDIT_CHECK_SYSTEM.format(tag=tag)
        contexts = None
        if self.s.audit_quote_context:
            system += CONTEXT_RULE.format(tag=tag)
            contexts = [quote_context(source, q, self.s.quote_context_chars) for q in quotes]
        try:
            async with self.gate:
                return await self.model_for(self.s.checker_model).structured(
                    node="check",
                    model=self.s.checker_model,
                    effort=self.s.checker_effort,
                    max_tokens=self.s.checker_max_tokens,
                    system=system,
                    # The claim and the quotes, plus their paragraphs if asked, are all the
                    # checker ever sees.
                    user=audit_check_prompt(claim, [q.text for q in quotes], tag, contexts),
                    schema=AuditJudgement,
                    config=config,
                )
        except ModelStopped:
            return None

    async def page_verdict(
        self, claim: str, source: Source, run_id: str, config: RunnableConfig | None
    ) -> dict[str, Any]:
        """The page judge's answer, as fields of a PageResult."""
        passages = await self.passages_for(claim, source, run_id)
        tag = new_tag("page")
        model = self.s.page_judge_model
        try:
            async with self.gate:
                judgement = await self.model_for(model).structured(
                    node="page_check",
                    model=model,
                    effort=self.s.page_judge_effort,
                    max_tokens=self.s.page_judge_max_tokens,
                    system=PAGE_JUDGE_SYSTEM.format(tag=tag),
                    user=page_judge_prompt(claim, passages, tag),
                    schema=PageJudgement,
                    config=config,
                )
        except ModelStopped:
            return {"page_judged": "no_answer", "page_reason": NO_PAGE_JUDGE}
        verdict = "supported" if judgement.supported else "not_supported"
        return {"page_judged": verdict, "page_reason": judgement.reason}

    async def assess(
        self, claim: str, source: Source, run_id: str, config: RunnableConfig | None = None
    ) -> PageResult:
        """The quote judge for one claim and one page: find, quote check and check."""
        result = PageResult(claim=0, citation_id="c1", url=source.url)
        evidence = await self.find_evidence(claim, source, run_id, config)
        if evidence is None:
            return result.model_copy(update={"reason": NO_FINDER})
        result = result.model_copy(update=self.offered(evidence))
        if not result.offered:
            return result
        quotes = match_quotes(result.offered, source, self.s.min_quote_chars)
        if not quotes:
            return result.model_copy(update={"reason": NOT_EXACT})
        judgement = await self.judge(claim, quotes, source, config)
        if judgement is None:
            return result.model_copy(update={"quotes": quotes, "reason": NO_CHECKER})
        update = {"quotes": quotes, "verdict": judgement.label, "reason": judgement.reason}
        return result.model_copy(update=update)


def build_audit_graph(deps: AuditDeps):
    nodes = AuditNodes(deps)
    graph = StateGraph(AuditState)
    for name in PATH:
        graph.add_node(
            name,
            getattr(nodes, name),
            timeout=TIMEOUTS[name],
            retry_policy=RetryPolicy(max_attempts=2),
        )
    for before, after in zip([START, *PATH], [*PATH, END], strict=True):
        graph.add_edge(before, after)
    return graph.compile()


async def run_audit(answer: str, deps: AuditDeps, on_update: OnUpdate | None = None) -> AuditState:
    """Audit one answer. `on_update` is called as each node finishes."""
    state = AuditState(run_id=uuid.uuid4().hex, answer=answer)
    graph = build_audit_graph(deps)
    config: RunnableConfig = {"callbacks": deps.tracer.callbacks(), "run_name": "evidentia-audit"}
    with deps.tracer.span("evidentia.audit", "span", {"run_id": state.run_id}) as root:
        async for mode, chunk in graph.astream(state, config, stream_mode=["updates", "values"]):
            if mode == "values":
                state = AuditState.model_validate(chunk)
            elif on_update:
                for node, update in chunk.items():
                    on_update(node, update or {})
        labels = [r.label for r in state.results]
        root.update(
            output={label: labels.count(label) for label in sorted(set(labels))},
            metadata={"usd": deps.ledger.spent, "claims": len(state.claims)},
        )
        state.trace_id = deps.tracer.trace_id()
        state.trace_url = deps.tracer.trace_url()
    return state
