"""The real-world audit's bookkeeping (D-042), with made-up audits. No network, no models."""

from evals.realworld import PILOT, counts, difference, measures, ratio


def report(*labels: str, cited_by: str = "sentence") -> dict:
    return {
        "claims": [{"label": label, "cited_by": cited_by} for label in labels],
        "scorecard": {"pages_cited": 2, "pages_read": 1, "usd": 0.01},
    }


def row(qid: str, *labels: str, cited_by: str = "sentence") -> dict:
    return {"id": qid, "answer_usd": 0.05} | counts(report(*labels, cited_by=cited_by))


def test_counts_separate_failures_from_partial_and_unverdicted_claims() -> None:
    c = counts(
        report("supported", "partial", "not_found", "contradicted", "needs_human", "uncited")
    )
    assert c["claims"] == 6 and c["with_verdict"] == 4 and c["failed"] == 2
    assert c["contradicted"] == 1 and c["needs_human"] == 1 and c["uncited"] == 1


def test_the_failed_share_pools_claims_across_answers() -> None:
    rows = [row("a", "supported", "not_found"), row("b", "supported", "supported", "supported")]
    assert ratio(rows, "failed", "with_verdict") == 0.2  # 1 of 5, not the mean of 1/2 and 0/3
    m = measures(rows)
    assert m["failed_share_of_verdicts"]["value"] == 0.2
    low, high = m["failed_share_of_verdicts"]["ci_low"], m["failed_share_of_verdicts"]["ci_high"]
    assert low <= 0.2 <= high


def test_the_difference_between_tools_is_paired_by_question() -> None:
    a = [row("q1", "not_found"), row("q2", "supported")]
    b = [row("q1", "supported"), row("q2", "supported"), row("q3", "not_found")]
    d = difference(a, b)
    assert d["questions"] == 2 and d["value"] == 0.5


def test_the_pilot_is_the_fixed_ten() -> None:
    assert PILOT[:5] == ["nq-01", "nq-02", "nq-03", "nq-04", "nq-05"]
    assert PILOT[5:] == [
        "science-01",
        "health-01",
        "technology-01",
        "economy-01",
        "sport_culture-01",
    ]


def test_the_headline_counts_only_claims_whose_own_sentence_is_cited() -> None:
    rows = [
        row("a", "supported", "supported"),
        row("b", "not_found", "not_found", cited_by="paragraph"),
    ]
    m = measures(rows)
    assert m["headline_failed_share"]["value"] == 0.0 and m["headline_claims"] == 2
    assert m["paragraph_cited_failed_share"]["value"] == 1.0 and m["paragraph_cited_claims"] == 2
    assert m["failed_share_of_verdicts"]["value"] == 0.5  # everything together, also reported
