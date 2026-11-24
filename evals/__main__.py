"""Entry point: `python -m evals <step>`. With no step, runs every step that needs no human.

`python -m evals aggrefact --help` is the LLM-AggreFact run (D-037), started only by hand.

Saved model outputs in `evals/runs/` are reused, so a second run only pays for what is missing.
`--fresh` deletes them first, which makes every model call again.
"""

import asyncio
import importlib
import os
import sys

# DeepEval sends usage telemetry and reads .env files unless told not to. Set before it loads.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")
os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")

# step name -> (module, function). Modules are imported only when their step runs.
STEPS = {
    "corpus": ("evals.corpus", "fetch_pages"),
    "gold": ("evals.corpus", "draft_gold"),
    "retrieval": ("evals.retrieval", "run"),
    "unanswerable": ("evals.unanswerable", "run"),
    "systems": ("evals.systems", "run"),
    "pairs": ("evals.pairs", "run"),
    "label": ("evals.label", "run"),
    "agreement": ("evals.agreement", "run"),
    "judge": ("evals.judge", "run"),
    "nasty": ("evals.nasty", "run"),
    "report": ("evals.report", "run"),
}
# `label` is Aditya's step and `pairs` must not be rebuilt once labelling has started.
AUTOMATIC = [
    "corpus",
    "retrieval",
    "unanswerable",
    "systems",
    "agreement",
    "judge",
    "nasty",
    "report",
]


def run_step(name: str) -> None:
    module, function = STEPS[name]
    result = getattr(importlib.import_module(module), function)()
    if asyncio.iscoroutine(result):
        asyncio.run(result)


def forget_saved_outputs() -> None:
    from evals.common import RUNS_DIR

    for path in [*RUNS_DIR.glob("*.jsonl"), RUNS_DIR / "cost.json"]:
        path.unlink(missing_ok=True)
    print("fresh: deleted saved model outputs in evals/runs/")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if args[:1] == ["aggrefact"]:  # has its own options; never part of the automatic steps
        from evals.aggrefact import main as aggrefact

        aggrefact(args[1:])
        return
    if "--fresh" in args:
        args.remove("--fresh")
        forget_saved_outputs()
    steps = args or AUTOMATIC
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        raise SystemExit(f"Unknown step {unknown}. Choose from: {', '.join(STEPS)}")
    for step in steps:
        print(f"== {step}")
        run_step(step)


if __name__ == "__main__":
    main()
