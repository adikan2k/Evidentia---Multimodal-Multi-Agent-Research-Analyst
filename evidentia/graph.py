"""The pipeline as a LangGraph graph.

    plan -> search -> fetch -> index -> retrieve -> write -> quote_check -> check
                                                                 ^            |
                                                                 |     any claim failed and
                                                                 |     no repair round yet?
                                                                 |            |
                                               revise <- reretrieve <- rewrite   (else: done)

Each node reads the run state, does one job, and returns only the fields it filled in.
"""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from evidentia.chunk import make_passages
from evidentia.config import Settings
from evidentia.cost import Ledger
from evidentia.embed import Embedder
from evidentia.fetch import Fetcher
from evidentia.llm import (
    CHECK_SYSTEM,
    LLM,
    PLAN_SYSTEM,
    REVISE_SYSTEM,
    REWRITE_SYSTEM,
    WRITE_SYSTEM,
    ModelStopped,
    check_prompt,
    new_tag,
    plan_prompt,
    revise_prompt,
    rewrite_prompt,
    with_tag,
    write_prompt,
)
from evidentia.quote_check import check_quotes
from evidentia.schemas import (
    CheckedClaim,
    Draft,
    Judgement,
    Passage,
    Plan,
    Repair,
    RepairQueries,
    Revision,
    RunState,
)
from evidentia.search import Searcher
from evidentia.store import Store
from evidentia.tracing import Tracer

# Seconds each node may run before LangGraph cancels it.
TIMEOUTS = {
    "plan": 180,
    "search": 90,
    "fetch": 180,
    "index": 240,
    "retrieve": 120,
    "write": 420,
    "quote_check": 30,
    "check": 300,
    "rewrite": 120,
    "reretrieve": 180,
    "revise": 420,
}
MAIN_PATH = ["plan", "search", "fetch", "index", "retrieve", "write", "quote_check", "check"]
REPAIR_PATH = ["rewrite", "reretrieve", "revise"]

NO_BACKING = "a second search of the fetched pages found nothing that backs it"

OnUpdate = Callable[[str, dict[str, Any]], None]


@dataclass
class Deps:
    """Everything the nodes need from outside. Tests pass fakes here."""

    settings: Settings
    ledger: Ledger
    tracer: Tracer
    llm: LLM
    searcher: Searcher
    fetcher: Fetcher
    embedder: Embedder
    store: Store


class Nodes:
    def __init__(self, deps: Deps) -> None:
        self.d = deps
        self.s = deps.settings

    async def plan(self, state: RunState, config: RunnableConfig) -> dict[str, Any]:
        plan = await self.d.llm.structured(
            node="plan",
            model=self.s.planner_model,
            effort=self.s.planner_effort,
            max_tokens=self.s.planner_max_tokens,
            system=PLAN_SYSTEM,
            user=plan_prompt(state.question, self.s.max_queries),
            schema=Plan,
            config=config,
        )
        queries = list(dict.fromkeys(q.strip() for q in plan.queries if q.strip()))
        return {"queries": queries[: self.s.max_queries] or [state.question]}

    async def search(self, state: RunState) -> dict[str, Any]:
        return {"hits": await self.d.searcher.search("search", state.queries)}

    async def fetch(self, state: RunState) -> dict[str, Any]:
        sources, skipped = await self.d.fetcher.fetch_all(state.hits)
        return {"sources": sources, "skipped": skipped}

    async def index(self, state: RunState) -> dict[str, Any]:
        passages = [p for source in state.sources for p in make_passages(source, state.run_id)]
        if passages:
            vectors = await self.d.embedder.embed_documents("index", [p.text for p in passages])
            await self.d.store.ensure_collection()
            await self.d.store.upsert(state.run_id, passages, vectors)
        return {"passages_indexed": len(passages)}

    async def _find(self, node: str, run_id: str, query: str, top_k: int) -> list[Passage]:
        """Hybrid search over this run's passages, then rerank and keep the best `top_k`."""
        vector = await self.d.embedder.embed_query(node, query)
        candidates = await self.d.store.hybrid(run_id, query, vector, self.s.retrieve_limit)
        return await self.d.embedder.rerank(node, query, candidates, top_k)

    async def retrieve(self, state: RunState) -> dict[str, Any]:
        if not state.passages_indexed:
            return {"passages": []}
        best = await self._find("retrieve", state.run_id, state.question, self.s.rerank_top_k)
        return {"passages": best}

    async def write(self, state: RunState, config: RunnableConfig) -> dict[str, Any]:
        if not state.passages:
            return {"claims": [], "checked": []}
        tag = new_tag()
        draft = await self.d.llm.structured(
            node="write",
            model=self.s.writer_model,
            effort=self.s.writer_effort,
            max_tokens=self.s.writer_max_tokens,
            system=with_tag(WRITE_SYSTEM, tag),
            user=write_prompt(state.question, state.passages, tag, self.s.max_claims),
            schema=Draft,
            config=config,
        )
        claims = draft.claims[: self.s.max_claims]
        return {"claims": claims, "checked": [CheckedClaim(**c.model_dump()) for c in claims]}

    async def quote_check(self, state: RunState) -> dict[str, Any]:
        checked = check_quotes(state.checked, state.sources, self.s.min_quote_chars)
        return {"checked": checked}

    async def check(self, state: RunState, config: RunnableConfig) -> dict[str, Any]:
        """Ask the checker about every claim whose quote is on the page and has no verdict yet."""
        waiting = [i for i, c in enumerate(state.checked) if c.quote_found and c.verdict is None]
        judged = await asyncio.gather(*(self._judge(state.checked[i], config) for i in waiting))
        checked = list(state.checked)
        for i, claim in zip(waiting, judged, strict=True):
            checked[i] = claim
        return {"checked": checked}

    async def _judge(self, claim: CheckedClaim, config: RunnableConfig) -> CheckedClaim:
        tag = new_tag("quote")
        try:
            judgement = await self.d.llm.structured(
                node="check",
                model=self.s.checker_model,
                effort=self.s.checker_effort,
                max_tokens=self.s.checker_max_tokens,
                system=with_tag(CHECK_SYSTEM, tag),
                # The claim and the quote are all the checker ever sees.
                user=check_prompt(claim.text, claim.quote, tag),
                schema=Judgement,
                config=config,
            )
        except ModelStopped:
            # No verdict means the claim cannot be labelled supported or partial.
            return claim.model_copy(update={"reason": "the checker did not return a verdict"})
        reason = "" if judgement.label == "supported" else judgement.reason
        return claim.model_copy(update={"verdict": judgement.label, "reason": reason})

    def route(self, state: RunState) -> str:
        """After the checker: repair failed claims once, otherwise finish."""
        rounds_left = state.round < self.s.max_repair_rounds
        return "rewrite" if rounds_left and any(c.failed for c in state.checked) else END

    async def rewrite(self, state: RunState, config: RunnableConfig) -> dict[str, Any]:
        failed = [i for i, c in enumerate(state.checked) if c.failed]
        answer = await self.d.llm.structured(
            node="rewrite",
            model=self.s.reader_model,
            effort="low",
            max_tokens=self.s.reader_max_tokens,
            system=REWRITE_SYSTEM,
            user=rewrite_prompt(state.question, [state.checked[i] for i in failed]),
            schema=RepairQueries,
            config=config,
        )
        queries = [q.strip() for q in answer.queries]
        repairs = [
            # If the model returned too few queries, the claim itself is a workable query.
            Repair(index=i, query=(queries[n] if n < len(queries) else "") or state.checked[i].text)
            for n, i in enumerate(failed)
        ]
        return {"repairs": repairs, "round": state.round + 1}

    async def reretrieve(self, state: RunState) -> dict[str, Any]:
        found = await asyncio.gather(
            *(
                self._find("reretrieve", state.run_id, r.query, self.s.repair_top_k)
                for r in state.repairs
            )
        )
        repairs = [
            r.model_copy(update={"passages": p}) for r, p in zip(state.repairs, found, strict=True)
        ]
        return {"repairs": repairs}

    async def revise(self, state: RunState, config: RunnableConfig) -> dict[str, Any]:
        revised = await asyncio.gather(
            *(self._revise(state.checked[r.index], r, config) for r in state.repairs)
        )
        checked = list(state.checked)
        for repair, claim in zip(state.repairs, revised, strict=True):
            checked[repair.index] = claim
        return {"checked": checked}

    async def _revise(
        self, claim: CheckedClaim, repair: Repair, config: RunnableConfig
    ) -> CheckedClaim:
        """A fresh claim to be checked again, or the old one marked as having no backing."""
        reason = "; ".join(part for part in (claim.reason, NO_BACKING) if part)
        gave_up = claim.model_copy(update={"reason": reason})
        if not repair.passages:
            return gave_up
        tag = new_tag()
        try:
            revision = await self.d.llm.structured(
                node="revise",
                model=self.s.writer_model,
                effort=self.s.writer_effort,
                max_tokens=self.s.reviser_max_tokens,
                system=with_tag(REVISE_SYSTEM, tag),
                user=revise_prompt(claim, repair.passages, tag),
                schema=Revision,
                config=config,
            )
        except ModelStopped:
            return gave_up
        if not (revision.backed and revision.text.strip() and revision.quote.strip()):
            return gave_up
        return CheckedClaim(
            text=revision.text, quote=revision.quote, source_id=revision.source_id, revised=True
        )


def build_graph(deps: Deps, start: str = "plan"):
    """`start` lets the evals skip search and fetch and begin from saved pages."""
    nodes = Nodes(deps)
    main_path = MAIN_PATH[MAIN_PATH.index(start) :]
    graph = StateGraph(RunState)
    for name in [*MAIN_PATH, *REPAIR_PATH]:
        graph.add_node(
            name,
            getattr(nodes, name),
            timeout=TIMEOUTS[name],
            retry_policy=RetryPolicy(max_attempts=2),
        )
    for before, after in zip([START, *main_path], main_path, strict=False):
        graph.add_edge(before, after)
    graph.add_conditional_edges("check", nodes.route, ["rewrite", END])
    # The repair path ends back at the quote check, so revised claims face both checks again.
    for before, after in zip(REPAIR_PATH, [*REPAIR_PATH[1:], "quote_check"], strict=True):
        graph.add_edge(before, after)
    return graph.compile()


async def run_question(
    question: str,
    deps: Deps,
    on_update: OnUpdate | None = None,
    initial: RunState | None = None,
    start: str = "plan",
) -> RunState:
    """Run the whole pipeline once. `on_update` is called as each node finishes."""
    state = initial or RunState(run_id=uuid.uuid4().hex, question=question)
    graph = build_graph(deps, start)
    config: RunnableConfig = {"callbacks": deps.tracer.callbacks(), "run_name": "evidentia"}
    run_input = {"question": question, "run_id": state.run_id}
    with deps.tracer.span("evidentia.run", "span", run_input) as root:
        async for mode, chunk in graph.astream(state, config, stream_mode=["updates", "values"]):
            if mode == "values":
                state = RunState.model_validate(chunk)
            elif on_update:
                for node, update in chunk.items():
                    on_update(node, update or {})
        labels = [c.label for c in state.checked]
        root.update(
            output={label: labels.count(label) for label in ("supported", "partial", "unverified")},
            metadata={"usd": deps.ledger.spent, "repair_rounds": state.round},
        )
        state.trace_id = deps.tracer.trace_id()
        state.trace_url = deps.tracer.trace_url()
    return state
