"""Build `evals/results/REPORT.md` from the result files. It makes no model calls.

Every number in the report is read from a JSON file in `evals/results/`. A section whose file
does not exist yet says so instead of showing a placeholder number.
"""

import json
from typing import Any

from evals.common import RESULTS_DIR
from evidentia.config import Settings

REPORT = RESULTS_DIR / "REPORT.md"
# The website's Evals page reads this one file: the result files with the long lists removed.
SITE_DATA = RESULTS_DIR.parent.parent / "web" / "src" / "data" / "evals.json"
TOO_LONG_FOR_THE_SITE = {
    "per_question",
    "disagreements",
    "runs",
    "supported_claims_the_judge_rejected",
    "confusion_reference_rows_checker_columns",
    "lowest_recall_questions",
}
# The real-world audit (D-042 to D-048), for the findings page. Absent files are left out, and the
# page says what is missing instead of showing a number.
REALWORLD = (
    "realworld",
    "realworld_reask",
    "realworld_rendered",
    "realworld_short",
    "realworld_hand_check",
)


def too_long(key: str, value: Any) -> bool:
    # "runs" is a long list in the nasty test, but in the real-world results it holds the
    # figures for each run (a dict), which the findings page shows.
    if key == "runs":
        return isinstance(value, list)
    return key in TOO_LONG_FOR_THE_SITE


def slim(value: Any) -> Any:
    """A copy without the long lists, so the site ships numbers and not megabytes."""
    if isinstance(value, dict):
        return {k: slim(v) for k, v in value.items() if not too_long(k, v)}
    if isinstance(value, list):
        return [slim(v) for v in value]
    return value


# The limits the site's method page states. They are read from the settings' defaults, so the
# page cannot say one thing while the code does another.
SITE_SETTINGS = (
    "audit_max_claims",
    "audit_max_pages",
    "audit_min_page_chars",
    "audit_page_chars",
    "audit_cap_usd",
    "max_audits_per_ip",
    "per_host_interval_s",
)


def auditor_limits() -> dict[str, Any]:
    return {name: Settings.model_fields[name].default for name in SITE_SETTINGS}


def write_site_data(results: dict[str, dict | None]) -> None:
    present = {name: slim(result) for name, result in results.items() if result}
    if present:  # never replace real numbers with an empty file
        present["auditor_limits"] = auditor_limits()
        SITE_DATA.parent.mkdir(parents=True, exist_ok=True)
        SITE_DATA.write_text(json.dumps(present, indent=1, ensure_ascii=False), encoding="utf-8")


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


SYSTEM_NAMES = {
    "baseline": "Baseline (one-shot RAG), Sonnet writer",
    "pipeline": "Pipeline, Sonnet writer and checker",
    "baseline_haiku": "Baseline, Haiku writer",
    "pipeline_haiku": "Pipeline, Haiku writer and checker",
    "pipeline_tighten": "Pipeline with partial claims tightened (the product default)",
}


def accuracy_section(d: dict | None) -> list[str]:
    out = ["## Baselines against pipelines", ""]
    if d is None:
        return [*out, "Not run yet: `evals/results/citation_accuracy.json` does not exist.", ""]
    out += [
        f"{d['what']} Judge: {d['judge']} Shown as backed means: {d['presented_as_backed']}.",
        "",
    ]
    rows = []
    for name, s in d["systems"].items():
        shown = s["presented_as_backed"]
        cost = s.get("cost_per_question_usd")
        rows.append(
            [
                SYSTEM_NAMES.get(name, name),
                with_ci(shown["citation_accuracy"], "value"),
                f"{shown['claims_per_question']['mean']:.2f}",
                f"{s['all_claims']['claims_per_question']['mean']:.2f}",
                str(s["evidence_chars_median"]),
                "n/a" if cost is None else f"${cost:.4f}",
            ]
        )
    header = ["System", "Shown as backed that are fully backed", "Shown as backed per question"]
    header += ["All claims per question", "Characters to read per claim", "Cost per question"]
    out += [*table(header, rows), ""]
    out += ["Fully backed, each system minus the Sonnet baseline, per question:", ""]
    rows = [
        [SYSTEM_NAMES.get(name, name), signed(diff), str(diff["n"])]
        for name, diff in d["accuracy_difference_from_baseline"].items()
    ]
    out += [*table(["System", "Difference", "Questions"], rows), ""]
    if d.get("deepeval_faithfulness"):
        scores = ", ".join(f"{k} {with_ci(v)}" for k, v in d["deepeval_faithfulness"].items())
        out += [f"DeepEval faithfulness (stock metric, same judge model): {scores}.", ""]
    return out


def unanswerable_section(d: dict | None) -> list[str]:
    out = ["## Questions the corpus cannot answer", ""]
    if d is None:
        return [*out, "Not run yet: `evals/results/unanswerable.json` does not exist.", ""]
    out += [f"{d['what']} {d['caveat']}", ""]
    rows = [
        [
            SYSTEM_NAMES.get(name.removeprefix("unanswerable_"), name),
            f"{s['presented_no_backed_claim']} of {s['questions']}",
            f"{s['gave_the_answer_from_memory']} of {s['questions']}",
            str(s["claims_presented_as_backed"]),
            str(s["of_those_fully_backed_by_their_evidence"]),
        ]
        for name, s in d["systems"].items()
    ]
    header = ["System", "Stayed quiet", "Answered from memory", "Claims shown as backed"]
    return [*out, *table([*header, "Of those, fully backed"], rows), ""]


def nasty_section(d: dict | None) -> list[str]:
    out = ["## Nasty tests", ""]
    if d is None:
        return [*out, "Not run yet: `evals/results/nasty.json` does not exist.", ""]
    rows = [[name, f"{c['passed']} of {c['trials']}"] for name, c in d["cases"].items()]
    return [*out, d["caveat"], "", *table(["Case", "Passed"], rows), ""]


def bacc(stat: dict[str, Any]) -> str:
    return with_ci(stat, "mean_bacc")


def aggrefact_section(runs: dict[str, dict | None]) -> list[str]:
    out = ["## The auditor on LLM-AggreFact", ""]
    present = {name: d for name, d in runs.items() if d}
    if not present:
        return [*out, "Not run yet: no `evals/results/aggrefact_test_*.json` file exists.", ""]
    out += [
        "LLM-AggreFact pairs a claim with a document and a person's label: supported or not. "
        "The sample is 50 test rows from each of its 11 sub-datasets. Balanced accuracy is "
        "computed per sub-dataset, then averaged, with a 95% interval. The auditor finds quotes, "
        "checks them by code, then a checker sees only the claim and the quotes; only "
        "'supported' counts as supported. The direct baseline is the same model shown the "
        "whole document and asked yes or no. Prompts were fixed on dev rows before this run.",
        "",
    ]
    rows = []
    for d in present.values():
        auditor, direct = d["systems"]["auditor"], d["systems"]["direct"]
        rows.append(
            [
                f"auditor, {d['model']}",
                bacc(auditor["score"]),
                bacc(auditor["score_partial_counted_supported"]),
                f"${auditor['usd_per_claim']:.5f}",
            ]
        )
        rows.append(
            [f"direct, {d['model']}", bacc(direct["score"]), "", f"${direct['usd_per_claim']:.5f}"]
        )
    out += table(
        ["System", "Balanced accuracy", "Partial counted as supported", "Cost per claim"], rows
    )
    for d in present.values():
        diff = d["auditor_minus_direct"]
        auditor = d["systems"]["auditor"]
        out += [
            "",
            f"{d['model']}, {d['rows']} rows: auditor minus direct "
            f"{diff['difference']:+.3f} ({diff['ci_low']:+.3f} to {diff['ci_high']:+.3f}). "
            f"Auditor labels: {', '.join(f'{n} {k}' for k, n in auditor['labels'].items())}. "
            f"{auditor['rows_with_an_exact_quote']} rows had at least one quote found word "
            f"for word.",
            "",
        ]
        pooled = [
            [
                name,
                str(s["pooled"]["said_supported"]),
                f"{s['pooled']['supported_and_right']:.3f}",
                f"{s['pooled']['caught_supported']:.3f}",
                f"{s['pooled']['caught_unsupported']:.3f}",
            ]
            for name, s in d["systems"].items()
            if "pooled" in s
        ]
        if pooled:
            header = ["System", "Said supported", "Of those, right", "Supported rows accepted"]
            out += table([*header, "Unsupported rows rejected"], pooled) + [""]
        names = list(auditor["score"]["per_dataset"])
        per = [
            [
                name,
                str(auditor["score"]["per_dataset"][name]["n"]),
                f"{auditor['score']['per_dataset'][name]['bacc']:.3f}",
                f"{d['systems']['direct']['score']['per_dataset'][name]['bacc']:.3f}",
            ]
            for name in names
        ]
        out += table(["Sub-dataset", "Rows", "Auditor", "Direct"], per)
    return [*out, ""]


def ci(stat: dict[str, Any] | None) -> str:
    if not stat or stat["value"] is None:
        return "none"
    if stat["ci_low"] is None:
        return f"{stat['value']:.3f}"
    return f"{stat['value']:.3f} ({stat['ci_low']:.3f} to {stat['ci_high']:.3f})"


def two_judges_section(runs: dict[str, dict]) -> list[str]:
    out = ["## Two judges on LLM-AggreFact", ""]
    if not runs:
        return [*out, "Not run yet: no `evals/results/aggrefact_*_q-*_p-*.json` file exists.", ""]
    out += [
        "A claim gets a verdict only when the quote judge (exact quotes, then a check on the "
        "quotes alone) and the page judge (the claim and the page) agree. Otherwise it is "
        "'needs a human'. Flag precision: of the claims flagged, the share people label "
        "unsupported. Supported precision: of the claims called supported, the share people "
        "label supported. Coverage: the share that get a verdict. 95% intervals in brackets.",
        "",
    ]
    for d in runs.values():
        two, quote, page = d["two_judges"], d["quote_judge_alone"], d["page_judge_alone"]
        judges = d["judges"]
        context = " with quote context" if judges.get("quote_context") == "True" else ""
        out += [
            f"### {d['sample']}: quote judge {judges['quote']}{context}, page judge "
            f"{judges['page']} ({d['rows']} rows)",
            "",
        ]
        header = ["System", "Balanced accuracy", "Flag precision", "Supported precision"]
        rows = [
            [
                "Two judges",
                ci(two["balanced_accuracy"]),
                ci(two["flag_precision"]),
                ci(two["supported_precision"]),
                ci(two["coverage"]),
            ],
            [
                "Quote judge alone",
                ci(quote["balanced_accuracy"]),
                ci(quote["flag_precision"]),
                ci(quote["supported_precision"]),
                "1.000",
            ],
            [
                "Page judge alone",
                ci(page["balanced_accuracy"]),
                ci(page["flag_precision"]),
                ci(page["supported_precision"]),
                "1.000",
            ],
        ]
        out += table([*header, "Coverage"], rows)
        labels = ", ".join(f"{n} {k}" for k, n in two["labels"].items())
        finish = d["finish_line"]
        verdict = "passed" if finish["passed"] else "not passed"
        bars = ", ".join(f"{k} {v}" for k, v in finish["thresholds"].items())
        out += [
            "",
            f"Two judges, with every 'needs a human' counted as wrong: balanced accuracy "
            f"{ci(two['balanced_accuracy_abstain_counted_wrong'])}. Labels: {labels}. "
            f"Cost per claim, both judges: ${d['usd']['per_claim_both']:.5f}. "
            f"D-038 finish line ({bars}): {verdict}.",
            "",
        ]
        per = [
            [
                ds,
                f"{two['per_dataset'][ds]:.3f}",
                f"{two['coverage_per_dataset'][ds]:.3f}",
                f"{quote['per_dataset'][ds]:.3f}",
                f"{page['per_dataset'][ds]:.3f}",
            ]
            for ds in two["per_dataset"]
        ]
        out += table(["Sub-dataset", "Two judges", "Coverage", "Quote alone", "Page alone"], per)
        sweep = d.get("threshold_sweep")
        if sweep:
            out += ["", "Best thresholds on these rows (most coverage that meets the bars):", ""]
            rows = []
            for name, key in (
                ("partial counted as a flag", "best_partial_as_flag"),
                ("partial as its own verdict", "best_partial_own_verdict"),
            ):
                pt = sweep[key]
                flag = (
                    "flag_precision"
                    if key == "best_partial_as_flag"
                    else ("flag_precision_partial_own_verdict")
                )
                rows.append(
                    [name, "none meets the bars", "", "", ""]
                    if pt is None
                    else [
                        name,
                        f"{pt['t_supported']} / {pt['t_flag']}",
                        f"{pt[flag]:.3f}",
                        f"{pt['supported_precision']:.3f}",
                        f"{pt['coverage']:.3f}",
                    ]
                )
            header = ["Partial", "Thresholds (supported / flag)", "Flags right"]
            out += table([*header, "Supported right", "Coverage"], rows)
        out += [""]
    return out


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
    unanswerable = results["unanswerable"]
    if unanswerable:
        for name, system in unanswerable["systems"].items():
            for leak in system["answers_from_memory"]:
                out += [f"- {name} answered from memory: {leak['question']} -> {leak['claim']}"]
    if nasty:
        for name, case in nasty["cases"].items():
            for run in case["runs"]:
                if not run["passed"]:
                    out += [f"- Nasty test {name}, trial {run['trial']}: {run['why']}."]
    if len(out) == 2:
        out += ["Nothing has been run yet."]
    return [*out, ""]


def run() -> None:
    names = ["retrieval", "checker_agreement", "citation_accuracy", "unanswerable", "nasty"]
    names += ["aggrefact_test_haiku", "aggrefact_test_sonnet"]
    results = {name: load(name) for name in names}
    aggrefact = {k: v for k, v in results.items() if k.startswith("aggrefact_")}
    two_judges = {
        p.stem: load(p.stem) for p in sorted(RESULTS_DIR.glob("aggrefact_*_q-*_p-*.json"))
    }
    results |= two_judges
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
        *unanswerable_section(results["unanswerable"]),
        *nasty_section(results["nasty"]),
        *aggrefact_section(aggrefact),
        *two_judges_section(two_judges),
        *failures_section(results),
    ]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    write_site_data(results | {name: load(name) for name in REALWORLD})
    print(f"report: wrote {REPORT}")
