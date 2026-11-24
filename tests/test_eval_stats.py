import pytest

from evals.corpus import page_id, page_record, trim
from evals.stats import (
    agreement,
    bootstrap_ci,
    cohen_kappa,
    confusion,
    mean,
    ndcg_at_k,
    paired_difference,
    precision_recall,
    recall_at_k,
    reciprocal_rank,
    summary,
)
from evidentia.tracing import MAX_TRACED_CHARS, shorten

T, F = True, False


def test_mean_of_nothing_is_zero() -> None:
    assert mean([]) == 0.0
    assert mean([1, 2, 3]) == 2.0


def test_bootstrap_interval_contains_the_mean_and_is_repeatable() -> None:
    values = [0, 0, 1, 1, 1, 0, 1, 1, 0, 1] * 4
    low, high = bootstrap_ci(values)
    assert low < mean(values) < high
    assert 0.3 < low and high < 0.9
    assert bootstrap_ci(values) == (low, high)  # fixed seed


def test_bootstrap_of_identical_values_has_no_width() -> None:
    assert bootstrap_ci([0.5] * 20) == (0.5, 0.5)
    assert bootstrap_ci([]) == (0.0, 0.0)


def test_summary_reports_mean_interval_and_count() -> None:
    result = summary([1.0, 1.0, 0.0, 1.0])
    assert result["mean"] == 0.75 and result["n"] == 4
    assert result["ci_low"] <= 0.75 <= result["ci_high"]


def test_paired_difference_is_per_question() -> None:
    result = paired_difference([1.0, 0.5, 1.0], [0.5, 0.5, 0.0])
    assert result["mean"] == pytest.approx(0.5)
    with pytest.raises(ValueError):
        paired_difference([1.0], [1.0, 0.0])


def test_recall_counts_relevant_passages_in_the_top_k() -> None:
    assert recall_at_k([T, F, T, F], total_relevant=4) == 0.5
    assert recall_at_k([F] * 10 + [T], total_relevant=1) == 0.0  # rank 11 is outside the top 10
    assert recall_at_k([T], total_relevant=0) == 0.0


def test_reciprocal_rank_uses_the_first_relevant_passage() -> None:
    assert reciprocal_rank([F, F, T, T]) == pytest.approx(1 / 3)
    assert reciprocal_rank([T]) == 1.0
    assert reciprocal_rank([F, F]) == 0.0


def test_ndcg_is_one_for_a_perfect_order_and_lower_when_relevant_passages_sink() -> None:
    assert ndcg_at_k([T, T, F, F], total_relevant=2) == pytest.approx(1.0)
    assert 0 < ndcg_at_k([F, F, T, T], total_relevant=2) < ndcg_at_k([T, F, T], total_relevant=2)
    assert ndcg_at_k([F, F], total_relevant=2) == 0.0


def test_agreement_and_kappa() -> None:
    same = [("supported", "supported"), ("partial", "partial"), ("unsupported", "unsupported")]
    assert agreement(same) == 1.0 and cohen_kappa(same) == pytest.approx(1.0)
    # The model always says "supported": 50% raw agreement, but no better than chance.
    lazy = [("supported", "supported"), ("partial", "supported")] * 5
    assert agreement(lazy) == 0.5 and cohen_kappa(lazy) == pytest.approx(0.0)
    assert cohen_kappa([]) == 0.0


def test_confusion_table_and_per_label_scores() -> None:
    pairs = [("supported", "supported"), ("supported", "partial"), ("partial", "partial")]
    table = confusion(pairs, ["supported", "partial"])
    assert table == {
        "supported": {"supported": 1, "partial": 1},
        "partial": {"supported": 0, "partial": 1},
    }
    scores = precision_recall(pairs, "partial")
    assert scores == {"precision": 0.5, "recall": 1.0, "model_count": 2, "human_count": 1}


def test_page_ids_are_short_and_readable() -> None:
    assert page_id("https://en.wikipedia.org/wiki/Mount_Everest") == "wiki-mount-everest"
    assert page_id("https://en.wikipedia.org/wiki/El_Ni%C3%B1o") == "wiki-el-ni-o"
    assert page_id("https://ourworldindata.org/life-expectancy") == "owid-life-expectancy"
    assert page_id("https://oceanservice.noaa.gov/facts/ninonina.html") == "noaa-ninonina"


def test_long_pages_are_cut_at_a_paragraph_break() -> None:
    text = "\n".join(["x" * 99] * 10)
    cut = trim(text, limit=250)
    assert cut == "\n".join(["x" * 99] * 2)
    assert trim("short", limit=250) == "short"


def test_page_record_carries_licence_and_hash() -> None:
    wiki = page_record("https://en.wikipedia.org/wiki/Black_hole", "Some text.")
    gov = page_record("https://www.epa.gov/ozone/basic-science", "Other text.")
    assert wiki["licence"] == "CC BY-SA 4.0" and wiki["title"] == "Black hole"
    assert gov["licence"].startswith("Public domain")
    assert len(wiki["sha256"]) == 64 and wiki["chars"] == 10


def test_very_long_strings_are_cut_before_tracing_but_prompts_are_not() -> None:
    page = "p" * (MAX_TRACED_CHARS + 5_000)
    prompt = "q" * (MAX_TRACED_CHARS - 1)
    traced = shorten(data={"sources": [{"text": page}], "prompt": prompt, "n": 3})
    assert len(traced["sources"][0]["text"]) < 2_100
    assert "more characters not traced" in traced["sources"][0]["text"]
    assert traced["prompt"] == prompt and traced["n"] == 3
