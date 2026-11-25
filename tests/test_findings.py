"""The findings page's examples (D-048): chosen by the fixed rule, the same every time."""

from evals.findings import NOT_FOUND_PER_TOOL, choose_examples


def report(*labels: str) -> dict:
    return {"claims": [{"claim": f"claim {i}", "label": label} for i, label in enumerate(labels)]}


def made_up() -> dict:
    reports = {}
    for tool in ("openai", "claude"):
        for n in range(1, 9):
            reports[(tool, f"q{n}")] = report("supported", "not_found", "not_found", "partial")
        reports[(tool, "q9")] = report("contradicted", "supported", "contradicted")
    return reports


def test_every_contradicted_claim_and_a_fixed_draw_of_the_rest() -> None:
    chosen = choose_examples(made_up())
    for tool in ("openai", "claude"):
        mine = [x for x in chosen if x["tool"] == tool]
        assert [x["label"] for x in mine].count("contradicted") == 2
        assert [x["label"] for x in mine].count("not_found") == NOT_FOUND_PER_TOOL
    assert {x["id"] for x in chosen if x["label"] == "contradicted"} == {
        "openai-q9-1",
        "openai-q9-3",
        "claude-q9-1",
        "claude-q9-3",
    }
    assert len({x["id"] for x in chosen}) == len(chosen)


def test_the_draw_does_not_depend_on_the_order_the_audits_arrive_in() -> None:
    reports = made_up()
    backwards = dict(reversed(list(reports.items())))
    assert choose_examples(reports) == choose_examples(backwards)


def test_supported_partial_and_unchecked_claims_are_never_chosen() -> None:
    chosen = choose_examples({("openai", "q1"): report("supported", "partial", "unchecked")})
    assert chosen == []
