"use client";

import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";

export type RecallSeries = {
  key: string;
  label: string;
  values: number[]; // one per k
  /** The one series the chart is about, drawn in ink; the others are context in grey. */
  emphasis?: boolean;
  /** For the grey lines: a dash pattern, so identity is never colour alone. */
  dash?: string;
};

type Props = {
  ks: readonly number[];
  series: RecallSeries[];
  /** What a perfect ranking would score at each k: drawn dashed and labelled. */
  ceiling: number[];
  caption: string;
};

const W = 640;
const H = 300;
const PAD = { top: 16, right: 178, bottom: 36, left: 44 };
// The context lines: 3.2 to 1 against the desk, the least a line in a chart needs, and still
// clearly lighter than the ink of the shipped search.
const GREY = "#86847d";

/**
 * Recall at each cut-off, one line per search (D-053). An emphasis chart: the shipped search in
 * ink, the others in grey with their own dash, and the best possible drawn dashed, so each line is
 * read against its ceiling, not against 1. Hover or focus a cut-off to read every value at it.
 */
export function RecallChart({ ks, series, ceiling, caption }: Props) {
  const [at, setAt] = useState<number | null>(null);
  const still = useReducedMotion();
  const maxK = ks[ks.length - 1];
  const x = (k: number) => PAD.left + ((k - ks[0]) / (maxK - ks[0])) * (W - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - v) * (H - PAD.top - PAD.bottom);
  const path = (values: number[]) => values.map((v, i) => `${i ? "L" : "M"}${x(ks[i])},${y(v)}`).join("");
  const shipped = series.find((s) => s.emphasis);
  const ordered = [...series.filter((s) => !s.emphasis), ...(shipped ? [shipped] : [])];
  const end = ks.length - 1;

  return (
    <figure>
      <ul className="label mb-4 flex flex-wrap gap-x-6 gap-y-2 font-normal text-ink-soft" aria-label="Legend">
        {ordered.map((s) => (
          <li key={s.key} className="flex items-center gap-2">
            <svg width="28" height="10" aria-hidden="true">
              <line
                x1="0"
                x2="28"
                y1="5"
                y2="5"
                stroke={s.emphasis ? "var(--ink)" : GREY}
                strokeWidth={s.emphasis ? 3 : 2}
                strokeDasharray={s.dash}
              />
            </svg>
            <span className={s.emphasis ? "font-medium text-ink" : ""}>{s.label}</span>
          </li>
        ))}
        <li className="flex items-center gap-2">
          <svg width="28" height="10" aria-hidden="true">
            <line x1="0" x2="28" y1="5" y2="5" stroke="var(--ink-soft)" strokeWidth={1.5} strokeDasharray="5 4" />
          </svg>
          Best possible
        </li>
      </ul>
      {/* On a narrow screen the chart keeps a readable size and scrolls inside this box. */}
      <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full min-w-[640px]"
        role="img"
        aria-label={`${caption} ${ordered
          .map((s) => `${s.label}: ${ks.map((k, i) => `${s.values[i].toFixed(2)} at ${k}`).join(", ")}`)
          .join("; ")}.`}
        onMouseLeave={() => setAt(null)}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--rule)" />
            <text x={PAD.left - 8} y={y(v) + 4} textAnchor="end" className="fill-ink-faint font-mono text-[12px]">
              {v.toFixed(2)}
            </text>
          </g>
        ))}
        {ks.map((k) => (
          <text key={k} x={x(k)} y={H - 12} textAnchor="middle" className="fill-ink-faint font-mono text-[12px]">
            top {k}
          </text>
        ))}
        {at !== null && (
          <line x1={x(ks[at])} x2={x(ks[at])} y1={PAD.top} y2={H - PAD.bottom} stroke="var(--ink-soft)" />
        )}
        <path d={path(ceiling)} fill="none" stroke="var(--ink-soft)" strokeWidth={1.5} strokeDasharray="5 4" />
        <text x={x(maxK) + 10} y={y(ceiling[end]) + 4} className="fill-ink-soft text-[13px]">
          Best possible
        </text>
        {ordered.map((s) => (
          <g key={s.key}>
            {s.dash ? (
              // A dashed line is drawn as it is: the draw-in animation works by rewriting the
              // dash pattern, which would erase the pattern that tells this line apart.
              <path
                d={path(s.values)}
                fill="none"
                stroke={GREY}
                strokeWidth={2}
                strokeDasharray={s.dash}
                strokeLinejoin="round"
              />
            ) : (
              <motion.path
                d={path(s.values)}
                fill="none"
                stroke={s.emphasis ? "var(--ink)" : GREY}
                strokeWidth={s.emphasis ? 3 : 2}
                strokeLinecap="round"
                strokeLinejoin="round"
                // Drawn once as it scrolls into view.
                initial={still ? false : { pathLength: 0 }}
                whileInView={{ pathLength: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.9, ease: "easeOut" }}
              />
            )}
            {s.values.map((v, i) => (
              <circle
                key={ks[i]}
                cx={x(ks[i])}
                cy={y(v)}
                r={s.emphasis ? 4.5 : 3}
                fill={s.emphasis ? "var(--ink)" : GREY}
                stroke="var(--paper)"
                strokeWidth={2}
              />
            ))}
          </g>
        ))}
        {shipped && (
          <text x={x(maxK) + 10} y={y(shipped.values[end]) + 16} className="fill-ink text-[13px] font-medium">
            {shipped.label}
          </text>
        )}
        {/* Wide hit areas, one per cut-off, for hover. */}
        {ks.map((k, i) => (
          <rect
            key={k}
            x={x(k) - 24}
            y={PAD.top}
            width={48}
            height={H - PAD.top - PAD.bottom}
            fill="transparent"
            onMouseEnter={() => setAt(i)}
          />
        ))}
      </svg>
      </div>
      <div className="mt-3 flex flex-wrap gap-2" aria-label="Read the values at a cut-off">
        {ks.map((k, i) => (
          <button
            key={k}
            type="button"
            onFocus={() => setAt(i)}
            onMouseEnter={() => setAt(i)}
            onClick={() => setAt(i)}
            aria-pressed={at === i}
            className={`label min-h-10 rounded-full border px-3 transition-colors ${
              at === i ? "border-ink bg-ink text-sheet" : "border-rule text-ink-soft hover:border-ink"
            }`}
          >
            Top {k}
          </button>
        ))}
      </div>
      <figcaption className="label mt-3 min-h-12 max-w-[44rem] font-normal leading-relaxed text-ink-soft">
        {at === null ? (
          caption
        ) : (
          <>
            <span className="font-medium text-ink">In the top {ks[at]}:</span>{" "}
            {ordered
              .slice()
              .reverse()
              .map((s) => `${s.label} ${s.values[at].toFixed(3)}`)
              .join(", ")}
            ; best possible {ceiling[at].toFixed(3)}.
          </>
        )}
      </figcaption>
    </figure>
  );
}
