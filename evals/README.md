# Evals

Everything here answers one question: how often is Evidentia right, and how do we know?
The design decisions are D-016 to D-021 in `docs/DECISIONS.md`. Results are in `results/`, and
`results/REPORT.md` is built from them.

## Running

```
uv run python -m evals            # every step that needs no human; reuses saved model outputs
uv run python -m evals --fresh    # the same, but makes every model call again
uv run python -m evals report     # rebuild REPORT.md from saved results; free
```

On Linux or in CI, `make evals` does the first of these.

## Steps

| Step | What it does | Writes |
|---|---|---|
| `corpus` | Fetches any page named in `questions.jsonl` that is not saved yet | `corpus/pages/` |
| `gold` | Drafts gold snippets for questions that have none | `questions.jsonl` |
| `retrieval` | Scores five retrievers on the 40 questions | `results/retrieval.json` |
| `systems` | Answers the questions with the baseline and the full pipeline | `runs/` |
| `pairs` | Builds the 150 claim-and-quote pairs for hand labelling | `pairs.jsonl` |
| `label` | The hand-labelling tool | `labels.jsonl` |
| `agreement` | Compares three checker models with the hand labels | `results/checker_agreement.json` |
| `judge` | Scores both systems' claims with a separate judge model | `results/citation_accuracy.json` |
| `nasty` | Hidden instructions, a paywall, two contradicting pages | `results/nasty.json` |
| `report` | Builds the report | `results/REPORT.md` |

`pairs` refuses to rebuild once labelling has started, so labels always match their pairs.

## What is model-made and what is hand-made

- The 40 questions and their gold snippets were drafted by Claude and are checked word for word
  against the page text by code. They still need a person's review.
- The labels in `labels.jsonl` are made by hand, by one person.
- Every other number is computed by the code in this folder.
