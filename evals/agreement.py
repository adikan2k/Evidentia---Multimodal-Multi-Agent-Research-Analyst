"""How well does the checker label claim-and-quote pairs? (D-018)

Three checker models label every pair. Their answers are compared with up to two reference sets:

- `labels.jsonl`: labels made by a person with the labelling tool. This is the measurement the
  plan asks for. It is empty until someone does the labelling.
- `labels_model.jsonl`: labels made by a different, stronger model reading the same two strings.
  Useful as a second opinion, but it is not a human and must never be reported as one.

A third check needs no labels at all: a third of the pairs were deliberately broken when they
were built, so we can count how many of those each checker flags.
"""

import asyncio

from evals.common import (
    LABELS,
    MODEL_LABELS,
    PAIRS,
    RUNS_DIR,
    eval_deps,
    read_jsonl,
    write_jsonl,
    write_result,
)
from evals.stats import agreement, bootstrap_ci, cohen_kappa, confusion, mean, precision_recall
from evidentia.graph import Deps
from evidentia.llm import CHECK_SYSTEM, ModelStopped, check_prompt, new_tag, with_tag
from evidentia.schemas import Judgement

VERDICTS = RUNS_DIR / "checker_verdicts.jsonl"
LABEL_NAMES = ["supported", "partial", "unsupported"]
MODELS = ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"]
BUILT_KINDS = ["wrong_quote", "changed_fact", "added_detail"]

REFERENCES = {
    "person": {
        "path": LABELS,
        "labeller": "A person using the labelling tool, shown only the claim and the quote.",
        "caveat": "One labeller, so there is no measure of how far two people would disagree.",
    },
    "second_model": {
        "path": MODEL_LABELS,
        "labeller": "Claude Fable 5.2, shown only the claim and the quote. NOT a person.",
        "caveat": "This is one model agreeing with another from the same family. It says the "
        "checker is consistent with a stronger model; it does not say either is right. "
        "Convention used: a pronoun in the quote that plainly refers to the page's subject is "
        "not counted as a missing fact, but an added number, date, cause or 'who said it' is.",
    },
}


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
        write_jsonl(VERDICTS, [saved[key] for key in sorted(saved)])

    missing = [(p, m) for p in pairs for m in MODELS if (p["id"], m) not in saved]
    await asyncio.gather(*(one(pair, model) for pair, model in missing))
    return saved


def with_interval(stat, items: list) -> dict[str, float]:
    low, high = bootstrap_ci(items, stat)
    return {"value": round(stat(items), 4), "ci_low": round(low, 4), "ci_high": round(high, 4)}


def measure(pairs: list[tuple[str, str]]) -> dict:
    """`pairs` are (reference label, checker label)."""
    return {
        "n": len(pairs),
        "agreement": with_interval(agreement, pairs),
        "cohen_kappa": with_interval(cohen_kappa, pairs),
        "confusion_reference_rows_checker_columns": confusion(pairs, [*LABEL_NAMES, "none"]),
        "per_label": {label: precision_recall(pairs, label) for label in LABEL_NAMES},
    }


def compare(pairs: list[dict], reference: dict[str, str], verdicts: dict) -> dict:
    """Every checker model against one reference label set."""
    labelled = [p for p in pairs if p["id"] in reference]
    out = {}
    for model in MODELS:

        def both(subset: list[dict], model: str = model) -> list[tuple[str, str]]:
            return [(reference[p["id"]], verdicts[(p["id"], model)]["label"]) for p in subset]

        out[model] = {
            "all": measure(both(labelled)),
            "real_pairs": measure(both([p for p in labelled if p["origin"] == "natural"])),
            "built_pairs": measure(both([p for p in labelled if p["origin"] != "natural"])),
            "disagreements": [
                {
                    "id": p["id"],
                    "origin": p["origin"],
                    "reference": reference[p["id"]],
                    "checker": verdicts[(p["id"], model)]["label"],
                    "checker_reason": verdicts[(p["id"], model)]["reason"],
                    "claim": p["claim"],
                    "quote": p["quote"],
                }
                for p in labelled
                if reference[p["id"]] != verdicts[(p["id"], model)]["label"]
            ],
        }
    return out


def error_detection(pairs: list[dict], verdicts: dict) -> dict:
    """Of the pairs that were broken on purpose, how many did each checker refuse to pass?

    No labels are needed: how a pair was built is a fact. "Flagged" means the checker said
    anything other than supported.
    """
    out = {}
    for model in MODELS:
        out[model] = {}
        for kind in [*BUILT_KINDS, "all_built"]:
            mine = [
                p
                for p in pairs
                if p["origin"] == kind or (kind == "all_built" and p["origin"] != "natural")
            ]
            flagged = [float(verdicts[(p["id"], model)]["label"] != "supported") for p in mine]
            out[model][kind] = {"n": len(mine), "flagged": int(sum(flagged))} | {
                "flagged_share": with_interval(mean, flagged)
            }
    return out


async def run() -> None:
    pairs = read_jsonl(PAIRS)
    if not pairs:
        print("agreement: no pairs yet. Run `uv run python -m evals pairs` first.")
        return
    async with eval_deps("eval.agreement") as deps:
        verdicts = await collect(deps, pairs)
        spent = deps.ledger.spent
    references = {}
    for name, info in REFERENCES.items():
        labels = {row["id"]: row["label"] for row in read_jsonl(info["path"])}
        if labels:
            references[name] = {
                "labeller": info["labeller"],
                "caveat": info["caveat"],
                "pairs_labelled": len(labels),
                "models": compare(pairs, labels, verdicts),
            }
    path = write_result(
        "checker_agreement",
        {
            "what": "Three checker models label 150 claim-and-quote pairs. A third of the pairs "
            "were broken on purpose when built.",
            "pairs_total": len(pairs),
            "product_checker": MODELS[0],
            "interval": "95% bootstrap over pairs, 2000 resamples",
            "human_labels": "present"
            if "person" in references
            else "NOT DONE. No person has "
            "labelled these pairs, so there is no agreement-with-a-human figure.",
            "error_detection_on_built_pairs": error_detection(pairs, verdicts),
            "references": references,
            "cost_usd": round(spent, 4),
        },
    )
    print(f"agreement: wrote {path}; references: {list(references) or 'none'} (cost ${spent:.2f})")
