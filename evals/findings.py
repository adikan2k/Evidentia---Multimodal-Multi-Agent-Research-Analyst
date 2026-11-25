"""The examples on the findings page, chosen by the rule fixed in D-042 (D-048).

    uv run python -m evals realworld examples     # free: writes web/public/findings/

Every contradicted claim, then 5 "not on the cited page" claims for each tool, drawn with a fixed
seed. All from the main run, with the page judge as shipped. No example is picked by hand.
Each chosen answer's saved audit is copied for the site, with the question it answered.
"""

import json
import random
from pathlib import Path
from typing import Any

from evals.realworld import HERE, TOOLS, answer_path, audit_path, load, load_questions

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "findings"
JUDGE = "haiku"
EXAMPLE_SEED = 20261203  # D-042 fixed the rule; this number was set when the page was built
NOT_FOUND_PER_TOOL = 5


def example_id(tool: str, qid: str, index: int) -> str:
    return f"{tool}-{qid}-{index + 1}"


def choose_examples(reports: dict[tuple[str, str], dict]) -> list[dict[str, Any]]:
    """The rule: every contradicted claim, then a seeded draw of "not on the cited page" claims.

    `reports` maps (tool, question id) to a saved audit report.
    """
    rng = random.Random(EXAMPLE_SEED)
    chosen: list[dict[str, Any]] = []
    for tool in TOOLS:
        found: dict[str, list[dict]] = {"contradicted": [], "not_found": []}
        for (t, qid), report in sorted(reports.items()):
            if t != tool:
                continue
            for index, claim in enumerate(report["claims"]):
                if claim["label"] in found:
                    found[claim["label"]].append(
                        {
                            "id": example_id(tool, qid, index),
                            "tool": tool,
                            "question": qid,
                            "claim_index": index,
                            "label": claim["label"],
                            "claim": claim["claim"],
                            "cited_by": claim.get("cited_by"),
                        }
                    )
        drawn = rng.sample(found["not_found"], min(NOT_FOUND_PER_TOOL, len(found["not_found"])))
        chosen += [x | {"why": "every contradicted claim"} for x in found["contradicted"]]
        chosen += [x | {"why": "drawn at random from the not-on-the-page claims"} for x in drawn]
    return chosen


def main_run_reports() -> dict[tuple[str, str], dict]:
    reports = {}
    for q in load_questions("all"):
        for tool in TOOLS:
            audit = load(audit_path(JUDGE, tool, q["id"]))
            if audit:
                reports[(tool, q["id"])] = audit["report"]
    return reports


def write_examples(out: Path = OUT) -> list[dict[str, Any]]:
    questions = {q["id"]: q for q in load_questions("all")}
    reports = main_run_reports()
    chosen = choose_examples(reports)
    answers = out / "answers"
    answers.mkdir(parents=True, exist_ok=True)
    for tool, qid in sorted({(x["tool"], x["question"]) for x in chosen}):
        answer = load(answer_path(tool, qid, HERE)) or {}
        body = {
            "tool": tool,
            "question_id": qid,
            "question": questions[qid]["question"],
            "source": questions[qid]["source"],
            "answer": {
                "model": answer.get("model"),
                "made_at": answer.get("made_at"),
                "usd": answer.get("usd"),
            },
            "report": reports[(tool, qid)],
        }
        path = answers / f"{tool}-{qid}.json"
        path.write_text(json.dumps(body, ensure_ascii=False) + "\n", encoding="utf-8")
    index = {
        "rule": f"Every contradicted claim, then {NOT_FOUND_PER_TOOL} 'not on the cited page' "
        "claims for each tool, drawn with a fixed seed (D-042). Main run, page judge as shipped.",
        "seed": EXAMPLE_SEED,
        "examples": [x | {"question_text": questions[x["question"]]["question"]} for x in chosen],
    }
    (out / "index.json").write_text(
        json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(chosen)} examples from {len(list(answers.glob('*.json')))} answers")
    return chosen
