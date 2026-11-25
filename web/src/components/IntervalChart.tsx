"use client";

import { useState } from "react";

export type IntervalRow = {
  label: string;
  value: number;
  /** The 95% interval. Left out when the result file has none for this row. */
  low?: number;
  high?: number;
  /** Shown in the hover note, e.g. "282 of 305 claims". */
  detail?: string;
  /** Written on the chart under the name, always visible: the point of this row (D-053). */
  note?: string;
};

type Props = {
  rows: IntervalRow[];
  /** "bar" grows from zero and needs a zero-based axis. "dot" may use a narrower axis. */
  mark: "bar" | "dot";
  domain: [number, number];
  ticks: number[];
  /** How many decimal places to print. */
  decimals?: number;
  caption: string;
  /** A line drawn across every row at one value, with its label, e.g. a bar set in advance. */
  threshold?: { value: number; label: string };
};

/**
 * One measure for a handful of named things, each with its 95% interval. A single series, so it
 * is drawn in ink with no legend; names are on the rows and values in the right-hand column.
 */
export function IntervalChart({ rows, mark, domain, ticks, decimals = 3, caption, threshold }: Props) {
  const format = (value: number) => value.toFixed(decimals);
  const [hovered, setHovered] = useState<number | null>(null);
  const [min, max] = domain;
  const at = (value: number) => `${(Math.min(Math.max(value, min), max) - min) / (max - min) * 100}%`;
  const width = (from: number, to: number) => `${((to - from) / (max - min)) * 100}%`;
  const noted = hovered === null ? null : rows[hovered];
  const intervalOf = (row: IntervalRow) =>
    row.low === undefined || row.high === undefined
      ? ""
      : `, 95% interval ${format(row.low)} to ${format(row.high)}`;

  return (
    <figure>
      {/* On a phone the name sits above its track, so the track keeps the width. */}
      <div className="grid grid-cols-[1fr_4.5rem] items-center gap-x-4 sm:grid-cols-[minmax(9rem,16rem)_1fr_4.5rem]">
        {rows.map((row, index) => (
          <div
            key={row.label}
            className="col-span-full grid grid-cols-subgrid items-center gap-y-1 rounded py-2.5 transition-colors hover:bg-paper-deep"
            onMouseEnter={() => setHovered(index)}
            onMouseLeave={() => setHovered(null)}
            onFocus={() => setHovered(index)}
            onBlur={() => setHovered(null)}
            // biome-ignore lint: rows are focusable so the interval can be read without a mouse
            tabIndex={0}
            aria-label={`${row.label}: ${format(row.value)}${intervalOf(row)}`}
          >
            <span className="col-span-full pl-2 text-[0.9375rem] leading-snug text-ink sm:col-span-1">
              {row.label}
              {row.note && <span className="label block font-normal text-ink-soft">{row.note}</span>}
            </span>
            <span className="relative ml-2 block h-6 sm:ml-0">
              {ticks.map((tick) => (
                <span
                  key={tick}
                  className="absolute inset-y-[-0.625rem] w-px bg-rule"
                  style={{ left: at(tick) }}
                />
              ))}
              {threshold && (
                <span
                  className="absolute inset-y-[-0.625rem] border-l-2 border-dashed border-ink"
                  style={{ left: at(threshold.value) }}
                />
              )}
              {mark === "bar" && (
                <span
                  className="absolute top-1 h-3 rounded-r bg-ink"
                  style={{ left: at(min), width: width(min, row.value) }}
                />
              )}
              {/* The interval: a thin line from its low end to its high end. */}
              {row.low !== undefined && row.high !== undefined && (
                <span
                  className={`absolute h-0.5 bg-ink-soft ${mark === "bar" ? "top-5" : "top-[0.6875rem]"}`}
                  style={{ left: at(row.low), width: width(row.low, row.high) }}
                />
              )}
              {mark === "dot" && (
                <span
                  className="absolute top-1.5 size-3 -translate-x-1/2 rounded-full bg-ink ring-2 ring-paper"
                  style={{ left: at(row.value) }}
                />
              )}
            </span>
            <span className="pr-2 text-right font-mono text-[0.875rem] tabular-nums text-ink">
              {format(row.value)}
            </span>
          </div>
        ))}
        <span className="hidden sm:block" />
        <span className="relative mt-1 ml-2 block h-5 sm:ml-0">
          {threshold && (
            <span
              className="label absolute top-6 -translate-x-1/2 whitespace-nowrap text-ink"
              style={{ left: at(threshold.value) }}
            >
              {threshold.label}
            </span>
          )}
          {ticks.map((tick) => (
            <span
              key={tick}
              className="data absolute -translate-x-1/2 text-ink-faint"
              style={{ left: at(tick) }}
            >
              {format(tick)}
            </span>
          ))}
        </span>
        <span />
      </div>
      <figcaption className="label mt-4 min-h-12 max-w-[44rem] font-normal leading-relaxed text-ink-soft">
        {noted ? (
          <>
            <span className="font-medium text-ink">{noted.label}:</span> {format(noted.value)}
            {intervalOf(noted)}
            {noted.detail ? `. ${noted.detail}.` : "."}
          </>
        ) : (
          caption
        )}
      </figcaption>
    </figure>
  );
}
