"""Command line entry: python -m evidentia "your question", or python -m evidentia audit FILE."""

import argparse
import asyncio
import sys

from langgraph.errors import NodeTimeoutError
from rich.console import Console
from rich.text import Text

from evidentia.config import ConfigError, Settings, load_settings
from evidentia.cost import BudgetExceeded, Ledger
from evidentia.embed import Embedder
from evidentia.fetch import Fetcher
from evidentia.graph import Deps, run_question
from evidentia.llm import LLM, ModelStopped
from evidentia.report import Reporter, to_json
from evidentia.search import Searcher
from evidentia.store import Store
from evidentia.tracing import LangfuseTracer, Tracer

EXIT_OK, EXIT_RUN_FAILED, EXIT_BAD_CONFIG = 0, 1, 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evidentia", description="Answer a question with claims you can check."
    )
    parser.add_argument("question", nargs="+", help="the question to research")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--cap", type=float, help="cost cap for this run in US dollars")
    args = parser.parse_args(argv)
    args.question = " ".join(args.question)
    return args


def build_deps(settings: Settings, ledger: Ledger, tracer: Tracer) -> Deps:
    return Deps(
        settings=settings,
        ledger=ledger,
        tracer=tracer,
        llm=LLM(settings, ledger),
        searcher=Searcher(settings, ledger, tracer),
        fetcher=Fetcher(settings, tracer),
        embedder=Embedder(settings, ledger, tracer),
        store=Store(settings, tracer),
    )


async def amain(args: argparse.Namespace) -> int:
    # With --json the result goes to stdout alone, so progress moves to stderr.
    console = Console(stderr=args.json)
    reporter = Reporter(console)
    try:
        settings = load_settings(**({"cost_cap_usd": args.cap} if args.cap is not None else {}))
        tracer = LangfuseTracer(settings)
    except ConfigError as err:
        console.print(Text(str(err), style="bold red"))
        return EXIT_BAD_CONFIG

    ledger = Ledger(settings.cost_cap_usd)
    deps = build_deps(settings, ledger, tracer)
    try:
        state = await run_question(args.question, deps, reporter.on_update)
    except (BudgetExceeded, ModelStopped, NodeTimeoutError) as err:
        console.print(Text(f"Run stopped: {err}", style="bold red"))
        reporter.costs(ledger)
        return EXIT_RUN_FAILED
    finally:
        await deps.fetcher.aclose()
        await deps.store.aclose()
        tracer.flush()

    if args.json:
        print(to_json(state, ledger))
    else:
        reporter.final(state, ledger)
    return EXIT_OK


def main() -> None:
    # Windows consoles default to a legacy code page; pages and quotes need UTF-8.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    if argv[:1] == ["audit"]:  # a question that starts with the word "audit" must be quoted
        from evidentia.audit.cli import amain as audit_main

        raise SystemExit(asyncio.run(audit_main(argv[1:])))
    raise SystemExit(asyncio.run(amain(parse_args(argv))))


if __name__ == "__main__":
    main()
