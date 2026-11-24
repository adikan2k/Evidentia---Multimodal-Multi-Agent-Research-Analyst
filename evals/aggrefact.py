"""LLM-AggreFact: the auditor's two judges against human labels (D-037 part B, D-038).

    uv run python -m evals aggrefact --sample dev550 --dry                      # free
    uv run python -m evals aggrefact --sample dev550 --quote haiku --page haiku  # paid; ask first

Each judge runs on its own and is saved on its own, one line per row:
- the quote judge: find, quote check by code, check on the quotes (as in the product);
- the page judge: the claim and the page, supported or not (as in the product).
Code then combines them with the product's own table (`evidentia.audit.schemas.combine`). So a
new page judge, or the quote judge with context, reuses whatever was already run.

On the benchmark, supported counts as 1. Partial, contradicted and not-on-the-page count as 0.
"Needs a human" and "could not check" get no verdict.

The first run (D-037: "auditor" against "direct") was made by this file as of commit 882b385.
Its result files are kept as they are.

The dataset is gated and licensed CC BY-ND 4.0 for evaluation only. It is downloaded to a
git-ignored cache. Nothing written by this module contains a document, a claim or a quote: only
row numbers, labels, verdicts and quote offsets.
"""

import argparse
import asyncio
import json
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from evals.common import ROOT, RUNS_DIR, read_jsonl, write_result
from evals.stats import RESAMPLES, SEED
from evidentia.audit.graph import AuditDeps, AuditNodes
from evidentia.audit.schemas import FLAGS, combine, page_call
from evidentia.config import Settings, load_settings
from evidentia.cost import BudgetExceeded, Charge, Ledger
from evidentia.embed import Embedder
from evidentia.fetch import clean_text
from evidentia.llm import LLM
from evidentia.openai_llm import OpenAILLM, is_openai_model, make_client
from evidentia.schemas import Source
from evidentia.tracing import LangfuseTracer, Tracer

REPO = "lytang/LLM-AggreFact"
CACHE = ROOT / "cache" / "aggrefact"
SAMPLE_SEED = 20261124
FRESH_SEED = 20261125  # D-038's confirming run: new rows, none from the "test" sample
# name -> (split, rows per sub-dataset, seed, sample whose rows are left out)
SAMPLES: dict[str, tuple[str, int, int, str | None]] = {
    "dev55": ("dev", 5, SAMPLE_SEED, None),
    "dev550": ("dev", 50, SAMPLE_SEED, None),
    "test": ("test", 50, SAMPLE_SEED, None),
    "test2": ("test", 50, FRESH_SEED, "test"),
}
QUOTE_MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}
# "luna-p" is gpt-6-luna scored by its token probability, with reasoning off (D-039).
PAGE_MODELS = QUOTE_MODELS | {"luna": "gpt-6-luna", "luna-p": "gpt-6-luna"}
GRID = [round(i * 0.05, 2) for i in range(21)]  # thresholds tried on the practice rows
DEFAULT_CAP = 1.50
CONCURRENT_ROWS = 6

# D-038's finish line, fixed before the confirming run.
FINISH_LINE = {"flag_precision": 0.80, "supported_precision": 0.93, "coverage": 0.70}

ACCESS_HELP = (
    "LLM-AggreFact is gated. Accept its terms at "
    "https://huggingface.co/datasets/lytang/LLM-AggreFact with your Hugging Face account, "
    "then set a read token in the HF_TOKEN environment variable."
)


class HfAccess(BaseSettings):
    """HF_TOKEN from the environment only (rule 6)."""

    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)
    hf_token: SecretStr | None = None


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

    token = HfAccess().hf_token
    try:
        path = hf_hub_download(
            repo_id=REPO,
            repo_type="dataset",
            filename=f"data/{split}-00000-of-00001.parquet",
            cache_dir=CACHE,
            token=token.get_secret_value() if token else None,
        )
    except GatedRepoError:
        raise SystemExit(ACCESS_HELP) from None
    return Path(path)


def load_rows(split: str) -> list[Row]:
    import pyarrow.parquet as pq

    table = pq.read_table(download(split), columns=["dataset", "doc", "claim", "label"])
    return [Row(split=split, row=i, **r) for i, r in enumerate(table.to_pylist())]


def draw_sample(
    rows: Sequence[Row],
    per_dataset: int,
    seed: int = SAMPLE_SEED,
    leave_out: set[int] = frozenset(),
) -> list[Row]:
    """`per_dataset` rows from each sub-dataset, chosen at random; the label mix stays as it is."""
    groups: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        if row.row not in leave_out:
            groups[row.dataset].append(row)
    rng = random.Random(seed)
    chosen = []
    for name in sorted(groups):
        group = sorted(groups[name], key=lambda r: r.row)
        chosen += rng.sample(group, min(per_dataset, len(group)))
    return sorted(chosen, key=lambda r: (r.dataset, r.row))


def sample(name: str, rows: Sequence[Row] | None = None) -> list[Row]:
    split, per_dataset, seed, leave_out_of = SAMPLES[name]
    rows = rows if rows is not None else load_rows(split)
    leave_out = {r.row for r in sample(leave_out_of, rows)} if leave_out_of else set()
    return draw_sample(rows, per_dataset, seed, leave_out)


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


async def run_quote(row: Row, deps: AuditDeps, config: dict) -> dict[str, Any]:
    result = await AuditNodes(deps).assess(
        row.claim, as_source(row), f"aggrefact-{row.row}", config
    )
    return {
        "quote_label": result.quote_label,
        "stance": result.stance,
        "verdict": result.verdict,
        "quotes_offered": len(result.offered),
        "quote_offsets": [[q.start, q.end] for q in result.quotes],
    }


async def run_page(row: Row, deps: AuditDeps, config: dict) -> dict[str, Any]:
    nodes = AuditNodes(deps)
    verdict = await nodes.page_verdict(row.claim, as_source(row), f"aggrefact-{row.row}", config)
    return {"page_judged": verdict["page_judged"], "page_score": verdict["page_score"]}


RUNNERS: dict[str, Callable] = {"quote": run_quote, "page": run_page}


def row_deps(
    settings: Settings, shared: Ledger, tracer: Tracer, voyage: Any, openai: Any = None
) -> AuditDeps:
    ledger = RowLedger(shared)
    return AuditDeps(
        settings=settings,
        ledger=ledger,
        tracer=tracer,
        llm=LLM(settings, ledger),
        fetcher=None,  # type: ignore[arg-type]  # the benchmark supplies the document
        embedder=Embedder(settings, ledger, tracer, client=voyage),
        openai=OpenAILLM(settings, ledger, client=openai) if openai is not None else None,
    )


async def evaluate(
    rows: Sequence[Row],
    judge: str,
    make_deps: Callable[[], AuditDeps],
    out: Path,
    config: dict | None = None,
) -> list[dict[str, Any]]:
    """Run `judge` on every row not already saved in `out`, appending as each finishes."""
    done = {r["row"]: r for r in read_jsonl(out)}
    todo = [r for r in rows if r.row not in done]
    gate = asyncio.Semaphore(CONCURRENT_ROWS)
    out.parent.mkdir(parents=True, exist_ok=True)

    async def one(row: Row) -> None:
        async with gate:
            deps = make_deps()
            try:
                found = await RUNNERS[judge](row, deps, config or {})
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


def mean_bacc(groups: dict[str, list[tuple[int, int]]]) -> float:
    return sum(balanced_accuracy(g) for g in groups.values()) / len(groups) if groups else 0.0


def by_dataset(lines: Sequence[dict[str, Any]], key: str) -> dict[str, list[tuple[int, int]]]:
    """(label, prediction) per sub-dataset, leaving out rows with no prediction."""
    groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for line in sorted(lines, key=lambda x: x["row"]):
        if line[key] is not None:
            groups[line["dataset"]].append((line["label"], line[key]))
    return dict(sorted(groups.items()))


def stratified_resamples(
    sizes: dict[str, int], resamples: int = RESAMPLES, seed: int = SEED
) -> list[dict[str, list[int]]]:
    """Index draws within each sub-dataset, shared by every measure so differences are paired."""
    rng = random.Random(seed)
    return [
        {d: [rng.randrange(n) for _ in range(n)] for d, n in sizes.items()}
        for _ in range(resamples)
    ]


def interval(values: list[float]) -> tuple[float, float]:
    values = sorted(values)
    return values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]


def with_interval(
    stat: Callable[[list[dict]], float | None],
    lines_by_dataset: dict[str, list[dict]],
    draws: list[dict[str, list[int]]],
) -> dict[str, float | None]:
    """A statistic over rows, with a 95% stratified bootstrap interval."""
    every = [x for g in lines_by_dataset.values() for x in g]
    value = stat(every)
    boot = []
    for draw in draws:
        drawn = [lines_by_dataset[d][i] for d, idx in draw.items() for i in idx]
        got = stat(drawn)
        if got is not None:
            boot.append(got)
    low, high = interval(boot) if boot else (None, None)
    rnd = lambda v: None if v is None else round(v, 4)  # noqa: E731
    return {"value": rnd(value), "ci_low": rnd(low), "ci_high": rnd(high)}


def share(hits: int, total: int) -> float | None:
    return hits / total if total else None


def flag_precision(lines: list[dict], key: str) -> float | None:
    flagged = [x for x in lines if x[key] == 0]
    return share(sum(x["label"] == 0 for x in flagged), len(flagged))


def supported_precision(lines: list[dict], key: str) -> float | None:
    said = [x for x in lines if x[key] == 1]
    return share(sum(x["label"] == 1 for x in said), len(said))


def coverage(lines: list[dict], key: str) -> float | None:
    return share(sum(x[key] is not None for x in lines), len(lines))


def bacc_of(lines: list[dict], key: str) -> float:
    return mean_bacc(by_dataset(lines, key))


# The product's labels, turned into benchmark predictions.


def quote_pred(line: dict) -> int:
    return int(line["quote_label"] == "supported")


def score_of(line: dict) -> float | None:
    """The page judge's score. Runs from before D-039 saved only the verdict."""
    if "page_score" in line:
        return line["page_score"]
    return {"supported": 1.0, "not_supported": 0.0}.get(line["page_judged"])


def page_pred(line: dict) -> int:
    score = score_of(line)
    return int(score is not None and score >= 0.5)


def merge_votes(vote_runs: list[list[dict]]) -> list[dict]:
    """One page line per row from several single-vote runs: the score is the share of the
    answered votes that say supported. Only rows every run finished are kept."""
    by_run = [{x["row"]: x for x in run} for run in vote_runs]
    merged = []
    for row in sorted(set.intersection(*(set(r) for r in by_run))):
        lines = [r[row] for r in by_run]
        scores = [score_of(x) for x in lines if score_of(x) is not None]
        score = sum(scores) / len(scores) if scores else None
        merged.append(
            lines[0]
            | {
                "page_score": score,
                "page_judged": page_call(score, 0.5, 0.5),
                "usd": sum(x["usd"] for x in lines),
            }
        )
    return merged


def two_judge_pred(label: str) -> int | None:
    if label == "supported":
        return 1
    return 0 if label in FLAGS else None  # needs a human, or could not check


def join(
    quote_lines: list[dict],
    page_lines: list[dict],
    t_supported: float = 0.5,
    t_flag: float = 0.5,
) -> list[dict]:
    """One line per row both judges finished, with every system's prediction."""
    pages = {x["row"]: x for x in page_lines}
    joined = []
    for q in sorted(quote_lines, key=lambda x: x["row"]):
        p = pages.get(q["row"])
        if p is None:
            continue
        label = combine(q["quote_label"], page_call(score_of(p), t_supported, t_flag))
        pred = two_judge_pred(label)
        joined.append(
            {
                "row": q["row"],
                "dataset": q["dataset"],
                "label": q["label"],
                "quote": quote_pred(q),
                "page": page_pred(p),
                "two": pred,
                "two_or_wrong": pred if pred is not None else 1 - q["label"],
                "two_label": label,
                "quote_label": q["quote_label"],
                "has_quote": bool(q["quote_offsets"]),
                "usd_quote": q["usd"],
                "usd_page": p["usd"],
            }
        )
    return joined


def point(joined: list[dict]) -> dict[str, float | None]:
    """The three D-038 measures, with partial both as a flag and as its own verdict."""
    own = [x for x in joined if x["two_label"] != "partial"]
    decided = sum(x["two_label"] in FLAGS | {"supported"} for x in joined)
    rnd = lambda v: None if v is None else round(v, 4)  # noqa: E731
    return {
        "coverage": rnd(share(decided, len(joined))),
        "supported_precision": rnd(supported_precision(joined, "two")),
        "flag_precision": rnd(flag_precision(joined, "two")),
        "flag_precision_partial_own_verdict": rnd(flag_precision(own, "two")),
    }


def meets(pt: dict, flag_key: str) -> bool:
    values = {
        "coverage": pt["coverage"],
        "supported_precision": pt["supported_precision"],
        "flag_precision": pt[flag_key],
    }
    return all(values[k] is not None and values[k] >= v for k, v in FINISH_LINE.items())


def sweep(quote_lines: list[dict], page_lines: list[dict]) -> dict[str, Any]:
    """Every threshold pair on the grid, and the pair with the most coverage that meets
    D-038's bars, for each way of counting partial. Chosen on these rows, so it is fixed
    before the confirming run, never chosen on it."""
    points = []
    for t_s in GRID:
        for t_f in GRID:
            if t_f <= t_s:
                pt = point(join(quote_lines, page_lines, t_s, t_f))
                points.append({"t_supported": t_s, "t_flag": t_f} | pt)

    def best(flag_key: str) -> dict | None:
        ok = [pt for pt in points if meets(pt, flag_key)]
        return max(ok, key=lambda pt: (pt["coverage"], pt[flag_key])) if ok else None

    return {
        "points": points,
        "best_partial_as_flag": best("flag_precision"),
        "best_partial_own_verdict": best("flag_precision_partial_own_verdict"),
    }


def summarise(
    quote_lines: list[dict],
    page_lines: list[dict],
    sample_name: str,
    judges: dict[str, str],
    thresholds: tuple[float, float] = (0.5, 0.5),
) -> dict[str, Any]:
    """Every number in the result file comes from here."""
    joined = join(quote_lines, page_lines, *thresholds)
    groups: dict[str, list[dict]] = defaultdict(list)
    for x in joined:
        groups[x["dataset"]].append(x)
    groups = dict(sorted(groups.items()))
    draws = stratified_resamples({d: len(g) for d, g in groups.items()})

    def measures(key: str) -> dict[str, Any]:
        return {
            "balanced_accuracy": with_interval(lambda ls: bacc_of(ls, key), groups, draws),
            "flag_precision": with_interval(lambda ls: flag_precision(ls, key), groups, draws),
            "supported_precision": with_interval(
                lambda ls: supported_precision(ls, key), groups, draws
            ),
            "per_dataset": {d: round(bacc_of(g, key), 4) for d, g in groups.items()},
        }

    two = measures("two") | {
        "coverage": with_interval(lambda ls: coverage(ls, "two"), groups, draws),
        "balanced_accuracy_abstain_counted_wrong": with_interval(
            lambda ls: bacc_of(ls, "two_or_wrong"), groups, draws
        ),
        "coverage_per_dataset": {d: round(coverage(g, "two"), 4) for d, g in groups.items()},
        "labels": dict(Counter(x["two_label"] for x in joined).most_common()),
    }
    finish = {
        "flag_precision": two["flag_precision"]["value"],
        "supported_precision": two["supported_precision"]["value"],
        "coverage": two["coverage"]["value"],
    }
    # D-038's proposed change: "partial" as its own verdict, not a flag.
    partial = [x for x in joined if x["two_label"] == "partial"]
    separate = {
        "flag_precision": with_interval(
            lambda ls: flag_precision([x for x in ls if x["two_label"] != "partial"], "two"),
            groups,
            draws,
        ),
        "supported_precision": two["supported_precision"],
        "coverage": two["coverage"],  # partial is still a verdict, so coverage is unchanged
        "partial_share": round(len(partial) / len(joined), 4) if joined else None,
        "partial_people_label_supported": (
            round(sum(x["label"] for x in partial) / len(partial), 4) if partial else None
        ),
    }
    separate_finish = {k: separate[k]["value"] for k in FINISH_LINE}
    two["partial_as_its_own_verdict"] = separate | {
        "finish_line_passed": all(
            separate_finish[k] is not None and separate_finish[k] >= v
            for k, v in FINISH_LINE.items()
        )
    }
    n = len(joined)
    usd_quote = sum(x["usd_quote"] for x in joined)
    usd_page = sum(x["usd_page"] for x in joined)
    return {
        "sample": sample_name,
        "split": SAMPLES[sample_name][0],
        "sample_seed": SAMPLES[sample_name][2],
        "rows": n,
        "judges": judges,
        "thresholds": {"t_supported": thresholds[0], "t_flag": thresholds[1]},
        "metric": "balanced accuracy per sub-dataset, then their plain mean (95% bootstrap)",
        "two_judges": two,
        "quote_judge_alone": measures("quote")
        | {
            "labels": dict(Counter(x["quote_label"] for x in joined).most_common()),
            "rows_with_an_exact_quote": sum(x["has_quote"] for x in joined),
        },
        "page_judge_alone": measures("page"),
        "finish_line": {
            "thresholds": FINISH_LINE,
            "measured": finish,
            "passed": all(finish[k] is not None and finish[k] >= v for k, v in FINISH_LINE.items()),
        },
        "threshold_sweep": sweep(quote_lines, page_lines),
        "usd": {
            "quote_judge": round(usd_quote, 4),
            "page_judge": round(usd_page, 4),
            "per_claim_both": round((usd_quote + usd_page) / n, 6) if n else None,
        },
    }


# Command.


def run_path(sample_name: str, judge: str, model: str, context: bool = False) -> Path:
    suffix = "_ctx" if context else ""
    return RUNS_DIR / f"aggrefact_{sample_name}_{judge}_{model}{suffix}.jsonl"


def vote_name(page: str, vote: int) -> str:
    """Each vote is its own run, so a fifth vote reuses the first four."""
    return page if vote == 1 else f"{page}_v{vote}"


def result_name(args: argparse.Namespace) -> str:
    name = f"aggrefact_{args.sample}_q-{args.quote}{'-ctx' if args.context else ''}_p-{args.page}"
    if args.votes > 1:
        name += f"-votes{args.votes}"
    if (args.t_supported, args.t_flag) != (0.5, 0.5):
        name += f"_t{args.t_supported}-{args.t_flag}"
    return name


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m evals aggrefact")
    parser.add_argument("--sample", choices=list(SAMPLES), default="dev550")
    parser.add_argument("--quote", choices=list(QUOTE_MODELS), default="haiku")
    parser.add_argument("--page", choices=list(PAGE_MODELS), default="haiku")
    parser.add_argument("--context", action="store_true", help="show the checker each paragraph")
    parser.add_argument("--votes", type=int, default=1, help="page judge answers per claim")
    parser.add_argument("--t-supported", type=float, default=0.5, dest="t_supported")
    parser.add_argument("--t-flag", type=float, default=0.5, dest="t_flag")
    parser.add_argument("--cap", type=float, default=DEFAULT_CAP, help="US dollars, whole command")
    parser.add_argument("--dry", action="store_true", help="download and describe the sample only")
    return parser.parse_args(argv)


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
    rows = sample(args.sample)
    describe(rows)
    if args.dry:
        return
    quote, page = QUOTE_MODELS[args.quote], PAGE_MODELS[args.page]
    settings = load_settings(
        cost_cap_usd=args.cap,
        finder_model=quote,
        audit_checker_model=quote,
        page_judge_model=page,
        page_judge_probability=args.page == "luna-p",
        audit_quote_context=args.context,
        audit_prompt_cache=False,  # no two rows share a document, so caching would only cost
    )
    print(
        f"  quote judge {quote}{' with context' if args.context else ''}, page judge {page}, "
        f"cap ${args.cap:.2f}"
    )
    asyncio.run(run_all(rows, args, settings))


async def run_all(rows: list[Row], args: argparse.Namespace, settings: Settings) -> None:
    tracer = LangfuseTracer(settings)
    shared = Ledger(settings.cost_cap_usd)
    voyage = Embedder(settings, shared, tracer).client
    openai = make_client(settings) if is_openai_model(settings.page_judge_model) else None
    config = {"callbacks": tracer.callbacks(), "run_name": "evidentia-aggrefact"}
    outs = {"quote": run_path(args.sample, "quote", args.quote, args.context)}
    for vote in range(1, args.votes + 1):
        outs[f"page vote {vote}"] = run_path(args.sample, "page", vote_name(args.page, vote))
    found = {}
    try:
        with tracer.span(f"aggrefact.{args.sample}", "span", {"rows": len(rows)}):
            for judge, out in outs.items():
                print(f"== {judge} judge")
                found[judge] = await evaluate(
                    rows,
                    judge.split()[0],
                    lambda: row_deps(settings, shared, tracer, voyage, openai),
                    out,
                    config,
                )
    finally:
        tracer.flush()
    print(f"  spent ${shared.spent:.4f} this command")
    votes = [found[k] for k in found if k.startswith("page")]
    if found["quote"] and all(votes):
        judges = {"quote": settings.audit_checker_model, "page": settings.page_judge_model}
        judges |= {"quote_context": str(args.context), "page_votes": str(args.votes)}
        judges["page_score"] = "token probability" if args.page == "luna-p" else "vote share"
        thresholds = (args.t_supported, args.t_flag)
        body = summarise(found["quote"], merge_votes(votes), args.sample, judges, thresholds)
        path = write_result(result_name(args), body)
        print(f"  wrote {path.name}")
