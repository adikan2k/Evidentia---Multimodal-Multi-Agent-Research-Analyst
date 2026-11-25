"use client";

import { useState } from "react";
import { Mark } from "@/components/Mark";
import { type AuditLabel, LABEL_MARK, LABEL_MEANING, LABEL_ORDER, LABEL_TEXT, LABEL_TONE } from "@/lib/audit";

// Fills for the bars only, checked with the dataviz validator (light, on white): lightness band,
// chroma floor, colour-blind separation and the normal-vision floor all pass for the five hued
// labels in bar order. Amber falls under 3:1 against white, so every segment also carries its
// mark in the legend and the counts are in the table. Text keeps the ink tones in LABEL_TONE.
// Shares written on a segment are in ink, which is 4.5:1 or more on every fill but purple.
const FILL: Record<AuditLabel, string> = {
  contradicted: "#8f5aa6",
  not_found: "#d4553f",
  dead_link: "#d4553f", // drawn hatched, so it never relies on colour alone
  partial: "#d49a28",
  needs_human: "#3c86c2",
  supported: "#3f9a5c",
  unchecked: "#9a978e",
  citation_unread: "#bcb9b0",
  uncited: "#dddad2",
};
const HATCHED: AuditLabel[] = ["dead_link"];

export type BarRow = { name: string; detail: string; counts: Partial<Record<AuditLabel, number>> };

function fillStyle(label: AuditLabel): React.CSSProperties {
  if (!HATCHED.includes(label)) return { background: FILL[label] };
  return {
    background: `repeating-linear-gradient(135deg, ${FILL[label]} 0 3px, #ffffff 3px 6px)`,
  };
}

/**
 * One bar per tool over all its claims, split by label. A segment wide enough carries its share;
 * every segment shows its count and meaning on hover or focus, and the table holds them all.
 */
export function LabelBars({ rows }: { rows: BarRow[] }) {
  const [hover, setHover] = useState<{ row: number; label: AuditLabel } | null>(null);
  const present = LABEL_ORDER.filter((label) => rows.some((r) => (r.counts[label] ?? 0) > 0));
  const total = (r: BarRow) => present.reduce((s, l) => s + (r.counts[l] ?? 0), 0);
  const noted = hover === null ? null : { row: rows[hover.row], label: hover.label };

  return (
    <figure>
      <div className="space-y-6">
        {rows.map((row, r) => (
          <div key={row.name}>
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4">
              <span className="font-medium text-ink">{row.name}</span>
              <span className="data text-ink-faint">{row.detail}</span>
            </div>
            <div className="flex h-9 w-full gap-[2px]">
              {present.map((label) => {
                const n = row.counts[label] ?? 0;
                if (!n) return null;
                const share = n / total(row);
                const on = hover?.row === r && hover.label === label;
                return (
                  <button
                    key={label}
                    type="button"
                    onMouseEnter={() => setHover({ row: r, label })}
                    onMouseLeave={() => setHover(null)}
                    onFocus={() => setHover({ row: r, label })}
                    onBlur={() => setHover(null)}
                    aria-label={`${row.name}: ${n} ${LABEL_TEXT[label].toLowerCase()}, ${Math.round(share * 100)}% of its claims`}
                    className={`relative h-full min-w-[3px] transition-opacity first:rounded-l-[4px] last:rounded-r-[4px] ${
                      hover && !on ? "opacity-55" : ""
                    }`}
                    style={{ width: `${share * 100}%`, ...fillStyle(label) }}
                  >
                    {share >= 0.07 && !HATCHED.includes(label) && (
                      <span
                        className={`data absolute inset-0 flex items-center justify-center ${
                          label === "contradicted" ? "text-white" : "text-ink"
                        }`}
                      >
                        {Math.round(share * 100)}%
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <figcaption className="label mt-4 min-h-12 font-normal text-ink-soft" aria-live="polite">
        {noted ? (
          <>
            <span className={`font-medium ${LABEL_TONE[noted.label]}`}>
              {noted.row.name}: {noted.row.counts[noted.label]} {LABEL_TEXT[noted.label].toLowerCase()}
            </span>{" "}
            of {total(noted.row).toLocaleString("en")} claims. {LABEL_MEANING[noted.label]}
          </>
        ) : (
          "Every claim each tool made, by the mark it got. Hover or tab to a segment for its count."
        )}
      </figcaption>

      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
        {present.map((label) => (
          <li key={label} className="label flex items-center gap-1.5 font-normal text-ink-soft">
            <span aria-hidden="true" className="inline-block size-3 rounded-[2px]" style={fillStyle(label)} />
            <Mark kind={LABEL_MARK[label]} className={LABEL_TONE[label]} />
            {LABEL_TEXT[label]}
          </li>
        ))}
      </ul>

      <details className="mt-5">
        <summary className="label cursor-pointer text-ink underline underline-offset-4">Show as a table</summary>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-ink">
                <th scope="col" className="data py-2 pr-6 font-normal text-ink-soft">
                  Mark
                </th>
                {rows.map((row) => (
                  <th key={row.name} scope="col" className="data py-2 pr-6 font-normal text-ink-soft">
                    {row.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {present.map((label) => (
                <tr key={label} className="border-b border-rule">
                  <td className="py-2 pr-6 text-ink">{LABEL_TEXT[label]}</td>
                  {rows.map((row) => {
                    const n = row.counts[label] ?? 0;
                    return (
                      <td key={row.name} className="py-2 pr-6 font-mono text-[0.875rem] tabular-nums text-ink-soft">
                        {n} ({Math.round((n / total(row)) * 100)}%)
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
