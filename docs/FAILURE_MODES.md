# Failure modes

Where Evidentia goes wrong, how we know, and what the code does about it. Each entry names the
decision in [`DECISIONS.md`](DECISIONS.md) that holds the evidence. Figures quoted here come from
`evals/results/`; where a diagnosis counted cases by hand, the count is in the decision entry,
not repeated here.

Status: **fixed** (the code no longer does it), **contained** (it still happens, and the output
says so), or **open** (known, not addressed).

## The auditor: reading the page

### The evidence is on the page but not in the text the judges read

- **What happens.** A date in a page header, a figure in a caption or stat box, a side table. A
  reader that keeps only the article drops them, and the judges say "not on the page".
- **How we know.** The first blind hand check (D-044): most of the flags the person rejected had
  their evidence in exactly these places.
- **What the code does.** The auditor reads the article, then the rest of the page's visible
  text, still as the page's own words, so quotes are still checked word for word (D-049).
- **Status: fixed** for HTML pages. The cost: menus and related-story headlines are read too, and
  can mislead a judge.

### A long PDF is read only in part

- **What happens.** PDFs are read up to a page limit. Evidence past it is never seen, and the
  claim is marked "not on the page" as if the whole document had been read.
- **How we know.** One of the second hand check's rejected flags cited a law of well over a
  hundred pages; the article it described sits past the limit (D-049 diagnosis).
- **What the code does.** Nothing yet. A fix (read further, and call a cut-off PDF "could not
  check") was drafted as D-050 and parked: it touches few flags.
- **Status: open.**

### Pages that change after the answer was written

- **What happens.** Live prices, counters, "latest" pages. The answer quoted one value, the
  audit reads another.
- **How we know.** A rejected flag in the first hand check cited a crypto price page (D-044).
- **What the code does.** Each saved audit records when it read the page.
- **Status: contained.** The verdict is about the page as read, which may not be the page the
  tool saw.

### Pages the fetcher cannot read

- **What happens.** robots.txt disallows us, the site refuses the request or redirects to a block
  page, the page has too little text without running scripts, or it times out.
- **What the code does.** The claim is labelled **could not check**, never "not on the page"
  (`evidentia/audit/schemas.py`). Pages that refuse are left unread on purpose: no proxy and no
  disguised browser (D-043). A browser reader for script-built pages was tried and changed little
  (D-046).
- **Status: contained.** These claims get no verdict, and the scorecard counts them apart.

### Short pages

- **What happens.** A paywall teaser or a cookie wall can look like a page.
- **What the code does.** A page whose article is under the minimum length is treated as unread
  (D-042). Menus do not count towards it (D-049). D-047 judged these pages anyway, as a
  sensitivity check, to see what the rule hides.
- **Status: contained.**

## The auditor: judging

### A name the answer uses that the page does not

- **What happens.** The answer calls something by a name ("Q1") in one sentence. To make each
  claim stand alone, the splitter carries the name into later claims. The page describes the
  same thing in full but never uses that name, and a judge says "not on the page".
- **How we know.** Two of the second hand check's four rejected flags (D-049 diagnosis).
- **Status: open.** A prompt change would move the benchmark score, so it needs its own
  decision and a fresh check.

### A judge weighs the wrong sentence

- **What happens.** The page says the claim in one place and something vaguer in another; the
  finder quotes the vaguer line and the judge reads it as against the claim. Also: a past record
  read as contradicting a later one.
- **How we know.** One rejected flag in each hand check (D-044, D-049 diagnoses).
- **Status: open**, for the same reason as above.

### Partly backed claims

- **What happens.** Both judges agree the main point is on the page but a detail is not. On
  LLM-AggreFact this is 18% of claims, and the benchmark's people accepted about half of them as
  supported (`aggrefact_pooled-dev550b+test2_q-haiku_p-haiku.json`).
- **What the code does.** "Partly backed" is its own label and never counted as a failure, so a
  count of failures is a lower bound.
- **Status: contained.**

### Some kinds of text are much harder than others

- **What happens.** On LLM-AggreFact, balanced accuracy ranges from 0.57 (ExpertQA) to 0.93
  (Lfqa) across its eleven sources (same file). Long expert answers and multi-part claims are
  the weak spot.
- **Status: open.** Shown on the site's Evals page, weakest first.

### When the two judges disagree

- **What happens.** On LLM-AggreFact, 18% of claims get no verdict (same file as above).
- **What the code does.** It is labelled **needs a human**, with both judges' reasons. This is
  the design: a disagreement is shown, not guessed (D-038).
- **Status: contained.**

### Both judges are the same model

- **What happens.** Two Claude Haiku calls can share a blind spot. Agreement between them is
  weaker evidence than agreement between two different models.
- **What was tried.** An OpenAI page judge made no clear difference on the benchmark's practice
  rows and was dropped by a rule set in advance (D-038). Sonnet as the judges was no better and
  cost far more (D-039). The real-world audit was also run with the OpenAI page judge, as a
  check on this blind spot (D-042, D-049).
- **Status: open.**

## The auditor on real answers

### It has not passed its own hand check

- **What happens.** On answers from two AI search tools, a person upheld 54% and then 69% of the
  flags he could settle, against a bar of 70% set before any label
  (`realworld_hand_check.json`, `realworld_hand_check_2.json`).
- **What the code does.** The site and the README do not compare the two tools. The findings
  page says why.
- **Status: open.** A third check would need new answers: every flag on one tool's answers has
  now been seen (D-050).

## The research agent

### It is not more accurate than plain RAG

- **What happens.** On the saved corpus and on the open web, the share of claims shown as backed
  that a judge found fully backed is the same for the pipeline and for plain RAG, within the
  intervals
  (`citation_accuracy.json`). What it adds is a short exact quote and a checker, at a higher
  cost per question (same file).
- **Status: open, and the reason the project became an auditor** (D-034).

### Measured on clean pages, and on the open web only once

- **What happens.** The main corpus is mostly Wikipedia, cleaner than the open web, and the search
  test's gold passages were drafted by a model (then checked word for word by code). On the open
  web the agent was asked 20 questions, once (`open_web.json`); it was again not clearly more
  accurate than plain RAG on the same pages (D-052). Search results change, so that run cannot be
  repeated exactly.
- **Status: open.** There are no retrieval scores on the open web, since live pages have no gold
  passages.

### No person has labelled the checker

- **What happens.** The checker's agreement figure is with a second model from the same family
  (`checker_agreement.json`), which says it is consistent, not that it is right.
- **Status: open.**

## Untrusted pages

### Instructions hidden in a page

- **What happens.** A fetched page can contain text addressed to the model.
- **What the code does.** Page text is passed inside marked data blocks with a random tag and
  treated as data (rule 9). Quotes must be exact spans, so a model cannot invent evidence.
- **How we know.** Hand-made pages with hidden instructions, a paywall and two pages that
  disagree all passed (`nasty.json`).
- **Status: contained**, for these cases. It is not a security guarantee.

## The public site

### Spending

- **What happens.** A public button that spends money.
- **What the code does.** A hard cap per run, audit and check; per-address daily limits; a daily
  budget for all visitors, kept in Qdrant so a restart does not reset it (D-051). If the day's
  spend cannot be read, live runs are refused.
- **Gaps.** Per-address counts are in memory and reset on a restart. A run in flight when the
  server dies is not counted. Monthly limits in each provider's console are the backstop that
  cannot be bypassed.
- **Status: contained.**

### Cold starts

- **What happens.** The API scales to zero, so the first request after a quiet spell waits for
  the server to start. If the free Qdrant cluster has paused, live runs are refused until it
  wakes.
- **What the code does.** The site says "Starting…" and why while it waits (D-043), and recorded
  audits and runs play without the API.
- **Status: contained.**

## Not supported

- **Video.** YouTube's robots.txt disallows the caption addresses (D-032).
- **Charts and figures.** A number read off a chart has no exact text to check (D-033).
