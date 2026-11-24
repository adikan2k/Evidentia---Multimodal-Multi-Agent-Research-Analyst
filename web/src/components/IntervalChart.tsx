"use client";

import { useState } from "react";

export type IntervalRow = {
  label: string;
  value: number;
  low: number;
  high: number;
  /** Shown in the hover note, e.g. "282 of 305 claims". */
  detail?: string;
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
};

/**
 * One measure for a handful of named things, each with its 95% interval. A single series, so it
 * is drawn in ink with no legend; names are on the rows and values in the right-hand column.
 */
export function IntervalChart({ rows, mark, domain, ticks, decimals = 3, caption }: Props) {
  const format = (value: number) => value.toFixed(decimals);
  const [hovered, setHovered] = useState<number | null>(null);
  const [min, max] = domain;
  const at = (value: number) => `${(Math.min(Math.max(value, min), max) - min) / (max - min) * 100}%`;
  const width = (from: number, to: number) => `${((to - from) / (max - min)) * 100}%`;
  const noted = hovered === null ? null : rows[hovered];

  return (
    <figure>
      <div className="grid grid-cols-[minmax(9rem,16rem)_1fr_4.5rem] items-center gap-x-4">
        {rows.map((row, index) => (
          <div
            key={row.label}
            className="col-span-3 grid grid-cols-subgrid items-center rounded py-2.5 transition-colors hover:bg-paper-deep"
            onMouseEnter={() => setHovered(index)}
            onMouseLeave={() => setHovered(null)}
            onFocus={() => setHovered(index)}
            onBlur={() => setHovered(null)}
            // biome-ignore lint: rows are focusable so the interval can be read without a mouse
            tabIndex={0}
            aria-label={`${row.label}: ${format(row.value)}, 95% interval ${format(row.low)} to ${format(row.high)}`}
          >
            <span className="pl-2 text-sm leading-snug text-ink">{row.label}</span>
            <span className="relative block h-6">
              {ticks.map((tick) => (
                <span
                  key={tick}
                  className="absolute inset-y-[-0.625rem] w-px bg-rule"
                  style={{ left: at(tick) }}
                />
              ))}
              {mark === "bar" && (
                <span
                  className="absolute top-1 h-3 rounded-r bg-ink"
                  style={{ left: at(min), width: width(min, row.value) }}
                />
              )}
              {/* The interval: a thin line from its low end to its high end. */}
              <span
                className={`absolute h-0.5 bg-ink-soft ${mark === "bar" ? "top-5" : "top-[0.6875rem]"}`}
                style={{ left: at(row.low), width: width(row.low, row.high) }}
              />
              {mark === "dot" && (
                <span
                  className="absolute top-1.5 size-3 -translate-x-1/2 rounded-full bg-ink ring-2 ring-paper"
                  style={{ left: at(row.value) }}
                />
              )}
            </span>
            <span className="pr-2 text-right font-mono text-sm tabular-nums text-ink">
              {format(row.value)}
            </span>
          </div>
        ))}
        <span />
        <span className="relative mt-1 block h-5">
          {ticks.map((tick) => (
            <span
              key={tick}
              className="label absolute -translate-x-1/2 text-ink-faint"
              style={{ left: at(tick) }}
            >
              {format(tick)}
            </span>
          ))}
        </span>
        <span />
      </div>
      <figcaption className="mt-4 min-h-10 text-sm leading-relaxed text-ink-soft">
        {noted ? (
          <>
            <span className="text-ink">{noted.label}:</span> {format(noted.value)}, 95% interval{" "}
            {format(noted.low)} to {format(noted.high)}
            {noted.detail ? `. ${noted.detail}.` : "."}
          </>
        ) : (
          caption
        )}
      </figcaption>
    </figure>
  );
}
