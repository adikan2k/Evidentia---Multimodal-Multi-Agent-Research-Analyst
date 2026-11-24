"""The two judges (D-038): the combining table, the page judge, quote context, and OpenAI calls."""

import asyncio
from types import SimpleNamespace

import pytest

from evidentia.audit.graph import AuditNodes, quote_context
from evidentia.audit.report import claim_views
from evidentia.audit.schemas import PageJudgement, Quote, combine
from evidentia.config import ConfigError
from evidentia.cost import Ledger, openai_usd
from evidentia.llm import ModelStopped
from evidentia.openai_llm import OpenAILLM
from evidentia.schemas import Source
from tests.test_audit_graph import FACT, GOOD, LONG, audit, make_deps

ANSWER = (
    "Solar capacity grew 24% in 2023 [1]. Solar is the cheapest energy source ever [1]. "
    f"Solar capacity fell 10% in 2023 [1].\n[1] {GOOD}"
)


@pytest.mark.parametrize(
    ("quote", "page", "label"),
    [
        ("supported", "supported", "supported"),
        ("contradicted", "not_supported", "contradicted"),
        ("partial", "not_supported", "partial"),
        ("not_found", "not_supported", "not_found"),
        ("supported", "not_supported", "needs_human"),
        ("partial", "supported", "needs_human"),
        ("not_found", "supported", "needs_human"),
        ("contradicted", "supported", "needs_human"),
        ("supported", "no_answer", "unchecked"),
        ("supported", None, "supported"),  # one judge only
        ("dead_link", None, "dead_link"),
        ("unchecked", "supported", "unchecked"),  # the page judge cannot rescue a failed read
    ],
)
def test_the_d038_table(quote, page, label) -> None:
    assert combine(quote, page) == label


def labels(state) -> list[str]:
    return [v["label"] for v in claim_views(state)]


def test_agreement_gives_a_verdict_and_disagreement_needs_a_human(settings) -> None:
    deps, _ = make_deps(settings)
    assert labels(audit(deps, ANSWER)) == ["supported", "not_found", "contradicted"]

    disagree = {
        "Solar capacity grew 24% in 2023.": False,
        "Solar is the cheapest energy source ever.": True,
    }
    deps, _ = make_deps(settings, page_says=disagree)
    state = audit(deps, ANSWER)
    assert labels(state) == ["needs_human", "needs_human", "contradicted"]
    page = claim_views(state)[0]["pages"][0]
    assert page["quote_label"] == "supported" and page["page_reason"] == "Scripted page verdict."


def test_a_page_judge_that_does_not_answer_means_could_not_check(settings) -> None:
    deps, _ = make_deps(settings, page_says={"Solar capacity grew 24% in 2023.": None})
    assert labels(audit(deps, ANSWER))[0] == "unchecked"


def test_with_one_judge_the_page_judge_is_never_called(settings) -> None:
    settings = settings.model_copy(update={"audit_two_judges": False})
    deps, fake = make_deps(settings, page_says={"Solar capacity grew 24% in 2023.": False})
    assert labels(audit(deps, ANSWER)) == ["supported", "not_found", "contradicted"]
    assert not [c for c in fake.calls if c["schema"] == "PageJudgement"]


def test_the_page_judge_reads_the_same_passages_and_the_reranker_runs_once(settings) -> None:
    settings = settings.model_copy(update={"audit_page_chars": 50, "audit_top_passages": 2})
    deps, fake = make_deps(settings)
    audit(deps, f"Solar capacity grew 24% in 2023 [1].\n[1] {LONG}")
    nodes = {t.node: t for t in deps.ledger.by_node()}
    assert nodes["find"].calls == 2  # one rerank and the finder
    assert nodes["page_check"].calls == 1
    find = next(c for c in fake.calls if c["schema"] == "Evidence")
    page = next(c for c in fake.calls if c["schema"] == "PageJudgement")

    def texts(call: dict) -> list[str]:  # the passage texts, without the random tags
        body = call["user"].split("\n\nPage:\n\n", 1)[1]
        return [block.split(">\n", 1)[1].rsplit("\n</", 1)[0] for block in body.split("\n\n<")]

    assert len(texts(find)) == 2 and texts(find) == texts(page)
    assert "untrusted data" in page["system"]


def test_quote_context_is_shown_only_when_switched_on(settings) -> None:
    deps, fake = make_deps(settings)
    audit(deps, ANSWER)
    check = next(c for c in fake.calls if c["schema"] == "AuditJudgement")
    assert "-context>" not in check["user"]

    settings = settings.model_copy(update={"audit_quote_context": True})
    deps, fake = make_deps(settings)
    audit(deps, ANSWER)
    check = next(c for c in fake.calls if c["schema"] == "AuditJudgement")
    assert "-context>" in check["user"] and "Use it only to understand" in check["system"]


def test_context_is_the_quotes_paragraph_cut_around_it() -> None:
    text = f"First paragraph.\nBefore it. {FACT} After it.\nLast paragraph."
    start = text.index(FACT)
    quote = Quote(text=FACT, start=start, end=start + len(FACT))
    source = Source(id="S1", url="u", text=text)
    assert quote_context(source, quote, 600) == f"Before it. {FACT} After it."
    cut = quote_context(source, quote, len(FACT) + 4)
    assert FACT in cut and "Before it." not in cut and len(cut) <= len(FACT) + 4


# OpenAI


class FakeResponses:
    def __init__(self, parsed, status="completed", cached=0) -> None:
        self.parsed, self.status, self.cached = parsed, status, cached
        self.kwargs: dict = {}

    async def parse(self, **kwargs):
        self.kwargs = kwargs
        usage = SimpleNamespace(
            input_tokens=1000,
            output_tokens=100,
            input_tokens_details=SimpleNamespace(cached_tokens=self.cached),
        )
        return SimpleNamespace(
            status=self.status,
            incomplete_details={"reason": "max_output_tokens"}
            if self.status != "completed"
            else None,
            output_parsed=self.parsed,
            usage=usage,
        )


def openai_with(parsed, settings, **kw):
    responses = FakeResponses(parsed, **kw)
    ledger = Ledger(1.0)
    return OpenAILLM(settings, ledger, client=SimpleNamespace(responses=responses)), responses


def ask(llm):
    return asyncio.run(
        llm.structured(
            node="page_check",
            model="gpt-6-luna",
            effort="low",
            max_tokens=500,
            system="rules",
            user="claim and page",
            schema=PageJudgement,
        )
    )


def test_openai_calls_send_the_schema_and_record_the_cost(settings) -> None:
    llm, responses = openai_with(PageJudgement(reason="r", supported=True), settings, cached=400)
    assert ask(llm).supported is True
    sent = responses.kwargs
    assert sent["text_format"] is PageJudgement and sent["model"] == "gpt-6-luna"
    assert sent["instructions"] == "rules" and sent["reasoning"] == {"effort": "low"}
    charge = llm.ledger.charges[0]
    assert charge.node == "page_check" and charge.item == "gpt-6-luna"
    assert charge.usd == pytest.approx(openai_usd("gpt-6-luna", 1000, 100, 400))
    assert charge.usd == pytest.approx((600 * 0.10 + 400 * 0.01 + 100 * 0.50) / 1e6)


def test_openai_refusals_and_cut_off_replies_stop_like_claude_ones(settings) -> None:
    llm, _ = openai_with(None, settings)
    with pytest.raises(ModelStopped):
        ask(llm)
    llm, _ = openai_with(PageJudgement(reason="r", supported=True), settings, status="incomplete")
    with pytest.raises(ModelStopped):
        ask(llm)
    assert llm.ledger.charges  # a cut-off reply is still paid for


def test_an_openai_model_without_a_key_is_refused_before_any_call(settings) -> None:
    with pytest.raises(ConfigError) as err:
        OpenAILLM(settings, Ledger(1.0))
    assert "OPENAI_API_KEY" in str(err.value)


def test_a_gpt_page_judge_goes_to_openai_and_claude_does_the_rest(settings) -> None:
    settings = settings.model_copy(update={"page_judge_model": "gpt-6-luna"})
    deps, fake = make_deps(settings)
    deps.openai, responses = openai_with(PageJudgement(reason="r", supported=True), settings)
    deps.openai.ledger = deps.ledger
    nodes = AuditNodes(deps)
    assert nodes.model_for("gpt-6-luna") is deps.openai
    assert nodes.model_for(settings.checker_model) is deps.llm
    state = audit(deps, f"Solar capacity grew 24% in 2023 [1].\n[1] {GOOD}")
    assert labels(state) == ["supported"]
    assert responses.kwargs["model"] == "gpt-6-luna"
    assert not [c for c in fake.calls if c["schema"] == "PageJudgement"]
    items = {(c.node, c.item) for c in deps.ledger.charges}
    assert ("page_check", "gpt-6-luna") in items and ("check", settings.checker_model) in items
