"""Record one real audit for the website (D-041).

    python -m evidentia.audit.record <id> "<question>"

Asks OpenAI's model, with web search, to answer the question; then audits that answer with the
real auditor, and writes `web/public/audits/<id>.json`. The site replays it for free. It costs
the answer (a few cents) plus the audit (about a cent).
"""

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from evidentia.audit.answers import answer_with_web_search
from evidentia.audit.cli import build_audit_deps
from evidentia.audit.events import AuditEventBuilder
from evidentia.audit.graph import run_audit
from evidentia.config import load_settings
from evidentia.cost import Ledger
from evidentia.tracing import LangfuseTracer

AUDITS_DIR = Path("web/public/audits")
ANSWER_CAP_USD = 0.25


async def record(audit_id: str, question: str, reuse: bool = False) -> Path:
    """`reuse` audits the answer already saved for `audit_id` again, without asking OpenAI."""
    settings = load_settings()
    tracer = LangfuseTracer(settings)
    answer_ledger = Ledger(ANSWER_CAP_USD)
    ledger = Ledger(settings.audit_cap_usd)
    deps = build_audit_deps(settings, ledger, tracer)
    builder = AuditEventBuilder(ledger)
    events = []
    try:
        with tracer.span("evidentia.record_audit", "span", {"id": audit_id, "question": question}):
            saved = AUDITS_DIR / f"{audit_id}.json"
            if reuse:
                answer = json.loads(saved.read_text(encoding="utf-8"))["answer"] | {"citations": 0}
            else:
                answer = await answer_with_web_search(question, settings, answer_ledger)
            print(
                f"  answer from {answer['model']}: {answer['citations']} cited pages, "
                f"${answer['usd']:.4f}"
            )
            started = time.monotonic()

            def on_update(node: str, update: dict) -> None:
                seconds = round(time.monotonic() - started, 2)
                event = builder.node_event(node, update)
                events.append({"t": seconds} | event)
                print(f"  {seconds:>6}s  {node:<12}{event['summary']}")

            state = await run_audit(answer["text"], deps, on_update)
    finally:
        await deps.fetcher.aclose()
        tracer.flush()
    recorded = {
        "id": audit_id,
        "question": question,
        "answer": {k: answer[k] for k in ("model", "tool", "made_at", "text", "usd")},
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "duration_s": round(time.monotonic() - started, 2),
        "judges": {
            "quote": settings.audit_checker_model,
            "finder": settings.finder_model,
            "page": settings.page_judge_model,
        },
        "events": events,
        "report": builder.report(state),
    }
    AUDITS_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDITS_DIR / f"{audit_id}.json"
    path.write_text(json.dumps(recorded, indent=1, ensure_ascii=False), encoding="utf-8")
    write_index()
    return path


def write_index() -> None:
    """The list of recorded audits the site offers, rebuilt from the files that exist."""
    audits = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(AUDITS_DIR.glob("*.json"))
        if p.name != "index.json"
    ]
    index = [
        {"id": a["id"], "question": a["question"], "model": a["answer"]["model"]} for a in audits
    ]
    (AUDITS_DIR / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if a != "--reuse"]
    if len(args) != 2:
        raise SystemExit('Usage: python -m evidentia.audit.record <id> "<question>" [--reuse]')
    path = asyncio.run(record(args[0], args[1], reuse="--reuse" in sys.argv))
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
