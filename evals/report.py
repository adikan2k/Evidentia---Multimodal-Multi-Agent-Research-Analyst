"""Build `evals/results/REPORT.md` from the result files. It makes no model calls.

Every number in the report is read from a JSON file in `evals/results/`. A section whose file
does not exist yet says so instead of showing a placeholder number.
"""

import json
from typing import Any

from evals.common import RESULTS_DIR

REPORT = RESULTS_DIR / "REPORT.md"


def load(name: str) -> dict[str, Any] | None:
    path = RESULTS_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def with_ci(stat: dict[str, Any], key: str = "mean") -> str:
    return f"{stat[key]:.3f} ({stat['ci_low']:.3f} to {stat['ci_high']:.3f})"


def signed(stat: dict[str, Any]) -> str:
    return f"{stat['mean']:+.3f} ({stat['ci_low']:+.3f} to {stat['ci_high']:+.3f})"


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join(row) + " |" for row in rows]


def retrieval_section(d: dict | None) -> list[str]:
    out = ["## Retrieval", ""]
    if d is None:
        return [*out, "Not run yet: `evals/results/retrieval.json` does not exist.", ""]
    corpus = d["corpus"]
    out += [
        f"{d['questions']} questions over {corpus['pages']} pages cut into "
        f"{corpus['passages']} passages. Scores are for the top 10 passages, with a "
        "95% interval in brackets.",
        "",
    ]
    rows = [
        [name, *(with_ci(m[k]) for k in ("recall_at_10", "mrr_at_10", "ndcg_at_10"))]
        for name, m in d["retrievers"].items()
    ]
    out += table(["Retriever", "Recall@10", "MRR@10", "nDCG@10"], rows)
    out += ["", "Difference per question, second minus first:", ""]
    rows = [
        [name.replace("_minus_", " minus "), *(signed(m[k]) for k in m)]
        for name, m in d["paired_differences"].items()
    ]
    out += table(["Comparison", "Recall@10", "MRR@10", "nDCG@10"], rows)
    return [*out, "", f"Gold: {d['gold']}", ""]


def agreement_section(d: dict | None) -> list[str]:
    out = ["## How reliable is the checker?", ""]
    if d is None:
        return [*out, "Not run yet: `evals/results/checker_agreement.json` does not exist.", ""]
    out += ["### Deliberately broken claims", ""]
    out += [
        "A third of the test pairs were broken on purpose: given the wrong quote, one fact "
        "changed, or a detail added. This counts how many each checker refused to pass as "
        "supported. No labels are involved.",
        "",
    ]
    kinds = ["wrong_quote", "changed_fact", "added_detail", "all_built"]
    rows = [
        [model, *(f"{m[k]['flagged']} of {m[k]['n']}" for k in kinds)]
        for model, m in d["error_detection_on_built_pairs"].items()
    ]
    header = ["Checker model", "Wrong quote", "Changed fact", "Added detail", "All broken pairs"]
    out += [*table(header, rows), ""]
    titles = {
        "person": "### Agreement with a person",
        "second_model": "### Agreement with a second model (not a person)",
    }
    if "person" not in d["references"]:
        out += [titles["person"], "", f"{d['human_labels']}", ""]
    for name, ref in d["references"].items():
        out += [titles[name], "", f"{ref['labeller']} {ref['caveat']}", ""]
        rows = []
        for model, m in ref["models"].items():
            a, k = m["all"]["agreement"], m["all"]["cohen_kappa"]
            real, built = m["real_pairs"]["agreement"], m["built_pairs"]["agreement"]
            rows.append(
                [model, with_ci(a, "value"), with_ci(k, "value")]
                + [f"{real['value']:.3f}", f"{built['value']:.3f}"]
            )
        header = ["Checker model", "Agreement", "Cohen's kappa", "Real pairs", "Built pairs"]
        out += [*table(header, rows), ""]
    return out


def accuracy_section(d: dict | None) -> list[str]:
    out = ["## Baseline against the full pipeline", ""]
    if d is None:
        return [*out, "Not run yet: `evals/results/citation_accuracy.json` does not exist.", ""]
    out += [f"{d['what']} Judge: {d['judge']}", ""]
    systems = {
        "Baseline (one-shot RAG), all claims": d["baseline"],
        "Pipeline, claims labelled supported": d["pipeline_claims_labelled_supported"],
        "Pipeline, all claims": d["pipeline_all_claims"],
    }
    rows = [
        [
            name,
            with_ci(s["citation_accuracy"], "value"),
            with_ci(s["main_point_backed"], "value"),
            with_ci(s["claims_per_question"]),
            with_ci(s["questions_with_a_fully_backed_claim"]),
        ]
        for name, s in systems.items()
    ]
    header = ["System", "Fully backed", "Main point backed", "Claims per question"]
    out += table([*header, "Questions with a fully backed claim"], rows)
    diff = d["accuracy_difference_supported_minus_baseline"]
    out += [
        "",
        "Fully backed, pipeline claims labelled supported minus baseline, per question: "
        f"{signed(diff)} over {diff['n']} questions.",
        "",
        f"Pipeline labels: {d['pipeline_labels']}.",
        "",
    ]
    if d.get("deepeval_faithfulness"):
        scores = ", ".join(f"{k} {with_ci(v)}" for k, v in d["deepeval_faithfulness"].items())
        out += [f"DeepEval faithfulness (stock metric, same judge model): {scores}.", ""]
    return out


def nasty_section(d: dict | None) -> list[str]:
    out = ["## Nasty tests", ""]
    if d is None:
        return [*out, "Not run yet: `evals/results/nasty.json` does not exist.", ""]
    rows = [[name, f"{c['passed']} of {c['trials']}"] for name, c in d["cases"].items()]
    return [*out, d["caveat"], "", *table(["Case", "Passed"], rows), ""]


def failures_section(results: dict[str, dict | None]) -> list[str]:
    out = ["## What failed", ""]
    retrieval, agreement, accuracy, nasty = (
        results[k] for k in ("retrieval", "checker_agreement", "citation_accuracy", "nasty")
    )
    if retrieval:
        worst = ", ".join(
            f"{q['id']} ({q['recall_at_10']:.2f})"
            for q in retrieval["lowest_recall_questions"]
            if q["recall_at_10"] < 1
        )
        out += [f"- Retrieval, lowest recall with hybrid + rerank: {worst or 'none below 1.0'}."]
    if accuracy:
        rejected = accuracy["supported_claims_the_judge_rejected"]
        out += [
            f"- {len(rejected)} pipeline claims were labelled supported but the judge did not "
            "agree. The first few:"
        ]
        out += [
            f"  - {r['claim']} (judge: {r['judge']}; {r['judge_reason']})" for r in rejected[:5]
        ]
    if agreement:
        product = agreement["product_checker"]
        missed = agreement["error_detection_on_built_pairs"][product]["all_built"]
        out += [
            f"- The product's checker passed {missed['n'] - missed['flagged']} of "
            f"{missed['n']} deliberately broken claims as supported."
        ]
        for name, ref in agreement["references"].items():
            rows = ref["models"][product]["disagreements"]
            who = "a person" if name == "person" else "the second model"
            out += [f"- It disagreed with {who} on {len(rows)} of {ref['pairs_labelled']} pairs."]
            out += [
                f"  - {r['id']} ({r['origin']}): reference {r['reference']}, checker "
                f"{r['checker']}. {r['claim']}"
                for r in rows[:5]
            ]
    if nasty:
        for name, case in nasty["cases"].items():
            for run in case["runs"]:
                if not run["passed"]:
                    out += [f"- Nasty test {name}, trial {run['trial']}: {run['why']}."]
    if len(out) == 2:
        out += ["Nothing has been run yet."]
    return [*out, ""]


def run() -> None:
    names = ["retrieval", "checker_agreement", "citation_accuracy", "nasty"]
    results = {name: load(name) for name in names}
    lines = [
        "# Evaluation report",
        "",
        "Built by `python -m evals report` from the JSON files in this folder. Nothing here is "
        "typed by hand.",
        "",
        "The corpus is a frozen set of openly licensed pages, mostly Wikipedia. Those pages are "
        "cleaner than the open web, so these scores are likely higher than real use would give.",
        "",
        *retrieval_section(results["retrieval"]),
        *agreement_section(results["checker_agreement"]),
        *accuracy_section(results["citation_accuracy"]),
        *nasty_section(results["nasty"]),
        *failures_section(results),
    ]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"report: wrote {REPORT}")
