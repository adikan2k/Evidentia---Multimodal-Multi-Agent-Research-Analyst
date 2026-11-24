"""LLM-AggreFact: the auditor's evidence steps against human labels (D-037, part B).

    uv run python -m evals aggrefact --split dev --model haiku --dry   # free: sample sizes only
    uv run python -m evals aggrefact --split test --model haiku        # paid; ask first

Two systems run on the same rows. "auditor" is the audit's find, quote check and check, with
the benchmark document as the page. "direct" is the same model shown the whole document and
asked only "supported or not". Supported counts as 1, everything else as 0 (decided before the
run); the result also reports partial counted as 1.

The dataset is gated and licensed CC BY-ND 4.0 for evaluation only. It is downloaded to a
git-ignored cache. Nothing written by this module contains a document, a claim or a quote: only
row numbers, labels, predictions and quote offsets.
"""

import argparse
import asyncio
import json
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evals.common import RESULTS_DIR, ROOT, RUNS_DIR, read_jsonl, write_result
from evals.stats import RESAMPLES, SEED
from evidentia.audit.graph import AuditDeps, AuditNodes
from evidentia.config import Settings, load_settings
from evidentia.cost import BudgetExceeded, Charge, Ledger
from evidentia.embed import Embedder
from evidentia.fetch import clean_text
from evidentia.llm import DATA_RULE, LLM, ModelStopped, new_tag
from evidentia.schemas import Source
from evidentia.tracing import LangfuseTracer, Tracer

REPO = "lytang/LLM-AggreFact"
CACHE = ROOT / "cache" / "aggrefact"
SAMPLE_SEED = 20261124
PER_DATASET = {"dev": 5, "test": 50}
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
DEFAULT_CAP = {"haiku": 1.50, "sonnet": 8.00}
SYSTEMS = ("auditor", "direct")
CONCURRENT_ROWS = 6

ACCESS_HELP = (
    "LLM-AggreFact is gated. Accept its terms at "
    "https://huggingface.co/datasets/lytang/LLM-AggreFact with your Hugging Face account, "
    "then set a read token in the HF_TOKEN environment variable."
)

DIRECT_SYSTEM = f"""You decide whether a document supports a claim. The document is inside \
<{{tag}}> ... </{{tag}}> tags.

{DATA_RULE}

supported is true only if the document states everything the claim says, including every \
number, date, name and qualifier. Otherwise it is false. Judge only from the document."""


class DirectJudgement(BaseModel):
    supported: bool = Field(
        description="True only if the document supports every part of the claim."
    )


class Row(BaseModel):
    split: str
    row: int  # position in the split's parquet file
    dataset: str
    doc: str
    claim: str
    label: int  # 1 = supported, 0 = not


# Data.


def download(split: str) -> Path:
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import GatedRepoError

    try:
        path = hf_hub_download(
            repo_id=REPO,
            repo_type="dataset",
            filename=f"data/{split}-00000-of-00001.parquet",
            cache_dir=CACHE,
        )
    except GatedRepoError:
        raise SystemExit(ACCESS_HELP) from None
    return Path(path)


def load_rows(split: str) -> list[Row]:
    import pyarrow.parquet as pq

    table = pq.read_table(download(split), columns=["dataset", "doc", "claim", "label"])
    return [Row(split=split, row=i, **r) for i, r in enumerate(table.to_pylist())]


def draw_sample(rows: Sequence[Row], per_dataset: int, seed: int = SAMPLE_SEED) -> list[Row]:
    """`per_dataset` rows from each sub-dataset, chosen at random; the label mix stays as it is."""
    groups: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        groups[row.dataset].append(row)
    rng = random.Random(seed)
    chosen = []
    for name in sorted(groups):
        group = sorted(groups[name], key=lambda r: r.row)
        chosen += rng.sample(group, min(per_dataset, len(group)))
    return sorted(chosen, key=lambda r: (r.dataset, r.row))


# Running one row.


class RowLedger(Ledger):
    """Counts one row's charges while the shared ledger keeps the cap for the whole run."""

    def __init__(self, shared: Ledger) -> None:
        super().__init__(shared.cap_usd)
        self.shared = shared

    def reserve(self, node: str, worst_case_usd: float):
        return self.shared.reserve(node, worst_case_usd)

    def add(self, charge: Charge) -> None:
        self.shared.add(charge)
        self.charges.append(charge)


def as_source(row: Row) -> Source:
    return Source(id="D1", url=f"aggrefact:{row.split}:{row.row}", text=clean_text(row.doc))


async def run_auditor(row: Row, deps: AuditDeps, config: dict) -> dict[str, Any]:
    result = await AuditNodes(deps).assess(
        row.claim, as_source(row), f"aggrefact-{row.row}", config
    )
    label = result.label
    return {
        "audit_label": label,
        "stance": result.stance,
        "verdict": result.verdict,
        "quotes_offered": len(result.offered),
        "quote_offsets": [[q.start, q.end] for q in result.quotes],
        "pred": int(label == "supported"),
        "pred_partial_ok": int(label in ("supported", "partial")),
    }


async def run_direct(row: Row, deps: AuditDeps, config: dict) -> dict[str, Any]:
    tag = new_tag("document")
    user = f"Claim: {row.claim}\n\nDocument:\n<{tag}>\n{clean_text(row.doc)}\n</{tag}>"
    try:
        judgement = await deps.llm.structured(
            node="direct",
            model=deps.settings.checker_model,
            effort=deps.settings.checker_effort,
            max_tokens=deps.settings.checker_max_tokens,
            system=DIRECT_SYSTEM.format(tag=tag),
            user=user,
            schema=DirectJudgement,
            config=config,
        )
    except ModelStopped:
        return {"answered": False, "pred": 0}
    return {"answered": True, "pred": int(judgement.supported)}


RUNNERS: dict[str, Callable] = {"auditor": run_auditor, "direct": run_direct}


def row_deps(settings: Settings, shared: Ledger, tracer: Tracer, voyage: Any) -> AuditDeps:
    ledger = RowLedger(shared)
    return AuditDeps(
        settings=settings,
        ledger=ledger,
        tracer=tracer,
        llm=LLM(settings, ledger),
        fetcher=None,  # type: ignore[arg-type]  # the benchmark supplies the document
        embedder=Embedder(settings, ledger, tracer, client=voyage),
    )


async def evaluate(
    rows: Sequence[Row],
    system: str,
    make_deps: Callable[[], AuditDeps],
    out: Path,
    config: dict | None = None,
) -> list[dict[str, Any]]:
    """Run `system` on every row not already saved in `out`, appending as each finishes."""
    done = {r["row"]: r for r in read_jsonl(out)}
    todo = [r for r in rows if r.row not in done]
    gate = asyncio.Semaphore(CONCURRENT_ROWS)
    out.parent.mkdir(parents=True, exist_ok=True)

    async def one(row: Row) -> None:
        async with gate:
            deps = make_deps()
            try:
                found = await RUNNERS[system](row, deps, config or {})
            except BudgetExceeded:
                raise
            except Exception as err:  # a network failure: not saved, so a rerun tries again
                print(f"  row {row.row}: {type(err).__name__}")
                return
            line = {"row": row.row, "dataset": row.dataset, "label": row.label} | found
            line["usd"] = round(deps.ledger.spent, 6)
            done[row.row] = line
            with out.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(line) + "\n")

    try:
        async with asyncio.TaskGroup() as group:  # the first error cancels the other rows
            for row in todo:
                group.create_task(one(row))
    except* BudgetExceeded as errors:
        print(f"  stopped at the cap: {errors.exceptions[0]}")
    wanted = {r.row for r in rows}
    return [done[n] for n in sorted(done) if n in wanted]


# Scoring.


def balanced_accuracy(pairs: Sequence[tuple[int, int]]) -> float:
    """Mean of the hit rate on supported rows and on unsupported rows (one if only one exists)."""
    rates = []
    for cls in (1, 0):
        preds = [p for label, p in pairs if label == cls]
        if preds:
            rates.append(sum(p == cls for p in preds) / len(preds))
    return sum(rates) / len(rates) if rates else 0.0


def by_dataset(lines: Sequence[dict[str, Any]], key: str) -> dict[str, list[tuple[int, int]]]:
    groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for line in sorted(lines, key=lambda x: x["row"]):
        groups[line["dataset"]].append((line["label"], line[key]))
    return dict(sorted(groups.items()))


def rates(pairs: Sequence[tuple[int, int]]) -> dict[str, float | int | None]:
    """Over all rows: how often "supported" is right, and the hit rate on each class."""

    def share(hits: int, total: int) -> float | None:
        return round(hits / total, 4) if total else None

    said_yes = [label for label, pred in pairs if pred == 1]
    return {
        "said_supported": len(said_yes),
        "supported_and_right": share(sum(said_yes), len(said_yes)),
        "caught_supported": share(
            sum(p for label, p in pairs if label == 1), sum(label for label, _ in pairs)
        ),
        "caught_unsupported": share(
            sum(1 - p for label, p in pairs if label == 0), sum(1 - label for label, _ in pairs)
        ),
    }


def mean_bacc(groups: dict[str, list[tuple[int, int]]]) -> float:
    return sum(balanced_accuracy(g) for g in groups.values()) / len(groups) if groups else 0.0


def stratified_resamples(
    sizes: dict[str, int], resamples: int = RESAMPLES, seed: int = SEED
) -> list[dict[str, list[int]]]:
    """Index draws within each sub-dataset, shared by every system so differences are paired."""
    rng = random.Random(seed)
    return [
        {d: [rng.randrange(n) for _ in range(n)] for d, n in sizes.items()}
        for _ in range(resamples)
    ]


def interval(values: list[float]) -> tuple[float, float]:
    values = sorted(values)
    return values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]


def score(groups: dict[str, list[tuple[int, int]]], draws: list[dict[str, list[int]]]) -> dict:
    boot = [mean_bacc({d: [g[i] for i in draw[d]] for d, g in groups.items()}) for draw in draws]
    low, high = interval(boot)
    return {
        "mean_bacc": round(mean_bacc(groups), 4),
        "ci_low": round(low, 4),
        "ci_high": round(high, 4),
        "per_dataset": {
            d: {
                "n": len(g),
                "supported": sum(label for label, _ in g),
                "bacc": round(balanced_accuracy(g), 4),
            }
            for d, g in groups.items()
        },
    }


def paired_difference(a: dict, b: dict, draws: list[dict[str, list[int]]]) -> dict[str, float]:
    diffs = [
        mean_bacc({d: [g[i] for i in draw[d]] for d, g in a.items()})
        - mean_bacc({d: [g[i] for i in draw[d]] for d, g in b.items()})
        for draw in draws
    ]
    low, high = interval(diffs)
    return {
        "difference": round(mean_bacc(a) - mean_bacc(b), 4),
        "ci_low": round(low, 4),
        "ci_high": round(high, 4),
    }


def summarise(results: dict[str, list[dict[str, Any]]], split: str, model: str) -> dict[str, Any]:
    """Every number in the result file comes from here. Only rows both systems finished count."""
    shared = set.intersection(*({x["row"] for x in lines} for lines in results.values()))
    kept = {s: [x for x in lines if x["row"] in shared] for s, lines in results.items()}
    first = next(iter(kept.values()))
    sizes = {d: len(g) for d, g in by_dataset(first, "pred").items()}
    draws = stratified_resamples(sizes)
    body: dict[str, Any] = {
        "split": split,
        "model": model,
        "sample_seed": SAMPLE_SEED,
        "rows": len(shared),
        "metric": "balanced accuracy per sub-dataset, then their plain mean (95% bootstrap)",
        "systems": {},
    }
    for system, lines in kept.items():
        entry = {
            "score": score(by_dataset(lines, "pred"), draws),
            "usd": round(sum(x["usd"] for x in lines), 4),
            "usd_per_claim": round(sum(x["usd"] for x in lines) / len(lines), 6) if lines else None,
            "pooled": rates([(x["label"], x["pred"]) for x in lines]),
        }
        if system == "auditor":
            entry["score_partial_counted_supported"] = score(
                by_dataset(lines, "pred_partial_ok"), draws
            )
            entry["labels"] = dict(Counter(x["audit_label"] for x in lines).most_common())
            entry["rows_with_an_exact_quote"] = sum(bool(x["quote_offsets"]) for x in lines)
            entry["rows_quotes_offered_none_exact"] = sum(
                x["quotes_offered"] > 0 and not x["quote_offsets"] for x in lines
            )
        if system == "direct":
            entry["unanswered"] = sum(not x["answered"] for x in lines)
        body["systems"][system] = entry
    if {"auditor", "direct"} <= kept.keys():
        body["auditor_minus_direct"] = paired_difference(
            by_dataset(kept["auditor"], "pred"), by_dataset(kept["direct"], "pred"), draws
        )
    return body


# Command.


def run_path(split: str, model: str, system: str) -> Path:
    return RUNS_DIR / f"aggrefact_{split}_{model}_{system}.jsonl"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m evals aggrefact")
    parser.add_argument("--split", choices=list(PER_DATASET), default="dev")
    parser.add_argument("--model", choices=list(MODELS), default="haiku")
    parser.add_argument("--systems", default=",".join(SYSTEMS))
    parser.add_argument("--cap", type=float, help="cost cap for the whole command in US dollars")
    parser.add_argument("--dry", action="store_true", help="download and describe the sample only")
    args = parser.parse_args(argv)
    args.systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    if not set(args.systems) <= set(SYSTEMS):
        parser.error(f"--systems must come from {', '.join(SYSTEMS)}")
    return args


def describe(rows: Sequence[Row]) -> None:
    lengths = sorted(len(r.doc) for r in rows)
    limit = Settings.model_fields["audit_page_chars"].default
    long = sum(len(clean_text(r.doc)) > limit for r in rows)
    print(
        f"  {len(rows)} rows, {len({r.dataset for r in rows})} sub-datasets, "
        f"{sum(r.label for r in rows)} labelled supported"
    )
    print(
        f"  document characters: median {lengths[len(lengths) // 2]:,}, max {lengths[-1]:,}; "
        f"{long} long enough to be cut to passages"
    )


def main(argv: list[str]) -> None:
    args = parse_args(argv)
    rows = draw_sample(load_rows(args.split), PER_DATASET[args.split])
    describe(rows)
    if args.dry:
        return
    cap = args.cap if args.cap is not None else DEFAULT_CAP[args.model]
    model = MODELS[args.model]
    settings = load_settings(cost_cap_usd=cap, finder_model=model, checker_model=model)
    print(f"  model {model}, systems {', '.join(args.systems)}, cap ${cap:.2f}")
    asyncio.run(run_all(rows, args, settings))


async def run_all(rows: list[Row], args: argparse.Namespace, settings: Settings) -> None:
    tracer = LangfuseTracer(settings)
    shared = Ledger(settings.cost_cap_usd)
    voyage = Embedder(settings, shared, tracer).client
    config = {"callbacks": tracer.callbacks(), "run_name": "evidentia-aggrefact"}
    results = {}
    try:
        with tracer.span(f"aggrefact.{args.split}.{args.model}", "span", {"rows": len(rows)}):
            for system in args.systems:
                print(f"== {system}")
                out = run_path(args.split, args.model, system)
                results[system] = await evaluate(
                    rows, system, lambda: row_deps(settings, shared, tracer, voyage), out, config
                )
    finally:
        tracer.flush()
    print(f"  spent ${shared.spent:.4f} this command")
    if all(results.values()):
        body = summarise(results, args.split, args.model)
        path = write_result(f"aggrefact_{args.split}_{args.model}", body)
        print(f"  wrote {path.relative_to(RESULTS_DIR.parent.parent)}")
