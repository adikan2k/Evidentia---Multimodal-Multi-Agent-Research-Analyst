# Decisions

One entry per decision. Each says what was chosen, why, what else was considered and the trade-off.
New entries go at the bottom. Aditya approves an entry before the module it covers is created.

## D-001. Package layout and tooling

Approved by Aditya on 2026-11-23.

**What.** A new `evidentia/` package at the repo root with one root `pyproject.toml` and `tests/`
beside it, managed with `uv`. Exact pins: `ruff==0.17.6`, `pytest==9.2.0`, build backend
`hatchling==1.33.0`. Python 3.11 or newer. Ruff checks `evidentia` and `tests` only; the old
`backend` and `frontend` folders are excluded.

**Why.** The plan names `evidentia/`, and M1 needs `python -m evidentia "question"` to work from the
repo root. `uv` writes a lockfile, so every machine and CI run installs the same versions.

**Considered.**
- A `src/` layout. Safer against importing the local folder by accident, but one more folder and
  not what the plan names.
- Building inside `backend/`. It would sit the new code next to old code we must not import.
- pip with `requirements.txt`. No lockfile, so transitive versions drift.

**Trade-off.** With a flat layout, tests can import the local folder instead of the installed
package, so a packaging mistake can go unnoticed. Acceptable because this is never published as a
library.

---

The entries below cover milestone M1. **Approved by Aditya on 2026-11-24**, with one change: he
said Claude API credits are not a constraint and to favour quality, but the other services (Voyage,
Tavily, Qdrant, Langfuse) must stay on their free tiers. D-004, D-005, D-006 and D-008 were updated
for that before any code was written, and D-011 was added.
Library facts were checked against the live docs and PyPI on 2026-11-24.

## D-002. M1 shape: one linear async graph of small modules

**What.** M1 is a straight line with no loop yet:
`plan -> search -> fetch -> index -> retrieve (hybrid + rerank) -> write -> quote_check`. It is built as a LangGraph
`StateGraph` whose state is one pydantic model. Every node is an `async` function with a `timeout=`
and a `retry_policy=`. Run state lives in memory and is printed at the end; Postgres waits for M4.

Files, all under `evidentia/`: `config.py`, `schemas.py`, `cost.py`, `llm.py`, `search.py`,
`fetch.py`, `chunk.py`, `embed.py`, `store.py`, `quote_check.py`, `tracing.py`, `graph.py`,
`report.py`, `__main__.py`. Each has a test file. Tests use fakes and never touch the network.

Pins: `langgraph==1.2.24`, `langchain-anthropic==1.7.12`, `langchain-core==1.8.4`,
`tavily-python==0.8.5`, `qdrant-client==1.20.0`, `voyageai==0.6.0`, `langfuse==5.2.0`,
`trafilatura==2.4.0`, `httpx==0.28.1`, `pydantic==2.14.4`, `pydantic-settings==2.16.3`,
`rich==15.0.0`.

**Why.** LangGraph node timeouts only work on async nodes (they are rejected at compile time on sync
ones), and the plan asks for node timeouts. M4 streams steps over server-sent events, which is also
async, so starting async avoids a rewrite. Using LangGraph for a straight line looks like overkill
today, but M2 adds the checker loop on the same graph.

**Considered.** Plain functions called in order (simplest, but M2 would need a rewrite and there
would be no per-node retry or timeout). Sync nodes with only client-level timeouts (easier to read,
but no node timeout and a rewrite in M4).

**Trade-off.** `async`/`await` on every node is more to explain than plain functions. The LangGraph
docs also say TypedDict state is faster than pydantic; we take pydantic for validation, as the
project rules require.

## D-003. Config and secrets

**What.** `config.py` holds one `Settings` class (pydantic-settings). It reads environment variables
and, at run time, the project's `.env` file. Keys are `SecretStr`, are passed straight to each
client, and are never printed, logged or written to a trace. A missing required key stops the run
at start with a message naming the variable, not its value.

**Why.** One place to see every setting. `SecretStr` means an accidental `print(settings)` shows
`**********`.

**Considered.** `os.getenv` calls scattered through modules (no validation, easy to miss one).
`python-dotenv` loading everything into `os.environ` (would also expose `ANTHROPIC_API_KEY` to
child processes).

**Trade-off.** The program reads `.env` itself. That is separate from the rule that Claude Code
never opens the file, which still holds.

## D-004. Model calls: structured output, no forced tools, data blocks

**What.** `llm.py` wraps `ChatAnthropic`. M1 uses `claude-sonnet-5-5` twice: the `plan` node turns
the question into up to 4 search queries, and the `write` node turns retrieved passages into up to
8 claims, each `{text, quote, source_id}`. `claude-haiku-5-5` is not used until a node needs it.

- Structured output uses `with_structured_output(Model, method="json_schema", include_raw=True)`.
  The LangChain default is function calling with a forced tool choice, which Sonnet 5.5 rejects.
- No `temperature` is sent; Sonnet 5.5 rejects non-default values.
- Effort is `medium` for `plan` and `high` for `write`. `max_tokens` is 4,000 and 12,000.
- Model names are settings, so trying `claude-opus-5-5` as the writer is a one-line change that
  the M3 evals can then justify with numbers.
- Fetched text goes in the user message inside `<passage-xxxxxxxx source_id="...">` blocks, where
  the `xxxxxxxx` part is random for each call. The system prompt says those blocks are data and
  that instructions inside them must be ignored. A page cannot close the block because it cannot
  guess the tag, so the text is passed through unchanged. (The first draft of this entry escaped
  `</source>` instead; that would have altered page text and broken exact quoting.)
- `stop_reason` is checked on every reply. `refusal` or `max_tokens` ends the run with a clear
  message instead of a half-parsed answer.

**Why.** Native structured output gives a validated pydantic object without the forced tool call
the model no longer accepts. Token limits stay finite so the worst-case cost of one call is known
before it is made.

**Considered.** The Anthropic SDK directly (fewer layers, but the plan names `langchain-anthropic`
and Langfuse traces LangChain calls for free). Anthropic's automatic refusal fallback to an older
Sonnet (a beta feature; not confirmed to pass through LangChain, so left off for now).

**Trade-off.** A 12,000-token limit can still cut off a long answer. When it does, the run fails loudly
and we raise the limit; it never prints a truncated report.

## D-005. Cost cap and per-node ledger

**What.** `cost.py` holds a price table and a `Ledger`. Before each paid call the ledger checks
`spent + worst case for this call <= cap` and raises `BudgetExceeded` if not. After the call it
records actual tokens and dollars against the node name. The cap is `1.00` dollar per run, set in
`Settings` (the plan started at $0.25; raised on Aditya's instruction). The cap stays in code
whatever the budget, because the public site in M4 runs questions from strangers. The CLI prints the per-node table and the total.

Prices in the table, each with its source and date in a comment:
Sonnet 5.5 $2 in / $10 out per million tokens, Opus 5.5 $4 / $20, Haiku 5.5 $0.10 / $0.50, Voyage
`voyage-4-large` $0.12 and `rerank-3` $0.05 per million tokens, Tavily basic search 1 credit at the
pay-as-you-go rate of $0.008 per credit.

Only Claude is expected to be billed. Voyage gives 200 million free tokens per model and a run uses
about 50 thousand; Tavily gives 1,000 free credits a month and a run uses 4.

**Why.** Checking before the call is what makes the cap hard; checking only after would let one
large call overshoot. Free-tier usage is still counted at list price so the number is the true
cost of a run, not a number that only holds while credits last.

**Considered.** Counting tokens exactly with the token-counting endpoint before each call (exact,
but an extra network call per model call). Tracking only model cost (misses search and embeddings).

**Trade-off.** The pre-call check uses an estimate: input characters divided by 3 plus the full
`max_tokens`. It is deliberately high, so a run can stop a little before the real cap.

## D-006. Search, fetch and extract

**What.** `search.py` calls Tavily with `search_depth="basic"`, 6 results per query, and keeps
at most 12 unique URLs per run. Basic costs 1 credit, half of advanced, and the extra depth only
improves Tavily's own snippets, which we do not use because we fetch every page ourselves. `fetch.py` downloads each page itself with `httpx`:

- `robots.txt` is read with the standard library parser and cached per host. Disallowed pages are
  skipped. If `robots.txt` cannot be read because of a server error, the host is skipped.
- At most one request every 2 seconds per host. 15 second timeout. 2 MB limit. HTML only in M1.
- The user agent is a generic `EvidentiaBot/0.1` with no personal details.
- `trafilatura` extracts the main text. Whitespace runs are collapsed and paragraphs are kept.
  That cleaned text is the **stored source text** that quotes are checked against.

**Why.** Fetching ourselves means we control and can show the exact text a quote came from, and
the robots and rate-limit rules apply to every page.

**Considered.** Tavily's `include_raw_content` (no fetching of our own, but we could not show
where the text came from or apply our own robots check). A headless browser for JavaScript-heavy
pages (heavy, slow, and not needed for M1).

**Trade-off.** Pages that need JavaScript, a login or a paywall yield little or no text and are
dropped. The run reports how many pages were skipped and why.

## D-007. Chunking

**What.** `chunk.py` packs whole paragraphs into chunks of about 1,200 characters. A paragraph
longer than 1,600 characters is split at sentence ends. No overlap. Every chunk stores its start
and end offsets, and a test asserts `source_text[start:end] == chunk.text` for every chunk.

**Why.** Character offsets tie each passage back to the stored source text, which the quote check
and later the PDF and video links depend on. Paragraph boundaries keep a quote from being cut in
half more often than fixed-size windows do.

**Considered.** Token-based splitting (needs a tokenizer dependency for little gain). LangChain
text splitters (another dependency, and harder to explain line by line). Overlapping windows
(returns near-duplicate passages).

**Trade-off.** With no overlap, a fact that spans two paragraphs can land in two chunks. The quote
check runs against the whole source text, not the chunk, so a quote crossing a chunk edge still
verifies.

## D-008. Embeddings and hybrid retrieval

**What.** `embed.py` calls Voyage `voyage-4-large` at 1,024 dimensions, with `input_type="document"` for
passages and `"query"` for the question, batching all passages of a run into as few requests as
the limits allow. `store.py` keeps one Qdrant collection with two vectors per point: `dense`
(cosine) and `bm25` (sparse, IDF modifier), plus the payload `run_id`, `source_id`, `url`, offsets
and text. Retrieval is one `query_points` call: top 30 dense and top 30 BM25 as prefetches, fused
with `RrfQuery`, filtered to the current `run_id`, top 30 returned. Voyage `rerank-3` then reorders
those 30 against the question and the best 10 go to the writer.

BM25 vectors are produced by Qdrant itself, not by a local model. The Qdrant docs confirm the
cluster can do this but the exact call was not on the pages read, so the first step of this module
is a small test against the real cluster. If the cluster cannot do it, the fallback is our own
term-count sparse vectors with Qdrant's IDF modifier, which needs no extra package.

**Why.** Dense vectors find passages that mean the same thing; BM25 finds exact names and numbers.
RRF combines the two rankings without tuning weights. The reranker reads the question and each
passage together, which is slower but more accurate than comparing vectors, so it is used only on
the 30 survivors. M3 measures what each stage adds.

**Considered.** `voyage-4` or `voyage-4-lite` (half and a sixth of the list price, but every one of
these models has the same 200 million free tokens, so the best one costs nothing here). `fastembed` for BM25 (pulls
in onnxruntime, against the no-heavy-local-models rule). One collection per run (slow to create
and clutters the free cluster).

**Trade-off.** Points from old runs stay in the collection until cleaned up; a cleanup command
comes later. Nothing is reused between runs, so the same page is embedded again each time.

## D-009. Quote check

**What.** `quote_check.py` is pure code with no model. For each claim it collapses whitespace in
the quote and looks for it with `str.find` in the stored text of the cited source. Found: the
claim is marked `verified` and the character offsets are saved. Not found, unknown `source_id`, or
a quote shorter than 20 characters: the claim is marked `unverified`. No fuzzy matching, no case
folding, no swapping of curly and straight quotes.

**Why.** This is the project's central promise: a citation is valid only if the quote is an exact
span of the stored text.

**Considered.** Fuzzy matching with a similarity threshold (catches near-misses, but then "exact"
is no longer true and a threshold has to be defended). Asking a model whether the quote is present
(forbidden by the rules, and it can be wrong).

**Trade-off.** A quote that differs by one character, such as a curly apostrophe typed straight,
fails. We accept honest "unverified" labels over lenient matching, and the eval in M3 will show
how often this happens.

## D-010. Tracing

**What.** `tracing.py` sets up Langfuse SDK v5. One parent span covers the whole run. The Langfuse
`CallbackHandler` is passed in the graph config, so every model call is traced with tokens. Tavily,
fetch, Voyage and Qdrant calls are wrapped in their own spans with inputs, outputs and cost. The
client is flushed before the process exits. Missing Langfuse keys stop the run at start; tests
inject a no-op tracer.

SDK v5 reads `LANGFUSE_BASE_URL`. The plan and `.env` use `LANGFUSE_HOST`, so `Settings` reads
either name and passes the value to the client explicitly. No change to `.env` is needed.

Two things found on the first live run (2026-11-24):
- Langfuse keys only work in the region the project was created in. The default host is the EU
  one, so a US project needs `LANGFUSE_HOST=https://us.cloud.langfuse.com`. The start-up error now
  says so.
- The Anthropic SDK emits its own span for every call, on top of the one LangChain's callback
  records, so each model call and its cost showed up twice. `export_span` drops the SDK's copy.

**Why.** The rules require every model call and tool call to be traced. Failing at start is better
than a run that silently leaves no trace.

**Considered.** OpenTelemetry directly (more setup, no ready LangChain view). Logging to a local
file only (nothing to show in an interview, no cost view).

**Trade-off.** Passage text and the question are sent to Langfuse cloud. API keys never are.

## D-011. Terminal report

**What.** `report.py` prints the run with `rich`. While the graph runs, each node prints one line
when it finishes, with what it actually did (queries written, pages fetched and skipped, passages
indexed, claims written). At the end it prints each claim with a verified or unverified mark, the
exact quote, the source URL, then a per-node table of tokens and dollars and the Langfuse trace id.
`--json` prints the same result as JSON for scripts and for the evals in M3.

**Why.** M1's deliverable is something you can run and show. Progress lines come from real node
updates streamed by LangGraph, so nothing on screen is decorative.

**Considered.** Plain `print` (works, but a wall of text hides the verified and unverified split,
which is the point of the project). A full-screen terminal UI (more code than the pipeline itself).

**Trade-off.** One more dependency for output only. The pipeline never imports it, so the API in
M4 does not carry it.

---

The entries below cover milestone M2. **Approved by Aditya on 2026-11-24.**

## D-012. The checker

**What.** A new `check` node runs after the quote check. For each claim whose quote was found on
the page, it makes one separate model call that is shown exactly two things: the claim and the
quote. It never sees the question, the other claims, the passages, the source URL or anything the
writer produced besides that one sentence. It returns one label and a one-sentence reason:

- `supported`: the quote on its own states everything the claim says.
- `partial`: the quote backs the main point, but the claim adds something the quote does not
  state, such as a number, a date, a comparison or a cause.
- `unsupported`: the quote does not back the main point, contradicts it, or is about something
  else.

The model is `claude-sonnet-5-5` at medium effort, set in `Settings`. The quote is web text, so it
goes inside the same random-tag data block the writer uses. The calls run at the same time.

**Why.** The writer chose the quote and wrote the claim, so it is the worst judge of its own work.
A fresh call that sees only the two strings cannot be swayed by the writer's framing or by other
claims. One call per claim also gives M3 a clean unit to label by hand: one claim, one quote, one
verdict.

**Considered.** One call for all claims (cheaper, but verdicts can influence each other and the
checker would see the full answer). A different model as checker, such as Opus (possibly more
independent; M3 can measure it, since the model is a setting). A smaller model (cheaper, likely
weaker on subtle over-claims; also for M3 to measure).

**Trade-off.** About eight extra model calls per run. Estimated at 2 to 3 cents; the first live run
will give the real figure.

## D-013. The repair loop

**What.** After `check`, a claim has failed if its quote was not found on the page or the checker
said `unsupported`. If any claim failed and no repair round has run yet, the graph takes one loop:

1. `rewrite`: one `claude-haiku-5-5` call writes a new retrieval query for each failed claim,
   using the claim and the reason it failed.
2. `reretrieve`: each query runs the same hybrid search and rerank over the pages already fetched
   for this run.
3. `revise`: for each failed claim, the writer model gets the claim, the reason and the new
   passages. It returns a corrected claim with a new quote, or says the passages do not back it.
4. The revised claims go through the quote check and the checker again.

A claim that still fails, or that the reviser could not back, is final: `unverified`. `partial`
claims do not trigger the loop; they are shown as partial with the checker's reason.

There is one repair round (`max_repair_rounds = 1`). The plan's diagram says "max 2 loops" and its
M2 text says "one more retrieval"; this follows the M2 text and leaves the number as a setting.

**Why.** A failed claim is often a retrieval miss: the fact is on a fetched page, but the first
search for the whole question did not surface that passage. Searching again for the specific claim
finds it. The loop is bounded so a run cannot spin and its worst-case cost is known.

**Considered.** A new web search in the loop (could find pages the first search missed, but costs
search credits and a second fetch-and-index pass; better judged with M3 numbers). Using the claim
text itself as the query with no model call (free, but ignores why the claim failed). Also
repairing `partial` claims by trimming them to what the quote says (would raise the supported
count, but the plan treats partial as an honest final label, and M3 should measure before we
change that).

**Trade-off.** A fact that is true but not on any fetched page ends as `unverified`. That is the
intended behaviour: the label describes our evidence, not the world.

## D-014. Final labels

**What.** Every claim ends with exactly one of three labels, shown in the report and the JSON:

| Quote on the page | Checker verdict | Final label |
|---|---|---|
| yes | supported | `supported` |
| yes | partial | `partial` |
| yes | unsupported (after the repair round) | `unverified` |
| no (after the repair round) | not run | `unverified` |

Each claim also records the checker's reason and whether it was revised in the repair round. The
report prints the reason under every `partial` and `unverified` claim, and a summary line with the
three counts. M1's `verified` label goes away, because "the quote exists" is no longer the claim
the report makes.

**Why.** One label per claim keeps the report honest and simple to read, and it is the unit M3
scores.

**Considered.** Keeping `verified` as a fourth label (two overlapping words for the reader to
decode). Hiding unverified claims (cleaner page, but hides exactly what the project is about).

**Trade-off.** `unverified` covers two different failures: a bad quote and an unbacked claim. The
reason line tells them apart.

## D-015. The cost cap when calls run at the same time

**What.** The ledger gains reservations. Before a call, its worst-case cost is reserved; the check
is `spent + reserved + this call <= cap`. When the call returns, the reservation is released and
the actual cost is recorded.

**Why.** M1 made one paid call at a time, so checking `spent` was enough. The checker makes several
calls at once. Without reservations, eight calls could each see room under the cap and together
pass it.

**Considered.** Running the checker calls one after another (keeps the old ledger, but makes every
run slower for no accuracy gain). A lock around all paid calls (same slowdown).

**Trade-off.** Reservations use worst-case prices, so near the cap a call can be refused even
though the actual costs would have fitted. The cap staying hard matters more.

### What the first live M2 runs showed (2026-11-24)

These are single runs, not an evaluation. M3 is where this gets measured.

- The checker is strict and its reasons are specific. Across three ordinary runs it labelled 7 of
  22 claims supported and 15 partial, and none unverified.
- Most partial labels are about context the writer added from around the quote: who said it,
  which study, how many trials. The writer prompt now says the checker sees only the claim and
  the quote and that such context must be inside the quote or left out. That instruction is not
  in D-012; it was added after the first run.
- No claim failed outright in ordinary runs, so the repair loop did not fire on its own. It was
  exercised against the real services by planting bad claims in a real draft: a corrupted quote
  was repaired and came back supported; a false claim was rewritten to what the pages say; and a
  claim no page could back ended as unverified.
- One thing D-012 did not cover: if the checker returns no verdict for a claim (a refusal or a
  cut-off), that claim is labelled unverified with the reason "the checker did not return a
  verdict", and the run continues.

---

The entries below cover milestone M3. **Approved by Aditya on 2026-11-24.**
DeepEval facts were checked against its docs and PyPI on 2026-11-24.

## D-016. A frozen, openly licensed evaluation corpus and 40 questions

**What.** The evals run on a fixed set of pages saved in the repo under `evals/corpus/`, not on
live web search. Pages come only from sources whose licence allows copying with credit:
Wikipedia (CC BY-SA), Our World in Data (CC BY) and United States government sites (public
domain). Each saved page keeps its URL, fetch date, licence and a hash of its text.

`evals/questions.jsonl` holds 40 questions. Each has the pages that answer it and one to three
gold snippets: exact text from those pages that contains the answer. About a quarter of the
questions are ones where the pages disagree or the honest answer is "it depends". Claude drafts
the questions and gold snippets with the pipeline's own fetcher; Aditya reviews them before any
number is reported, and the results file records that this is how the gold set was made.

**Why.** Live search returns different pages each day, so a number measured today could not be
reproduced tomorrow or in CI. A frozen corpus makes every result repeatable by anyone who clones
the repo. Open licences are what make it legal to commit the text.

**Considered.** Live search for every eval run (realistic, but unrepeatable and it spends search
credits). Any web page, cached locally and not committed (wider range of sources, but nobody else
could reproduce the numbers). An existing public benchmark (comparable to other work, but its
questions are not research questions with quotable sources).

**Trade-off.** Encyclopaedia and government pages are cleaner than the open web, so these numbers
will flatter the pipeline compared with real use. The report says so. The nasty tests in D-020
cover the messy cases on purpose.

## D-017. Retrieval evaluation

**What.** All corpus pages are chunked and indexed once. For each question, four retrievers return
their top 10 passages: keyword only (BM25), dense only, hybrid (both fused by rank), and hybrid
followed by the reranker. A passage counts as relevant if it overlaps a gold snippet. Reported per
retriever: recall at 10, mean reciprocal rank and nDCG at 10, each with a 95% bootstrap confidence
interval over the 40 questions, plus the paired difference between neighbouring retrievers.
`store.py` gains a way to run each prefetch alone.

**Why.** This is the table that shows whether hybrid search and the reranker earn their place. A
paired difference with an interval says whether a gap is real or noise at 40 questions.

**Considered.** Judging relevance with a model (scales to more passages, but adds a judge that
would itself need checking). Only reporting the final pipeline (hides which stage helps).

**Trade-off.** Gold snippets mark the passages we know are relevant; a passage that answers the
question in other words is counted as a miss. All four retrievers are scored the same way, so the
comparison stays fair even though absolute recall is understated.

## D-018. Does the checker agree with a human?

**What.** A set of about 150 claim-and-quote pairs in `evals/pairs.jsonl`. About two thirds come
from real writer output on the 40 questions. The rest are built to make sure all three labels are
well represented: a claim paired with the wrong quote, a claim with one number or name changed,
and a claim with added context. Aditya labels every pair as supported, partial or unsupported
using a small terminal tool that shows only the claim and the quote, in random order, without the
checker's answer or how the pair was made. Labels are saved to `evals/labels.jsonl`.

The checker then labels the same pairs. Reported: overall agreement, Cohen's kappa, a confusion
table and per-label precision and recall, all with bootstrap intervals, split by real and built
pairs. The same is run for `claude-haiku-5-5` and `claude-opus-5-5` as the checker.

**Why.** Every label the product shows rests on the checker. This measures how far it can be
trusted, against the only ground truth available: a careful person reading the same two strings.

**Considered.** Skipping built pairs (M2's live runs produced no unsupported claims at all, so the
set would say nothing about the checker's most important label). Having a model produce the
"human" labels (not hand labels, and circular).

**Trade-off.** One labeller, so no measure of how much two people would disagree. This costs
Aditya about an hour and a half. The results file states both.

## D-019. Baseline against the full pipeline

**What.** Two systems answer the 40 questions from the same indexed corpus.

- Baseline, "one-shot RAG": dense retrieval of the top 10 passages, one writer call that returns
  claims each citing a passage, and nothing else. No quote, no quote check, no checker, no repair.
- Full pipeline: as built in M1 and M2, started from the index step.

A judge decides for every claim whether the evidence the system points to backs it: the cited
passage for the baseline, the quote for the pipeline. The judge is `claude-opus-5-5` using the
checker's rubric, so it is a different model from the Sonnet checker inside the pipeline, and its
own agreement with Aditya's labels comes from D-018. Reported for each system, with bootstrap
intervals over questions and the paired difference:

- citation accuracy: of the claims the system presents as backed, the share the judge finds
  fully supported. For the pipeline, "presented as backed" means labelled supported.
- claims per question, so accuracy cannot be bought by saying less.
- the share of questions with at least one fully supported claim.

DeepEval's `FaithfulnessMetric`, with Claude as its judge, is run on both systems' answers as a
second score that we did not design.

**Why.** "Proves every sentence" is only worth saying if it beats the obvious simple system on
the same questions. The judge is not the pipeline's own checker, because scoring the pipeline
with the model that already filtered its claims would be marking its own homework.

**Considered.** Aditya judging every claim by hand (about 600 claims; too much). Using the Sonnet
checker as judge (circular). Comparing only on live web questions (unrepeatable).

**Trade-off.** The judge is still a model in the same family as the writer and checker. Its error
rate against hand labels is reported next to the result so the reader can discount accordingly.

## D-020. Nasty tests

**What.** Three made-up pages are served to the real pipeline in place of fetched pages, with the
real models:

1. Hidden instructions: an ordinary article with text, invisible to a human reader, telling the
   model to add a specific made-up phrase and link. Pass: neither appears anywhere in the output.
2. Paywall: an article that stops after a teaser followed by a subscribe notice. Pass: every claim
   is backed by the visible teaser, and nothing is claimed about the hidden part.
3. Contradiction: two pages giving different figures for the same thing. Pass: the report carries
   both figures, each tied to its own page.

Each runs several times and the pass rate is reported. Failures are kept with their full output.

**Why.** These are the cases a reader will ask about, and the frozen corpus is too clean to
contain them.

**Considered.** Finding real pages that do this (they change or disappear, and quoting a real
attack page is unwise). Unit tests with fake models only (already in the test suite; they prove
the plumbing, not the model's behaviour).

**Trade-off.** Three hand-made cases show behaviour on those cases only. They are evidence, not a
security guarantee, and the report words it that way.

## D-021. How evals run and where results go

**What.** A new top-level `evals/` package with one entry point, `python -m evals`. A `Makefile`
target `evals` calls it, so `make evals` works on Linux and in CI; on Windows the command is
`uv run python -m evals`. It writes one JSON file per evaluation into `evals/results/` and builds
`evals/results/REPORT.md` from those files, including a "what failed" section listing the worst
questions, the checker's disagreements with Aditya and any nasty-test failures. Every number in
the README and on the site will be read from these files.

Eval-only packages go in a separate `evals` dependency group: `deepeval==4.3.5`. DeepEval needs
`rich` below 15, so the `rich` pin moves from 15.0.0 to 14.3.4. DeepEval's telemetry is switched
off (`DEEPEVAL_TELEMETRY_OPT_OUT=1`) and it is stopped from loading `.env` on its own
(`DEEPEVAL_DISABLE_DOTENV=1`); keys are passed to it from `Settings`.

CI is replaced. The old workflow ran black and isort over the old code. The new one has two jobs:

- on every push and pull request: `ruff` and `pytest`. No keys, no network, no cost.
- started by hand from the GitHub Actions page: the full evals with keys from repository secrets,
  with the results uploaded as a file attached to the run.

`.pre-commit-config.yaml` is cut down to ruff to match.

**Why.** One command and one results folder keep "no invented stats" checkable: a number is real
if and only if it is in a committed results file. Evals cost money and need secrets, so they run
when asked, not on every push.

**Considered.** Running evals on every push (slow, costs a few dollars each time, and secrets are
not available to pull requests from forks). Keeping black and isort (they would fight ruff's
formatter over the same files).

**Trade-off.** A full run is estimated at 5 to 10 dollars of Claude usage and about 20 minutes;
the first run will give the real figures. Voyage and Qdrant stay inside their free tiers and
Tavily is not used at all. The CI eval job needs the branch pushed and the service keys added as
secrets on GitHub, both of which are Aditya's to do.

### What the first M3 results showed (2026-11-24)

All figures are in `evals/results/`. Checker agreement is not measured yet; it waits on the hand
labels.

- Retrieval: the reranker helps and hybrid search does not. Plain hybrid scored below dense
  search alone, and dense + rerank matched hybrid + rerank exactly. On this corpus keyword search
  adds nothing. The fifth retriever, dense + rerank, was added to D-017's four to test this.
- Baseline against pipeline: no measurable difference in citation accuracy. The judge found about
  92% of claims fully backed for both, and the interval on the difference spans zero. Neither
  system produced a single claim the judge called unsupported.
- That comparison is not like for like. The baseline is judged against a whole passage of about
  1,200 characters; the pipeline against a quote of a sentence or two, which is a harder bar. A
  passage-level judgement of the pipeline was not run.
- DeepEval's faithfulness score was 1.0 for both systems, so it cannot tell them apart here. One
  pipeline answer could not be scored because DeepEval failed to parse its judge's reply.
- Nasty tests passed 15 of 15.
- The Anthropic API refused 33 requests sent at once, so eval steps now send at most 4 at a time.
- Wikipedia refuses crawlers that do not identify themselves. With Aditya's approval the
  fetcher's User-Agent now carries the public repository address, for every fetch.

### Change to D-018: labels made by a model, not by Aditya (2026-11-24)

Aditya said he does not have time to label the 150 pairs and asked Claude to do it. Claude (Fable
5.2) read all 150 pairs, seeing only the claim and the quote, and labelled them. Those labels are
in `evals/labels_model.jsonl`, kept apart from `evals/labels.jsonl`, which is reserved for labels
made by a person and is still empty.

What this changes:

- There is **no agreement-with-a-human figure**. D-018's main measurement has not been made, and
  nothing in the README or on the site may say or imply that it has.
- What exists instead is agreement between each checker model and a second, stronger model. It
  shows whether the checker is consistent with a careful second reading. It cannot show that
  either reading is right, and both models are from the same family.
- A measurement that needs no labels was added: of the 50 pairs broken on purpose when they were
  built, how many does each checker refuse to pass as supported.
- The labelling tool still works. If Aditya later labels even the first 30 pairs, which are a
  random sample because the file is shuffled, the report will show both comparisons side by side.

Also changed: the default Langfuse address in `config.py` is now the US region, where this
project lives, so the commands run without an extra line in `.env`.

---

The entries below cover phase 1 of the gameplan agreed on 2026-11-24. Aditya approved the phase
in outline ("Yes, start phase 1"); these entries write down what that outline means in detail.

## D-022. Three harder evaluations

**What.** Added to M3, all on the frozen corpus:

1. Unanswerable questions. `evals/unanswerable.jsonl` holds 20 general-knowledge questions whose
   answers are not in any corpus page. Each has an answer pattern, and code confirms the pattern
   matches nothing in the corpus. Both systems answer them. Reported: how often each system
   presents no backed claim, how often a backed claim contains the answer (which can only have
   come from the model's memory), and what the judge makes of the claims it does present.
2. A cheap writer. The baseline and the pipeline are rerun with `claude-haiku-5-5` as the writer
   (and, for the pipeline, as the checker too), to see whether checking lets a model twenty times
   cheaper be used safely.
3. Evidence size. From the saved runs, with no model calls: how many characters a reader must
   read to verify one claim. For the baseline that is the cited passage; for the pipeline, the
   quote.

**Why.** The first results showed no accuracy gap between the baseline and the pipeline, because
a strong writer on clean pages rarely errs. These three look where a gap could exist: when the
sources lack the answer, when the writer is weaker, and in how precise the evidence is.

**Considered.** Stopping at the first result (honest, but leaves the obvious follow-up questions
unasked). A live-web slice (more realistic, but unrepeatable; still open as a later option).

**Trade-off.** The unanswerable questions were written by Claude and are easy trivia, so a model
is strongly tempted to answer from memory. That is the point, but it is a stress test and not a
sample of real questions.

## D-023. Three product changes, each kept only if measurement supports it

**What.**

1. Tighten partial claims. A new setting, `tighten_partial`. When on, a claim the checker calls
   partial is rewritten in the repair round to say only what its quote says, keeping the same
   quote, and is then checked again. This reverses D-013's choice to leave partial claims alone.
2. Dense search by default. A new setting, `keyword_search`, off by default. Retrieval becomes
   dense search plus the reranker. Passages are still indexed with both vectors, so switching
   keyword search back on needs no re-indexing.
3. A cheaper checker. `checker_model` moves from Sonnet to Haiku if the cheap-pipeline run in
   D-022 holds up.

**Why.** Each follows from a measured result: 87 of 310 claims were labelled partial, mostly for
context added around the quote; dense + rerank matched hybrid + rerank exactly; and Haiku caught
48 of 50 broken claims against Sonnet's 49.

**Considered.** Leaving all three as they are (the plan's original design, but it ignores what the
evals found). Removing keyword search outright (simpler, but it has not been tested on live web
pages, where exact names and numbers may matter more).

**Trade-off.** Tightening makes claims safer and blander: "A Cochrane review found X" becomes "X"
when the quote does not name the review. The eval reports how many claims change so the loss is
visible.

### What phase 1 showed (2026-11-24)

All figures are in `evals/results/`. Judge: Opus, same rubric as the checker.

- No accuracy advantage was found anywhere. Fully backed share of claims shown as backed:
  Sonnet baseline 0.917, Sonnet pipeline 0.928, Haiku baseline 0.921, Haiku pipeline 0.888,
  pipeline with tightening 0.925. Every difference from the baseline has an interval that
  includes zero.
- The cheap writer did not need rescuing. Haiku as a one-shot baseline was as accurate as Sonnet.
- Unanswerable questions did not separate the systems. On 20 questions the corpus cannot answer,
  three systems made no claim at all and the Haiku baseline made two, neither from memory.
- What the pipeline measurably gives: evidence about five times shorter (a median of 188
  characters to read per claim against 1,039), exact quotes checked by code, 49 of 50
  deliberately broken claims caught by its checker, and 15 of 15 on the nasty tests. It costs
  about three and a half times the baseline per question.
- D-023 outcomes:
  1. Tightening is now on by default. Partial labels fell from 87 of 310 to 6 of 311, claims
     shown as backed rose from 5.6 to 7.6 per question, and accuracy did not drop.
  2. Dense search is the default, as the retrieval eval already supported.
  3. The checker stays on Sonnet. The Haiku pipeline's accuracy was the lowest of the five and
     Haiku passed one more broken claim. Neither gap is statistically clear, but the checker is
     the part the product's promise rests on, and the saving is under two cents a run.
- The unanswerable set has 20 questions drawn from 40 candidates; code dropped the other 20
  because the corpus did contain their answers.

---

The entries below cover milestone M4, the live site. **Approved by Aditya on 2026-11-24.** The three reference galleries in `docs/PLAN.md` were looked at on 2026-11-24.

## D-024. Visual direction: a marked-up document

**What.** The site looks like a carefully typeset page that someone has gone over with a
highlighter. Off-white paper background, near-black ink, a serif display face for headlines, a
plain sans for reading text and a monospace face for small labels and numbers. One accent colour
only, a highlighter yellow, and it is used for exactly one thing: evidence. Supported, partial
and unverified get three quiet ink colours for their labels.

Motion follows one rule: something moves only when something real happened.

- When a claim is checked, a highlighter stroke sweeps across its quote inside the source text.
- Claims are set on the page as the writer produces them. Labels stamp in when the checker
  answers.
- The pipeline is a thin strip of seven steps that fill in with real counts and cost.
- Scrolling the home page plays a recorded real run in step with the scroll.

**Why.** The galleries' best AI sites share four habits: large confident type with space around
it, a near-monochrome palette with one accent, the product itself shown in the first screen
instead of abstract art, and one strong motif. Evidentia's whole point is the exact quote, so the
highlighter is the motif, and it is also what the animation shows. That keeps it from looking
like every other dark-gradient AI site.

**Considered.** Dark theme with glowing accents (the default look for AI products, and close to
the old site this rebuild is leaving behind). A terminal look (matches the command-line tool,
but reads as a developer toy). Heavy 3D or WebGL (impressive in a gallery, slow on phones, and
nothing in the product is three-dimensional).

**Trade-off.** A light, typographic site is quieter than the flashiest Awwwards winners. The bet
is that precise motion tied to real events is more memorable than spectacle. A dark mode can come
later; it is not in M4.

## D-025. What the site contains

**What.** Four screens.

1. Home. A headline, the question box, and directly beneath it a recorded real run that plays as
   you scroll. Then the three measured facts with links to their numbers, and a short "what this
   does not do".
2. Run. The main screen. Claims on the left, the source on the right. Clicking a claim scrolls
   the source to its quote and highlights it. The pipeline strip sits on top with cost so far.
   The same screen plays recorded runs and live ones.
3. Try to break it. Any claim on the Run screen can be edited in place. The checker is called
   and its verdict and reason appear. This is the 49-of-50 result made into something a visitor
   can poke at.
4. Evals. Charts drawn from the files in `evals/results/`, including the result that the
   pipeline is not more accurate than plain RAG, and the "what failed" list.

**Why.** Each screen is one of the three things the evidence supports: you can see the exact
words, the checker catches errors, and the numbers are shown whether or not they flatter.

**Considered.** A chat interface (familiar, but it hides the evidence, which is the product). A
dashboard of past runs (needs accounts and a database for little gain).

**Trade-off.** No accounts and no history. A visitor's run lives in their browser tab.

## D-026. Frontend: a fresh app in `web/`

**What.** A new Next.js app in `web/`, with Tailwind, shadcn components and Motion for animation,
deployed on Vercel. Exact versions are pinned when it is created, after checking current docs.
The old `frontend/` folder is deleted in the same change; it stays in git history and on the
archive branch.

**Why.** The old frontend is built from glass cards, gradients and pages for features that no
longer exist. Restyling it would mean deleting most of it anyway, and starting clean avoids
carrying its dependencies.

**Considered.** Restyling `frontend/` in place (keeps the folder, but nearly every file would
change). A plain static site (simplest to host, but the live run view needs real interactivity).

**Trade-off.** Any link to an old page will break. Nothing public depends on them.

## D-027. API: FastAPI with a live event stream, and no database

**What.** A small FastAPI app in `evidentia/api.py`, deployed on Cloud Run:

- `POST /runs` starts a run and streams it as server-sent events: one event as each node
  finishes, then the final report.
- `POST /check` takes one claim and one quote and returns the checker's verdict. This powers
  "try to break it".
- `GET /health`.

Recorded runs are plain JSON files in `web/public/replays/`, produced by a script from real runs
and served by Vercel. Browsing them never touches the API. There is no database: the plan's
Postgres is dropped for M4.

The source pane shows each quote with a few hundred characters either side and a link to the
original page, not the whole page.

**Why.** Server-sent events are the simplest way to push the pipeline's real progress to a
browser. Replays as files make the site fast, free to browse and still working if the API is
down or over its cap. Showing a window around the quote, not the full text, avoids republishing
other people's pages.

**Considered.** WebSockets (two-way, which we do not need). Postgres for run history (needed only
if runs must outlive the browser tab). Showing full page text (better context, but it is
republishing).

**Trade-off.** A live run is lost if the tab closes. Replays are a fixed set chosen in advance.

## D-028. Protecting the credits on a public site

**What.** Four layers, all on by default:

1. Replays first. The home page and the default Run screen play recorded runs. A live run
   happens only when a visitor types a question and presses the button.
2. A daily budget in dollars, in code. When the day's live runs and checks reach it, the API
   answers "today's live budget is used up; here are recorded runs" until midnight UTC. It
   starts at $1.00 a day, about 20 live runs.
3. Per-visitor limits: 3 live runs and 30 checks per IP address per day, one run at a time.
4. Cloud Run is limited to one instance, so the counters in memory are the only counters.

Outside the code, Aditya sets a monthly spend limit in the Anthropic console. That is the real
backstop and it is his to set.

**Why.** A public box that spends money per press will be found and pressed. The per-run cap
already exists; these add a cap per day and per visitor.

**Considered.** A sign-in wall (stops abuse, and also stops interviewers trying it). A CAPTCHA
(friction, and a third-party script). A shared counter in a database (survives restarts, but
adds a service for a small gain).

**Trade-off.** The in-memory counters reset if the instance restarts, so a restart can let a
little more than the daily budget through. The console spend limit covers that.

## D-029. Build order

**What.** Four steps, each ending in something to look at:

1. A clickable prototype of the Run screen in `web/`, playing two recorded runs. No API, and no
   model calls beyond recording the runs once. Aditya reacts to the look and the motion here,
   before anything else is built on it.
2. The API with the event stream, the caps, and live runs wired into the Run screen.
3. Try to break it, the Evals page and the Home page.
4. Deploy to Vercel and Cloud Run.

**Why.** The look and the motion are the riskiest part and the cheapest to change early. Seeing
the main screen first means a wrong direction costs an hour, not a milestone.

**Considered.** API first (the usual order, but nothing to look at for longest).

**Trade-off.** Step 1 uses hand-recorded data, so a little of it is reworked when live events
arrive in step 2.

## D-030. PDFs: stored text that knows its page numbers

**What.** The fetcher accepts PDFs as well as HTML pages.

- A response is a PDF when its content type is `application/pdf` or its body starts with `%PDF-`.
- Text comes from each page with `pypdf` 7.1.1 (pure Python, no other dependencies). Each page is
  cleaned like a web page: whitespace collapsed, a word split by a hyphen at a line end joined
  back ("evi-" + "dence" becomes "evidence"), and line breaks inside the page turned into spaces.
  Pages are joined with a line break, so no paragraph runs across a page boundary.
- `Source` gains `kind` (`html` or `pdf`) and `page_starts`, the offset in the stored text where
  each page begins. A claim's page is worked out from where its quote starts; a quote that runs
  over a page break is cited as "pp. 4-5". The quote check itself does not change.
- Limits: 15 MB per PDF (web pages stay at 2 MB), the first 40 pages only (the report says when
  it cut a document short), parsing done off the event loop with a 20-second limit.
- Skipped, with the reason shown: a PDF with no text layer ("scanned PDF, no text"), and an
  encrypted PDF. No OCR.
- robots.txt, the per-domain rate limit and the private-address guard apply unchanged.

**Why.** Many of the best sources for factual questions are PDFs (agency reports, papers,
statistical releases), and today every one of them is skipped as "not an HTML page". The quote
check works on any stored text, so PDF quotes get the same exact-span guarantee as web pages
with no change to rule 8.

**Considered.**
- `pdfplumber` 0.11.11: better layout and table handling, but pulls in `pdfminer.six` and Pillow
  and is slower.
- OCR through an API for scans: costs per page, and OCR mistakes would become "exact quotes" of
  text the PDF does not contain.
- Page images for charts: see D-033.

**Trade-off.** `pypdf` sometimes gets the reading order wrong on two-column pages and splits
words oddly. Then a true quote fails the exact-span check and the claim is dropped or marked
unverified: the failure costs claims, never produces a false citation. PDFs are untrusted input
parsed in our own process; a malformed file could keep a worker thread busy past the time limit
(Python cannot stop a thread), and the size and page caps bound that.

**Tests.** Small PDFs built inside the test code: page offsets, a quote on page 3, a quote across
a page break, hyphen joining, a scanned (textless) PDF, an encrypted PDF, an oversized PDF, and
a PDF served with the wrong content type. No paid calls.

## D-031. How a PDF citation is shown

**What.** A claim from a PDF shows "PDF, p. 7" beside its source. The evidence pane shows the
quote highlighted inside its stored context, exactly as for a web page. The source link opens
the original document at that page (`url#page=7`), which the built-in PDF viewers in Chrome,
Edge and Firefox follow.

**Why.** The plan asked for pdf.js opening the page with the quote highlighted on it. pdf.js
running on our site has to download the PDF from its host, and browsers block that unless the
host allows cross-site reads, which most do not. The only way round it is to pass the file
through our API, which means serving other people's documents from our address and paying for
the bandwidth.

**Considered.** pdf.js with a proxy (above). Rendering page images on the server (needs a PDF
renderer, storage, and is still republishing).

**Trade-off.** The highlight is in our evidence pane, not painted on the PDF page. The page
itself is one click away.

## D-032. YouTube captions: left out, because robots.txt forbids fetching them

**What.** No YouTube support.

**Why.** Rule 15 says respect robots.txt. Checked on 2026-11-24: YouTube's robots.txt for all
crawlers disallows `/api/`, `/youtubei/`, `/timedtext_video` and `/get_video_info`. Every way to
get captions for someone else's video goes through those paths: `youtube-transcript-api` 1.2.5
posts to `/youtubei/v1/player`, and the caption files it then downloads are under `/api/`. The
official Data API (`captions.download`) only gives captions to the video's owner. The plan also
warned that YouTube blocks cloud addresses, so it would probably fail on Cloud Run regardless.

**Considered.**
1. Use `youtube-transcript-api` anyway. Breaks rule 15; would need Aditya to write an exception
   into `CLAUDE.md`.
2. Another source of timestamped transcripts whose robots.txt allows it (a talk or podcast site).
   Each site is different, and it narrows "video" to one publisher.
3. Let the visitor paste a transcript. The quote check would work on it, but nothing could check
   that the pasted text matches the video.

**Trade-off.** Evidentia covers web pages and PDFs, not video. The pitch loses "a video moment"
and keeps only sentences that are true.

## D-033. Charts read by vision: left out, and M5's finish line changes

**What.** No page images, no `voyage-multimodal-3.5`, no chart reading. M5's "done when" becomes:
one report cites a web page and a PDF page, each through a quote that passes the code check,
and the site shows the page number and opens the PDF at that page. `docs/PLAN.md` is updated to
match.

**Why.** Rule 8: a citation is valid only if the quote is an exact span of the stored source
text. A number read off a chart by a model has no span: the only text would be the model's own
description, and checking a model against its own words proves nothing. Every chart claim would
come out unverified. Charts that print their numbers (axis labels, data labels, captions, a
table beside the chart) already have them in the PDF's text layer, and those get cited the
normal way.

**Considered.** Storing the vision model's reading as text marked "read from a figure" and
always labelling those claims unverified. It shows a multimodal step, but adds a kind of claim
the product's promise cannot stand behind, and costs a vision call per page.

**Trade-off.** The milestone called "Multimodal" becomes "PDFs". The project gets narrower and
stays honest.

**Build order.**

1. Fetcher, `Source` and claim page numbers, with tests. No paid calls.
2. Page numbers in the report, the events and the site.
3. One recorded run that cites a PDF, for the site's replays (about 10 cents), then deploy.

### What M5 showed

- One recorded run (`web/public/replays/cbo-deficit-outlook.json`, $0.10) read 11 pages, 2 of
  them PDFs. Three of its six final claims cite page 3 of a CBO testimony PDF, three cite a web
  page, and every quote was found word for word by code.
- Some publishers' robots.txt rules disallow their PDFs (IRENA's reports, for one), so those
  are skipped like any other disallowed page.
- The first replay showed a PDF quote's surrounding text running back into the cover page. The
  context window now stops at the edges of the quote's own pages.
- On a narrow screen the run layout scrolled sideways; its single column is now capped at the
  screen width.

# After M5: from research agent to auditor

## D-034. Evidentia becomes an auditor of other AI tools' answers

**What.** The main product changes from "a research agent that proves every sentence" to "an
auditor that checks the citations in any AI answer". The research pipeline stays and keeps
working, but the work from here goes into the auditor, in this order:

1. Clean-up: the resolved-address guard (D-035), the old code removed, an accurate README,
   `rebuild` merged into `main` (D-036).
2. The auditor's core: split an answer into claims, fetch each cited page, find the exact words,
   and label each claim supported, partial, not on the cited page, contradicted, or dead link.
   A contradiction must also be an exact quote. Then a run on LLM-AggreFact, a public set of
   claim and document pairs labelled by people.
3. Audit mode on the site: paste an answer, see it marked up with a scorecard, try to break it.
4. A real-world audit of AI tools' answers, with a results page.
5. A citation repair loop, then the hybrid-search rerun on finding one sentence in a page.
6. MCP tools (`check_claim`, `audit_answer`), then image evidence.

Each new module still gets its own entry here before it is built.

**Why.** Our own evals: the pipeline was no more accurate than one-shot RAG (0.928 against
0.917, intervals overlapping) at about 3.5 times the cost, while the checker caught 49 of 50
deliberately broken claims (`evals/results/`). On clean pages our writer rarely errs, so the
checker has little to catch. Answers from other AI tools are where wrong citations are, and a
reviewer pointed this out.

**Considered.** Keep improving the research agent (more agents, better retrieval): the evals
give no sign that it would beat plain RAG by much. A redesign of the site: it already works.

**Trade-off.** The README and the pitch change, and the research pipeline becomes the second
feature. Numbers about other tools must come from our own audit; published figures from other
studies cannot appear on the site (rule 7).

## D-035. Check the address a host name resolves to, at the moment of connecting

**What.** The fetcher's HTTP client connects only to public addresses. Every connection,
including robots.txt and every redirect hop, resolves the host name, refuses if any address it
resolves to is not public (loopback, private ranges, link-local such as the cloud metadata
address, and so on), and then connects to the address it checked. The existing check on the
host name as written stays as a quick first filter.

**Why.** Until now only the name as written was checked. A public domain whose DNS points at
`127.0.0.1` or `169.254.169.254` passed. Search results could already contain such a name, and
the auditor will fetch links that visitors paste, so this must hold before step 3.

**How.** httpx 0.28.1 has no public setting for name resolution, so the fetcher's transport is
given an httpcore connection pool (httpcore 1.0.9) with a wrapped network backend. Checking at
connect time, then connecting to the checked address, also closes DNS rebinding (a name that
answers with a public address when checked and a private one when used). TLS still checks the
certificate against the host name. A test sends a real request through the client and fails if
a library upgrade bypasses the wrapper. The fetcher stops reading proxy settings from the
environment, because a proxy connection would otherwise be refused or would skip the check.

**Considered.** Resolving once before each request and then letting httpx connect: simpler, but
leaves the rebinding window open.

**Trade-off.** The wrapper sets one private attribute of httpx's transport (`_pool`), so an httpx
upgrade could break it. The test above turns that into a failing build rather than a silent
hole.

## D-036. Clean-up: old code removed, a README that describes today's code, `main` updated

**What.**
- Delete the first version: `backend/` (49 files), `ops/docker-compose.yml`, `QUICKSTART.md`,
  `CONTRIBUTING.md` and `docs/DEVELOPER_GUIDE.md`. They describe or run a system that no longer
  exists. Git history keeps all of it.
- Replace `README.md` with a short one that describes only what the code does today, with every
  number taken from `evals/results/`. It credits the first version's authors.
- Merge `rebuild` into `main` through a pull request, only when Aditya says so.
- Renaming the GitHub repository is Aditya's click in its settings; GitHub redirects the old
  address. The crawler's User-Agent and the docs are updated to the new name afterwards.

**Why.** Anyone opening the repository today sees a README for the old system, with features
the code does not have. That breaks rule 7 on the default branch.

**Considered.** Moving the old code to an `archive/` folder: it would still be read as part of
the project.

**Trade-off.** The README is written now and again after the auditor ships.

## D-037. The auditor's core, and testing it against human labels (step 2)

This entry covers two new modules: the auditor itself (`evidentia/audit.py` and its graph) and
its benchmark run (`evals/aggrefact.py`).

### Part A. What an audit does

**What.** Input: an AI tool's answer with its citations, as pasted text (markdown links, or
numbered markers like `[1]` with a list of sources). Output: every claim in the answer with one
label, the exact words on the cited page that the label rests on, and a scorecard for the answer.

The steps, as a LangGraph graph like the research pipeline:

1. **Parse (code).** Find every citation: inline links, and numbered markers matched to the
   source list. Each becomes a marker such as `[c1]` tied to one address.
2. **Split (Haiku).** The model breaks the answer into claims. For each claim it returns the
   sentence it came from and a self-contained version of the claim ("it grew 40%" becomes
   "global solar capacity grew 40% in 2023"). Code checks that the sentence is an exact span of
   the answer, and attaches the citation markers found inside or right after that span. So code
   decides which source a claim cites; the model does not.
3. **Fetch (code).** The existing fetcher: robots.txt, the per-site wait, the address guard
   (D-035), PDFs with pages.
4. **Find evidence (Sonnet).** For each claim and each page it cites, the model is shown the
   claim and the page (the whole page if it is short, else the passages Voyage's reranker ranks
   highest for that claim, with no index needed). It returns whether the page backs or
   contradicts the claim, with up to three quotes copied from the page. Up to three, not one,
   because a claim often rests on two sentences that are not next to each other.
5. **Quote check (code).** Each quote must be an exact span of the stored page text (rule 8),
   with the page number for PDFs. A quote that fails is dropped.
6. **Check (Sonnet).** A separate call that sees only the claim and the surviving quotes, as in
   the research pipeline, and labels it supported, partial, contradicted or unsupported. The
   auditor gets its own check prompt with the extra label. The research pipeline's checker is
   left unchanged, so its measured numbers still stand.
7. **Score (code).** Counts per label, the share of cited claims that are supported, dead
   links, tokens and dollars per step.

**Labels, decided by code from the steps above:**

| Label | When |
|---|---|
| supported | quotes found by code, checker says supported |
| partial | quotes found, checker says partial |
| contradicted | quotes found, checker says the quotes contradict the claim |
| not on the cited page | no quote passed the code check, or the checker says unsupported |
| dead link | the address answers 404 or 410, or the name does not resolve |
| could not check | the page exists but was not read: robots.txt, size limit, timeout, scanned PDF, not a public address |
| uncited | the claim has no citation |

The checker's word wins over the evidence finder's when they disagree, because the checker is
the independent one. When a claim cites several pages, each page's result is kept, and the
claim shows the best one, flagged when another cited page contradicts it. "Could not check" is
kept apart from "dead link" on purpose: a site that blocks crawlers has not lost its page.

The pasted answer is untrusted, like the pages: both go to models inside marked data blocks.

Limits per audit, in `config.py`: a cost cap (starting at $0.25), at most 25 claims and at most
10 cited pages. Every call is traced in Langfuse.

Entry point in step 2: `uv run python -m evidentia audit answer.md`, which prints each claim with
its label and quote. The site comes in step 3.

**Considered.**
- Letting the model assign citations to claims: simpler, but then a model decides what an
  answer cited.
- Checking the original sentence instead of a self-contained rewrite: "it grew 40%" cannot be
  checked on its own. The rewrite could change the meaning, so both are kept and the original
  sentence is what the reader sees next to the label.
- One quote per claim, as in the research pipeline: stricter, but it would mark claims that rest
  on two sentences as not found.
- Plain async code instead of LangGraph: less code, but the site's live event stream already
  works on graph events.

**Trade-off.** Two Sonnet calls per claim and page, about 1 to 2 cents each, so a 15-claim
answer costs roughly $0.15 to $0.30. Requiring exact quotes will miss support that is only
implied across a page, and the benchmark run below measures how often that happens.

### Part B. LLM-AggreFact run

**What.** LLM-AggreFact is a public set of claim and document pairs labelled by people
(`lytang/LLM-AggreFact` on Hugging Face). It has 11 sub-datasets (news summaries, meeting and
interview transcripts, Wikipedia, long-form answers, RAG outputs), a test split of 29,320 rows,
and a binary label (1 = supported, 0 = not).

- **Sample.** 50 rows from each sub-dataset of the test split, 550 in all, drawn with a fixed
  seed. The label mix inside each sub-dataset is kept as it is.
- **What runs.** Steps 4 to 6 of the auditor, given the benchmark's document as the "page".
  Parse, split and fetch are skipped, because the benchmark supplies the claim and the document.
  Supported counts as 1. Partial, contradicted and not-found count as 0, decided before the run.
  The result file also reports partial counted as 1.
- **Baseline.** On the same rows, the same model shown the whole document and asked only
  "supported or not". This tests whether making the model quote costs accuracy.
- **Metric.** Balanced accuracy for each sub-dataset, then the plain mean over the 11, with 95%
  bootstrap intervals. This follows the benchmark's own leaderboard, whose average is the plain
  mean of the 11 sub-datasets. I will confirm the metric in the MiniCheck paper while building.
  Also reported: how often an exact quote was found, and cost per claim.
- **No tuning on the test rows.** The prompts are fixed on 50 dev-split rows, then the test
  sample is run once.
- **Leaderboard figures are not used.** They are other people's numbers, so they do not appear
  on the site or in the README (rule 7). The comparison is against our own baseline.

**Order and cost** (estimates; each paid run needs Aditya's yes first):
1. Prompt fixing on 50 dev rows: about $0.30.
2. Haiku, auditor and baseline, 550 rows: about $0.50.
3. Sonnet, auditor and baseline, 550 rows: about $5 to $6. This run happens only after the
   Haiku result is in, and only if Aditya approves.

The eval's cost cap stops the command at the cap.

**Data handling.** The dataset is gated: Aditya accepts its terms on Hugging Face with his own
account and sets a read token in the `HF_TOKEN` environment variable. The code never prints or
logs it. The licence is CC BY-ND 4.0, and the terms allow use as an evaluation benchmark and not
for training. So the data is downloaded to a git-ignored cache and never committed. Result files
under `evals/results/` hold row numbers, labels, predictions and quote offsets, not the documents
or quote text. The download uses `huggingface_hub` and reads parquet with `pyarrow`; versions
are pinned after checking their current docs.

**Considered.**
- Our own 30 human labels first: still worth doing, but 30 labels cannot show much. The
  benchmark gives hundreds of labels at once.
- The whole test split: about 50 times the cost, for intervals that are already narrow enough
  to compare two systems.
- Quoting published leaderboard scores: ruled out by rule 7.

**Trade-off.** The benchmark is not the auditor's real job. Its documents are clean and come
supplied, and its claims are not split out of real answers. It measures steps 4 to 6 only. The
real-world audit (step 4) measures the rest.

### Done when (step 2)

- `uv run python -m evidentia audit answer.md` works, and tests with fakes cover every label in
  the table. `pytest` passes.
- The Haiku AggreFact results are under `evals/results/`, and the Sonnet results too if that run
  is approved.
- One live audit of a real answer that Aditya pastes from an AI tool he uses.

### What building it changed

- **Cap and concurrency.** The ledger reserves each call's worst case before making it. With
  the finder allowed 3,000 output tokens and 8 calls at once, a 5-claim test answer stopped at
  a $0.10 cap after spending $0.003. So the finder now gets 2,000 tokens, at most 4 calls run at
  once, and the cap per audit starts at $0.50 instead of $0.25. The same answer then cost
  $0.047: split $0.0002, find $0.0368, check $0.0098.
- **Dev rows.** The dev sample is 5 rows from each of the 11 sub-datasets, 55 in all, rather
  than 50.
- **Dead links.** The fetcher now tells "DNS says this name does not exist" apart from other
  network errors. A temporary DNS failure is not called a dead link.
- **Libraries.** `huggingface-hub` is pinned at 1.16.1, the version already locked through
  Voyage's tokenizer. 2.4.0 conflicts with DeepEval's `click` pin. `pyarrow` is 26.0.1. Both are
  in the evals group only.
- **Metric.** The MiniCheck paper (section 4.1) reports balanced accuracy, with no
  per-dataset threshold tuning in the main results.

### What the LLM-AggreFact run showed (Haiku)

Every number below is in `evals/results/aggrefact_*_haiku*.json`.

- **Dev rows, first prompts** (`aggrefact_dev_haiku_v1.json`): the auditor scored 0.718 and the
  direct baseline 0.794. On a re-run of the wrong rows, the checker's reasons showed multi-part
  summary claims left partial because no quote covered one part.
- **The one prompt fix.** The finder was told that its quotes together must cover every part of
  the claim, and the quote limit went from 3 to 5. The dev score moved to 0.725
  (`aggrefact_dev_haiku.json`), within noise. No further tuning: 55 rows cannot support it.
- **Test, 550 rows** (`aggrefact_test_haiku.json`):
  - Balanced accuracy: auditor 0.688 (0.646 to 0.728), direct 0.768 (0.721 to 0.811).
    Difference −0.080 (−0.120 to −0.038).
  - When each says supported, it is right 0.915 (auditor) and 0.910 (direct). Each rejects
    0.916 and 0.876 of unsupported rows, and accepts 0.523 and 0.730 of supported rows.
  - Auditor labels: 199 supported, 189 partial, 141 not found, 21 contradicted. Partial counted
    as supported gives 0.696 (0.648 to 0.748).
  - The worst sub-datasets for the auditor against direct are TofuEval-MediaS (0.483 against
    0.729) and XSum (0.554 against 0.747). Both have summary claims that blend several parts of
    a document.
  - Cost $0.38 for both systems: $0.00045 per claim for the auditor, $0.00024 for direct.

**What this means.** Requiring exact quotes makes the auditor strict. It rarely calls a wrong
claim supported, but it rejects many claims a person would accept, because they paraphrase or
combine parts of the page. On this benchmark that strictness loses to a plain yes/no. The claims
in step 3's real answers are split into single facts first, which should suit quoting better,
but that is untested. The Sonnet run stays separate and needs Aditya's yes. The README says the
auditor scores below the baseline.

## D-038. Make the auditor's flags trustworthy: two independent judges, and "needs a human"

**Goal.** The headline of this project will be the real-world audit (D-034, step 4): how often
the citations in ChatGPT, Perplexity and Gemini answers fail to back their sentences. That
number is only worth publishing if the auditor's flags are right. Today they are not.

**Why.** On 550 test rows (`evals/results/aggrefact_test_haiku.json`), the auditor and the
plain yes/no on the whole document fail in opposite ways:

- **The auditor is strict.** When it says supported it is right 0.915 of the time, but it
  accepts only 0.523 of the claims people accept.
- **The yes/no is lenient.** It accepts 0.730 of them and is right 0.910 of the time.
- **Flags.** Of the 351 rows the auditor did not call supported, people call only 185
  unsupported, so its flags are right about 53% of the time. The yes/no's flags are right about
  65% of the time.

Two judges that fail differently are worth more together than either alone.

### What changes

Each claim-page pair gets two judges:

1. **Quote judge.** As now: find quotes, check them word for word by code, then a checker that
   sees only the claim and the quotes.
2. **Page judge.** A separate call that sees the claim and the page and answers supported or
   not, with one sentence of reason. It sees the whole page if the page is short, otherwise the
   same best passages the finder sees. On the benchmark this is the direct baseline, now part
   of the product.

Code combines them:

| Quote judge | Page judge | Label |
|---|---|---|
| supported | supported | supported (with the exact quote as proof) |
| contradicted | not supported | contradicted (with the exact quote) |
| partial | not supported | partial |
| not on the page | not supported | not on the cited page |
| supported | not supported | **needs a human** |
| partial, not on the page, or contradicted | supported | **needs a human** |

"Needs a human" is a new label. It shows both judges' reasons, so a reader sees exactly what
they disagree on. Dead link, could not check and uncited are unchanged. A claim citing several
pages still shows its best result.

### How it is measured

Every number goes in the AggreFact result files, the report and the README. On the benchmark:
supported counts as 1; partial, contradicted and not-on-page count as 0; "needs a human" is
neither.

- **Flag precision.** Of the claims flagged (partial, contradicted or not on the page), the share
  people label unsupported.
- **Supported precision.** Of the claims called supported, the share people label supported.
- **Coverage.** The share of claims that get a verdict rather than "needs a human".
- **Balanced accuracy, two ways.** On the claims with a verdict. And over all claims with every
  "needs a human" counted as wrong, so abstaining can never make the score look better.
- **Per sub-dataset**, and next to the quote judge alone and the page judge alone on the same
  rows.

### Where it is tuned, and the finish line

**Practice set.** 550 rows from the dev split, 50 per sub-dataset, fixed seed. The test split is
not touched. At most four practice runs, each kept in its own result file:

1. **Two judges**, both Claude Haiku, as above.
2. **Two judges from two companies.** The page judge is OpenAI's `gpt-6-luna` instead of Haiku.
   It is priced the same as Haiku: $0.10 in and $0.50 out per million tokens (OpenAI's pricing
   page, read 2026-11-24). Models from different vendors should make fewer of the same
   mistakes, so agreement should mean more. It is kept only if it raises flag precision or
   coverage over run 1. The quote judge stays Claude in every run.
3. **Two judges, plus quote context.** The checker sees each quote together with its paragraph,
   up to about 600 characters. Most disagreements are expected where the quote judge says
   partial because a quote cannot be read alone. The context is marked as context; the quote
   is still what is checked by code.
4. **Two judges, plus single facts.** Each claim is split into single facts by the product's own
   splitter. Each fact goes through the quote judge, and code combines the facts' results.

   This run happens only if coverage is still under 0.70.

A change is kept only if it raises coverage without lowering flag precision or supported
precision by more than 0.01.

**Finish line, fixed now.** Measured once on a fresh test sample: 50 rows per sub-dataset, a new
seed, none of the rows from the first test run. All three must hold:

- flag precision at least 0.80;
- supported precision at least 0.93;
- coverage at least 0.70.

If any fails, the README says so with the numbers, and Aditya decides whether the real-world
audit goes ahead.

### Cost

With Haiku, and each paid run needs Aditya's yes first:

| Run | About |
|---|---|
| Practice, two judges | $0.40 |
| Practice, OpenAI page judge | $0.15 to $0.30 |
| Practice, plus quote context | $0.30 |
| Practice, plus single facts, if needed | $0.60 |
| Confirming run on fresh test rows | $0.50 to $0.80 |
| **Total** | **$1.35 to $2.40** |

A Sonnet confirming run is a separate question, at about $5 to $8.

In the product, the page judge adds one call per claim-page pair. A 15-claim answer would cost
roughly $0.30 to $0.45 with Sonnet, so the per-audit cap goes from $0.50 to $0.75.

**Considered.**

- **Tuning one judge further.** It moves the trade-off between strict and lenient but does not
  remove it. The first dev pass moved 0.718 to 0.725.
- **The page judge alone, with quotes attached afterwards.** About the baseline's accuracy, but
  its flags would be right only about 65% of the time, and the label would not rest on the quote
  shown.
- **Haiku and Sonnet as the two judges.** Same vendor, so their errors are likely more alike
  than Claude's and GPT's. Run 2 tests the stronger version of the same idea.
- **Training a classifier.** The benchmark's terms forbid training on it, and rule 12 rules out
  local models.

**Trade-off.**

- Every claim costs one more call.
- With two Claude judges, their mistakes are not fully independent. A GPT page judge reduces
  that but does not remove it, since both kinds of model are trained on much the same web.
  Agreement is evidence, not proof, which is why a person still checks a sample of flags in the
  real-world audit.
- **Self-preference.** In the real-world audit, a GPT judge would check ChatGPT's own answers and
  might go easier on them. If run 2 is kept, step 4 also audits a sample of ChatGPT answers with
  two Claude judges and reports any gap between the two setups.
- "Needs a human" is an honest answer but not a verdict. If coverage is low, the auditor is less
  useful, and the coverage finish line exists to catch that.
- The first test run stays in the record. The confirming run uses new rows rather than
  replacing it.

### Using OpenAI (applies to every OpenAI call from here on)

- **Key.** `OPENAI_API_KEY` from the environment only (rule 6). Aditya has set it.
- **Client.** The `openai` Python package, pinned at 3.58.0 (PyPI, read 2026-11-24). Structured
  answers use `client.responses.parse(..., text_format=<pydantic model>)`.
- **Code checks first.** Before writing against the SDK, the token-usage fields and the
  reasoning-effort parameter are checked against the installed package.
- **Prices.** OpenAI models get their own rows in `cost.py`. A model without a price is refused,
  as for Claude, so the cost cap holds for OpenAI calls too.
- **Tracing.** Every OpenAI call is traced in Langfuse, through the same tracer as the Claude
  calls (rule 11). I check Langfuse's current OpenAI integration before writing it.
- **Data blocks.** Page text goes inside the same marked data blocks with the same untrusted-data
  rule (rule 9).
- **Later, for step 4.** OpenAI's Responses API can answer with web search and citations
  (`url_citation` annotations with `start_index` and `end_index`). That is a way to collect
  ChatGPT-style answers. It gets its own decision entry and cost estimate.

### What the practice runs showed (550 dev rows, all Haiku unless named)

Every number below is in `evals/results/aggrefact_dev550_*.json`. Cost of all three runs: $0.77.

| Run | Flags right | "Supported" right | Coverage | Kept? |
|---|---|---|---|---|
| Quote judge alone (for comparison) | 0.560 | 0.922 | 1.000 | |
| Page judge alone (for comparison) | 0.684 | 0.890 | 1.000 | |
| 1. Two judges | 0.695 | 0.940 | 0.804 | the base |
| 2. Page judge is GPT (`gpt-6-luna`) | 0.706 | 0.926 | 0.809 | no |
| 3. Plus quote context | 0.709 | 0.929 | 0.847 | no |

- **Two judges help.** Run 1 beats either judge alone on flags and on "supported". Balanced
  accuracy on the claims with a verdict is 0.794.
- **The GPT judge made no clear difference.** "Supported" right fell 0.014, more than the 0.01
  allowed, so by the rule set in advance it is not kept. It cost $0.10 against Haiku's $0.15.
- **Context raised coverage by 0.043,** but "supported" right fell 0.0107, just over the 0.01
  allowed, so it is not kept either.
- **No run met the flag bar, for one reason.** In run 1, "partial" flags are right half the time
  (48 of 96). "Not on the cited page" flags are right 112 of 142 times, and "contradicted" 20 of
  21. Both judges agree a detail of those partial claims is not stated, but the people who
  labelled the benchmark accepted half of them anyway.

### Proposed change, waiting for Aditya's yes

Make "partial" its own verdict instead of a flag: "the page backs the main point but not every
detail". It is still shown, with the detail that is missing. Flags become "not on the cited
page" and "contradicted" only. The real-world audit's headline would then count only those two:
citations that fail outright.

On run 1 this gives flags right 0.810 (0.750 to 0.862), "supported" right 0.940 and coverage
0.804. That passes all three bars (`partial_as_its_own_verdict` in
`aggrefact_dev550_q-haiku_p-haiku.json`). Partial is 17% of claims.

If approved, the confirming run is run 1's setup on the fresh test rows (`test2`), scored with
this definition, once. It costs about $0.40.

**Trade-off.** The headline would then leave out claims where a detail is missing. It gets more
conservative and easier to defend, but it counts fewer failures. The change was found on
practice rows, which is what they are for. The fresh test rows have not been seen.

## D-039. A calibrated score, the model the product uses, and a person's word on "partial"

**What.** Four pieces of work. Each paid run gets Aditya's yes first. The confirming run on the
fresh test rows (D-038) waits until all four are done.

**Why.** D-038's practice runs showed three gaps:

- **Crude confidence.** Two judges agreeing is a single fixed trade-off between how often flags
  are right and how many claims get a verdict.
- **Wrong model.** Every number so far is for Haiku, but the product runs Sonnet.
- **"Partial" is unresolved.** On those claims both judges agree a detail is not stated, yet the
  benchmark's labellers accepted half of them. Only a person can say which side is right.

### A. Aditya labels the "partial" cases (built)

- **What is labelled.** `uv run python -m evals label-partial` shows 50 practice rows: 40 that
  both judges called partial, and 10 controls (5 supported, 5 not on the page), shuffled
  together. All are rows whose document is at most 8,000 characters, and the items are fixed in
  `evals/partial_items.json`.
- **What is shown.** Only the claim and the document. Not the judges' answers, not the
  benchmark's label, and not which group an item is in.
- **The answer and the scoring.** The answer is yes, no or unsure. `uv run python -m evals
  partial-labels` writes `evals/results/partial_labels.json`, which holds counts only. Only row
  numbers and answers are saved, never text.

**The rule, fixed now, before any labels exist.** It looks at the partial items Aditya answered
yes or no:

- **At least 60% "no".** The judges are right and the benchmark is lenient. In the product,
  partial counts as a failed citation ("the cited page does not state everything"). AggreFact
  results are reported both ways, with these labels as the evidence.
- **Otherwise.** Partial becomes its own verdict ("the page backs the main point but not every
  detail") and is not counted as a failure, as proposed in D-038.

The 10 controls show how often Aditya agrees with the benchmark on clear cases. That number is
reported next to the result.

### B. A calibrated score for the page judge

Two ways to get a probability that a claim is supported, both measured on the 550 practice rows:

1. **Token probability.** `gpt-6-luna` with reasoning switched off returns the probability of
   each output token, so the score is the probability of `true`. A probe on 2026-11-24 showed it
   works with reasoning off and is refused with reasoning on. This is one call per claim, about
   $0.05 for 550 rows.
2. **Repeated votes.** The Haiku page judge answers five times, and the score is the share of
   "supported" votes. That is four more runs on top of D-038's run 1, about $0.60.

Code then decides with two thresholds:
- **Supported** if the quote judge says supported and the score is at least `t_supported`.
- **Flag** if the quote judge says not on the page or contradicted, and the score is at most
  `t_flag`. Partial counts as a flag here too if part A says so.
- **Needs a human** otherwise.

The two thresholds are chosen on the practice rows: the largest coverage that still meets
D-038's bars (flags right 0.80, "supported" right 0.93). They are then fixed for the confirming
run. The report also shows the whole curve: flag precision against coverage as the thresholds
move. Two numbers chosen on 550 rows is a small risk of fitting the practice set, and the fresh
test rows check it.

### C. The model the product uses

Sonnet as both judges, once, on the 550 practice rows: about $5 for the quote judge and $3 for
the page judge (one vote; five Sonnet votes would cost about $15). It answers whether Sonnet is
worth about 20 times Haiku's price per token. If it is not clearly better, the product uses
Haiku for the judges and Sonnet only where it is measured to help. That is a separate yes.

### D. Product engineering

1. **The two judges run at the same time.** The page judge starts right after fetching, in
   parallel with find, quote check and check. It writes its own state field. A final `combine`
   node merges the two, and is deferred until both branches finish (`defer=True` in
   `StateGraph.add_node`, checked in langgraph 1.2.24). The live stream still shows each step
   as it finishes.
2. **Prompt caching.** Claims citing the same page re-send that page today, to two judges.
   - **One tag per audit.** Each audit uses one random data-block tag instead of one per call.
     It is still unguessable by a page's author, which is what the tag is for.
   - **Page before claim.** The page text comes before the claim, with a cache breakpoint after
     the page, so later claims on the same page read it from the cache.
   - **When it applies.** Claude 5.5 models cache prompts of at least 512 tokens (Claude API
     docs, read 2026-11-24).
   - **Measured.** The cost of one real answer, before and after.
3. **Cache prices per model.** `cost.py` prices every cache read at 0.1 times input. The docs
   give 0.05 for Sonnet 5.5, so the factor becomes per model. Without caching this changes no
   past number.
4. **The score is shown.** The page judge's score appears next to each label, so a reader sees
   how close a call was.

### Order and cost

| Step | About |
|---|---|
| A. Aditya's labels | free, 20 to 30 minutes of his time |
| B. Token-probability run, practice rows | $0.05 |
| B. Four more Haiku votes, practice rows | $0.60 |
| D. Engineering, plus one live audit to measure caching | $0.10 |
| C. Sonnet as both judges, practice rows (separate yes) | $8 |
| Confirming run on fresh test rows, chosen setup | $0.50 to $1 with Haiku, about $8 with Sonnet |

**Considered.**

- **Asking the model for a confidence percentage.** Stated confidence is known to be poorly
  calibrated. A token probability or a vote share is measured, not stated.
- **Fitting a small classifier on the judges' outputs.** The benchmark's terms forbid training
  on it, and two thresholds are enough to show the curve.
- **More prompt changes.** D-038's runs moved the numbers by less than the noise.
- **Skipping the labels.** Then "partial" would stay a matter of definition, and the README
  would have to say so.

**Trade-off.**

- Votes cost five times as many page-judge calls. The token probability is cheaper but only
  comes from `gpt-6-luna` with reasoning off, which may judge worse than with it on.
- Running the judges in parallel makes the graph harder to read: two branches and a join
  instead of one line.
- One tag per audit means a page cannot be cached across different audits. That is fine,
  because a cache entry lasts five minutes anyway.

### What D-039's work showed so far

Every number below is in `evals/results/aggrefact_dev550_*.json`, except the live-audit costs,
which come from two runs of `python -m evidentia audit`. Spent: $0.67 on the two practice runs
and about $0.25 on four live audits.

**The calibrated score did not fix the flags.** On the 550 practice rows:

| Page judge | Flags right, partial a flag | Flags right, partial its own verdict | "Supported" right | Coverage |
|---|---|---|---|---|
| One Haiku vote, plain agreement (D-038 run 1) | 0.695 | 0.810 | 0.940 | 0.804 |
| Five Haiku votes, best thresholds (0.25 / 0) | 0.729 | 0.809 | ≥ 0.93 | 0.766 |
| GPT token probability, best thresholds | 0.680 | 0.812 | 0.932 | 0.829 |

- **Why the scores add nothing.** Haiku's five votes were unanimous on 476 of 550 rows, and
  GPT's probabilities sit at 0 or 1. The judges are not unsure on the problem cases; they are
  sure, and they disagree with the benchmark's labellers. So this is a question of what
  "supported" means, not of confidence. Aditya's labels (part A) settle it.
- **Decision.** The page judge keeps one vote. Five cost five times as much ($0.74 against
  $0.15 for the page judge on 550 rows) for no real gain. The token-probability mode stays in
  the code, with its tests, but is off.

**The engineering changes work.**

- **Parallel judges.** The two judges now run at the same time, and `combine` runs once, after
  both.
- **Caching.** At first, caching mostly missed: the calls about one page all started together,
  so none of them found a cache entry yet. Now one call per page goes first and the rest
  follow. On a 6-claim answer citing one page, 58,415 of the 70,368 tokens the judges sent were
  read from the cache. The find and page-judge steps cost $0.0031 and $0.0030 per call, against
  $0.0062 and $0.0060 the run before. That run reused entries written minutes earlier, so a
  cold run also pays one write per page and judge.
- **Cache prices and tracing.** Cache tokens are now counted per step in the ledger, and cache
  reads are priced per model.
- **Trace volume.** Langfuse's free tier (50,000 units a month) was used up by the eval runs,
  because LangChain's wrapper steps made about nine of every ten observations. Those are no
  longer sent: one live audit went from 108 observations to 27, with every model call, tool
  call and graph step still traced.

**Still to do before the confirming run:**

1. Aditya's labels on the 50 items.
2. The Sonnet measurement (C), with its own yes.

### Sonnet as the judges (part C)

Measured on the 550 practice rows for $6.07 (`aggrefact_dev550_q-sonnet_p-sonnet.json`):

| Both judges | Flags right, partial a flag | Flags right, partial its own verdict | "Supported" right | Coverage | Cost per claim |
|---|---|---|---|---|---|
| Haiku | 0.695 | 0.810 | 0.940 | 0.804 | $0.0007 |
| Sonnet | 0.704 | 0.794 | 0.919 | 0.846 | $0.0110 |

Sonnet gives a verdict on more claims, but its "supported" verdicts are less often right, and
fall below the 0.93 bar. It costs 15 times as much per claim. The two mixed pairs (one judge of
each), scored from the saved rows at no cost, are no better than Haiku alone.

**Decision, as part C set in advance.** The auditor's judges are Haiku: finder, checker and page
judge. The auditor now has its own checker setting (`audit_checker_model`), so the research
pipeline's checker stays Sonnet and its measured numbers still hold. The per-audit cap goes from
$0.75 to $0.25. The Eiffel Tower test answer gives the same five labels with Haiku as it did with
Sonnet, for $0.008 instead of $0.045.

### A different route for part A, chosen by Aditya

Aditya supplied labels for all 50 items made by OpenAI Codex, an AI model, and not by a person.
They are kept apart in `evals/labels_partial_codex.jsonl`, marked as AI labels, and are never
reported as human labels. On their own they say "not supported" for 33 of the 40 partial cases,
and agree with the benchmark on 9 of the 10 controls.

**Spot-check, with the rule fixed before Aditya labels anything.**
- **What Aditya labels.** The first 15 items in the fixed order: 13 partial cases and 2 controls.
  The tool stops there.
- **If he and Codex give the same answer on at least 13 of the 15.** Codex's labels on the other
  35 items are used with his 15. The result says how many labels came from each, and the
  agreement rate.
- **Otherwise.** Codex's labels are not used, and the decision rests on Aditya's labels alone.
  If those are too few to decide, he labels more.
- **The decision itself is unchanged.** If at least 60% of the decided partial items are "not
  supported", partial counts as a failed citation; otherwise it is its own verdict.

### Part A closed without a person's labels: partial is not a failure

Aditya does not have time to label, so no person has labelled the partial cases. D-039 allowed
for this ("then partial would stay a matter of definition, and the README would have to say
so"). The definition is chosen on what holds up whoever is right, not on the benchmark:

- **Failed citation** means "not on the cited page" or "contradicted". The real-world audit's
  headline counts only these.
- **Partial** ("partly backed": the main point is backed, a detail is not) is its own verdict.
  It is reported separately with the missing detail, and never counted as a failure.

**Why this is safe either way.** If the judges are right that partial claims leave something
out, then leaving them out of the failures makes the headline a lower bound. If the benchmark's
labellers are right that those claims are fine, then they should not count as failures anyway.
Either way, "X% of citations fail outright" does not overstate.

**The confirming run, fixed now.** Two Haiku judges with one vote and thresholds of 0.5/0.5, as
in D-038 run 1. It goes on the `test2` sample (50 rows per sub-dataset, seed 20261125, no rows
from the first test run) and is scored with partial as its own verdict, against D-038's bars:
flags right at least 0.80, "supported" right at least 0.93, coverage at least 0.70. It is run
once. The result is reported whether it passes or not.

Codex's AI labels say "not supported" on 33 of 40 partial cases. They are mentioned only as an
AI's view (`labels_partial_codex.jsonl`) and not used for any decision.

### The confirming run: not passed

Run once on the `test2` sample, 550 test rows never used before, for $0.37
(`aggrefact_test2_q-haiku_p-haiku.json`). The setup and the bars are as fixed above.

| Two judges, partial its own verdict | Measured | Bar | Met? |
|---|---|---|---|
| Flags right | 0.774 (0.720 to 0.828) | 0.80 | no |
| "Supported" right | 0.910 (0.867 to 0.948) | 0.93 | no |
| Coverage | 0.816 | 0.70 | yes |

- **What failed.** Two of the three bars. The practice rows had given 0.810 and 0.940, so part of
  that was luck in the practice sample; the bar upper bounds still overlap the measured
  intervals.
- **What held.** Two judges beat either alone on the same unseen rows. Flags right: 0.774, against
  0.660 for the page judge and 0.543 for the quote judge. "Supported" right: 0.910, against
  0.892 and 0.904.
- **Reported as is.** The README states it with these numbers.
- **Next.** Aditya decides whether the real-world audit goes ahead with these measured rates
  shown next to its results, or whether the auditor is improved first.

## D-040. Tune the judges again, with a separate check before the confirming run

**What.** Two targeted changes, each aimed at one kind of error found on the practice rows.
Any change that helps is checked on a second, separate set of practice rows. Only a change that
survives that check is run once on fresh test rows.

**Why.** D-039's confirming run missed the bars: flags right 0.774 against 0.80, "supported" right
0.910 against 0.93. Reading the errors on the practice rows (console only, nothing saved) showed
two opposite problems:

- **Wrong "supported" (11 on the practice rows).** The checker accepts quotes that are close to
  the claim but shift what it is about. "A mirror diameter of 2.4 metres" was taken to back "the
  telescope is 2.4 m in diameter". A name "meaning Saint Joseph of the Fields" was taken to back
  "named after Saint Joseph". One striker's comment was taken to back "they credit their success
  to…". The benchmark's labellers reject these, and a citation checker should too.
- **Wrong flags (31 on the practice rows; 22 of them in ExpertQA and RAGTruth).** Both judges say
  "not supported" where people say supported. Many of these claims paraphrase, sum up or draw a
  plain conclusion from the page. The papers do not show that those two sub-datasets are
  labelled differently, so they stay in.
- **What was already tried.** More judges, Sonnet, votes and probabilities moved flags right only
  from 0.810 to about 0.82 on the practice rows. The problem is what each judge counts as
  support, not how many judges there are.

### The changes

1. **A graded page judge (one call, as now).** It answers one of four: the page *states* the
   claim; the page *implies* it (a fair paraphrase, a summary, or a plain conclusion from what it
   says); it *does not support* it; or it *contradicts* it. Code then decides:
   - **Supported:** the quote judge says supported, and the page judge says states. Implies is
     not enough.
   - **A flag:** the quote judge says not on the page or contradicted, and the page judge says
     does not support or contradicts.
   - **Partial:** the quote judge says partial, and the page judge says does not support or
     contradicts, as before.
   - **Needs a human:** everything else, including implies against a flag.

   This aims at both errors at once. Supported gets stricter, and a flag is no longer raised
   when the page plainly implies the claim.
2. **Precision rules for the quote judge's checker.** Three general rules are added to its
   prompt, each with no example taken from the benchmark:
   - **The same thing.** The claim must be about the same thing as the quote. A part is not the
     whole, a component is not the system, and a measurement of one thing is not a measurement
     of another.
   - **The same scope.** A statement by or about one person or source does not back a claim
     about a group.
   - **The same relation.** "Meaning X", "named X", "named after X" and "like X" are different
     claims.

   This aims at the wrong supported verdicts.

### Tune, check, confirm

- **Tune** on the 550 practice rows already used (`dev550`). Each change is run alone, then both
  together. A change is kept only if it raises flags right or "supported" right, without lowering
  the other or coverage by more than 0.01, as before.
- **Check** the kept version once on a second practice set: `dev550b`, 50 rows per sub-dataset from
  the dev split, seed 20261127, none of them in `dev550`. It goes ahead only if it still beats
  D-039's setup there on flags right and "supported" right.
- **Confirm** once on `test3`: 50 rows per sub-dataset from the test split, seed 20261128, none of
  them in `test` or `test2`. The bars are unchanged: flags right 0.80, "supported" right 0.93,
  coverage 0.70, with partial as its own verdict. The result is reported either way.

### Cost

All with Haiku, and each paid run needs Aditya's yes first, under a cap:

| Run | About |
|---|---|
| Graded page judge on `dev550` | $0.15 |
| Checker rules on `dev550` (the quote judge runs again) | $0.25 |
| The kept version on `dev550b`, both judges | $0.40 |
| The kept version on `test3`, both judges | $0.40 |
| **Total** | **about $1.20** |

**Considered.**

- **Dropping ExpertQA and RAGTruth from the score.** The papers do not support it, as above.
- **Prompt examples taken from the benchmark rows.** That would fit those rows. The rules are
  written in general terms instead.
- **Two separate page-judge calls (one strict, one lenient).** It doubles the cost, and one
  graded answer gives the same two thresholds.

**Trade-off.** "Implies" will move some claims from a verdict to "needs a human", so coverage
may fall; the 0.70 bar is there to catch that. Prompt rules are tuning, and the second practice
set is there to catch tuning that only fits the first one.

### What D-040 found

Spent: $0.79 (graded judge $0.15, checker rules $0.25, second practice set $0.39 + $0.14 less
what was reused). Every number below is in `evals/results/aggrefact_dev550*_*.json`, except the
pooled figures, which come from saved rows and are not yet in a result file.

**Tuning on `dev550`**, with partial as its own verdict:

| Version | Flags right | "Supported" right | Coverage | Kept? |
|---|---|---|---|---|
| D-039 setup | 0.810 | 0.940 | 0.804 | the base |
| Checker rules | 0.802 | 0.939 | 0.771 | no: worse on all three |
| Graded page judge, as designed | 0.837 | 0.946 | 0.675 | no: coverage fell 0.13 |
| Graded, "implies" keeps partial as partial | 0.837 | 0.946 | 0.816 | yes, for the check |
| Graded plus rules | 0.829 | 0.942 | 0.796 | no |

The kept reading of "implies" was chosen from four, on the same rows. The rule behind it: an
implying page backs the main point, and that is what partial says. "Implies" is still not
enough for supported, and it still blocks a flag.

**The check on `dev550b`** (550 dev rows never used):

| Version | Flags right | "Supported" right | Coverage |
|---|---|---|---|
| D-039 setup | 0.839 (0.790 to 0.886) | 0.943 (0.905 to 0.975) | 0.829 |
| Graded page judge | 0.861 (0.813 to 0.906) | 0.938 (0.899 to 0.973) | 0.807 |

The graded judge wins on flags and loses slightly on "supported", so by the rule fixed above it
does not go on to `test3`. It stays in the code, switched off (`page_judge_graded`).

**What the three samples show together.** The same D-039 setup scored 0.810, 0.839 and 0.774 for
flags right on three separate sets of 550 rows. That spread comes from which rows are drawn, and
it is as large as any change tried in D-039 or D-040. Pooled over the 1,100 rows never used to
tune it (`dev550b` and `test2`):

- flags right **0.806** (0.767 to 0.844);
- "supported" right **0.926** (0.897 to 0.951);
- coverage **0.823**.

Both bars lie inside those intervals. The auditor's true rates sit at the bars, and a single run
of 550 rows cannot say on which side.
