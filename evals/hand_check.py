"""A person checks a sample of the real-world audit's verdicts (D-044).

    uv run python -m evals hand-check          # Aditya labels; stop and resume at any time
    uv run python -m evals hand-check-score    # free: writes realworld_hand_check.json
    uv run python -m evals hand-check-2        # the second check, on the D-049 audits
    uv run python -m evals hand-check-2-score  # free: writes realworld_hand_check_2.json

40 own-cited claims: from each tool, 10 the auditor failed outright and 10 it called supported.
The screen shows the claim and opens the cited page. It does not show which tool wrote the
answer, the auditor's verdict, the quotes or the judges' reasons.

The labels file is written only by the interactive command below. No model fills it.
"""

import json
import math
import random
import re
import time
import webbrowser
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from evals.common import read_jsonl, write_jsonl, write_result
from evals.realworld import FAILED, HERE, REST, TOOLS, audit_path, load, load_questions

ITEMS = HERE / "hand_check_items.json"  # the sample, fixed and committed before any label
LABELS = HERE / "hand_check_labels.jsonl"  # made by a person; never by a model
SEED = 20261201
PER_GROUP = 10  # per tool: 10 failed and 10 supported, so 40 items in all
JUDGE = "haiku"  # the page judge as shipped
KEYS = {"y": "yes", "n": "no", "u": "unsure", "x": "would_not_open"}
UPHELD_NEEDED = 0.70  # D-044: below this, the findings page makes no comparison


@dataclass(frozen=True)
class Check:
    result: str  # the result file's name
    items: Path
    labels: Path
    seed: int
    audits: Path  # where the audits the sample is drawn from are
    # D-049: also withhold when one tool's interval for flags upheld lies wholly below the line.
    per_tool_guard: bool = False
    leave_out: Path | None = None  # an earlier check's items, already seen by the labeller


FIRST = Check("realworld_hand_check", ITEMS, LABELS, SEED, HERE)
# D-049: fixed before any label of this check.
SECOND = Check(
    "realworld_hand_check_2",
    HERE / "hand_check_2_items.json",
    HERE / "hand_check_2_labels.jsonl",
    20261204,
    REST,
    per_tool_guard=True,
    leave_out=ITEMS,
)

RUBRIC = """The cited page opens in your browser. Read it, then answer for the claim shown.
Judge only from the page, not from what you know.

  y  yes     The page states everything the claim says. Rewording is fine, and so is putting
             together what different parts of the page say.
  n  no      At least one part of the claim (a number, date, name, place, event or detail) is
             not on the page, or the page says otherwise.
  u  unsure  You cannot tell.
  x          The page would not open, or shows nothing to read.

  o  open the page again     b  go back one item     q  save and quit"""

# Things that would show which tool wrote the answer: link text such as "(nasa.gov)" and
# numbered markers such as "[2]" left in a claim, and tracking parameters on an address.
SITE_IN_BRACKETS = re.compile(r"\s*\(\s*(?:[\w-]+\.)+[a-z]{2,}\s*\)")
MARKER = re.compile(r"\s*\[\^?\d+(?:\s*,\s*\d+)*\]")


def neutral_claim(claim: str) -> str:
    return MARKER.sub("", SITE_IN_BRACKETS.sub("", claim)).strip()


def neutral_url(url: str) -> str:
    """The address without `utm_...` tracking parameters, which name the tool that cited it."""
    parts = urlsplit(url)
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith("utm_")
    ]
    return urlunsplit(parts._replace(query=urlencode(kept)))


def seen_sentences(items_file: Path) -> set[tuple[str, str, str]]:
    """(tool, question, sentence) for each item of an earlier check, from the audits it used."""
    seen = set()
    for it in json.loads(items_file.read_text(encoding="utf-8")):
        tool, qid, index = it["item"].split(":")
        audit = load(audit_path(JUDGE, tool, qid))
        if audit:
            seen.add((tool, qid, audit["report"]["claims"][int(index)]["sentence"]))
    return seen


def candidates(
    audits: Path = HERE, leave_out: set[tuple[str, str, str]] = frozenset()
) -> dict[tuple[str, str], list[dict]]:
    """Every own-cited claim the auditor failed or supported, by (tool, group).

    Claims from a sentence in `leave_out` are left out: the labeller has seen that sentence.
    """
    pools: dict[tuple[str, str], list[dict]] = {}
    for tool in TOOLS:
        for q in load_questions("all"):
            audit = load(audit_path(JUDGE, tool, q["id"], audits))
            for index, claim in enumerate(audit["report"]["claims"] if audit else []):
                if claim.get("cited_by") != "sentence":
                    continue
                if (tool, q["id"], claim["sentence"]) in leave_out:
                    continue
                group = "failed" if claim["label"] in FAILED else claim["label"]
                if group not in ("failed", "supported"):
                    continue
                pools.setdefault((tool, group), []).append(
                    {
                        "item": f"{tool}:{q['id']}:{index}",
                        "tool": tool,
                        "group": group,
                        "auditor_label": claim["label"],
                        "claim": neutral_claim(claim["claim"]),
                        "urls": [neutral_url(p["url"]) for p in claim["pages"]],
                    }
                )
    return pools


def choose_items(pools: dict[tuple[str, str], list[dict]], seed: int = SEED) -> list[dict]:
    """10 from each of the four groups, in blocks of four: one from each group, shuffled.

    So stopping after any block leaves a balanced sample.
    """
    rng = random.Random(seed)
    picked = {
        key: rng.sample(sorted(pool, key=lambda x: x["item"]), PER_GROUP)
        for key, pool in sorted(pools.items())
    }
    items = []
    for n in range(PER_GROUP):
        block = [picked[key][n] for key in sorted(picked)]
        rng.shuffle(block)
        items += block
    return items


def load_items(check: Check = FIRST) -> list[dict]:
    """The check's fixed sample, drawn and written once, before its first label."""
    if not check.items.exists():
        seen = seen_sentences(check.leave_out) if check.leave_out else frozenset()
        chosen = choose_items(candidates(check.audits, seen), check.seed)
        check.items.write_text(
            json.dumps(chosen, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return json.loads(check.items.read_text(encoding="utf-8"))


def show(console: Console, item: dict, position: int, total: int) -> None:
    """Only the claim and the address. Never the tool, the verdict or the quotes."""
    console.print()
    console.rule(f"Item {position} of {total}")
    console.print(Panel(Text(item["claim"]), title="Claim", title_align="left"))
    for url in item["urls"]:
        console.print(Text(f"  Cited page: {url}", style="blue"))


def open_pages(item: dict) -> None:
    for url in item["urls"]:
        webbrowser.open(url)


def run(check: Check = FIRST) -> None:
    console = Console()
    items = load_items(check)
    labels = {x["item"]: x for x in read_jsonl(check.labels)}
    console.print(Panel(RUBRIC, title="How to check", title_align="left"))
    index = next((i for i, it in enumerate(items) if it["item"] not in labels), len(items))
    while index < len(items):
        item = items[index]
        show(console, item, index + 1, len(items))
        open_pages(item)
        started = time.monotonic()
        while True:
            answer = console.input("[bold]y / n / u / x   (o, b, q) > [/bold]").strip().lower()
            if answer == "o":
                open_pages(item)
                continue
            break
        if answer in KEYS:
            labels[item["item"]] = {
                "item": item["item"],
                "answer": KEYS[answer],
                "labelled_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "seconds": round(time.monotonic() - started, 1),
            }
            write_jsonl(check.labels, [labels[it["item"]] for it in items if it["item"] in labels])
            index += 1
        elif answer == "b" and index > 0:
            index -= 1
        elif answer == "q":
            break
    done = sum(it["item"] in labels for it in items)
    console.print(f"\n{done} of {len(items)} items checked. Saved to {check.labels.name}.")
    if done:
        score_cmd = "hand-check-score" if check == FIRST else "hand-check-2-score"
        console.print(f"To see the result: `uv run python -m evals {score_cmd}`.")


# Scoring.


def wilson(hits: int, n: int) -> dict[str, Any]:
    """A share with its 95% Wilson interval, which behaves well for small samples."""
    if n == 0:
        return {"hits": 0, "n": 0, "share": None, "ci_low": None, "ci_high": None}
    z = 1.96
    p = hits / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return {
        "hits": hits,
        "n": n,
        "share": round(p, 4),
        "ci_low": round(max(centre - half, 0.0), 4),
        "ci_high": round(min(centre + half, 1.0), 4),
    }


def upheld(items: list[dict], labels: dict[str, dict], group: str, tool: str | None) -> dict:
    """Of the `group` claims answered yes or no, how many the person agrees with the auditor on.

    A failed claim is upheld by "no" (it is not on the page); a supported one by "yes".
    """
    agree_with = "no" if group == "failed" else "yes"
    answers = [
        labels[it["item"]]["answer"]
        for it in items
        if it["group"] == group and (tool is None or it["tool"] == tool) and it["item"] in labels
    ]
    decided = [a for a in answers if a in ("yes", "no")]
    return wilson(sum(a == agree_with for a in decided), len(decided)) | {
        "unsure": answers.count("unsure"),
        "would_not_open": answers.count("would_not_open"),
    }


def rule(flags: dict[str, dict], per_tool_guard: bool) -> dict[str, Any]:
    """D-044's rule, and for the second check D-049's guard for each tool."""
    both = flags["both_tools"]
    met = both["share"] is not None and both["share"] >= UPHELD_NEEDED
    body: dict[str, Any] = {"flags_upheld_needed_both_tools": UPHELD_NEEDED}
    if per_tool_guard:
        tripped = [
            t
            for t in TOOLS
            if flags[t]["ci_high"] is not None and flags[t]["ci_high"] < UPHELD_NEEDED
        ]
        body["per_tool_guard"] = {"tools_clearly_below": tripped}
        met = met and not tripped
    return body | {"met": met}


def summarise(
    items: list[dict], labels: dict[str, dict], per_tool_guard: bool = False
) -> dict[str, Any]:
    done = [it for it in items if it["item"] in labels]
    flags_all = {"both_tools": upheld(items, labels, "failed", None)} | {
        tool: upheld(items, labels, "failed", tool) for tool in TOOLS
    }
    disagreements = [
        {"item": it["item"], "auditor": it["auditor_label"], "person": labels[it["item"]]["answer"]}
        for it in done
        if labels[it["item"]]["answer"] == ("yes" if it["group"] == "failed" else "no")
    ]
    seconds = [labels[it["item"]]["seconds"] for it in done]
    return {
        "what": "Aditya's own check of the auditor's verdicts on real answers (D-044)",
        "labeller": "Aditya (a person)",
        "items_in_sample": len(items),
        "items_checked": len(done),
        "median_seconds_per_item": round(median(seconds), 1) if seconds else None,
        "flags_upheld": flags_all,
        "supported_upheld": {"both_tools": upheld(items, labels, "supported", None)}
        | {tool: upheld(items, labels, "supported", tool) for tool in TOOLS},
        "rule": rule(flags_all, per_tool_guard),
        "disagreements": disagreements,
    }


def score(check: Check = FIRST) -> None:
    items = load_items(check)
    labels = {x["item"]: x for x in read_jsonl(check.labels)}
    if not labels:
        print("No labels yet. Run the hand-check command first.")
        return
    body = summarise(items, labels, check.per_tool_guard)
    if check != FIRST:
        body |= {"audits": "D-049 re-audit, reader: article and rest of page"}
    path = write_result(check.result, body)
    print(f"wrote {path.name}")
    print(
        json.dumps(
            {k: body[k] for k in ("items_checked", "flags_upheld", "supported_upheld", "rule")},
            indent=1,
        )
    )


def run_second() -> None:
    run(SECOND)


def score_second() -> None:
    score(SECOND)


def draw_second() -> None:
    """Fix the second check's sample and say how it was drawn. Free; no labels involved."""
    items = load_items(SECOND)
    groups = {(it["tool"], it["group"]) for it in items}
    print(f"{len(items)} items in {SECOND.items.name}, {len(groups)} groups, seed {SECOND.seed}")
