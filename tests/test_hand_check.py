"""The hand-check tool (D-044): the sample, what the screen shows, and the scoring."""

from rich.console import Console

from evals.hand_check import (
    PER_GROUP,
    choose_items,
    neutral_claim,
    neutral_url,
    show,
    summarise,
    upheld,
    wilson,
)


def pools(n: int = 30) -> dict:
    out = {}
    for tool in ("claude", "openai"):
        for group in ("failed", "supported"):
            out[(tool, group)] = [
                {
                    "item": f"{tool}:{group}{i}:0",
                    "tool": tool,
                    "group": group,
                    "auditor_label": group,
                    "claim": "c",
                    "urls": ["https://a.example.org/"],
                }
                for i in range(n)
            ]
    return out


def test_the_sample_is_fixed_and_balanced_in_every_block_of_four() -> None:
    items = choose_items(pools())
    assert items == choose_items(pools()) and len(items) == 4 * PER_GROUP
    for start in range(0, len(items), 4):
        block = items[start : start + 4]
        assert sorted((it["tool"], it["group"]) for it in block) == [
            ("claude", "failed"),
            ("claude", "supported"),
            ("openai", "failed"),
            ("openai", "supported"),
        ]
    assert len({it["item"] for it in items}) == len(items)


def test_nothing_on_screen_tells_which_tool_or_what_verdict() -> None:
    assert neutral_url("https://www.nps.gov/x.htm?eId=7&utm_source=openai&utm_medium=x") == (
        "https://www.nps.gov/x.htm?eId=7"
    )
    assert neutral_url("https://a.org/p") == "https://a.org/p"
    assert (
        neutral_claim("GPT-5 could still make mistakes. (openai.com)")
        == "GPT-5 could still make mistakes."
    )
    assert neutral_claim("Solar grew 24% in 2023 [1][2].") == "Solar grew 24% in 2023."
    item = {
        "item": "openai:nq-03:2",
        "tool": "openai",
        "group": "failed",
        "auditor_label": "not_found",
        "claim": "Haaland scored 36 goals.",
        "urls": ["https://www.premierleague.com/stats"],
    }
    console = Console(record=True, width=100)
    show(console, item, 3, 40)
    screen = console.export_text().lower()
    assert "haaland scored 36 goals." in screen and "premierleague.com" in screen
    for tell in ("openai", "claude", "failed", "not_found", "not on the", "supported", "nq-03"):
        assert tell not in screen


def test_wilson_interval_for_small_samples() -> None:
    assert wilson(0, 0)["share"] is None
    eight = wilson(8, 10)
    assert (
        eight["share"] == 0.8 and 0.48 < eight["ci_low"] < 0.50 and 0.94 < eight["ci_high"] < 0.95
    )
    assert wilson(10, 10)["ci_high"] == 1.0 and wilson(10, 10)["ci_low"] > 0.7


def test_a_flag_is_upheld_by_no_and_a_supported_verdict_by_yes() -> None:
    items = [
        {"item": "a", "tool": "openai", "group": "failed", "auditor_label": "not_found"},
        {"item": "b", "tool": "openai", "group": "failed", "auditor_label": "contradicted"},
        {"item": "c", "tool": "claude", "group": "failed", "auditor_label": "not_found"},
        {"item": "d", "tool": "claude", "group": "supported", "auditor_label": "supported"},
        {"item": "e", "tool": "claude", "group": "supported", "auditor_label": "supported"},
    ]
    labels = {
        "a": {"answer": "no", "seconds": 40.0},
        "b": {"answer": "yes", "seconds": 60.0},
        "c": {"answer": "unsure", "seconds": 90.0},
        "d": {"answer": "yes", "seconds": 30.0},
    }
    flags = upheld(items, labels, "failed", None)
    assert (flags["hits"], flags["n"], flags["unsure"]) == (1, 2, 1)
    assert upheld(items, labels, "failed", "claude")["n"] == 0
    body = summarise(items, labels)
    assert body["items_checked"] == 4 and body["median_seconds_per_item"] == 50.0
    assert body["supported_upheld"]["both_tools"]["share"] == 1.0
    assert body["rule"]["met"] is False  # 1 of 2 flags upheld is under 70%
    assert body["disagreements"] == [{"item": "b", "auditor": "contradicted", "person": "yes"}]


# D-049: the second check.


def share(hits: int, n: int) -> dict:
    return wilson(hits, n) | {"unsure": 0, "would_not_open": 0}


def test_the_first_check_keeps_its_rule_and_the_second_adds_a_guard_for_each_tool() -> None:
    from evals.hand_check import FIRST, SECOND, rule

    # 14 of 20 upheld together, but one tool only 4 of 10: met under D-044, not under D-049.
    flags = {"both_tools": share(14, 20), "openai": share(10, 10), "claude": share(4, 10)}
    assert rule(flags, FIRST.per_tool_guard) == {"flags_upheld_needed_both_tools": 0.7, "met": True}
    second = rule(flags, SECOND.per_tool_guard)
    assert second["met"] is False
    assert second["per_tool_guard"] == {"tools_clearly_below": ["claude"]}
    # 5 of 10 is not clearly below 70%, so the guard does not trip on it.
    flags = {"both_tools": share(15, 20), "openai": share(10, 10), "claude": share(5, 10)}
    assert rule(flags, True)["met"] is True


def test_the_second_check_is_drawn_from_the_new_audits_with_its_own_seed() -> None:
    from evals.hand_check import FIRST, SECOND
    from evals.realworld import REST

    assert SECOND.audits == REST and FIRST.audits != REST
    assert SECOND.seed != FIRST.seed and SECOND.leave_out == FIRST.items
    assert SECOND.items != FIRST.items and SECOND.labels != FIRST.labels
    assert choose_items(pools(), SECOND.seed) != choose_items(pools(), FIRST.seed)


def test_sentences_the_labeller_has_seen_are_left_out(tmp_path, monkeypatch) -> None:
    import json

    import evals.hand_check as hc
    from evals.realworld import audit_path

    def write(root, tool, qid, claims):
        path = audit_path("haiku", tool, qid, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"report": {"claims": claims}}), encoding="utf-8")

    def claim(sentence, label):
        return {
            "sentence": sentence,
            "claim": sentence,
            "label": label,
            "cited_by": "sentence",
            "pages": [{"url": "https://a.example.org/"}],
        }

    old, new = tmp_path / "old", tmp_path / "new"
    monkeypatch.setattr(hc, "load_questions", lambda which: [{"id": "q1"}])
    monkeypatch.setattr(hc, "audit_path", lambda j, t, q, root=old: audit_path(j, t, q, root))
    write(old, "openai", "q1", [claim("Seen before.", "not_found")])
    write(new, "openai", "q1", [claim("Seen before.", "contradicted"), claim("New.", "not_found")])
    items = tmp_path / "items.json"
    items.write_text(json.dumps([{"item": "openai:q1:0"}]), encoding="utf-8")

    seen = hc.seen_sentences(items)
    assert seen == {("openai", "q1", "Seen before.")}
    pool = hc.candidates(new, seen)[("openai", "failed")]
    assert [p["claim"] for p in pool] == ["New."]


def test_the_second_sample_keeps_the_flags_and_mixes_in_a_few_supported_claims() -> None:
    from collections import Counter

    from evals.hand_check import SECOND, choose_flags_first

    flags, supported = SECOND.flags_and_supported
    items = choose_flags_first(pools(), SECOND.seed, flags, supported)
    assert items == choose_flags_first(pools(), SECOND.seed, flags, supported)
    assert len(items) == 24 and len({it["item"] for it in items}) == 24
    assert Counter((it["tool"], it["group"]) for it in items) == {
        ("claude", "failed"): 10,
        ("openai", "failed"): 10,
        ("claude", "supported"): 2,
        ("openai", "supported"): 2,
    }
    # Stopping early leaves the tools' flags balanced to within one.
    for stop in range(len(items) + 1):
        done = Counter(it["tool"] for it in items[:stop] if it["group"] == "failed")
        assert abs(done["claude"] - done["openai"]) <= 1


def test_a_tool_with_too_few_flags_gives_all_it_has() -> None:
    from collections import Counter

    from evals.hand_check import choose_flags_first

    few = pools()
    few[("claude", "failed")] = few[("claude", "failed")][:7]
    items = choose_flags_first(few, 1, 10, 2)
    counts = Counter((it["tool"], it["group"]) for it in items)
    assert counts[("claude", "failed")] == 7 and counts[("openai", "failed")] == 10
    assert len(items) == 21
    flags = [it["tool"] for it in items if it["group"] == "failed"]
    for stop in range(15):  # balanced while both tools have flags left
        assert abs(flags[:stop].count("claude") - flags[:stop].count("openai")) <= 1
