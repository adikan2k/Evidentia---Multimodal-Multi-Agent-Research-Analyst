"""Build the frozen corpus: fetch each question's pages once, save them, and draft gold snippets.

Pages come only from openly licensed sources, so their text can be committed (see D-016).
"""

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, Field

from evals.common import (
    PAGES_DIR,
    GoldSnippet,
    Question,
    eval_deps,
    load_pages,
    load_questions,
    save_questions,
)
from evidentia.graph import Deps
from evidentia.llm import DATA_RULE, new_tag, with_tag
from evidentia.quote_check import find_quote
from evidentia.schemas import SearchHit

LICENCES = {"en.wikipedia.org": "CC BY-SA 4.0", "ourworldindata.org": "CC BY 4.0"}
US_GOV = "Public domain (United States government work)"
PREFIXES = {"en.wikipedia.org": "wiki", "ourworldindata.org": "owid"}

# Long encyclopaedia articles are cut at a paragraph break so the corpus stays a few megabytes.
MAX_PAGE_CHARS = 60_000
SNIPPETS_PER_QUESTION = 3

GOLD_SYSTEM = f"""You pick the evidence a careful reader would highlight. You are given a \
question and the text of one page inside <{{tag}}> ... </{{tag}}> tags.

{DATA_RULE}

Return the passages of the page that most directly answer the question:
- Each snippet is one or two whole sentences copied character for character from the page.
- Pick snippets that state the answer itself, not background or section headings.
- If the page gives competing answers or figures, pick one snippet for each.
- If the page does not answer the question, return an empty list."""


class GoldPick(BaseModel):
    snippets: list[str] = Field(description="Exact contiguous text copied from the page.")


def page_id(url: str) -> str:
    """A short, stable, readable id such as `wiki-mount-everest`."""
    parts = urlsplit(url)
    host = parts.netloc.removeprefix("www.")
    tail = unquote(parts.path).strip("/").split("/")[-1].removesuffix(".html") or "index"
    slug = re.sub(r"[^a-z0-9]+", "-", tail.lower()).strip("-")
    return f"{PREFIXES.get(host, host.split('.')[-2])}-{slug}"


def trim(text: str, limit: int = MAX_PAGE_CHARS) -> str:
    return text if len(text) <= limit else text[: text.rfind("\n", 0, limit)]


def page_record(url: str, text: str) -> dict[str, str | int]:
    host = urlsplit(url).netloc.removeprefix("www.")
    text = trim(text)
    title = unquote(urlsplit(url).path).strip("/").split("/")[-1].replace("_", " ")
    return {
        "id": page_id(url),
        "url": url,
        "title": title.removesuffix(".html"),
        "licence": LICENCES.get(host, US_GOV),
        "fetched": datetime.now(UTC).date().isoformat(),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "chars": len(text),
        "text": text,
    }


async def fetch_pages() -> None:
    """Fetch every page the questions name that is not saved yet. Polite: robots and rate limit."""
    saved = {page["url"] for page in load_pages().values()}
    wanted = sorted({url for q in load_questions() for url in q.pages} - saved)
    if not wanted:
        print(f"corpus: all {len(saved)} pages already saved")
        return
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    async with eval_deps("eval.corpus") as deps:
        sources, skipped = await deps.fetcher.fetch_all([SearchHit(url=u) for u in wanted])
    for source in sources:
        record = page_record(source.url, source.text)
        path = PAGES_DIR / f"{record['id']}.json"
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"corpus: saved {len(sources)} pages, {len(skipped)} could not be used")
    for page in skipped:
        print(f"  skipped {page.url}: {page.reason}")


async def pick_snippets(deps: Deps, question: Question, page: dict) -> list[GoldSnippet]:
    tag = new_tag("page")
    user = f"Question: {question.question}\n\nPage:\n<{tag}>\n{page['text']}\n</{tag}>"
    pick = await deps.llm.structured(
        node="gold",
        model=deps.settings.writer_model,
        effort="medium",
        max_tokens=3_000,
        system=with_tag(GOLD_SYSTEM, tag),
        user=user + f"\n\nReturn up to {SNIPPETS_PER_QUESTION} snippets.",
        schema=GoldPick,
        config={"callbacks": deps.tracer.callbacks()},
    )
    gold = []
    for snippet in pick.snippets:
        span = find_quote(snippet, page["text"])
        if span:  # a snippet that is not word for word on the page is dropped, not trusted
            text = page["text"][span[0] : span[1]]
            gold.append(GoldSnippet(page=page["id"], text=text, start=span[0], end=span[1]))
    return gold


async def draft_gold() -> None:
    """Fill in gold snippets for questions that have none. Aditya reviews the result."""
    pages = load_pages()
    questions = load_questions()
    todo = [q for q in questions if not q.gold]
    if not todo:
        print("gold: every question already has gold snippets")
        return
    limit = asyncio.Semaphore(4)

    async def one(deps: Deps, question: Question) -> None:
        available = [pages[page_id(u)] for u in question.pages if page_id(u) in pages]
        async with limit:
            found = await asyncio.gather(*(pick_snippets(deps, question, p) for p in available))
        # Take snippets from each page in turn so a two-page question is covered by both.
        merged = [s for group in zip(*found, strict=False) for s in group]
        merged += [s for group in found for s in group if s not in merged]
        question.gold = merged[:SNIPPETS_PER_QUESTION]

    async with eval_deps("eval.gold") as deps:
        await asyncio.gather(*(one(deps, q) for q in todo))
        spent = deps.ledger.spent
    save_questions(questions)
    empty = [q.id for q in questions if not q.gold]
    print(f"gold: drafted for {len(todo)} questions, cost ${spent:.2f}")
    print(f"gold: questions still without a snippet: {empty or 'none'}")
