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


def score() -> None:
    items, rows = load_items()
    labels = {x["row"]: x for x in read_jsonl(LABELS)}
    body = {
        "what": "Aditya's yes/no on claims both judges called partial, plus 10 controls",
        "labeller": "Aditya (a person)",
        "items": len(items),
        "by_group": tally(items, labels, {n: r.label for n, r in rows.items()}),
    }
    path = write_result("partial_labels", body)
    print(f"wrote {path.name}: {json.dumps(body['by_group'])}")
