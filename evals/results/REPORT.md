# Evaluation report

Built by `python -m evals report` from the JSON files in this folder. Nothing here is typed by hand.

The corpus is a frozen set of openly licensed pages, mostly Wikipedia. Those pages are cleaner than the open web, so these scores are likely higher than real use would give.

## Retrieval

40 questions over 50 pages cut into 2362 passages. Scores are for the top 10 passages, with a 95% interval in brackets.

| Retriever | Recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|
| bm25 | 0.571 (0.463 to 0.675) | 0.537 (0.408 to 0.657) | 0.455 (0.363 to 0.545) |
| dense | 0.917 (0.850 to 0.967) | 0.740 (0.644 to 0.833) | 0.751 (0.675 to 0.821) |
| hybrid | 0.858 (0.775 to 0.925) | 0.682 (0.571 to 0.794) | 0.673 (0.591 to 0.751) |
| dense_rerank | 0.938 (0.883 to 0.979) | 0.816 (0.725 to 0.900) | 0.804 (0.739 to 0.863) |
| hybrid_rerank | 0.938 (0.883 to 0.979) | 0.817 (0.727 to 0.900) | 0.804 (0.740 to 0.863) |

Difference per question, second minus first:

| Comparison | Recall@10 | MRR@10 | nDCG@10 |
|---|---|---|---|
| dense minus bm25 | +0.346 (+0.250 to +0.454) | +0.204 (+0.083 to +0.324) | +0.296 (+0.225 to +0.376) |
| hybrid minus dense | -0.058 (-0.113 to -0.008) | -0.058 (-0.128 to +0.008) | -0.077 (-0.118 to -0.041) |
| hybrid_rerank minus hybrid | +0.079 (+0.025 to +0.142) | +0.134 (+0.040 to +0.238) | +0.131 (+0.083 to +0.189) |
| hybrid_rerank minus dense | +0.021 (-0.017 to +0.058) | +0.076 (+0.000 to +0.165) | +0.053 (+0.016 to +0.095) |
| hybrid_rerank minus dense_rerank | +0.000 (+0.000 to +0.000) | +0.001 (+0.000 to +0.002) | +0.000 (+0.000 to +0.001) |

Gold: Gold snippets were drafted by Claude from each question's pages and checked word for word against the page text. See evals/questions.jsonl.

## Does the checker agree with a person?

Not measured yet. This needs the hand labels: run `uv run python -m evals label`, then `uv run python -m evals agreement report`.

## Baseline against the full pipeline

For each claim, does the evidence the system points to back it? Baseline evidence is the cited passage; pipeline evidence is the quote. Judge: claude-opus-5-5 with the checker's rubric. Its agreement with hand labels is in checker_agreement.json.

| System | Fully backed | Main point backed | Claims per question | Questions with a fully backed claim |
|---|---|---|---|---|
| Baseline (one-shot RAG), all claims | 0.917 (0.877 to 0.953) | 1.000 (1.000 to 1.000) | 7.850 (7.675 to 7.975) | 1.000 (1.000 to 1.000) |
| Pipeline, claims labelled supported | 0.928 (0.895 to 0.961) | 1.000 (1.000 to 1.000) | 5.575 (5.100 to 6.050) | 0.975 (0.925 to 1.000) |
| Pipeline, all claims | 0.681 (0.611 to 0.748) | 1.000 (1.000 to 1.000) | 7.750 (7.550 to 7.925) | 0.975 (0.925 to 1.000) |

Fully backed, pipeline claims labelled supported minus baseline, per question: -0.013 (-0.060 to +0.032) over 40 questions.

Pipeline labels: {'supported': 223, 'partial': 87, 'unverified': 0}.

DeepEval faithfulness (stock metric, same judge model): baseline 1.000 (1.000 to 1.000), pipeline 1.000 (1.000 to 1.000).

## Nasty tests

Hand-made cases show behaviour on these cases only. This is evidence, not a security guarantee.

| Case | Passed |
|---|---|
| hidden_instructions | 5 of 5 |
| paywall | 5 of 5 |
| contradiction | 5 of 5 |

## What failed

- Retrieval, lowest recall with hybrid + rerank: q34 (0.33), q25 (0.50), q16 (0.67), q21 (0.67), q26 (0.67), q33 (0.67).
- 16 pipeline claims were labelled supported but the judge did not agree. The first few:
  - Mount Everest's height was most recently measured in 2020 by a joint Nepalese and Chinese survey as 8,848.86 m. (judge: partial; The quote backs the 2020 joint Nepalese–Chinese survey measuring the height as 8,848.86 m, but it refers only to "its" height and never names Mount Everest.)
  - Cas9 nickases, which are Cas9 active-site mutants, can induce single-strand nicks instead of double-strand breaks. (judge: partial; The quote says Cas9 active-site mutants, also called Cas9 nickases, can induce single-strand nicks, but it never says this happens instead of double-strand breaks.)
  - Before the explosion, nearly all of the 211 control rods had been withdrawn, leaving the reactor in an extremely unstable state. (judge: partial; The quote states nearly all 211 control rods were withdrawn and the reactor was left extremely unstable, but it never mentions an explosion, so the 'before the explosion' timing is not backed.)
  - The Kessler syndrome is a scenario proposed by NASA scientists Donald J. Kessler and Burton G. Cour-Palais in 1978. (judge: partial; The quote states that a scenario was proposed by NASA scientists Donald J. Kessler and Burton G. Cour-Palais in 1978, but it is cut off before the subject, so it never says that this scenario is the Kessler syndrome.)
  - UDP is lightweight and simple, with no ordering of messages and no tracking of connections. (judge: partial; The quote states that the protocol is lightweight and very simple, with no message ordering and no connection tracking, but it never names UDP as the protocol being described.)
