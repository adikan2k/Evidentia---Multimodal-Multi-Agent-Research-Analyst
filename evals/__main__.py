"""Entry point: `python -m evals <step>`. With no step, runs every step that needs no human."""

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
    "systems": ("evals.systems", "run"),
    "pairs": ("evals.pairs", "run"),
    "label": ("evals.label", "run"),
    "agreement": ("evals.agreement", "run"),
    "judge": ("evals.judge", "run"),
    "nasty": ("evals.nasty", "run"),
    "report": ("evals.report", "run"),
}
# `label` is Aditya's step and `pairs` must not be rebuilt once labelling has started.
AUTOMATIC = ["corpus", "retrieval", "systems", "agreement", "judge", "nasty", "report"]


def run_step(name: str) -> None:
    module, function = STEPS[name]
    result = getattr(importlib.import_module(module), function)()
    if asyncio.iscoroutine(result):
        asyncio.run(result)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    steps = sys.argv[1:] or AUTOMATIC
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        raise SystemExit(f"Unknown step {unknown}. Choose from: {', '.join(STEPS)}")
    for step in steps:
        print(f"== {step}")
        run_step(step)


if __name__ == "__main__":
    main()
