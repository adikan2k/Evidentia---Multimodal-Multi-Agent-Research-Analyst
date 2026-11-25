"""The arithmetic behind every reported number. Plain Python, no models, fully tested."""

import math
import random
from collections import Counter
from collections.abc import Callable, Sequence

RESAMPLES = 2000
SEED = 20261124


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def bootstrap_ci(
    items: Sequence,
    stat: Callable[[Sequence], float] = mean,
    resamples: int = RESAMPLES,
    seed: int = SEED,
) -> tuple[float, float]:
    """95% interval: recompute `stat` on many samples drawn from `items` with replacement.

    It answers "how much would this number move if we had asked a different 40 questions?".
    """
    if not items:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(items)
    stats = sorted(stat([items[rng.randrange(n)] for _ in range(n)]) for _ in range(resamples))
    return (stats[int(0.025 * resamples)], stats[int(0.975 * resamples) - 1])


def summary(values: Sequence[float]) -> dict[str, float | int]:
    low, high = bootstrap_ci(values)
    return {"mean": round(mean(values), 4), "ci_low": round(low, 4), "ci_high": round(high, 4)} | {
        "n": len(values)
    }


def paired_difference(a: Sequence[float], b: Sequence[float]) -> dict[str, float | int]:
    """Mean of `a[i] - b[i]` with its interval. The same questions are used for both systems,
    so comparing them question by question removes the noise of some questions being harder."""
    return summary([x - y for x, y in zip(a, b, strict=True)])


# --- retrieval: `hits` is the ranked list, True where the passage is relevant ---------------


def recall_at_k(hits: Sequence[bool], total_relevant: int, k: int = 10) -> float:
    return sum(hits[:k]) / total_relevant if total_relevant else 0.0


def precision_at_k(hits: Sequence[bool], k: int = 10) -> float:
    """Share of the top k that is relevant. A question with fewer than k relevant passages
    cannot reach 1.0, so this is read next to the number of relevant passages."""
    return sum(hits[:k]) / k


def reciprocal_rank(hits: Sequence[bool], k: int = 10) -> float:
    for rank, hit in enumerate(hits[:k], start=1):
        if hit:
            return 1 / rank
    return 0.0


def ndcg_at_k(hits: Sequence[bool], total_relevant: int, k: int = 10) -> float:
    """Rewards relevant passages more the higher they rank; 1.0 is the best possible order."""
    gain = sum(1 / math.log2(rank + 1) for rank, hit in enumerate(hits[:k], start=1) if hit)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(total_relevant, k) + 1))
    return gain / ideal if ideal else 0.0


# --- agreement between two labellers ----------------------------------------------------------


def agreement(pairs: Sequence[tuple[str, str]]) -> float:
    return mean([a == b for a, b in pairs])


def cohen_kappa(pairs: Sequence[tuple[str, str]]) -> float:
    """Agreement corrected for chance: 0 is what guessing would give, 1 is perfect."""
    if not pairs:
        return 0.0
    observed = agreement(pairs)
    first, second = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(first[label] * second[label] for label in first) / len(pairs) ** 2
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def confusion(pairs: Sequence[tuple[str, str]], labels: Sequence[str]) -> dict[str, dict[str, int]]:
    """`table[human][model]` is how many pairs got that combination."""
    counts = Counter(pairs)
    return {a: {b: counts[(a, b)] for b in labels} for a in labels}


def precision_recall(pairs: Sequence[tuple[str, str]], label: str) -> dict[str, float]:
    """For one label: of the times the model said it, how often the human agreed (precision),
    and of the times the human said it, how often the model found it (recall)."""
    said = [human for human, model in pairs if model == label]
    truth = [model for human, model in pairs if human == label]
    return {
        "precision": round(mean([h == label for h in said]), 4),
        "recall": round(mean([m == label for m in truth]), 4),
        "model_count": len(said),
        "human_count": len(truth),
    }
