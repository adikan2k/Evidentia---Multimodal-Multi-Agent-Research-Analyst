"use client";

import { motion } from "motion/react";
import { Mark } from "@/components/Mark";
import {
  type AuditClaim,
  type AuditPage,
  type AuditQuote,
  LABEL_MARK,
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

/** The last part of an address, readable: "/wiki/Kessler_syndrome" becomes "Kessler syndrome". */
function pageName(page: AuditPage): string {
  if (page.title) return page.title;
  try {
    const last = new URL(page.url).pathname.split("/").filter(Boolean).pop() ?? "";
    const words = decodeURIComponent(last)
      .replace(/\.[a-z]{2,5}$/i, "")
      .replace(/[-_]+/g, " ")
      .trim();
    return words.length > 3 ? words : page.host;
  } catch {
    return page.host;
  }
}

/** One quote, highlighted inside the text around it on the page. */
function QuoteInPlace({ quote }: { quote: AuditQuote }) {
  const pages = quotePages(quote);
  return (
    <p className="sheet-text text-[1.0625rem] leading-[1.7] text-ink-soft">
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
      {pages && <span className="data ml-2 text-ink-soft">PDF {pages}</span>}
    </p>
  );
}

/** The quote judge's reason, or what its silence means. */
function quoteJudgeSaid(page: AuditPage): string {
  if (page.quote_reason) return page.quote_reason;
  if (page.quotes.length === 0) return "Found no words on the page that state or contradict the claim.";
  return "The quotes state the claim.";
}

/** A strip cut from the cited page, with what each judge made of it. */
function Clipping({ page }: { page: AuditPage }) {
  const firstPage = page.quotes[0]?.pages?.[0];
  const href = firstPage ? `${page.url}#page=${firstPage}` : page.url;
  return (
    <section className="mt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="min-w-0 font-medium text-ink underline decoration-rule underline-offset-4 hover:decoration-ink"
        >
          <span className="line-clamp-2">{pageName(page)} ↗</span>
        </a>
        <span className={`label flex items-center gap-1.5 ${LABEL_TONE[page.label]}`}>
          <Mark kind={LABEL_MARK[page.label]} />
          {LABEL_TEXT[page.label]}
        </span>
      </div>
      <p className="data mt-1 text-ink-faint normal-case">{page.host}</p>

      <div className="clipping mt-3 space-y-3 px-4 py-4">
        {page.skipped && (
          <p className="label font-normal text-ink-soft">This page was not read: {page.skipped}.</p>
        )}
        {!page.skipped && page.quotes.length === 0 && (
          <p className="label font-normal text-ink-soft">
            No words on this page state the claim, so there is nothing to quote.
          </p>
        )}
        {page.quotes.map((q) => (
          <QuoteInPlace key={q.text} quote={q} />
        ))}
      </div>

      {!page.skipped && (
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="border-l-2 border-ink pl-3">
            <dt className="label">Quote judge</dt>
            <dd className="data mt-0.5 text-ink-faint normal-case">sees only the quotes</dd>
            <dd className="label mt-1.5 font-normal text-ink-soft">{quoteJudgeSaid(page)}</dd>
          </div>
          <div className="border-l-2 border-ink pl-3">
            <dt className="label">Page judge</dt>
            <dd className="data mt-0.5 text-ink-faint normal-case">sees the page</dd>
            <dd className="label mt-1.5 font-normal text-ink-soft">
              {page.page_reason || "Gave no reason."}
            </dd>
          </div>
        </dl>
      )}
    </section>
  );
}

function ClaimResult({ claim, number }: { claim: AuditClaim; number: number }) {
  return (
    <div className="border-t border-rule pt-5 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="data text-ink-faint">Claim {String(number).padStart(2, "0")}</span>
        {claim.label && (
          <span className={`label flex items-center gap-1.5 ${LABEL_TONE[claim.label]}`}>
            <Mark kind={LABEL_MARK[claim.label]} />
            {LABEL_TEXT[claim.label]}
          </span>
        )}
      </div>
      <p className="mt-2 text-[1.0625rem] leading-snug font-medium text-ink">{claim.claim}</p>
      {claim.disputed && (
        <p className="label mt-2 font-normal text-contradicted">
          Another cited page contradicts this claim.
        </p>
      )}
      {claim.cited_by === "paragraph" && (
        <p className="label mt-2 font-normal text-ink-soft">
          Cited at the end of its paragraph, not in this sentence.
        </p>
      )}
      {claim.label === "citation_unread" && (
        <p className="label mt-2 font-normal text-ink-soft">
          This sentence is marked {(claim.unread_markers ?? []).map((m) => `[${m}]`).join(" ")}, but
          no source with that number could be read from what was pasted. So it was not checked
          against any page.
        </p>
      )}
      {claim.label === "uncited" && (
        <p className="label mt-2 font-normal text-ink-soft">
          No citation in this sentence or its paragraph.
        </p>
      )}
      {claim.label === "needs_human" && (
        <p className="label mt-2 font-normal text-human">
          The two judges disagree, so no verdict is given. Their reasons are below.
        </p>
      )}
      {(claim.pages ?? []).map((page) => (
        <Clipping key={page.citation_id} page={page} />
      ))}
    </div>
  );
}

type Props = {
  sentence: Sentence | null;
  firstNumber: number;
  judged: boolean;
  onClose: () => void;
};

/**
 * The evidence behind one sentence. Beside the sheet on a wide screen; on a phone it comes up
 * from the bottom of the screen, over the sheet.
 */
export function AuditEvidence({ sentence, firstNumber, judged, onClose }: Props) {
  if (!sentence) {
    return (
      <div className="label hidden rounded-[3px] border border-dashed border-ink-faint p-6 font-normal text-ink-soft lg:block">
        Select a sentence on the sheet. The words from the cited page appear here, with what each
        judge made of them.
      </div>
    );
  }
  return (
    <section
      aria-label="Evidence for the selected sentence"
      className="sheet p-5 max-lg:fixed max-lg:inset-x-0 max-lg:bottom-0 max-lg:z-40 max-lg:max-h-[78vh] max-lg:overflow-y-auto max-lg:rounded-b-none max-lg:shadow-[0_-12px_40px_-12px_rgb(20_20_19/0.45)] md:p-6"
    >
      <div className="mb-4 flex items-center justify-between gap-4">
        <h3 className="label text-ink-soft">Evidence</h3>
        <button
          type="button"
          onClick={onClose}
          className="label -my-2 flex min-h-10 items-center px-2 text-ink-soft underline underline-offset-4 hover:text-ink"
        >
          Close
        </button>
      </div>
      {judged ? (
        <div className="space-y-5">
          {sentence.claims.map((claim, i) => (
            <ClaimResult key={`${claim.claim}-${i}`} claim={claim} number={firstNumber + i} />
          ))}
        </div>
      ) : (
        <p className="label font-normal text-ink-soft">
          <span className="animate-pulse">The judges are still reading the cited pages…</span>
        </p>
      )}
    </section>
  );
}
