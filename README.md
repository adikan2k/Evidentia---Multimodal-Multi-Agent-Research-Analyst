# Evidentia

An auditor for AI answers. Paste an answer with its sources, and Evidentia checks whether each
cited page says what the answer says it does.

Every claim in the answer is checked twice against the page it cites: once against exact quotes
that code has found on the page word for word, and once against the page as a whole. A claim
gets a verdict only when the two checks agree. When they disagree, it is labelled **needs a
human**. Beside every result, the site shows how often the auditor itself is right, measured on
claims that people labelled.

- Site: https://evidentia-green.vercel.app/audit (paste an answer, or watch a recorded audit)
- Decisions behind every part: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- Full evaluation report: [`evals/results/REPORT.md`](evals/results/REPORT.md)

Evidentia began as a research agent that backs each sentence with an exact quote. That agent is
still here, in the second half of this page. Its own evaluation found it no more accurate than
plain RAG, and that result is why the project turned to auditing (D-034).

## How an audit works

On the site's Audit page, or with `python -m evidentia audit answer.md`. The answer can use
markdown links, bare addresses, or numbered markers like `[1]` with a source list, whether the
list is on separate lines or has lost its line breaks in the paste.

1. **Parse (code).** Finds every citation and where it sits in the answer.
2. **Split (Claude Haiku).** Breaks the answer into claims. Code checks that each claim's
   sentence is really in the answer, and code decides which pages it cites.
3. **Fetch (code).** Evidentia's own fetcher downloads each cited page. It obeys robots.txt,
   waits between requests to the same site, and connects only to public addresses, checked
   after DNS resolution. PDFs are read page by page.
4. **Two judges, at the same time, both Claude Haiku:**
   - **Quote judge.** Finds up to five quotes on the cited page that back or contradict the
     claim. Code checks that each is an exact span of the page. A separate call then sees only
     the claim and the quotes.
   - **Page judge.** Sees the claim and the page, and says whether the page supports it.
5. **Combine (code).** A claim gets a verdict only when the two judges agree. Otherwise it is
   labelled **needs a human**, with both judges' reasons.

The labels are:

| Label | Meaning |
|---|---|
| supported | both judges agree the cited page states the claim |
| partial | the page backs the main point but not every detail; never counted as a failure |
| contradicted | the page says something that cannot be true along with the claim |
| not on the cited page | both judges agree the page does not state it |
| needs a human | the two judges disagree |
| dead link | the address answers 404 or 410, or its name does not resolve |
| could not check | the page was not read: robots.txt, a refusal, too little text, a time-out |
| could not read the citation | the sentence has a marker such as `[7]`, but no source matches it |
| uncited | no citation in the sentence or its paragraph |

A sentence with no citation of its own takes the one that closes its paragraph, and is marked as
cited that way.

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

**Current version (D-038 to D-040): two judges.** It was tuned on 550 practice rows from the
benchmark's dev split, then measured on 1,100 rows never used to tune it: 550 more dev rows
and 550 test rows (`evals/results/aggrefact_pooled-dev550b+test2_q-haiku_p-haiku.json`).
Partial is counted as its own verdict, not as a failure.

| On 1,100 untouched rows | Flags right | When it says supported, right | Claims with a verdict |
|---|---|---|---|
| Two judges | 0.806 (0.767 to 0.844) | 0.926 (0.897 to 0.951) | 0.823 |
| Quote judge alone | 0.560 | 0.913 | 1.000 |
| Page judge alone | 0.681 | 0.918 | 1.000 |

For a single judge, "flags" means every claim it does not call supported.

- **Two judges beat either one alone.** About 81 of every 100 flags are right, against 68 for the
  better single judge. The price is that 18% of claims get "needs a human" instead of a verdict.
- **A finish line was set before the test run** (flags right at least 0.80, supported right at
  least 0.93). On the 550 test rows alone it was missed: 0.773 and 0.910
  (`aggrefact_test2_q-haiku_p-haiku.json`). On the 550 dev rows it was met. Three samples of 550
  rows gave flags right of 0.810, 0.839 and 0.773, so a single sample of that size cannot settle
  a bar this close. The pooled figures above are the better estimate, and both bars lie inside
  their intervals.
- **What else was tried, and dropped by rules set in advance.** Sonnet as the judges, a judge from
  OpenAI, more votes, token probabilities, quote context, extra checker rules, and a graded page
  judge. None held up on rows it had not been tuned on (`docs/DECISIONS.md`, D-038 to D-040).
- **About partial.** On 18% of claims, both judges agree a detail is not stated. The benchmark's
  labellers accepted about half of those. No person checked them for this project, so partial is
  reported apart and never counted as a failed citation. That way, a count of failures is a
  lower bound either way.

Cost: $0.00069 per claim for both judges together.

Full tables: `evals/results/REPORT.md`.

### The real-world audit, and a hand check it did not pass

OpenAI's `gpt-6.2-sol` and Claude Sonnet 5.5, each with web search on, answered the same 100
fixed questions, and Evidentia audited every answer (D-042 to D-047). Before publishing a
comparison, Aditya checked a blind sample of the auditor's verdicts against the live pages
(D-044). He saw each claim and its cited page, and not which tool wrote it or what the auditor
said.

| Hand check, 40 claims | Upheld | 95% interval |
|---|---|---|
| Flags (not on the cited page, or contradicted) | 54%, 7 of the 13 he could settle | 29% to 77% |
| "Supported" | 84%, 16 of 19 | 62% to 94% |

He was unsure on 7 of the 20 flags. The rule, fixed before the first label, was that at least
70% of flags must be upheld for the two tools to be compared. They were not, so neither this
README nor the site compares them. On the benchmark above, 81% of the auditor's flags are right;
on real answers and live pages, fewer are, and why is not yet known.

The questions, answers, audits, labels and every figure are in `evals/realworld/` and
`evals/results/realworld*.json`, including the per-tool figures that are not compared here.

## The research agent

Ask a question. Evidentia searches the web, reads the pages (HTML and PDFs), and writes short
claims. Each claim carries a quote copied from a page. Code checks that the quote is on the page
word for word, and a separate model, shown only the claim and the quote, judges whether the
quote backs the claim. Each claim ends up labelled **supported**, **partial** or **unverified**.

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

### What the research agent's evaluation found

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
`QDRANT_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`. `OPENAI_API_KEY` is needed only
for the real-world audit and for recording new audits.

```
uv sync
uv run python -m evidentia audit answer.md
uv run python -m evidentia "How fast did global solar capacity grow in 2023?"
```

The first line audits an answer saved in a file, for about a cent. The second runs the research
agent. Both cost money (model, search and embedding calls) and stop at the caps set in
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

The evaluations are under `uv run python -m evals`. They make many model calls; see D-021 in the
decisions file before running them. `uv run python -m evals report` rebuilds the report from the
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
