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
