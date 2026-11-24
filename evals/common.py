"""Paths, file helpers and the shared set-up for every evaluation."""

import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from evidentia.__main__ import build_deps
from evidentia.config import load_settings
from evidentia.cost import Ledger
from evidentia.graph import Deps
from evidentia.schemas import Source
from evidentia.tracing import LangfuseTracer

ROOT = Path(__file__).parent
PAGES_DIR = ROOT / "corpus" / "pages"
QUESTIONS = ROOT / "questions.jsonl"
RUNS_DIR = ROOT / "runs"
PAIRS = ROOT / "pairs.jsonl"
LABELS = ROOT / "labels.jsonl"  # made by a person with `python -m evals label`
MODEL_LABELS = ROOT / "labels_model.jsonl"  # made by a model; never reported as human
RESULTS_DIR = ROOT / "results"

# One cap for a whole evaluation command, on top of nothing else: evals make many calls.
EVAL_CAP_USD = float(os.environ.get("EVAL_CAP_USD", "15"))


class GoldSnippet(BaseModel):
    page: str
    text: str
    start: int
    end: int


class Question(BaseModel):
    id: str
    question: str
    kind: str  # "factual" or "contested"
    pages: list[str]
    gold: list[GoldSnippet] = []


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_result(name: str, body: dict[str, Any]) -> Path:
    """Every reported number lives in a file written here."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    stamped = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds")} | body
    path.write_text(json.dumps(stamped, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_questions() -> list[Question]:
    return [Question(**row) for row in read_jsonl(QUESTIONS)]


def save_questions(questions: list[Question]) -> None:
    write_jsonl(QUESTIONS, [q.model_dump() for q in questions])


def load_pages() -> dict[str, dict[str, Any]]:
    """Saved pages by id."""
    pages = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PAGES_DIR.glob("*.json"))]
    return {page["id"]: page for page in pages}


def corpus_sources() -> list[Source]:
    return [
        Source(id=p["id"], url=p["url"], title=p["title"], text=p["text"])
        for p in load_pages().values()
    ]


@asynccontextmanager
async def eval_deps(span_name: str, **setting_overrides: Any):
    """Real services with tracing on and one cost cap for the whole command."""
    settings = load_settings(cost_cap_usd=EVAL_CAP_USD, **setting_overrides)
    tracer = LangfuseTracer(settings)
    deps: Deps = build_deps(settings, Ledger(settings.cost_cap_usd), tracer)
    try:
        with tracer.span(span_name, "span"):
            yield deps
    finally:
        await deps.fetcher.aclose()
        await deps.store.aclose()
        tracer.flush()
