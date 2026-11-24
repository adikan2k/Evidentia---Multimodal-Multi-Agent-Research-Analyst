"use client";

import { motion } from "motion/react";

/** The proofreader's marks (D-045). Each verdict has its own shape, so colour is never the
 *  only signal. */
export type MarkKind = "tick" | "tick-caret" | "cross" | "not-equal" | "question" | "dash" | "dots";

// Stroke paths on a 24 by 24 grid, in the order a pencil would draw them.
const PATHS: Record<MarkKind, string[]> = {
  tick: ["M4.5 12.5l5 5L19.5 6.5"],
  "tick-caret": ["M3 11.5l4.5 4.5L15 7.5", "M15.5 18.5l3-4 3 4"],
  cross: ["M6 6l12 12", "M18 6L6 18"],
  "not-equal": ["M5 9.5h14", "M5 14.5h14", "M15.5 5l-7 14"],
  question: ["M8.5 9a3.5 3.5 0 1 1 5.4 2.9c-1.2.8-1.9 1.5-1.9 3.1", "M12 18.6v.4"],
  dash: ["M6 12h12"],
  dots: ["M6 12h.5", "M11.75 12h.5", "M17.5 12h.5"],
};

type Props = { kind: MarkKind; className?: string; draw?: boolean };

/** One mark. With `draw`, it is drawn stroke by stroke, as a verdict arrives. */
export function Mark({ kind, className = "", draw = false }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className={`inline-block h-[1.15em] w-[1.15em] shrink-0 align-[-0.2em] ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth={2.4}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {PATHS[kind].map((d, i) =>
        draw ? (
          <motion.path
            key={d}
            d={d}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.32, delay: 0.1 + i * 0.22, ease: "easeOut" }}
          />
        ) : (
          <path key={d} d={d} />
        ),
      )}
    </svg>
  );
}
