"""The M1 pipeline as a LangGraph graph: seven nodes in a straight line.

Each node reads the run state, does one job, and returns only the fields it filled in.
"""

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
from evidentia.llm import LLM, PLAN_SYSTEM, new_tag, plan_prompt, write_prompt, write_system
from evidentia.quote_check import check_claims
from evidentia.schemas import Draft, Plan, RunState
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
}
ORDER = list(TIMEOUTS)

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

    async def retrieve(self, state: RunState) -> dict[str, Any]:
        if not state.passages_indexed:
            return {"passages": []}
        vector = await self.d.embedder.embed_query("retrieve", state.question)
        candidates = await self.d.store.hybrid(
            state.run_id, state.question, vector, self.s.retrieve_limit
        )
        best = await self.d.embedder.rerank(
            "retrieve", state.question, candidates, self.s.rerank_top_k
        )
        return {"passages": best}

    async def write(self, state: RunState, config: RunnableConfig) -> dict[str, Any]:
        if not state.passages:
            return {"claims": []}
        tag = new_tag()
        draft = await self.d.llm.structured(
            node="write",
            model=self.s.writer_model,
            effort=self.s.writer_effort,
            max_tokens=self.s.writer_max_tokens,
            system=write_system(tag),
            user=write_prompt(state.question, state.passages, tag, self.s.max_claims),
            schema=Draft,
            config=config,
        )
        return {"claims": draft.claims[: self.s.max_claims]}

    async def quote_check(self, state: RunState) -> dict[str, Any]:
        checked = check_claims(state.claims, state.sources, self.s.min_quote_chars)
        return {"checked": checked}


def build_graph(deps: Deps):
    nodes = Nodes(deps)
    graph = StateGraph(RunState)
    for name in ORDER:
        graph.add_node(
            name,
            getattr(nodes, name),
            timeout=TIMEOUTS[name],
            retry_policy=RetryPolicy(max_attempts=2),
        )
    for before, after in zip([START, *ORDER], [*ORDER, END], strict=True):
        graph.add_edge(before, after)
    return graph.compile()


async def run_question(question: str, deps: Deps, on_update: OnUpdate | None = None) -> RunState:
    """Run the whole pipeline once. `on_update` is called as each node finishes."""
    state = RunState(run_id=uuid.uuid4().hex, question=question)
    graph = build_graph(deps)
    config: RunnableConfig = {"callbacks": deps.tracer.callbacks(), "run_name": "evidentia"}
    run_input = {"question": question, "run_id": state.run_id}
    with deps.tracer.span("evidentia.run", "span", run_input) as root:
        async for mode, chunk in graph.astream(state, config, stream_mode=["updates", "values"]):
            if mode == "values":
                state = RunState.model_validate(chunk)
            elif on_update:
                for node, update in chunk.items():
                    on_update(node, update or {})
        verified = sum(c.status == "verified" for c in state.checked)
        root.update(
            output={"claims": len(state.checked), "verified": verified},
            metadata={"usd": deps.ledger.spent},
        )
        state.trace_id = deps.tracer.trace_id()
        state.trace_url = deps.tracer.trace_url()
    return state
