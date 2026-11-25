"""Aditya's labels for the claims both judges called partial (D-038, D-039).

    uv run python -m evals label-partial    # label, one claim at a time; stop and resume any time
    uv run python -m evals partial-labels   # score the labels (free)

Both judges said these claims leave out a detail, yet the benchmark's labellers accepted half of
them. A person decides who is right. The tool shows only the claim and the document: not the
judges' answers, not the benchmark's label, and not whether an item is a partial case or one of
the ten control items mixed in to check the labelling itself.

The items are practice (dev) rows. Only row numbers and answers are saved, never the text.
"""

import json
import random
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from evals.aggrefact import Row, join, run_path, sample
from evals.common import ROOT, read_jsonl, write_jsonl, write_result

ITEMS = ROOT / "partial_items.json"  # which rows to label, fixed once chosen
LABELS = ROOT / "labels_partial.jsonl"  # made by a person; never by a model
MODEL_LABELS = ROOT / "labels_partial_codex.jsonl"  # made by OpenAI Codex, an AI; kept apart
SPOT_CHECK = 15  # the first 15 items, which Aditya labels to check the model's labels
# The spot-check rule (D-039), fixed before Aditya labels: if he and the model agree on at
# least 13 of the 15, the model's labels on the other 35 are used with his, and reported as such.
SPOT_CHECK_AGREEMENT = 13
SEED = 20261126
PARTIAL_ITEMS, CONTROL_ITEMS = 40, 10
MAX_DOC_CHARS = 8_000  # longer documents are too slow to read on screen
KEYS = {"y": "yes", "n": "no", "u": "unsure"}

RUBRIC = """Read the claim, then the document. Judge only from the document, not from what you know.

  y  yes     The document states everything the claim says. Rewording is fine, and so is
             putting together what different sentences say.
  n  no      At least one part of the claim (a number, date, name, place, event or detail)
             is not stated in the document, or the document says otherwise.
  u  unsure  You cannot tell.

  b  go back one item        q  save and quit"""


def choose_items(joined: list[dict], rows: dict[int, Row], seed: int = SEED) -> list[dict]:
    """40 partial cases and 10 controls (5 supported, 5 not on the page), short documents only."""
    short = [x for x in joined if len(rows[x["row"]].doc) <= MAX_DOC_CHARS]
    rng = random.Random(seed)

    def pick(label: str, n: int) -> list[dict]:
        pool = sorted((x for x in short if x["two_label"] == label), key=lambda x: x["row"])
        return [{"row": x["row"], "group": label} for x in rng.sample(pool, min(n, len(pool)))]

    items = pick("partial", PARTIAL_ITEMS)
    items += pick("supported", CONTROL_ITEMS // 2) + pick("not_found", CONTROL_ITEMS // 2)
    rng.shuffle(items)
    return items


def load_items() -> tuple[list[dict], dict[int, Row]]:
    rows = {r.row: r for r in sample("dev550")}
    if not ITEMS.exists():
        joined = join(
            read_jsonl(run_path("dev550", "quote", "haiku")),
            read_jsonl(run_path("dev550", "page", "haiku")),
        )
        ITEMS.write_text(json.dumps(choose_items(joined, rows), indent=1) + "\n", encoding="utf-8")
    return json.loads(ITEMS.read_text(encoding="utf-8")), rows


def show(console: Console, row: Row, position: int, total: int) -> None:
    """Only the claim and the document."""
    console.print()
    console.rule(f"Item {position} of {total}")
    console.print(Panel(Text(row.claim), title="Claim", title_align="left"))
    console.print(Panel(Text(row.doc), title="Document", title_align="left"))


def run() -> None:
    console = Console()
    items, rows = load_items()
    labels = {x["row"]: x for x in read_jsonl(LABELS)}
    console.print(Panel(RUBRIC, title="How to label", title_align="left"))
    index = next((i for i, it in enumerate(items) if it["row"] not in labels), len(items))
    while index < len(items):
        row = rows[items[index]["row"]]
        show(console, row, index + 1, len(items))
        answer = console.input("[bold]y / n / u / b / q > [/bold]").strip().lower()
        if answer in KEYS:
            now = datetime.now(UTC).isoformat(timespec="seconds")
            labels[row.row] = {"row": row.row, "answer": KEYS[answer], "labelled_at": now}
            write_jsonl(LABELS, [labels[n] for n in sorted(labels)])
            index += 1
            if index == SPOT_CHECK and not all(it["row"] in labels for it in items):
                console.print(f"\nThat is the {SPOT_CHECK} for the spot-check, saved.")
                more = console.input("[bold]c to carry on, anything else to finish > [/bold]")
                if more.strip().lower() != "c":
                    break
        elif answer == "b" and index > 0:
            index -= 1
        elif answer == "q":
            break
    done = sum(it["row"] in labels for it in items)
    console.print(f"\n{done} of {len(items)} items labelled. Saved to {LABELS.name}.")
    if done == len(items):
        console.print("All done. Next: `uv run python -m evals partial-labels`.")


def tally(items: list[dict], labels: dict[int, dict], benchmark: dict[int, int]) -> dict[str, Any]:
    """Counts only. `benchmark` is each row's label from the benchmark (1 = supported)."""
    out: dict[str, Any] = {}
    for group in ("partial", "supported", "not_found"):
        mine = [it for it in items if it["group"] == group and it["row"] in labels]
        answers = Counter(labels[it["row"]]["answer"] for it in mine)
        decided = [it for it in mine if labels[it["row"]]["answer"] != "unsure"]
        agree = sum(
            (labels[it["row"]]["answer"] == "yes") == (benchmark[it["row"]] == 1) for it in decided
        )
        out[group] = {
            "labelled": len(mine),
            "answers": {k: answers[k] for k in ("yes", "no", "unsure")},
            "agrees_with_benchmark": agree,
            "decided": len(decided),
        }
    return out


def agreement(items: list[dict], mine: dict[int, dict], model: dict[int, dict]) -> dict[str, int]:
    """On items both answered yes or no: how often the person and the model give the same answer."""
    both = [
        it["row"]
        for it in items
        if it["row"] in mine
        and it["row"] in model
        and "unsure" not in (mine[it["row"]]["answer"], model[it["row"]]["answer"])
    ]
    same = sum(mine[r]["answer"] == model[r]["answer"] for r in both)
    return {"compared": len(both), "same": same}


def partial_decision(items: list[dict], labels: dict[int, dict]) -> dict[str, Any]:
    """D-039's rule: at least 60% "no" on the partial items means partial counts as a failure."""
    answers = [labels[it["row"]]["answer"] for it in items if it["group"] == "partial"]
    decided = [a for a in answers if a != "unsure"]
    share_no = sum(a == "no" for a in decided) / len(decided) if decided else None
    return {
        "partial_items_decided": len(decided),
        "share_no": None if share_no is None else round(share_no, 4),
        "partial_counts_as_a_failure": share_no is not None and share_no >= 0.60,
    }


def combined(
    items: list[dict], mine: dict[int, dict], model: dict[int, dict]
) -> tuple[dict, dict[str, Any]]:
    """Aditya's labels where he gave them; the model's elsewhere, only if the spot-check passed."""
    spot = agreement(items[:SPOT_CHECK], mine, model)
    passed = spot["compared"] == SPOT_CHECK and spot["same"] >= SPOT_CHECK_AGREEMENT
    labels = (model | mine) if passed else dict(mine)
    sources = {
        "by_aditya": sum(it["row"] in mine for it in items),
        "by_the_model": sum(it["row"] in labels and it["row"] not in mine for it in items),
    }
    return labels, {
        "spot_check": spot | {"needed": SPOT_CHECK_AGREEMENT, "passed": passed},
        **sources,
    }


def score() -> None:
    items, rows = load_items()
    mine = {x["row"]: x for x in read_jsonl(LABELS)}
    model = {x["row"]: x for x in read_jsonl(MODEL_LABELS)}
    benchmark = {n: r.label for n, r in rows.items()}
    labels, how = combined(items, mine, model)
    body = {
        "what": "Yes/no on 40 claims both judges called partial, plus 10 controls (D-039)",
        "items": len(items),
        "aditya": {"labeller": "Aditya (a person)"} | {"by_group": tally(items, mine, benchmark)},
        "model": {"labeller": "OpenAI Codex (AI)"} | {"by_group": tally(items, model, benchmark)},
        "agreement_aditya_and_model_all_items": agreement(items, mine, model),
        "used_for_the_decision": how | {"by_group": tally(items, labels, benchmark)},
        "decision": partial_decision(items, labels),
    }
    path = write_result("partial_labels", body)
    print(f"wrote {path.name}")
    print(json.dumps({k: body[k] for k in ("used_for_the_decision", "decision")}, indent=1))
