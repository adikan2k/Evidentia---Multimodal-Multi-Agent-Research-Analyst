"""Build the claim-and-quote pairs that Aditya labels by hand (D-018).

About two thirds are real writer output. The rest are built so that all three labels are well
represented: the writer almost never produces an unsupported claim on its own.
"""

import asyncio
import random

from pydantic import BaseModel, Field

from evals.common import LABELS, PAIRS, eval_deps, load_pages, read_jsonl, write_jsonl
from evals.stats import SEED
from evals.systems import PIPELINE_RUNS
from evidentia.graph import Deps
from evidentia.llm import DATA_RULE, new_tag, with_tag
from evidentia.quote_check import find_quote

NATURAL = 100
BUILT = {"wrong_quote": 17, "changed_fact": 17, "added_detail": 16}

EDITS = {
    "changed_fact": "Rewrite the claim so that exactly one specific fact in it is different: a "
    "number, a date, a name, a place, or a direction such as rose or fell. The quote must no "
    "longer back that fact. Keep the rest of the wording as it is.",
    "added_detail": "Rewrite the claim by adding one specific, plausible detail that the quote "
    "does not state, such as a number, a date, a cause, or who said it. Keep the rest of the "
    "wording as it is.",
}
EDIT_SYSTEM = f"""You help build a test set for a fact checker. You are given a claim and the \
quote that backs it. The quote is inside <{{tag}}> ... </{{tag}}> tags.

{DATA_RULE}

{{instruction}}

Return only the rewritten claim, as one sentence."""


class Edited(BaseModel):
    text: str = Field(description="The rewritten claim.")


def natural_pairs() -> list[dict]:
    """Every first-draft claim whose quote really is on the cited page."""
    pages = load_pages()
    pairs = []
    for row in read_jsonl(PIPELINE_RUNS):
        for claim in row["draft"]:
            page = pages.get(claim["source_id"])
            if page and find_quote(claim["quote"], page["text"]):
                pair = {"claim": claim["text"], "quote": claim["quote"], "question_id": row["id"]}
                pairs.append(pair | {"origin": "natural"})
    return pairs


def wrong_quote(base: dict, pool: list[dict], rng: random.Random) -> dict:
    """The claim keeps its text but gets a quote from a different question."""
    other = rng.choice([p for p in pool if p["question_id"] != base["question_id"]])
    return base | {"quote": other["quote"], "origin": "wrong_quote"}


async def edited(deps: Deps, base: dict, kind: str) -> dict:
    tag = new_tag("quote")
    system = with_tag(EDIT_SYSTEM.replace("{instruction}", EDITS[kind]), tag)
    result = await deps.llm.structured(
        node="pairs",
        model=deps.settings.writer_model,
        effort="low",
        max_tokens=1_000,
        system=system,
        user=f"Claim: {base['claim']}\n\nQuote:\n<{tag}>\n{base['quote']}\n</{tag}>",
        schema=Edited,
        config={"callbacks": deps.tracer.callbacks()},
    )
    return base | {"claim": result.text.strip(), "origin": kind}


async def run() -> None:
    if read_jsonl(LABELS):
        print("pairs: labels already exist, so the pairs are frozen. Nothing rebuilt.")
        return
    rng = random.Random(SEED)
    pool = natural_pairs()
    rng.shuffle(pool)
    natural, rest = pool[:NATURAL], pool[NATURAL:]
    bases = (rest + natural)[: sum(BUILT.values())]  # prefer claims not already in the set
    kinds = [kind for kind, count in BUILT.items() for _ in range(count)]
    jobs = list(zip(bases, kinds, strict=False))
    swapped = [wrong_quote(base, pool, rng) for base, kind in jobs if kind == "wrong_quote"]
    limit = asyncio.Semaphore(4)  # the API refuses too many requests at the same time

    async def one(deps: Deps, base: dict, kind: str) -> dict:
        async with limit:
            return await edited(deps, base, kind)

    async with eval_deps("eval.pairs") as deps:
        rewritten = await asyncio.gather(
            *(one(deps, base, kind) for base, kind in jobs if kind != "wrong_quote")
        )
        spent = deps.ledger.spent
    built = swapped + list(rewritten)
    pairs = natural + list(built)
    rng.shuffle(pairs)  # so the labeller cannot tell real from built by position
    rows = [{"id": f"p{n:03d}"} | pair for n, pair in enumerate(pairs, start=1)]
    write_jsonl(PAIRS, rows)
    origins = {kind: sum(r["origin"] == kind for r in rows) for kind in ["natural", *BUILT]}
    print(f"pairs: wrote {len(rows)} pairs {origins}, cost ${spent:.2f}")
