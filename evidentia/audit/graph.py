"""The audit as a LangGraph graph (D-037, D-038, D-039).

    parse -> split -> fetch -+-> find -> quote_check -> check -+-> combine
                             +-> page_check -------------------+

parse, quote_check and combine are code. split, find, check and page_check are model calls.
find, quote check and check are the quote judge; page_check is the page judge, and the two run
at the same time. combine waits for both and merges them. Each node returns only
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
    page_blocks,
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
    page_call,
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
    "page_check": 420,
    "combine": 10,
}
PATH = list(TIMEOUTS)

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
        # (claim, url) -> the passages, shared by both judges even while they run at once
        self._passages: dict[tuple[str, str], asyncio.Task[list[Passage]]] = {}
        # One random data-block tag for the whole audit, so prompts about the same page are
        # identical up to the claim and can be cached. Page authors still cannot guess it.
        self.tag = new_tag("page")

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
        """Runs alongside the quote judge, so it writes its own field, not `results`."""
        if not self.s.audit_two_judges:
            return {"page_verdicts": {}}
        by_url = {s.url: s for s in state.sources}
        todo = [i for i, r in enumerate(state.results) if r.skipped is None]

        async def one(i: int) -> dict[str, Any]:
            result = state.results[i]
            claim = state.claims[result.claim].claim
            return await self.page_verdict(claim, by_url[result.url], state.run_id, config)

        verdicts = await asyncio.gather(*(one(i) for i in todo))
        return {"page_verdicts": dict(zip(todo, verdicts, strict=True))}

    async def combine(self, state: AuditState) -> dict[str, Any]:
        """Both judges are done: put the page judge's answers next to the quote judge's."""
        results = [
            r.model_copy(update=state.page_verdicts.get(i, {})) for i, r in enumerate(state.results)
        ]
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
            self._passages[key] = asyncio.create_task(self._passages_for(claim, source, run_id))
        return await self._passages[key]

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
        tag = self.tag
        system = FIND_SYSTEM.format(tag=tag, max_quotes=self.s.audit_max_quotes)
        try:
            async with self.gate:
                return await self.d.llm.structured(
                    node="find",
                    model=self.s.finder_model,
                    effort=self.s.finder_effort,
                    max_tokens=self.s.finder_max_tokens,
                    system=system,
                    prefix=page_blocks(passages, tag) if self.s.audit_prompt_cache else None,
                    user=find_prompt(claim, passages, tag, with_page=not self.s.audit_prompt_cache),
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
        """The page judge's score and verdict, as fields of a PageResult (D-038, D-039)."""
        passages = await self.passages_for(claim, source, run_id)
        tag = self.tag
        cache = self.s.audit_prompt_cache
        system = PAGE_JUDGE_SYSTEM.format(tag=tag)
        prefix = page_blocks(passages, tag) if cache else None
        user = page_judge_prompt(claim, passages, tag, with_page=not cache)
        if self.s.page_judge_probability:
            score, reason = await self._page_probability(system, prefix, user)
        else:
            score, reason = await self._page_votes(system, prefix, user, config)
        verdict = page_call(score, self.s.audit_t_supported, self.s.audit_t_flag)
        return {"page_judged": verdict, "page_reason": reason, "page_score": score}

    async def _page_votes(
        self, system: str, prefix: str | None, user: str, config: RunnableConfig | None
    ) -> tuple[float | None, str]:
        """The share of the votes that say supported; votes that fail are left out."""
        model = self.s.page_judge_model

        async def vote() -> PageJudgement | None:
            try:
                async with self.gate:
                    return await self.model_for(model).structured(
                        node="page_check",
                        model=model,
                        effort=self.s.page_judge_effort,
                        max_tokens=self.s.page_judge_max_tokens,
                        system=system,
                        prefix=prefix,
                        user=user,
                        schema=PageJudgement,
                        config=config,
                    )
            except ModelStopped:
                return None

        votes = [
            v for v in await asyncio.gather(*(vote() for _ in range(self.s.page_judge_votes))) if v
        ]
        if not votes:
            return None, NO_PAGE_JUDGE
        score = sum(v.supported for v in votes) / len(votes)
        majority = next(v for v in votes if v.supported == (score >= 0.5))
        return score, majority.reason

    async def _page_probability(
        self, system: str, prefix: str | None, user: str
    ) -> tuple[float | None, str]:
        model = self.s.page_judge_model
        llm = self.model_for(model)
        if not isinstance(llm, OpenAILLM):
            raise ValueError(f"page_judge_probability needs an OpenAI model, not {model}")
        try:
            async with self.gate:
                judgement, score = await llm.probability(
                    node="page_check",
                    model=model,
                    max_tokens=self.s.page_judge_max_tokens,
                    system=system,
                    prefix=prefix,
                    user=user,
                    schema=PageJudgement,
                )
        except ModelStopped:
            return None, NO_PAGE_JUDGE
        return score, judgement.reason

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
            defer=name == "combine",  # waits until both judges have finished
        )
    edges = [
        (START, "parse"),
        ("parse", "split"),
        ("split", "fetch"),
        ("fetch", "find"),
        ("find", "quote_check"),
        ("quote_check", "check"),
        ("check", "combine"),
        ("fetch", "page_check"),
        ("page_check", "combine"),
        ("combine", END),
    ]
    for before, after in edges:
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
