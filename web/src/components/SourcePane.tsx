"use client";

import { motion } from "motion/react";
import { BreakIt } from "@/components/BreakIt";
import { type Claim, pageLabel, sourceHref } from "@/lib/replay";

// How much of the page to show either side of the quote. Enough to see it in its setting,
// little enough that the quote is what the eye lands on.
const AROUND = 230;

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

/**
 * The evidence for one claim: its quote, shown as a strip cut from the page it came from. The
 * highlighter only appears once code has found the quote word for word on that page.
 */
type Props = { claim: Claim | null; index: number; canCheck: boolean };

export function SourcePane({ claim, index, canCheck }: Props) {
  if (!claim) {
    return (
      <div className="label rounded-[3px] border border-dashed border-ink-faint p-6 font-normal text-ink-soft">
        The source appears here once the writer has made its first claim.
      </div>
    );
  }
  const found = claim.quote_found === true && claim.context !== null;
  const page = pageLabel(claim);

  return (
    <article className="sheet p-5 md:p-6">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <p className="data text-ink-faint">Evidence for claim {String(index + 1).padStart(2, "0")}</p>
          <p className="mt-1.5 line-clamp-2 font-medium text-ink">{claim.title || claim.host}</p>
        </div>
        {claim.url && (
          <a
            href={sourceHref(claim)}
            target="_blank"
            rel="noreferrer"
            className="label flex min-h-10 shrink-0 items-center text-ink underline underline-offset-4"
          >
            {claim.host}
            {page && ` · PDF ${page}`} ↗
          </a>
        )}
      </header>

      {/* Keyed by the quote, so choosing another claim replays the highlighter stroke. */}
      <div className="clipping mt-4 px-4 py-4">
        <p key={`${index}-${claim.quote}-${found}`} className="sheet-text text-[1.0625rem] leading-[1.7] text-ink-soft">
          {found && <span>… {lastWords(claim.context!.before)}</span>}
          {found ? (
            <motion.mark
              className="marker"
              initial={{ backgroundSize: "0% 82%" }}
              animate={{ backgroundSize: "100% 82%" }}
              transition={{ duration: 0.9, ease: [0.3, 0.1, 0.2, 1], delay: 0.15 }}
            >
              {claim.quote}
            </motion.mark>
          ) : (
            <span className="text-ink">{claim.quote}</span>
          )}
          {found && <span>{firstWords(claim.context!.after)} …</span>}
        </p>
      </div>

      <p className="label mt-4 font-normal text-ink-soft">
        {claim.quote_found === null && "Quoted by the writer. Not yet checked against the page."}
        {claim.quote_found === false && (
          <span className="text-unverified">This quote is not on the page word for word.</span>
        )}
        {found && !page && "Found word for word on the page, by code. Shown with the text around it."}
        {found && page && `Found word for word on ${page} of the PDF, by code. Shown with the text around it.`}
      </p>

      {/* Keyed by the claim, so the editor starts from each claim's own wording. */}
      {found && canCheck && claim.label && (
        <BreakIt key={`${index}-${claim.text}`} claimText={claim.text} quote={claim.quote} />
      )}
    </article>
  );
}
