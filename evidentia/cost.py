"""Price table and the per-run ledger that enforces the hard cost cap."""

from pydantic import BaseModel

# US dollars per million tokens: (input, output).
# Source: Anthropic model pricing as cached in the Claude API reference on 2026-11-03.
# Haiku 5.5's price applies to prompts up to 100K tokens, which is far above anything we send.
CLAUDE_PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
# Cache reads cost a tenth of input and cache writes 1.25 times input. M1 does not cache.
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25

# US dollars per million tokens. Source: https://docs.voyageai.com/docs/pricing read 2026-11-24.
VOYAGE_PRICES: dict[str, float] = {
    "voyage-4-large": 0.12,
    "voyage-4": 0.06,
    "voyage-4-lite": 0.02,
    "rerank-3": 0.05,
    "rerank-3-lite": 0.02,
}

# Source: https://docs.tavily.com/documentation/api-credits read 2026-11-24.
TAVILY_USD_PER_CREDIT = 0.008
TAVILY_CREDITS = {"basic": 1, "advanced": 2}

# Rough upper estimate used only for the check before a call. Actual tokens are recorded after.
CHARS_PER_TOKEN = 3


class BudgetExceeded(RuntimeError):
    """The next call could take the run past its cost cap, so it was not made."""


class UnknownPrice(RuntimeError):
    """A model with no price cannot be costed, so it cannot be capped. Refuse to call it."""


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN + 1


def claude_usd(
    model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0
) -> float:
    if model not in CLAUDE_PRICES:
        raise UnknownPrice(model)
    price_in, price_out = CLAUDE_PRICES[model]
    weighted_in = input_tokens + cache_read * CACHE_READ_FACTOR + cache_write * CACHE_WRITE_FACTOR
    return (weighted_in * price_in + output_tokens * price_out) / 1_000_000


def voyage_usd(model: str, tokens: int) -> float:
    if model not in VOYAGE_PRICES:
        raise UnknownPrice(model)
    return tokens * VOYAGE_PRICES[model] / 1_000_000


def tavily_usd(depth: str, searches: int = 1) -> float:
    if depth not in TAVILY_CREDITS:
        raise UnknownPrice(depth)
    return searches * TAVILY_CREDITS[depth] * TAVILY_USD_PER_CREDIT


class Charge(BaseModel):
    node: str
    item: str
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float


class NodeTotal(BaseModel):
    node: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0


class Ledger:
    def __init__(self, cap_usd: float) -> None:
        self.cap_usd = cap_usd
        self.charges: list[Charge] = []

    @property
    def spent(self) -> float:
        return sum(c.usd for c in self.charges)

    def check(self, node: str, worst_case_usd: float) -> None:
        """Call before every paid request. Raises instead of letting the run pass the cap."""
        if self.spent + worst_case_usd > self.cap_usd:
            raise BudgetExceeded(
                f"{node}: spent ${self.spent:.4f}, next call could cost up to "
                f"${worst_case_usd:.4f}, cap is ${self.cap_usd:.2f}"
            )

    def add(self, charge: Charge) -> None:
        self.charges.append(charge)

    def by_node(self) -> list[NodeTotal]:
        totals: dict[str, NodeTotal] = {}
        for c in self.charges:
            t = totals.setdefault(c.node, NodeTotal(node=c.node))
            t.calls += 1
            t.input_tokens += c.input_tokens
            t.output_tokens += c.output_tokens
            t.usd += c.usd
        return list(totals.values())
