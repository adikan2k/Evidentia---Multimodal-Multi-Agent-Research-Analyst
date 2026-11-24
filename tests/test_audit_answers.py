import asyncio
from types import SimpleNamespace

from evidentia.audit.answers import WEB_SEARCH_USD_PER_CALL, answer_with_web_search, with_markers
from evidentia.audit.citations import citations_for, locate, parse_answer
from evidentia.cost import Ledger, openai_usd

TEXT = "Solar grew 24% in 2023. Wind grew 10%. Hydro was flat."


def cite(url: str, start: int, end: int):
    return SimpleNamespace(
        type="url_citation", url=url, start_index=start, end_index=end, title="t"
    )


def test_markers_go_after_each_cited_span_and_the_sources_are_listed() -> None:
    a, b = "https://a.example.org/x", "https://b.example.org/y"
    out = with_markers(TEXT, [cite(a, 0, 23), cite(b, 24, 38), cite(a, 24, 38)])
    assert out.startswith("Solar grew 24% in 2023.[1] Wind grew 10%.[2][1] Hydro was flat.")
    assert out.endswith(f"Sources:\n[1] {a}\n[2] {b}")


def test_the_marked_answer_reads_back_through_the_auditors_parser() -> None:
    a = "https://a.example.org/x"
    parsed = parse_answer(with_markers(TEXT, [cite(a, 0, 23)]))
    span = locate("Solar grew 24% in 2023.", parsed.text)
    assert [c.url for c in parsed.citations] == [a]
    assert citations_for(parsed, *span) == ["c1"]
    assert citations_for(parsed, *locate("Hydro was flat.", parsed.text)) == []


def test_the_answer_call_uses_web_search_and_is_charged_with_its_searches(settings) -> None:
    sent = {}

    async def create(**kwargs):
        sent.update(kwargs)
        part = SimpleNamespace(
            type="output_text", text=TEXT, annotations=[cite("https://a.example.org/x", 0, 23)]
        )
        return SimpleNamespace(
            output=[
                SimpleNamespace(type="web_search_call"),
                SimpleNamespace(type="web_search_call"),
                SimpleNamespace(type="message", content=[part]),
            ],
            usage=SimpleNamespace(input_tokens=5000, output_tokens=400, input_tokens_details=None),
        )

    ledger = Ledger(1.0)
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    answer = asyncio.run(answer_with_web_search("A question?", settings, ledger, client=client))
    assert sent["tools"] == [{"type": "web_search"}] and sent["store"] is False
    assert answer["citations"] == 1 and "[1]" in answer["text"]
    expected = openai_usd("gpt-6.2-sol", 5000, 400) + 2 * WEB_SEARCH_USD_PER_CALL
    assert abs(ledger.spent - expected) < 1e-9
    assert ledger.charges[0].item == "gpt-6.2-sol + 2 web searches"


def test_a_span_that_already_holds_its_link_gets_no_marker() -> None:
    url = "https://science.nasa.gov/launch/"
    text = f"Webb launched in 2021. ([nasa]({url})) It orbits L2."
    span_end = text.index(")) ") + 2
    other = cite("https://b.example.org/", text.index("It orbits"), len(text))
    out = with_markers(text, [cite(url, 23, span_end), other])
    assert out.count(url) == 1 and "[1]" in out and out.endswith("[1] https://b.example.org/")


def claude_block(text: str, *urls: str):
    citations = [
        SimpleNamespace(type="web_search_result_location", url=u, cited_text="x") for u in urls
    ]
    return SimpleNamespace(type="text", text=text, citations=citations or None)


def test_claude_blocks_get_markers_after_each_cited_block() -> None:
    from evidentia.audit.answers import claude_markers

    a, b = "https://a.example.org/", "https://b.example.org/"
    text, cited = claude_markers(
        [
            claude_block("Webb launched in 2021. "),
            claude_block("It orbits L2.", a, b),
            claude_block(" It has a 6.5 m mirror.", a),
        ]
    )
    assert text.startswith("Webb launched in 2021. It orbits L2.[1][2] It has a 6.5 m mirror.[1]")
    assert text.endswith(f"Sources:\n[1] {a}\n[2] {b}") and cited == 2


def test_claude_answers_resume_a_paused_turn_and_count_searches(settings) -> None:
    from evidentia.audit.answers import claude_answer_with_web_search
    from evidentia.cost import claude_usd
    from evidentia.tracing import NoopTracer

    calls = []
    usage = lambda searches: SimpleNamespace(  # noqa: E731
        input_tokens=4000,
        output_tokens=300,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        server_tool_use=SimpleNamespace(web_search_requests=searches),
    )
    replies = [
        SimpleNamespace(
            stop_reason="pause_turn",
            content=[claude_block("Part one. ", "https://a.example.org/")],
            usage=usage(2),
        ),
        SimpleNamespace(
            stop_reason="end_turn", content=[claude_block("Part two.")], usage=usage(1)
        ),
    ]

    async def create(**kwargs):
        calls.append(kwargs)
        return replies[len(calls) - 1]

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    ledger = Ledger(1.0)
    answer = asyncio.run(
        claude_answer_with_web_search("Q?", settings, ledger, NoopTracer(), client=client)
    )
    assert len(calls) == 2 and calls[0]["tools"][0]["type"] == "web_search_20250305"
    assert calls[1]["messages"][1]["role"] == "assistant"  # the paused turn is sent back
    assert answer["text"].startswith("Part one. [1]Part two.") and answer["citations"] == 1
    expected = 2 * claude_usd("claude-sonnet-5-5", 4000, 300) + 3 * 0.01
    assert abs(ledger.spent - expected) < 1e-9
