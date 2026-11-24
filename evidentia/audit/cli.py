"""Command line entry: python -m evidentia audit answer.md (or - to read the answer from stdin)."""

import argparse
import sys
from pathlib import Path

from langgraph.errors import NodeTimeoutError
from rich.console import Console
from rich.text import Text

from evidentia.audit.graph import AuditDeps, run_audit
from evidentia.audit.report import AuditReporter, to_json
from evidentia.config import ConfigError, Settings, load_settings
from evidentia.cost import BudgetExceeded, Ledger
from evidentia.embed import Embedder
from evidentia.fetch import Fetcher
from evidentia.llm import LLM, ModelStopped
from evidentia.tracing import LangfuseTracer, Tracer

EXIT_OK, EXIT_RUN_FAILED, EXIT_BAD_CONFIG, EXIT_BAD_INPUT = 0, 1, 2, 3
MAX_ANSWER_CHARS = 40_000


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evidentia audit", description="Check the citations in an AI tool's answer."
    )
    parser.add_argument("answer", help="a text or markdown file with the answer, or - for stdin")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--cap", type=float, help="cost cap for this audit in US dollars")
    return parser.parse_args(argv)


def read_answer(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def build_audit_deps(settings: Settings, ledger: Ledger, tracer: Tracer) -> AuditDeps:
    return AuditDeps(
        settings=settings,
        ledger=ledger,
        tracer=tracer,
        llm=LLM(settings, ledger),
        fetcher=Fetcher(settings, tracer),
        embedder=Embedder(settings, ledger, tracer),
    )


async def amain(argv: list[str]) -> int:
    args = parse_args(argv)
    console = Console(stderr=args.json)
    try:
        answer = read_answer(args.answer)
    except OSError as err:
        console.print(Text(f"Could not read {args.answer}: {err.strerror}", style="bold red"))
        return EXIT_BAD_INPUT
    if not answer.strip() or len(answer) > MAX_ANSWER_CHARS:
        console.print(
            Text(f"The answer must be 1 to {MAX_ANSWER_CHARS:,} characters.", style="bold red")
        )
        return EXIT_BAD_INPUT
    try:
        settings = load_settings()
        tracer = LangfuseTracer(settings)
    except ConfigError as err:
        console.print(Text(str(err), style="bold red"))
        return EXIT_BAD_CONFIG

    ledger = Ledger(args.cap if args.cap is not None else settings.audit_cap_usd)
    deps = build_audit_deps(settings, ledger, tracer)
    reporter = AuditReporter(console)
    try:
        state = await run_audit(answer, deps, reporter.on_update)
    except (BudgetExceeded, ModelStopped, NodeTimeoutError) as err:
        console.print(Text(f"Audit stopped: {err}", style="bold red"))
        return EXIT_RUN_FAILED
    finally:
        await deps.fetcher.aclose()
        tracer.flush()

    if args.json:
        print(to_json(state, ledger))
    else:
        reporter.final(state, ledger)
    return EXIT_OK
