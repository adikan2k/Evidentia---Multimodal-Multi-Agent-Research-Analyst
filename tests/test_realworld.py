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


def test_both_readings_and_every_label_are_reported() -> None:
    rows = [
        row("a", "supported", "not_found", "uncited", "uncited"),
        row("b", "supported", "unchecked"),
    ]
    m = measures(rows)
    assert m["headline_failed_share"]["value"] == round(1 / 3, 4)  # of claims with a verdict
    assert m["verified_share_of_all_claims"]["value"] == round(2 / 6, 4)  # of everything said
    assert m["labels"]["uncited"] == {"claims": 2, "share": round(2 / 6, 4)}
    assert sum(v["claims"] for v in m["labels"].values()) == m["claims"] == 6


def test_bounds_cover_what_the_unread_pages_could_have_been() -> None:
    from evals.realworld import bounds

    rows = [row("a", "supported", "not_found", "unchecked", "unchecked", "needs_human")]
    unread = bounds(rows, ("unread_own",))
    assert unread == {"undecided_claims": 2, "if_all_supported": 0.25, "if_none_supported": 0.75}
    wider = bounds(rows, ("unread_own", "needs_human_own"))
    assert wider["undecided_claims"] == 3 and wider["if_all_supported"] == 0.2


def test_pages_not_read_are_counted_once_each_by_site_and_reason() -> None:
    from evals.realworld import pages_not_read

    def claim(url: str, skipped: str | None) -> dict:
        return {"pages": [{"url": url, "skipped": skipped}]}

    reports = [
        {
            "claims": [
                claim("https://www.a.org/1", "HTTP 403"),
                claim("https://www.a.org/1", "HTTP 403"),
            ]
        },
        {
            "claims": [
                claim("https://a.org/2", "disallowed by robots.txt"),
                claim("https://b.org/x", None),
            ]
        },
    ]
    got = pages_not_read(reports)
    assert got["pages_cited"] == 3 and got["pages_not_read"] == 2
    assert got["by_reason"] == {"HTTP 403": 1, "disallowed by robots.txt": 1}
    assert got["sites_most_often_not_read"][0]["site"] == "a.org"


def test_the_difference_can_be_taken_on_the_share_of_all_claims() -> None:
    a = [row("q1", "supported", "uncited")]
    b = [row("q1", "supported", "supported", "supported", "uncited")]
    assert difference(a, b, top="supported", bottom="claims")["value"] == -0.25
