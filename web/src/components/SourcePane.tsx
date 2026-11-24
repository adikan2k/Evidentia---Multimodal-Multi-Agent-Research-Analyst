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
 * The evidence for one claim: its quote, shown inside the surrounding text of the page it came
 * from. The highlighter only appears once code has found the quote word for word on that page.
 */
type Props = { claim: Claim | null; index: number; canCheck: boolean };

export function SourcePane({ claim, index, canCheck }: Props) {
  if (!claim) {
    return (
      <div className="rounded-lg border border-dashed border-rule p-8 text-sm text-ink-faint">
        The sources appear here once the writer has made its first claim.
      </div>
    );
  }
  const found = claim.quote_found === true && claim.context !== null;
  const page = pageLabel(claim);

  return (
    <article className="rounded-lg border border-rule bg-white/60 p-7 shadow-[0_1px_0_var(--rule)]">
      <header className="mb-5 flex items-baseline justify-between gap-4 border-b border-rule pb-4">
        <div className="min-w-0">
          <p className="label text-ink-faint">Evidence for claim {String(index + 1).padStart(2, "0")}</p>
          <p className="mt-1.5 truncate font-serif text-xl leading-tight">{claim.title || claim.host}</p>
        </div>
        {claim.url && (
          <a
            href={sourceHref(claim)}
            target="_blank"
            rel="noreferrer"
            className="label shrink-0 border-b border-ink-faint pb-0.5 text-ink-soft transition-colors hover:border-ink hover:text-ink"
          >
            {claim.host}
            {page && ` · PDF ${page}`} ↗
          </a>
        )}
      </header>

      {/* Keyed by the quote, so choosing another claim replays the highlighter stroke. */}
      <p key={`${index}-${claim.quote}-${found}`} className="text-[0.9375rem] leading-[1.75] text-ink-faint">
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
          <span className="text-ink-soft">{claim.quote}</span>
        )}
        {found && <span>{firstWords(claim.context!.after)} …</span>}
      </p>

      <footer className="label mt-6 border-t border-rule pt-4 text-ink-faint">
        {claim.quote_found === null && "Quoted by the writer. Not yet checked against the page."}
        {claim.quote_found === false && (
          <span className="text-unverified">This quote is not on the page word for word.</span>
        )}
        {found && !page && "Found word for word on the page, by code. Shown with the text around it."}
        {found && page && `Found word for word on ${page} of the PDF, by code. Shown with the text around it.`}
      </footer>

      {/* Keyed by the claim, so the editor starts from each claim's own wording. */}
      {found && canCheck && claim.label && (
        <BreakIt key={`${index}-${claim.text}`} claimText={claim.text} quote={claim.quote} />
      )}
    </article>
  );
}
