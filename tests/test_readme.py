"""The README's results block is written from the result files, never by hand (rule 7)."""

import pytest

from evals import readme
from evals.retrieval import best_possible


def test_the_readme_shows_exactly_what_the_result_files_say() -> None:
    text = readme.README.read_text(encoding="utf-8")
    assert readme.START in text and readme.END in text
    # If this fails, run `uv run python -m evals report` and commit the README.
    assert readme.with_block(text) == text


def test_the_block_is_replaced_and_nothing_around_it_changes() -> None:
    page = f"before\n{readme.START}\nold numbers\n{readme.END}\nafter\n"
    out = readme.with_block(page)
    assert out.startswith("before\n") and out.endswith("\nafter\n")
    assert "old numbers" not in out and "Results at a glance" in out


def test_a_perfect_ranking_is_limited_by_how_many_passages_are_relevant() -> None:
    best = best_possible([1, 3])
    assert best["recall_at_1"] == pytest.approx((1 + 1 / 3) / 2, abs=1e-4)
    assert best["precision_at_10"] == pytest.approx((0.1 + 0.3) / 2)
    assert best["mrr_at_10"] == 1.0 and best["ndcg_at_10"] == 1.0
