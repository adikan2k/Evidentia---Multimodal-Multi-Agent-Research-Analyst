"use client";

import { motion } from "motion/react";
import {
  type AuditClaim,
  type AuditPage,
  type AuditQuote,
  LABEL_TEXT,
  LABEL_TONE,
  quotePages,
  type Sentence,
} from "@/lib/audit";

// How much of the page to show either side of a quote: enough to see it in its setting.
const AROUND = 200;

function lastWords(text: string): string {
  if (text.length <= AROUND) return text;
  const cut = text.slice(-AROUND);
  return cut.slice(cut.indexOf(" ") + 1);
}

function firstWords(text: string): string {
  if (text.length <= AROUND) return text;
  const cut = text.slice(0, AROUND);
  return cut.slice(0, cut.lastIndexOf(" "));
}

/** One quote, highlighted inside the text around it on the page. */
function QuoteInPlace({ quote }: { quote: AuditQuote }) {
  const pages = quotePages(quote);
  return (
    <p className="text-[0.9375rem] leading-[1.75] text-ink-faint">
      {quote.context && <span>… {lastWords(quote.context.before)}</span>}
      <motion.mark
        className="marker"
        initial={{ backgroundSize: "0% 82%" }}
        animate={{ backgroundSize: "100% 82%" }}
        transition={{ duration: 0.8, ease: [0.3, 0.1, 0.2, 1], delay: 0.1 }}
      >
        {quote.text}
      </motion.mark>
      {quote.context && <span>{firstWords(quote.context.after)} …</span>}
      {pages && <span className="label ml-2 text-ink-soft">PDF {pages}</span>}
    </p>
  );
}

/** The quote judge's reason, or what its silence means. */
function quoteJudgeSaid(page: AuditPage): string {
  if (page.quote_reason) return page.quote_reason;
  if (page.quotes.length === 0) return "Found no words on the page that state or contradict the claim.";
  return "The quotes state the claim.";
}

function PageResult({ page }: { page: AuditPage }) {
  const firstPage = page.quotes[0]?.pages?.[0];
  const href = firstPage ? `${page.url}#page=${firstPage}` : page.url;
  return (
    <section className="mt-5 border-t border-rule pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="min-w-0 truncate font-serif text-lg text-ink underline decoration-rule underline-offset-4 hover:decoration-ink"
        >
          {page.title || page.host} ↗
        </a>
        <span className={`label ${LABEL_TONE[page.label]}`}>{LABEL_TEXT[page.label]}</span>
      </div>
      <p className="label mt-1 text-ink-faint">{page.host}</p>

      {page.skipped ? (
        <p className="mt-3 text-sm text-ink-soft">Not read: {page.skipped}.</p>
      ) : (
        <div className="mt-3 space-y-3">
          {page.quotes.length > 0 ? (
            page.quotes.map((q) => <QuoteInPlace key={q.text} quote={q} />)
          ) : (
            <p className="text-sm text-ink-soft">No quote on this page states the claim word for word.</p>
          )}
        </div>
      )}

      {!page.skipped && (
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="label text-ink-faint">Quote judge · sees only the quotes</dt>
            <dd className="mt-1 text-ink-soft">{quoteJudgeSaid(page)}</dd>
          </div>
          <div>
            <dt className="label text-ink-faint">Page judge · sees the page</dt>
            <dd className="mt-1 text-ink-soft">{page.page_reason || "—"}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}

function ClaimResult({ claim, number }: { claim: AuditClaim; number: number }) {
  return (
    <div className="mt-6 first:mt-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="label text-ink-faint">Claim {String(number).padStart(2, "0")}</span>
        {claim.label && (
          <span className={`label ${LABEL_TONE[claim.label]}`}>{LABEL_TEXT[claim.label]}</span>
        )}
        {claim.disputed && <span className="label text-contradicted">another cited page contradicts it</span>}
      </div>
      <p className="mt-1.5 text-[1.0625rem] leading-snug text-ink">{claim.claim}</p>
      {claim.cited_by === "paragraph" && (
        <p className="label mt-1.5 text-ink-faint">Cited at the end of its paragraph, not in this sentence</p>
      )}
      {claim.label === "citation_unread" && (
        <p className="mt-2 text-sm text-ink-soft">
          This sentence is marked {(claim.unread_markers ?? []).map((m) => `[${m}]`).join(" ")}, but
          no source with that number could be read from what was pasted. So it was not checked
          against any page.
        </p>
      )}
      {claim.label === "uncited" && (
        <p className="mt-2 text-sm text-ink-soft">No citation in this sentence or its paragraph.</p>
      )}
      {claim.label === "needs_human" && (
        <p className="mt-2 text-sm text-human">
          The two judges disagree, so neither verdict is shown. Their reasons are below.
        </p>
      )}
      {(claim.pages ?? []).map((page) => (
        <PageResult key={page.citation_id} page={page} />
      ))}
    </div>
  );
}

type Props = { sentence: Sentence | null; firstNumber: number; judged: boolean };

/** The evidence behind one sentence of the audited answer. */
export function AuditEvidence({ sentence, firstNumber, judged }: Props) {
  if (!sentence) {
    return (
      <div className="rounded-lg border border-dashed border-rule p-8 text-sm text-ink-faint">
        Click an underlined sentence to see the words on the cited page, and what each judge said.
      </div>
    );
  }
  if (!judged) {
    return (
      <div className="rounded-lg border border-rule p-8 text-sm text-ink-soft">
        <span className="animate-pulse">The judges are still reading the cited pages…</span>
      </div>
    );
  }
  return (
    <article className="rounded-lg border border-rule bg-white/60 p-7 shadow-[0_1px_0_var(--rule)]">
      {sentence.claims.map((claim, i) => (
        <ClaimResult key={`${claim.claim}-${i}`} claim={claim} number={firstNumber + i} />
      ))}
    </article>
  );
}
