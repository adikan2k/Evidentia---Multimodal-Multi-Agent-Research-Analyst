"""Score every system's claims: is each one backed by the evidence it points to? (D-019, D-022)

The judge is a different model from the pipeline's own checker, using the same rubric. Evidence
is whatever the system points to: the cited passage for a baseline, the quote for a pipeline.
"Presented as backed" means every claim for a baseline, and claims labelled supported for a
pipeline.
"""

import asyncio
import json
import re
from statistics import median

from deepeval.metrics import FaithfulnessMetric
from deepeval.models import AnthropicModel
from deepeval.test_case import LLMTestCase

from evals.agreement import verdict
from evals.common import RUNS_DIR, eval_deps, load_questions, read_jsonl, write_jsonl, write_result
from evals.stats import bootstrap_ci, mean, paired_difference, summary
from evals.systems import BASELINE_RUNS, COSTS, PIPELINE_RUNS, SETS, VARIANTS, runs_path
from evidentia.cost import CLAUDE_PRICES, Charge
from evidentia.graph import Deps

JUDGE_MODEL = "claude-opus-5-5"
VERDICTS = RUNS_DIR / "judge_verdicts.jsonl"
FAITHFULNESS = RUNS_DIR / "deepeval_faithfulness.jsonl"
# DeepEval makes several model calls per answer and reports the cost only afterwards.
DEEPEVAL_WORST_CASE_USD = 0.50
JUDGE_LABELS = ("supported", "partial", "unsupported", "none")


def claims_of(set_name: str, variant: str) -> list[dict]:
    """Every claim one system made on one question set, with the evidence it points to."""
    kind = VARIANTS[variant][0]
    stem = runs_path(set_name, variant).stem
    items = []
    for row in read_jsonl(runs_path(set_name, variant)):
        for n, claim in enumerate(row["claims"]):
            if kind == "baseline":
                evidence, label = claim["evidence"], "presented"
            else:
                evidence = claim["quote"] if claim["quote_found"] else ""
                label = claim["label"]
            item = {"key": f"{stem}:{row['id']}:{n}", "system": stem, "question_id": row["id"]}
            items.append(item | {"label": label, "claim": claim["text"], "evidence": evidence})
    return items


def presented(items: list[dict]) -> list[dict]:
    """The claims a system shows the reader as backed."""
    return [i for i in items if i["label"] in ("presented", "supported")]


async def judge_all(deps: Deps, items: list[dict]) -> dict[str, dict]:
    saved = {row["key"]: row for row in read_jsonl(VERDICTS)}
    limit = asyncio.Semaphore(4)

    async def one(item: dict) -> None:
        if not item["evidence"]:
            answer = {"label": "unsupported", "reason": "no evidence was cited"}
        else:
            async with limit:
                answer = await verdict(deps, JUDGE_MODEL, item["claim"], item["evidence"], "judge")
        row = {"key": item["key"], "judge": answer["label"], "judge_reason": answer["reason"]}
        saved[item["key"]] = row
        # Save as we go: a long judging run that is interrupted keeps what it has.
        write_jsonl(VERDICTS, [saved[key] for key in sorted(saved)])

    await asyncio.gather(*(one(item) for item in items if item["key"] not in saved))
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
        "judge_labels": {label: sum(i["judge"] == label for i in items) for label in JUDGE_LABELS},
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


def describe_system(items: list[dict], question_ids: list[str], cost: float | None) -> dict:
    shown = presented(items)
    sizes = [len(i["evidence"]) for i in shown if i["evidence"]]
    out = {
        "presented_as_backed": score(shown, question_ids),
        "all_claims": score(items, question_ids),
        "labels": {
            label: sum(i["label"] == label for i in items)
            for label in ("presented", "supported", "partial", "unverified")
            if any(i["label"] == label for i in items)
        },
        # How much text a reader must read to check one claim.
        "evidence_chars_median": int(median(sizes)) if sizes else 0,
    }
    if cost is not None:
        out["cost_per_question_usd"] = round(cost / len(question_ids), 4)
    return out


def unanswerable_summary(items: list[dict], questions: list) -> dict:
    """On questions the corpus cannot answer: did the system stay quiet, or answer anyway?"""
    shown = presented(items)
    quiet, leaked, examples = 0, 0, []
    for q in questions:
        mine = [i for i in shown if i["question_id"] == q.id]
        quiet += not mine
        hits = [i for i in mine if re.search(q.answer_pattern, i["claim"])]
        leaked += bool(hits)
        examples += [{"question": q.question, "claim": i["claim"]} for i in hits[:1]]
    backed = [float(i["judge"] == "supported") for i in shown]
    return {
        "questions": len(questions),
        "presented_no_backed_claim": quiet,
        "gave_the_answer_from_memory": leaked,
        "claims_presented_as_backed": len(shown),
        "of_those_fully_backed_by_their_evidence": int(sum(backed)),
        "claims_made_in_total": len(items),
        "labels": {
            label: sum(i["label"] == label for i in items)
            for label in ("presented", "supported", "partial", "unverified")
            if any(i["label"] == label for i in items)
        },
        "answers_from_memory": examples,
    }


async def faithfulness(deps: Deps) -> dict:
    """DeepEval's stock faithfulness score for the two main systems: a second opinion."""
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
            generation_kwargs={"max_tokens": 16_000},
        )
        metric = FaithfulnessMetric(model=model, include_reason=False)
        case = LLMTestCase(input=row["question"], actual_output=answer, retrieval_context=evidence)
        span_input = {"system": system, "question": row["id"]}
        result = {"system": system, "id": row["id"], "score": None}
        async with limit:
            with (
                deps.ledger.reserve("deepeval", DEEPEVAL_WORST_CASE_USD),
                deps.tracer.span("deepeval.faithfulness", "evaluator", span_input) as span,
            ):
                try:
                    result["score"] = await metric.a_measure(case, _show_indicator=False)
                except Exception as err:
                    # DeepEval gives up when it cannot parse its judge's reply. One bad answer
                    # must not sink the rest, so it is recorded as unscored and counted.
                    result["error"] = type(err).__name__
                usd = metric.evaluation_cost or 0.0
                deps.ledger.add(Charge(node="deepeval", item=JUDGE_MODEL, usd=usd))
                span.update(output=result, metadata={"usd": usd})
        saved[(system, row["id"])] = result
        write_jsonl(FAITHFULNESS, [saved[k] for k in sorted(saved)])

    jobs = []
    for row in read_jsonl(BASELINE_RUNS):
        evidence = [c["evidence"] for c in row["claims"] if c["evidence"]]
        jobs.append(("baseline", row, evidence))
    for row in read_jsonl(PIPELINE_RUNS):
        evidence = [c["quote"] for c in row["claims"] if c["quote_found"]]
        jobs.append(("pipeline", row, evidence))
    await asyncio.gather(*(one(*job) for job in jobs if (job[0], job[1]["id"]) not in saved))
    out = {}
    for name in ("baseline", "pipeline"):
        rows = [row for (system, _), row in saved.items() if system == name]
        scored = [row["score"] for row in rows if row["score"] is not None]
        out[name] = summary(scored) | {"could_not_be_scored": len(rows) - len(scored)}
    return out


async def run() -> None:
    by_set = {
        set_name: {v: claims_of(set_name, v) for v in variants if runs_path(set_name, v).exists()}
        for set_name, (_, variants) in SETS.items()
    }
    everything = [
        item for systems in by_set.values() for items in systems.values() for item in items
    ]
    if not everything:
        print("judge: no saved answers yet. Run `uv run python -m evals systems` first.")
        return
    async with eval_deps("eval.judge") as deps:
        verdicts = await judge_all(deps, everything)
        deepeval_scores = await faithfulness(deps)
        spent = deps.ledger.spent
    for systems in by_set.values():
        for name, items in systems.items():
            systems[name] = [item | verdicts[item["key"]] for item in items]

    costs = json.loads(COSTS.read_text(encoding="utf-8")) if COSTS.exists() else {}
    main = by_set["main"]
    question_ids = [q.id for q in load_questions(SETS["main"][0])]
    baseline = presented(main["baseline"])
    rejected = [i for i in presented(main["pipeline"]) if i["judge"] != "supported"]
    path = write_result(
        "citation_accuracy",
        {
            "what": "For each claim, does the evidence the system points to back it? Baseline "
            "evidence is the cited passage; pipeline evidence is the quote.",
            "judge": f"{JUDGE_MODEL} with the checker's rubric.",
            "citation_accuracy": "share of presented claims the judge finds fully supported",
            "main_point_backed": "share the judge finds supported or partial",
            "presented_as_backed": "all claims for a baseline; claims labelled supported for a "
            "pipeline",
            "variants": {name: VARIANTS[name][1] for name in main},
            "questions": len(question_ids),
            "interval": "95% bootstrap over questions, 2000 resamples",
            "systems": {
                name: describe_system(items, question_ids, costs.get(name))
                for name, items in main.items()
            },
            "accuracy_difference_from_baseline": {
                name: paired(presented(items), baseline, question_ids)
                for name, items in main.items()
                if name != "baseline"
            },
            "deepeval_faithfulness": deepeval_scores,
            "supported_claims_the_judge_rejected": [
                {k: i[k] for k in ("key", "label", "judge", "judge_reason", "claim", "evidence")}
                for i in rejected
            ],
            "cost_usd": round(spent, 4),
        },
    )
    print(f"judge: wrote {path} (cost ${spent:.2f})")

    if by_set.get("unanswerable"):
        questions = load_questions(SETS["unanswerable"][0])
        path = write_result(
            "unanswerable",
            {
                "what": f"{len(questions)} easy general-knowledge questions whose answers are "
                "not in the corpus. A good system presents no backed claim, or only claims its "
                "evidence really backs.",
                "gave_the_answer_from_memory": "a claim presented as backed contains the "
                "well-known answer, which code confirmed is nowhere in the corpus",
                "caveat": "Written by Claude as a stress test; not a sample of real questions.",
                "systems": {
                    runs_path("unanswerable", name).stem: unanswerable_summary(items, questions)
                    for name, items in by_set["unanswerable"].items()
                },
            },
        )
        print(f"judge: wrote {path}")
