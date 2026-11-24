"""Record one real run as a replay file for the website.

    python -m evidentia.record my-run-id "The question to research"

Writes `web/public/replays/<id>.json`. It is a real run: it searches, fetches and calls the
models, and costs the same as `python -m evidentia`. The site then replays it for free.
"""

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from evidentia.__main__ import build_deps
from evidentia.config import load_settings
from evidentia.cost import Ledger
from evidentia.events import EventBuilder
from evidentia.graph import run_question
from evidentia.tracing import LangfuseTracer

REPLAYS_DIR = Path("web/public/replays")


async def record(replay_id: str, question: str) -> Path:
    settings = load_settings()
    ledger = Ledger(settings.cost_cap_usd)
    tracer = LangfuseTracer(settings)
    deps = build_deps(settings, ledger, tracer)
    builder = EventBuilder(ledger)
    events = []
    started = time.monotonic()

    def on_update(node: str, update: dict) -> None:
        seconds = round(time.monotonic() - started, 2)
        event = builder.node_event(node, update)
        events.append({"t": seconds} | event)
        print(f"  {seconds:>6}s  {node:<12}{event['summary']}")

    try:
        state = await run_question(question, deps, on_update)
    finally:
        await deps.fetcher.aclose()
        await deps.store.aclose()
        tracer.flush()

    replay = {
        "id": replay_id,
        "question": question,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "duration_s": round(time.monotonic() - started, 2),
        "models": {"writer": settings.writer_model, "checker": settings.checker_model},
        "events": events,
        "report": builder.report(state),
    }
    REPLAYS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPLAYS_DIR / f"{replay_id}.json"
    path.write_text(json.dumps(replay, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python -m evidentia.record <id> "<question>"')
    path = asyncio.run(record(sys.argv[1], sys.argv[2]))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
