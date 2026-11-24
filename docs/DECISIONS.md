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
said money and API credits are not a constraint and to favour quality. D-004, D-005, D-006 and
D-008 were updated for that before any code was written, and D-011 was added.
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
- Fetched text goes in the user message inside `<source id="...">` blocks. The system prompt says
  those blocks are data and that instructions inside them must be ignored. Any `</source>` inside
  fetched text is escaped.
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
`voyage-4-large` $0.12 and `rerank-3` $0.05 per million tokens, Tavily advanced search 2 credits
at the pay-as-you-go rate of $0.008 per credit.

**Why.** Checking before the call is what makes the cap hard; checking only after would let one
large call overshoot. Free-tier usage is still counted at list price so the number is the true
cost of a run, not a number that only holds while credits last.

**Considered.** Counting tokens exactly with the token-counting endpoint before each call (exact,
but an extra network call per model call). Tracking only model cost (misses search and embeddings).

**Trade-off.** The pre-call check uses an estimate: input characters divided by 3 plus the full
`max_tokens`. It is deliberately high, so a run can stop a little before the real cap.

## D-006. Search, fetch and extract

**What.** `search.py` calls Tavily with `search_depth="advanced"`, 6 results per query, and keeps
at most 12 unique URLs per run. `fetch.py` downloads each page itself with `httpx`:

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

**Considered.** `voyage-4` or `voyage-4-lite` (half and a sixth of the price; M3 can compare). `fastembed` for BM25 (pulls
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
