"""Baseline against the full pipeline: is each claim backed by the evidence it points to? (D-019)

The judge is a different model from the pipeline's own checker, using the same rubric. Its
agreement with hand labels is measured separately in `agreement.py`.
"""

import asyncio

from deepeval.metrics import FaithfulnessMetric
from deepeval.models import AnthropicModel
from deepeval.test_case import LLMTestCase

from evals.agreement import verdict
from evals.common import RUNS_DIR, eval_deps, read_jsonl, write_jsonl, write_result
from evals.stats import bootstrap_ci, mean, paired_difference, summary
from evals.systems import BASELINE_RUNS, PIPELINE_RUNS
from evidentia.cost import CLAUDE_PRICES, Charge
from evidentia.graph import Deps

JUDGE_MODEL = "claude-opus-5-5"
VERDICTS = RUNS_DIR / "judge_verdicts.jsonl"
FAITHFULNESS = RUNS_DIR / "deepeval_faithfulness.jsonl"
# DeepEval makes several model calls per answer and reports the cost only afterwards.
DEEPEVAL_WORST_CASE_USD = 0.50


def claims_to_judge() -> list[dict]:
    """Every claim from both systems, with the evidence that system points to."""
    items = []
    for row in read_jsonl(BASELINE_RUNS):
        for n, claim in enumerate(row["claims"]):
            key = f"baseline:{row['id']}:{n}"
            items.append(
                {"key": key, "system": "baseline", "question_id": row["id"], "label": "presented"}
                | {"claim": claim["text"], "evidence": claim["evidence"]}
            )
    for row in read_jsonl(PIPELINE_RUNS):
        for n, claim in enumerate(row["claims"]):
            key = f"pipeline:{row['id']}:{n}"
            evidence = claim["quote"] if claim["quote_found"] else ""
            items.append(
                {"key": key, "system": "pipeline", "question_id": row["id"]}
                | {"label": claim["label"], "claim": claim["text"], "evidence": evidence}
            )
    return items


async def judge_all(deps: Deps, items: list[dict]) -> dict[str, dict]:
    saved = {row["key"]: row for row in read_jsonl(VERDICTS)}
    limit = asyncio.Semaphore(4)

    async def one(item: dict) -> None:
        if not item["evidence"]:
            answer = {"label": "unsupported", "reason": "no evidence was cited"}
        else:
            async with limit:
                answer = await verdict(deps, JUDGE_MODEL, item["claim"], item["evidence"], "judge")
        saved[item["key"]] = {"key": item["key"], "judge": answer["label"]} | {
            "judge_reason": answer["reason"]
        }
        # Save as we go: a long judging run that is interrupted keeps what it has.
        write_jsonl(VERDICTS, [saved[key] for key in sorted(saved)])

    await asyncio.gather(*(one(item) for item in items if item["key"] not in saved))
    write_jsonl(VERDICTS, [saved[key] for key in sorted(saved)])
    return saved


def ratio(rows: list[tuple[int, int]]) -> float:
    """Sum of the first numbers over the sum of the second, e.g. correct claims over claims."""
    total = sum(den for _, den in rows)
    return sum(num for num, _ in rows) / total if total else 0.0


def ratio_summary(rows: list[tuple[int, int]]) -> dict[str, float | int]:
    low, high = bootstrap_ci(rows, ratio)
    counts = {"correct": sum(n for n, _ in rows), "claims": sum(d for _, d in rows)}
    return {"value": round(ratio(rows), 4), "ci_low": round(low, 4), "ci_high": round(high, 4)} | (
        counts
    )


def per_question(items: list[dict], question_ids: list[str], accept: set[str]) -> dict[str, list]:
    """For each question: how many claims were presented and how many the judge accepted."""
    rows = []
    for qid in question_ids:
        mine = [i for i in items if i["question_id"] == qid]
        rows.append((sum(i["judge"] in accept for i in mine), len(mine)))
    return {"rows": rows, "accuracy": [n / d for n, d in rows if d]}


def score(items: list[dict], question_ids: list[str]) -> dict:
    strict = per_question(items, question_ids, {"supported"})
    lenient = per_question(items, question_ids, {"supported", "partial"})
    return {
        "citation_accuracy": ratio_summary(strict["rows"]),
        "main_point_backed": ratio_summary(lenient["rows"]),
        "claims_per_question": summary([d for _, d in strict["rows"]]),
        "questions_with_a_fully_backed_claim": summary([float(n > 0) for n, _ in strict["rows"]]),
        "judge_labels": {
            label: sum(i["judge"] == label for i in items)
            for label in ("supported", "partial", "unsupported", "none")
        },
    }


def paired(a: list[dict], b: list[dict], question_ids: list[str]) -> dict:
    """Per-question accuracy of `a` minus `b`, on questions where both presented a claim."""
    first, second = [], []
    for qid in question_ids:
        mine = [i for i in a if i["question_id"] == qid]
        theirs = [i for i in b if i["question_id"] == qid]
        if mine and theirs:
            first.append(mean([i["judge"] == "supported" for i in mine]))
            second.append(mean([i["judge"] == "supported" for i in theirs]))
    return paired_difference(first, second)


async def faithfulness(deps: Deps) -> dict:
    """DeepEval's stock faithfulness score for both systems: a second opinion we did not design."""
    saved = {(row["system"], row["id"]): row for row in read_jsonl(FAITHFULNESS)}
    price_in, price_out = CLAUDE_PRICES[JUDGE_MODEL]
    key = deps.settings.anthropic_api_key.get_secret_value()
    limit = asyncio.Semaphore(4)

    async def one(system: str, row: dict, evidence: list[str]) -> None:
        answer = " ".join(claim["text"] for claim in row["claims"])
        if not answer or not evidence:
            return
        model = AnthropicModel(
            model=JUDGE_MODEL,
            api_key=key,
            cost_per_input_token=price_in / 1e6,
            cost_per_output_token=price_out / 1e6,
        )
        metric = FaithfulnessMetric(model=model, include_reason=False)
        case = LLMTestCase(input=row["question"], actual_output=answer, retrieval_context=evidence)
        span_input = {"system": system, "question": row["id"]}
        async with limit:
            with (
                deps.ledger.reserve("deepeval", DEEPEVAL_WORST_CASE_USD),
                deps.tracer.span("deepeval.faithfulness", "evaluator", span_input) as span,
            ):
                value = await metric.a_measure(case, _show_indicator=False)
                usd = metric.evaluation_cost or 0.0
                deps.ledger.add(Charge(node="deepeval", item=JUDGE_MODEL, usd=usd))
                span.update(output={"score": value}, metadata={"usd": usd})
        saved[(system, row["id"])] = {"system": system, "id": row["id"], "score": value}

    jobs = []
    for row in read_jsonl(BASELINE_RUNS):
        evidence = [c["evidence"] for c in row["claims"] if c["evidence"]]
        jobs.append(("baseline", row, evidence))
    for row in read_jsonl(PIPELINE_RUNS):
        evidence = [c["quote"] for c in row["claims"] if c["quote_found"]]
        jobs.append(("pipeline", row, evidence))
    await asyncio.gather(*(one(*job) for job in jobs if (job[0], job[1]["id"]) not in saved))
    write_jsonl(FAITHFULNESS, [saved[k] for k in sorted(saved)])
    scores = {s: [r["score"] for (system, _), r in saved.items() if system == s] for s in SYSTEMS}
    return {system: summary(values) for system, values in scores.items()}


SYSTEMS = ("baseline", "pipeline")


async def run() -> None:
    items = claims_to_judge()
    if not items:
        print("judge: no saved answers yet. Run `uv run python -m evals systems` first.")
        return
    async with eval_deps("eval.judge") as deps:
        verdicts = await judge_all(deps, items)
        deepeval_scores = await faithfulness(deps)
        spent = deps.ledger.spent
    items = [item | verdicts[item["key"]] for item in items]
    question_ids = sorted({item["question_id"] for item in items})
    baseline = [i for i in items if i["system"] == "baseline"]
    pipeline = [i for i in items if i["system"] == "pipeline"]
    shown_as_supported = [i for i in pipeline if i["label"] == "supported"]
    failures = [
        {k: i[k] for k in ("key", "label", "judge", "judge_reason", "claim", "evidence")}
        for i in shown_as_supported
        if i["judge"] != "supported"
    ]
    path = write_result(
        "citation_accuracy",
        {
            "what": "For each claim, does the evidence the system points to back it? Baseline "
            "evidence is the cited passage; pipeline evidence is the quote.",
            "judge": f"{JUDGE_MODEL} with the checker's rubric. Its agreement with hand labels "
            "is in checker_agreement.json.",
            "citation_accuracy": "share of presented claims the judge finds fully supported",
            "main_point_backed": "share the judge finds supported or partial",
            "questions": len(question_ids),
            "interval": "95% bootstrap over questions, 2000 resamples",
            "baseline": score(baseline, question_ids),
            "pipeline_claims_labelled_supported": score(shown_as_supported, question_ids),
            "pipeline_all_claims": score(pipeline, question_ids),
            "pipeline_labels": {
                label: sum(i["label"] == label for i in pipeline)
                for label in ("supported", "partial", "unverified")
            },
            "accuracy_difference_supported_minus_baseline": paired(
                shown_as_supported, baseline, question_ids
            ),
            "accuracy_difference_all_pipeline_minus_baseline": paired(
                pipeline, baseline, question_ids
            ),
            "deepeval_faithfulness": deepeval_scores,
            "supported_claims_the_judge_rejected": failures,
            "baseline_claims_judged_unsupported": [
                {k: i[k] for k in ("key", "judge_reason", "claim")}
                for i in baseline
                if i["judge"] == "unsupported"
            ],
            "cost_usd": round(spent, 4),
        },
    )
    print(f"judge: wrote {path} (cost ${spent:.2f})")
