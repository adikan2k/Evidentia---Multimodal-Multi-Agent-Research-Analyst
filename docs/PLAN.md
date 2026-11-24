# Evidentia rebuild plan

## Goal

A research agent whose every sentence can be checked. You ask a question. It reads web pages,
PDFs and videos, and writes an answer where each claim links to the exact quote, PDF page or
video second that supports it. Claims it cannot support are marked unverified.

Interview line: "Most research agents ask you to trust them. Mine proves each sentence, and
here is how often it is right."

## What we keep and what we drop

Keep: the name, the repo, the ideas in `backend/app/ingest` (trafilatura, pdfplumber, YouTube
captions), the citation formatters, the Next.js shell.

Drop: the template report writers, the keyword "fact checker" and "credibility" scores, the local
summarizers (Ollama, BART), Whisper, BLIP, torch, MinIO, Valkey, the invented home-page stats.
Old code stays in git history and on the `archive/2025-local` branch.

## Stack

| Part | Choice |
|---|---|
| Orchestration | LangGraph 1.2 (state graph, checkpoints, approval interrupts, node timeouts) |
| Models | Claude via `langchain-anthropic`: `claude-sonnet-5-5` plans, writes, checks; `claude-haiku-5-5` reads |
| Web search | Tavily (test on 10 of our own questions before trusting it) |
| Vector database | Qdrant Cloud: dense + BM25 sparse vectors on each point, Query API with RRF fusion |
| Embeddings | Voyage text model, Voyage reranker, `voyage-multimodal-3.5` for page images |
| Records | Neon Postgres: runs, sources, passages, claims, citations |
| API | FastAPI on Cloud Run, server-sent events for live steps |
| Frontend | Next.js + Tailwind + shadcn on Vercel, pdf.js for page highlights |
| Tracing | Langfuse |
| Evals | pytest + DeepEval in CI, our own retrieval metrics, bootstrap confidence intervals |

## The graph

```
plan -> search -> fetch + extract -> index (Qdrant) -> retrieve (hybrid + rerank)
     -> write claims with quotes -> quote check (code) -> checker (independent model)
     -> enough evidence?  no -> rewrite query -> retrieve again (max 2 loops)
                          yes -> final report (supported / partial / unverified)
```

The checker sees only the claim and the quote. It never sees the writer's reasoning.

## Milestones

Each one ends with something you can run and show.

### M0. Clean slate
- Aditya: rotate the Qdrant key in the Qdrant console. The old one is public.
- Commit the current local work as-is to a new branch `archive/2025-local` (local only, do not push).
- Create `rebuild` from `main`. Remove the hardcoded Qdrant URL and key from `settings.py`,
  the invented stats and "Live Updates" badge on the home page, and the clutter files.
- New Python package `evidentia/` with `pyproject.toml`, ruff, pytest, a passing empty test.
- Done when: `pytest` passes and `git grep` finds no secret.

### M1. One real run in the terminal
- plan -> Tavily search -> fetch and extract web pages -> chunk -> embed -> Qdrant hybrid
  retrieval -> answer as a list of claims, each with a quote and source URL -> quote check in code.
- Langfuse tracing and the cost cap from the first commit.
- Done when: `python -m evidentia "question"` prints claims, quotes, sources and the run cost.

### M2. The checker and the loop
- Independent checker node labels each claim supported, partial or unsupported.
- Unsupported claims trigger a rewritten query and one more retrieval; still unsupported means "unverified".
- Done when: a run on a question with conflicting sources shows both sides and at least one honest "unverified".

### M3. Evals
- 40 questions with known good sources. Retrieval table: keyword vs dense vs hybrid vs hybrid + rerank.
- About 150 claim-and-quote pairs labelled by hand. Measure how often the checker agrees with you.
- Baseline: one-shot RAG with no checker. Report citation accuracy for both, with confidence intervals.
- Nasty tests: a page with hidden instructions, a paywalled page, two sources that contradict.
- Done when: `make evals` writes `evals/results/*.json` and a "what failed" section. Evals run in CI.

### M4. Live site
- FastAPI endpoints with server-sent events. Per-IP and per-day caps. Per-run cost in the response.
- Frontend restyled: question box, live graph steps, report where clicking a claim opens its evidence.
- Design bar (set by Aditya on 2026-11-24): the site should look and move like the best work in
  these galleries, with rich animation and a top-tier finish:
  https://minimal.gallery/tag/ai/ , https://www.framer.com/community/gallery/categories/ai/ ,
  https://www.awwwards.com/websites/ .
  Study them at the start of M4 and write the chosen direction into `docs/DECISIONS.md` before
  building. Everything shown on screen must still be real: no invented numbers, no fake statuses.
- Deploy: API on Cloud Run, frontend on Vercel.
- Done when: a stranger can run a question from the public URL.

### M5. PDFs
- PDFs: text with page numbers; a claim names its page, and its source link opens the PDF at
  that page (D-030, D-031).
- Left out: YouTube captions, because YouTube's robots.txt disallows the caption endpoints
  (D-032); charts read by vision, because a chart reading has no exact text span to check (D-033).
- Done when: one report cites a web page and a PDF page, each through a quote that passes the
  code check.

### M6. Ship
- README with architecture diagram, results table, the nasty test and its result.
- `docs/DECISIONS.md` and `docs/FAILURE_MODES.md` complete. Two-minute demo video. Recorded fallback run.
- Five real users try it; their feedback goes in the README.

## Budget

Claude API inside the $100 monthly credit. Free tiers for Qdrant, Voyage, Tavily, Neon, Langfuse,
Vercel. Hard cap per run in code (start at $0.25) and a daily cap on the public site.

## Environment variables

`ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `VOYAGE_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`,
`DATABASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`.

Keep them in the project's `.env` only. Do not set `ANTHROPIC_API_KEY` as a system variable,
or Claude Code will bill the key instead of the Max plan.
