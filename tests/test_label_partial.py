from rich.console import Console

from evals.aggrefact import Row
from evals.label_partial import CONTROL_ITEMS, PARTIAL_ITEMS, choose_items, show, tally


def joined(n: int = 300) -> tuple[list[dict], dict[int, Row]]:
    labels = ["partial", "supported", "not_found", "needs_human"]
    lines = [{"row": i, "two_label": labels[i % 4]} for i in range(n)]
    rows = {
        i: Row(
            split="dev",
            row=i,
            dataset="D",
            doc="d" * (100 if i % 7 else 9000),
            claim="c",
            label=i % 2,
        )
        for i in range(n)
    }
    return lines, rows


def test_items_are_fixed_short_and_mixed() -> None:
    lines, rows = joined()
    items = choose_items(lines, rows)
    assert items == choose_items(list(reversed(lines)), rows)
    groups = [it["group"] for it in items]
    assert groups.count("partial") == PARTIAL_ITEMS
    assert groups.count("supported") + groups.count("not_found") == CONTROL_ITEMS
    assert all(len(rows[it["row"]].doc) <= 8000 for it in items)
    assert groups[:5] != ["partial"] * 5 or groups[5:10] != ["partial"] * 5  # shuffled in


def test_the_screen_shows_only_the_claim_and_the_document() -> None:
    row = Row(
        split="dev",
        row=7,
        dataset="AggreFact-CNN",
        doc="The document.",
        claim="The claim.",
        label=1,
    )
    console = Console(record=True, width=80)
    show(console, row, 1, 50)
    screen = console.export_text()
    assert "The claim." in screen and "The document." in screen
    assert "AggreFact" not in screen and "partial" not in screen.lower()
    assert "label" not in screen.lower() and "supported" not in screen.lower()


def test_tally_counts_answers_and_agreement_with_the_benchmark() -> None:
    items = [
        {"row": 1, "group": "partial"},
        {"row": 2, "group": "partial"},
        {"row": 3, "group": "partial"},
        {"row": 4, "group": "supported"},
    ]
    labels = {
        1: {"answer": "yes"},
        2: {"answer": "no"},
        3: {"answer": "unsure"},
        4: {"answer": "yes"},
    }
    benchmark = {1: 1, 2: 1, 3: 0, 4: 1}
    got = tally(items, labels, benchmark)
    assert got["partial"] == {
        "labelled": 3,
        "answers": {"yes": 1, "no": 1, "unsure": 1},
        "agrees_with_benchmark": 1,
        "decided": 2,
    }
    assert got["supported"]["agrees_with_benchmark"] == 1 and got["not_found"]["labelled"] == 0
