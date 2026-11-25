"""The README's "Results at a glance" block, written from the result files (rule 7).

`python -m evals report` rewrites the block between the two markers below. A test checks that the
README matches what this module builds, so a number cannot be typed in or left stale.
"""

import json
import pathlib
from typing import Any

from evals.common import RESULTS_DIR

README = RESULTS_DIR.parent.parent / "README.md"
START = "<!-- results:start (written by `python -m evals report`; do not edit by hand) -->"
END = "<!-- results:end -->"

POOLED = "aggrefact_pooled-dev550b+test2_q-haiku_p-haiku"
RETRIEVERS = {
    "bm25": "Keyword only (BM25)",
    "dense": "Dense only",
    "hybrid": "Hybrid (dense + BM25)",
    "dense_rerank": "**Dense + rerank (shipped)**",
    "hybrid_rerank": "Hybrid + rerank",
}
SYSTEMS = {
    "baseline": "Plain RAG, Sonnet",
    "pipeline": "Evidentia before tightening",
    "pipeline_tighten": "**Evidentia (shipped)**",
}
QUIET = {
    "unanswerable_baseline": "Plain RAG, Sonnet",
    "unanswerable_pipeline": "Evidentia",
    "unanswerable_baseline_haiku": "Plain RAG, Haiku",
    "unanswerable_pipeline_haiku": "Evidentia, all Haiku",
}
HOSTILE = {
    "hidden_instructions": "Hidden instructions in a page",
    "paywall": "A paywalled page",
    "contradiction": "Two pages that disagree",
}
KS = (1, 3, 5, 10)


def load(name: str) -> dict[str, Any]:
    return json.loads((RESULTS_DIR / f"{name}.json").read_text(encoding="utf-8"))


def three(x: float) -> str:
    return f"{x:.3f}"


def interval(stat: dict[str, Any]) -> str:
    return f"{three(stat['ci_low'])} to {three(stat['ci_high'])}"


def pct(x: float) -> str:
    return f"{round(x * 100)}%"


def table(head: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    return lines + ["| " + " | ".join(row) + " |" for row in rows]


def auditor() -> list[str]:
    d = load(POOLED)
    two = d["two_judges"]
    shipped = two["partial_as_its_own_verdict"]
    rows = [
        [
            "Flags right (marked not on the page or contradicted)",
            three(shipped["flag_precision"]["value"]),
            interval(shipped["flag_precision"]),
        ],
        [
            "Supported marks right",
            three(shipped["supported_precision"]["value"]),
            interval(shipped["supported_precision"]),
        ],
        [
            "Balanced accuracy, on claims with a verdict",
            three(two["balanced_accuracy"]["value"]),
            interval(two["balanced_accuracy"]),
        ],
        [
            "Claims given a verdict (the rest go to a person)",
            three(two["coverage"]["value"]),
            interval(two["coverage"]),
        ],
    ]
    return [
        "### The auditor, against people's labels",
        "",
        f"{d['rows']:,} rows of LLM-AggreFact that were never used to tune it. 0.500 balanced "
        "accuracy is a guess.",
        "",
        *table(["Measure", "Value", "95% interval"], rows),
        "",
        f"Source: `evals/results/{POOLED}.json`.",
        "",
    ]


def hand_checks() -> list[str]:
    rows = []
    for name, label in (
        ("realworld_hand_check", "First, before the fix (D-044)"),
        ("realworld_hand_check_2", "Second, after the fix (D-049)"),
    ):
        path = RESULTS_DIR / f"{name}.json"
        if not path.exists():
            continue
        d = load(name)
        flags = d["flags_upheld"]["both_tools"]
        backed = d["supported_upheld"]["both_tools"]
        rows.append(
            [
                label,
                str(d["items_checked"]),
                f"{pct(flags['share'])}, {flags['hits']} of {flags['n']}",
                f"{pct(flags['ci_low'])} to {pct(flags['ci_high'])}",
                f"{backed['hits']} of {backed['n']}",
                "yes" if d["rule"]["met"] else "no",
            ]
        )
    return [
        "### The auditor on real answers: blind hand checks",
        "",
        "A person checked samples of its verdicts on two AI search tools' answers against the "
        "live pages, blind to the tool and the verdict. The bar, set before any label: 70% of "
        "flags upheld. It was not met, so the tools are not compared.",
        "",
        *table(
            ["Hand check", "Claims", "Flags upheld", "95% interval", "Supported upheld", "Bar met"],
            rows,
        ),
        "",
        "Source: `evals/results/realworld_hand_check.json`, `realworld_hand_check_2.json`.",
        "",
    ]


def search() -> list[str]:
    d = load("retrieval")
    best = d["best_possible"]
    head = ["Retriever", *(f"R@{k}" for k in KS), *(f"P@{k}" for k in KS), "MRR@10", "nDCG@10"]
    rows = []
    for key, label in RETRIEVERS.items():
        m = d["retrievers"][key]
        rows.append(
            [
                label,
                *(three(m[f"recall_at_{k}"]["mean"]) for k in KS),
                *(three(m[f"precision_at_{k}"]["mean"]) for k in KS),
                three(m["mrr_at_10"]["mean"]),
                three(m["ndcg_at_10"]["mean"]),
            ]
        )
    rows.append(
        [
            "Best possible",
            *(three(best[f"recall_at_{k}"]) for k in KS),
            *(three(best[f"precision_at_{k}"]) for k in KS),
            three(best["mrr_at_10"]),
            three(best["ndcg_at_10"]),
        ]
    )
    rel = d["relevant_per_question"]["mean"]
    return [
        "### Search: recall and precision at k",
        "",
        f"{d['questions']} questions over {d['corpus']['passages']:,} passages from "
        f"{d['corpus']['pages']} saved pages, mostly Wikipedia. R@k is the share of relevant "
        "passages in the top k; P@k is the share of the top k that is relevant. A question has "
        f"{rel:.1f} relevant passages on average, so no ranking can reach 1 on every measure: "
        "the last row is what a perfect ranking would score.",
        "",
        *table(head, rows),
        "",
        f"Intervals ({d['interval']}) are in `evals/results/REPORT.md`. "
        "Source: `evals/results/retrieval.json`.",
        "",
    ]


def research_agent() -> list[str]:
    acc = load("citation_accuracy")
    rows = []
    for key, label in SYSTEMS.items():
        s = acc["systems"][key]
        backed = s["presented_as_backed"]["citation_accuracy"]
        rows.append(
            [
                label,
                f"{three(backed['value'])} ({interval(backed)})",
                str(s["evidence_chars_median"]),
                f"${s['cost_per_question_usd']:.4f}",
            ]
        )
    agreement = load("checker_agreement")
    product = agreement["product_checker"]
    caught = agreement["error_detection_on_built_pairs"]
    second = agreement["references"]["second_model"]
    checker_rows = []
    for model, kinds in caught.items():
        a = second["models"][model]["all"]
        name = f"**{model} (shipped)**" if model == product else model
        checker_rows.append(
            [
                name,
                f"{kinds['all_built']['flagged']} of {kinds['all_built']['n']}",
                f"{three(a['agreement']['value'])} ({interval(a['agreement'])})",
                f"{three(a['cohen_kappa']['value'])} ({interval(a['cohen_kappa'])})",
            ]
        )
    unanswerable = load("unanswerable")["systems"]
    nasty = load("nasty")["cases"]
    hostile = ", ".join(
        f"{label.lower()} {nasty[key]['passed']} of {nasty[key]['trials']}"
        for key, label in HOSTILE.items()
        if key in nasty
    )
    quiet = ", ".join(
        f"{QUIET.get(name, name)} {s['presented_no_backed_claim']} of {s['questions']}"
        for name, s in unanswerable.items()
    )
    return [
        "### The research agent, against plain RAG",
        "",
        f"{acc['questions']} questions on the same saved pages. A separate judge "
        f"({acc['judge'].split(' ')[0]}) checked whether each claim's evidence backs it.",
        "",
        *table(
            [
                "System",
                "Claims shown as backed that are fully backed",
                "Characters to read",
                "Cost per question",
            ],
            rows,
        ),
        "",
        *table(
            [
                "Checker model",
                "Broken claims caught",
                "Agreement with a second model",
                "Cohen's kappa",
            ],
            checker_rows,
        ),
        "",
        "Agreement is with a stronger model from the same family, not with a person.",
        "",
        f"- Hostile pages passed: {hostile}.",
        f"- Questions the pages cannot answer, where the system made no claim: {quiet}.",
        "",
        "Source: `evals/results/citation_accuracy.json`, `checker_agreement.json`, "
        "`unanswerable.json`, `nasty.json`.",
        "",
    ]


def open_web() -> list[str]:
    if not (RESULTS_DIR / "open_web.json").exists():
        return []
    d = load("open_web")
    rows = []
    for key, label in (
        ("open_web_baseline", "Plain RAG, same pages"),
        ("open_web_pipeline", "**Evidentia (shipped)**"),
    ):
        s = d["systems"][key]
        backed = s["presented_as_backed"]["citation_accuracy"]
        cost = s.get("cost_per_question_usd")
        rows.append(
            [
                label,
                f"{three(backed['value'])} ({interval(backed)})",
                f"{backed['correct']} of {backed['claims']}",
                f"${cost:.4f}" if cost is not None else "not measured",
            ]
        )
    pages = d["pages"]
    diff = d["accuracy_difference_from_baseline"]["open_web_pipeline"]
    return [
        "### The research agent on the open web",
        "",
        f"{d['questions']} of the questions, asked from the start on live web search. Plain RAG "
        "answered from the pages the agent fetched for each question. Same judge as above. "
        "Search results change, so this run cannot be repeated exactly.",
        "",
        *table(
            [
                "System",
                "Claims shown as backed that are fully backed",
                "Claims",
                "Cost per question",
            ],
            rows,
        ),
        "",
        f"- Difference per question, Evidentia minus plain RAG: {diff['mean']:+.3f} "
        f"({diff['ci_low']:+.3f} to {diff['ci_high']:+.3f}).",
        f"- Pages read: {pages['pages_read']} from {pages['different_sites_read']} sites, "
        f"{pct(pages['wikipedia_share_of_pages_read'])} from Wikipedia; "
        f"{pages['pages_not_read']} could not be read.",
        "",
        "Source: `evals/results/open_web.json`.",
        "",
    ]


def block() -> str:
    lines = [
        START,
        "",
        "## Results at a glance",
        "",
        "Every number in this section is written by code from `evals/results/`. "
        "The website's Evals page reads the same files.",
        "",
        *auditor(),
        *hand_checks(),
        *search(),
        *research_agent(),
        *open_web(),
        END,
    ]
    return "\n".join(lines)


def with_block(readme: str) -> str:
    """The README with its results block replaced. Both markers must already be there."""
    start, end = readme.index(START), readme.index(END) + len(END)
    return readme[:start] + block() + readme[end:]


def write(path: pathlib.Path = README) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(with_block(text), encoding="utf-8", newline="\n")
