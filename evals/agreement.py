"""How often does the checker give the same label as Aditya? (D-018)

Runs the checker prompt on every hand-labelled pair with three models and compares.
"""

import asyncio

from evals.common import LABELS, PAIRS, RUNS_DIR, eval_deps, read_jsonl, write_jsonl, write_result
from evals.stats import agreement, bootstrap_ci, cohen_kappa, confusion, precision_recall
from evidentia.graph import Deps
from evidentia.llm import CHECK_SYSTEM, ModelStopped, check_prompt, new_tag, with_tag
from evidentia.schemas import Judgement

VERDICTS = RUNS_DIR / "checker_verdicts.jsonl"
LABEL_NAMES = ["supported", "partial", "unsupported"]
MODELS = ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"]


async def verdict(deps: Deps, model: str, claim: str, evidence: str, node: str) -> dict:
    """One checker call. Shared with the judge, which is the same prompt on another model."""
    tag = new_tag("quote")
    try:
        result = await deps.llm.structured(
            node=node,
            model=model,
            effort=deps.settings.checker_effort,
            max_tokens=deps.settings.checker_max_tokens,
            system=with_tag(CHECK_SYSTEM, tag),
            user=check_prompt(claim, evidence, tag),
            schema=Judgement,
            config={"callbacks": deps.tracer.callbacks()},
        )
    except ModelStopped:
        return {"label": "none", "reason": "the model did not return a verdict"}
    return {"label": result.label, "reason": result.reason}


async def collect(deps: Deps, pairs: list[dict]) -> dict[tuple[str, str], dict]:
    """Verdicts for every pair and model, reusing any saved from an earlier run."""
    saved = {(row["id"], row["model"]): row for row in read_jsonl(VERDICTS)}
    limit = asyncio.Semaphore(4)

    async def one(pair: dict, model: str) -> None:
        async with limit:
            answer = await verdict(deps, model, pair["claim"], pair["quote"], f"agreement-{model}")
        saved[(pair["id"], model)] = {"id": pair["id"], "model": model} | answer

    missing = [(p, m) for p in pairs for m in MODELS if (p["id"], m) not in saved]
    await asyncio.gather(*(one(pair, model) for pair, model in missing))
    write_jsonl(VERDICTS, [saved[key] for key in sorted(saved)])
    return saved


def with_interval(stat, pairs: list[tuple[str, str]]) -> dict[str, float]:
    low, high = bootstrap_ci(pairs, stat)
    return {"value": round(stat(pairs), 4), "ci_low": round(low, 4), "ci_high": round(high, 4)}


def measure(pairs: list[tuple[str, str]]) -> dict:
    """`pairs` are (human label, model label)."""
    return {
        "n": len(pairs),
        "agreement": with_interval(agreement, pairs),
        "cohen_kappa": with_interval(cohen_kappa, pairs),
        "confusion_human_rows_model_columns": confusion(pairs, [*LABEL_NAMES, "none"]),
        "per_label": {label: precision_recall(pairs, label) for label in LABEL_NAMES},
    }


async def run() -> None:
    human = {row["id"]: row["label"] for row in read_jsonl(LABELS)}
    pairs = [p for p in read_jsonl(PAIRS) if p["id"] in human]
    if not pairs:
        print("agreement: no hand labels yet. Run `uv run python -m evals label` first.")
        return
    async with eval_deps("eval.agreement") as deps:
        verdicts = await collect(deps, pairs)
        spent = deps.ledger.spent
    built = [p for p in pairs if p["origin"] != "natural"]
    natural = [p for p in pairs if p["origin"] == "natural"]
    by_model = {}
    for model in MODELS:

        def both(subset: list[dict], model: str = model) -> list[tuple[str, str]]:
            return [(human[p["id"]], verdicts[(p["id"], model)]["label"]) for p in subset]

        by_model[model] = {
            "all": measure(both(pairs)),
            "natural_pairs": measure(both(natural)),
            "built_pairs": measure(both(built)),
            "disagreements": [
                {
                    "id": p["id"],
                    "origin": p["origin"],
                    "human": human[p["id"]],
                    "model": verdicts[(p["id"], model)]["label"],
                    "model_reason": verdicts[(p["id"], model)]["reason"],
                    "claim": p["claim"],
                    "quote": p["quote"],
                }
                for p in pairs
                if human[p["id"]] != verdicts[(p["id"], model)]["label"]
            ],
        }
    path = write_result(
        "checker_agreement",
        {
            "what": "Checker labels compared with one person's hand labels on the same pairs.",
            "labeller": "Aditya, shown only the claim and the quote, in shuffled order.",
            "caveat": "One labeller, so there is no measure of how far two people would disagree.",
            "pairs_labelled": len(pairs),
            "pairs_total": len(read_jsonl(PAIRS)),
            "product_checker": MODELS[0],
            "interval": "95% bootstrap over pairs, 2000 resamples",
            "models": by_model,
            "cost_usd": round(spent, 4),
        },
    )
    print(f"agreement: wrote {path} for {len(pairs)} labelled pairs (cost ${spent:.2f})")
