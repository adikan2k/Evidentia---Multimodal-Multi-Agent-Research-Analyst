"""The hand-labelling tool. Run: `uv run python -m evals label`.

It shows one claim and one quote at a time and nothing else: not the checker's answer and not
whether the pair is real or built. You can stop at any point; labels are saved after every answer.
"""

from datetime import UTC, datetime

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from evals.common import LABELS, PAIRS, read_jsonl, write_jsonl

KEYS = {"s": "supported", "p": "partial", "u": "unsupported"}

RUBRIC = """Judge only from the words of the quote. Do not use what you know about the topic.

  s  supported    The quote on its own states everything the claim says. Rewording is fine,
                  but every number, date, name, place, comparison and cause must be in the quote.
  p  partial      The quote backs the claim's main point, but the claim adds at least one
                  specific that the quote does not state.
  u  unsupported  The quote does not back the main point, contradicts it, or is about
                  something else.

  b  go back one pair        q  save and quit"""


def save(labels: dict[str, dict]) -> None:
    write_jsonl(LABELS, [labels[key] for key in sorted(labels)])


def show(console: Console, pair: dict, position: int, total: int) -> None:
    console.print()
    console.rule(f"Pair {position} of {total}")
    console.print(Panel(Text(pair["claim"]), title="Claim", title_align="left"))
    console.print(Panel(Text(pair["quote"]), title="Quote", title_align="left"))


def run() -> None:
    console = Console()
    pairs = read_jsonl(PAIRS)
    if not pairs:
        console.print("No pairs yet. Run `uv run python -m evals pairs` first.")
        return
    labels = {row["id"]: row for row in read_jsonl(LABELS)}
    console.print(Panel(RUBRIC, title="How to label", title_align="left"))
    index = next((i for i, p in enumerate(pairs) if p["id"] not in labels), len(pairs))
    while index < len(pairs):
        pair = pairs[index]
        show(console, pair, index + 1, len(pairs))
        answer = console.input("[bold]s / p / u / b / q > [/bold]").strip().lower()
        if answer in KEYS:
            now = datetime.now(UTC).isoformat(timespec="seconds")
            labels[pair["id"]] = {"id": pair["id"], "label": KEYS[answer], "labelled_at": now}
            save(labels)
            index += 1
        elif answer == "b" and index > 0:
            index -= 1
        elif answer == "q":
            break
    done = sum(p["id"] in labels for p in pairs)
    console.print(f"\n{done} of {len(pairs)} pairs labelled. Saved to {LABELS}.")
    if done == len(pairs):
        console.print("All done. Next: `uv run python -m evals agreement report`.")
