"use client";

import { AnimatePresence, motion } from "motion/react";
import { Mark, type MarkKind } from "@/components/Mark";
import { type Claim, type Label, pageLabel } from "@/lib/replay";

const LABEL_TONE: Record<Label, string> = {
  supported: "text-supported",
  partial: "text-partial",
  unverified: "text-unverified",
};
const LABEL_MARK: Record<Label, MarkKind> = {
  supported: "tick",
  partial: "tick-caret",
  unverified: "cross",
};
const LABEL_NAME: Record<Label, string> = {
  supported: "Supported",
  partial: "Partly backed",
  unverified: "Unverified",
};

/** The verdict: a proofreader's mark, drawn as the checker answers, with its name. */
export function Stamp({ label }: { label: Label }) {
  return (
    <span className={`label inline-flex items-center gap-1.5 ${LABEL_TONE[label]}`}>
      <Mark kind={LABEL_MARK[label]} draw className="text-[1.1rem]" />
      {LABEL_NAME[label]}
    </span>
  );
}

function status(claim: Claim): string {
  if (claim.label) return "";
  if (claim.quote_found === null) return "Written, not checked yet";
  if (claim.quote_found) return "Quote found on the page, waiting for the checker";
  return "";
}

type Props = {
  claims: Claim[];
  firstDraft: string[];
  selected: number;
  onSelect: (index: number) => void;
};

/** The claims, set on the sheet one under another, each with its mark in the margin. */
export function ClaimList({ claims, firstDraft, selected, onSelect }: Props) {
  return (
    <ol>
      <AnimatePresence initial={false}>
        {claims.map((claim, index) => {
          const active = index === selected;
          const reworded = claim.revised && firstDraft[index] && firstDraft[index] !== claim.text;
          return (
            <motion.li
              key={index}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: index * 0.06, ease: [0.2, 0.7, 0.2, 1] }}
              className="border-b border-rule last:border-b-0"
            >
              <button
                type="button"
                onClick={() => onSelect(index)}
                aria-pressed={active}
                className={`grid w-full gap-x-6 gap-y-2 px-5 py-5 text-left transition-colors duration-200 md:grid-cols-[9.5rem_1fr] md:px-8 ${
                  active ? "bg-paper-deep/70" : "hover:bg-paper/70"
                }`}
              >
                <span className="flex items-start gap-3 md:flex-col md:gap-1.5">
                  <span className="data text-ink-faint">Claim {String(index + 1).padStart(2, "0")}</span>
                  {claim.label && <Stamp key={`${claim.label}-${claim.text}`} label={claim.label} />}
                  {!claim.label && (
                    <span className="label flex items-center gap-1.5 font-normal text-ink-faint">
                      <Mark kind="dots" className="animate-pulse" />
                      Checking
                    </span>
                  )}
                </span>
                <span>
                  {/* The claim's words. If the repair round rewrote it, the new wording swaps in. */}
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.span
                      key={claim.text}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.25 }}
                      className="sheet-text block leading-[1.45] text-ink"
                    >
                      {claim.text}
                    </motion.span>
                  </AnimatePresence>
                  <span className="label mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-normal text-ink-soft">
                    <span>
                      {claim.host}
                      {pageLabel(claim) && <span> · PDF {pageLabel(claim)}</span>}
                    </span>
                    {!claim.label && <span>{status(claim)}</span>}
                    {reworded && (
                      <span title={`First draft: ${firstDraft[index]}`}>Reworded to match its quote</span>
                    )}
                  </span>
                  {claim.label && claim.label !== "supported" && claim.reason && (
                    <span className="label mt-2 block font-normal text-ink-soft">{claim.reason}</span>
                  )}
                </span>
              </button>
            </motion.li>
          );
        })}
      </AnimatePresence>
    </ol>
  );
}
