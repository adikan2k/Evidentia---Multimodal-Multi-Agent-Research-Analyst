import pytest

from evidentia.cost import (
    BudgetExceeded,
    Charge,
    Ledger,
    UnknownPrice,
    claude_usd,
    estimate_tokens,
    tavily_usd,
    voyage_usd,
)


def test_claude_price_is_per_million_tokens() -> None:
    assert claude_usd("claude-sonnet-5-5", 1_000_000, 0) == pytest.approx(2.00)
    assert claude_usd("claude-sonnet-5-5", 0, 1_000_000) == pytest.approx(10.00)
    assert claude_usd("claude-sonnet-5-5", 1_000, 500) == pytest.approx(0.007)


def test_cache_tokens_use_their_own_rates() -> None:
    assert claude_usd("claude-sonnet-5-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.20)
    assert claude_usd("claude-sonnet-5-5", 0, 0, cache_write=1_000_000) == pytest.approx(2.50)


def test_other_services() -> None:
    assert voyage_usd("voyage-4-large", 1_000_000) == pytest.approx(0.12)
    assert tavily_usd("basic", 4) == pytest.approx(0.032)


@pytest.mark.parametrize(
    "call",
    [
        lambda: claude_usd("claude-made-up", 1, 1),
        lambda: voyage_usd("voyage-made-up", 1),
        lambda: tavily_usd("deepest"),
    ],
)
def test_unpriced_models_are_refused(call) -> None:
    with pytest.raises(UnknownPrice):
        call()


def test_estimate_is_at_least_one_token() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 300) == 101


def test_ledger_blocks_a_call_that_could_pass_the_cap() -> None:
    ledger = Ledger(cap_usd=0.10)
    ledger.add(Charge(node="plan", item="claude-sonnet-5-5", usd=0.06))
    with ledger.reserve("write", 0.04):
        pass
    with pytest.raises(BudgetExceeded, match="cap is \$0.10"), ledger.reserve("write", 0.05):
        pass
    assert ledger.spent == pytest.approx(0.06)


def test_calls_in_flight_count_against_the_cap() -> None:
    ledger = Ledger(cap_usd=0.10)
    with ledger.reserve("check", 0.06):
        assert ledger.reserved == pytest.approx(0.06)
        with pytest.raises(BudgetExceeded, match="reserved"), ledger.reserve("check", 0.06):
            pass
        with ledger.reserve("check", 0.03):
            assert ledger.reserved == pytest.approx(0.09)
    assert ledger.reserved == pytest.approx(0.0)


def test_reservation_is_released_when_the_call_fails() -> None:
    ledger = Ledger(cap_usd=0.10)
    with pytest.raises(ValueError), ledger.reserve("check", 0.08):
        raise ValueError("network down")
    assert ledger.reserved == pytest.approx(0.0)
    with ledger.reserve("check", 0.08):
        pass


def test_budget_error_is_not_retried_by_langgraph() -> None:
    # LangGraph's default retry rule skips RuntimeError, so an exceeded budget ends the run.
    assert issubclass(BudgetExceeded, RuntimeError)


def test_ledger_totals_by_node() -> None:
    ledger = Ledger(cap_usd=1.0)
    ledger.add(Charge(node="search", item="tavily", usd=0.008))
    ledger.add(Charge(node="search", item="tavily", usd=0.008))
    ledger.add(Charge(node="write", item="m", input_tokens=10, output_tokens=5, usd=0.5))
    search, write = ledger.by_node()
    assert (search.node, search.calls, search.usd) == ("search", 2, pytest.approx(0.016))
    assert (write.input_tokens, write.output_tokens) == (10, 5)
