# Evidentia

A research agent that backs every sentence with an exact quote, and checks each quote with code.

Ask a question. Evidentia searches the web, reads the pages (HTML and PDFs), and writes short
claims. Each claim carries a quote copied from a page. Code then checks that the quote is on the
page word for word, and a separate model, shown only the claim and the quote, judges whether the
quote backs the claim. Each claim ends up labelled **supported**, **partial** or **unverified**,
and you can open the quote in its place on the page.

- Site: https://evidentia-green.vercel.app (recorded runs, live runs, and the evaluation results)
- Decisions behind every part: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- Full evaluation report: [`evals/results/REPORT.md`](evals/results/REPORT.md)

## How a run works

```
plan → search → fetch → index → retrieve → write → quote check → check
                                                                   │
                     failed claims: new query → search the pages again → rewrite → check again
```

1. **Plan.** Claude Sonnet writes a few web search queries.
2. **Search and fetch.** Tavily returns addresses; Evidentia's own fetcher downloads them. It
   obeys robots.txt, waits between requests to the same site, and connects only to public
   addresses, checked after DNS resolution. PDFs are read page by page, so a quote from a PDF is
   cited to its page.
3. **Index and retrieve.** Pages are cut into passages, embedded with Voyage, stored in Qdrant,
   and reranked with Voyage's reranker.
4. **Write.** Sonnet writes claims, each with a quote and the source it came from. Page text is
   passed to the model inside marked data blocks and treated as data, never as instructions.
5. **Quote check (code).** A quote counts only if it is an exact span of the stored page text.
6. **Check (model).** An independent checker sees only the claim and the quote.
7. **Repair.** A claim that fails gets one more try: a new query, a fresh look through the
   fetched pages, and a rewrite, which is checked again from the start.

Every run has a hard cost cap in code and records tokens and dollars per step. Every model and
tool call is traced in Langfuse.

## Auditing another tool's answer

`python -m evidentia audit answer.md` checks the citations in an answer written by another AI
tool (D-037, D-038, D-039). The answer can use markdown links, bare addresses, or numbered
markers like `[1]` with a source list.

1. **Parse (code).** Finds every citation and where it sits in the answer.
2. **Split (Claude Haiku).** Breaks the answer into claims. Code checks that each claim's
   sentence is really in the answer, and code decides which pages it cites.
3. **Fetch (code).** The same fetcher as above.
4. **Two judges, at the same time, both Claude Haiku:**
   - **Quote judge.** Finds up to five quotes on the cited page that back or contradict the
     claim. Code checks that each is an exact span of the page. A separate call then sees only
     the claim and the quotes.
   - **Page judge.** Sees the claim and the page, and says whether the page supports it.
5. **Combine (code).** A claim gets a verdict only when the two judges agree. Otherwise it is
   labelled **needs a human**, with both judges' reasons.

The labels are: supported, partial, contradicted, not on the cited page, needs a human, dead
link (404, 410, or a name that does not resolve), could not check (for example, robots.txt
forbids it), and uncited.

Long pages are cut to the passages Voyage's reranker ranks highest. A page cited by several
claims is sent as a cached prompt prefix, so later claims about it read it cheaply.

Haiku is used for the judges because, on 550 practice rows, Sonnet was no better and cost 15
times as much per claim (`evals/results/aggrefact_dev550_q-sonnet_p-sonnet.json`).

### How the auditor compares with people's labels

LLM-AggreFact pairs claims with documents, each labelled supported or not by people.

**First version (D-037): one judge, quotes only.** On 550 of its test rows (50 from each of 11
sub-datasets), with Claude Haiku:

| System | Balanced accuracy | When it says supported, right | Supported rows it accepts | Unsupported rows it rejects |
|---|---|---|---|---|
| Auditor (exact quotes, then a check on the quotes alone) | 0.688 (0.646 to 0.728) | 0.915 | 0.523 | 0.916 |
| Plain yes/no on the whole document | 0.768 (0.721 to 0.811) | 0.910 | 0.730 | 0.876 |

That version agreed with people less than a plain yes/no did (difference −0.080, from −0.120 to
−0.038). It was stricter, not looser: it turned down about half the claims people accept.

**Current version (D-038, D-039): two judges.** It was tuned on 550 practice rows from the
benchmark's dev split, then run once on 550 test rows it had never seen
(`evals/results/aggrefact_test2_q-haiku_p-haiku.json`). Partial is counted as its own verdict,
not as a failure. The finish line was set before the run.

| On 550 unseen test rows | Flags right | When it says supported, right | Claims with a verdict |
|---|---|---|---|
| Two judges | 0.774 (0.720 to 0.828) | 0.910 (0.867 to 0.948) | 0.816 |
| Quote judge alone | 0.543 | 0.904 | 1.000 |
| Page judge alone | 0.660 | 0.892 | 1.000 |
| Finish line set in advance | at least 0.80 | at least 0.93 | at least 0.70 |

**It did not reach the finish line.** Flags right came in at 0.774 against 0.80, and "supported"
right at 0.910 against 0.93. On the practice rows the same setup had scored 0.810 and 0.940.

**Two judges still beat either one alone on flags.** About 77 of every 100 flags are right,
against 66 for the page judge alone and 54 for the quote judge alone. The price is that 18% of
claims get "needs a human" instead of a verdict.

**About partial.** On 17% of claims both judges agree a detail is not stated. The benchmark's
labellers accepted about half of those. No person checked them for this project, so partial is
reported apart and never counted as a failed citation. That way a count of failures is a lower
bound either way.

Cost: $0.00068 per claim for both judges together.

Full tables: `evals/results/REPORT.md`.

## What the evaluation found

Run on a frozen set of 50 openly licensed pages (mostly Wikipedia) and 40 questions. These pages
are cleaner than the open web, so real use would likely score lower. All numbers below are
copied from `evals/results/`, with 95% intervals.

**Accuracy is not better than plain RAG.** A judge model checked whether each claim's evidence
backs it:

| System | Claims shown as backed that are fully backed | Characters to read per claim | Cost per question |
|---|---|---|---|
| One-shot RAG baseline, Sonnet | 0.917 (0.877 to 0.953) | 1039 | $0.0141 |
| Evidentia pipeline, Sonnet | 0.928 (0.895 to 0.961) | 195 | $0.0401 |
| Evidentia pipeline, partial claims tightened (the default) | 0.925 (0.901 to 0.948) | 188 | $0.0491 |

The intervals overlap. What the pipeline adds is evidence you can check quickly (a short quote
instead of a whole passage) and a checker that catches mistakes, at a higher cost.

**The checker catches broken claims.** Of 50 claims broken on purpose (wrong quote, one fact
changed, or a detail added), the Sonnet checker passed 1 as supported, Haiku 2, Opus 0.

**Keyword search did not help retrieval here.** Dense search alone beat dense plus BM25 before
reranking (recall@10 0.917 against 0.858), and after reranking the two were equal (0.938 each).

**Hand-made attacks.** Hidden instructions in a page, paywalled pages, and contradictory pages:
5 of 5 passed in each case. That covers these cases only; it is not a security guarantee.

**Not done.** No person has labelled the checker's verdicts, so there is no agreement-with-a-human
figure; the only agreement figure is with a second model, which says little about correctness.

## Running it

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/), and Node 22 for the site. Keys come from
environment variables: `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `VOYAGE_API_KEY`, `QDRANT_URL`,
`QDRANT_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`.

```
uv sync
uv run python -m evidentia "How fast did global solar capacity grow in 2023?"
```

A run costs money (model, search and embedding calls) and stops at the cap set in
`evidentia/config.py`.

The site and the API:

```
uv run uvicorn evidentia.api:create_app --factory --port 8000
cd web && npm install && npm run dev
```

Tests and lint, no keys or money needed:

```
uv run pytest
uv run ruff check .
```

The evaluation is `uv run python -m evals`. It makes many model calls; see D-021 in the
decisions file before running it. `uv run python -m evals report` rebuilds the report from the
saved results for free.

Deployment (Cloud Run for the API, Vercel for the site) is in [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Layout

| Path | What it is |
|---|---|
| `evidentia/` | The pipeline, the fetcher, the quote check, the API |
| `evidentia/audit/` | The auditor for other tools' answers |
| `evals/` | The evaluation: corpus, questions, runs and results |
| `tests/` | Tests; they use fakes and make no paid calls |
| `web/` | The site (Next.js) |
| `docs/` | The plan, the decisions, the deployment steps |

## Not supported

Video and charts. YouTube's robots.txt disallows the addresses captions come from (D-032), and a
number read off a chart by a model has no exact text to check (D-033).

## Credits

Rebuilt in 2026 by Aditya Kanbargi. The first version of Evidentia (2025), by Aditya Kanbargi and
Sanjana Kadambe Muralidhar, is kept in the git history.

MIT licence; see [`LICENSE`](LICENSE).
