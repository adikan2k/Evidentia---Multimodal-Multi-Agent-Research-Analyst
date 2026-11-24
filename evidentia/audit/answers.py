"""Get an answer with citations from another AI tool, to audit (D-041).

OpenAI's Responses API with its web search tool writes an answer and marks which spans of it
come from which web pages (`url_citation` annotations with start and end offsets). This turns
that into the plain text with numbered markers and a source list that the auditor reads, the
same shape as an answer pasted from a chat app.
"""

from datetime import UTC, datetime
from typing import Any

from evidentia.config import Settings
from evidentia.cost import Charge, Ledger, claude_usd, estimate_tokens, openai_usd
from evidentia.openai_llm import make_client

# The Responses API's web search tool. Source: developers.openai.com/api/docs/pricing, read
# 2026-11-24: $10 per 1,000 calls, plus the search content tokens at the model's own rates.
WEB_SEARCH_USD_PER_CALL = 0.01
ANSWER_MODEL = "gpt-6.2-sol"
MAX_OUTPUT_TOKENS = 4_000  # both tools think before they write, and that counts too
WORST_CASE_SEARCHES = 5


def with_markers(text: str, citations: list[Any]) -> str:
    """The answer with a [n] after each cited span, and a numbered source list at the end.

    A span that already holds its link inline, such as "([nasa.gov](https://...))", is left as
    it is: the auditor reads markdown links, and a marker would cite the page twice.
    """
    numbers: dict[str, int] = {}
    ends: dict[int, list[int]] = {}
    for c in citations:
        if c.url in text[c.start_index : c.end_index]:
            continue
        n = numbers.setdefault(c.url, len(numbers) + 1)
        if n not in ends.setdefault(c.end_index, []):
            ends[c.end_index].append(n)
    out, pos = [], 0
    for end in sorted(ends):
        out.append(text[pos:end])
        out.append("".join(f"[{n}]" for n in ends[end]))
        pos = end
    out.append(text[pos:])
    sources = "\n".join(f"[{n}] {url}" for url, n in numbers.items())
    return "".join(out).rstrip() + ("\n\nSources:\n" + sources if sources else "")


def charge(ledger: Ledger, model: str, response: Any) -> float:
    usage = response.usage
    cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
    searches = sum(getattr(item, "type", "") == "web_search_call" for item in response.output)
    usd = openai_usd(model, usage.input_tokens, usage.output_tokens, cached)
    usd += searches * WEB_SEARCH_USD_PER_CALL
    ledger.add(
        Charge(
            node="answer",
            item=f"{model} + {searches} web searches",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read=cached,
            usd=usd,
        )
    )
    return usd


CLAUDE_ANSWER_MODEL = "claude-sonnet-5-5"
# The Messages API's web search tool. The newer web_search_20260209 filters results with code
# and its answers carry no citation data (checked on 2026-11-24), so the basic tool is used.
CLAUDE_WEB_SEARCH = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
MAX_PAUSES = 3  # a long search turn can pause; the API resumes it when the turn is sent back


def claude_markers(blocks: list[Any]) -> tuple[str, int]:
    """Claude's text blocks, each cited one followed by its [n] markers, and a source list.

    Claude splits its answer into text blocks at citation boundaries, so a block's citations
    belong to that block's text.
    """
    numbers: dict[str, int] = {}
    out = []
    for block in blocks:
        out.append(block.text)
        urls = [
            c.url
            for c in (getattr(block, "citations", None) or [])
            if getattr(c, "type", "") == "web_search_result_location"
        ]
        marks = list(dict.fromkeys(numbers.setdefault(u, len(numbers) + 1) for u in urls))
        out.append("".join(f"[{n}]" for n in marks))
    sources = "\n".join(f"[{n}] {url}" for url, n in numbers.items())
    text = "".join(out).rstrip() + ("\n\nSources:\n" + sources if sources else "")
    return text, len(numbers)


async def claude_answer_with_web_search(
    question: str,
    settings: Settings,
    ledger: Ledger,
    tracer: Any,
    client: Any = None,
    model: str = CLAUDE_ANSWER_MODEL,
) -> dict[str, Any]:
    """Ask Claude with its web search tool on; return the answer in the auditor's input shape."""
    if client is None:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    blocks: list[Any] = []
    usd = 0.0
    # The SDK's own spans are not exported (tracing.export_span), so this call gets its own.
    with tracer.span("answer.claude", "generation", {"question": question, "model": model}) as span:
        for _ in range(MAX_PAUSES + 1):
            worst = claude_usd(model, estimate_tokens(question) + 30_000, MAX_OUTPUT_TOKENS)
            with ledger.reserve("answer", worst + WORST_CASE_SEARCHES * WEB_SEARCH_USD_PER_CALL):
                response = await client.messages.create(
                    model=model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    messages=messages,
                    tools=[CLAUDE_WEB_SEARCH],
                )
                usd += charge_claude(ledger, model, response.usage)
            blocks += [b for b in response.content if getattr(b, "type", "") == "text"]
            if response.stop_reason != "pause_turn":
                break
            messages = [messages[0], {"role": "assistant", "content": response.content}]
        text, cited = claude_markers(blocks)
        ended = response.stop_reason  # "end_turn", or "max_tokens" if the answer was cut off
        span.update(output={"answer": text}, metadata={"usd": round(usd, 4), "cited_pages": cited})
    return {
        "question": question,
        "model": model,
        "tool": "web search",
        "made_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "text": text,
        "citations": cited,
        "ended": ended,
        "usd": round(usd, 4),
    }


def charge_claude(ledger: Ledger, model: str, usage: Any) -> float:
    searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    usd = claude_usd(model, usage.input_tokens, usage.output_tokens, cache_read, cache_write)
    usd += searches * WEB_SEARCH_USD_PER_CALL
    ledger.add(
        Charge(
            node="answer",
            item=f"{model} + {searches} web searches",
            input_tokens=usage.input_tokens + cache_read + cache_write,
            output_tokens=usage.output_tokens,
            cache_read=cache_read,
            cache_write=cache_write,
            usd=usd,
        )
    )
    return usd


async def answer_with_web_search(
    question: str, settings: Settings, ledger: Ledger, client: Any = None, model: str = ANSWER_MODEL
) -> dict[str, Any]:
    """Ask the model with web search on; return the answer in the auditor's input shape."""
    client = client or make_client(settings)
    worst = openai_usd(model, estimate_tokens(question) + 20_000, MAX_OUTPUT_TOKENS)
    worst += WORST_CASE_SEARCHES * WEB_SEARCH_USD_PER_CALL
    with ledger.reserve("answer", worst):
        response = await client.responses.create(
            model=model,
            input=question,
            tools=[{"type": "web_search"}],
            max_output_tokens=MAX_OUTPUT_TOKENS,
            store=False,
        )
        usd = charge(ledger, model, response)
    texts = [
        part
        for item in response.output
        if getattr(item, "type", "") == "message"
        for part in item.content
        if getattr(part, "type", "") == "output_text"
    ]
    text = "".join(p.text for p in texts)
    citations = [
        a for p in texts for a in (p.annotations or []) if getattr(a, "type", "") == "url_citation"
    ]
    return {
        "question": question,
        "model": model,
        "tool": "web search",
        "made_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "text": with_markers(text, citations),
        "citations": len({c.url for c in citations}),
        "ended": getattr(response, "status", None),  # "completed", or "incomplete" if cut off
        "usd": round(usd, 4),
    }
