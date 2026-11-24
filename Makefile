# On Windows without make, run the command on the right-hand side directly.

.PHONY: test lint evals report

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check evidentia evals tests

# Full evaluation. Needs the service keys and costs money (see docs/DECISIONS.md, D-021).
# `make evals ARGS=--fresh` ignores saved model outputs and makes every call again.
evals:
	uv run python -m evals $(ARGS)

# Rebuild evals/results/REPORT.md from the saved result files. Free.
report:
	uv run python -m evals report
