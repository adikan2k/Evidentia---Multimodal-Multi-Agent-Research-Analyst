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
| Flags right | 0.773 (0.720 to 0.828) | 0.80 | no |
| "Supported" right | 0.910 (0.867 to 0.948) | 0.93 | no |
| Coverage | 0.816 | 0.70 | yes |

- **What failed.** Two of the three bars. The practice rows had given 0.810 and 0.940, so part of
  that was luck in the practice sample; the bar upper bounds still overlap the measured
  intervals.
- **What held.** Two judges beat either alone on the same unseen rows. Flags right: 0.773, against
  0.660 for the page judge and 0.543 for the quote judge. "Supported" right: 0.910, against
  0.892 and 0.904.
- **Reported as is.** The README states it with these numbers.
- **Next.** Aditya decides whether the real-world audit goes ahead with these measured rates
  shown next to its results, or whether the auditor is improved first.

## D-040. Tune the judges again, with a separate check before the confirming run

**What.** Two targeted changes, each aimed at one kind of error found on the practice rows.
Any change that helps is checked on a second, separate set of practice rows. Only a change that
survives that check is run once on fresh test rows.

**Why.** D-039's confirming run missed the bars: flags right 0.773 against 0.80, "supported" right
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

**What the three samples show together.** The same D-039 setup scored 0.810, 0.839 and 0.773 for
flags right on three separate sets of 550 rows. That spread comes from which rows are drawn, and
it is as large as any change tried in D-039 or D-040. Pooled over the 1,100 rows never used to
tune it (`dev550b` and `test2`):

- flags right **0.806** (0.767 to 0.844);
- "supported" right **0.926** (0.897 to 0.951);
- coverage **0.823**.

Both bars lie inside those intervals. The auditor's true rates sit at the bars, and a single run
of 550 rows cannot say on which side.

## D-041. The audit page on the site (D-034, step 3)

**What.** A page where a visitor pastes an AI tool's answer with its citations and watches
Evidentia check it, sentence by sentence. Each claim shows the exact words on the cited page,
what both judges said, and a scorecard. Next to the scorecard sit the auditor's measured error
rates. Recorded audits play for free; live audits are limited the same way live research runs
are.

**Why.** This is the demo. It is also the tool the real-world audit (step 4) uses, and it is the
first thing anyone tries. The auditor is measured (D-038 to D-040), so its results can be shown
together with how often they are right.

### API

- **`POST /audits`** takes `{answer}`, 20 to 12,000 characters. It streams server-sent events,
  as `/runs` does:
  - `node`, as each audit step finishes, with only what that step found: the claims and their
    places in the answer; which pages were read, and why others were not; and the verdicts;
  - then `report`: every claim with its label, its quotes with the text around them, both
    judges' reasons, and the scorecard;
  - or `error`.
- **A new event builder.** `evidentia/audit/events.py` builds those events, as
  `evidentia/events.py` does for research runs.
- **Limits** (`limits.py`). The audits share the daily budget ($1.00) with live runs and checks.
  On top of that, each address gets at most 5 audits a day, at most 2 audits run at once, $0.05
  is reserved per audit, and each audit has a $0.25 cap. The Haiku judges cost about $0.01 for a
  15-claim answer (D-039), so the daily budget allows about 100 audits.
- **Safety, as it already stands.** Visitors' links go through the fetcher's rules: public
  addresses only, checked after DNS (D-035); robots.txt; the wait per site; size limits; and at
  most 10 pages per audit. The pasted answer and the pages go to the models as untrusted data in
  marked blocks.

### The page (`/audit`, Next.js, the site's existing style, D-024)

1. **Paste.** One text box, an "Audit" button, and a picker of recorded audits.
2. **Watch it run.** The answer is shown as text.
   - As steps finish, each claim's sentence is underlined.
   - It turns its label's colour when both judges have ruled.
   - A strip shows the steps (parse, split, fetch, the two judges, combine) as they really
     finish. No animation runs ahead of the events.
3. **Open a claim.** Clicking a sentence opens the side pane, as for research runs:
   - the cited page;
   - the exact quotes, with their context and page numbers for PDFs;
   - the quote judge's and the page judge's reasons;
   - for "needs a human", what the two disagree on.
4. **Scorecard.** Failed outright (not on the cited page, or contradicted), partly backed, needs a
   human, supported, dead links, could not check, uncited, and the cost.
5. **"How often is this right?"** Flags right 0.806 (0.767 to 0.844), "supported" right 0.926
   (0.897 to 0.951), and 18% of claims sent to a person, all on 1,100 human-labelled benchmark
   rows. They are read from `evals/results/` through the site's data file, never typed in, with
   a link to the method.

### Recorded audits

The page plays three recorded audits without spending anything. Their answers are made by
OpenAI's Responses API with web search (`gpt-6.2-sol`, about $0.02 to $0.05 each). Each is
labelled with the model, "with web search", and the date. Three questions of general interest,
picked before seeing any answer. Recording the three audits costs about $0.03. This is not the
real-world audit; it only gives the page real content. It needs one OpenAI client call with web
search: the current docs are checked first, and the call is traced and priced like the others.

### Tests and checks

- API tests with fake services: the event order, the limits, the refusals, and that a closed tab
  stops the audit.
- Event-builder tests: the sentence offsets match the answer text, and no secret or page text
  beyond the quotes and their context goes out.
- `npm run build` and `npm run lint`, then a look in the browser at desktop and phone widths.

**Deploy.** The API to Cloud Run, then the site through Vercel. Both only when Aditya says to push.

**Cost.** About $0.25 in all: the three recorded answers and their audits, and a few live audits
while building.

**Considered.**

- **Folding audits into `/runs`:** the two have different inputs and events, so they are kept
  apart.
- **Collecting the recorded answers by hand:** Aditya has no time for it. API answers are
  repeatable and dated.
- **Live audits only:** the page would cost money every time someone opened it, and would break
  when the daily budget runs out.

**Trade-off.** Recorded answers from the API are not the same as answers in the ChatGPT app,
which can differ. The labels say exactly where they came from. The daily budget is shared with
research runs, so a busy day for one leaves less for the other.

### What recording the first audits changed (D-041)

- **Numbered list items that cite a page now stay in the answer.** The parser used to read
  "1. **A bright galaxy...** ([stsci.edu](...))" as an entry in a source list and drop it. A
  numbered line now counts as a source only if it is an address with at most a short title and
  no markdown link.
- **A page is not cited twice.** When the model's text already holds a link inline, the answer
  collector adds no numbered marker for it.
- **Paragraph citations.** The chat tool puts one citation at the end of a paragraph for the
  whole of it. So a sentence with no citation of its own now takes the citation that closes its
  paragraph. It is marked "cited at the end of its paragraph" (`cited_by: paragraph`), so the
  reader can see the citation was not attached to that sentence. This is the charitable reading
  of the tool being audited. Without it, 6 of the 9 claims in one answer came out "uncited". The
  benchmark numbers are unaffected, because that eval gives each claim its document directly.
- **Cost.** The API's answers cost $0.06 to $0.11 each, not $0.02 to $0.05, so recording costs
  about $0.45 in all, against the $0.25 estimate.
- **One recording replaced.** One answer cited only journal pages (doi.org, bmj.com) that refuse
  automated fetches (HTTP 403). It is replaced by a different question. Pages like these are a
  real limit of auditing, and the real-world audit will count them as "could not check".

## D-042. The real-world audit: how often do AI tools' citations hold up? (D-034, step 4)

**What.** Ask two AI tools the same 100 questions, with web search on, through their APIs.
Audit every answer with the auditor as shipped. Publish the results on the site and in the
repository, next to the auditor's own measured error rates.

**Why.** This is the project's headline: a finding about real AI products, made with a tool
that has been measured against people's labels (D-038 to D-040). The audit page (D-041) lets
anyone check one answer; this checks many, in the same way, under a plan fixed in advance.

### The tools

| Tool | How | Price tier |
|---|---|---|
| OpenAI | `gpt-6.2-sol` with the Responses API's `web_search` tool, as in D-041 | $2 / $10 per million tokens, plus $10 per 1,000 searches |
| Anthropic | Claude Sonnet 5.5 with the Messages API's web search tool | $2 / $10 per million tokens, plus $10 per 1,000 searches |

- **Same price tier, same treatment.** Both get the question exactly as written, with no extra
  instructions, and up to 2,000 output tokens. Each question is asked once per tool.
- **Turning answers into the auditor's input.** Each tool's citations are turned into links or
  numbered markers, as D-041's collector does for OpenAI. The Claude version is new: its current
  docs are checked first, and it gets tests.
- **More tools only with Aditya's keys and a yes.** Perplexity's Sonar API and Gemini with Google
  Search grounding are left out unless Aditya provides keys. Each would get its own docs check
  and cost estimate.
- **Not the consumer apps.** API answers are not the same as the ChatGPT or Claude apps, which add
  their own instructions. The results page says "the API with web search", never "ChatGPT" or
  "Claude.ai".

### The questions, fixed before any answer is made

They are committed to the repository before the first answer is requested.

1. **50 from Natural Questions.** These are real anonymised Google searches, from the dev split,
   CC BY-SA 3.0, with attribution. They are drawn with a fixed seed from questions where
   annotators marked a paragraph-length answer, so a one-word answer is unlikely. Only one dev
   file is downloaded, about 190 MB, to the git-ignored cache.
2. **50 about 2025 and 2026.** 10 in each of science, health, technology, economy, and sport and
   culture. Written so that answering needs several checkable facts and a current web search.

**Why both.** The first half cannot be picked to suit the result. The second half tests the
case where tools most need the web and are most likely to slip, and its questions were written
before seeing any answer.

### What is measured, fixed now

For each tool:

- **Headline.** Of the claims that get a verdict, the share whose citation fails outright: not
  on the cited page, or contradicted. With a 95% interval, bootstrapped over questions, since
  claims from one answer are not independent.
- **Also reported:**
  - partly backed, needs a human, could not check (robots.txt, refused, paywalled), dead links,
    and uncited claims, each as a share;
  - claims and cited pages per answer;
  - cost per answer.
- **Between the tools.** The difference on the headline, paired by question, with its interval.
  Also each measure split by question source (Natural Questions against 2025 and 2026).
- **Shown with the auditor's own rates.** Flags right 81%, "supported" right 93%, 18% sent to a
  human (D-040). No correction is applied to the tools' figures: rates measured on the benchmark
  may not hold for these answers, and the page says so.

**Self-preference check.** Our judges are Claude models, and one tool is Claude. So every answer
is also audited with OpenAI's `gpt-6-luna` as the page judge instead of Haiku. That costs about
$0.002 an answer, and both results are reported. If the comparison between the tools changes
with the judge's maker, the page says so.

### Where it is published

- **`evals/results/realworld.json`.** Every number, written by code.
- **`evals/realworld/`.** The questions, every answer, and every audit. Quotes are kept with their
  surrounding context only, never whole pages.
- **A Findings page on the site.**
  - Each tool's headline and other measures, with intervals.
  - Example audits chosen by a rule fixed now: every contradicted claim, then 5 "not on the cited
    page" claims drawn with a fixed seed. Each opens like a recorded audit.
  - A link to the data and the method.
- **The README** gets a section with the headline, its interval and the limits below.

### Order and cost

| Step | About |
|---|---|
| Pilot: 10 questions × 2 tools, to measure the real cost and catch problems | $2 |
| Full run: the other 90 questions × 2 tools (answers) | $13 to $18 |
| Audits, about $0.01 each, plus the GPT page-judge re-audit | $2.50 |
| **Total** | **about $17 to $23** |

- **Answer cost.** OpenAI's three recorded answers cost $0.074 on average. Claude's is unmeasured
  and is measured in the pilot.
- **Approvals.** The full run needs a separate yes after the pilot, with the measured cost. Every
  command has a cap.
- **Fetching.** About 1,500 page fetches, with robots.txt obeyed and a wait between requests to
  the same site.
- **Tracing.** About 6,000 Langfuse units. The free tier is already used up this month, so traces
  may be dropped until 1 December unless Aditya moves to the paid plan ($29 a month). That is his
  call. The README will say if any part of the run went untraced.

**Considered.**

- **Answers pasted by hand from the consumer apps.** Truer to what people see, but Aditya has no
  time for it, and it cannot be repeated.
- **More tools now.** They need keys Aditya has not given.
- **More questions.** Twice the cost, for intervals about a third narrower.
- **A person checking a sample of flags.** No time. The benchmark rates stand in for it, and the
  page says so.

**Trade-off.** One answer per question per tool, so run-to-run variation is not measured. Half
the questions were written by this project; they are fixed and published before any answer
exists. The auditor is right about 81% of the time on flags, so a tool's failure share is an
estimate with that error in it, and the page shows both numbers side by side.

### Done when

- The questions are committed before any answer exists.
- The pilot is run and its cost reported.
- The full run is done on Aditya's yes.
- `evals/results/realworld.json` is written by code.
- The Findings page is built and checked in the browser.
- The README section is written.
- The tests pass, including those for the Claude answer collector.

### What the first pilot found (D-042), and what changed before any full run

The pilot ran the 10 fixed questions through both tools for $1.03 (answers $0.80, audits about
$0.004 each), plus about $0.30 of single calls to find the causes. Its answers, audits and
result file are kept in `evals/realworld/pilot_v1/` and `evals/results/realworld_pilot_v1.json`.
They are not used for any finding, because three problems in this project's pipeline made them
wrong:

1. **Claude's answers came with no citations.** All 154 of its claims were counted "uncited".
   The newer search tool (`web_search_20260209`) filters results with code, and its final text
   carries no citation data. A single test call confirmed it. The older `web_search_20250305`,
   still offered for this model, attaches each citation to its text block. Claude now uses it.
   Both tools now get up to 4,000 output tokens instead of 2,000, because both think before
   they write and the thinking counts. Each answer now records how it ended, so a cut-off
   answer can be seen.
2. **A blocked page was counted as a dead link.** FDA's server sends this fetcher to an "FDA
   Apology" page that ends in a 404, while the same address returns 200 to other clients. Now
   only a 404 or 410 on the address itself, with no redirect, counts as a dead link. A 404
   reached through a redirect is "could not check". The Met Office PDF that answered 404 to every
   client stays a dead link.
3. **Paragraph citations turned uncited sentences into failures.** Under D-041's charitable
   reading, a sentence with no citation of its own takes the one closing its paragraph. In the
   pilot, that page often covered only the paragraph's last sentence, so the earlier sentences
   were scored as failures instead of "uncited". **The headline now counts only claims whose own
   sentence carries a citation.** Paragraph-cited claims are reported apart with their own
   failure share, and so is everything together. This changes a measure D-042 fixed in advance.
   It is recorded here before the full run, and the first pilot's numbers are kept for anyone to
   compare.

Not changed: tracking parameters that OpenAI adds to its links (`utm_source=openai`). The same
addresses with those parameters returned 200 when tested.

**Next.** The pilot runs again with these fixes, about $1.10, and needs Aditya's yes because it
goes past the $2 first estimated. The full run follows only after that, with its own yes and
its measured cost.

### The pilot, run again with the fixes (D-042)

The cost: $0.91 for the answers and audits, $0.16 to re-audit after the fourth fix, and about $0.35
of single calls to find the causes. All the pilot runs came to about $2.45. The result is in
`evals/results/realworld_pilot.json`.

**A fourth fix, from reading the cited pages.** Five pages came back with only 311 to 1,552
characters of text: a gallery, a product page, a sports page and others built in the browser by
scripts. Claims cited to those pages looked "not on the cited page" when the page was simply not
read. An audit now treats a page with under 2,000 characters of text as not read ("could not
check"). The research pipeline keeps its own lower limit.

**What the 10 pilot questions show.** Too few to compare the tools with any confidence; this was
only a check of the pipeline.

- **Claims whose own citation fails outright**, with the Haiku page judge:
  - OpenAI: 35% of 26 claims, interval 12% to 63%.
  - Claude: 16% of 38 claims, interval 0% to 45%.
- **With the GPT page judge**, the same figures are 41% and 13%. So there is no sign that the
  Claude judges are easier on Claude. The GPT judge is the one that is harder on OpenAI.
- **Uncited claims.** OpenAI 26%, Claude 53%. Claude often answers without searching: 5 of its
  10 answers cite nothing.
- **Pages that could not be read.** About 16% to 24% of cited claims: 403 refusals, redirects to
  block pages, robots.txt, and too little text.
- **Cost.** $0.045 per OpenAI answer, $0.030 per Claude answer, and about $0.004 per audit.
- **Spot check.** The flags read by hand hold up. One example: the claim "the Virgo cluster
  contains about 10 million galaxies" cites a page saying the image holds about 10 million
  galaxies, of which a few thousand form the cluster.

**Full run estimate, from the measured costs.** The other 90 questions × 2 tools: about $6.70 for
answers and $1.50 for the two audits of each. About $8.20 in all, under a $12 cap. It needs
Aditya's yes.

### The full run (D-042)

All 100 questions × 2 tools were answered, and each answer audited twice, for $7.24. Finishing
one audit cost another $0.21; that answer had twice hit Voyage's limit of 2 million rerank tokens
a minute. The pilot answers were reused. Every number below is in `evals/results/realworld.json`.

**Two engineering changes made during the run.**

- **The reranker now runs under the same four-at-a-time gate as the model calls.**
- **Very long pages are shortlisted first.** For a page over about 100 passages, the 100 passages
  sharing the most words with the claim are picked in code, then reranked. This came from an
  answer citing the full text of a law, over a megabyte.
- **Where it applies.** Only that one audit (economy-06, OpenAI) ran with the shortlist. It
  changes nothing for pages under about 120,000 characters.

**Results with the page judge as shipped (Haiku).** The headline counts only claims whose own
sentence carries a citation.

| | OpenAI `gpt-6.2-sol` + web search | Claude Sonnet 5.5 + web search |
|---|---|---|
| Own-cited claims that fail outright | **38.0%** (29.1% to 46.4%), of 187 | **7.9%** (4.5% to 11.9%), of 382 |
| Paragraph-cited claims that fail | 43.4%, of 99 | 17.0%, of 59 |
| Claims with no citation at all | 13.0% | 44.0% |
| Cited claims whose page could not be read | 32.1% | 19.3% |
| Claims per answer / cited pages per answer | 6.5 / 1.6 | 15.2 / 2.9 |
| Contradicted claims (all 100 answers) | 5 | 7 |
| Cost per answer / per audit | $0.033 / $0.004 | $0.032 / $0.004 |

- **The difference.** OpenAI minus Claude on the headline is **30.1 points**, interval 21.1 to 38.3,
  paired by question.
- **With the GPT page judge.** 45.3% against 7.8%, a difference of 37.5 points (27.1 to 47.1). So the
  gap is not the Claude judges favouring Claude: the judge from OpenAI's own maker is harder on
  OpenAI's answers.
- **Both question sources show it.** On the 2025–2026 questions: 37.3% against 8.1%. On Natural
  Questions: 40.0% against 6.0%, on fewer claims, 45 and 50.
- **Uncited claims.** Claude leaves far more claims uncited: 44% against 13%. On the Natural
  Questions half, 76% of Claude's claims cite nothing, because it often answers without
  searching. So the two tools fail in different ways. OpenAI cites more of what it says, but its
  citations often do not hold it. Claude cites less, but what it cites mostly holds.

**Spot check.** Ten of OpenAI's failed own-cited claims, drawn with a fixed seed, were checked
against the re-fetched pages. All ten pages had been read in full (2,000 to 30,000 characters),
and the claim's facts are not on them. Some examples:

- "ended new Grad PLUS loans" cited to an IRS FAQ about energy credits;
- "the chance peaked at 2.8% according to ESA on February 18" cited to a NASA page saying NASA
  put it at 3.1% on that day;
- an "extension in August" cited to the May joint statement.

This check was made by Claude Code, a model, not by a person.

**Limits, for the README and the Findings page.**

- These are API answers, not the consumer apps.
- Each question was asked once per tool.
- Half the questions were written by this project; they were fixed and committed before any
  answer existed.
- The auditor's flags are right about 81% of the time on the benchmark (D-040). No person has
  checked these flags.
- Pages that could not be read (32% and 19% of cited claims) are left out of the headline.
- **Tracing.** Langfuse accepted this run's traces, despite the free tier being used up this
  month.

## D-043. The plan in answer to the review of 24 November 2026

**What.** An outside review of the site and the code (written as a hiring manager, at commit
`a4c0aa5`) listed 20 items. This entry fixes the order they are done in, who does each, and what
each costs. It is a plan only. Every new module still gets its own entry before it is built.

**Why.** The review's verdict: the engineering is strong, but two things decide an interview.
Whether the OpenAI-against-Claude finding survives a hostile reading, and what Aditya did himself.
Both are answered by work in phase 1 and phase 4, so the order below puts those first.

**Checked before planning.** Two of the review's claims were tested and hold:
- A source list pasted on one line makes the parser drop the markers. The claim is then judged
  against the wrong page.
- Claude's searches were capped at 5 per answer and OpenAI's were not.

**Marked [ADITYA].** These need Aditya's own hands. No model does them, and no model's labels
stand in for his.

### Phase 0. Wrong verdicts and the front door (hours, free)

| Review item | Work | Who |
|---|---|---|
| 5 | Parse source lists written on one line | Claude Code |
| 5 | A marker with no source, or a source list that cannot be read, gives the new label "could not read the citation". It never gives "not on the cited page", and the paragraph rule never borrows from a source list | Claude Code |
| 5 | Tests in the shapes chat apps paste (numbered, footnote, inline links; with and without line breaks) | Claude Code, from formats I know |
| 5 | Three or four real pastes from the apps, to add as fixtures | **[ADITYA]**, 5 minutes, optional |
| 5, 10 | The Audit and Run buttons work at once and say "starting" while the server wakes. The dead click in the review was most likely the button disabled during a 13-second cold start | Claude Code |
| 6 | The README opens with the auditor; the research agent comes second | Claude Code |
| 6 | Merge the pull request into `main`; switch Vercel's production branch | **[ADITYA]** says when |
| 6 | Rename the repository to `evidentia`; then the User-Agent and docs are updated | **[ADITYA]** clicks, then Claude Code |

### Phase 1. Can the finding survive a hostile reading? (review items 1 to 4)

Nothing about the real-world audit goes on the site until this phase is done.

**1a. Free analyses from the saved audits, added to `evals/results/realworld.json`:**
- **Both denominators.** The failure rate among checkable cited claims (38.0% and 7.9%), and the
  share of all claims verified against a cited page (18.5% and 24.6% by the review's count).
- **All eight labels** for each tool, as counts and shares.
- **Bounds.** The headline if every unread page had supported its claim, and if none had.
- **Which sites refuse**, by tool and by reason.

**1b. A person checks the flags (item 1). [ADITYA], about two hours.**
- **The tool.** A blind labelling tool, built by Claude Code with its own decision entry.
- **The sample.** 100 claims drawn with a fixed seed: 25 failed and 25 supported from each tool,
  all with their own citation.
- **What is shown.** The claim and the cited page, opened in the browser. Tracking parameters such
  as `utm_source=openai` are stripped from the address, because they would give the tool away.
  Not shown: the tool's name, the auditor's verdict, or the judges' reasons.
- **What is reported.** For each tool, the share of flags upheld and of "supported" verdicts
  upheld, with intervals. The headline is not adjusted. The findings page and README state "N
  flags checked by hand, X% upheld."
- **If Aditya cannot do it.** The finding is published only with "no flag was checked by a
  person" in its first screen. That is a much weaker claim, and it leaves the review's first
  question open.

**1c. Treat the two tools alike (item 3).** One paid run of about $4.50, with Aditya's yes first.
- **The run.** 20 questions, chosen by a fixed seed, are asked three more times of each tool.
  Both tools are capped at 5 searches. The run saves how many searches each answer used, and
  OpenAI's raw citation offsets.
- **What it gives.** The spread between repeated answers. Whether the search cap changes
  OpenAI's result. The data for a code test that every marker sits right after the span its
  annotation covers. A person reading 20 answers against their markers would be stronger; that is
  **[ADITYA]**, optional.
- **Disclosed on the findings page, not only here.** Claude ran on the older search tool
  (`web_search_20250305`), because the newer one returns no citation data.

**1d. Pages that could not be read (item 4).**
- **Script-built pages.** A second reader, with its own decision entry, renders the page in a
  headless browser where robots.txt allows. It is used only for pages that answered but gave too
  little text. The audits of those pages are run again, and the report says how far the headline
  moves. About $1.
- **Refusals.** Pages that refused the fetcher (403, or a redirect to a block page) stay unread. A
  site that refuses a crawler has said no, and getting round that with a browser's identity is
  not something this project does. Those pages are covered by the bounds in 1a.

**1e. The findings page**, built only after 1a to 1d.
- **First screen.** A stacked bar per tool over all claims and all labels. Both readings of the
  result. The plain statement that the tools fail differently. The hand-check line. The limits.
- **Below.** Examples chosen by D-042's rule, each with its own address.

### Phase 2. The site (review items 7 to 10, 13, 14)

One decision entry for the set, then built and checked in the browser at desktop and phone widths.

- **Home (7).** Audit becomes the home page: what this is, the finding, "paste an answer". The
  research agent moves to its own tab.
- **Reading a result (8).**
  - A text mark and a legend for every verdict, so colour is never the only signal.
  - Step names that fit.
  - The evidence beside the answer on wide screens, and as a sheet on a phone.
  - Page titles in place of bare site names.
  - Recorded audits open on the finished result, with a replay button.
- **Sharing (9).** An address for each recorded audit and each findings example. Link previews
  (`og:` tags and an image). A footer with the author and a contact. A short "method and limits"
  page.
- **First visit (10).** Keep the service warm. The choice between a scheduled ping and one
  minimum instance is made in the entry, with Google's current prices checked first.
- **Legibility (13).** Labels at 12px and at least 4.5 to 1 contrast. Tap targets at least 40px
  tall. A skip link. Focus styles checked by keyboard.
- **Visual design (14).** Verdicts as proofreader's marks, and fewer uppercase labels, done as part
  of the work on item 8. The larger redesign waits until phase 1 is public.
- **Research agent (12).** It is the weaker half, so it gets only small repairs: check that the
  raw `<u>` tag in a source title is gone, and note where two claims give different figures.
  A written answer on top and source ranking are not planned unless Aditya asks.

### Phase 3. The budget (review item 11)

- **Persist the counters.** The day's spend and the per-address counts move out of memory into a
  small store, so a cold start no longer resets them. Proposed: Firestore in the same Google
  Cloud project, which needs no new account. It gets its own entry, and Aditya approves the
  permission it needs.
- **Console limits.** Hard monthly limits in the Anthropic, OpenAI, Voyage and Tavily consoles,
  named in `DEPLOY.md` as the real ceiling. **[ADITYA]**, about 15 minutes.

### Phase 4. The record, and Aditya in it (review items 17 to 19)

- **A one-page summary** at the top of this file: the ten decisions that mattered and what each
  measured. Claude Code.
- **The trade-off curve (17).** Flags right against the share of claims given a verdict, as the
  agreement rule is loosened and tightened, drawn from the benchmark rows already saved. Free.
- **"What changes at scale" (18).** A short README section: a queue for audits, stored results,
  shared counters, and what breaks first. Claude Code.
- **In Aditya's own words. [ADITYA]**
  - A "what I learned" note.
  - A two-minute video in which he pastes an answer and explains one flag.
  - Five people outside the project auditing an answer of their own, quoted.
  - The review's ten interview questions. Claude Code can list where each answer's evidence
    lives; the answers are his.

### Phase 5. Depth (review items 15, 16, 20), one at a time, each measured

1. **A review queue for "needs a human" (15).** The audit pauses with LangGraph's interrupt and a
   checkpointer, a person rules, and the audit resumes. This comes first because its rulings are
   also human labels.
2. **Citation repair (15).** When a citation fails, a loop searches for a page that does back the
   claim, or refutes it, and decides when to stop. The share repaired is measured. This is D-034's
   step 5.
3. **The vector database (16).** Either a cache of pages across runs, keyed by address and content
   hash, with the keyword-against-dense test rerun on finding one sentence in a long page. Or
   Qdrant removed from the research pipeline, with the reason stated. Decided in its own entry.
4. **Later (20).** More tools if keys are given; MCP tools; evidence from tables and figures.

### Cost

| | About |
|---|---|
| Models and search, phases 0 to 4 | $6 to $8: the re-ask run $4.50, re-audits $1, live checks under $2 |
| Phase 5 | estimated in each entry |
| Aditya's time, phases 0 to 4 | 4 to 5 hours: labelling 2 h; merge, rename and console limits 30 min; his own words and video 1 to 2 h; five outside users as they come |

**Considered.**

- **Publishing the finding now and fixing later.** The review shows where it would be attacked. A
  named company's product is involved, so it waits for phase 1.
- **A model labelling the flags.** That is the thing the review says cannot stand in for a person.
- **A reader service or a browser identity for pages that refuse.** Not done, for the reason in 1d.
- **Doing the agent work first.** It is the most interesting to build, and it does nothing for the
  finding's credibility.

**Trade-off.** The finding stays off the site for some days. Phase 1 cannot finish without about
two hours of Aditya's time, and nothing in this plan removes that.

### Phase 0 done (D-043)

- **One-line source lists are parsed.** "Sources: [1] … [2] …" on the answer's own line, a list
  with no heading, dotted numbers, titles, and sources written as links all reach the right page.
  The list is removed from the answer shown. Tests cover eight layouts. They are written from how
  chat apps lay citations out, not from captured pastes.
- **New label: "could not read the citation".** A sentence with a marker that matches no source
  gets this label and is checked against no page. The paragraph rule no longer borrows across an
  unreadable marker or from a source list left in the text.
- **Checked on the running site** with the review's example plus a `[7]` that has no source. Each
  marker reached its own page, and the `[7]` claim read "could not read the citation".
- **Not done from the review's item 5.** Labelling a claim unreadable when two markers resolve to
  one page. Two numbers can properly point at the same address, and with the fixes above the
  faulty case no longer arises.
- **Buttons.** "Audit it" and "Run it live" work as soon as the page loads. While the server
  wakes, the page says "Starting…" and why.
- **README.** It opens with the auditor. The research agent is its second half. The real-world
  audit is named but not summarised, until phase 1 is done.
- **Seen while checking, not changed.** "8,849 metres" against a page that says 8,848.86 came out
  contradicted in one run and "needs a human" in the next. The auditor treats rounding as a
  mismatch, and its verdict on such a claim can differ between runs. This goes on the list for
  the hand check in phase 1.

### Phase 1a done: what the saved audits say when read every way (D-043)

No new model calls. `evals/results/realworld.json` now holds both readings, every label, bounds
and the pages that were not read. With the page judge as shipped (Haiku):

| | OpenAI `gpt-6.2-sol` | Claude Sonnet 5.5 | Difference |
|---|---|---|---|
| Own-cited claims with a verdict that fail outright | 38.0% (29.1 to 46.4) | 7.9% (4.5 to 11.9) | 30.1 points (21.1 to 38.3) |
| Share of all claims verified against a cited page | 18.5% (13.5 to 24.4) | 24.6% (19.0 to 30.4) | −6.1 points (−12.8 to +0.6) |
| Share of all claims that fail outright | 17.4% | 2.6% | |
| Share of all claims with no citation | 13.0% | 44.0% | |
| Cited pages not read | 66 of 156 | 108 of 288 | |

- **The two readings disagree about how big the gap is.** Among claims that could be checked,
  OpenAI's citations fail far more often. As a share of everything each tool said, the amount
  verified is close, and the interval on that difference includes zero. Both go on the findings
  page's first screen.
- **The bounds are wide.** If every unread page had backed its claim, OpenAI's failure rate would
  be 21% and Claude's 5%. If none had, 65% and 45%. The worst case for one tool overlaps the best
  case for the other, so the unread pages alone could not rule out a much smaller gap. The size of
  the gap rests on the pages that were read.
- **Why pages were not read.**
  - Too little text, on pages built in the browser by scripts: 18 pages for OpenAI and 34 for
    Claude. This is the largest single reason for each tool, and the one a second reader can fix
    (phase 1d).
  - robots.txt: 16 and 24.
  - Refused with 403: 6 and 29.
  - robots.txt itself unreadable: 10 and 2.
- **No one kind of site dominates.** The most any site accounts for is 4 pages.

### Phase 1c done: the same questions asked three more times (D-043)

Run on 24 November 2026 with `python -m evals realworld reask`. Figures are in
`evals/results/realworld_reask.json`; answers and audits are in `evals/realworld/reask/`.

**What was run.**

- **20 questions**, 10 from each source, chosen with seed 20261202 before any repeated answer.
- **Three more asks of each tool**, 120 answers in all, every one audited.
- **Both tools capped at 5 searches.** OpenAI through `max_tool_calls`; Claude's tool already
  carried `max_uses: 5`.
- **One judge, not two.** The repeats were audited with the page judge as shipped only. The GPT
  page judge was left out to stay inside the approved cost. This is a change from the main run.
- **Cost:** $4.31 ($3.87 of answers, $0.44 of audits), against "about $4.50" approved.

**What it shows.**

| On the 20 questions | OpenAI | Claude | OpenAI minus Claude |
|---|---|---|---|
| First ask (main run), own-cited claims that fail | 45.7% of 35 | 7.3% of 55 | 38 points (15 to 57) |
| Repeat 1 | 51.6% of 31 | 3.3% of 60 | 48 points (22 to 64) |
| Repeat 2 | 61.8% of 34 | 4.7% of 64 | 57 points (13 to 76) |
| Repeat 3 | 65.2% of 23 | 6.0% of 67 | 59 points (16 to 88) |
| Three repeats pooled | 59.1% of 88 | 4.7% of 191 | 54 points (20 to 73) |

- **The direction holds every time.** In all four asks OpenAI's cited claims fail far more often
  than Claude's, and no interval for the gap reaches zero.
- **The size does not hold.** OpenAI's figure moved from 46% to 65% across four asks of the same
  20 questions. Each rests on 23 to 35 claims, so one pass of 20 questions cannot give its size.
  Claude's stayed between 3% and 7%.
- **The other reading moved towards Claude.** Share of all claims verified against a cited page,
  three repeats pooled: OpenAI 10.4%, Claude 23.2%, a gap of 13 points (3 to 23). On the main
  run's 100 questions that gap was 6 points with an interval that reached zero. Twenty questions
  are too few to settle it, but the repeats do not support "the tools are level on this reading".

**The search cap never applied.** No answer reached 5 searches. OpenAI's highest was 4 and its
mean 1.4; Claude's highest was 2 and its mean 0.7. So the cap cannot explain any difference, and
the main run, where OpenAI had no cap, was not unfair to Claude on this count.

**Many answers used no search at all.** 21 of Claude's 60 and 9 of OpenAI's 60. Those answers cite
nothing, so all their claims are uncited and none enters the headline. The tools differ in when
they choose to search, and that belongs in the findings.

**The marker question does not arise.** The review asked whether our code puts each `[n]` marker
after the right span. In these 60 OpenAI answers there are 121 citations, and in every one the
tool wrote the link into its own text. Our code added no marker. The same holds for all 100
OpenAI answers of the main run: none has a source list added by our code. The auditor reads
OpenAI's citations where OpenAI put them. (Claude's citations do come as separate blocks, and
there the marker goes at the end of the block Claude attached the citation to.)

**Limits.**

- Within one question, only 7 of OpenAI's 20 had cited claims with a verdict in two or more
  repeats, so the question-by-question spread is thin: a mean gap of 8 points, at most 29.
- The first ask's search counts were not saved, so the capped and uncapped runs cannot be
  compared search for search.
- OpenAI's higher figures in the repeats cannot be told apart from chance at this size.

**What this changes.** The findings page should lead with the direction and the pooled figures
with their intervals, and should not state OpenAI's rate as one number.

## D-044. A person checks a sample of the real-world verdicts (D-043, phase 1b)

**What.** A small tool with which Aditya, by hand, checks 100 of the auditor's verdicts on real
answers. It measures how often the auditor's flags and its "supported" verdicts are right on
this data, not on the benchmark. New module: `evals/hand_check.py`.

**Why.** The review's first point. The auditor was built by Claude and judged by Claude, and the
result favours Claude. The only check so far was ten claims read by a model. Nothing replaces a
person reading the pages.

### The sample, fixed before any label exists

- **Drawn from** the audits with the page judge as shipped (Haiku), own-cited claims only.
- **100 claims**, with a fixed seed: from each tool, 25 that failed outright (not on the cited
  page, or contradicted) and 25 called supported.
- **Order.** Blocks of four, one claim from each of the four groups, shuffled within the block.
  If Aditya stops early, what he has done is still balanced.
- **Committed first.** The list of items goes into the repository before the first label.

### What Aditya sees and does

`uv run python -m evals hand-check` shows one item at a time:

- **Shown:** the claim, and the address of the cited page, which the tool opens in his browser.
  Tracking parameters such as `utm_source=openai` are stripped, because they would give the tool
  away.
- **Not shown:** which tool wrote the answer, the auditor's verdict, the quotes, or the judges'
  reasons.
- **He answers** one of four:
  - yes: the page states everything the claim says;
  - no: a part of the claim is missing from the page, or the page says otherwise;
  - unsure;
  - the page would not open.
- **Saved after every answer**, so he can stop and resume. Each label records the item, the
  answer, the time, and how many seconds the item took.
- **Only a person.** The labels file is written only by this interactive command. No model fills
  it, and model-made labels are never merged into it.

### What is reported, fixed now

`uv run python -m evals hand-check-score` writes `evals/results/realworld_hand_check.json`:

- **Flags upheld.** Of the failed claims he answered yes or no, the share he answered no. For each
  tool and for both together, with 95% intervals.
- **"Supported" upheld.** Of the supported claims, the share he answered yes. The same way.
- **Also:** how many items he labelled, how many were unsure or would not open, and the median
  time per item.

**What the result changes, decided now:**

- The headline is not adjusted by these numbers. They are shown beside it: "N flags checked by
  hand, X% upheld."
- If fewer than 70% of either tool's checked flags are upheld, the findings page says so in its
  first screen and makes no comparison between the tools.
- Every item where Aditya and the auditor disagree is listed in the result file by its id, so it
  can be looked at.

**Considered.**

- **Showing the page text the auditor read, in the terminal.** Pages run to tens of thousands of
  characters. And a person reading the live page also catches text the fetcher missed, which is
  an auditor error worth counting.
- **Showing the auditor's quote to save time.** It would give away the verdict.
- **A web page for labelling.** More to build, and no better for this.
- **All 154 failed claims.** Twice the time. 50 give an interval of about ±13 points.

**Trade-off.**

- With 25 flags per tool, the interval for one tool is about ±18 points. This check can show that
  the flags are mostly right or mostly wrong, not measure a small difference between the tools.
- Pages can change between the audit and the check, so the labelling should not wait long.
- It costs about two hours of Aditya's time and no money.

### D-044 as built: 40 items, not 100

Aditya capped the sample at 40 on 2026-11-24: from each tool, 10 failed and 10 supported claims.
That is about 45 minutes of his time.

- **The sample is fixed.** `evals/realworld/hand_check_items.json` was drawn with seed 20261201
  and committed before any label. Every item cites one page.
- **What 40 can show.** With 20 flags, "flags upheld" for both tools together is good to about
  ±20 points. That is enough to say whether the flags are mostly right or mostly wrong. It is not
  enough to compare the two tools' flags, so per-tool figures are reported but not compared.
- **The 70% rule now applies to both tools together.** With 10 flags per tool, one tool's share is
  too noisy to act on. If fewer than 70% of the 20 checked flags are upheld, the findings page
  says so in its first screen and makes no comparison between the tools.
- **Kept off the screen.** The tool's name, the verdict, the quotes, the question's id, link text
  such as "(openai.com)" inside a claim, numbered markers, and `utm_` tracking parameters.
- **Intervals** are Wilson intervals, which behave well for samples this small.

### D-044 result (25 November 2026): the rule is missed, and the comparison is withheld

Aditya labelled all 40 items between 17:26 and 18:12 UTC, with the blind command. The labels were
committed before they were scored again (`evals/realworld/hand_check_labels.jsonl`).

| | Upheld | 95% interval | Unsure |
|---|---|---|---|
| Flags, both tools | 7 of 13 settled, 54% | 29% to 77% | 7 of 20 |
| "Supported", both tools | 16 of 19 settled, 84% | 62% to 94% | 1 of 20 |

No page failed to open. The median item took 61 seconds.

- **The rule is missed.** 54% is under 70%, so the findings page and the README make no
  comparison between the tools. The per-tool figures stay in `realworld_hand_check.json` and are
  not compared, as decided above.
- **The amendment below was not adopted.** It was drafted before the labels but not approved
  before they were scored. It would have given the same result, since it only adds a way to
  withhold.
- **What changed in D-048's page.** As built, a missed rule replaced only the two readings, which
  left the bar chart, "they fail differently", the checks and the example lists comparing the
  tools. D-044 says no comparison, so the page now shows the hand check instead: its figures, the
  rule, what it means and the data. The example pages stay, each with a note to read its mark
  with care.
- **Why, from the 9 disagreements** (looked at after scoring; the score above stands as labelled).
  Each page was fetched again on 25 November with Evidentia's own fetcher, and the text it keeps
  was compared with the raw page.
  - **5 of the 6 flags Aditya rejected: the page reader threw the evidence away.** The fact was
    in the page's HTML but not in the text the judges read. `trafilatura` with
    `favor_precision=True` drops bylines and dates, stat boxes and side tables:
    - GPT-5's release date (openai.com) and the FDA's approval date (fda.gov), both in the header;
    - the 423 to 421 points (aljazeera.com);
    - the Congressional Research Service's "42 full days" (governmentshutdowntracker.com);
    - Bitcoin's $126,198 high (coinmarketcap.com). There the judges also read an old FAQ line about
      a 2021 high and called the claim contradicted, though a past record does not contradict a
      later one.
  - **The 6th: a live price page.** cryptoclassic.org shows a price that updates by the hour.
    It said one thing when the answer was written, another when it was audited, and neither
    now.
  - **The 3 "supported" marks he rejected** are still on the pages word for word, as the code
    verified at the time: the LBMA high of $4,449 on 23 December (gold.org), Spikevax from 6
    months (page 17 of an FDA PDF), and the Coordinating Financial Mechanism (who.int). The
    auditor looks right on these, but the labels stand as made.
  - **The 7 flags he was unsure on** have not been looked at.

### D-044 amendment, not adopted: a guard for each tool (drafted 2026-11-25, before any label)

**What.** Keep the rule above, and add one more way to withhold the comparison. The findings
page makes no comparison between the tools if either of these is true:

- fewer than 70% of the checked flags are upheld, both tools together (unchanged);
- **new:** for either tool, the top of its 95% interval for flags upheld is below 70%. With 10
  decided flags, that means 4 or fewer upheld.

**Why.** The pooled rule can hide one tool's flags being bad, which is the bias a reader worries
about. OpenAI 4 of 10 and Claude 10 of 10 is 70% together, so the pooled rule is met, yet most of
OpenAI's checked flags would be wrong. The guard withholds only when one tool's share is clearly
below 70%, not when a count of 10 dips by chance.

**What the numbers say** (binomial, worked out before any label):

- If 81% of flags are right for both tools, as on the benchmark, the pooled rule trips by chance
  7% of the time and the guard adds under 1%.
- If one tool's flags are right half the time and the other's 95%, the pooled rule catches it 28%
  of the time and the two rules together 40%.

**Considered.**

- **Only an interval rule, pooled** (withhold when the top of the interval is below 70%). It would
  withhold only at 10 or fewer of 20 upheld, letting through samples that look poor.
- **More items.** Back to 25 per group (100 items) would make one tool's interval about ±18
  points, not about ±22. About an hour more of Aditya's time.
- **Comparing the two tools' upheld shares.** With 10 each, only a very large difference shows.

**Trade-off.** With 10 flags per tool, no rule can find a moderate difference between the tools'
flags. The guard catches only a gross one, and the result file still reports each tool's share
with its interval so a reader can judge the rest.

## D-045. The site's look: an editor's desk, at the full width of the screen (D-043, phase 2)

**What.** A redesign of the whole site, asked for by Aditya on 2026-11-24. Two things drive it.
At 100% zoom on a desktop the site sits in a narrow centred column and looks small. And the
review found the current look (cream paper, a thin serif headline, small uppercase mono labels)
is the most common look for AI-built sites this year. D-024's idea, a marked-up document, stays.
It is carried all the way through.

### The idea

**An editor's desk.** The visitor's pasted answer is a sheet of paper lying on a desk. Evidentia
is the editor going over it with a pencil.

- **The sheet.** The audited answer is set on a white sheet in a reading serif, with a wide
  margin. Nothing else on the site is set in that serif, so the answer always reads as "the
  document" and the rest as "the tool".
- **The marks.** Each sentence gets a proofreader's mark in the margin, drawn as the verdict
  arrives, with its name beside it. Colour is never the only signal.

  | Verdict | Mark |
  |---|---|
  | supported | a tick |
  | partly backed | a tick with a caret (something missing) |
  | not on the cited page | a cross |
  | contradicted | a "not equal" sign |
  | needs a human | a question mark |
  | could not check, could not read the citation, uncited | a dash |

- **The clipping.** Evidence opens as a strip cut from the cited page: its title and address
  across the top, the quote highlighted in its surrounding text, and the two judges' reasons as
  two notes beneath.
- **The tally.** The scorecard is one bar across the sheet's foot, split by verdict, with the
  count of each. It fills as verdicts land. The auditor's own error rates sit beside it.
- **The desk.** Everything around the sheet (navigation, steps, controls, numbers) is set in the
  sans face on a slightly darker surface, in sentence case. Uppercase mono is kept only for
  numbers and data labels.

### Full width

- **The canvas.** It spans the screen. The centred 78rem column goes. Content runs to about
  112rem (1,800px), with side padding that grows with the screen.
- **Type that grows.** Headline, body and sheet text scale smoothly with the width, so a 1920px
  screen gets larger type and not wider margins.
- **Wide screens, three zones side by side.** The steps and controls in a narrow left rail, the
  sheet in the middle, the clipping and tally on the right. The right zone stays in view while
  the sheet scrolls.
- **Laptops and phones.** Two zones on a laptop. On a phone, one column, with the clipping
  opening as a sheet from the bottom.

### Type and colour

- **Faces.** Geist for the interface and headlines, set heavier and tighter than now. Newsreader,
  a reading serif, for the audited answer and quotes only. Geist Mono for numbers. Instrument
  Serif is dropped.
- **Surfaces.** A warm grey desk, a white sheet, near-black ink.
- **Accents.** The highlighter yellow stays for quoted evidence only. Verdict colours are used
  only on marks, the tally and verdict names.
- **Legibility.** No text under 12px. All text at least 4.5 to 1 against its background. Tap
  targets at least 40px tall. A skip link, and visible focus rings.

### Motion, only when something real happened

- A mark is drawn stroke by stroke when its verdict arrives.
- The highlighter sweeps across a quote when its clipping opens.
- The tally bar grows as verdicts land.
- The steps fill as the server reports them.
- A recorded audit opens on its finished result, with a "Replay" button, so nobody waits 20
  seconds to see anything.
- All of it is switched off for visitors who ask for reduced motion.

### Pages

1. **Home is the auditor.**
   - First screen: what this is, in one headline; the paste box; and a recorded audit beside it,
     already marked up.
   - Below: how it works in three steps; how often it is right, read from the results files; the
     finding, once phase 1 is done; and the limits.
2. **Research** gets its own tab, restyled with the same pieces. Its claims are the sheet, its
   source the clipping.
3. **Evals**, restyled, with step names and tables that fit.
4. **Method and limits**, a new short page.
5. **Shared pieces.**
   - A footer with the author and a contact.
   - An address for each recorded audit, so it can be linked.
   - Link previews (`og:` tags and one image).
   - Page titles in place of bare site names in the clipping.
   - Short step names that fit.

### How it is checked

- `npm run build` and `npm run lint`.
- Measured in the browser at 390, 1280, 1440 and 1920 pixels wide: no sideways scroll, text
  sizes, contrast, and how much of the width the content uses.
- **A limit of my own checking.** The browser pane I work in is too small to judge fine visual
  detail. So Aditya looks at each page on his own screen before it is pushed.

**Considered.**

- **Only widening the column.** It fixes "small" and leaves the generic look.
- **A dark theme.** D-024 ruled it out as the default AI look, and that still holds.
- **Handwriting fonts for the marks.** They slide into kitsch. Marks drawn as simple strokes read
  as an editor's pencil without pretending to be handwriting.
- **Keeping the thin serif headline.** It is the single most recognisable part of the look the
  review named.

**Trade-off.**

- Every component is touched, so this is the largest change to the site since M4.
- Type that scales with the screen needs care at the extremes, which is why four widths are
  measured.
- The home page will have a gap where the finding goes until phase 1 is done. It shows the
  auditor's measured accuracy until then.

**Order.** Tokens and layout first, the widest win. Then the audit page as home, then research,
evals and the shared pieces. Each step is committed on its own. Nothing is pushed until Aditya has
seen it. Cost: a few cents of live audits while checking.

### As built (24 November 2026)

**The pages.**

- **Home (`/`)** is the auditor: headline, paste box, a recorded audit on the desk, three steps.
  `/audit` redirects to it. Each recorded audit has its own address, `/recorded/<id>`.
- **Research (`/research`)** uses the same desk: steps in a rail, the claims on a sheet with
  proofreader's marks in place of stamps, the quote as a clipping.
- **Evals (`/evals`)** now leads with the auditor, then the research agent, then what was not done.
  Two charts are new:
  - one judge against two, with a partly backed claim counted as a flag for all three so the
    comparison is like for like. The old table set the as-shipped figure (0.806) beside
    single-judge figures counted by the other rule, which flattered two judges. The text now says
    the intervals overlap.
  - balanced accuracy for each of the 11 sources of rows, weakest first.
- **Method and limits (`/method`)** is new: the five steps, the nine marks, eight limits, and the
  rules for live audits.
- **Link preview.** One generated image, with no numbers on it.

**Numbers on the method page come from code.** `python -m evals report` now writes an
`auditor_limits` block into the site's data file from the settings' defaults (claims and pages per
audit, the least text a page must give, the spending cap, audits per address, seconds between
requests to one site). The page reads them from there, so it cannot drift from the code.

**Three faults found while checking, all fixed before any push.**

- The site's own CSS classes sat outside a layer, so they beat every Tailwind utility on the same
  element. Sizes and weights set beside them were ignored. They are now in the components layer.
- The page frame's class list was exported from a client file. A server component that imported it
  got a stub, not the string, so the footer had no side padding. It now lives in `lib/site.ts`.
- The production build failed on the recorded-audit page: a route setting this Next.js version
  does not allow, and a file read that had to be cached. `npm run build` had not been run after
  part 1. It passes now.

**Measured** at 390, 1280, 1440 and 1920 pixels on `/`, `/research`, `/evals` and `/method`: no
sideways scroll, no text under 12 pixels, no text under 4.5 to 1 contrast. Content runs from 77 to
1,828 pixels on a 1,920 pixel screen. On a phone the charts put each row's name above its track.

**Not done here.** The home page does not show the real-world finding; that waits for phase 1.
An unknown `/recorded/<id>` shows the not-found page but answers with status 200, because the
page streams.

## D-046. A second reader for pages built by scripts (D-043, phase 1d)

**Status: approved by Aditya on 24 November 2026, built and run. The result is at the end of this entry: the reader works, and it barely changes anything.**

### The problem

The fetcher downloads a page's HTML and reads the text in it. Some pages hold almost no text
until scripts run in a browser. The auditor marks those "too little text read" and gives their
claims no verdict.

| Saved audits (Haiku page judge) | OpenAI | Claude |
|---|---|---|
| Main run: pages with too little text | 18 | 34 |
| Main run: answers that cite one | 15 | 21 |
| Main run: own-cited claims left without a verdict | 36 | 90 |
| Re-ask run: pages with too little text | 7 | 10 |
| Re-ask run: own-cited claims left without a verdict | 39 | 47 |

The main run's headline rests on 187 and 382 own-cited claims. So 36 and 90 more are enough to
move it, and the review was right to ask.

### What is proposed

A second reader, `evidentia/render.py`, that opens a page in a headless browser, lets its scripts
run, and reads the text of what results. It is used only for a page that answered and gave fewer
than 2,000 characters. Every other page is read as it is today.

**It stays a crawler that says who it is.** These rules are the point of the design:

1. **Same name.** The browser sends Evidentia's own user agent, not a browser's.
2. **The browser never touches the network itself.** Every request the page makes is handed to
   our code. Our code makes it with the fetcher's own client and passes the answer back. So each
   request, and each redirect of it, goes through the same checks as today:
   - robots.txt for that address, read once for each site;
   - the guard that refuses private and internal addresses.
   As a second lock, the browser is given a proxy address that leads nowhere, so anything that
   slips past our code fails instead of going out.
3. **Reading only.** GET requests only. A page that needs a POST to load its text stays unread.
   Nothing is clicked, no consent banner is accepted, no form is filled.
4. **Less load, not more.** Images, video, fonts and stylesheets are not fetched. One page may
   make at most 40 requests and take at most 20 seconds.
5. **Nothing kept.** A fresh browser profile for each page: no cookies, no storage, no
   downloads, no service workers.
6. **Refusals stay refusals.** A page that answered 403, or that robots.txt disallows, is never
   sent to this reader.

**What happens to the text.** The rendered HTML goes through the same text extraction as a
fetched page and is stored as the source text. Quotes are still checked by code against that
stored text. Each source records which reader read it, and the audit shows it.

**If the page is still thin** after rendering (a paywall, a consent wall, a bot check), it stays
"too little text read". No further attempt is made.

### Where it runs

- **Only in the eval, on Aditya's machine.** A setting, `audit_render_thin_pages`, off by default.
- **Not on the live site.** The server image is unchanged. The site keeps marking these pages
  "too little text read", and the method page keeps saying so.
- **Why not the server yet.** A browser needs about 300 MB more in the image and more memory
  than the service has. Running untrusted scripts on the server also deserves its own decision.

### How the result is measured

- **Only the stranded claims are judged.** For each saved audit, the claims left without a
  verdict because of a thin page are judged against the rendered page. Every other claim keeps
  the label it already has. Re-auditing whole answers would mix the reader's effect with the
  judges' run-to-run noise.
- **Saved apart.** New files under `evals/realworld/rendered/`. The original audits are not
  changed.
- **Reported in `evals/results/realworld_rendered.json`:**
  - pages tried, pages that gave enough text, pages still thin, and why;
  - claims that gained a verdict, by label, for each tool;
  - the headline and the bounds before and after, with intervals, for the main run;
  - the same for the re-ask run.
- **Fixed now, before any page is rendered:** whatever comes out is reported, whichever tool it
  favours. Pages still unread stay in the bounds.

### What it needs from Aditya

- **A yes to one new dependency:** `playwright` 1.65.2, in a group the server does not install,
  and its headless Chromium build, a download of a few hundred MB from Playwright's own servers.
  This is a browser, not a model, so rule 12 is not broken, but it is the heaviest tool the
  project would have.
- **A yes to the cost:** under $1 of model calls, for about 250 claims in the main run and the
  re-ask run (212 with their own citation, the rest citing through their paragraph). No search calls.
- **A yes to rule 4,** which is a judgement call: a rendered page makes up to 40 requests to a
  site where a fetch makes one. Requests inside one page load are spaced 0.25 seconds apart for
  each site, not the 2 seconds kept between page loads.

### Considered

- **A reader service that renders pages for you.** It fetches under its own name, ignores our
  robots.txt check and our rate limit, and sends every address to a third party. No.
- **Reading the data a page ships inside its HTML** (`__NEXT_DATA__`, JSON-LD). No browser is
  needed, but each framework needs its own code and the text is not what a reader sees.
- **Letting the browser load pages itself and watching its requests.** Simpler, but the checks
  would see only the first address of each request, not its redirects. A redirect to an internal
  address would get through.
- **Leaving these pages to the bounds.** That is today's state. The bounds are wide (21% to 65%
  and 5% to 45%) and these pages are the largest single reason.

### Trade-off

- A browser running scripts from pages the tools chose to cite is the riskiest code in the
  project, even with the network held by our own client. It is why this stays off the server.
- The yield is unknown. Some of these pages (69 across the two runs) are thin for other reasons, and GET-only and
  robots.txt will leave more unread. It may move the headline a little or not at all.
- The live site and the eval will read pages differently. The findings page must say so.
- One point to confirm while building: that the browser works with every request answered by
  our code and a dead proxy behind it. If it does not, the design comes back here before any
  page is rendered.

### Tests

- The reader's rules, with a fake browser: the user agent, GET only, the request cap, blocked
  resource types, a refused robots.txt, a private address.
- One real render of a local page whose text is written by a script, skipped where the browser
  is not installed.
- The eval's bookkeeping with made-up audits: only stranded claims change, and the before and
  after figures add up.

### As built and run (24 November 2026)

**Built as drafted.** `evidentia/render.py` is the reader and `evals/reread.py` the eval. The
point left to confirm held: the browser renders with every request answered by our code and a
dead proxy behind it. In that test a request our code let through failed at the proxy, and so did
a WebSocket. A real-browser test also shows the page's own scripts see Evidentia's user agent.

**One addition.** Pages the fetcher had skipped as "no readable text" (under 200 characters) were
tried too, since they also answered and gave too little text.

**The result.** Figures are in `evals/results/realworld_rendered.json`.

| | Main run | Re-ask run |
|---|---|---|
| Thin pages tried | 62 | 19 |
| Gave 2,000 characters or more in the browser | 5 | 2 |
| Still too little text | 49 | 14 |
| No readable text at all | 6 | 2 |
| Other (not HTML; one 403) | 2 | 1 |

| Main run, own-cited claims that fail | Before | After |
|---|---|---|
| OpenAI | 38.0% of 187 | 39.1% of 197 |
| Claude | 7.9% of 382 | 7.8% of 386 |
| OpenAI minus Claude | 30 points (21 to 38) | 31 points (23 to 39) |

- 17 claims gained a verdict in the main run: 13 of OpenAI's (8 not on the page, 4 supported, 1
  partly backed) and 4 of Claude's (all supported). Two more went to a person.
- The bounds hardly narrowed: OpenAI 23% to 64%, Claude 5% to 44%.
- Cost: $0.02 of model calls, because so few pages could be judged.

**Why so little.** The premise was wrong. On a sample of 14 of these pages, 12 gave exactly the
same text in the browser as in a plain fetch. They are not built by scripts. They are:

- short real pages: an arXiv abstract (1,937 characters), a NASA blog post (1,175), a news brief
  (954);
- paywall teasers (Japan Times, Bloomberg);
- pages with no article at all, such as a video page.

So the cause is the 2,000-character minimum set in D-042, not scripts. The label the auditor
shows, "the page may need a browser to show it", was a guess from the pilot. It is wrong for
most of these pages and should be reworded.

**What stays.** The reader stays in the code, off by default. It did what it was built to do on
the 7 pages that needed it. It is not worth putting on the server.

**What this leaves open.** Whether short pages should be judged. A size limit cannot tell a
short real article from a paywall teaser, and judging a teaser would blame the tool for text we
could not see. That is a new decision, not part of this one.

## D-047. Judge the short pages too, as a third reading (sensitivity check)

**Status: approved by Aditya on 24 November 2026, built and run. Results at the end of this entry: the gap between the tools holds in every reading.**

### The problem

D-046 found that most "too little text" pages are not built by scripts. They are short: an arXiv
abstract, a blog post, a news brief, or a paywall teaser. The auditor leaves their claims without
a verdict because of the 2,000-character minimum set after the pilot (D-042).

Claims still stranded on pages with 200 to 1,999 characters, after the browser re-read:

| | OpenAI | Claude |
|---|---|---|
| Main run: short pages | 16 | 33 |
| Main run: own-cited claims stranded | 35 | 89 |
| Re-ask run: short pages | 5 | 9 |
| Re-ask run: own-cited claims stranded | 35 | 43 |

The main run's headline rests on 197 and 386 own-cited claims, so Claude's 89 in particular could
move it.

### What is proposed

Judge those stranded claims against the short text as it was fetched, with both judges as
shipped, and report the result as a **third reading** beside the headline. The headline itself
does not change, and neither does the 2,000-character rule on the live site.

- **Only the stranded pairs are judged.** Every other claim keeps the label it has, as in D-046.
- **The short text is fetched again** with the plain fetcher, under the same robots.txt check and
  rate limit, since the saved audits do not keep page text.
- **Each short page is recorded with its length**, so the report can say how many were under
  1,000 characters.
- **Saved apart**, under `evals/realworld/short/`, and summarised in
  `evals/results/realworld_short.json`:
  - the headline as it stands, the third reading, and the difference, with intervals, for each
    tool;
  - the claims that gained a verdict, by label;
  - the same for the re-ask run.

**How it is read, fixed now before any claim is judged:**

- If the gap between the tools stays clearly apart from zero in the third reading, the finding
  does not rest on the 2,000-character rule, and the findings page says so in one line.
- If the gap shrinks a lot or its interval reaches zero, the findings page leads with that.
- Either way, the third reading is shown, not hidden.

### Why not simply lower the minimum

A size limit cannot tell a short real article from a paywall teaser. On a teaser, a claim the full
article supports would be marked "not on the cited page", which blames the tool for text we could
not see. That is why the result is a sensitivity reading and not a new headline.

### Also proposed: a truer label

The auditor tells a reader that a page gave "too little text read (the page may need a browser to
show it)". D-046 showed the second half is usually wrong. Proposed instead: **"too little text
read (a short page, a paywall, or a page built by scripts)"**. The reason text is all that
changes; the label, the rule and the figures stay as they are. The saved audits keep the old
wording, so the eval code will match both.

### Cost

About 240 claim-and-page pairs in the two runs (51 and 102 in the main run, 36 and 50 in the re-ask), judged by Haiku. Under $0.50. No search calls.

### Considered

- **Lowering the minimum to 1,000 characters for everyone.** It still cannot tell a teaser from
  an article, and it changes the live site on the strength of one look at 14 pages.
- **Having a person sort the short pages (63 across both runs and tools, some cited more than once) into "real article" and "teaser" first.** The
  strongest option, about an hour of Aditya's time. It can be added later and the third reading
  split by it.
- **Doing nothing.** The bounds already cover these claims, but they are wide (OpenAI 23% to 64%,
  Claude 5% to 44%), and a reader is left not knowing which end is likely.

### Trade-off

The third reading mixes real verdicts on short articles with unfair ones on teasers, so it is a
check on the headline, not a better headline. It costs little and answers the question the
review would ask next: does the result depend on a threshold we picked?

### Tests

- The pairs chosen: only claims still stranded after D-046 on pages of 200 to 1,999 characters.
- The bookkeeping: only those claims change, and the before and after figures add up.
- The new reason text, and that the eval still recognises the old one.

### As built and run (24 November 2026)

`evals/short.py`; figures in `evals/results/realworld_short.json`; reports in
`evals/realworld/short/`. Cost: $0.07 of model calls, against "under $0.50".

**One addition, made after a two-answer trial and before the full results were seen.** In the
trial, a 311-character page failed all four claims judged against it, which is what a teaser
looks like. So a fourth reading was added: the same as the third, but pages under 1,000
characters left unjudged, as before. It was not in the approved draft, and is labelled as added.

**Pages.** Main run: 57 short pages tried, 51 read, 24 of them under 1,000 characters, 6 with no
readable text. Re-ask run: 17 tried, 15 read, 8 under 1,000 characters.

**Main run, own-cited claims that fail:**

| Reading | OpenAI | Claude | OpenAI minus Claude |
|---|---|---|---|
| As saved (the headline) | 38.0% of 187 | 7.9% of 382 | 30 points (21 to 38) |
| With the browser re-read (D-046) | 39.1% of 197 | 7.8% of 386 | 31 points (23 to 39) |
| With short pages judged | 43.6% of 227 | 10.4% of 461 | 33 points (23 to 42) |
| The same, pages under 1,000 characters left out | 41.7% of 211 | 8.4% of 431 | 33 points (24 to 42) |

**Main run, share of all claims verified against a cited page:**

| Reading | OpenAI | Claude | OpenAI minus Claude |
|---|---|---|---|
| As saved | 18.5% | 24.6% | -6 points (-13 to +1) |
| With short pages judged | 20.3% | 28.5% | -8 points (-15 to -1) |
| The same, under 1,000 left out | 19.7% | 27.6% | -8 points (-15 to -1) |

**Re-ask run** (repeats pooled), own-cited claims that fail: OpenAI 59% as saved, 70% with short
pages judged, 59% with pages under 1,000 characters left out; Claude 5%, 8% and 6%. Almost all of
OpenAI's new failures here came from pages under 1,000 characters.

**How it reads, by the rule fixed in the draft.** The gap between the tools stays clearly apart
from zero in every reading, and barely moves (30 to 33 points). **The finding does not rest on
the 2,000-character rule**, and the findings page says so in one line.

**Also seen.**

- Judging short pages raises both tools' failure rates, and the shortest pages raise them most.
  That fits the worry that teasers are judged as if complete. It is why the headline stays as
  saved.
- On the second reading, Claude's lead in verified claims becomes clear of zero once short pages
  are judged (8 points, 1 to 15). It was not clear as saved. Worth one line on the findings page,
  as a reading that depends on the short pages.
- The bounds narrow: OpenAI 30% to 61%, Claude 8% to 34%, with short pages judged.

**The label.** The reason shown for a thin page now reads "too little text read (a short page, a
paywall, or a page built by scripts)". It reaches the live site with the next deploy. Saved and
recorded audits keep the old wording.


## D-048. The findings page (D-043, phase 1e)

**Status: approved by Aditya on 24 November 2026, built, and held locally until the hand check is in or Aditya decides to publish without it.**

### What it is for

One page that states what the real-world audit found, both ways it can be read, how far each
number can be trusted, and what was done to try to break it. It answers review items 1 to 3 on
the page itself, not only in this log. No model calls: every number is already in a results file.

### The first screen

What a visitor sees before scrolling, at 1280 pixels and up:

1. **A headline that states the difference, not a verdict on a company.** Proposed: "Asked the
   same 100 questions, two AI search tools cited very differently." Under it, one line naming
   them: OpenAI's `gpt-6.2-sol` with web search, and Anthropic's Claude Sonnet 5.5 with web
   search, as answered in November 2026.
2. **A stacked bar for each tool over all its claims, all nine labels** (review item 2). Each
   segment carries the label's mark as well as its colour, so colour is never the only signal.
   Built with the dataviz method, and its colours checked by its validator.
3. **Both readings, side by side, with intervals:**
   - Of claims cited in their own sentence that got a verdict, the share that fail: OpenAI 38.0%,
     Claude 7.9%, a gap of 30 points (21 to 38).
   - Of everything each tool said, the share verified against a page it cited: OpenAI 18.5%,
     Claude 24.6%, a gap of 6 points that could be zero.
4. **The plain statement** that they fail differently: OpenAI cites most claims, and many of
   those citations do not hold. Claude's citations hold more often, but it leaves 44% of its
   claims uncited.
5. **The hand-check line.** Read from `evals/results/realworld_hand_check.json`: "N flags checked
   by hand, X% upheld". Until that file exists it says "No flag has been checked by a person yet".
6. **Three limits**, in one line each:
   - the auditor is right about 81% of the time on flags, measured on a benchmark;
   - both of its judges are Claude models judging a Claude product, and a GPT judge was run as a
     check (next section);
   - one answer per question, so the size of a tool's figure moves between asks.

### Below: what was done to try to break it

Each a short block with its numbers, all read from results files:

- **Another judge.** With OpenAI's `gpt-6-luna` as the page judge: 45.3% against 7.8%. The
  Claude judge was not kinder to Claude. (`realworld.json`)
- **Asking again.** 20 questions asked three more times: the direction held every time, OpenAI's
  figure moved between 46% and 65%. (`realworld_reask.json`)
- **Pages that could not be read.** The bounds if every unread page had backed its claim, and if
  none had. Rendering thin pages in a browser rescued 7 of 81. Judging short pages anyway moved
  the gap from 30 to 33 points. (`realworld.json`, `realworld_rendered.json`,
  `realworld_short.json`)
- **Was it fair to each tool?** Claude ran on the older search tool, because the newer one returns
  no citation data. Both were capped at 5 searches and no answer reached the cap. OpenAI's
  citation markers are the links it wrote itself. Many answers used no search at all.
- **What it cost:** the model and search spend of each run, from the results files.

### Below that: examples, each with its own address

- **Chosen by the rule fixed in D-042, before any answer existed:** every contradicted claim
  (5 OpenAI, 7 Claude), then 5 "not on the cited page" claims for each tool, drawn with a fixed
  seed. No example is picked by hand.
- **Each opens on its own page,** `/findings/<tool>/<question>`, with the answer on the sheet, its
  marks in the margin, and the chosen claim selected with its evidence. The same pieces as a
  recorded audit, drawn from the saved report without a replay.
- **Written by code:** a command copies the chosen reports into `web/public/findings/`. Quotes
  keep only the context the audits already hold, never whole pages.

### Elsewhere

- **The header** gets "Findings". **The home page** gets one line linking to it.
- **`evals/report.py`** writes the real-world results into the site's data file, as it does for
  the other evals.
- **The README's** real-world section gets the two readings, the hand-check line and the limits.

### When it goes live

Built and checked locally, then held. It is pushed only when one of these is true:

- Aditya's 40 hand-check labels are in, and the page shows the result, whatever it is; or
- Aditya decides to publish without them. The first screen then says "No flag has been checked
  by a person yet", as D-043 set out.

### Considered

- **Leading with the 38% figure alone.** It is the more striking number, and showing it alone is
  what review item 2 warned against.
- **A single "trust score" per tool.** It would hide the two different ways the tools fail.
- **Picking good examples by hand.** Easier to read, and exactly the cherry-picking the fixed rule
  is there to prevent.
- **Showing the examples inline only.** They could not be linked, which review item 13 asked for.

### Trade-off

- Naming two companies' products makes this the most visible claim the project makes. Hence
  both readings, the limits and the hand-check line on the first screen, not below it.
- It is long. The first screen carries the finding; everything after it is evidence for people
  who want it.

### Tests

- The examples are chosen by the fixed rule and seed, and the same every time.
- The site's data file carries the real-world figures and nothing hand-typed.
- The hand-check line in both states: with no result file, and with one.
- Built and measured in the browser at 390, 1280, 1440 and 1920 pixels, as for D-045.

### As built (24 November 2026)

- **Pages.** `/findings`, and one page for each of the 22 examples, `/findings/<tool>-<question>-<claim>`.
  All are made ahead of time. "Findings" is in the header, and the home page has one link to it.
- **Data.** `python -m evals report` now writes the real-world results into the site's data file.
  The rule that drops long lists from it no longer drops "runs" when it holds figures (a dict).
- **Examples.** `python -m evals realworld examples` chooses them by D-042's rule with seed
  20261203, set when the page was built, and copies the 20 answers they come from to
  `web/public/findings/`.
- **The chart.** The bar fills were checked with the dataviz validator on white: every check
  passes, and amber, under 3:1, gets its relief from the legend's marks and the table. Dead links
  are hatched. Shares written on the bars are in ink.
- **The hand-check line** reads the result file when it exists. If the result misses D-044's rule
  (70% of flags upheld), the two readings are replaced by a statement that the comparison is
  withheld.
- **Two corrections made while building.**
  - A difference is now written with the tool it favours, so "Claude's is higher by 6 points (−1
    to 13)" and not "6 points (−13 to 1)".
  - Percentages are rounded half up on the stored four decimals, so Claude's 0.0785 reads 7.9%,
    as in this log, and not 7.8% as binary floating point gave.
- **Measured** at 390, 1280, 1440 and 1920 pixels: no sideways scroll, no text under 12 pixels,
  no text under 4.5 to 1. `npm run build` makes all 37 pages.
- **A testing note, not a fault.** In the hidden browser pane the example pages stay on their
  loading line until a frame is drawn, because the browser holds back drawing in a hidden tab.
  They show at once when drawn, with the marks level with their sentences.


## D-049. The auditor reads the rest of the page, not only the article (after D-044)

Approved by Aditya on 25 November 2026, with the re-audit and its cost.

**What.** The auditor keeps the article text it reads today. After it, it adds the rest of the
page's visible text, one block per line: headers with their dates, image captions, stat boxes and
side tables. Then the saved answers are audited again with the new reader (no new answers), and a
fresh blind hand check is run on a new sample.

- **Only the auditor changes.** The research agent keeps its reader, so its evals stay valid.
- **No made-up text is stored.** Every character added is page text, so a quote is still an exact
  span of the page (rule 8). The source records where the article ends, so the site can show the
  two parts apart.
- **Dropped:** scripts, styles, forms, buttons, frames, and elements marked `hidden` or
  `aria-hidden`. Lines already in the article are not repeated.
- **The 2,000-character rule (D-047) counts the article only.** Otherwise a paywall teaser would
  pass on the strength of its menus.

**Why.** D-044's diagnosis: in 5 of the 6 flags Aditya rejected, the evidence was in the page's
HTML but `trafilatura` with `favor_precision=True` had dropped it.

- **Tried on those 5 pages:** `trafilatura`'s default and `favor_recall` settings recovered none
  of the 5 facts. The article plus the rest of the page recovered all 5. It also kept the facts behind
  the 2 "supported" marks on HTML pages; the third is a PDF, which is read as before.
- **Across the main run** (fetched again on 25 November, no model calls): of 101 flags, 15 cite a
  page where a number in the claim is missing from the article text but present elsewhere on the
  page: 5 of OpenAI's 71 and 10 of Claude's 30. This is a rough test. Some matches are a year in
  a menu, and claims without numbers and pages that cannot be read now were not tested.
- **The added text is a median 55% of the article's length.**

**Considered.**

- **Other `trafilatura` settings.** Recovered none of the 5.
- **A line with the page's metadata date.** Made-up text that a quote could then cite. And the
  metadata date is often a "last reviewed" date, not when the thing happened.
- **The whole page as one block** (`html2txt`). It recovers the facts but loses every line break,
  so quotes cannot be shown in their paragraph, and it mixes the article with the menus.
- **The browser reader (D-046).** These facts were in the served HTML, not built by scripts, and
  the browser is slower.
- **Telling the judges that a past record does not contradict a later one** (the CoinMarketCap
  case). A prompt change moves the benchmark score too, so it needs its own benchmark run. Left
  for a later decision.

**Trade-off.**

- **More noise.** Menus, related-story headlines and old FAQ text can give a wrong "supported" or
  "contradicted". The benchmark cannot measure this, because it hands the auditor clean text. Only
  the fresh hand check can, which is why it is part of this decision.
- **Text a person cannot see.** Text hidden by stylesheets, not by the `hidden` attribute, is still
  read, including some paywalled text.
- **Pages have moved on.** The re-audit reads each page as it is now, a day or more after the
  answer was written. Live pages such as prices will differ more. Each audit records when it read
  the page.

### The re-audit

- **Runs:** the main run with both page judges (Haiku as shipped, and `gpt-6-luna`), and the 20
  re-ask questions over all four asks. Saved answers are reused.
- **Cost:** the old audits cost $0.81 (Haiku), $0.83 (luna) and $0.44 (re-ask). With about 50%
  more text, about $3.10 in all. Hard cap of $5 in code. Aditya says yes to the run first.
- **Kept apart:** results go to new files, and the old audits stay as they are. D-046 and D-047
  were measured on the old reader, so their figures are not carried over to the new one.

### The fresh hand check, fixed now, before any label

- **The sample:** 40 claims from the new Haiku audits, 10 from each of the four groups, as before,
  with a new seed, 20261204. The 40 claims already labelled are left out. The item list is
  committed before the first label.
- **The rule:** the comparison is shown only if at least 70% of the flags Aditya settles are upheld,
  both tools together, **and** neither tool's 95% interval for flags upheld lies wholly below 70%.
  The second part is the per-tool guard drafted above, adopted here before any label of this
  check.
- **About 45 minutes of Aditya's time.** Same blind command, same rubric.

**Changed on 25 November, before the sample was drawn and before any result of the re-audit was
looked at: 24 items, not 40.** Aditya could not give 45 minutes. The rule rests on the flags, so
they are kept:

- **10 flags per tool**, 20 in all, as planned, in pairs of one from each tool, so stopping early
  leaves the tools balanced.
- **2 "supported" claims per tool**, 4 in all, put in at places drawn by the seed, so that not
  every item is a flag.
- **The cost of this.** Aditya knows most items are flags, which may lean him towards "yes, the
  page says it". The "supported" figure rests on 4 claims and is reported, not judged. The rule is
  unchanged. About 25 minutes.

**And then 21 items, because Claude has only 7 flags left to draw.** Drawing the sample showed
that the new audits flag 14 of Claude's own-cited claims (OpenAI: 76). 7 of those 14 come from
sentences Aditya labelled in the first check, and he has since seen the auditor's verdicts on
several of them, so they cannot be checked blind. All 7 that remain are taken, with 10 of
OpenAI's: 17 flags and 4 "supported" claims. The rule is unchanged; for Claude the guard now
works on 7 flags, and trips at 2 or fewer upheld. This was the only count looked at before the
sample was fixed. About 20 minutes.

### Tests

- The reader keeps the article first and adds the rest, with no repeated lines and nothing from
  scripts, styles, or hidden elements.
- A quote found in the rest of the page passes the exact-span check.
- The thin-page rule counts the article's characters only.
- The research agent's reader is unchanged.
- The new sample is the same every time, has 10 flags and 2 supported claims per tool, keeps the
  tools' flags balanced wherever labelling stops, and contains no sentence from the old 40.

### D-049 result (25 November 2026): closer, and still short, by one flag

**The re-audit.** All 100 saved answers from each tool were audited again with both page judges,
and the 120 re-asked answers with the shipped judge. It cost $2.38 in all ($0.02 trial, $1.87
main, $0.49 re-asks), under the $3.10 approved. Results: `realworld_rest_of_page.json` and
`realworld_rest_of_page_reask.json`. The old audits are untouched.

**The second hand check.** Aditya labelled all 21 items between 19:16 and 20:07 UTC. The labels
were committed before they were scored (`hand_check_2_labels.jsonl`).

| | Upheld | 95% interval | Unsure |
|---|---|---|---|
| Flags, both tools | 9 of 13 settled, 69% | 42% to 87% | 4 of 17 |
| "Supported", both tools | 4 of 4 | 51% to 100% | 0 of 4 |

- **The rule is missed by one flag.** 69.2% is under 70%. Ten upheld of 13 would have met it. The
  per-tool guard did not trip. So the page and the README still make no comparison, and say how
  close it was. The bar is not moved after the labels.
- **Up from 54%.** The fix helped, but this check is small, and the two intervals overlap widely.
- **What the page shows now.** The second check governs, because it was run on the auditor as it
  is now. The first check, the fix and the second check are told in that order. The example pages
  still come from the first audit and say so.
- **Not done.** The comparison page still reads the first audit's results. If a later check meets
  the rule, that page must first be moved to the re-audit's results, and the "Trying to break it"
  checks run again on the new reader where they depend on it.
- **Why, from the 4 disagreements** (looked at after scoring; the score above stands as labelled).
  Each page was fetched again on 25 November with the auditor's reader. All four were "not on the
  page", and in all four Aditya found the claim backed. The reader is no longer the cause: the
  evidence was in the text the judges read in three of them. Three causes, none of them the one
  D-049 fixed:
  - **A name the page does not use (2, both Claude, one answer about Euclid).** The answer named the
    release "Q1" in its first sentence. The splitter carried that name into two later claims ("Q1
    was a quick release...", "The Q1 release included a catalogue of more than 380,000
    galaxies"), as it should, so each claim stands alone. Both pages say the rest almost word for
    word, and one dates the release to 19 March, but neither page says "Q1". The shipped judge
    held each claim to that name and said not found. The other judge did too on the first, and
    sent the second to a person. On one page the finder's quote also missed by a character: the
    page writes ‘quick’ with curly marks, and the quote check is exact (rule 8), so that miss is
    correct as built.
  - **The part of the PDF that holds the evidence was never read (1, OpenAI).** The claim cites
    the AI Act on EUR-Lex, a 144-page PDF. The reader stops at 40 pages (`pdf_max_pages`), and
    the first 40 are all recitals; Article 4, the duty the claim states, comes after them. The
    judges read recitals about AI literacy and said not found. The auditor does not tell a
    partly-read document from a whole one. Across the re-audit, 4 PDFs behind flags were cut
    short at 40 pages, and they carry 13 of OpenAI's flagged citations (EUR-Lex 7, an APHIS
    report of 85 pages 4, two inspector-general reports of over 40 pages 1 each). Some of those may
    be right; a not found on pages that were never read is not a verdict either way.
  - **A judge misread the page (1, Claude).** The claim: upside risks to inflation persisted at
    the time of the Fed's September 2025 cut. CNBC's page says "upside threats to inflation
    continued", in the article the old reader kept too. The finder quoted the minutes instead,
    that these risks "had either diminished or not increased", and the judge read that as
    against the claim. Not increased is not gone. The judge saw the backing sentence and weighed
    it wrongly.
  - **Found on the way.** The saved audits record every cited page as "html" with no title, PDFs
    included, because the pages' text is not kept with them. The page judge's label is right; only
    that field is wrong.
  - **What this suggests, not decided.** Treat a PDF cut short as unchecked when nothing is found
    in the pages read, or read further into long PDFs for the auditor. The first changes no
    model call; it would move up to 13 OpenAI flags out of the flags. The name and misreading
    errors are judge errors, and a prompt change for them would need its own decision and a
    fresh check.

## D-050. The auditor reads long PDFs to the end, and says when it could not (after D-049)

Drafted 25 November 2026. **Parked by Aditya the same day, not built.** It touches 13 of
OpenAI's 114 flags and cannot unlock the comparison (see "What it does not do"), so the project
ships without it.

**What.** Three changes, all in how the auditor reads, none in how it judges.

- **Read up to 300 pages of a PDF, not 40.** For the auditor only (`audit_pdf_max_pages`). The
  research agent keeps 40, so its evals stay valid. The 15 MB and 20-second limits stay.
- **A page cut short cannot be "not on the page".** If a PDF still has pages past the limit and
  the judges find nothing in the pages read, that page is marked "could not check", with the
  reason "read only the first 300 of N pages". A "supported", "partly supported" or
  "contradicted" from the pages read stands, because the evidence for it was read. The claim's
  label follows the existing order, in which "could not check" ranks above "not on the page".
- **Saved audits record each page as it was read.** The real-world runner never gave the fetched
  pages to the report, so every saved page says "html" with no title and no quote context. The
  runner now hands them over, as the live API already does. Labels are not affected.

**Why.** D-049's diagnosis: one of the 4 flags Aditya rejected cites the AI Act, a 144-page PDF
on EUR-Lex. The first 40 pages are recitals; Article 4 is on page 51. Fetched again with no model
calls:

- **4 PDFs behind flags in the re-audit run past 40 pages:** EUR-Lex (144), an APHIS report (85),
  NASA's inspector general (50) and the Labor Department's (44). They carry 13 of OpenAI's flagged
  citations and none of Claude's. 11 other flagged PDFs were read whole.
- **Reading them to the end is cheap.** The 144-page Act takes 2.3 seconds, against 0.9 at 40
  pages, and is 596,000 characters. The free word-match shortlist still sends at most 100 passages
  to the reranker, and the judges still see 6, so the cost per claim does not change.
- **It reaches the evidence.** With the whole Act read, the passage holding Article 4's wording is
  in the shortlist for the claim Aditya checked. For the 13 flags, between 4 and 76 of the 100
  shortlisted passages now come from past page 40.

**Considered.**

- **Only marking cut PDFs "could not check".** No model calls and no re-audit of the judges, but
  it gives up on the 13 citations instead of checking them. Kept as the backstop above 300 pages.
- **Only reading further.** Leaves a document over the new limit marked "not on the page" when the
  evidence may be past it.
- **No limit.** One huge PDF could hold up a live run. 300 pages covers every flagged PDF here.
- **Re-auditing only the 4 answers that cite these PDFs.** A few cents, but their claims would be
  split again and judged on a different day from the rest of the run. Re-auditing everything, as
  D-049 did, keeps one run read one way.

**Trade-off.**

- **This moves only OpenAI's figures.** All 13 are OpenAI flags, so its failure rate can only go
  down. That is the direction a reader suspicious of bias would ask for, but it is still a change
  made after looking at labels, and it is recorded as that.
- **More pages, more noise.** A long document has more passages that share words with a claim.
  The reranker and the judges only ever see the best 6.
- **Live runs.** A long PDF adds a few seconds to a live audit and a few MB of memory on the
  1 GB Cloud Run instance.

### The re-audit

- **Runs:** the same three as D-049, from the saved answers: the main run with both page judges,
  and the re-asks. Results go to a new folder, `evals/realworld/full_pdf/`; D-049's audits stay.
- **Cost:** D-049's audits cost $0.93 (Haiku), $0.96 (luna) and $0.49 (re-ask), $2.38 in all.
  These pages add no judge tokens, so about $2.40. Hard cap of $4 in code. Aditya says yes first.

### What it does not do

- **The second hand check stands as scored.** Its EUR-Lex item would now leave the flags, but a
  check is scored on the auditor it was drawn from. Re-scoring it after a fix would be moving the
  bar.
- **No third hand check, and the comparison stays withheld.** All 14 of Claude's own-cited flags
  in D-049's audits have now been seen by Aditya, 7 in each check, so a third blind check of
  these answers has almost no Claude flags to draw. A third check would need new answers, and
  that is a decision of its own.
- **No judge change.** The other 3 disagreements were judge errors: a name carried in from the
  answer ("Q1") that the page does not use, and a misread. A prompt change moves the benchmark
  score and needs its own decision.

### Tests

- The auditor reads past page 40 of a long PDF; the research agent stops at 40.
- A PDF over the auditor's limit with nothing found is "could not check", with the pages read
  and the total in the reason. One that is supported or contradicted from the pages read keeps
  that label.
- A PDF read to its end, and every web page, are labelled as before.
- A saved real-world audit records each page's kind and title, and its quotes' context.

## D-051. The day's spend survives a restart (D-043, phase 3)

Drafted 25 November 2026. Waiting for Aditya's approval.

**What.** The dollars spent today by live runs, audits and checks are kept in Qdrant, in a small
collection of their own (`evidentia_spend`), one point per UTC day. When the server starts, it
reads today's figure. Each time a run, audit or check finishes, the new total is written back.

- **Only the total is kept.** The per-address counts stay in memory. Storing them would mean
  storing visitors' IP addresses, and the daily total already bounds what any address can spend.
- **If Qdrant cannot be read at start, live runs are refused** until it can, with the message
  "Live runs are paused: today's spend could not be read." Recorded runs still play. Each new
  request tries the read again. Failing open would bring back the gap this fixes.
- **If a write fails,** the total stays right in memory and the write is tried again at the next
  finish. The failure is logged, with no secret in it.

**Why.** The counters live in memory (D-028), and Cloud Run stops the only instance when no one is
using it. Each fresh start begins the day at $0, so the $1 daily cap is not a real cap: a visitor
who waits for the server to sleep gets a fresh budget. Each run is still capped at $0.25.

**Considered.**

- **Neon Postgres** (in the plan's stack). A new account, a new secret and a new driver for one
  number.
- **Firestore or a Cloud Storage file.** New Google APIs, permissions and a new library.
- **Keeping it in memory with a minimum of one instance.** Costs money every hour, and a restart
  still resets it.
- **Console limits alone.** They are the real backstop and are still needed (Aditya sets them),
  but they are monthly, so one bad day could use a month's budget.

**Trade-off.**

- **Qdrant becomes needed for audits too.** Before, only the research agent used it. The free
  cluster pauses after a long idle spell; then live runs and audits are refused until it wakes.
- **A run in flight when the server dies is not counted** (at most $0.25, the per-run cap).
- **One instance only, as now.** Two instances would each write their own total.

### Tests

- A new server reads today's spend and refuses a run that would go over the cap.
- Each finish writes the new total; a new day starts at $0.
- A store that cannot be read at start refuses live runs; one that fails to write keeps the
  total in memory and tries again.
- No IP address is written to the store.

## D-052. The research agent on the open web

Drafted 25 November 2026. Waiting for Aditya's approval, with its cost.

**What.** Ask the research agent the same 40 questions again, this time from the start: it plans,
searches the live web, fetches and reads what it finds, as the site does. Plain RAG answers each
question from the same pages the agent fetched, so the two still see the same evidence. The same
judge as before (Opus, with the checker's rubric) scores both. Results go to a new file,
`evals/results/open_web.json`; the clean-corpus results stay as they are.

Measured, for each system: the share of claims shown as backed that the judge finds fully
backed (the same measure as on the clean pages), the share whose main point is backed, claims per
question, and cost per question. For the agent only: the share of its claims labelled
unverified, and how many pages it fetched, read and could not read, by reason.

Shown on the evals page and in the README's results block beside the clean-corpus figures. The
"not measured on the open web" item comes off the "What was not done" list, replaced by what the
run found.

**Why.** Every research-agent figure so far comes from 50 saved pages, mostly Wikipedia, which
are cleaner than the open web. The open web has paywalls, script-built pages, refusals, near
duplicates and pages that disagree. That is where a checker should matter more, if it matters
at all.

**Considered.**

- **New questions.** The same 40 keep the comparison with the clean pages direct.
- **Scoring the agent's answers with the auditor.** The auditor has not passed its own hand
  check on real answers, so it cannot be the measure here.
- **The agent alone, with no plain RAG.** Then there is nothing to compare against. Giving plain
  RAG the agent's own fetched pages keeps the comparison about writing and checking, not search.
- **Retrieval scores on the open web.** They need gold passages, and there are none for pages
  found live. Left out.

**Trade-off.**

- **It cannot be repeated exactly.** Search results and pages change. The run saves the
  addresses it fetched and when, so it can be inspected, not replayed.
- **The questions were written around Wikipedia pages,** so search will often find Wikipedia
  again. The result reports the share of fetched pages from wikipedia.org, so a reader can see
  how open the "open web" really was.
- **The judge is a model,** from the same family as the writer, as on the clean pages. No person
  checks it, and the page says so.
- **One run of 40 questions,** so the intervals will be wide.

### Cost

On the clean pages the shipped agent cost $1.96 for 40 questions, and plain RAG $0.56. The open
web adds search, more pages to read and to embed, and possibly a repair round more often. About
$5 in all, judge included. Hard cap of $8 in code. Aditya says yes first.

### Tests

- The open-web runner starts the graph at "plan", not "retrieve".
- Plain RAG answers from the pages the agent fetched for the same question, and from no others.
- The result file records each fetched address, when it was read, and why any page was not.
- The evals page and the README block read the new file, and say so when it does not exist.

**Changed on 26 November, after a 2-question trial and before the run: 20 questions, not 40.**
The trial cost about $0.41 for 2 questions, judge included, so all 40 would be about $8 to $9,
over the $5 approved. Aditya chose 20. They are drawn with a fixed seed (20261126) in the
corpus's own mix, 15 factual and 5 contested, because the first 20 questions are all factual and
contested questions are where pages disagree. The sample is fixed in code before any of the 20
is asked. Cap $6. The trial's figures are kept apart (`open_web_trial.json`) and are not
reported.
