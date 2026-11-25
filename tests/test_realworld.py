"""The real-world audit's bookkeeping (D-042), with made-up audits. No network, no models."""

from types import SimpleNamespace

from evals.realworld import (
    PILOT,
    REASK_PER_SOURCE,
    REPEATS,
    choose_reask,
    counts,
    difference,
    marker_check,
    measures,
    pooled,
    ratio,
    reask_items,
    searches_used,
    within_question_range,
)
from evidentia.audit.answers import with_markers


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


def made_up_questions() -> list[dict]:
    return [
        {"id": f"{source[:2]}-{n:02d}", "source": source, "question": f"Q {n}?"}
        for source in ("natural_questions", "2025_2026")
        for n in range(1, 31)
    ]


def test_the_reask_takes_the_same_number_from_each_source_and_never_changes() -> None:
    chosen = choose_reask(made_up_questions())
    for source in ("natural_questions", "2025_2026"):
        assert sum(q["source"] == source for q in chosen) == REASK_PER_SOURCE
    assert chosen == choose_reask(list(reversed(made_up_questions())))  # order in, same out
    items = reask_items(made_up_questions())
    assert len(items) == len(chosen) * REPEATS and len({i["id"] for i in items}) == len(items)
    assert items[0]["id"] == f"{items[0]['of']}-r1" and items[0]["question"]


def test_a_marker_in_the_wrong_place_is_counted() -> None:
    raw = "Solar grew 24% in 2023. Wind grew 10%. Hydro was flat."
    a, b = "https://a.example.org/x", "https://b.example.org/y"
    notes = [{"url": a, "start": 0, "end": 23}, {"url": b, "start": 24, "end": 38}]
    cites = [
        SimpleNamespace(url=n["url"], start_index=n["start"], end_index=n["end"]) for n in notes
    ]
    good = with_markers(raw, cites)
    assert marker_check(raw, notes, good) == {
        "annotations": 2,
        "links_the_tool_wrote_inline": 0,
        "markers_added_by_our_code": 2,
        "misplaced": 0,
        "spans_over_one_sentence": 0,
    }
    moved = good.replace("Wind grew 10%.[2] Hydro was flat.", "Wind grew 10%. Hydro was flat.[2]")
    assert moved != good and marker_check(raw, notes, moved)["misplaced"] == 1
    wide = [{"url": a, "start": 0, "end": 38}]
    marked = raw[:38] + "[1]" + raw[38:] + f"\n\nSources:\n[1] {a}"
    check = marker_check(raw, wide, marked)
    assert check["misplaced"] == 0 and check["spans_over_one_sentence"] == 1
    linked = f"Solar grew. ([a]({a}))"
    own = marker_check(linked, [{"url": a, "start": 12, "end": len(linked)}], linked)
    assert own["links_the_tool_wrote_inline"] == 1 and own["markers_added_by_our_code"] == 0


def test_repeats_are_pooled_by_question_and_their_range_is_reported() -> None:
    r1 = [row("q1", "not_found", "supported"), row("q2", "supported")]
    r2 = [row("q1", "supported", "supported"), row("q2", "supported")]
    both = pooled(r1 + r2)
    assert len(both) == 2 and both[0]["verdict_own"] == 4 and both[0]["failed_own"] == 1
    spread = within_question_range({"r1": r1, "r2": r2})
    assert spread == {"questions": 2, "median": 0.25, "mean": 0.25, "max": 0.5}


def test_searches_are_counted_against_the_cap() -> None:
    used = searches_used([{"searches": 2}, {"searches": 5}, {"searches": 6}, {}])
    assert used["answers"] == 3 and used["mean"] == 4.33 and used["max"] == 6
    assert used["answers_at_or_over_the_cap"] == 2 and used["answers_with_no_search"] == 0
    assert searches_used([{"searches": 0}, {"searches": 1}])["answers_with_no_search"] == 1


# D-049: the re-audit reuses saved answers and reads the rest of the page.


def test_the_reaudit_never_asks_for_a_new_answer(settings, tmp_path) -> None:
    import asyncio

    import pytest

    from evals.realworld import Runner
    from evidentia.tracing import NoopTracer

    runner = Runner(settings, 0.01, NoopTracer(), tmp_path / "new", answers_root=tmp_path / "old")
    with pytest.raises(FileNotFoundError):
        asyncio.run(runner.answer("openai", {"id": "q1", "question": "?"}))
    assert runner.fetcher.rest_of_page is settings.audit_rest_of_page is True
    asyncio.run(runner.fetcher.aclose())


def test_the_auditor_reads_the_rest_of_the_page_and_the_research_agent_does_not(settings) -> None:
    import asyncio

    from evidentia.audit.cli import build_audit_deps
    from evidentia.cost import Ledger
    from evidentia.fetch import Fetcher
    from evidentia.tracing import NoopTracer

    deps = build_audit_deps(settings, Ledger(0.01), NoopTracer())
    assert deps.fetcher.rest_of_page is True
    assert Fetcher(settings, NoopTracer()).rest_of_page is False  # the research agent's
    asyncio.run(deps.fetcher.aclose())
