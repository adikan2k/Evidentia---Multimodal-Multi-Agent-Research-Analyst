"""The two judges (D-038): the combining table, the page judge, quote context, and OpenAI calls."""

import asyncio
from types import SimpleNamespace

import pytest

from evidentia.audit.graph import AuditNodes, quote_context
from evidentia.audit.report import claim_views
from evidentia.audit.schemas import PageJudgement, Quote, combine, page_call
from evidentia.config import ConfigError
from evidentia.cost import Ledger, openai_usd
from evidentia.llm import ModelStopped
from evidentia.openai_llm import OpenAILLM
from evidentia.schemas import Source
from tests.fakes import reply
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

    def texts(call: dict) -> list[str]:  # the passage texts, without the tags
        body = call["user"].split("Page:\n\n", 1)[1].rsplit("\n\nClaim: ", 1)[0]
        return [block.split(">\n", 1)[1].rsplit("\n</", 1)[0] for block in body.split("\n\n<")]

    assert len(texts(find)) == 2 and texts(find) == texts(page)
    assert "untrusted data" in page["system"]


def test_both_judges_start_together_and_combine_waits_for_both(settings) -> None:
    deps, _ = make_deps(settings)
    seen: list[str] = []
    state = audit(deps, ANSWER, seen)
    assert seen.index("page_check") < seen.index("quote_check")  # ran alongside find
    assert seen[-1] == "combine" and seen.count("combine") == 1
    assert labels(state) == ["supported", "not_found", "contradicted"]
    assert state.results[0].page_judged == "supported"


def test_the_page_goes_first_as_a_cached_prefix_with_one_tag_per_audit(settings) -> None:
    deps, _ = make_deps(settings)
    sent: list[dict] = []
    original = deps.llm._call

    async def spy(model, effort, max_tokens, system, user, schema, config, prefix=None):
        sent.append({"schema": schema.__name__, "prefix": prefix, "user": user})
        return await original(model, effort, max_tokens, system, user, schema, config, prefix)

    deps.llm._call = spy
    audit(deps, ANSWER)
    page_calls = [c for c in sent if c["schema"] in ("Evidence", "PageJudgement")]
    assert all(
        c["prefix"].startswith("Page:") and c["user"].startswith("Claim:") for c in page_calls
    )
    assert len({c["prefix"] for c in page_calls}) == 1  # same page, same tag: one cache entry


def test_without_caching_the_page_is_inside_the_message(settings) -> None:
    settings = settings.model_copy(update={"audit_prompt_cache": False})
    deps, fake = make_deps(settings)
    audit(deps, ANSWER)
    find = next(c for c in fake.calls if c["schema"] == "Evidence")
    assert find["user"].startswith("Page:") and "\n\nClaim: " in find["user"]


def test_a_cached_call_sends_the_page_as_a_marked_block(settings) -> None:
    from evidentia.llm import LLM

    llm = LLM(settings, Ledger(1.0))
    captured = {}

    class FakeRunnable:
        async def ainvoke(self, messages, config=None):
            captured["messages"] = messages
            raw = SimpleNamespace(usage_metadata={}, response_metadata={"stop_reason": "end_turn"})
            return {"raw": raw, "parsed": PageJudgement(reason="r", supported=True)}

    class FakeChat:
        def __init__(self, **kwargs):
            pass

        def with_structured_output(self, *args, **kwargs):
            return FakeRunnable()

    import evidentia.llm as llm_module

    real = llm_module.ChatAnthropic
    llm_module.ChatAnthropic = FakeChat
    try:
        asyncio.run(
            llm.structured(
                node="find",
                model="claude-haiku-5-5",
                effort="low",
                max_tokens=100,
                system="s",
                user="Claim: c",
                schema=PageJudgement,
                prefix="Page:\n\n<page-1>\ntext\n</page-1>",
            )
        )
    finally:
        llm_module.ChatAnthropic = real
    content = captured["messages"][1].content
    assert content[0]["cache_control"] == {"type": "ephemeral"}
    assert content[0]["text"].startswith("Page:") and content[1]["text"] == "Claim: c"


def test_cache_reads_are_priced_per_model() -> None:
    from evidentia.cost import claude_usd

    sonnet = claude_usd("claude-sonnet-5-5", 0, 0, cache_read=1_000_000)
    haiku = claude_usd("claude-haiku-5-5", 0, 0, cache_read=1_000_000)
    assert sonnet == pytest.approx(2.00 * 0.05) and haiku == pytest.approx(0.10 * 0.1)


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
    assert nodes.model_for(settings.audit_checker_model) is deps.llm
    state = audit(deps, f"Solar capacity grew 24% in 2023 [1].\n[1] {GOOD}")
    assert labels(state) == ["supported"]
    assert responses.kwargs["model"] == "gpt-6-luna"
    assert not [c for c in fake.calls if c["schema"] == "PageJudgement"]
    items = {(c.node, c.item) for c in deps.ledger.charges}
    assert ("page_check", "gpt-6-luna") in items
    assert ("check", settings.audit_checker_model) in items


# Scores and thresholds (D-039)


@pytest.mark.parametrize(
    ("score", "t_supported", "t_flag", "call"),
    [
        (1.0, 0.5, 0.5, "supported"),
        (0.0, 0.5, 0.5, "not_supported"),
        (0.6, 0.8, 0.2, "uncertain"),
        (0.8, 0.8, 0.2, "supported"),
        (0.2, 0.8, 0.2, "not_supported"),
        (None, 0.5, 0.5, "no_answer"),
    ],
)
def test_the_score_becomes_a_verdict_by_two_thresholds(score, t_supported, t_flag, call) -> None:
    assert page_call(score, t_supported, t_flag) == call


def test_an_uncertain_page_judge_means_a_human_decides() -> None:
    assert combine("supported", "uncertain") == "needs_human"
    assert combine("not_found", "uncertain") == "needs_human"


def test_votes_give_a_score_and_the_thresholds_decide(settings) -> None:
    answers = iter([True, True, False, True, True])  # four of five votes say supported
    settings = settings.model_copy(
        update={"page_judge_votes": 5, "audit_t_supported": 0.9, "audit_t_flag": 0.2}
    )
    deps, fake = make_deps(settings)
    original = fake._call

    async def mixed(model, effort, max_tokens, system, user, schema, config, prefix=None):
        if schema is PageJudgement:
            fake.calls.append({"schema": "PageJudgement", "user": user})
            return reply(PageJudgement(reason="vote", supported=next(answers)))
        return await original(model, effort, max_tokens, system, user, schema, config, prefix)

    deps.llm._call = mixed
    state = audit(deps, f"Solar capacity grew 24% in 2023 [1].\n[1] {GOOD}")
    page = claim_views(state)[0]["pages"][0]
    assert page["page_score"] == 0.8 and page["page_judged"] == "uncertain"
    assert claim_views(state)[0]["label"] == "needs_human"
    assert len([c for c in fake.calls if c["schema"] == "PageJudgement"]) == 5


def token(text: str, logprob: float, alts=()):
    top = [SimpleNamespace(token=t, logprob=lp) for t, lp in alts]
    return SimpleNamespace(token=text, logprob=logprob, top_logprobs=top)


def response_with(tokens):
    part = SimpleNamespace(logprobs=tokens)
    return SimpleNamespace(output=[SimpleNamespace(content=[part])])


def test_probability_of_true_reads_the_boolean_token() -> None:
    import math

    from evidentia.openai_llm import probability_of_true

    tokens = [token('{"', 0.0), token("supported", 0.0), token('":', 0.0)]
    sure = response_with([*tokens, token("true", 0.0), token("}", 0.0)])
    assert probability_of_true(sure) == 1.0
    split = [token("false", math.log(0.7), [("false", math.log(0.7)), ("true", math.log(0.3))])]
    assert probability_of_true(response_with([*tokens, *split])) == pytest.approx(0.3)
    with pytest.raises(ModelStopped):
        probability_of_true(response_with(tokens))


def test_the_probability_call_turns_reasoning_off_and_asks_for_token_probabilities(
    settings,
) -> None:
    parsed = PageJudgement(reason="r", supported=True)
    llm, responses = openai_with(parsed, settings)

    async def parse(**kwargs):
        responses.kwargs = kwargs
        result = await FakeResponses(parsed).parse(**kwargs)
        result.output = [SimpleNamespace(content=[SimpleNamespace(logprobs=[token("true", 0.0)])])]
        return result

    responses.parse = parse
    judgement, score = asyncio.run(
        llm.probability(
            node="page_check",
            model="gpt-6-luna",
            max_tokens=200,
            system="s",
            user="u",
            schema=PageJudgement,
        )
    )
    assert judgement.supported and score == 1.0
    assert responses.kwargs["reasoning"] == {"effort": "none"}
    assert responses.kwargs["include"] == ["message.output_text.logprobs"]


def test_probability_mode_needs_an_openai_model(settings) -> None:
    settings = settings.model_copy(update={"page_judge_probability": True})
    deps, _ = make_deps(settings)
    with pytest.raises(ValueError, match="needs an OpenAI model"):
        asyncio.run(AuditNodes(deps)._page_probability("s", None, "u"))


def test_one_call_per_page_goes_first_so_the_others_can_read_its_cache() -> None:
    from evidentia.audit.graph import page_first

    events: list[str] = []

    async def run(i: int) -> int:
        events.append(f"start {i}")
        await asyncio.sleep(0)
        events.append(f"end {i}")
        return i * 10

    urls = {0: "a", 1: "a", 2: "b", 3: "a"}
    got = asyncio.run(page_first([0, 1, 2, 3], urls.__getitem__, run))
    assert got == [0, 10, 20, 30]
    assert events.index("end 0") < events.index("start 1")  # page a: first call alone
    assert events.index("end 0") < events.index("start 3")
    assert events.index("start 2") < events.index("end 0")  # page b runs alongside


def test_cache_tokens_are_counted_per_step(settings) -> None:
    from evidentia.cost import Charge

    ledger = Ledger(1.0)
    ledger.add(Charge(node="find", item="m", input_tokens=100, cache_read=60, usd=0.0))
    ledger.add(Charge(node="find", item="m", input_tokens=100, cache_write=90, usd=0.0))
    total = ledger.by_node()[0]
    assert (total.cache_read, total.cache_write) == (60, 90)


# D-040: the graded page judge and the checker rules


@pytest.mark.parametrize(
    ("quote", "grade", "label"),
    [
        ("supported", "states", "supported"),
        ("supported", "implies", "needs_human"),  # implied is not enough for supported
        ("not_found", "implies", "needs_human"),  # nor for a flag
        ("not_found", "does_not_support", "not_found"),
        ("contradicted", "contradicts", "contradicted"),
        ("partial", "does_not_support", "partial"),
        ("partial", "implies", "partial"),  # an implying page backs the main point
        ("partial", "states", "needs_human"),
        ("supported", "does_not_support", "needs_human"),
    ],
)
def test_the_graded_table(quote, grade, label) -> None:
    from evidentia.audit.schemas import GRADE_CALL

    assert combine(quote, GRADE_CALL[grade]) == label


def test_the_graded_judge_is_asked_when_switched_on(settings) -> None:
    from evidentia.audit.schemas import GradedPageJudgement

    settings = settings.model_copy(update={"page_judge_graded": True})
    deps, fake = make_deps(settings)
    original = fake._call
    asked = []

    async def graded(model, effort, max_tokens, system, user, schema, config, prefix=None):
        if schema is GradedPageJudgement:
            asked.append(system)
            grade = "implies" if "cheapest" in user else "states"
            return reply(GradedPageJudgement(reason="graded", grade=grade))
        return await original(model, effort, max_tokens, system, user, schema, config, prefix)

    deps.llm._call = graded
    state = audit(deps, ANSWER)
    assert labels(state) == ["supported", "needs_human", "needs_human"]
    page = claim_views(state)[0]["pages"][0]
    assert page["page_grade"] == "states" and page["page_judged"] == "supported"
    assert asked and "implies:" in asked[0] and "untrusted data" in asked[0]


def test_the_checker_rules_are_added_only_when_switched_on(settings) -> None:
    deps, fake = make_deps(settings)
    audit(deps, ANSWER)
    check = next(c for c in fake.calls if c["schema"] == "AuditJudgement")
    assert "The same thing." not in check["system"]

    settings = settings.model_copy(update={"audit_checker_rules": True})
    deps, fake = make_deps(settings)
    audit(deps, ANSWER)
    check = next(c for c in fake.calls if c["schema"] == "AuditJudgement")
    assert "The same thing." in check["system"] and "The same scope." in check["system"]
