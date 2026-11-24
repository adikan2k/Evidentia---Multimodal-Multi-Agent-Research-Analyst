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
