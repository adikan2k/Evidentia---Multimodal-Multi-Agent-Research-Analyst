"use client";

import { AnimatePresence, motion } from "motion/react";
import type { Claim, Label } from "@/lib/replay";

const LABEL_COLOUR: Record<Label, string> = {
  supported: "text-supported border-supported",
  partial: "text-partial border-partial",
  unverified: "text-unverified border-unverified",
};

/** The verdict, pressed onto the page like a rubber stamp when the checker answers. */
function Stamp({ label }: { label: Label }) {
  return (
    <motion.span
      initial={{ opacity: 0, scale: 1.6, rotate: -8 }}
      animate={{ opacity: 1, scale: 1, rotate: -2 }}
      transition={{ type: "spring", stiffness: 520, damping: 22 }}
      className={`label inline-block rounded-[3px] border px-1.5 py-0.5 ${LABEL_COLOUR[label]}`}
    >
      {label}
    </motion.span>
  );
}

function status(claim: Claim): string {
  if (claim.label) return "";
  if (claim.quote_found === null) return "written, not checked yet";
  if (claim.quote_found) return "quote found on the page, waiting for the checker";
  return "";
}

type Props = {
  claims: Claim[];
  firstDraft: string[];
  selected: number;
  onSelect: (index: number) => void;
};

export function ClaimList({ claims, firstDraft, selected, onSelect }: Props) {
  return (
    <ol className="space-y-1">
      <AnimatePresence initial={false}>
        {claims.map((claim, index) => {
          const active = index === selected;
          const reworded = claim.revised && firstDraft[index] && firstDraft[index] !== claim.text;
          return (
            <motion.li
              key={index}
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, delay: index * 0.07, ease: [0.2, 0.7, 0.2, 1] }}
            >
              <button
                type="button"
                onClick={() => onSelect(index)}
                aria-pressed={active}
                className={`group grid w-full grid-cols-[2.25rem_1fr] gap-x-2 rounded-md border-l-2 py-4 pr-4 text-left transition-colors duration-200 ${
                  active ? "border-ink bg-paper-deep" : "border-transparent hover:bg-paper-deep/60"
                }`}
              >
                <span className="label pt-1.5 text-right text-ink-faint tabular-nums">
                  {String(index + 1).padStart(2, "0")}
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
                      className="block font-serif text-[1.375rem] leading-[1.3] text-ink"
                    >
                      {claim.text}
                    </motion.span>
                  </AnimatePresence>
                  <span className="mt-2.5 flex min-h-6 flex-wrap items-center gap-x-3 gap-y-1">
                    {claim.label && <Stamp key={`${claim.label}-${claim.text}`} label={claim.label} />}
                    {!claim.label && <span className="label text-ink-faint">{status(claim)}</span>}
                    <span className="label text-ink-faint normal-case tracking-normal">
                      {claim.host}
                    </span>
                    {reworded && (
                      <span className="label text-ink-faint" title={`First draft: ${firstDraft[index]}`}>
                        reworded to match its quote
                      </span>
                    )}
                  </span>
                  {claim.label && claim.label !== "supported" && claim.reason && (
                    <span className="mt-2 block text-sm leading-relaxed text-ink-soft">
                      {claim.reason}
                    </span>
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
